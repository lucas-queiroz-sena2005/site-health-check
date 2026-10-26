import { useState, useCallback } from 'react'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Button } from '@/components/ui/button'
import { useRunHostDetail } from '../api/useScanResults'
import {
  EntityStatusBadge,
  FindingBadge,
  FormatLatency,
  FormatTlsExpiry,
  FormatHttpStatus,
} from './StatusBadge'

export interface HostDetailDrawerProps {
  runId: string | null
  ipAddress: string | null
  open: boolean
  onClose: () => void
  onDrillDown: (tab: 'services' | 'checks', ip: string) => void
}

export function HostDetailDrawer({
  runId,
  ipAddress,
  open,
  onClose,
  onDrillDown,
}: HostDetailDrawerProps) {
  const [copied, setCopied] = useState(false)

  const { data, isLoading, error } = useRunHostDetail(
    open ? (runId ?? undefined) : undefined,
    open ? (ipAddress ?? undefined) : undefined
  )

  const handleCopyIp = useCallback(() => {
    if (ipAddress && navigator.clipboard) {
      navigator.clipboard.writeText(ipAddress)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }, [ipAddress])

  return (
    <Sheet open={open} onOpenChange={(isOpen) => { if (!isOpen) onClose() }}>
      <SheetContent
        data-testid="host-detail-drawer"
        showCloseButton={false}
        className="w-[90vw] sm:max-w-lg md:max-w-xl overflow-y-auto p-6 flex flex-col gap-6"
      >
        <SheetHeader className="flex flex-row items-start justify-between space-y-0 pb-2 border-b">
          <div className="space-y-1">
            <SheetTitle className="sr-only">Host Details for {ipAddress || 'Host'}</SheetTitle>
            <div className="flex items-center gap-2">
              <span className="text-xl font-mono font-bold text-foreground">
                {ipAddress || '—'}
              </span>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={handleCopyIp}
                title="Copy IP to clipboard"
                aria-label="Copy IP"
                className="h-7 w-7 text-muted-foreground hover:text-foreground"
              >
                {copied ? (
                  <svg className="size-3.5 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                ) : (
                  <svg className="size-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                  </svg>
                )}
              </Button>
              {data?.status && <EntityStatusBadge status={data.status} />}
            </div>

            {data?.finding_codes && data.finding_codes.length > 0 && (
              <div className="flex flex-wrap gap-1 pt-1">
                {data.finding_codes.map((f) => (
                  <FindingBadge key={f} code={f} />
                ))}
              </div>
            )}
          </div>

          <Button
            variant="ghost"
            size="icon-sm"
            onClick={onClose}
            aria-label="Close drawer"
            className="h-8 w-8 rounded-md text-muted-foreground hover:text-foreground"
          >
            <svg className="size-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
            <span className="sr-only">Close drawer</span>
          </Button>
        </SheetHeader>

        {/* Drill-Down Action Buttons */}
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => ipAddress && onDrillDown('services', ipAddress)}
            className="h-8 text-xs font-semibold"
          >
            Show in Services
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => ipAddress && onDrillDown('checks', ipAddress)}
            className="h-8 text-xs font-semibold"
          >
            Show in HTTP Checks
          </Button>
        </div>

        {/* Loading / Error States */}
        {isLoading && (
          <div className="flex items-center justify-center py-12 text-muted-foreground text-xs">
            Loading host details...
          </div>
        )}

        {error && (
          <div className="p-3 rounded-md bg-destructive/10 text-destructive text-xs">
            Failed to load host details.
          </div>
        )}

        {data && (
          <div className="space-y-6">
            {/* Discovery Lineage */}
            <div className="space-y-2 border rounded-md p-3.5 bg-muted/20">
              <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                Discovery Lineage
              </h3>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div>
                  <span className="text-muted-foreground">Depth: </span>
                  <span className="font-mono font-medium">
                    {data.depth} {data.depth === 0 ? '(Root Target)' : '(SAN Expansion)'}
                  </span>
                </div>
                <div>
                  <span className="text-muted-foreground">Root Target: </span>
                  <span className="font-mono font-medium">{data.root_target || 'N/A'}</span>
                </div>
                <div className="col-span-2">
                  <span className="text-muted-foreground">Discovered From: </span>
                  {data.discovered_from && data.discovered_from.length > 0 ? (
                    <span className="font-mono font-medium">{data.discovered_from.join(', ')}</span>
                  ) : (
                    <span className="text-muted-foreground italic">Direct</span>
                  )}
                </div>
                <div className="col-span-2">
                  <span className="text-muted-foreground">Resolved Domains: </span>
                  {data.resolved_domains && data.resolved_domains.length > 0 ? (
                    <div className="flex flex-wrap gap-1 mt-1">
                      {data.resolved_domains.map((dom) => (
                        <span key={dom} className="px-1.5 py-0.5 rounded bg-muted text-[11px] font-mono">
                          {dom}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <span className="text-muted-foreground italic">None</span>
                  )}
                </div>
              </div>
            </div>

            {/* Services Table */}
            <div className="space-y-2">
              <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                Services ({data.services?.length || 0})
              </h3>
              {(!data.services || data.services.length === 0) ? (
                <p className="text-xs text-muted-foreground italic py-2">No services discovered on this host.</p>
              ) : (
                <div className="border rounded-md divide-y overflow-hidden">
                  {data.services.map((svc) => (
                    <div key={svc.port_number} className="p-3 text-xs space-y-1.5 hover:bg-muted/10">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="font-mono font-bold text-sm">{svc.port_number}</span>
                          <span className="text-muted-foreground font-mono uppercase text-[10px]">{svc.tcp_status}</span>
                          <EntityStatusBadge status={svc.status} />
                          {svc.tcp_latency_ms !== null && svc.tcp_latency_ms !== undefined && (
                            <span className="text-muted-foreground font-mono text-[11px]">
                              <FormatLatency ms={svc.tcp_latency_ms} />
                            </span>
                          )}
                        </div>
                        {svc.finding_codes && svc.finding_codes.length > 0 && (
                          <div className="flex gap-1">
                            {svc.finding_codes.map((f) => (
                              <FindingBadge key={f} code={f} />
                            ))}
                          </div>
                        )}
                      </div>
                      {svc.tls_certificate && (
                        <div className="mt-1 p-2 rounded bg-muted/30 text-[11px] font-mono space-y-1">
                          <div className="flex items-center justify-between">
                            <span className="font-semibold text-foreground">
                              {svc.tls_certificate.protocol_version || 'TLS'}
                            </span>
                            <span className={svc.tls_certificate.valid ? 'text-green-600 dark:text-green-400 font-bold' : 'text-red-600 font-bold'}>
                              {svc.tls_certificate.valid ? 'Valid' : 'Invalid'}
                            </span>
                          </div>
                          {svc.tls_certificate.issuer && (
                            <div className="truncate text-muted-foreground">
                              <span>Issuer: </span>
                              <span>{svc.tls_certificate.issuer}</span>
                            </div>
                          )}
                          {svc.tls_certificate.expires_in_days !== undefined && svc.tls_certificate.expires_in_days !== null && (
                            <div>
                              Expires: <FormatTlsExpiry days={svc.tls_certificate.expires_in_days} />
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* HTTP Checks Table */}
            <div className="space-y-2">
              <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                HTTP Checks ({data.checks?.length || 0})
              </h3>
              {(!data.checks || data.checks.length === 0) ? (
                <p className="text-xs text-muted-foreground italic py-2">No HTTP checks recorded for this host.</p>
              ) : (
                <div className="border rounded-md divide-y overflow-hidden">
                  {data.checks.map((chk, idx) => (
                    <div key={idx} className="p-3 text-xs space-y-1.5 hover:bg-muted/10">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="font-mono font-bold">Port {chk.port}</span>
                          <span className="font-mono text-muted-foreground">{chk.domain}</span>
                          {chk.status_code && <FormatHttpStatus code={chk.status_code} />}
                        </div>
                        {chk.http_latency_ms !== null && chk.http_latency_ms !== undefined && (
                          <span className="text-muted-foreground font-mono text-[11px]">
                            <FormatLatency ms={chk.http_latency_ms} />
                          </span>
                        )}
                      </div>
                      {chk.redirects_to_url && (
                        <div className="text-[11px] font-mono text-muted-foreground truncate">
                          Redirects to: <span className="text-foreground">{chk.redirects_to_url}</span>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Certificate SANs Badges */}
            <div className="space-y-2">
              <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                Certificate SANs ({data.tls_sans?.length || 0})
              </h3>
              {(!data.tls_sans || data.tls_sans.length === 0) ? (
                <p className="text-xs text-muted-foreground italic py-1">No certificate SANs discovered on this host.</p>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {data.tls_sans.map((san) => (
                    <span
                      key={san}
                      className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono bg-primary/10 text-primary border border-primary/20"
                    >
                      {san}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
  )
}
