import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type { ServiceRowDTO } from '../../types'
import {
  EntityStatusBadge,
  FormatLatency,
  FormatTlsExpiry,
  FormatTlsVersion,
  FormatHttpStatus,
} from '../StatusBadge'
import {
  SortableHead,
  IpAddressCell,
  FindingBadgeList,
  EmptyTableState,
} from './TablePrimitives'

export interface ServicesTableProps {
  items?: ServiceRowDTO[]
  sortBy: string
  sortDir: 'asc' | 'desc'
  onSort: (col: string) => void
  onSelectIp: (ip: string) => void
}

export function ServicesTable({
  items,
  sortBy,
  sortDir,
  onSort,
  onSelectIp,
}: ServicesTableProps) {
  return (
    <Table>
      <TableHeader className="bg-muted/50 sticky top-0">
        <TableRow>
          <SortableHead column="ip_address" label="IP Address" currentSort={sortBy} currentDir={sortDir} onSort={onSort} />
          <SortableHead column="port" label="Port" currentSort={sortBy} currentDir={sortDir} onSort={onSort} />
          <SortableHead column="status" label="Status" currentSort={sortBy} currentDir={sortDir} onSort={onSort} />
          <SortableHead column="depth" label="Depth" currentSort={sortBy} currentDir={sortDir} onSort={onSort} />
          <SortableHead column="tcp_latency_ms" label="TCP Latency" currentSort={sortBy} currentDir={sortDir} onSort={onSort} />
          <SortableHead column="tls_valid" label="TLS Valid" currentSort={sortBy} currentDir={sortDir} onSort={onSort} />
          <SortableHead column="tls_expires_in_days" label="TLS Expiry" currentSort={sortBy} currentDir={sortDir} onSort={onSort} />
          <SortableHead column="tls_version" label="TLS Version" currentSort={sortBy} currentDir={sortDir} onSort={onSort} />
          <SortableHead column="tls_issuer" label="Issuer" currentSort={sortBy} currentDir={sortDir} onSort={onSort} />
          <SortableHead column="san_count" label="SAN Count" currentSort={sortBy} currentDir={sortDir} onSort={onSort} />
          <SortableHead column="http_check_count" label="HTTP Checks" currentSort={sortBy} currentDir={sortDir} onSort={onSort} />
          <SortableHead column="worst_http_status" label="Worst HTTP" currentSort={sortBy} currentDir={sortDir} onSort={onSort} />
          <TableHead className="font-bold">Findings</TableHead>
        </TableRow>
      </TableHeader>

      <TableBody>
        {!items || items.length === 0 ? (
          <EmptyTableState colSpan={13} />
        ) : (
          items.map((s) => (
            <TableRow key={`${s.ip_address}-${s.port}`} className="hover:bg-muted/30 font-mono text-xs">
              <IpAddressCell ip={s.ip_address} onOpen={onSelectIp} />
              <TableCell className="font-bold">{s.port}</TableCell>
              <TableCell>
                <EntityStatusBadge status={s.status} />
              </TableCell>
              <TableCell>{s.depth}</TableCell>
              <TableCell>
                <FormatLatency latency={s.tcp_latency_ms} />
              </TableCell>
              <TableCell>
                {s.tls_valid === true ? (
                  <span className="text-green-600 font-bold">✓</span>
                ) : s.tls_valid === false ? (
                  <span className="text-red-600 font-bold">✗</span>
                ) : (
                  <span className="text-muted-foreground/60">—</span>
                )}
              </TableCell>
              <TableCell>
                <FormatTlsExpiry days={s.tls_expires_in_days} />
              </TableCell>
              <TableCell>
                <FormatTlsVersion version={s.tls_version} />
              </TableCell>
              <TableCell className="max-w-[150px] truncate" title={s.tls_issuer || ''}>
                {s.tls_issuer || '—'}
              </TableCell>
              <TableCell>{s.san_count || '—'}</TableCell>
              <TableCell>{s.http_check_count}</TableCell>
              <TableCell>
                <FormatHttpStatus status={s.worst_http_status} />
              </TableCell>
              <TableCell>
                <FindingBadgeList codes={s.finding_codes} />
              </TableCell>
            </TableRow>
          ))
        )}
      </TableBody>
    </Table>
  )
}
