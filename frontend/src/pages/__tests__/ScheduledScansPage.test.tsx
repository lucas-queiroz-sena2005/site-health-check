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

  it('waits for server response on Create Schedule, stays in dialog and shows bottom alert banner on error, and clears error when re-opened', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string, options?: RequestInit) => {
      if (url === '/api/scans' && (!options?.method || options.method === 'GET')) {
        return Promise.resolve({
          ok: true,
          json: async () => mockScans,
        })
      }
      if (url === '/api/scans' && options?.method === 'POST') {
        return Promise.resolve({
          ok: false,
          status: 422,
          json: async () => ({
            detail: [
              {
                loc: ['body', 'cron_expression'],
                msg: "Value error, Invalid cron expression format (expected 5 fields, e.g. '0 0 * * *')",
              },
            ],
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

    // Open Create Schedule modal
    const createTrigger = await screen.findByRole('button', { name: /\+ Create New Schedule/i })
    fireEvent.click(createTrigger)

    const cronInput = (await screen.findByLabelText(/Cron Schedule/i)) as HTMLInputElement
    fireEvent.change(cronInput, { target: { value: 'invalid-cron' } })

    const submitBtn = screen.getByRole('button', { name: /Create Schedule/i })
    fireEvent.click(submitBtn)

    // Bottom alert banner should appear with human-readable error
    const errorBanner = await screen.findByTestId('form-error-banner')
    expect(errorBanner.textContent).toContain("Invalid cron expression format (expected 5 fields, e.g. '0 0 * * *')")

    // Dialog remains open and user input is preserved
    expect(screen.getByText(/Create New Scheduled Scan/i)).toBeTruthy()
    expect((screen.getByLabelText(/Cron Schedule/i) as HTMLInputElement).value).toBe('invalid-cron')

    // Close modal and re-open — stale error banner must be cleared
    const cancelBtn = screen.getByRole('button', { name: /Cancel/i })
    fireEvent.click(cancelBtn)

    fireEvent.click(screen.getByRole('button', { name: /\+ Create New Schedule/i }))
    await screen.findByText(/Create New Scheduled Scan/i)
    expect(screen.queryByTestId('form-error-banner')).toBeNull()
  })

  it('keeps inline Edit Schedule open and displays bottom error banner when update fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string, options?: RequestInit) => {
      if (url === '/api/scans') {
        return Promise.resolve({
          ok: true,
          json: async () => mockScans,
        })
      }
      if (url === '/api/scans/scan-active-alerts' && options?.method === 'PUT') {
        return Promise.resolve({
          ok: false,
          status: 422,
          json: async () => ({
            detail: 'Port 70000 is out of valid range (1-65535)',
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

    const row = await screen.findByText('Production Core')
    fireEvent.click(row)

    const editBtn = await screen.findByRole('button', { name: /Edit Schedule/i })
    fireEvent.click(editBtn)

    const saveBtn = await screen.findByRole('button', { name: /Save Changes/i })
    fireEvent.click(saveBtn)

    const errorBanner = await screen.findByTestId('form-error-banner')
    expect(errorBanner.textContent).toContain('Port 70000 is out of valid range (1-65535)')
    // Still in edit mode
    expect(screen.getByRole('button', { name: /Save Changes/i })).toBeTruthy()
  })

  it('renders void pruning evaluation switches under Evaluation Settings and includes them in form payload', async () => {
    let capturedPayload: any = null
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string, options?: RequestInit) => {
      if (url === '/api/scans' && (!options || options.method === 'GET')) {
        return Promise.resolve({ ok: true, json: async () => mockScans })
      }
      if (url === '/api/scans' && options?.method === 'POST') {
        capturedPayload = JSON.parse(String(options.body))
        return Promise.resolve({ ok: true, json: async () => ({ id: 'new-scan' }) })
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

    const createTrigger = await screen.findByRole('button', { name: /\+ Create New Schedule/i })
    fireEvent.click(createTrigger)

    // Check switches exist in Evaluation Settings
    const voidHostsSwitch = await screen.findByRole('switch', { name: /Prune Void Hosts/i })
    const closedPortsSwitch = await screen.findByRole('switch', { name: /Prune Routine Closed Ports/i })

    expect(voidHostsSwitch).toBeTruthy()
    expect(closedPortsSwitch).toBeTruthy()

    // Both should be checked by default
    expect(voidHostsSwitch.getAttribute('aria-checked')).toBe('true')
    expect(closedPortsSwitch.getAttribute('aria-checked')).toBe('true')

    // Toggle void hosts off
    fireEvent.click(voidHostsSwitch)
    expect(voidHostsSwitch.getAttribute('aria-checked')).toBe('false')

    // Fill minimal required fields
    fireEvent.change(screen.getByLabelText(/Scan Name/i), { target: { value: 'Void Test Scan' } })
    fireEvent.change(screen.getByLabelText(/Targets/i), { target: { value: '192.168.1.1' } })

    fireEvent.click(screen.getByRole('button', { name: /Create Schedule/i }))

    await waitFor(() => {
      expect(capturedPayload).not.toBeNull()
      expect(capturedPayload.prune_void_hosts).toBe(false)
      expect(capturedPayload.prune_closed_ports).toBe(true)
    })
  })
})
