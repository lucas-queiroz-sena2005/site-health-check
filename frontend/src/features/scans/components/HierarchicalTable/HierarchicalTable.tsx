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
      <div className="w-full h-full overflow-x-auto flex flex-col">
        <div className="min-w-[1200px] flex flex-col flex-1 h-full">
          <div className="flex text-sm whitespace-nowrap bg-muted/10 text-muted-foreground border-y border-border shrink-0 font-medium">
            <div className="py-3 px-4 w-[35%] sticky left-0 bg-background z-10">Resource Path</div>
            <div className="py-3 px-4 w-[15%]">Type</div>
            <div className="py-3 px-4 w-[15%]">TLS Exp</div>
            <div className="py-3 px-4 w-[15%]">Latency</div>
            <div className="py-3 px-4 w-[20%]">Status</div>
          </div>
          <div className="flex-1 overflow-y-auto">
            <table className={`w-full text-left text-sm whitespace-nowrap table-fixed border-separate border-spacing-0 ${className}`}>
              <tbody>
                {children}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </TableProvider>
  )
}
