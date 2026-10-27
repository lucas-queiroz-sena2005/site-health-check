import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type { HttpCheckRowDTO } from '../../types'
import {
  EntityStatusBadge,
  FormatLatency,
  FormatHttpStatus,
  FindingBadge,
  CopyButton,
} from '../StatusBadge'
import {
  SortableHead,
  IpAddressCell,
  EmptyTableState,
} from './TablePrimitives'

export interface ChecksTableProps {
  items?: HttpCheckRowDTO[]
  sortBy: string
  sortDir: 'asc' | 'desc'
  onSort: (col: string) => void
  onSelectIp: (ip: string) => void
}

export function ChecksTable({
  items,
  sortBy,
  sortDir,
  onSort,
  onSelectIp,
}: ChecksTableProps) {
  return (
    <Table>
      <TableHeader className="bg-muted/50 sticky top-0">
        <TableRow>
          <SortableHead column="ip_address" label="IP Address" currentSort={sortBy} currentDir={sortDir} onSort={onSort} />
          <SortableHead column="port" label="Port" currentSort={sortBy} currentDir={sortDir} onSort={onSort} />
          <SortableHead column="domain" label="Domain" currentSort={sortBy} currentDir={sortDir} onSort={onSort} />
          <SortableHead column="status" label="Status" currentSort={sortBy} currentDir={sortDir} onSort={onSort} />
          <SortableHead column="status_code" label="HTTP Code" currentSort={sortBy} currentDir={sortDir} onSort={onSort} />
          <SortableHead column="http_latency_ms" label="Latency" currentSort={sortBy} currentDir={sortDir} onSort={onSort} />
          <SortableHead column="redirects_to_url" label="Redirect To" currentSort={sortBy} currentDir={sortDir} onSort={onSort} />
          <SortableHead column="server_header" label="Server" currentSort={sortBy} currentDir={sortDir} onSort={onSort} />
          <TableHead className="font-bold">Notes</TableHead>
          <SortableHead column="finding_code" label="Finding" currentSort={sortBy} currentDir={sortDir} onSort={onSort} />
        </TableRow>
      </TableHeader>

      <TableBody>
        {!items || items.length === 0 ? (
          <EmptyTableState colSpan={10} />
        ) : (
          items.map((c, idx) => (
            <TableRow key={`${c.ip_address}-${c.port}-${c.domain}-${idx}`} className="hover:bg-muted/30 font-mono text-xs">
              <IpAddressCell ip={c.ip_address} onOpen={onSelectIp} />
              <TableCell className="font-bold">{c.port}</TableCell>
              <TableCell className="font-bold text-foreground">{c.domain}</TableCell>
              <TableCell>
                <EntityStatusBadge status={c.status} />
              </TableCell>
              <TableCell>
                <FormatHttpStatus status={c.status_code} />
              </TableCell>
              <TableCell>
                <FormatLatency latency={c.http_latency_ms} />
              </TableCell>
              <TableCell className="max-w-[240px] truncate font-mono text-[11px]" title={c.redirects_to_url || ''}>
                {c.redirects_to_url ? (
                  <span className="text-primary font-semibold">{c.redirects_to_url}</span>
                ) : (
                  <span className="text-muted-foreground/60">—</span>
                )}
              </TableCell>
              <TableCell className="max-w-[120px] truncate" title={c.server_header || ''}>
                {c.server_header || '—'}
              </TableCell>
              <TableCell className="max-w-[200px] overflow-hidden" title={c.notes || ''}>
                {c.notes ? (
                  <div className="flex items-center justify-between gap-1.5 min-w-0">
                    <span className="truncate font-mono text-[11px] text-muted-foreground block" title={c.notes}>
                      {c.notes}
                    </span>
                    <CopyButton text={c.notes} label="Copy note" />
                  </div>
                ) : (
                  <span className="text-muted-foreground/60">—</span>
                )}
              </TableCell>
              <TableCell>
                {c.finding_code ? <FindingBadge code={c.finding_code} /> : <span className="text-muted-foreground/60">—</span>}
              </TableCell>
            </TableRow>
          ))
        )}
      </TableBody>
    </Table>
  )
}
