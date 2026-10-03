<script setup lang="ts">
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/card/style/css'
import 'element-plus/es/components/dialog/style/css'
import 'element-plus/es/components/form/style/css'
import 'element-plus/es/components/form-item/style/css'
import 'element-plus/es/components/input/style/css'
import 'element-plus/es/components/loading/style/css'
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'
import 'element-plus/es/components/option/style/css'
import 'element-plus/es/components/pagination/style/css'
import 'element-plus/es/components/select/style/css'
import 'element-plus/es/components/table/style/css'
import 'element-plus/es/components/table-column/style/css'

import {
  ElButton,
  ElCard,
  ElDialog,
  ElForm,
  ElFormItem,
  ElInput,
  ElLoading,
  ElOption,
  ElPagination,
  ElSelect,
  ElTable,
  ElTableColumn,
} from 'element-plus'
import { useQueryRequest } from '@/composables/useQueryRequest'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createUser, disableUser, enableUser, listUsers, resetUserPassword } from '@/api/users'
import { ApiError, type CurrentUser } from '@/types/api'
import PageHeader from '@/components/common/PageHeader.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import { asApiError, getFieldErrors, isUncertainWrite, writeErrorMessage } from '@/utils/apiErrors'
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'
import { useViewScope } from '@/composables/useViewScope'
import { useAuthStore } from '@/stores/auth'
import { formatDateTime } from '@/utils/format'
import OperationFeedback from '@/components/common/OperationFeedback.vue'

const users = ref<CurrentUser[]>([])
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
let applied = { q: '', is_active: undefined as boolean | undefined }
let requestSequence = 0
const loading = ref(true)
const error = ref<ApiError | null>(null)
const search = ref('')
const status = ref<'' | 'active' | 'inactive'>('')
const createVisible = ref(false)
const resetVisible = ref(false)
const createSaving = ref(false)
const resetSaving = ref(false)
const actionId = ref<number | null>(null)
const selected = ref<CurrentUser | null>(null)
const createForm = ref({ username: '', password: '', confirm: '' })
const createFieldErrors = ref<Record<string, string>>({})
const resetForm = ref({ password: '', confirm: '' })
const closing = ref(false)
const busy = computed(
  () => createSaving.value || resetSaving.value || actionId.value !== null || closing.value,
)
const { dirty, confirmDiscard } = useUnsavedChanges()
const auth = useAuthStore()
const identity = computed(() => `${auth.sessionVersion}:${auth.user?.id ?? ''}`)
const scope = useViewScope(() => identity.value)
const vLoading = ElLoading.directive
const operationMessage = ref('')
const createUncertain = ref(false)
const resetUncertain = reactive(new Set<number>())
const statusUncertain = reactive(new Set<number>())
const hasUncertain = computed(
  () => createUncertain.value || resetUncertain.size > 0 || statusUncertain.size > 0,
)
watch(
  [createForm, resetForm, createVisible, resetVisible],
  () => {
    dirty.value =
      (createVisible.value &&
        Boolean(
          createForm.value.username || createForm.value.password || createForm.value.confirm,
        )) ||
      (resetVisible.value && Boolean(resetForm.value.password || resetForm.value.confirm))
  },
  { deep: true, flush: 'sync' },
)
const dateText = (value: string) =>
  Number.isFinite(Date.parse(value)) ? formatDateTime(value, auth.user?.timezone) : '—'
