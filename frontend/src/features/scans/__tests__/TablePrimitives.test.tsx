import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import {
  SortableHead,
  IpAddressCell,
  FindingBadgeList,
  EmptyTableState,
} from '../components/table/TablePrimitives'
import { Table, TableHeader, TableBody, TableRow } from '@/components/ui/table'

describe('TablePrimitives', () => {
  describe('SortableHead', () => {
    it('renders label and handles onSort click', () => {
      const handleSort = vi.fn()
      render(
        <Table>
          <TableHeader>
            <TableRow>
              <SortableHead
                column="ip_address"
                label="IP Address"
                currentSort="ip_address"
                currentDir="asc"
                onSort={handleSort}
              />
            </TableRow>
          </TableHeader>
        </Table>
      )

      const head = screen.getByText(/IP Address/i)
      expect(head).toBeDefined()
      expect(screen.getByText('▲')).toBeDefined()

      fireEvent.click(head)
      expect(handleSort).toHaveBeenCalledWith('ip_address')
    })

    it('renders descending arrow when sorted desc', () => {
      render(
        <Table>
          <TableHeader>
            <TableRow>
              <SortableHead
                column="port"
                label="Port"
                currentSort="port"
                currentDir="desc"
                onSort={vi.fn()}
              />
            </TableRow>
          </TableHeader>
        </Table>
      )

      expect(screen.getByText('▼')).toBeDefined()
    })

    it('does not render sort indicator when column is not sorted', () => {
      render(
        <Table>
          <TableHeader>
            <TableRow>
              <SortableHead
                column="depth"
                label="Depth"
                currentSort="ip_address"
                currentDir="asc"
                onSort={vi.fn()}
              />
            </TableRow>
          </TableHeader>
        </Table>
      )

      expect(screen.queryByText('▲')).toBeNull()
      expect(screen.queryByText('▼')).toBeNull()
    })
  })

  describe('IpAddressCell', () => {
    it('renders IP in a button and invokes onOpen when clicked', () => {
      const handleOpen = vi.fn()
      render(
        <Table>
          <TableBody>
            <TableRow>
              <IpAddressCell ip="192.168.1.1" onOpen={handleOpen} />
            </TableRow>
          </TableBody>
        </Table>
      )

      const btn = screen.getByRole('button', { name: '192.168.1.1' })
      expect(btn).toBeDefined()

      fireEvent.click(btn)
      expect(handleOpen).toHaveBeenCalledWith('192.168.1.1')
    })
  })

  describe('FindingBadgeList', () => {
    it('renders canonical finding badges', () => {
      render(<FindingBadgeList codes={['TLS_EXPIRED', 'HTTP_5XX']} />)

      expect(screen.getByText('TLS_EXPIRED')).toBeDefined()
      expect(screen.getByText('HTTP_5XX')).toBeDefined()
    })

    it('renders null/empty when no finding codes', () => {
      const { container } = render(<FindingBadgeList codes={[]} />)
      expect(container.firstChild).toBeNull()
    })
  })

  describe('EmptyTableState', () => {
    it('renders empty message across specified colSpan', () => {
      render(
        <Table>
          <TableBody>
            <EmptyTableState colSpan={10} message="No hosts discovered." />
          </TableBody>
        </Table>
      )

      const cell = screen.getByText('No hosts discovered.')
      expect(cell).toBeDefined()
      expect(cell.getAttribute('colspan')).toBe('10')
    })
  })
})
