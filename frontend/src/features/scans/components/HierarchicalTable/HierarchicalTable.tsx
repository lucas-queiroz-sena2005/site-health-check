import type { ReactNode } from 'react'
import { TableProvider } from './TableContext'

export interface HierarchicalTableProps {
  children?: ReactNode
  className?: string
  expandedRowIds?: Set<string>
  onToggleRow?: (id: string) => void
}

export function HierarchicalTable({ children, className = '', expandedRowIds, onToggleRow }: HierarchicalTableProps) {
  return (
    <TableProvider expandedRowIds={expandedRowIds} onToggleRow={onToggleRow}>
      <table className={`w-full text-left text-sm whitespace-nowrap table-fixed ${className}`}>
        <thead className="bg-muted text-muted-foreground border-b border-border sticky top-0 z-10 select-none shadow-sm">
          <tr>
            <th className="py-3 px-4 font-medium w-[35%]">Resource Path</th>
            <th className="py-3 px-4 font-medium w-[15%]">Type</th>
            <th className="py-3 px-4 font-medium w-[15%]">TLS Exp</th>
            <th className="py-3 px-4 font-medium w-[15%]">Latency</th>
            <th className="py-3 px-4 font-medium w-[20%]">Status</th>
          </tr>
        </thead>
        <tbody>
          {children}
        </tbody>
      </table>
    </TableProvider>
  )
}
