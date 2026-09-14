import type { ReactNode } from 'react'

export interface HierarchicalTableProps {
  children?: ReactNode
  className?: string
}

export function HierarchicalTable({ children, className = '' }: HierarchicalTableProps) {
  return (
    <table className={`w-full text-left border-collapse ${className}`}>
      {children}
    </table>
  )
}
