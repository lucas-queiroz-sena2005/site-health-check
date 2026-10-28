import { useState, useEffect, useCallback, useMemo } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams, Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import {
  useRunDetail,
  useRunHosts,
  useRunServices,
  useRunChecks,
  RunSummaryHeader,
  RunHistorySheet,
  ScanFilterToolbar,
  ScanTabsNav,
  TablePaginationBar,
  HostsTable,
  ServicesTable,
  ChecksTable,
  HostDetailDrawer,
  ScanRunStatus,
} from '@/features/scans'
import type { ScanRunResponse, TableQueryParams, SavedView } from '@/features/scans'

export function HostTablePage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const queryClient = useQueryClient()

  // 1. Run ID & URL Sync
  const runParam = searchParams.get('run') || searchParams.get('run_id')

  const { data: latestRuns, isLoading: isLatestRunsLoading } = useQuery<ScanRunResponse[]>({
    queryKey: ['runs', 'latest'],
    queryFn: async () => {
      const res = await fetch('/api/runs?limit=1')
      if (!res.ok) throw new Error('Network error')
      return res.json()
    },
    enabled: !runParam,
  })

  const selectedRunId = runParam || (latestRuns && latestRuns.length > 0 ? latestRuns[0].id : null)

  useEffect(() => {
    if (!runParam && latestRuns && latestRuns.length > 0) {
      const latestRunId = latestRuns[0].id
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          next.set('run', latestRunId)
          return next
        },
        { replace: true }
      )
    }
  }, [runParam, latestRuns, setSearchParams])

  // 2. Active Tab & Navigation
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

  // 3. Table Query Parameters from URL
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
  const drawerParam = searchParams.get('drawer') || null

  // Debounced search input
  const [searchInput, setSearchInput] = useState(qParam)
  const [prevQParam, setPrevQParam] = useState(qParam)
  if (prevQParam !== qParam) {
    setPrevQParam(qParam)
    setSearchInput(qParam)
  }

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

  // 4. Data Fetching
  const { data: run, isLoading: isRunLoading, error: runError } = useRunDetail(selectedRunId || undefined)
  const summary = run?.metrics_json?.summary
  const isRunActive = run?.status === ScanRunStatus.RUNNING || run?.status === ScanRunStatus.PENDING
  const pollInterval = isRunActive ? 3000 : false

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

  const hostsQuery = useRunHosts(activeTab === 'hosts' ? selectedRunId || undefined : undefined, queryParams, { refetchInterval: pollInterval })
  const servicesQuery = useRunServices(activeTab === 'services' ? selectedRunId || undefined : undefined, queryParams, { refetchInterval: pollInterval })
  const checksQuery = useRunChecks(activeTab === 'checks' ? selectedRunId || undefined : undefined, queryParams, { refetchInterval: pollInterval })

  const activeTableQuery = activeTab === 'hosts' ? hostsQuery : activeTab === 'services' ? servicesQuery : checksQuery
  const currentTotal = activeTableQuery.data?.total || 0

  // 5. Saved Views Integration
  const [activeViewId, setActiveViewId] = useState('view-default')

  const { data: fetchedViews } = useQuery<SavedView[]>({
    queryKey: ['views'],
    queryFn: async () => {
      const res = await fetch('/api/views')
      if (!res.ok) throw new Error('Network error')
      return res.json()
    },
  })

  const savedViews = useMemo<SavedView[]>(() => {
    const defaultView: SavedView = {
      id: 'view-default',
      name: 'Default View (All Targets)',
      search: '',
      statuses: ['all'],
      table_sort_by: null,
      table_sort_dir: 'asc',
    }
    return [defaultView, ...(fetchedViews || [])]
  }, [fetchedViews])

  const handleSelectSavedView = useCallback(
    (viewId: string) => {
      setActiveViewId(viewId)
      if (viewId === 'custom-new') return
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

  const handleSaveViewSubmit = useCallback(
    async (name: string) => {
      try {
        const payload = {
          name,
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
          queryClient.invalidateQueries({ queryKey: ['views'] })
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
    },
    [qParam, statusParam, sortByParam, sortDirParam, queryClient, setSearchParams]
  )

  const handleDeleteView = useCallback(async () => {
    if (activeViewId && activeViewId !== 'view-default') {
      try {
        const res = await fetch(`/api/views/${activeViewId}`, { method: 'DELETE' })
        if (res.ok) {
          queryClient.invalidateQueries({ queryKey: ['views'] })
          handleSelectSavedView('view-default')
        }
      } catch (err) {
        console.error('Failed to delete view:', err)
      }
    }
  }, [activeViewId, queryClient, handleSelectSavedView])

  // 6. Table Event Handlers
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

  const handleClearIp = useCallback(() => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.delete('ip')
      next.delete('page')
      return next
    })
  }, [setSearchParams])

  const handlePortChange = useCallback(
    (port?: number) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        if (port !== undefined) next.set('port', String(port))
        else next.delete('port')
        next.delete('page')
        return next
      })
    },
    [setSearchParams]
  )

  const handleFindingChange = useCallback(
    (finding?: string) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        if (finding) next.set('finding', finding)
        else next.delete('finding')
        next.delete('page')
        return next
      })
    },
    [setSearchParams]
  )

  const handleIncludeClosedChange = useCallback(
    (includeClosed: boolean) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        if (includeClosed) next.set('include_closed', 'true')
        else next.delete('include_closed')
        next.delete('page')
        return next
      })
    },
    [setSearchParams]
  )

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

  const handleCloseDrawer = useCallback(() => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.delete('drawer')
      return next
    })
  }, [setSearchParams])

  const handleDrillDown = useCallback(
    (tab: 'services' | 'checks', ip: string) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        next.delete('drawer')
        next.set('tab', tab)
        next.set('ip', ip)
        next.delete('page')
        return next
      })
    },
    [setSearchParams]
  )

  const handleSelectRun = useCallback(
    (id: string | null) => {
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev)
        if (id) next.set('run', id)
        else next.delete('run')
        return next
      })
    },
    [setSearchParams]
  )

  // Fallback 1: Run error (e.g. 404 or missing run)
  if (runError) {
    return (
      <div className="w-full flex-1 flex flex-col bg-background">
        <RunSummaryHeader
          selectedRunId={selectedRunId}
          run={undefined}
          isRunActive={false}
          onSelectRun={handleSelectRun}
        />
        <div className="flex-1 flex flex-col items-center justify-center p-8">
          <div
            data-testid="scan-not-found-fallback"
            className="max-w-lg w-full rounded-xl border-2 border-border bg-card p-8 text-center shadow-lg flex flex-col items-center gap-4"
          >
            <div className="w-12 h-12 rounded-full bg-destructive/10 text-destructive flex items-center justify-center">
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            </div>
            <div>
              <h3 className="text-xl font-bold tracking-tight">Scan Run Not Found</h3>
              <p className="text-sm text-muted-foreground mt-2 leading-relaxed">
                No scan run found with ID <code className="font-mono font-bold text-foreground bg-muted px-1.5 py-0.5 rounded text-xs">{selectedRunId}</code>. It may have been pruned, deleted, or the URL parameter is incorrect.
              </p>
            </div>
            <div className="flex flex-wrap items-center justify-center gap-3 mt-2">
              <Button
                variant="default"
                className="font-bold shadow-sm"
                onClick={() => {
                  setSearchParams((prev) => {
                    const next = new URLSearchParams(prev)
                    next.delete('run')
                    return next
                  })
                }}
              >
                View Latest Scan
              </Button>
              <RunHistorySheet
                selectedRunId={selectedRunId}
                onSelectRun={handleSelectRun}
                triggerLabel="Select from History"
              />
              <Link to="/scan">
                <Button variant="outline" className="border-2 font-bold">
                  ▶ Launch Live Scan
                </Button>
              </Link>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // Fallback 2: No scan runs exist in system or no scan selected
  if (!selectedRunId && !isLatestRunsLoading) {
    return (
      <div className="w-full flex-1 flex flex-col bg-background">
        <RunSummaryHeader
          selectedRunId={null}
          run={undefined}
          isRunActive={false}
          onSelectRun={handleSelectRun}
        />
        <div className="flex-1 flex flex-col items-center justify-center p-8">
          <div
            data-testid="no-scan-selected-fallback"
            className="max-w-md w-full rounded-xl border-2 border-border bg-card p-8 text-center shadow-lg flex flex-col items-center gap-4"
          >
            <div className="w-12 h-12 rounded-full bg-primary/10 text-primary flex items-center justify-center">
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            </div>
            <div>
              <h3 className="text-xl font-bold tracking-tight">No Scan Runs Recorded</h3>
              <p className="text-sm text-muted-foreground mt-2 leading-relaxed">
                There are no recorded scans in the database. Run an ad-hoc live scan or configure automated schedules to begin inspecting your perimeter.
              </p>
            </div>
            <div className="flex flex-wrap items-center justify-center gap-3 mt-2">
              <Link to="/scan">
                <Button size="lg" className="font-bold shadow-sm">
                  ▶ Launch Live Scan
                </Button>
              </Link>
              <Link to="/scheduled-runs">
                <Button size="lg" variant="outline" className="border-2 font-bold">
                  Configure Scheduled Scans
                </Button>
              </Link>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // Loading state
  if (isRunLoading || (!runParam && isLatestRunsLoading)) {
    return (
      <div className="w-full flex-1 flex flex-col bg-background">
        <RunSummaryHeader
          selectedRunId={selectedRunId}
          run={undefined}
          isRunActive={false}
          onSelectRun={handleSelectRun}
        />
        <div className="flex-1 flex flex-col items-center justify-center p-12 text-muted-foreground gap-3">
          <div className="animate-spin rounded-full h-8 w-8 border-2 border-primary border-t-transparent" />
          <p className="text-sm font-medium">Loading scan run...</p>
        </div>
      </div>
    )
  }

  const hostsCount = summary ? summary.active + summary.warning + summary.failed + summary.ghost : 0

  return (
    <div className="w-full flex-1 flex flex-col bg-background">
      {/* 1. Header & Run Summary Strip */}
      <RunSummaryHeader
        selectedRunId={selectedRunId}
        run={run}
        isRunActive={isRunActive}
        onSelectRun={(id) => {
          setSearchParams((prev) => {
            const next = new URLSearchParams(prev)
            if (id) next.set('run', id)
            else next.delete('run')
            return next
          })
        }}
      />

      {/* 2. Filter Toolbar & Saved Views */}
      <ScanFilterToolbar
        activeTab={activeTab}
        savedViews={savedViews}
        activeViewId={activeViewId}
        onSelectView={handleSelectSavedView}
        onSaveView={handleSaveViewSubmit}
        onDeleteView={handleDeleteView}
        searchInput={searchInput}
        onSearchChange={setSearchInput}
        ipParam={ipParam}
        onClearIp={handleClearIp}
        portParam={portParam}
        onPortChange={handlePortChange}
        findingParam={findingParam}
        onFindingChange={handleFindingChange}
        includeClosed={includeClosedParam}
        onIncludeClosedChange={handleIncludeClosedChange}
        statusParam={statusParam}
        onStatusToggle={handleStatusToggle}
      />

      {/* 3. Three Tabs Navigation */}
      <ScanTabsNav
        activeTab={activeTab}
        onTabChange={handleTabChange}
        hostsCount={hostsCount}
        servicesCount={summary?.service_count ?? 0}
        checksCount={summary?.http_check_count ?? 0}
      />

      {/* 4. Table Views */}
      <div className="flex-1 overflow-auto p-6">
        {activeTableQuery.isLoading ? (
          <div className="text-center py-12 text-sm text-muted-foreground">Loading table data...</div>
        ) : activeTableQuery.isError ? (
          <div className="text-center py-12 text-sm text-destructive">Failed to load table items.</div>
        ) : (
          <>
            {activeTab === 'hosts' && (
              <HostsTable
                items={hostsQuery.data?.items}
                sortBy={sortByParam}
                sortDir={sortDirParam}
                onSort={handleSort}
                onSelectIp={handleOpenDrawer}
              />
            )}
            {activeTab === 'services' && (
              <ServicesTable
                items={servicesQuery.data?.items}
                sortBy={sortByParam}
                sortDir={sortDirParam}
                onSort={handleSort}
                onSelectIp={handleOpenDrawer}
              />
            )}
            {activeTab === 'checks' && (
              <ChecksTable
                items={checksQuery.data?.items}
                sortBy={sortByParam}
                sortDir={sortDirParam}
                onSort={handleSort}
                onSelectIp={handleOpenDrawer}
              />
            )}
          </>
        )}
      </div>

      {/* 5. Pagination Footer */}
      <TablePaginationBar
        page={pageParam}
        limit={limitParam}
        total={currentTotal}
        onPageChange={handlePageChange}
        onLimitChange={handleLimitChange}
      />

      {/* On-Demand Slide-Over IP Detail Drawer */}
      <HostDetailDrawer
        runId={selectedRunId}
        ipAddress={drawerParam}
        open={Boolean(drawerParam)}
        onClose={handleCloseDrawer}
        onDrillDown={handleDrillDown}
        refetchInterval={pollInterval}
      />
    </div>
  )
}
