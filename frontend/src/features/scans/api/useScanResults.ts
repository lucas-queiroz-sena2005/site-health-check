import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { scanQueryKeys } from './queryKeys'
import { type ScanResult } from '../types'

export function useScanSummary(runId?: string) {
  return useQuery({
    queryKey: scanQueryKeys.results({ runId, type: 'summary' }),
    queryFn: async () => {
      if (!runId) return null
      
      const url = `/api/results/summary?run_id=${runId}`
      const res = await fetch(url)
      if (!res.ok) {
        throw new Error('Network response was not ok')
      }
      
      return await res.json()
    },
    enabled: !!runId
  })
}

export function useScanResults(runId?: string) {
  const queryClient = useQueryClient()
  
  const query = useQuery({
    queryKey: scanQueryKeys.results({ runId }),
    queryFn: async () => {
      if (!runId) return null
      // By default, just fetch empty hosts, since we rely on summaries first
      const data: ScanResult = {
        id: runId,
        timestamp: new Date().toISOString(),
        hosts: [],
        metadata: {}
      }
      return data
    },
    enabled: !!runId
  })

  const fetchSubrun = useMutation({
    mutationFn: async (subrunId: string) => {
      if (!runId) throw new Error('No runId')
      const url = `/api/results?run_id=${runId}&subrun_id=${encodeURIComponent(subrunId)}`
      const res = await fetch(url)
      if (!res.ok) throw new Error('Network error')
      return await res.json()
    },
    onSuccess: (newHosts) => {
      queryClient.setQueryData(scanQueryKeys.results({ runId }), (oldData: any) => {
        if (!oldData) return oldData
        // Append new hosts and deduplicate by ip_address just in case
        const existingHostIds = new Set(oldData.hosts.map((h: any) => h.id))
        const filteredNewHosts = newHosts.filter((h: any) => !existingHostIds.has(h.id))
        return {
          ...oldData,
          hosts: [...oldData.hosts, ...filteredNewHosts]
        }
      })
    }
  })

  return { ...query, fetchSubrun }
}
