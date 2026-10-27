import { TableHead, TableCell, TableRow } from '@/components/ui/table'
import { FindingBadge } from '../StatusBadge'

export function SortableHead({
  column,
  label,
  currentSort,
  currentDir = 'asc',
  onSort,
  className,
}: {
  column: string
  label: string
  currentSort?: string
  currentDir?: 'asc' | 'desc'
  onSort: (col: string) => void
  className?: string
}) {
  const isSorted = currentSort === column
  return (
    <TableHead
      className={`cursor-pointer font-bold select-none ${className || ''}`}
      onClick={() => onSort(column)}
    >
      <span className="inline-flex items-center gap-1">
        <span>{label}</span>
        {isSorted && (
          <span className="text-primary font-bold">{currentDir === 'asc' ? '▲' : '▼'}</span>
        )}
      </span>
    </TableHead>
  )
}

export function IpAddressCell({
  ip,
  onOpen,
}: {
  ip: string
  onOpen: (ip: string) => void
}) {
  return (
    <TableCell className="font-bold">
      <button
        type="button"
        onClick={() => onOpen(ip)}
        className="text-primary hover:underline font-mono text-xs font-bold text-left cursor-pointer"
      >
        {ip}
      </button>
    </TableCell>
  )
}

export function FindingBadgeList({
  codes,
  className,
}: {
  codes?: string[]
  className?: string
}) {
  if (!codes || codes.length === 0) return null
  return (
    <div className={`flex flex-wrap gap-1 max-w-[200px] ${className || ''}`}>
      {codes.map((code) => (
        <FindingBadge key={code} code={code} />
      ))}
    </div>
  )
}

export function EmptyTableState({
  colSpan,
  message = 'No rows match the selected filters.',
}: {
  colSpan: number
  message?: string
}) {
  return (
    <TableRow>
      <TableCell
        colSpan={colSpan}
        className="h-32 text-center text-muted-foreground font-medium"
      >
        {message}
      </TableCell>
    </TableRow>
  )
}
