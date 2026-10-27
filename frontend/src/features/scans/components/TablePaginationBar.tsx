import { Button } from '@/components/ui/button'

export interface TablePaginationBarProps {
  page: number
  limit: number
  total: number
  onPageChange: (newPage: number) => void
  onLimitChange: (newLimit: number) => void
}

export function TablePaginationBar({
  page,
  limit,
  total,
  onPageChange,
  onLimitChange,
}: TablePaginationBarProps) {
  const totalPages = Math.ceil(total / limit) || 1
  const offset = (page - 1) * limit

  return (
    <div className="px-6 py-3 shrink-0 border-t border-border bg-muted/20 flex items-center justify-between text-xs text-muted-foreground">
      <div className="flex items-center gap-2">
        <span>Rows per page:</span>
        <select
          value={limit}
          onChange={(e) => onLimitChange(Number(e.target.value))}
          className="bg-background text-foreground border border-border rounded px-2 py-1 text-xs font-mono cursor-pointer"
        >
          <option value={25}>25</option>
          <option value={50}>50</option>
          <option value={100}>100</option>
        </select>
      </div>

      <div className="flex items-center gap-4">
        <span>
          {total > 0 ? `${offset + 1}–${Math.min(offset + limit, total)} of ${total}` : '0 of 0'}
        </span>
        <div className="flex items-center gap-1">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => onPageChange(page - 1)}
            className="h-7 px-2 text-xs"
          >
            ‹ Prev
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= totalPages}
            onClick={() => onPageChange(page + 1)}
            className="h-7 px-2 text-xs"
          >
            Next ›
          </Button>
        </div>
      </div>
    </div>
  )
}
