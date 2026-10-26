import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { HostTablePage } from '../HostTablePage'

const mockRun = {
  id: 'run-abc-123',
  scan_id: 'scan-1',
  scan_name: 'Core Perimeter',
  status: 'COMPLETED',
  started_at: '2026-10-26T12:00:00Z',
  finished_at: '2026-10-26T12:01:15Z',
  targets: ['192.168.1.0/24'],
  ports: [80, 443],
  flags: {},
  ghost_window: '7d',
  tls_warning_days: 30,
  metrics_json: {
    total_targets_scanned: 256,
    scan_duration_seconds: 75.0,
    anomalies_found: 3,
    summary: {
      active: 5,
      warning: 2,
      failed: 1,
      ghost: 1,
      void: 247,
      service_count: 8,
      http_check_count: 12,
    },
  },
}

const mockHostsPage = {
  items: [
    {
      ip_address: '192.168.1.10',
      status: 'ok',
      depth: 0,
      vhost_count: 2,
      open_port_count: 2,
      scanned_port_count: 2,
      min_tcp_latency_ms: 15,
      min_tls_expires_days: 45,
      worst_tls_version: 'TLSv1.3',
      worst_http_status: 200,
      finding_codes: [],
    },
  ],
  total: 1,
  limit: 50,
  offset: 0,
}

const mockServicesPage = {
  items: [
    {
      ip_address: '192.168.1.10',
      port: 443,
      status: 'ok',
      depth: 0,
      tcp_latency_ms: 15,
      tls_valid: true,
      tls_expires_in_days: 45,
      tls_version: 'TLSv1.3',
      tls_issuer: "Let's Encrypt",
      san_count: 2,
      http_check_count: 1,
      worst_http_status: 200,
      finding_codes: [],
    },
  ],
  total: 1,
  limit: 50,
  offset: 0,
}

const mockChecksPage = {
  items: [
    {
      ip_address: '192.168.1.10',
      port: 443,
      domain: 'app.example.com',
      status: 'ok',
      status_code: 200,
      http_latency_ms: 25,
      redirects_to_url: 'https://app.example.com/login',
      server_header: 'nginx',
      notes: null,
      finding_code: null,
    },
  ],
  total: 1,
  limit: 50,
  offset: 0,
}

