import type { ReactNode } from 'react'

export interface TableCellProps {
  children?: ReactNode
  className?: string
}

export function TableCell({ children, className = '' }: TableCellProps) {
  return <td className={`p-2 ${className}`}>{children}</td>
}
