import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RunHistorySheet } from '../RunHistorySheet'

describe('RunHistorySheet', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    })
    vi.restoreAllMocks()
  })

  it('renders target string preview on run cards', async () => {
    vi.spyOn(global, 'fetch').mockImplementation(async (url: any) => {
      if (String(url).includes('/api/runs')) {
        return {
          ok: true,
          json: async () => [
            {
              id: 'run-1',
              scan_name: 'Ad-hoc Scan',
              status: 'COMPLETED',
              targets: ['143.106.16.128/26', 'nimbus.lab.ic.unicamp.br'],
              started_at: '2026-10-29T10:00:00Z',
            },
          ],
        } as Response
      }
      return { ok: true, json: async () => [] } as Response
    })

    render(
      <QueryClientProvider client={queryClient}>
        <RunHistorySheet selectedRunId="run-1" onSelectRun={vi.fn()} />
      </QueryClientProvider>
    )

    // Open sheet
    const trigger = screen.getByRole('button', { name: /history/i })
    fireEvent.click(trigger)

    expect(await screen.findByText(/143\.106\.16\.128\/26, nimbus\.lab\.ic\.unicamp\.br/i)).toBeTruthy()
  })

  it('deletes terminal run with DELETE /api/runs/{id} and resets selectedRunId if active', async () => {
    const onSelectRunMock = vi.fn()
    let deleteCalled = false

    vi.spyOn(global, 'fetch').mockImplementation(async (url: any, init?: any) => {
      if (String(url).includes('/api/runs/run-to-delete') && init?.method === 'DELETE') {
        deleteCalled = true
        return { ok: true, status: 204 } as Response
      }
      if (String(url).includes('/api/runs')) {
        return {
          ok: true,
          json: async () => [
            {
              id: 'run-to-delete',
              scan_name: 'Past Scan',
              status: 'COMPLETED',
              targets: ['10.0.0.1'],
              started_at: '2026-10-29T10:00:00Z',
            },
          ],
        } as Response
      }
      return { ok: true, json: async () => [] } as Response
    })

    render(
      <QueryClientProvider client={queryClient}>
        <RunHistorySheet selectedRunId="run-to-delete" onSelectRun={onSelectRunMock} />
      </QueryClientProvider>
    )

    // Open sheet
    const trigger = screen.getByRole('button', { name: /history/i })
    fireEvent.click(trigger)

    const deleteBtn = await screen.findByTitle(/delete run/i)
    fireEvent.click(deleteBtn)

    await waitFor(() => {
      expect(deleteCalled).toBe(true)
      expect(onSelectRunMock).toHaveBeenCalledWith(null)
    })
  })
})
