import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ScanConfigForm } from '../ScanConfigForm'

describe('ScanConfigForm', () => {
  it('renders Ghost Window input when mode is schedule', () => {
    render(
      <ScanConfigForm
        mode="schedule"
        onSave={vi.fn()}
      />
    )
    expect(screen.getByLabelText(/ghost window/i)).toBeTruthy()
  })

  it('hides Ghost Window input when mode is live', () => {
    render(
      <ScanConfigForm
        mode="live"
        onSave={vi.fn()}
      />
    )
    expect(screen.queryByLabelText(/ghost window/i)).toBeNull()
  })
})
