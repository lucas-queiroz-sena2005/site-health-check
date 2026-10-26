import { useState, useEffect, useCallback, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import {
  useRunDetail,
  useRunHosts,
  useRunServices,
  useRunChecks,
  RunHistorySheet,
  EntityStatusBadge,
  FindingBadge,
  FormatLatency,
  FormatTlsExpiry,
  FormatTlsVersion,
  FormatHttpStatus,
} from '@/features/scans'
import type { TableQueryParams } from '@/features/scans/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

const CANONICAL_FINDINGS = [
  'TCP_CLOSED',
  'TLS_INVALID',
  'TLS_EXPIRED',
  'TLS_EXPIRING_SOON',
  'TLS_DEPRECATED_VERSION',
  'HTTP_5XX',
  'HTTP_4XX',
  'HTTP_ERROR',
  'HOST_GHOST',
]

export function HostTablePage() {
  const [searchParams, setSearchParams] = useSearchParams()

  const runParam = searchParams.get('run') || searchParams.get('run_id')
  const [selectedRunId, setSelectedRunId] = useState<string | null>(runParam)

  // Fetch latest run if runId is not in URL
  const { data: latestRuns } = useQuery({
    queryKey: ['runs', 'latest'],
    queryFn: async () => {
      const res = await fetch('/api/runs?limit=1')
      if (!res.ok) throw new Error('Network error')
      return res.json()
    },
    enabled: !selectedRunId,
  })

  useEffect(() => {
    if (!selectedRunId && latestRuns && latestRuns.length > 0) {
      const latestRunId = latestRuns[0].id
      setSelectedRunId(latestRunId)
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          next.set('run', latestRunId)
          return next
        },
        { replace: true }
      )
    }
  }, [selectedRunId, latestRuns, setSearchParams])

  // Sync selectedRunId from URL
  useEffect(() => {
    if (runParam && runParam !== selectedRunId) {
      setSelectedRunId(runParam)
    }
  }, [runParam, selectedRunId])

  // Active Tab
  const activeTab = (searchParams.get('tab') as 'hosts' | 'services' | 'checks') || 'hosts'
  const handleTabChange = useCallback(
    (tab: 'hosts' | 'services' | 'checks') => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        next.set('tab', tab)
        next.delete('page')
        return next
      })
    },
    [setSearchParams]
  )

  // URL Query Parameters for Tables
  const qParam = searchParams.get('q') || ''
  const ipParam = searchParams.get('ip') || ''
  const statusParam = searchParams.get('status') || 'all'
  const portParam = searchParams.get('port') ? Number(searchParams.get('port')) : undefined
  const findingParam = searchParams.get('finding') || ''
  const includeClosedParam = searchParams.get('include_closed') === 'true'
  const sortByParam = searchParams.get('sort_by') || 'ip_address'
  const sortDirParam = (searchParams.get('sort_dir') as 'asc' | 'desc') || 'asc'
  const limitParam = Number(searchParams.get('limit') || 50)
  const pageParam = Number(searchParams.get('page') || 1)
  const offsetParam = (pageParam - 1) * limitParam

  // Local state for debounced search
  const [searchInput, setSearchInput] = useState(qParam)
  useEffect(() => {
    setSearchInput(qParam)
  }, [qParam])

  useEffect(() => {
    const timer = setTimeout(() => {
      if (searchInput !== qParam) {
        setSearchParams((prev) => {
          const next = new URLSearchParams(prev)
          if (searchInput.trim()) {
            next.set('q', searchInput.trim())
          } else {
            next.delete('q')
          }
          next.delete('page')
          return next
        })
      }
    }, 300)
    return () => clearTimeout(timer)
  }, [searchInput, qParam, setSearchParams])

  // Fetch Run Detail for Metadata and Summary
  const { data: run, isLoading: isRunLoading, error: runError } = useRunDetail(selectedRunId || undefined)
  const summary = run?.metrics_json?.summary

  // Table Query Params object
  const queryParams: TableQueryParams = useMemo(
    () => ({
      q: qParam || undefined,
      ip: ipParam || undefined,
      status: statusParam === 'all' ? undefined : statusParam,
      port: portParam,
      finding: findingParam || undefined,
      include_closed: activeTab === 'services' ? includeClosedParam : undefined,
      sort_by: sortByParam,
      sort_dir: sortDirParam,
      limit: limitParam,
      offset: offsetParam,
    }),
    [
      qParam,
      ipParam,
      statusParam,
      portParam,
      findingParam,
      activeTab,
      includeClosedParam,
      sortByParam,
      sortDirParam,
      limitParam,
      offsetParam,
    ]
  )

  // Fetch Table Data
  const hostsQuery = useRunHosts(activeTab === 'hosts' ? selectedRunId || undefined : undefined, queryParams)
  const servicesQuery = useRunServices(
    activeTab === 'services' ? selectedRunId || undefined : undefined,
    queryParams
  )
  const checksQuery = useRunChecks(
    activeTab === 'checks' ? selectedRunId || undefined : undefined,
    queryParams
  )

  const activeTableQuery = activeTab === 'hosts' ? hostsQuery : activeTab === 'services' ? servicesQuery : checksQuery
  const currentTotal = activeTableQuery.data?.total || 0

  // Saved Views Integration
  const [savedViews, setSavedViews] = useState<any[]>([
    { id: 'view-default', name: 'Default View (All Targets)', search: '', statuses: ['all'], table_sort_by: null, table_sort_dir: 'asc' },
  ])
  const [activeViewId, setActiveViewId] = useState('view-default')
  const [isSavingView, setIsSavingView] = useState(false)
  const [newViewName, setNewViewName] = useState('')

  const { data: fetchedViews } = useQuery({
    queryKey: ['views'],
    queryFn: async () => {
      const res = await fetch('/api/views')
      if (!res.ok) throw new Error('Network error')
      return res.json()
    },
  })

  useEffect(() => {
    if (fetchedViews) {
      const defaultView = {
        id: 'view-default',
        name: 'Default View (All Targets)',
        search: '',
        statuses: ['all'],
        table_sort_by: null,
        table_sort_dir: 'asc',
      }
      setSavedViews([defaultView, ...fetchedViews])
    }
  }, [fetchedViews])

  const handleSelectSavedView = useCallback(
    (viewId: string) => {
      setActiveViewId(viewId)
      if (viewId === 'custom-new') {
        setIsSavingView(true)
        return
      }
      const view = savedViews.find((v) => v.id === viewId)
      if (view) {
        setSearchParams((prev) => {
          const next = new URLSearchParams(prev)
          if (view.search) next.set('q', view.search)
          else next.delete('q')

          if (view.statuses && view.statuses.length > 0 && !view.statuses.includes('all')) {
            next.set('status', view.statuses.join(','))
          } else {
            next.delete('status')
          }

          if (view.table_sort_by) next.set('sort_by', view.table_sort_by)
          else next.delete('sort_by')

          if (view.table_sort_dir) next.set('sort_dir', view.table_sort_dir)
          else next.delete('sort_dir')

          if (!viewId.startsWith('view-default')) next.set('view', viewId)
          else next.delete('view')

          next.delete('page')
          return next
        })
      }
    },
    [savedViews, setSearchParams]
  )

  const handleSaveViewSubmit = useCallback(async () => {
    if (newViewName.trim()) {
      try {
        const payload = {
          name: newViewName.trim(),
          search: qParam || null,
          statuses: statusParam ? statusParam.split(',') : ['all'],
          table_sort_by: sortByParam || null,
          table_sort_dir: sortDirParam || 'asc',
        }
        const response = await fetch('/api/views', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        })
        if (response.ok) {
          const data = await response.json()
          setSavedViews((prev) => [...prev, data])
          setActiveViewId(data.id)
          setSearchParams((prev) => {
            const next = new URLSearchParams(prev)
            next.set('view', data.id)
            return next
          })
        }
      } catch (err) {
        console.error('Failed to save view:', err)
      }
    }
    setIsSavingView(false)
    setNewViewName('')
  }, [newViewName, qParam, statusParam, sortByParam, sortDirParam, setSearchParams])

  const handleDeleteView = useCallback(async () => {
    if (activeViewId && activeViewId !== 'view-default') {
      try {
        const res = await fetch(`/api/views/${activeViewId}`, { method: 'DELETE' })
        if (res.ok) {
          setSavedViews((prev) => prev.filter((v) => v.id !== activeViewId))
          handleSelectSavedView('view-default')
        }
      } catch (err) {
        console.error('Failed to delete view:', err)
      }
    }
  }, [activeViewId, handleSelectSavedView])

  // Sort toggle handler
  const handleSort = useCallback(
    (colName: string) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        if (sortByParam === colName) {
          next.set('sort_dir', sortDirParam === 'asc' ? 'desc' : 'asc')
        } else {
          next.set('sort_by', colName)
          next.set('sort_dir', 'asc')
        }
        next.delete('page')
        return next
      })
    },
    [sortByParam, sortDirParam, setSearchParams]
  )

  // Status Filter Pill Toggle Handler
  const handleStatusToggle = useCallback(
    (st: string) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        const currentStatuses = statusParam === 'all' ? [] : statusParam.split(',').filter(Boolean)

        if (st === 'all') {
          next.delete('status')
        } else {
          let updated: string[]
          if (currentStatuses.includes(st)) {
            updated = currentStatuses.filter((s) => s !== st)
          } else {
            updated = [...currentStatuses, st]
          }
          if (updated.length === 0 || updated.length === 4) {
            next.delete('status')
          } else {
            next.set('status', updated.join(','))
          }
        }
        next.delete('page')
        return next
      })
    },
    [statusParam, setSearchParams]
  )

  // IP filter chip clear
  const handleClearIp = useCallback(() => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.delete('ip')
      next.delete('page')
      return next
    })
  }, [setSearchParams])

  // Open Drawer handler
  const handleOpenDrawer = useCallback(
    (ip: string) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        next.set('drawer', ip)
        return next
      })
    },
    [setSearchParams]
  )

  // Pagination navigation
  const totalPages = Math.ceil(currentTotal / limitParam) || 1
  const handlePageChange = useCallback(
    (newPage: number) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        if (newPage <= 1) next.delete('page')
        else next.set('page', String(newPage))
        return next
      })
    },
    [setSearchParams]
  )

  const handleLimitChange = useCallback(
    (newLimit: number) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        next.set('limit', String(newLimit))
        next.delete('page')
        return next
      })
    },
    [setSearchParams]
  )

  if (isRunLoading) return <div className="p-8 text-muted-foreground">Loading scans...</div>
  if (runError) return <div className="p-8 text-destructive">Error loading scans.</div>

  const hostsCount = summary ? summary.active + summary.warning + summary.failed + summary.ghost : 0

  return (
    <div className="w-full flex-1 flex flex-col bg-background">
      {/* 1. Header & Run Summary Strip */}
      <div className="px-6 py-4 shrink-0 border-b border-border bg-muted/30 flex justify-between items-center">
        <div className="flex items-center gap-6">
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Run ID</span>
              <span className="text-sm font-mono font-bold bg-background border px-2 py-0.5 rounded">
                {selectedRunId || 'Latest'}
              </span>
              {run?.scan_name && (
                <span className="text-sm font-semibold text-foreground ml-1">
                  ({run.scan_name})
                </span>
              )}
            </div>
            <p className="text-muted-foreground text-sm font-mono font-semibold">
              <span className="text-foreground">{run?.metrics_json?.total_targets_scanned || 0}</span> IPs scanned •{' '}
              <span className="text-foreground">{run?.metrics_json?.scan_duration_seconds || 0}s</span> duration
            </p>
          </div>

          <div className="h-8 w-px bg-border mx-2"></div>

          {summary && (
            <div className="flex items-center gap-3 text-xs font-mono font-bold">
              <div className="flex items-center gap-1.5 bg-green-500/10 text-green-600 dark:text-green-400 px-2 py-1 rounded border border-green-500/20">
                <span className="uppercase tracking-wider opacity-70">Active</span>
                <span>{summary.active ?? 0}</span>
              </div>
              <div className="flex items-center gap-1.5 bg-yellow-500/10 text-yellow-600 dark:text-yellow-400 px-2 py-1 rounded border border-yellow-500/20">
                <span className="uppercase tracking-wider opacity-70">Warning</span>
                <span>{summary.warning ?? 0}</span>
              </div>
              <div className="flex items-center gap-1.5 bg-red-500/10 text-red-600 dark:text-red-400 px-2 py-1 rounded border border-red-500/20">
                <span className="uppercase tracking-wider opacity-70">Failed</span>
                <span>{summary.failed ?? 0}</span>
              </div>
              <div className="flex items-center gap-1.5 bg-purple-500/10 text-purple-600 dark:text-purple-400 px-2 py-1 rounded border border-purple-500/20">
                <span className="uppercase tracking-wider opacity-70">Ghost</span>
                <span>{summary.ghost ?? 0}</span>
              </div>
              <div className="flex items-center gap-1.5 bg-slate-500/10 text-slate-600 dark:text-slate-400 px-2 py-1 rounded border border-slate-500/20">
                <span className="uppercase tracking-wider opacity-70">Void</span>
                <span>{summary.void ?? 0}</span>
              </div>
            </div>
          )}
        </div>

        <div className="flex items-center gap-3">
          <RunHistorySheet
            selectedRunId={selectedRunId}
            onSelectRun={(id) => {
              setSelectedRunId(id)
              setSearchParams((prev) => {
                const next = new URLSearchParams(prev)
                if (id) {
                  next.set('run', id)
                } else {
                  next.delete('run')
                }
                return next
              })
            }}
          />
        </div>
      </div>

      {/* 2. Filter Toolbar & Saved Views */}
      <div className="px-6 py-3 shrink-0 bg-muted/20 flex items-center gap-4 flex-wrap border-b border-border shadow-sm">
        {/* Saved Views */}
        <div className="flex items-center gap-2 shrink-0">
          {isSavingView ? (
            <div className="flex items-center gap-2">
              <span className="text-muted-foreground text-xs font-semibold">Save View:</span>
              <Input
                type="text"
                placeholder="View name..."
                autoFocus
                value={newViewName}
                onChange={(e) => setNewViewName(e.target.value)}
                className="bg-background text-foreground h-8 text-xs font-mono font-semibold w-40"
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleSaveViewSubmit()
                  if (e.key === 'Escape') setIsSavingView(false)
                }}
              />
              <Button size="sm" onClick={handleSaveViewSubmit} className="h-8 px-2 text-xs font-semibold">
                ✓ Save
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  setIsSavingView(false)
                  setActiveViewId('view-default')
                }}
                className="h-8 px-2 text-xs"
              >
                ✕ Cancel
              </Button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <span className="text-muted-foreground text-xs font-semibold">Global View:</span>
              <select
                value={activeViewId}
                onChange={(e) => handleSelectSavedView(e.target.value)}
                className="bg-background text-foreground border border-border rounded px-2.5 py-1 text-xs font-mono font-semibold focus:outline-none focus:ring-1 focus:ring-primary cursor-pointer max-w-[200px]"
              >
                {savedViews.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.name}
                  </option>
                ))}
              </select>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setIsSavingView(true)}
                className="h-7 px-2 text-xs"
                title="Save Current View"
              >
                + Create
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleDeleteView}
                disabled={!activeViewId || activeViewId === 'view-default'}
                className="h-7 px-2 text-xs text-destructive hover:text-destructive disabled:opacity-40"
                title="Delete View"
              >
                ✕
              </Button>
            </div>
          )}
        </div>

        {/* Search Input */}
        <div className="flex items-center gap-2 min-w-[220px] max-w-sm">
          <Input
            type="text"
            placeholder="Search IP, domain, issuer, findings..."
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className="w-full bg-background border border-border h-8 text-xs placeholder:text-muted-foreground focus:ring-1 focus:ring-primary"
          />
        </div>

        {/* Active IP Filter Chip */}
        {ipParam && (
          <div
            data-testid="ip-filter-chip"
            className="inline-flex items-center gap-1.5 bg-primary/10 text-primary border border-primary/20 px-2 py-1 rounded-full text-xs font-mono font-semibold"
          >
            <span>Host: {ipParam}</span>
            <button
              aria-label="Clear IP filter"
              onClick={handleClearIp}
              className="text-primary hover:text-primary/70 font-bold ml-1"
            >
              ×
            </button>
          </div>
        )}

        {/* Port Filter (Services & Checks) */}
        {(activeTab === 'services' || activeTab === 'checks') && (
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-muted-foreground font-semibold">Port:</span>
            <Input
              type="number"
              placeholder="e.g. 443"
              value={portParam !== undefined ? portParam : ''}
              onChange={(e) => {
                const val = e.target.value.trim()
                setSearchParams((prev) => {
                  const next = new URLSearchParams(prev)
                  if (val) next.set('port', val)
                  else next.delete('port')
                  next.delete('page')
                  return next
                })
              }}
              className="w-20 bg-background border border-border h-8 text-xs font-mono"
            />
          </div>
        )}

        {/* Finding Code Filter */}
        <div className="flex items-center gap-1.5">
          <select
            value={findingParam}
            onChange={(e) => {
              const val = e.target.value
              setSearchParams((prev) => {
                const next = new URLSearchParams(prev)
                if (val) next.set('finding', val)
                else next.delete('finding')
                next.delete('page')
                return next
              })
            }}
            className="bg-background text-foreground border border-border rounded px-2 py-1 text-xs font-mono cursor-pointer"
          >
            <option value="">All Findings</option>
            {CANONICAL_FINDINGS.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
        </div>

        {/* Include Closed Ports (Services Tab) */}
        {activeTab === 'services' && (
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground font-semibold cursor-pointer">
            <input
              type="checkbox"
              checked={includeClosedParam}
              onChange={(e) => {
                const checked = e.target.checked
                setSearchParams((prev) => {
                  const next = new URLSearchParams(prev)
                  if (checked) next.set('include_closed', 'true')
                  else next.delete('include_closed')
                  next.delete('page')
                  return next
                })
              }}
              className="rounded border-border text-primary focus:ring-primary h-3.5 w-3.5"
            />
            <span>Include Closed Ports</span>
          </label>
        )}

        {/* Status Toggle Pills */}
        <div className="flex items-center gap-1 ml-auto bg-muted/40 border border-border p-0.5 rounded-lg font-mono text-xs">
          {(['all', 'active', 'warning', 'failed', 'ghost'] as const).map((st) => {
            const isSelected =
              st === 'all'
                ? statusParam === 'all' || !statusParam
                : statusParam.split(',').includes(st)
            return (
              <button
                key={st}
                onClick={() => handleStatusToggle(st)}
                className={`px-3 py-1 rounded capitalize transition-all ${
                  isSelected
                    ? 'bg-background shadow-sm font-bold text-foreground'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
                }`}
              >
                {st}
              </button>
            )
          })}
        </div>
      </div>

      {/* 3. Three Tabs Navigation */}
      <div className="px-6 pt-3 shrink-0 border-b border-border bg-background flex items-center gap-2" role="tablist">
        <button
          role="tab"
          aria-selected={activeTab === 'hosts'}
          onClick={() => handleTabChange('hosts')}
          className={`flex items-center gap-2 px-4 py-2 border-b-2 font-semibold text-sm transition-colors ${
            activeTab === 'hosts'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          <span>Hosts</span>
          <span className="bg-muted px-2 py-0.5 rounded-full text-xs font-mono text-foreground font-bold">
            {hostsCount}
          </span>
        </button>

        <button
          role="tab"
          aria-selected={activeTab === 'services'}
          onClick={() => handleTabChange('services')}
          className={`flex items-center gap-2 px-4 py-2 border-b-2 font-semibold text-sm transition-colors ${
            activeTab === 'services'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          <span>Services</span>
          <span className="bg-muted px-2 py-0.5 rounded-full text-xs font-mono text-foreground font-bold">
            {summary?.service_count ?? 0}
          </span>
        </button>

        <button
          role="tab"
          aria-selected={activeTab === 'checks'}
          onClick={() => handleTabChange('checks')}
          className={`flex items-center gap-2 px-4 py-2 border-b-2 font-semibold text-sm transition-colors ${
            activeTab === 'checks'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          <span>HTTP Checks</span>
          <span className="bg-muted px-2 py-0.5 rounded-full text-xs font-mono text-foreground font-bold">
            {summary?.http_check_count ?? 0}
          </span>
        </button>
      </div>

      {/* 4. Table Views */}
      <div className="flex-1 overflow-auto p-6">
        {activeTableQuery.isLoading ? (
          <div className="text-center py-12 text-sm text-muted-foreground">Loading table data...</div>
        ) : activeTableQuery.isError ? (
          <div className="text-center py-12 text-sm text-destructive">Failed to load table items.</div>
        ) : (
          <Table>
            <TableHeader className="bg-muted/50 sticky top-0">
              {activeTab === 'hosts' && (
                <TableRow>
                  <TableHead className="cursor-pointer font-bold" onClick={() => handleSort('ip_address')}>
                    IP Address {sortByParam === 'ip_address' ? (sortDirParam === 'asc' ? '▲' : '▼') : ''}
                  </TableHead>
                  <TableHead className="cursor-pointer font-bold" onClick={() => handleSort('status')}>
                    Status {sortByParam === 'status' ? (sortDirParam === 'asc' ? '▲' : '▼') : ''}
                  </TableHead>
                  <TableHead className="cursor-pointer font-bold" onClick={() => handleSort('depth')}>
                    Depth {sortByParam === 'depth' ? (sortDirParam === 'asc' ? '▲' : '▼') : ''}
                  </TableHead>
                  <TableHead className="cursor-pointer font-bold" onClick={() => handleSort('vhost_count')}>
                    VHosts {sortByParam === 'vhost_count' ? (sortDirParam === 'asc' ? '▲' : '▼') : ''}
                  </TableHead>
                  <TableHead className="cursor-pointer font-bold" onClick={() => handleSort('open_port_count')}>
                    Open Ports {sortByParam === 'open_port_count' ? (sortDirParam === 'asc' ? '▲' : '▼') : ''}
                  </TableHead>
                  <TableHead className="cursor-pointer font-bold" onClick={() => handleSort('min_tcp_latency_ms')}>
                    Min Latency {sortByParam === 'min_tcp_latency_ms' ? (sortDirParam === 'asc' ? '▲' : '▼') : ''}
                  </TableHead>
                  <TableHead className="cursor-pointer font-bold" onClick={() => handleSort('min_tls_expires_days')}>
                    Min TLS Expiry {sortByParam === 'min_tls_expires_days' ? (sortDirParam === 'asc' ? '▲' : '▼') : ''}
                  </TableHead>
                  <TableHead className="cursor-pointer font-bold" onClick={() => handleSort('worst_tls_version')}>
                    Worst TLS {sortByParam === 'worst_tls_version' ? (sortDirParam === 'asc' ? '▲' : '▼') : ''}
                  </TableHead>
                  <TableHead className="cursor-pointer font-bold" onClick={() => handleSort('worst_http_status')}>
                    Worst HTTP {sortByParam === 'worst_http_status' ? (sortDirParam === 'asc' ? '▲' : '▼') : ''}
                  </TableHead>
                  <TableHead className="font-bold">Findings</TableHead>
                </TableRow>
              )}

              {activeTab === 'services' && (
                <TableRow>
                  <TableHead className="cursor-pointer font-bold" onClick={() => handleSort('ip_address')}>
                    IP Address {sortByParam === 'ip_address' ? (sortDirParam === 'asc' ? '▲' : '▼') : ''}
                  </TableHead>
                  <TableHead className="cursor-pointer font-bold" onClick={() => handleSort('port')}>
                    Port {sortByParam === 'port' ? (sortDirParam === 'asc' ? '▲' : '▼') : ''}
                  </TableHead>
                  <TableHead className="cursor-pointer font-bold" onClick={() => handleSort('status')}>
                    Status {sortByParam === 'status' ? (sortDirParam === 'asc' ? '▲' : '▼') : ''}
                  </TableHead>
                  <TableHead className="cursor-pointer font-bold" onClick={() => handleSort('depth')}>
                    Depth {sortByParam === 'depth' ? (sortDirParam === 'asc' ? '▲' : '▼') : ''}
                  </TableHead>
                  <TableHead className="cursor-pointer font-bold" onClick={() => handleSort('tcp_latency_ms')}>
                    TCP Latency {sortByParam === 'tcp_latency_ms' ? (sortDirParam === 'asc' ? '▲' : '▼') : ''}
                  </TableHead>
                  <TableHead className="cursor-pointer font-bold" onClick={() => handleSort('tls_valid')}>
                    TLS Valid {sortByParam === 'tls_valid' ? (sortDirParam === 'asc' ? '▲' : '▼') : ''}
                  </TableHead>
                  <TableHead className="cursor-pointer font-bold" onClick={() => handleSort('tls_expires_in_days')}>
                    TLS Expiry {sortByParam === 'tls_expires_in_days' ? (sortDirParam === 'asc' ? '▲' : '▼') : ''}
                  </TableHead>
                  <TableHead className="cursor-pointer font-bold" onClick={() => handleSort('tls_version')}>
                    TLS Version {sortByParam === 'tls_version' ? (sortDirParam === 'asc' ? '▲' : '▼') : ''}
                  </TableHead>
                  <TableHead className="cursor-pointer font-bold" onClick={() => handleSort('tls_issuer')}>
                    Issuer {sortByParam === 'tls_issuer' ? (sortDirParam === 'asc' ? '▲' : '▼') : ''}
                  </TableHead>
                  <TableHead className="cursor-pointer font-bold" onClick={() => handleSort('san_count')}>
                    SAN Count {sortByParam === 'san_count' ? (sortDirParam === 'asc' ? '▲' : '▼') : ''}
                  </TableHead>
                  <TableHead className="cursor-pointer font-bold" onClick={() => handleSort('http_check_count')}>
                    HTTP Checks {sortByParam === 'http_check_count' ? (sortDirParam === 'asc' ? '▲' : '▼') : ''}
                  </TableHead>
                  <TableHead className="cursor-pointer font-bold" onClick={() => handleSort('worst_http_status')}>
                    Worst HTTP {sortByParam === 'worst_http_status' ? (sortDirParam === 'asc' ? '▲' : '▼') : ''}
                  </TableHead>
                  <TableHead className="font-bold">Findings</TableHead>
                </TableRow>
              )}

              {activeTab === 'checks' && (
                <TableRow>
                  <TableHead className="cursor-pointer font-bold" onClick={() => handleSort('ip_address')}>
                    IP Address {sortByParam === 'ip_address' ? (sortDirParam === 'asc' ? '▲' : '▼') : ''}
                  </TableHead>
                  <TableHead className="cursor-pointer font-bold" onClick={() => handleSort('port')}>
                    Port {sortByParam === 'port' ? (sortDirParam === 'asc' ? '▲' : '▼') : ''}
                  </TableHead>
                  <TableHead className="cursor-pointer font-bold" onClick={() => handleSort('domain')}>
                    Domain {sortByParam === 'domain' ? (sortDirParam === 'asc' ? '▲' : '▼') : ''}
                  </TableHead>
                  <TableHead className="cursor-pointer font-bold" onClick={() => handleSort('status')}>
                    Status {sortByParam === 'status' ? (sortDirParam === 'asc' ? '▲' : '▼') : ''}
                  </TableHead>
                  <TableHead className="cursor-pointer font-bold" onClick={() => handleSort('status_code')}>
                    HTTP Code {sortByParam === 'status_code' ? (sortDirParam === 'asc' ? '▲' : '▼') : ''}
                  </TableHead>
                  <TableHead className="cursor-pointer font-bold" onClick={() => handleSort('http_latency_ms')}>
                    Latency {sortByParam === 'http_latency_ms' ? (sortDirParam === 'asc' ? '▲' : '▼') : ''}
                  </TableHead>
                  <TableHead className="cursor-pointer font-bold" onClick={() => handleSort('redirects_to_url')}>
                    Redirect To {sortByParam === 'redirects_to_url' ? (sortDirParam === 'asc' ? '▲' : '▼') : ''}
                  </TableHead>
                  <TableHead className="cursor-pointer font-bold" onClick={() => handleSort('server_header')}>
                    Server {sortByParam === 'server_header' ? (sortDirParam === 'asc' ? '▲' : '▼') : ''}
                  </TableHead>
                  <TableHead className="font-bold">Notes</TableHead>
                  <TableHead className="cursor-pointer font-bold" onClick={() => handleSort('finding_code')}>
                    Finding {sortByParam === 'finding_code' ? (sortDirParam === 'asc' ? '▲' : '▼') : ''}
                  </TableHead>
                </TableRow>
              )}
            </TableHeader>

            <TableBody>
              {activeTableQuery.data?.items.length === 0 ? (
                <TableRow>
                  <TableCell
                    colSpan={activeTab === 'hosts' ? 10 : activeTab === 'services' ? 13 : 10}
                    className="h-32 text-center text-muted-foreground font-medium"
                  >
                    No rows match the selected filters.
                  </TableCell>
                </TableRow>
              ) : (
                <>
                  {activeTab === 'hosts' &&
                    (activeTableQuery.data?.items as any[])?.map((h) => (
                      <TableRow key={h.ip_address} className="hover:bg-muted/30 font-mono text-xs">
                        {/* Strict IP Leftmost Column */}
                        <TableCell className="font-bold">
                          <button
                            onClick={() => handleOpenDrawer(h.ip_address)}
                            className="text-primary hover:underline font-mono text-xs font-bold text-left"
                          >
                            {h.ip_address}
                          </button>
                        </TableCell>
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
                          <div className="flex flex-wrap gap-1 max-w-[200px]">
                            {h.finding_codes?.map((code: string) => (
                              <FindingBadge key={code} code={code} />
                            ))}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}

                  {activeTab === 'services' &&
                    (activeTableQuery.data?.items as any[])?.map((s) => (
                      <TableRow key={`${s.ip_address}-${s.port}`} className="hover:bg-muted/30 font-mono text-xs">
                        {/* Strict IP Leftmost Column */}
                        <TableCell className="font-bold">
                          <button
                            onClick={() => handleOpenDrawer(s.ip_address)}
                            className="text-primary hover:underline font-mono text-xs font-bold text-left"
                          >
                            {s.ip_address}
                          </button>
                        </TableCell>
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
                          <div className="flex flex-wrap gap-1 max-w-[200px]">
                            {s.finding_codes?.map((code: string) => (
                              <FindingBadge key={code} code={code} />
                            ))}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}

                  {activeTab === 'checks' &&
                    (activeTableQuery.data?.items as any[])?.map((c, idx) => (
                      <TableRow key={`${c.ip_address}-${c.port}-${c.domain}-${idx}`} className="hover:bg-muted/30 font-mono text-xs">
                        {/* Strict IP Leftmost Column */}
                        <TableCell className="font-bold">
                          <button
                            onClick={() => handleOpenDrawer(c.ip_address)}
                            className="text-primary hover:underline font-mono text-xs font-bold text-left"
                          >
                            {c.ip_address}
                          </button>
                        </TableCell>
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
                        <TableCell className="max-w-[150px] truncate" title={c.notes || ''}>
                          {c.notes || '—'}
                        </TableCell>
                        <TableCell>
                          {c.finding_code ? <FindingBadge code={c.finding_code} /> : <span className="text-muted-foreground/60">—</span>}
                        </TableCell>
                      </TableRow>
                    ))}
                </>
              )}
            </TableBody>
          </Table>
        )}
      </div>

      {/* 5. Pagination Footer */}
      <div className="px-6 py-3 shrink-0 border-t border-border bg-muted/20 flex items-center justify-between text-xs text-muted-foreground">
        <div className="flex items-center gap-2">
          <span>Rows per page:</span>
          <select
            value={limitParam}
            onChange={(e) => handleLimitChange(Number(e.target.value))}
            className="bg-background text-foreground border border-border rounded px-2 py-1 text-xs font-mono cursor-pointer"
          >
            <option value={25}>25</option>
            <option value={50}>50</option>
            <option value={100}>100</option>
          </select>
        </div>

        <div className="flex items-center gap-4">
          <span>
            {currentTotal > 0 ? `${offsetParam + 1}–${Math.min(offsetParam + limitParam, currentTotal)} of ${currentTotal}` : '0 of 0'}
          </span>
          <div className="flex items-center gap-1">
            <Button
              variant="outline"
              size="sm"
              disabled={pageParam <= 1}
              onClick={() => handlePageChange(pageParam - 1)}
              className="h-7 px-2 text-xs"
            >
              ‹ Prev
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={pageParam >= totalPages}
              onClick={() => handlePageChange(pageParam + 1)}
              className="h-7 px-2 text-xs"
            >
              Next ›
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
