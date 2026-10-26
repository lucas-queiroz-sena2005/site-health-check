import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import {
  useRunDetail,
  useRunHosts,
  useRunServices,
  useRunChecks,
  useRunHostDetail,
} from '../api/useScanResults'

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })
  return ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  )
}

describe('Orthogonal Flat Explorer Query Hooks', () => {
  let fetchMock: any

  beforeEach(() => {
    vi.restoreAllMocks()
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })

  describe('useRunDetail', () => {
    it('is disabled when runId is not provided', () => {
      const { result } = renderHook(() => useRunDetail(undefined), {
        wrapper: createWrapper(),
      })
      expect(result.current.fetchStatus).toBe('idle')
      expect(fetchMock).not.toHaveBeenCalled()
    })

    it('fetches run detail and summary metadata from /api/runs/:id', async () => {
      const mockRun = {
        id: 'run-123',
        status: 'COMPLETED',
        metrics_json: {
          total_targets_scanned: 10,
          scan_duration_seconds: 5.2,
          anomalies_found: 2,
          summary: {
            active: 8,
            warning: 1,
            failed: 1,
            ghost: 0,
            void: 0,
            service_count: 12,
            http_check_count: 15,
          },
        },
      }
      fetchMock.mockResolvedValueOnce({
        ok: true,
        json: async () => mockRun,
      })

      const { result } = renderHook(() => useRunDetail('run-123'), {
        wrapper: createWrapper(),
      })

      await waitFor(() => expect(result.current.isSuccess).toBe(true))
      expect(fetchMock).toHaveBeenCalledWith('/api/runs/run-123')
      expect(result.current.data?.metrics_json?.summary.service_count).toBe(12)
    })
  })

  describe('useRunHosts', () => {
    it('is disabled when runId is not provided', () => {
      const { result } = renderHook(() => useRunHosts(undefined), {
        wrapper: createWrapper(),
      })
      expect(result.current.fetchStatus).toBe('idle')
      expect(fetchMock).not.toHaveBeenCalled()
    })

    it('constructs query URL with orthogonal parameters for /api/runs/:id/hosts', async () => {
      const mockPage = {
        items: [
          {
            ip_address: '142.251.134.174',
            status: 'ok',
            depth: 0,
            vhost_count: 1,
            open_port_count: 2,
            scanned_port_count: 2,
            min_tcp_latency_ms: 45,
            min_tls_expires_days: 60,
            worst_tls_version: 'TLSv1.3',
            worst_http_status: 200,
            finding_codes: [],
          },
        ],
        total: 1,
        limit: 25,
        offset: 50,
      }
      fetchMock.mockResolvedValueOnce({
        ok: true,
        json: async () => mockPage,
      })

      const { result } = renderHook(
        () =>
          useRunHosts('run-123', {
            q: 'google',
            ip: '142.251',
            status: 'warning,failed',
            finding: 'TLS_EXPIRED',
            sort_by: 'min_tcp_latency_ms',
            sort_dir: 'desc',
            limit: 25,
            offset: 50,
          }),
        { wrapper: createWrapper() }
      )

      await waitFor(() => expect(result.current.isSuccess).toBe(true))
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/runs/run-123/hosts?q=google&ip=142.251&status=warning%2Cfailed&finding=TLS_EXPIRED&sort_by=min_tcp_latency_ms&sort_dir=desc&limit=25&offset=50'
      )
      expect(result.current.data?.items).toHaveLength(1)
      expect(result.current.data?.items[0].ip_address).toBe('142.251.134.174')
    })
  })

  describe('useRunServices', () => {
    it('constructs query URL with port and include_closed for /api/runs/:id/services', async () => {
      const mockPage = {
        items: [
          {
            ip_address: '142.251.134.174',
            port: 443,
            status: 'ok',
            depth: 0,
            tcp_latency_ms: 45,
            tls_valid: true,
            tls_expires_in_days: 60,
            tls_version: 'TLSv1.3',
            tls_issuer: 'Google Trust Services',
            san_count: 65,
            http_check_count: 2,
            worst_http_status: 200,
            finding_codes: [],
          },
        ],
        total: 1,
        limit: 50,
        offset: 0,
      }
      fetchMock.mockResolvedValueOnce({
        ok: true,
        json: async () => mockPage,
      })

      const { result } = renderHook(
        () =>
          useRunServices('run-123', {
            port: 443,
            include_closed: true,
            sort_by: 'port',
            sort_dir: 'asc',
          }),
        { wrapper: createWrapper() }
      )

      await waitFor(() => expect(result.current.isSuccess).toBe(true))
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/runs/run-123/services?port=443&include_closed=true&sort_by=port&sort_dir=asc'
      )
      expect(result.current.data?.items[0].port).toBe(443)
    })
  })

  describe('useRunChecks', () => {
    it('constructs query URL for /api/runs/:id/checks', async () => {
      const mockPage = {
        items: [
          {
            ip_address: '142.251.134.174',
            port: 80,
            domain: 'google.com',
            status: 'ok',
            status_code: 301,
            http_latency_ms: 32,
            redirects_to_url: 'https://www.google.com/',
            server_header: 'gws',
            notes: null,
            finding_code: null,
          },
        ],
        total: 1,
        limit: 50,
        offset: 0,
      }
      fetchMock.mockResolvedValueOnce({
        ok: true,
        json: async () => mockPage,
      })

      const { result } = renderHook(
        () =>
          useRunChecks('run-123', {
            finding: 'HTTP_5XX',
          }),
        { wrapper: createWrapper() }
      )

      await waitFor(() => expect(result.current.isSuccess).toBe(true))
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/runs/run-123/checks?finding=HTTP_5XX'
      )
      expect(result.current.data?.items[0].domain).toBe('google.com')
    })
  })

  describe('useRunHostDetail', () => {
    it('is disabled when either runId or ip is missing', () => {
      const { result: res1 } = renderHook(() => useRunHostDetail('run-123', null), {
        wrapper: createWrapper(),
      })
      expect(res1.current.fetchStatus).toBe('idle')

      const { result: res2 } = renderHook(() => useRunHostDetail(undefined, '8.8.8.8'), {
        wrapper: createWrapper(),
      })
      expect(res2.current.fetchStatus).toBe('idle')
      expect(fetchMock).not.toHaveBeenCalled()
    })

    it('fetches full HostDetailDTO from /api/runs/:id/hosts/:ip', async () => {
      const mockDetail = {
        ip_address: '8.8.8.8',
        status: 'ok',
        depth: 0,
        root_target: 'dns.google',
        resolved_domains: ['dns.google'],
        discovered_from: [],
        open_port_count: 2,
        scanned_port_count: 2,
        vhost_count: 1,
        min_tcp_latency_ms: 22,
        min_tls_expires_days: 45,
        worst_tls_version: 'TLSv1.3',
        worst_http_status: 200,
        finding_codes: [],
        tls_sans: ['dns.google', '8888.google'],
        services: [
          {
            port_number: 443,
            tcp_status: 'open',
            tcp_latency_ms: 22,
            status: 'ok',
            san_count: 2,
            http_check_count: 1,
            worst_http_status: 200,
            finding_codes: [],
            tls_certificate: {
              valid: true,
              expires_in_days: 45,
              issuer: 'Google Trust Services',
              protocol_version: 'TLSv1.3',
              domains_discovered_sans_json: ['dns.google', '8888.google'],
            },
          },
        ],
        checks: [
          {
            port: 443,
            domain: 'dns.google',
            status: 'ok',
            status_code: 200,
            http_latency_ms: 30,
            redirects_to_url: null,
            server_header: 'gws',
            notes: null,
            finding_code: null,
          },
        ],
      }
      fetchMock.mockResolvedValueOnce({
        ok: true,
        json: async () => mockDetail,
      })

      const { result } = renderHook(() => useRunHostDetail('run-123', '8.8.8.8'), {
        wrapper: createWrapper(),
      })

      await waitFor(() => expect(result.current.isSuccess).toBe(true))
      expect(fetchMock).toHaveBeenCalledWith('/api/runs/run-123/hosts/8.8.8.8')
      expect(result.current.data?.ip_address).toBe('8.8.8.8')
      expect(result.current.data?.tls_sans).toEqual(['dns.google', '8888.google'])
      expect(result.current.data?.services[0].port_number).toBe(443)
    })
  })
})
