import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
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
      notes: 'Connection reset by peer',
      finding_code: null,
    },
  ],
  total: 1,
  limit: 50,
  offset: 0,
}

const mockHostDetail = {
  ip_address: '192.168.1.10',
  status: 'ok',
  depth: 1,
  root_target: 'example.com',
  resolved_domains: ['app.example.com', 'api.example.com'],
  discovered_from: ['192.168.1.1'],
  open_port_count: 2,
  scanned_port_count: 2,
  vhost_count: 2,
  min_tcp_latency_ms: 15,
  min_tls_expires_days: 45,
  worst_tls_version: 'TLSv1.3',
  worst_http_status: 200,
  finding_codes: ['HOST_OK'],
  tls_sans: ['app.example.com', 'api.example.com', 'internal.example.com'],
  services: [
    {
      port_number: 443,
      tcp_status: 'open',
      tcp_latency_ms: 15,
      status: 'ok',
      san_count: 3,
      http_check_count: 1,
      worst_http_status: 200,
      finding_codes: [],
      tls_certificate: {
        valid: true,
        expires_in_days: 45,
        issuer: "Let's Encrypt Authority X3",
        protocol_version: 'TLSv1.3',
        domains_discovered_sans_json: ['app.example.com', 'api.example.com'],
      },
    },
    {
      port_number: 80,
      tcp_status: 'open',
      tcp_latency_ms: 12,
      status: 'ok',
      san_count: 0,
      http_check_count: 0,
      worst_http_status: null,
      finding_codes: [],
      tls_certificate: null,
    },
  ],
  checks: [
    {
      port: 443,
      domain: 'app.example.com',
      status: 'ok',
      status_code: 200,
      http_latency_ms: 25,
      redirects_to_url: 'https://app.example.com/login',
      server_header: 'nginx',
      notes: 'Connection reset by peer',
      finding_code: null,
    },
  ],
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
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.restoreAllMocks()
    fetchMock = vi.fn().mockImplementation((url: string) => {
      const u = String(url)
      if (u.includes('/api/runs?limit=1') || u.includes('/api/runs?limit=50')) {
        return Promise.resolve({ ok: true, json: async () => [mockRun] })
      }
      if (u.match(/\/api\/runs\/[^/]+\/hosts\/[0-9.]+/)) {
        return Promise.resolve({ ok: true, json: async () => mockHostDetail })
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
    expect(screen.getByText('Completed')).toBeTruthy() // Run status badge

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
      const calls = fetchMock.mock.calls.map((c: unknown[]) => String(c[0]))
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

  it('opens slide-over drawer when clicking IP address and renders host detail sections', async () => {
    renderComponent()

    const ipButton = await screen.findByRole('button', { name: '192.168.1.10' })
    fireEvent.click(ipButton)

    // Drawer should open and fetch GET /api/runs/:id/hosts/192.168.1.10
    const drawer = await screen.findByTestId('host-detail-drawer')
    expect(drawer).toBeTruthy()

    // Wait for async host detail query to resolve
    await screen.findByText(/Discovery Lineage/i)

    // Host status badge and IP in header
    expect(drawer.textContent).toContain('192.168.1.10')
    expect(drawer.textContent).toContain('OK')
    expect(drawer.textContent).toContain('HOST_OK')

    // Discovery Lineage
    expect(screen.getByText('example.com')).toBeTruthy()
    expect(screen.getByText('192.168.1.1')).toBeTruthy()

    // Services list with port, protocol, TLS details
    expect(within(drawer).getByText("Let's Encrypt Authority X3")).toBeTruthy()
    expect(within(drawer).getByText('TLSv1.3')).toBeTruthy()

    // HTTP checks
    expect(within(drawer).getByText('https://app.example.com/login')).toBeTruthy()

    // Notes and error details with copy button
    expect(within(drawer).getAllByText('Connection reset by peer').length).toBeGreaterThan(0)
    expect(within(drawer).getAllByRole('button', { name: /copy note/i }).length).toBeGreaterThan(0)

    // Deduplicated Certificate SAN badges
    expect(within(drawer).getByText('internal.example.com')).toBeTruthy()
  })

  it('drills down to Services tab when clicking "Show in Services", closing drawer and applying IP filter', async () => {
    renderComponent('/?run=run-abc-123&drawer=192.168.1.10')

    const drawer = await screen.findByTestId('host-detail-drawer')
    expect(drawer).toBeTruthy()

    const showInServicesBtn = screen.getByRole('button', { name: /show in services/i })
    fireEvent.click(showInServicesBtn)

    await waitFor(() => {
      // Drawer is closed
      expect(screen.queryByTestId('host-detail-drawer')).toBeNull()
      // Tab switched to services
      const servicesTab = screen.getByRole('tab', { name: /services/i })
      expect(servicesTab.getAttribute('data-state') === 'active' || servicesTab.getAttribute('aria-selected') === 'true').toBe(true)
      // IP filter chip is visible
      expect(screen.getByTestId('ip-filter-chip').textContent).toContain('192.168.1.10')
    })
  })

  it('drills down to HTTP Checks tab when clicking "Show in HTTP Checks", closing drawer and applying IP filter', async () => {
    renderComponent('/?run=run-abc-123&drawer=192.168.1.10')

    const drawer = await screen.findByTestId('host-detail-drawer')
    expect(drawer).toBeTruthy()

    const showInChecksBtn = screen.getByRole('button', { name: /show in http checks/i })
    fireEvent.click(showInChecksBtn)

    await waitFor(() => {
      expect(screen.queryByTestId('host-detail-drawer')).toBeNull()
      const checksTab = screen.getByRole('tab', { name: /checks/i })
      expect(checksTab.getAttribute('data-state') === 'active' || checksTab.getAttribute('aria-selected') === 'true').toBe(true)
      expect(screen.getByTestId('ip-filter-chip').textContent).toContain('192.168.1.10')
    })
  })

  it('closes the drawer when clicking the close drawer button', async () => {
    renderComponent('/?run=run-abc-123&drawer=192.168.1.10')

    const drawer = await screen.findByTestId('host-detail-drawer')
    expect(drawer).toBeTruthy()

    const closeBtn = screen.getByRole('button', { name: /close drawer/i })
    fireEvent.click(closeBtn)

    await waitFor(() => {
      expect(screen.queryByTestId('host-detail-drawer')).toBeNull()
    })
  })

  it('displays live pulsing status and refresh indicator when run is RUNNING', async () => {
    const runningRun = { ...mockRun, status: 'RUNNING' }
    fetchMock.mockImplementation((url: string) => {
      const u = String(url)
      if (u.includes('/api/runs?limit=1') || u.includes('/api/runs?limit=50')) return Promise.resolve({ ok: true, json: async () => [runningRun] })
      if (u.includes('/api/runs/run-abc-123/hosts')) return Promise.resolve({ ok: true, json: async () => mockHostsPage })
      if (u.includes('/api/runs/run-abc-123')) return Promise.resolve({ ok: true, json: async () => runningRun })
      if (u.includes('/api/views')) return Promise.resolve({ ok: true, json: async () => [] })
      return Promise.resolve({ ok: true, json: async () => ({}) })
    })

    const { container } = renderComponent()

    expect(await screen.findByText('Running')).toBeTruthy()
    expect(screen.getByText(/\(Live • refreshing every 3s\)/i)).toBeTruthy()
    expect(container.querySelector('.animate-ping')).toBeTruthy()
  })

  it('displays live pulsing status and refresh indicator when run is PENDING', async () => {
    const pendingRun = { ...mockRun, status: 'PENDING' }
    fetchMock.mockImplementation((url: string) => {
      const u = String(url)
      if (u.includes('/api/runs?limit=1') || u.includes('/api/runs?limit=50')) return Promise.resolve({ ok: true, json: async () => [pendingRun] })
      if (u.includes('/api/runs/run-abc-123/hosts')) return Promise.resolve({ ok: true, json: async () => mockHostsPage })
      if (u.includes('/api/runs/run-abc-123')) return Promise.resolve({ ok: true, json: async () => pendingRun })
      if (u.includes('/api/views')) return Promise.resolve({ ok: true, json: async () => [] })
      return Promise.resolve({ ok: true, json: async () => ({}) })
    })

    const { container } = renderComponent()

    expect(await screen.findByText('Pending')).toBeTruthy()
    expect(screen.getByText(/\(Live • refreshing every 3s\)/i)).toBeTruthy()
    expect(container.querySelector('.animate-ping')).toBeTruthy()
  })

  it('renders scan-not-found fallback card when requested run ID does not exist', async () => {
    fetchMock.mockImplementation((url: string) => {
      const u = String(url)
      if (u.includes('/api/views')) return Promise.resolve({ ok: true, json: async () => [] })
      if (u.includes('/api/runs?limit=50') || u.includes('/api/runs?limit=1')) {
        return Promise.resolve({ ok: true, json: async () => [mockRun] })
      }
      if (u.includes('/api/runs/missing-run-id')) {
        return Promise.resolve({ ok: false, status: 404, json: async () => ({ detail: 'Run not found' }) })
      }
      return Promise.resolve({ ok: true, json: async () => ({}) })
    })

    renderComponent('/?run=missing-run-id')

    const fallbackCard = await screen.findByTestId('scan-not-found-fallback')
    expect(fallbackCard).toBeTruthy()
    expect(fallbackCard.textContent).toContain('Scan Run Not Found')
    expect(fallbackCard.textContent).toContain('missing-run-id')

    // Action buttons must be present
    expect(screen.getByRole('button', { name: /View Latest Scan/i })).toBeTruthy()
    expect(screen.getByRole('button', { name: /Select from History/i })).toBeTruthy()
    expect(screen.getByRole('button', { name: /▶ Launch Live Scan/i })).toBeTruthy()

    // History Sheet trigger in header must still be accessible
    expect(screen.getByRole('button', { name: /History/i })).toBeTruthy()
  })

  it('renders no-scans fallback card when database has zero runs', async () => {
    fetchMock.mockImplementation((url: string) => {
      const u = String(url)
      if (u.includes('/api/views')) return Promise.resolve({ ok: true, json: async () => [] })
      if (u.includes('/api/runs?limit=1') || u.includes('/api/runs?limit=50')) {
        return Promise.resolve({ ok: true, json: async () => [] })
      }
      return Promise.resolve({ ok: true, json: async () => ({}) })
    })

    renderComponent('/')

    const emptyFallback = await screen.findByTestId('no-scan-selected-fallback')
    expect(emptyFallback).toBeTruthy()
    expect(emptyFallback.textContent).toContain('No Scan Runs Recorded')

    // Quick action buttons present
    expect(screen.getByRole('button', { name: /▶ Launch Live Scan/i })).toBeTruthy()
    expect(screen.getByRole('button', { name: /Configure Scheduled Scans/i })).toBeTruthy()
  })
})
