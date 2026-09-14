import type { ReactNode, CSSProperties } from 'react'

export interface TableCellProps {
  children?: ReactNode
  className?: string
  width?: string
  style?: CSSProperties
}

export function TableCell({ children, className = '', width = '', style }: TableCellProps) {
  return (
    <td className={`p-3 truncate ${width} ${className}`} style={style}>
      {children}
    </td>
  )
}
