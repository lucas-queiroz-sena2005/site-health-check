export const scanQueryKeys = {
  all: ['scans'] as const,
  results: (filters?: Record<string, unknown>) => [...scanQueryKeys.all, 'results', filters] as const,
}
