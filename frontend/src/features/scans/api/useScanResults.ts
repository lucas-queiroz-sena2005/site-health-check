import { useQuery } from '@tanstack/react-query'
import { scanQueryKeys } from './queryKeys'
import type {
  HostDetailDTO,
  HostRowDTO,
  HttpCheckRowDTO,
  Page,
  ScanRunResponse,
  ServiceRowDTO,
  TableQueryParams,
} from '../types'

function buildQueryString(params?: TableQueryParams): string {
  if (!params) return ''
  const searchParams = new URLSearchParams()
  if (params.q) searchParams.set('q', params.q)
  if (params.ip) searchParams.set('ip', params.ip)
  if (params.status) searchParams.set('status', params.status)
  if (params.port !== undefined && params.port !== null) searchParams.set('port', String(params.port))
  if (params.finding) searchParams.set('finding', params.finding)
  if (params.include_closed !== undefined) searchParams.set('include_closed', String(params.include_closed))
  if (params.sort_by) searchParams.set('sort_by', params.sort_by)
  if (params.sort_dir) searchParams.set('sort_dir', params.sort_dir)
  if (params.limit !== undefined && params.limit !== null) searchParams.set('limit', String(params.limit))
  if (params.offset !== undefined && params.offset !== null) searchParams.set('offset', String(params.offset))

  const qs = searchParams.toString()
  return qs ? `?${qs}` : ''
}

export function useRunDetail(runId?: string) {
  return useQuery<ScanRunResponse>({
    queryKey: scanQueryKeys.detail(runId),
    queryFn: async () => {
      const res = await fetch(`/api/runs/${runId}`)
      if (!res.ok) {
        throw new Error(`Failed to fetch run details for ${runId}`)
      }
      return res.json()
    },
    enabled: Boolean(runId),
  })
}

export function useRunHosts(runId?: string, params?: TableQueryParams) {
  return useQuery<Page<HostRowDTO>>({
    queryKey: scanQueryKeys.hosts(runId, params),
    queryFn: async () => {
      const qs = buildQueryString(params)
      const res = await fetch(`/api/runs/${runId}/hosts${qs}`)
      if (!res.ok) {
        throw new Error(`Failed to fetch hosts for run ${runId}`)
      }
      return res.json()
    },
    enabled: Boolean(runId),
  })
}

export function useRunServices(runId?: string, params?: TableQueryParams) {
  return useQuery<Page<ServiceRowDTO>>({
    queryKey: scanQueryKeys.services(runId, params),
    queryFn: async () => {
      const qs = buildQueryString(params)
      const res = await fetch(`/api/runs/${runId}/services${qs}`)
      if (!res.ok) {
        throw new Error(`Failed to fetch services for run ${runId}`)
      }
      return res.json()
    },
    enabled: Boolean(runId),
  })
}

export function useRunChecks(runId?: string, params?: TableQueryParams) {
  return useQuery<Page<HttpCheckRowDTO>>({
    queryKey: scanQueryKeys.checks(runId, params),
    queryFn: async () => {
      const qs = buildQueryString(params)
      const res = await fetch(`/api/runs/${runId}/checks${qs}`)
      if (!res.ok) {
        throw new Error(`Failed to fetch HTTP checks for run ${runId}`)
      }
      return res.json()
    },
    enabled: Boolean(runId),
  })
}

export function useRunHostDetail(runId?: string, ip?: string | null) {
  return useQuery<HostDetailDTO>({
    queryKey: scanQueryKeys.hostDetail(runId, ip),
    queryFn: async () => {
      const res = await fetch(`/api/runs/${runId}/hosts/${ip}`)
      if (!res.ok) {
        throw new Error(`Failed to fetch host detail for IP ${ip} in run ${runId}`)
      }
      return res.json()
    },
    enabled: Boolean(runId && ip),
  })
}
