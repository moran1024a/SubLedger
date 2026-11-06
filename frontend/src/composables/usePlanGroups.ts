import { onMounted, ref } from 'vue'
import { listPlanGroups } from '@/api/planGroups'
import type { ApiError, BillPlanGroup } from '@/types/api'
import { asApiError } from '@/utils/apiErrors'
import { useQueryRequest } from './useQueryRequest'

export function usePlanGroups() {
  const groups = ref<BillPlanGroup[]>([])
  const loading = ref(true)
  const error = ref<ApiError | null>(null)
  const requests = useQueryRequest()
  async function reload() {
    const signal = requests.next()
    loading.value = true
    error.value = null
    try {
      const result = await listPlanGroups(signal)
      if (!signal.aborted) groups.value = result
    } catch (cause) {
      if (!signal.aborted) error.value = asApiError(cause)
    } finally {
      if (!signal.aborted) loading.value = false
    }
  }
  onMounted(reload)
  return { groups, loading, error, reload }
}