const queryRequests = useQueryRequest()
async function load() {
  const signal = queryRequests.next()
  const current = scope.capture()
  const sequence = ++requestSequence
  loading.value = true
  error.value = null
  try {
    const result = await listUsers(
      { ...applied, page: page.value, page_size: pageSize.value },
      signal,
    )
    if (signal.aborted || sequence !== requestSequence || !current()) return
    total.value = result.total
    const lastPage = Math.max(1, Math.ceil(result.total / pageSize.value))
    if (page.value > lastPage) {
      page.value = lastPage
      await load()
      return
    }
    users.value = result.items
  } catch (cause) {
    if (signal.aborted || sequence !== requestSequence || !current()) return
    error.value = asApiError(cause, '无法连接服务器，请检查网络或服务状态。')
  } finally {
    if (!signal.aborted && sequence === requestSequence && current()) loading.value = false
  }
}
function query() {
  applied = {
    q: search.value.trim(),
    is_active: status.value ? status.value === 'active' : undefined,
  }
  page.value = 1
  void load()
}
function resize() {
  page.value = 1
  void load()
}
async function closeDialog(kind: 'create' | 'reset', done?: () => void) {
  if (busy.value) return
  closing.value = true
  const current = scope.capture()
  try {
    if (dirty.value && !(await confirmDiscard('有未提交的账户信息，确定放弃并关闭吗？'))) return
    if (!current()) return
    if (kind === 'create') {
      createVisible.value = false
      createForm.value = { username: '', password: '', confirm: '' }
      createFieldErrors.value = {}
    } else {
      resetVisible.value = false
      resetForm.value = { password: '', confirm: '' }
      selected.value = null
    }
    done?.()
  } finally {
    if (current()) closing.value = false
  }
}
const closeCreate = (done?: () => void) => closeDialog('create', done)
const closeReset = (done?: () => void) => closeDialog('reset', done)
async function openCreate() {
  if (busy.value || createVisible.value) return
  const current = scope.capture()
  if (resetVisible.value) {
    await closeReset()
    if (!current() || resetVisible.value) return
  }
  createForm.value = { username: '', password: '', confirm: '' }
  createFieldErrors.value = {}
  createVisible.value = true
}
async function confirmRetry(message: string) {
  await ElMessageBox.confirm(message, '确认再次提交', {
    type: 'warning',
    confirmButtonText: '继续提交',
    cancelButtonText: '取消',
  })
}
async function submitCreate() {
  if (busy.value) return
  if (
    !createForm.value.username.trim() ||
    createForm.value.password.length < 8 ||
    createForm.value.password !== createForm.value.confirm
  ) {
    ElMessage.error('请填写有效用户名，并确认至少 8 位且一致的密码')
    return
  }
  createSaving.value = true
  createFieldErrors.value = {}
  const current = scope.capture()
  const submitted = {
    username: createForm.value.username.trim(),
    password: createForm.value.password,
  }
  try {
    if (createUncertain.value)
      await confirmRetry(
        '上次创建结果待确认。请先查询用户名并核实是否已创建；存在的账户可重置密码。确定已核实并再次创建吗？',
      )
    if (!current()) return
    await createUser(submitted)
    if (!current()) return
    createVisible.value = false
    createForm.value = { username: '', password: '', confirm: '' }
    createUncertain.value = false
    operationMessage.value = ''
    ElMessage.success('普通用户已创建')
    await load()
  } catch (cause) {
    if (!current() || cause === 'cancel' || cause === 'close') return
    createFieldErrors.value = getFieldErrors(cause)
    createUncertain.value = isUncertainWrite(cause)
    operationMessage.value = writeErrorMessage(cause)
    if (createUncertain.value)
      operationMessage.value += '请查询用户名核实是否已创建；已存在的账户可重置密码。'
  } finally {
    if (current()) createSaving.value = false
  }
}
async function openReset(user: CurrentUser) {
  if (busy.value || user.id === 0 || (resetVisible.value && selected.value?.id === user.id)) return
  const current = scope.capture()
  if (createVisible.value) {
    await closeCreate()
    if (!current() || createVisible.value) return
  }
  if (resetVisible.value) {
    await closeReset()
    if (!current() || resetVisible.value) return
  }
  selected.value = user
  resetForm.value = { password: '', confirm: '' }
  resetVisible.value = true
}
async function submitReset() {
  if (busy.value || !selected.value || selected.value.id === 0) return
  if (resetForm.value.password.length < 8 || resetForm.value.password !== resetForm.value.confirm) {
    ElMessage.error('请确认至少 8 位且一致的新密码')
    return
  }
  resetSaving.value = true
  const current = scope.capture()
  const targetId = selected.value.id
  const submitted = resetForm.value.password
  try {
    if (resetUncertain.has(targetId))
      await confirmRetry(
        '上次密码重置结果待确认。请让用户尝试新密码；查询用户资料不能确认密码。确定已核实并再次重置吗？',
      )
    if (!current()) return
    await ElMessageBox.confirm('重置后该用户的现有会话将失效，需要重新登录。', '确认重置密码', {
      type: 'warning',
      confirmButtonText: '重置',
      cancelButtonText: '取消',
    })
    if (!current()) return
    await resetUserPassword(targetId, submitted)
    if (!current()) return
    resetVisible.value = false
    resetForm.value = { password: '', confirm: '' }
    resetUncertain.delete(targetId)
    operationMessage.value = ''
    ElMessage.success('密码已重置')
  } catch (cause) {
    if (!current() || cause === 'cancel' || cause === 'close') return
    if (isUncertainWrite(cause)) resetUncertain.add(targetId)
    operationMessage.value = writeErrorMessage(cause)
    if (resetUncertain.has(targetId))
      operationMessage.value += '请让用户尝试新密码；核实后再次重置会要求确认。'
  } finally {
    if (current()) resetSaving.value = false
  }
}
async function toggle(user: CurrentUser) {
  if (busy.value || user.id === 0) return
  actionId.value = user.id
  const current = scope.capture()
  const wasActive = user.is_active
  try {
    if (statusUncertain.has(user.id))
      await confirmRetry('上次停启结果待确认。请先重新查询账户状态并核对，确定已核实并再次提交吗？')
    if (!current()) return
    if (wasActive)
      await ElMessageBox.confirm(
        '该用户将无法继续登录，当前会话会失效，数据会保留，账单和提醒会停止，停用期间的历史不会补处理。',
        '确认停用用户',
        { type: 'warning', confirmButtonText: '停用', cancelButtonText: '取消' },
      )
    if (!current()) return
    if (wasActive) await disableUser(user.id)
    else await enableUser(user.id)
    if (!current()) return
    statusUncertain.delete(user.id)
    operationMessage.value = ''
    ElMessage.success(wasActive ? '用户已停用' : '用户已启用')
    await load()
  } catch (cause) {
    if (!current() || cause === 'cancel' || cause === 'close') return
    if (isUncertainWrite(cause)) statusUncertain.add(user.id)
    operationMessage.value = writeErrorMessage(cause)
  } finally {
    if (current()) actionId.value = null
  }
}
async function check() {
  if (busy.value) return
  const current = scope.capture()
  await load()
  if (current() && !error.value)
    operationMessage.value =
      '已读取当前账户列表，请核对用户名和状态。列表不能确认密码是否已重置；请让用户尝试新密码。再次提交会要求确认。'
}
watch([identity, () => auth.loading], ([session, authLoading], previous) => {
  if (session !== previous?.[0]) {
    queryRequests.cancel()
    requestSequence += 1
    users.value = []
    total.value = 0
    error.value = null
    loading.value = false
    createVisible.value = false
    resetVisible.value = false
    createForm.value = { username: '', password: '', confirm: '' }
    resetForm.value = { password: '', confirm: '' }
    selected.value = null
    createSaving.value = false
    resetSaving.value = false
    actionId.value = null
    closing.value = false
    createFieldErrors.value = {}
    createUncertain.value = false
    resetUncertain.clear()
    statusUncertain.clear()
    operationMessage.value = ''
  }
  if (!authLoading && auth.isAdmin) void load()
})
onMounted(load)
</script>

