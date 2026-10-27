import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { HostsTable, ServicesTable, ChecksTable } from '../components/table'
import type { HostRowDTO, ServiceRowDTO, HttpCheckRowDTO } from '../types'

describe('Domain Table Components', () => {
  const mockHosts: HostRowDTO[] = [
    {
      ip_address: '1.1.1.1',
      status: 'ok',
      depth: 0,
      vhost_count: 1,
      open_port_count: 2,
      scanned_port_count: 2,
      min_tcp_latency_ms: 15,
      min_tls_expires_days: 45,
      worst_tls_version: 'TLSv1.3',
      worst_http_status: 200,
      finding_codes: ['TLS_EXPIRING_SOON'],
    },
  ]

  const mockServices: ServiceRowDTO[] = [
    {
      ip_address: '1.1.1.1',
      port: 443,
      status: 'ok',
      depth: 0,
      tcp_latency_ms: 12,
      tls_valid: true,
      tls_expires_in_days: 45,
      tls_version: 'TLSv1.3',
      tls_issuer: 'Cloudflare Inc',
      san_count: 3,
      http_check_count: 1,
      worst_http_status: 200,
      finding_codes: [],
    },
  ]

  const mockChecks: HttpCheckRowDTO[] = [
    {
      ip_address: '1.1.1.1',
      port: 443,
      domain: 'one.one.one.one',
      status: 'ok',
      status_code: 200,
      http_latency_ms: 25,
      redirects_to_url: null,
      server_header: 'cloudflare',
      notes: null,
      finding_code: null,
    },
  ]

  describe('HostsTable', () => {
    it('renders host rows and handles sort and IP click', () => {
      const handleSort = vi.fn()
      const handleSelectIp = vi.fn()

      render(
        <HostsTable
          items={mockHosts}
          sortBy="ip_address"
          sortDir="asc"
          onSort={handleSort}
          onSelectIp={handleSelectIp}
        />
      )

      expect(screen.getByText('1.1.1.1')).toBeDefined()
      expect(screen.getByText('2/2')).toBeDefined()
      expect(screen.getByText('15 ms')).toBeDefined()
      expect(screen.getByText('TLS_EXPIRING_SOON')).toBeDefined()

      // Click IP address button
      const ipBtn = screen.getByRole('button', { name: '1.1.1.1' })
      fireEvent.click(ipBtn)
      expect(handleSelectIp).toHaveBeenCalledWith('1.1.1.1')

      // Click sort header
      const statusHead = screen.getByText(/Status/i)
      fireEvent.click(statusHead)
      expect(handleSort).toHaveBeenCalledWith('status')
    })

    it('renders empty message when items array is empty', () => {
      render(
        <HostsTable
          items={[]}
          sortBy="ip_address"
          sortDir="asc"
          onSort={vi.fn()}
          onSelectIp={vi.fn()}
        />
      )

      expect(screen.getByText(/No rows match the selected filters/i)).toBeDefined()
    })
  })

  describe('ServicesTable', () => {
    it('renders service rows and handles sort and IP click', () => {
      const handleSort = vi.fn()
      const handleSelectIp = vi.fn()

      render(
        <ServicesTable
          items={mockServices}
          sortBy="port"
          sortDir="desc"
          onSort={handleSort}
          onSelectIp={handleSelectIp}
        />
      )

      expect(screen.getByText('1.1.1.1')).toBeDefined()
      expect(screen.getByText('443')).toBeDefined()
      expect(screen.getByText('Cloudflare Inc')).toBeDefined()
      expect(screen.getByText('✓')).toBeDefined()

      const ipBtn = screen.getByRole('button', { name: '1.1.1.1' })
      fireEvent.click(ipBtn)
      expect(handleSelectIp).toHaveBeenCalledWith('1.1.1.1')

      const issuerHead = screen.getByText(/Issuer/i)
      fireEvent.click(issuerHead)
      expect(handleSort).toHaveBeenCalledWith('tls_issuer')
    })
  })

  describe('ChecksTable', () => {
    it('renders check rows and handles sort and IP click', () => {
      const handleSort = vi.fn()
      const handleSelectIp = vi.fn()

      render(
        <ChecksTable
          items={mockChecks}
          sortBy="ip_address"
          sortDir="asc"
          onSort={handleSort}
          onSelectIp={handleSelectIp}
        />
      )

      expect(screen.getByText('1.1.1.1')).toBeDefined()
      expect(screen.getByText('one.one.one.one')).toBeDefined()
      expect(screen.getByText('cloudflare')).toBeDefined()

      const ipBtn = screen.getByRole('button', { name: '1.1.1.1' })
      fireEvent.click(ipBtn)
      expect(handleSelectIp).toHaveBeenCalledWith('1.1.1.1')

      const domainHead = screen.getByText(/Domain/i)
      fireEvent.click(domainHead)
      expect(handleSort).toHaveBeenCalledWith('domain')
    })
  })
})
