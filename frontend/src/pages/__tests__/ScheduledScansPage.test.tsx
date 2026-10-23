import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { ScheduledScansPage } from '../ScheduledScansPage'

const mockScans = [
  {
    id: 'scan-active-alerts',
    name: 'Production Core',
    cron_expression: '0 * * * *',
    targets: ['192.168.1.1'],
    ports: [80, 443],
    flags: {},
    alert_config: {
      webhook_url: 'https://chat.googleapis.com/test',
      alert_on_failure: true,
    },
    alerts_muted: false,
    last_run: null,
    next_run: null,
  },
  {
    id: 'scan-muted-alerts',
    name: 'Staging Cluster',
    cron_expression: '*/15 * * * *',
    targets: ['10.0.0.1'],
    ports: [80],
    flags: {},
    alert_config: {
      webhook_url: 'https://chat.googleapis.com/test',
      alert_on_warning: true,
    },
    alerts_muted: true,
    last_run: null,
    next_run: null,
  },
  {
    id: 'scan-no-alerts',
    name: 'Internal Tools',
    cron_expression: '0 0 * * *',
    targets: ['127.0.0.1'],
    ports: [8080],
    flags: {},
    alert_config: null,
    alerts_muted: false,
    last_run: null,
    next_run: null,
  },
]

describe('ScheduledScansPage Alert Stopper Controls', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    })
    vi.restoreAllMocks()
  })

  it('renders the Alerts column header and indicators for active, muted, and empty alert configs', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockScans,
    } as Response))

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <ScheduledScansPage />
        </MemoryRouter>
      </QueryClientProvider>
    )

    // Verify Alerts column header
    expect(await screen.findByText('Alerts')).toBeTruthy()

    // Active alert indicator for scan-active-alerts
    const activeIndicator = await screen.findByTestId('alert-status-scan-active-alerts')
    expect(activeIndicator.textContent).toMatch(/Active/i)

    // Muted alert indicator for scan-muted-alerts
    const mutedIndicator = await screen.findByTestId('alert-status-scan-muted-alerts')
    expect(mutedIndicator.textContent).toMatch(/Muted/i)

    // No alert indicator for scan-no-alerts
    expect(screen.queryByTestId('alert-status-scan-no-alerts')).toBeNull()
  })

  it('renders stopper button between Edit Schedule and Delete and toggles mute state in-place', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string, options?: RequestInit) => {
      if (url === '/api/scans') {
        return Promise.resolve({
          ok: true,
          json: async () => mockScans,
        })
      }
      if (url === '/api/scans/scan-active-alerts' && options?.method === 'PATCH') {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            ...mockScans[0],
            alerts_muted: true,
          }),
        })
      }
      return Promise.resolve({ ok: true, json: async () => ({}) })
    }))

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <ScheduledScansPage />
        </MemoryRouter>
      </QueryClientProvider>
    )

    // Click on scan row to expand
    const row = await screen.findByText('Production Core')
    fireEvent.click(row)

    // Stopper button should say "Mute Alerts"
    const muteBtn = await screen.findByRole('button', { name: /Mute Alerts/i })
    expect(muteBtn).toBeTruthy()

    // Click stopper button
    fireEvent.click(muteBtn)

    // Verify in-place update without route change or reload
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Resume Alerts/i })).toBeTruthy()
    })

    const statusElem = screen.getByTestId('alert-status-scan-active-alerts')
    expect(statusElem.textContent).toMatch(/Muted/i)
  })
})