<template>
  <div class="page-container">
    <PageHeader title="用户管理" description="创建和维护普通账户"
      ><template #actions
        ><el-button type="primary" :disabled="busy" @click="openCreate"
          >创建普通用户</el-button
        ></template
      ></PageHeader
    ><OperationFeedback
      :message="operationMessage"
      action="重新查询并核对"
      :disabled="busy || loading"
      :loading="loading"
      @check="check"
    />
    <p v-if="hasUncertain" class="hint" role="status">
      此前有账户操作结果待确认。请查询用户名和状态；密码需让用户尝试新密码。核实后再次提交会要求确认。
    </p>
    <el-card
      ><p class="hint">以下时间按账户时区 {{ auth.user?.timezone || '当前时区' }} 显示。</p>
      <div class="filter-bar">
        <el-input
          v-model="search"
          maxlength="64"
          @keyup.enter="query"
          clearable
          placeholder="搜索用户名"
          style="max-width: 240px"
        /><el-select v-model="status" clearable placeholder="状态" style="width: 140px"
          ><el-option label="启用" value="active" /><el-option label="停用" value="inactive"
        /></el-select>
        <el-button type="primary" :disabled="busy" @click="query">查询</el-button
        ><el-button :loading="loading" :disabled="busy" @click="load">刷新</el-button>
      </div>
      <ErrorState
        v-if="error"
        :message="error.message"
        :request-id="error.requestId"
        @retry="load"
      /><EmptyState
        v-else-if="!loading && !total && !applied.q && applied.is_active === undefined"
        title="暂无普通用户"
      /><EmptyState v-else-if="!loading && !users.length" title="暂无匹配用户" /><el-table
        v-else
        v-loading="loading"
        class="desktop-users"
        :data="users"
        stripe
        ><el-table-column prop="id" label="ID" width="80" /><el-table-column
          prop="username"
          label="用户名"
          min-width="150"
        /><el-table-column label="角色" width="110"
          ><template #default="{ row }">{{
            row.role === 'admin' ? '管理员' : '普通用户'
          }}</template></el-table-column
        ><el-table-column label="状态" width="100"
          ><template #default="{ row }"
            ><StatusTag :active="row.is_active" /></template></el-table-column
        ><el-table-column label="创建时间" width="180"
          ><template #default="{ row }">{{ dateText(row.created_at) }}</template></el-table-column
        ><el-table-column label="更新时间" width="180"
          ><template #default="{ row }">{{ dateText(row.updated_at) }}</template></el-table-column
        ><el-table-column label="操作" fixed="right" width="250"
          ><template #default="{ row }"
            ><el-button link type="primary" @click="$router.push(`/admin/users/${row.id}`)"
              >查看</el-button
            ><template v-if="row.id !== 0"
              ><el-button link :disabled="busy" @click="openReset(row as CurrentUser)"
                >重置密码</el-button
              ><el-button
                link
                :type="row.is_active ? 'danger' : 'success'"
                :loading="actionId === row.id"
                :disabled="busy"
                @click="toggle(row as CurrentUser)"
                >{{ row.is_active ? '停用' : '启用' }}</el-button
              ></template
            ></template
          ></el-table-column
        ></el-table
      >
      <div v-if="!error && users.length" class="mobile-users" v-loading="loading">
        <article v-for="item in users" :key="item.id">
          <div class="user-heading">
            <strong>{{ item.username }}</strong
            ><StatusTag :active="item.is_active" />
          </div>
          <p>ID {{ item.id }} · {{ item.role === 'admin' ? '管理员' : '普通用户' }}</p>
          <p>创建：{{ dateText(item.created_at) }}</p>
          <p>更新：{{ dateText(item.updated_at) }}</p>
          <div class="user-actions">
            <el-button link type="primary" @click="$router.push(`/admin/users/${item.id}`)"
              >查看</el-button
            >
            <template v-if="item.id !== 0"
              ><el-button link :disabled="busy" @click="openReset(item)">重置密码</el-button
              ><el-button
                link
                :type="item.is_active ? 'danger' : 'success'"
                :loading="actionId === item.id"
                :disabled="busy"
                @click="toggle(item)"
                >{{ item.is_active ? '停用' : '启用' }}</el-button
              ></template
            >
          </div>
        </article>
      </div>
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        @current-change="load"
        @size-change="resize"
      /> </el-card
    ><el-dialog
      v-model="createVisible"
      title="创建普通用户"
      width="min(480px, 92vw)"
      :before-close="closeCreate"
      :close-on-click-modal="!busy"
      :close-on-press-escape="!busy"
      :show-close="!busy"
      ><el-form label-position="top" :disabled="busy"
        ><el-form-item label="用户名" :error="createFieldErrors.username"
          ><el-input v-model="createForm.username" /></el-form-item
        ><el-form-item label="初始密码" :error="createFieldErrors.password"
          ><el-input v-model="createForm.password" type="password" show-password /></el-form-item
        ><el-form-item label="确认密码"
          ><el-input
            v-model="createForm.confirm"
            type="password"
            show-password /></el-form-item></el-form
      ><template #footer
        ><p v-if="operationMessage" class="hint" role="status">{{ operationMessage }}</p>
        <div class="form-actions">
          <el-button :disabled="busy" @click="closeCreate()">取消</el-button
          ><el-button type="primary" :loading="createSaving" :disabled="busy" @click="submitCreate"
            >创建</el-button
          >
        </div></template
      ></el-dialog
    ><el-dialog
      v-model="resetVisible"
      title="重置用户密码"
      width="min(480px, 92vw)"
      :before-close="closeReset"
      :close-on-click-modal="!busy"
      :close-on-press-escape="!busy"
      :show-close="!busy"
      ><el-form label-position="top" :disabled="busy"
        ><el-form-item label="新密码"
          ><el-input v-model="resetForm.password" type="password" show-password /></el-form-item
        ><el-form-item label="确认密码"
          ><el-input
            v-model="resetForm.confirm"
            type="password"
            show-password /></el-form-item></el-form
      ><template #footer
        ><p v-if="operationMessage" class="hint" role="status">{{ operationMessage }}</p>
        <div class="form-actions">
          <el-button :disabled="busy" @click="closeReset()">取消</el-button
          ><el-button type="primary" :loading="resetSaving" :disabled="busy" @click="submitReset"
            >重置</el-button
          >
        </div></template
      ></el-dialog
    >
  </div>
</template>

<style scoped>
.hint,
.mobile-users p {
  color: var(--sl-text-muted);
  font-size: 13px;
}
.mobile-users {
  display: none;
}
.mobile-users article {
  padding: var(--sl-space-4, 16px) 0;
  border-bottom: 1px solid var(--sl-border);
  overflow-wrap: anywhere;
}
.user-heading,
.user-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--sl-space-3, 12px);
}
.user-heading {
  justify-content: space-between;
}
.el-pagination {
  margin-top: var(--sl-space-4, 16px);
  overflow-x: auto;
}
@media (max-width: 700px) {
  .desktop-users {
    display: none;
  }
  .mobile-users {
    display: block;
  }
}
</style>
