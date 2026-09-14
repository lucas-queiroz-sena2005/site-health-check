import { createContext, useContext, useState, type ReactNode } from 'react'

export interface TableContextType {
  expandedRowIds: Set<string>
  toggleRow: (id: string) => void
}

const TableContext = createContext<TableContextType | undefined>(undefined)

export interface TableProviderProps {
  children: ReactNode
  expandedRowIds?: Set<string>
  onToggleRow?: (id: string) => void
}

export function TableProvider({ children, expandedRowIds: controlledExpanded, onToggleRow: controlledToggle }: TableProviderProps) {
  const [internalExpanded, setInternalExpanded] = useState<Set<string>>(new Set())
  
  const expandedRowIds = controlledExpanded !== undefined ? controlledExpanded : internalExpanded

  const toggleRow = (id: string) => {
    if (controlledToggle) {
      controlledToggle(id)
      return
    }

    setInternalExpanded(prev => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
        for (const openId of next) {
          if (openId.startsWith(`${id}-`)) {
            next.delete(openId)
          }
        }
      } else {
        next.add(id)
      }
      return next
    })
  }

  return (
    <TableContext.Provider value={{ expandedRowIds, toggleRow }}>
      {children}
    </TableContext.Provider>
  )
}

export function useTableContext() {
  const context = useContext(TableContext)
  if (!context) {
    throw new Error('useTableContext must be used within a TableProvider')
  }
  return context
}
