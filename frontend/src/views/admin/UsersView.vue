<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createUser,
  disableUser,
  enableUser,
  getAdminSummary,
  listUsers,
  resetUserPassword,
} from '@/api/users'
import { ApiError, type CurrentUser } from '@/types/api'
import PageHeader from '@/components/common/PageHeader.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import { getFieldErrors } from '@/utils/apiErrors'

const users = ref<CurrentUser[]>([])
const maxUsers = ref<number | null>(null)
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
const filtered = computed(() =>
  users.value.filter(
    (user) =>
      (!search.value || user.username.toLowerCase().includes(search.value.toLowerCase())) &&
      (!status.value || (status.value === 'active' ? user.is_active : !user.is_active)),
  ),
)
async function load() {
  loading.value = true
  error.value = null
  try {
    const [loadedUsers, summary] = await Promise.all([listUsers(), getAdminSummary()])
    users.value = loadedUsers
    maxUsers.value = summary.max_users
  } catch (cause) {
    error.value =
      cause instanceof ApiError
        ? cause
        : new ApiError({
            status: 0,
            code: 'NETWORK',
            message: '无法连接服务器，请检查网络或服务状态。',
          })
  } finally {
    loading.value = false
  }
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
        ><el-button
          type="primary"
          :disabled="maxUsers !== null && users.length >= maxUsers"
          @click="openCreate"
          >创建普通用户</el-button
        ></template
      ></PageHeader
    ><el-card
      ><div class="filters">
        <el-input
          v-model="search"
          clearable
          placeholder="搜索用户名"
          style="max-width: 240px"
        /><el-select v-model="status" clearable placeholder="状态" style="width: 140px"
          ><el-option label="启用" value="active" /><el-option label="停用" value="inactive"
        /></el-select>
      </div>
      <ErrorState
        v-if="error"
        :message="error.message"
        :request-id="error.requestId"
        @retry="load"
      /><EmptyState
        v-else-if="!loading && users.length === 1 && users[0]?.id === 0"
        title="暂无普通用户"
      /><EmptyState
        v-else-if="!loading && !filtered.length"
        title="暂无匹配用户"
      /><el-table v-else v-loading="loading" :data="filtered" stripe
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
              ><el-button link :disabled="actionId !== null" @click="openReset(row)"
                >重置密码</el-button
              ><el-button
                link
                :type="row.is_active ? 'danger' : 'success'"
                :loading="actionId === row.id"
                :disabled="actionId !== null"
                @click="toggle(row)"
                >{{
                row.is_active ? '停用' : '启用'
              }}</el-button></template
            ></template
          ></el-table-column
        ></el-table
      ></el-card
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
