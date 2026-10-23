from typing import Annotated
from fastapi import Query
from pydantic import BaseModel, Field


class HostRowDTO(BaseModel):
    ip_address: str
    status: str
    depth: int
    vhost_count: int
    open_port_count: int
    scanned_port_count: int
    min_tcp_latency_ms: int | None = None
    min_tls_expires_days: int | None = None
    worst_tls_version: str | None = None
    worst_http_status: int | None = None
    finding_codes: list[str] = Field(default_factory=list)


class ServiceRowDTO(BaseModel):
    ip_address: str
    port: int
    status: str
    depth: int
    tcp_latency_ms: int | None = None
    tls_valid: bool | None = None
    tls_expires_in_days: int | None = None
    tls_version: str | None = None
    tls_issuer: str | None = None
    san_count: int = 0
    http_check_count: int = 0
    worst_http_status: int | None = None
    finding_codes: list[str] = Field(default_factory=list)


class HttpCheckRowDTO(BaseModel):
    ip_address: str
    port: int
    domain: str
    status: str
    status_code: int | None = None
    http_latency_ms: int | None = None
    redirects_to_url: str | None = None
    server_header: str | None = None
    notes: str | None = None
    finding_code: str | None = None


class TlsCertificateDetailDTO(BaseModel):
    valid: bool
    expires_in_days: int = 0
    issuer: str | None = None
    protocol_version: str | None = None
    domains_discovered_sans_json: list[str] = Field(default_factory=list)


class PortDetailDTO(BaseModel):
    port_number: int
    tcp_status: str
    tcp_latency_ms: int | None = None
    status: str
    san_count: int = 0
    http_check_count: int = 0
    worst_http_status: int | None = None
    finding_codes: list[str] = Field(default_factory=list)
    tls_certificate: TlsCertificateDetailDTO | None = None


class HttpCheckDetailDTO(BaseModel):
    port: int
    domain: str
    status: str
    status_code: int | None = None
    http_latency_ms: int | None = None
    redirects_to_url: str | None = None
    server_header: str | None = None
    notes: str | None = None
    finding_code: str | None = None


class HostDetailDTO(BaseModel):
    ip_address: str
    status: str
    depth: int
    root_target: str | None = None
    resolved_domains: list[str] = Field(default_factory=list)
    discovered_from: list[str] = Field(default_factory=list)
    open_port_count: int = 0
    scanned_port_count: int = 0
    vhost_count: int = 0
    min_tcp_latency_ms: int | None = None
    min_tls_expires_days: int | None = None
    worst_tls_version: str | None = None
    worst_http_status: int | None = None
    finding_codes: list[str] = Field(default_factory=list)
    tls_sans: list[str] = Field(default_factory=list)
    services: list[PortDetailDTO] = Field(default_factory=list)
    checks: list[HttpCheckDetailDTO] = Field(default_factory=list)


class TableQueryParams:
    def __init__(
        self,
        q: Annotated[
            str | None,
            Query(description="Deep search query across IP, domains, issuer, headers, and findings"),
        ] = None,
        ip: Annotated[
            str | None,
            Query(description="Filter by exact IP address or prefix"),
        ] = None,
        status: Annotated[
            str | None,
            Query(description="Filter by status (single or comma-separated, e.g. 'warning,failed')"),
        ] = None,
        port: Annotated[
            int | None,
            Query(description="Filter by port number"),
        ] = None,
        finding: Annotated[
            str | None,
            Query(description="Filter by canonical finding code (e.g. 'TLS_EXPIRED')"),
        ] = None,
        include_closed: Annotated[
            bool,
            Query(description="Include routine closed ports on services table"),
        ] = False,
        sort_by: Annotated[
            str,
            Query(description="Column to sort by"),
        ] = "ip_address",
        sort_dir: Annotated[
            str,
            Query(pattern="^(asc|desc)$", description="Sort direction ('asc' or 'desc')"),
        ] = "asc",
        limit: Annotated[
            int,
            Query(ge=1, le=500, description="Page limit"),
        ] = 50,
        offset: Annotated[
            int,
            Query(ge=0, description="Page offset"),
        ] = 0,
    ):
        self.q = q.strip() if q else None
        self.ip = ip.strip() if ip else None
        self.status = status.strip() if status else None
        self.port = port
        self.finding = finding.strip() if finding else None
        self.include_closed = include_closed
        self.sort_by = sort_by.strip() if sort_by else "ip_address"
        self.sort_dir = sort_dir.lower().strip() if sort_dir else "asc"
        self.limit = limit
        self.offset = offset
