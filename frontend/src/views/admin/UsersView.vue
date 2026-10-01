<script setup lang="ts">
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/card/style/css'
import 'element-plus/es/components/dialog/style/css'
import 'element-plus/es/components/form/style/css'
import 'element-plus/es/components/form-item/style/css'
import 'element-plus/es/components/input/style/css'
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
  ElOption,
  ElPagination,
  ElSelect,
  ElTable,
  ElTableColumn,
} from 'element-plus'
import { useQueryRequest } from '@/composables/useQueryRequest'
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createUser, disableUser, enableUser, listUsers, resetUserPassword } from '@/api/users'
import { ApiError, type CurrentUser } from '@/types/api'
import PageHeader from '@/components/common/PageHeader.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import { asApiError, getFieldErrors } from '@/utils/apiErrors'

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
const queryRequests = useQueryRequest()
async function load() {
  const signal = queryRequests.next()
  const sequence = ++requestSequence
  loading.value = true
  error.value = null
  try {
    const result = await listUsers(
      { ...applied, page: page.value, page_size: pageSize.value },
      signal,
    )
    if (signal.aborted || sequence !== requestSequence) return
    total.value = result.total
    const lastPage = Math.max(1, Math.ceil(result.total / pageSize.value))
    if (page.value > lastPage) {
      page.value = lastPage
      await load()
      return
    }
    users.value = result.items
  } catch (cause) {
    if (signal.aborted || sequence !== requestSequence) return
    error.value = asApiError(cause, '无法连接服务器，请检查网络或服务状态。')
  } finally {
    if (!signal.aborted && sequence === requestSequence) loading.value = false
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
function openCreate() {
  createForm.value = { username: '', password: '', confirm: '' }
  createFieldErrors.value = {}
  createVisible.value = true
}
async function submitCreate() {
  if (
    !createForm.value.username.trim() ||
    createForm.value.password.length < 8 ||
    createForm.value.password !== createForm.value.confirm
  ) {
    ElMessage.error('请填写有效用户名，并确认至少 8 位且一致的密码')
    return
  }
  createFieldErrors.value = {}
  createSaving.value = true
  try {
    await createUser({
      username: createForm.value.username.trim(),
      password: createForm.value.password,
    })
    createVisible.value = false
    ElMessage.success('普通用户已创建')
    await load()
  } catch (cause) {
    createFieldErrors.value = getFieldErrors(cause)
    ElMessage.error(cause instanceof ApiError ? cause.message : '创建失败')
  } finally {
    createSaving.value = false
  }
}
function openReset(user: CurrentUser) {
  selected.value = user
  resetForm.value = { password: '', confirm: '' }
  resetVisible.value = true
}
async function submitReset() {
  if (resetForm.value.password.length < 8 || resetForm.value.password !== resetForm.value.confirm) {
    ElMessage.error('请确认至少 8 位且一致的新密码')
    return
  }
  if (!selected.value) return
  try {
    await ElMessageBox.confirm('重置后该用户的现有会话将失效，需要重新登录。', '确认重置密码', {
      type: 'warning',
      confirmButtonText: '重置',
      cancelButtonText: '取消',
    })
    resetSaving.value = true
    await resetUserPassword(selected.value.id, resetForm.value.password)
    resetVisible.value = false
    ElMessage.success('密码已重置')
  } catch (cause) {
    if (cause !== 'cancel' && cause !== 'close')
      ElMessage.error(cause instanceof ApiError ? cause.message : '重置失败')
  } finally {
    resetSaving.value = false
  }
}
async function toggle(user: CurrentUser) {
  if (actionId.value !== null) return
  const wasActive = user.is_active
  try {
    if (wasActive)
      await ElMessageBox.confirm(
        '该用户将无法继续登录，当前会话会失效，数据会保留，账单和提醒会停止，停用期间的历史不会补处理。',
        '确认停用用户',
        { type: 'warning', confirmButtonText: '停用', cancelButtonText: '取消' },
      )
    actionId.value = user.id
    if (wasActive) await disableUser(user.id)
    else await enableUser(user.id)
    ElMessage.success(wasActive ? '用户已停用' : '用户已启用')
    await load()
  } catch (cause) {
    if (cause !== 'cancel' && cause !== 'close')
      ElMessage.error(cause instanceof ApiError ? cause.message : '操作失败')
  } finally {
    actionId.value = null
  }
}
onMounted(load)
</script>

<template>
  <div class="page-container">
    <PageHeader title="用户管理" description="创建和维护普通账户"
      ><template #actions
        ><el-button type="primary" @click="openCreate">创建普通用户</el-button></template
      ></PageHeader
    ><el-card
      ><div class="filters">
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
        <el-button type="primary" @click="query">查询</el-button>
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
          ><template #default="{ row }">{{
            new Date(row.created_at).toLocaleString()
          }}</template></el-table-column
        ><el-table-column label="更新时间" width="180"
          ><template #default="{ row }">{{
            new Date(row.updated_at).toLocaleString()
          }}</template></el-table-column
        ><el-table-column label="操作" fixed="right" width="250"
          ><template #default="{ row }"
            ><el-button link type="primary" @click="$router.push(`/admin/users/${row.id}`)"
              >查看</el-button
            ><template v-if="row.id !== 0"
              ><el-button link :disabled="actionId !== null" @click="openReset(row as CurrentUser)"
                >重置密码</el-button
              ><el-button
                link
                :type="row.is_active ? 'danger' : 'success'"
                :loading="actionId === row.id"
                :disabled="actionId !== null"
                @click="toggle(row as CurrentUser)"
                >{{ row.is_active ? '停用' : '启用' }}</el-button
              ></template
            ></template
          ></el-table-column
        ></el-table
      >
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        @current-change="load"
        @size-change="resize"
      /> </el-card
    ><el-dialog v-model="createVisible" title="创建普通用户" width="min(480px, 92vw)"
      ><el-form label-position="top"
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
        ><el-button @click="createVisible = false">取消</el-button
        ><el-button type="primary" :loading="createSaving" @click="submitCreate"
          >创建</el-button
        ></template
      ></el-dialog
    ><el-dialog v-model="resetVisible" title="重置用户密码" width="min(480px, 92vw)"
      ><el-form label-position="top"
        ><el-form-item label="新密码"
          ><el-input v-model="resetForm.password" type="password" show-password /></el-form-item
        ><el-form-item label="确认密码"
          ><el-input
            v-model="resetForm.confirm"
            type="password"
            show-password /></el-form-item></el-form
      ><template #footer
        ><el-button @click="resetVisible = false">取消</el-button
        ><el-button type="primary" :loading="resetSaving" @click="submitReset"
          >重置</el-button
        ></template
      ></el-dialog
    >
  </div>
</template>

<style scoped>
.filters {
  display: flex;
  gap: 10px;
  margin-bottom: 18px;
  flex-wrap: wrap;
}
</style>
