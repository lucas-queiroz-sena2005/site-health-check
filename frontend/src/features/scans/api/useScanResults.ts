import { useQuery } from '@tanstack/react-query'
import { scanQueryKeys } from './queryKeys'
import { type ScanResult, type HostState } from '../types'

export function useScanResults(runId?: string) {
  return useQuery({
    queryKey: scanQueryKeys.results({ runId }),
    queryFn: async () => {
      // Mocking fetch from local engine file instead of real API
      const url = '/results-sca2n.json'
      const res = await fetch(url)
      if (!res.ok) {
        throw new Error('Network response was not ok')
      }
      
      const rawMap = await res.json()
      
      // The engine raw file is a Record<ip, data> but the API returns HostState[]
      // Let's map it into the format the UI expects:
      const mockHosts: HostState[] = Object.entries(rawMap).map(([ip, data]: [string, any]) => ({
        ...data,
        ip_address: ip
      }))
      
      const data: ScanResult = {
        id: 'mock-engine-data',
        timestamp: new Date().toISOString(),
        hosts: mockHosts
      }
      
      return data
    },
  })
}
