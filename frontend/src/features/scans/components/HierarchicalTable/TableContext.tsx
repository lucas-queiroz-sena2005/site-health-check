import { createContext, useContext, useState, useMemo, useCallback, type ReactNode } from 'react'

export interface TableStateContextType {
  expandedRowIds: Set<string>
  expandedDetailIds: Set<string>
}

export interface TableDispatchContextType {
  toggleRow: (id: string) => void
  toggleDetail: (id: string) => void
}

const TableStateContext = createContext<TableStateContextType | undefined>(undefined)
const TableDispatchContext = createContext<TableDispatchContextType | undefined>(undefined)

export interface TableProviderProps {
  children: ReactNode
  expandedRowIds?: Set<string>
  onToggleRow?: (id: string) => void
}

export function TableProvider({ children, expandedRowIds: controlledExpanded, onToggleRow: controlledToggle }: TableProviderProps) {
  const [internalExpanded, setInternalExpanded] = useState<Set<string>>(new Set())
  const [expandedDetailIds, setExpandedDetailIds] = useState<Set<string>>(new Set())
  
  const expandedRowIds = controlledExpanded !== undefined ? controlledExpanded : internalExpanded

  const toggleDetail = useCallback((id: string) => {
    setExpandedDetailIds(prev => {
      const next = new Set<string>()
      if (!prev.has(id)) {
        next.add(id)
      }
      return next
    })
  }, [])

  const toggleRow = useCallback((id: string) => {
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
  }, [controlledToggle])

  const stateValue = useMemo(() => ({
    expandedRowIds,
    expandedDetailIds
  }), [expandedRowIds, expandedDetailIds])

  const dispatchValue = useMemo(() => ({
    toggleRow,
    toggleDetail
  }), [toggleRow, toggleDetail])

  return (
    <TableStateContext.Provider value={stateValue}>
      <TableDispatchContext.Provider value={dispatchValue}>
        {children}
      </TableDispatchContext.Provider>
    </TableStateContext.Provider>
  )
}

export function useTableStateContext() {
  const context = useContext(TableStateContext)
  if (!context) {
    throw new Error('useTableStateContext must be used within a TableProvider')
  }
  return context
}

export function useTableDispatchContext() {
  const context = useContext(TableDispatchContext)
  if (!context) {
    throw new Error('useTableDispatchContext must be used within a TableProvider')
  }
  return context
}
