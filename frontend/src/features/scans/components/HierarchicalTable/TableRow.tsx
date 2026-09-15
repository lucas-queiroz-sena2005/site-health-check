import React, { type ReactNode } from 'react'
import { useTableContext } from './TableContext'
import { DetailsPanel } from './DetailsPanel'

export interface TableRowProps {
  id: string
  depth?: number
  isLeaf?: boolean
  rawPayload?: any
  children?: ReactNode
  subRows?: ReactNode // The nested rows to render when expanded
}

export function TableRow({ id, depth = 0, isLeaf = false, rawPayload, children, subRows }: TableRowProps) {
  const { expandedRowIds, toggleRow, expandedDetailIds } = useTableContext()
  const isExpanded = expandedRowIds.has(id)
  
  // Base padding plus depth-based indentation (e.g. 1.5rem per depth level)
  const indentStyle = { paddingLeft: `calc(0.75rem + ${depth * 1.5}rem)` }

  return (
    <>
      <tr 
        className="border-b border-border hover:bg-muted/50 cursor-pointer transition-colors"
        onClick={() => toggleRow(id)}
      >
        {/* Clone the first TableCell to inject indentation and arrow icon */}
        {React.Children.map(children, (child, index) => {
          if (!React.isValidElement(child)) return child
          
          if (index === 0) {
            const element = child as React.ReactElement<{ style?: React.CSSProperties; children?: React.ReactNode }>
            return React.cloneElement(element, {
              style: indentStyle,
              children: (
                <div className="flex items-center gap-2">
                  <span className="w-4 h-4 flex-shrink-0 flex items-center justify-center font-mono font-bold text-border">
                    {isLeaf ? (
                      '│'
                    ) : (
                      <svg
                        className={`w-3 h-3 transition-transform duration-200 text-muted-foreground ${isExpanded ? 'rotate-90' : ''}`}
                        fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                      </svg>
                    )}
                  </span>
                  {element.props.children}
                </div>
              )
            })
          }
          return child
        })}
      </tr>
      
      {/* Independent Details and Children */}
      {expandedDetailIds.has(id) && <DetailsPanel payload={rawPayload} />}
      {isExpanded && !isLeaf && subRows}
    </>
  )
}
