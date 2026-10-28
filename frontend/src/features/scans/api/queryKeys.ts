import type { TableQueryParams } from '../types'

export const scanQueryKeys = {
  all: ['runs'] as const,
  detail: (id?: string) => [...scanQueryKeys.all, 'detail', id] as const,
  hosts: (id?: string, params?: TableQueryParams) => [...scanQueryKeys.all, id, 'hosts', params] as const,
  services: (id?: string, params?: TableQueryParams) => [...scanQueryKeys.all, id, 'services', params] as const,
  checks: (id?: string, params?: TableQueryParams) => [...scanQueryKeys.all, id, 'checks', params] as const,
  hostDetail: (id?: string, ip?: string | null) => [...scanQueryKeys.all, id, 'hosts', ip] as const,
  history: () => [...scanQueryKeys.all, 'history'] as const,
}