function renderComponent(initialRoute = '/?run=run-abc-123') {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialRoute]}>
        <Routes>
          <Route path="/" element={<HostTablePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('HostTablePage 3-Tab Flat Relational Explorer', () => {
  let fetchMock: any

  beforeEach(() => {
    vi.restoreAllMocks()
    fetchMock = vi.fn().mockImplementation((url: string) => {
      const u = String(url)
      if (u.includes('/api/runs?limit=1') || u.includes('/api/runs?limit=50')) {
        return Promise.resolve({ ok: true, json: async () => [mockRun] })
      }
      if (u.includes('/api/runs/run-abc-123/hosts')) {
        return Promise.resolve({ ok: true, json: async () => mockHostsPage })
      }
      if (u.includes('/api/runs/run-abc-123/services')) {
        return Promise.resolve({ ok: true, json: async () => mockServicesPage })
      }
      if (u.includes('/api/runs/run-abc-123/checks')) {
        return Promise.resolve({ ok: true, json: async () => mockChecksPage })
      }
      if (u.includes('/api/runs/run-abc-123')) {
        return Promise.resolve({ ok: true, json: async () => mockRun })
      }
      if (u.includes('/api/views')) {
        return Promise.resolve({ ok: true, json: async () => [] })
      }
      return Promise.resolve({ ok: true, json: async () => ({}) })
    })
    vi.stubGlobal('fetch', fetchMock)
  })

  it('renders Run Summary strip badges and 3 tab badges with metrics from GET /api/runs/:id', async () => {
    renderComponent()

    // Run metadata in header
    expect(await screen.findByText('Core Perimeter')).toBeTruthy()
    expect(screen.getByText('256')).toBeTruthy() // targets scanned

    // Status summary strip pills
    expect(screen.getByText('Active').parentElement?.textContent).toContain('5')
    expect(screen.getByText('Warning').parentElement?.textContent).toContain('2')
    expect(screen.getByText('Failed').parentElement?.textContent).toContain('1')
    expect(screen.getByText('Ghost').parentElement?.textContent).toContain('1')
    expect(screen.getByText('Void').parentElement?.textContent).toContain('247')

    // 3 Tab triggers with counts
    // Hosts count = active + warning + failed + ghost = 5 + 2 + 1 + 1 = 9
    const hostsTab = await screen.findByRole('tab', { name: /hosts/i })
    expect(hostsTab.textContent).toContain('9')

    const servicesTab = screen.getByRole('tab', { name: /services/i })
    expect(servicesTab.textContent).toContain('8')

    const checksTab = screen.getByRole('tab', { name: /checks/i })
    expect(checksTab.textContent).toContain('12')
  })

  it('enforces IP Address as strictly the first column and clickable in Hosts table', async () => {
    renderComponent()

    // Column 1 header is IP Address
    const headers = await screen.findAllByRole('columnheader')
    expect(headers[0].textContent).toMatch(/IP Address/i)

    // First cell is clickable IP address link/button
    const ipLink = await screen.findByRole('button', { name: '192.168.1.10' })
    expect(ipLink).toBeTruthy()

    // Host row columns exist: VHosts, Open Ports (2/2)
    expect(screen.getByText('2/2')).toBeTruthy()
  })

  it('switches to Services tab with IP Address as column 1 and displays port and TLS issuer', async () => {
    renderComponent('/?run=run-abc-123&tab=services')

    const servicesTab = await screen.findByRole('tab', { name: /services/i })
    fireEvent.click(servicesTab)

    await waitFor(() => {
      const headers = screen.getAllByRole('columnheader')
      expect(headers[0].textContent).toMatch(/IP Address/i)
      expect(headers[1].textContent).toMatch(/Port/i)
    })

    expect(await screen.findByRole('button', { name: '192.168.1.10' })).toBeTruthy()
    expect(screen.getByText('443')).toBeTruthy()
    expect(screen.getByText("Let's Encrypt")).toBeTruthy()
  })

  it('switches to HTTP Checks tab and displays domain and redirects directly without IP map', async () => {
    renderComponent('/?run=run-abc-123&tab=checks')

    await waitFor(() => {
      const headers = screen.getAllByRole('columnheader')
      expect(headers[0].textContent).toMatch(/IP Address/i)
      expect(headers[2].textContent).toMatch(/Domain/i)
    })

    expect(await screen.findByText('app.example.com')).toBeTruthy()
    // Directly renders redirect URL as monospace text without client-side IP lookup badge
    expect(screen.getByText('https://app.example.com/login')).toBeTruthy()
  })

  it('synchronizes search input and status toggles with backend query parameters', async () => {
    renderComponent()

    // Type into search
    const searchInput = await screen.findByPlaceholderText(/Search IP, domain, issuer, findings/i)
    fireEvent.change(searchInput, { target: { value: 'staging' } })

    // Click 'warning' status toggle
    const warningBtn = screen.getByRole('button', { name: /warning/i })
    fireEvent.click(warningBtn)

    await waitFor(() => {
      const calls = fetchMock.mock.calls.map((c: any) => String(c[0]))
      const matched = calls.some((c: string) => c.includes('q=staging') && c.includes('status=warning'))
      expect(matched).toBe(true)
    })
  })

  it('renders removable IP filter chip when ip query param is set and clears it on click', async () => {
    renderComponent('/?run=run-abc-123&ip=192.168.1.10')

    const ipChip = await screen.findByTestId('ip-filter-chip')
    expect(ipChip.textContent).toContain('192.168.1.10')

    // Click remove button on chip
    const clearBtn = screen.getByRole('button', { name: /clear ip filter/i })
    fireEvent.click(clearBtn)

    await waitFor(() => {
      expect(screen.queryByTestId('ip-filter-chip')).toBeNull()
    })
  })
})
