export enum ScanRunStatus {
  PENDING = 'PENDING',
  RUNNING = 'RUNNING',
  COMPLETED = 'COMPLETED',
  FAILED = 'FAILED',
  ABORTED = 'ABORTED',
}

export interface ScanRunSummary {
  active: number
  warning: number
  failed: number
  ghost: number
  void: number
  service_count: number
  http_check_count: number
}

export interface ScanRunMetrics {
  total_targets_scanned?: number
  scan_duration_seconds?: number
  anomalies_found?: number
  summary: ScanRunSummary
  [key: string]: any
}

export interface ScanRunResponse {
  id: string
  scan_id?: string | null
  scan_name?: string | null
  status: ScanRunStatus
  started_at?: string | null
  finished_at?: string | null
  metrics_json?: ScanRunMetrics | null
  targets: string[]
  ports: (string | number)[]
  flags: Record<string, any>
  ghost_window: string
  tls_warning_days: number
}

export interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

export interface HostRowDTO {
  ip_address: string
  status: string
  depth: number
  vhost_count: number
  open_port_count: number
  scanned_port_count: number
  min_tcp_latency_ms?: number | null
  min_tls_expires_days?: number | null
  worst_tls_version?: string | null
  worst_http_status?: number | null
  finding_codes: string[]
}

export interface ServiceRowDTO {
  ip_address: string
  port: number
  status: string
  depth: number
  tcp_latency_ms?: number | null
  tls_valid?: boolean | null
  tls_expires_in_days?: number | null
  tls_version?: string | null
  tls_issuer?: string | null
  san_count: number
  http_check_count: number
  worst_http_status?: number | null
  finding_codes: string[]
}

export interface HttpCheckRowDTO {
  ip_address: string
  port: number
  domain: string
  status: string
  status_code?: number | null
  http_latency_ms?: number | null
  redirects_to_url?: string | null
  server_header?: string | null
  notes?: string | null
  finding_code?: string | null
}

export interface TlsCertificateDetailDTO {
  valid: boolean
  expires_in_days: number
  issuer?: string | null
  protocol_version?: string | null
  domains_discovered_sans_json: string[]
}

export interface PortDetailDTO {
  port_number: number
  tcp_status: string
  tcp_latency_ms?: number | null
  status: string
  san_count: number
  http_check_count: number
  worst_http_status?: number | null
  finding_codes: string[]
  tls_certificate?: TlsCertificateDetailDTO | null
}

export interface HttpCheckDetailDTO {
  port: number
  domain: string
  status: string
  status_code?: number | null
  http_latency_ms?: number | null
  redirects_to_url?: string | null
  server_header?: string | null
  notes?: string | null
  finding_code?: string | null
}

export interface HostDetailDTO {
  ip_address: string
  status: string
  depth: number
  root_target?: string | null
  resolved_domains: string[]
  discovered_from: string[]
  open_port_count: number
  scanned_port_count: number
  vhost_count: number
  min_tcp_latency_ms?: number | null
  min_tls_expires_days?: number | null
  worst_tls_version?: string | null
  worst_http_status?: number | null
  finding_codes: string[]
  tls_sans: string[]
  services: PortDetailDTO[]
  checks: HttpCheckDetailDTO[]
}

export interface TableQueryParams {
  q?: string
  ip?: string
  status?: string
  port?: number
  finding?: string
  include_closed?: boolean
  sort_by?: string
  sort_dir?: 'asc' | 'desc'
  limit?: number
  offset?: number
}
