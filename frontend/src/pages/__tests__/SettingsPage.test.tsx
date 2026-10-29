import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { SettingsPage } from '../SettingsPage'

describe('SettingsPage', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    })
    vi.restoreAllMocks()
  })

  it('renders system storage metrics from GET /api/system/settings', async () => {
    vi.spyOn(global, 'fetch').mockImplementation(async (url: any) => {
      if (String(url).includes('/api/system/settings')) {
        return {
          ok: true,
          json: async () => ({
            retention_days: 14,
            db_size_bytes: 5242880, // 5 MB
            total_runs: 42,
            total_hosts: 1250,
            total_scans: 3,
          }),
        } as Response
      }
      return { ok: true, json: async () => ({}) } as Response
    })

    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>
    )

    expect(await screen.findByText('42')).toBeTruthy()
    expect(screen.getByText('1250')).toBeTruthy()
    expect(screen.getByText('3')).toBeTruthy()
    expect(screen.getByText(/5(\.0)? MB/)).toBeTruthy()
  })

  it('saves retention policy with PUT /api/system/settings', async () => {
    let putBody: any = null

    vi.spyOn(global, 'fetch').mockImplementation(async (url: any, init?: any) => {
      if (String(url).includes('/api/system/settings')) {
        if (init?.method === 'PUT') {
          putBody = JSON.parse(init.body)
          return {
            ok: true,
            json: async () => ({
              retention_days: putBody.retention_days,
              db_size_bytes: 1048576,
              total_runs: 10,
              total_hosts: 100,
              total_scans: 1,
            }),
          } as Response
        }
        return {
          ok: true,
          json: async () => ({
            retention_days: 0,
            db_size_bytes: 1048576,
            total_runs: 10,
            total_hosts: 100,
            total_scans: 1,
          }),
        } as Response
      }
      return { ok: true, json: async () => ({}) } as Response
    })

    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>
    )

    // Wait for initial fetch to populate the card metrics
    await screen.findByText('10')
    const input = screen.getByLabelText(/retention period/i)
    fireEvent.change(input, { target: { value: '30' } })

    const saveBtn = screen.getByRole('button', { name: /save retention policy/i })
    fireEvent.click(saveBtn)

    await waitFor(() => {
      expect(putBody).toEqual({ retention_days: 30 })
    })
  })

  it('triggers purge history flow calling POST /api/system/purge-runs', async () => {
    let purgeCalled = false

    vi.spyOn(global, 'fetch').mockImplementation(async (url: any, init?: any) => {
      if (String(url).includes('/api/system/purge-runs')) {
        purgeCalled = true
        return {
          ok: true,
          json: async () => ({ message: 'Successfully purged 10 runs', purged_count: 10 }),
        } as Response
      }
      if (String(url).includes('/api/system/settings')) {
        return {
          ok: true,
          json: async () => ({
            retention_days: 0,
            db_size_bytes: 1048576,
            total_runs: 10,
            total_hosts: 100,
            total_scans: 1,
          }),
        } as Response
      }
      return { ok: true, json: async () => ({}) } as Response
    })

    render(
      <QueryClientProvider client={queryClient}>
        <SettingsPage />
      </QueryClientProvider>
    )

    const purgeBtn = await screen.findByRole('button', { name: /purge history/i })
    fireEvent.click(purgeBtn)

    // Confirmation dialog
    const confirmBtn = await screen.findByRole('button', { name: /confirm purge/i })
    fireEvent.click(confirmBtn)

    await waitFor(() => {
      expect(purgeCalled).toBe(true)
    })
  })
})
