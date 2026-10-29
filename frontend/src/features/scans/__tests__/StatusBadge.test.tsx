import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { RunStatusBadge, EntityStatusBadge, FindingBadge, FormatTlsExpiry } from '../components/StatusBadge'
import { ScanRunStatus } from '../types'

describe('RunStatusBadge', () => {
  it('renders RUNNING status with vibrant blue styling and pulsing animation dot', () => {
    const { container } = render(<RunStatusBadge status={ScanRunStatus.RUNNING} />)
    expect(screen.getByText('Running')).toBeTruthy()
    const pingDot = container.querySelector('.animate-ping')
    expect(pingDot).toBeTruthy()
    expect(pingDot?.className).toContain('bg-blue-400')
  })

  it('renders PENDING status with amber styling and pulsing animation dot', () => {
    const { container } = render(<RunStatusBadge status={ScanRunStatus.PENDING} />)
    expect(screen.getByText('Pending')).toBeTruthy()
    const pingDot = container.querySelector('.animate-ping')
    expect(pingDot).toBeTruthy()
    expect(pingDot?.className).toContain('bg-amber-400')
  })

  it('renders COMPLETED status with green badge without pulsing animation', () => {
    const { container } = render(<RunStatusBadge status={ScanRunStatus.COMPLETED} />)
    expect(screen.getByText('Completed')).toBeTruthy()
    expect(container.querySelector('.animate-ping')).toBeNull()
  })

  it('renders FAILED status with red badge without pulsing animation', () => {
    const { container } = render(<RunStatusBadge status={ScanRunStatus.FAILED} />)
    expect(screen.getByText('Failed')).toBeTruthy()
    expect(container.querySelector('.animate-ping')).toBeNull()
  })

  it('renders ABORTED status with slate badge without pulsing animation', () => {
    const { container } = render(<RunStatusBadge status={ScanRunStatus.ABORTED} />)
    expect(screen.getByText('Aborted')).toBeTruthy()
    expect(container.querySelector('.animate-ping')).toBeNull()
  })

  it('renders fallback for custom or unknown status', () => {
    render(<RunStatusBadge status="CUSTOM_STATUS" />)
    expect(screen.getByText('CUSTOM_STATUS')).toBeTruthy()
  })
})

describe('FindingBadge and EntityStatusBadge backwards compatibility', () => {
  it('renders EntityStatusBadge correctly', () => {
    render(<EntityStatusBadge status="ok" />)
    expect(screen.getByText('OK')).toBeTruthy()
  })

  it('renders FindingBadge correctly', () => {
    render(<FindingBadge code="TLS_EXPIRED" />)
    expect(screen.getByText('TLS_EXPIRED')).toBeTruthy()
  })
})

describe('FormatTlsExpiry', () => {
  it('renders days <= 0 as red expired badge', () => {
    const { rerender } = render(<FormatTlsExpiry days={0} />)
    expect(screen.getByText('expired 0d')).toBeTruthy()
    expect(screen.getByText('expired 0d').className).toContain('text-red')

    rerender(<FormatTlsExpiry days={-5} />)
    expect(screen.getByText('expired 5d')).toBeTruthy()
    expect(screen.getByText('expired 5d').className).toContain('text-red')
  })

  it('renders days between 1 and 29 as yellow warning badge', () => {
    render(<FormatTlsExpiry days={15} />)
    expect(screen.getByText('15d')).toBeTruthy()
    expect(screen.getByText('15d').className).toContain('text-yellow')
  })

  it('renders days >= 30 as green ok badge', () => {
    render(<FormatTlsExpiry days={60} />)
    expect(screen.getByText('60d')).toBeTruthy()
    expect(screen.getByText('60d').className).toContain('text-green')
  })
})
