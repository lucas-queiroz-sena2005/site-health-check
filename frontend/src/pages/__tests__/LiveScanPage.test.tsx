import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { LiveScanPage } from '../LiveScanPage'

describe('LiveScanPage Wait-Before-Leaving & Input Validation', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    })
    vi.restoreAllMocks()
  })

  it('disables Launch Live Scan button when targets are empty', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <LiveScanPage />
        </MemoryRouter>
      </QueryClientProvider>
    )

    const targetInput = screen.getByPlaceholderText(/192\.168\.1\.0\/24/i) as HTMLInputElement
    fireEvent.change(targetInput, { target: { value: '   ' } })

    const launchBtn = screen.getByRole('button', { name: /Launch Live Scan/i })
    expect((launchBtn as HTMLButtonElement).disabled).toBe(true)
  })

  it('closes confirmation dialog on launch failure, does not start terminal stream, and shows bottom error banner on ScanConfigForm', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      json: async () => ({
        detail: [
          {
            loc: ['body', 'targets'],
            msg: "Value error, '999.999.999.999' is not a valid Domain, IPv4 address, or CIDR block.",
          },
        ],
      }),
    } as Response))

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <LiveScanPage />
        </MemoryRouter>
      </QueryClientProvider>
    )

    const targetInput = screen.getByPlaceholderText(/192\.168\.1\.0\/24/i) as HTMLInputElement
    fireEvent.change(targetInput, { target: { value: '999.999.999.999' } })

    const triggerBtn = screen.getByRole('button', { name: /Launch Live Scan/i })
    fireEvent.click(triggerBtn)

    const confirmBtn = await screen.findByRole('button', { name: /^Launch Scan$/i })
    fireEvent.click(confirmBtn)

    // Bottom alert banner appears on ScanConfigForm
    const errorBanner = await screen.findByTestId('form-error-banner')
    expect(errorBanner.textContent).toContain("'999.999.999.999' is not a valid Domain, IPv4 address, or CIDR block.")

    // Confirmation dialog is closed so form is immediately editable
    await waitFor(() => {
      expect(screen.queryByText(/Confirm Live Scan/i)).toBeNull()
    })

    // Terminal did NOT transition to finished/redirect state
    expect(screen.getByText(/Waiting for input\.\.\./i)).toBeTruthy()
    expect(screen.queryByText(/Redirecting to dashboard/i)).toBeNull()
  })
})
