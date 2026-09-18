import { useQuery } from '@tanstack/react-query'
import { scanQueryKeys } from './queryKeys'
import { type ScanResult } from '../types'

export function useScanResults(runId?: string) {
  return useQuery({
    queryKey: scanQueryKeys.results({ runId }),
    queryFn: async () => {
      if (!runId) return null
      
      const url = `/api/runs/${runId}/results`
      const res = await fetch(url)
      if (!res.ok) {
        throw new Error('Network response was not ok')
      }
      
      const rawData = await res.json()
      
      const data: ScanResult = {
        id: runId,
        timestamp: new Date().toISOString(),
        hosts: rawData.results || []
      }
      
      return data
    },
    enabled: !!runId
  })
}
