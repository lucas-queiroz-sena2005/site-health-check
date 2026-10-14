import type { ReactNode } from 'react'
import { TableProvider } from './TableContext'

export interface HierarchicalTableProps {
  children?: ReactNode
  className?: string
  expandedRowIds?: Set<string>
  onToggleRow?: (id: string) => void
  sortBy?: 'latency' | 'tls' | null
  sortDir?: 'asc' | 'desc'
  onSortChange?: (by: 'latency' | 'tls' | null, dir: 'asc' | 'desc') => void
}

export function HierarchicalTable({ 
  children, 
  className = '', 
  expandedRowIds, 
  onToggleRow,
  sortBy,
  sortDir,
  onSortChange
}: HierarchicalTableProps) {
  const handleSortClick = (field: 'latency' | 'tls') => {
    if (!onSortChange) return
    if (sortBy === field) {
      if (sortDir === 'asc') onSortChange(field, 'desc')
      else onSortChange(null, 'asc')
    } else {
      onSortChange(field, 'asc')
    }
  }

  const renderSortArrow = (field: 'latency' | 'tls') => {
    if (sortBy !== field) return null
    return <span className="ml-1.5 font-mono text-base text-primary font-bold leading-none">{sortDir === 'asc' ? '↑' : '↓'}</span>
  }
  return (
    <TableProvider expandedRowIds={expandedRowIds} onToggleRow={onToggleRow}>
      <div className="w-full h-full overflow-x-auto flex flex-col">
        <div className="min-w-[1200px] flex flex-col flex-1 h-full">
          <div className="flex text-sm whitespace-nowrap bg-muted/10 text-muted-foreground border-y border-border shrink-0 font-medium">
            <div className="py-3 px-4 w-[35%] sticky left-0 bg-background z-10">Resource Path</div>
            <div className="py-3 px-4 w-[15%]">Type</div>
            <div 
              className="py-3 px-4 w-[15%] cursor-pointer select-none hover:text-foreground transition-colors flex items-center"
              onClick={() => handleSortClick('tls')}
            >
              TLS Exp{renderSortArrow('tls')}
            </div>
            <div 
              className="py-3 px-4 w-[15%] cursor-pointer select-none hover:text-foreground transition-colors flex items-center"
              onClick={() => handleSortClick('latency')}
            >
              Latency{renderSortArrow('latency')}
            </div>
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
