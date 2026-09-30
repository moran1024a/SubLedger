<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { createPlan, getPlan, updatePlan } from '@/api/plans'
import { ApiError, type BillPlan, type BillPlanPayload } from '@/types/api'
import PageHeader from '@/components/common/PageHeader.vue'
import LoadingBlock from '@/components/common/LoadingBlock.vue'
import ErrorState from '@/components/common/ErrorState.vue'
import BillPlanForm from '@/components/billing/BillPlanForm.vue'
import { getFieldErrors } from '@/utils/apiErrors'

const route = useRoute()
const router = useRouter()
const id = computed(() => Number(route.params.id))
const plan = ref<BillPlan | null>(null)
const loading = ref(id.value > 0)
const submitting = ref(false)
const error = ref<ApiError | null>(null)
const scheduleChanged = ref(false)
const fieldErrors = ref<Record<string, string>>({})
async function load() {
  if (!id.value) return
  error.value = null
  try {
    plan.value = await getPlan(id.value)
  } catch (cause) {
    error.value =
      cause instanceof ApiError
        ? cause
        : new ApiError({ status: 0, code: 'NETWORK', message: '加载失败' })
  } finally {
    loading.value = false
  }
}
async function save(payload: BillPlanPayload) {
  fieldErrors.value = {}
  submitting.value = true
  try {
    if (id.value) {
      const old = plan.value!
      scheduleChanged.value =
        old.first_due_date !== payload.first_due_date ||
        old.cycle_type !== payload.cycle_type ||
        old.cycle_days !== payload.cycle_days
      const next = await updatePlan(id.value, payload)
      ElMessage.success(scheduleChanged.value ? '已保存，未来账单已重新生成' : '账单规则已保存')
      plan.value = next
      if (scheduleChanged.value) ElMessage.info('未来账单已有的无效标记可能已被清除')
    } else {
      const created = await createPlan(payload)
      ElMessage.success('账单规则已创建')
      await router.replace(`/plans/${created.id}`)
    }
  } catch (cause) {
    fieldErrors.value = getFieldErrors(cause)
    ElMessage.error(cause instanceof ApiError ? cause.message : '保存失败')
  } finally {
    submitting.value = false
  }
}
onMounted(load)
</script>

<template>
  <div class="page-container">
    <PageHeader :title="id ? '编辑账单规则' : '新建账单规则'" /><LoadingBlock
      v-if="loading"
    /><ErrorState
      v-else-if="error"
      :message="error.message"
      :request-id="error.requestId"
      @retry="load"
    /><el-card v-else
      ><BillPlanForm
        :plan="plan"
        :submitting="submitting"
        :field-errors="fieldErrors"
        @submit="save"
        @cancel="router.push('/plans')"
    /></el-card>
  </div>
</template>
