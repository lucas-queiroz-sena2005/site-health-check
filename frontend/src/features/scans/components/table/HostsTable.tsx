import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type { HostRowDTO } from '../../types'
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

export interface HostsTableProps {
  items?: HostRowDTO[]
  sortBy: string
  sortDir: 'asc' | 'desc'
  onSort: (col: string) => void
  onSelectIp: (ip: string) => void
}

export function HostsTable({
  items,
  sortBy,
  sortDir,
  onSort,
  onSelectIp,
}: HostsTableProps) {
  return (
    <Table>
      <TableHeader className="bg-muted/50 sticky top-0">
        <TableRow>
          <SortableHead column="ip_address" label="IP Address" currentSort={sortBy} currentDir={sortDir} onSort={onSort} />
          <SortableHead column="status" label="Status" currentSort={sortBy} currentDir={sortDir} onSort={onSort} />
          <SortableHead column="depth" label="Depth" currentSort={sortBy} currentDir={sortDir} onSort={onSort} />
          <SortableHead column="vhost_count" label="VHosts" currentSort={sortBy} currentDir={sortDir} onSort={onSort} />
          <SortableHead column="open_port_count" label="Open Ports" currentSort={sortBy} currentDir={sortDir} onSort={onSort} />
          <SortableHead column="min_tcp_latency_ms" label="Min Latency" currentSort={sortBy} currentDir={sortDir} onSort={onSort} />
          <SortableHead column="min_tls_expires_days" label="Min TLS Expiry" currentSort={sortBy} currentDir={sortDir} onSort={onSort} />
          <SortableHead column="worst_tls_version" label="Worst TLS" currentSort={sortBy} currentDir={sortDir} onSort={onSort} />
          <SortableHead column="worst_http_status" label="Worst HTTP" currentSort={sortBy} currentDir={sortDir} onSort={onSort} />
          <TableHead className="font-bold">Findings</TableHead>
        </TableRow>
      </TableHeader>

      <TableBody>
        {!items || items.length === 0 ? (
          <EmptyTableState colSpan={10} />
        ) : (
          items.map((h) => (
            <TableRow key={h.ip_address} className="hover:bg-muted/30 font-mono text-xs">
              <IpAddressCell ip={h.ip_address} onOpen={onSelectIp} />
              <TableCell>
                <EntityStatusBadge status={h.status} />
              </TableCell>
              <TableCell>{h.depth}</TableCell>
              <TableCell>{h.vhost_count}</TableCell>
              <TableCell>
                {h.open_port_count}/{h.scanned_port_count}
              </TableCell>
              <TableCell>
                <FormatLatency latency={h.min_tcp_latency_ms} />
              </TableCell>
              <TableCell>
                <FormatTlsExpiry days={h.min_tls_expires_days} />
              </TableCell>
              <TableCell>
                <FormatTlsVersion version={h.worst_tls_version} />
              </TableCell>
              <TableCell>
                <FormatHttpStatus status={h.worst_http_status} />
              </TableCell>
              <TableCell>
                <FindingBadgeList codes={h.finding_codes} />
              </TableCell>
            </TableRow>
          ))
        )}
      </TableBody>
    </Table>
  )
}
