import { useMemo, useState, useCallback, useEffect } from 'react'
import { 
  useScanResults, 
  HierarchicalTable, 
  buildTreeData,
  RenderTreeNode
} from '@/features/scans'
import type { TreeNode } from '@/features/scans/types'

function filterTree(
  nodes: TreeNode[], 
  explicitFilters: Record<string, string[]>, 
  parentFilter: string[] = ['all'],
  globalSearch: string = '',
  parentMatchesSearch: boolean = false,
  parentMatchesStatus: boolean = false
): TreeNode[] {
  return nodes.map(node => {
    // A child doesn't merge with parent. If explicit exists, it overrides completely.
    const filterForChildren = explicitFilters[node.id] || parentFilter
    let matchesStatus = false
    
    if (filterForChildren.includes('all')) {
      matchesStatus = true
    } else {
      if (node.type === 'HTTP' || node.type === 'SAN') {
        matchesStatus = parentMatchesStatus
      } else {
        for (const f of filterForChildren) {
          if (f === 'active' && node.status === 'success') matchesStatus = true
          if (f === 'warning' && node.status === 'warning') matchesStatus = true
          if (f === 'failed' && node.status === 'error') matchesStatus = true
          if (f === 'ghost' && node.status === 'ghost') matchesStatus = true
          if (f === 'void' && node.type === 'Void') matchesStatus = true
          if (matchesStatus) break
        }
      }
    }

    let matchesSearch = parentMatchesSearch
    if (!matchesSearch && globalSearch) {
      const searchLower = globalSearch.toLowerCase()
      const searchStr = `${node.label} ${node.tlsInfo || ''} ${node.rawPayload ? JSON.stringify(node.rawPayload) : ''}`.toLowerCase()
      matchesSearch = searchStr.includes(searchLower)
    } else if (!globalSearch) {
      matchesSearch = true
    }

    const filteredChildren = filterTree(node.children, explicitFilters, filterForChildren, globalSearch, matchesSearch, matchesStatus)
    
    if ((matchesStatus && matchesSearch) || filteredChildren.length > 0) {
      const hasExplicit = explicitFilters[node.id] !== undefined
      // check if redundant by comparing arrays
      const isRedundant = hasExplicit && JSON.stringify(explicitFilters[node.id].sort()) === JSON.stringify(parentFilter.sort())
      return { ...node, children: filteredChildren, appliedFilter: filterForChildren, isExplicitFilter: hasExplicit && !isRedundant } as TreeNode
    }
    return null
  }).filter((n) => n !== null) as TreeNode[]
}

function getSortValue(node: TreeNode, sortBy: string, sortDir: 'asc' | 'desc'): number | null {
  if (sortBy === 'latency') {
    let bestVal: number | null = node.latencyMs !== undefined && node.latencyMs !== null ? node.latencyMs : null
    if (node.children && node.children.length > 0) {
      const vals = node.children.map(c => getSortValue(c, sortBy, sortDir)).filter((v): v is number => v !== null)
      if (vals.length > 0) {
        const childBest = sortDir === 'asc' ? Math.min(...vals) : Math.max(...vals)
        bestVal = bestVal !== null ? (sortDir === 'asc' ? Math.min(bestVal, childBest) : Math.max(bestVal, childBest)) : childBest
      }
    }
    return bestVal
  }
  if (sortBy === 'tls') {
    let bestVal: number | null = node.rawPayload?.tls_certificate?.expires_in_days ?? null
    
    if (node.rawPayload?.tls_certificate && node.rawPayload.tls_certificate.valid === false) {
       bestVal = -1
    }

    if (node.children && node.children.length > 0) {
      const vals = node.children.map(c => getSortValue(c, sortBy, sortDir)).filter((v): v is number => v !== null)
      if (vals.length > 0) {
        const childBest = sortDir === 'asc' ? Math.min(...vals) : Math.max(...vals)
        bestVal = bestVal !== null ? (sortDir === 'asc' ? Math.min(bestVal, childBest) : Math.max(bestVal, childBest)) : childBest
      }
    }
    return bestVal
  }
  return null
}

function sortTree(nodes: TreeNode[], sortBy: string | null, sortDir: 'asc' | 'desc'): TreeNode[] {
  if (!sortBy) return nodes
  
  return [...nodes].sort((a, b) => {
    const valA = getSortValue(a, sortBy, sortDir)
    const valB = getSortValue(b, sortBy, sortDir)

    if (valA === null && valB !== null) return 1
    if (valA !== null && valB === null) return -1
    if (valA === null && valB === null) return 0

    if (valA! < valB!) return sortDir === 'asc' ? -1 : 1
    if (valA! > valB!) return sortDir === 'asc' ? 1 : -1
    return 0
  }).map(node => ({
    ...node,
    children: sortTree(node.children, sortBy, sortDir)
  }))
}

export function HostTablePage() {
  const { data, isLoading, error } = useScanResults()
  const [explicitFilters, setExplicitFilters] = useState<Record<string, string[]>>({
    'global-root-id': ['all']
  })
  const [expandedRowIds, setExpandedRowIds] = useState<Set<string>>(new Set())
  const [globalSearch, setGlobalSearch] = useState<string>('')
  const [sortBy, setSortBy] = useState<'latency' | 'tls' | null>(null)
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')

  const [savedViews, setSavedViews] = useState([
    { id: 'view-default', name: 'Default View (All Targets)', search: '', statuses: ['all'], tableSortBy: null, tableSortDir: 'asc' },
    { id: 'view-ghosts', name: 'Critical Outages & Ghosts', search: '', statuses: ['ghost', 'failed'], tableSortBy: 'status', tableSortDir: 'desc' },
    { id: 'view-active-ghost', name: 'Active & Ghost Outages', search: '', statuses: ['active', 'ghost'], tableSortBy: null, tableSortDir: 'asc' },
    { id: 'view-datacenter', name: 'Datacenter Core Infrastructure', search: 'datacenter_core', statuses: ['all'], tableSortBy: null, tableSortDir: 'asc' }
  ])
  const [activeViewId, setActiveViewId] = useState('view-default')
  const [isSavingView, setIsSavingView] = useState(false)
  const [newViewName, setNewViewName] = useState('')

  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search)
    const viewId = urlParams.get('view')
    if (viewId) {
      fetch(`/api/views/${viewId}`)
        .then(res => {
          if (res.ok) return res.json()
          throw new Error('View not found')
        })
        .then(data => {
          const id = data.id
          setSavedViews(prev => {
            if (!prev.find(v => v.id === id)) {
               return [...prev, { id, name: `🔗 ${data.name}`, search: data.search || '', statuses: data.statuses || ['all'], tableSortBy: data.table_sort_by || null, tableSortDir: data.table_sort_dir || 'asc' }]
            }
            return prev
          })
          setActiveViewId(id)
          setGlobalSearch(data.search || '')
          setExplicitFilters({ 'global-root-id': data.statuses || ['all'] })
          setSortBy((data.table_sort_by as any) || null)
          setSortDir((data.table_sort_dir as any) || 'asc')
        })
        .catch(err => {
          console.error("Failed to load view from URL:", err)
        })
    }
  }, [])

  const handleSelectSavedView = useCallback((viewId: string) => {
    setActiveViewId(viewId)
    if (viewId === 'custom-new') {
      setIsSavingView(true)
      return
    }
    const view = savedViews.find((v) => v.id === viewId)
    if (view) {
      setGlobalSearch(view.search)
      setExplicitFilters({ 'global-root-id': view.statuses || ['all'] })
      setSortBy((view.tableSortBy as any) || null)
      setSortDir((view.tableSortDir as any) || 'asc')

      const newUrl = new URL(window.location.href)
      if (!viewId.startsWith('view-') && viewId !== 'custom' && viewId !== 'custom-new') {
         newUrl.searchParams.set('view', viewId)
      } else {
         newUrl.searchParams.delete('view')
      }
      window.history.pushState({}, '', newUrl)
    }
  }, [savedViews])

  const handleDeleteView = useCallback(() => {
     if (activeViewId && activeViewId !== 'view-default' && activeViewId !== 'custom' && activeViewId !== 'custom-new') {
        setSavedViews(prev => prev.filter(v => v.id !== activeViewId))
        handleSelectSavedView('view-default')
     }
  }, [activeViewId, handleSelectSavedView])

  const handleSaveViewSubmit = useCallback(async () => {
    if (newViewName.trim()) {
      try {
        const payload = {
          name: newViewName.trim(),
          search: globalSearch,
          statuses: explicitFilters['global-root-id'] || ['all'],
          table_sort_by: sortBy,
          table_sort_dir: sortDir
        }
        const response = await fetch('/api/views', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        })
        
        if (response.ok) {
          const data = await response.json()
          const id = data.id
          setSavedViews((prev) => [...prev, { id, name: data.name, search: data.search, statuses: data.statuses, tableSortBy: data.table_sort_by, tableSortDir: data.table_sort_dir }])
          setActiveViewId(id)
          
          const newUrl = new URL(window.location.href)
          newUrl.searchParams.set('view', id)
          window.history.pushState({}, '', newUrl)
        } else {
          console.error("Failed to save view via API, falling back to local storage")
          const id = `view-${Date.now()}`
          setSavedViews((prev) => [...prev, { id, name: newViewName.trim(), search: globalSearch, statuses: explicitFilters['global-root-id'] || ['all'], tableSortBy: sortBy, tableSortDir: sortDir }])
          setActiveViewId(id)
        }
      } catch (err) {
        console.error(err)
        const id = `view-${Date.now()}`
        setSavedViews((prev) => [...prev, { id, name: newViewName.trim(), search: globalSearch, statuses: explicitFilters['global-root-id'] || ['all'], tableSortBy: sortBy, tableSortDir: sortDir }])
        setActiveViewId(id)
      }
    }
    setIsSavingView(false)
    setNewViewName('')
  }, [newViewName, globalSearch, explicitFilters, sortBy, sortDir])

  // Build tree
  const rawTree = useMemo(() => {
    if (!data?.hosts) return []
    return buildTreeData(data.hosts)
  }, [data])

  const filteredTreeData = useMemo(() => {
    const filtered = filterTree(rawTree, explicitFilters, ['all'], globalSearch)
    let visibleNodes = filtered[0]?.children || []
    if (sortBy) {
      visibleNodes = sortTree(visibleNodes, sortBy, sortDir)
    }
    return visibleNodes
  }, [rawTree, explicitFilters, globalSearch, sortBy, sortDir])

  const handleToggleRow = useCallback((id: string) => {
    const isCollapsing = expandedRowIds.has(id)
    
    let descendantsToClear: string[] = []
    const findDescendants = (nodes: TreeNode[], isUnder: boolean) => {
      for (const node of nodes) {
        const under = isUnder || node.id === id
        if (under && node.id !== id) {
          descendantsToClear.push(node.id)
        }
        if (node.children.length > 0) {
          findDescendants(node.children, under)
        }
      }
    }
    findDescendants(rawTree, false)

    setExpandedRowIds(prev => {
      const next = new Set(prev)
      
      if (isCollapsing) {
        next.delete(id)
        descendantsToClear.forEach(dId => next.delete(dId))
      } else {
        next.add(id)
      }
      return next
    })

    if (isCollapsing && descendantsToClear.length > 0) {
      setExplicitFilters(filtersPrev => {
        let changed = false
        const nextFilters = { ...filtersPrev }
        descendantsToClear.forEach(dId => {
          if (nextFilters[dId]) {
            delete nextFilters[dId]
            changed = true
          }
        })
        return changed ? nextFilters : filtersPrev
      })
    }
  }, [rawTree, expandedRowIds])

  const handleGlobalFilterClick = useCallback((f: string) => {
    setExplicitFilters(prev => {
      const currentGlobal = prev['global-root-id'] || ['all']
      let newGlobal = [...currentGlobal]

      if (f === 'all') {
        newGlobal = ['all']
      } else {
        if (newGlobal.includes('all')) {
          newGlobal = [f]
        } else {
          if (newGlobal.includes(f)) {
            newGlobal = newGlobal.filter(item => item !== f)
            if (newGlobal.length === 0) newGlobal = ['all']
          } else {
            newGlobal.push(f)
            const allPossible = ['active', 'warning', 'failed', 'ghost', 'void']
            if (allPossible.every(p => newGlobal.includes(p))) {
              newGlobal = ['all']
            }
          }
        }
      }

      const newFilters = { 'global-root-id': newGlobal }
      
      if (!newGlobal.includes('all')) {
        setTimeout(() => {
          setExpandedRowIds(prevIds => {
            const tempFiltered = filterTree(rawTree, newFilters, ['all'], globalSearch)
            const visibleNodes = tempFiltered[0]?.children || []
            const next = new Set<string>(prevIds)
            const collectIds = (nodes: TreeNode[]) => {
              for (const n of nodes) {
                next.add(n.id)
                collectIds(n.children)
              }
            }
            collectIds(visibleNodes)
            return next
          })
        }, 0)
      } else {
        setTimeout(() => setExpandedRowIds(new Set()), 0)
      }
      return newFilters
    })
  }, [rawTree])

  const handleStatusClick = useCallback((nodeId: string, st: string) => {
    let descendantsToClear: string[] = []
    const findDescendants = (nodes: TreeNode[], isUnder: boolean) => {
      for (const node of nodes) {
        const under = isUnder || node.id === nodeId
        if (under && node.id !== nodeId) {
          descendantsToClear.push(node.id)
        }
        if (node.children.length > 0) {
          findDescendants(node.children, under)
        }
      }
    }
    findDescendants(rawTree, false)

    setExplicitFilters(prev => {
      const next = { ...prev }
      const current = next[nodeId] || []
      let updated = [...current]

      if (updated.includes(st)) {
        updated = updated.filter(i => i !== st)
      } else {
        if (updated.includes('all')) {
          updated = [st]
        } else {
          updated.push(st)
        }
      }

      if (updated.length === 0) {
        delete next[nodeId]
      } else {
        next[nodeId] = updated
      }

      descendantsToClear.forEach(dId => delete next[dId])
      return next
    })

    setExpandedRowIds(prev => {
      const next = new Set(prev)
      descendantsToClear.forEach(dId => next.delete(dId))
      next.add(nodeId)
      
      const traverseAndCollect = (nodes: TreeNode[], parentMatches: boolean) => {
        let anyMatch = false
        for (const node of nodes) {
          const isTargetNode = node.id === nodeId
          const isUnderTarget = parentMatches || isTargetNode
          
          let childMatched = false
          if (node.children && node.children.length > 0) {
            childMatched = traverseAndCollect(node.children, isUnderTarget)
          }

          if (isUnderTarget) {
            let matchesStatus = false
            if (st === 'active' && (node.status === 'success' || (node.type === 'HTTP' && node.status === 'neutral'))) matchesStatus = true
            if (st === 'warning' && node.status === 'warning') matchesStatus = true
            if (st === 'failed' && node.status === 'error') matchesStatus = true
            if (st === 'ghost' && (node.nodeStats?.ghost || 0) > 0) matchesStatus = true
            if (st === 'void' && node.type === 'Void') matchesStatus = true

            if (matchesStatus || childMatched) {
              if (node.children && node.children.length > 0) {
                next.add(node.id)
              }
              anyMatch = true
            }
          }
        }
        return anyMatch
      }
      
      traverseAndCollect(rawTree, false)
      return next
    })
  }, [rawTree])

  const handleExpandAll = useCallback(() => {
    const allIds = new Set<string>()
    const traverse = (nodes: TreeNode[]) => {
      for (const node of nodes) {
        if (node.children && node.children.length > 0) {
          allIds.add(node.id)
          traverse(node.children)
        }
      }
    }
    traverse(filteredTreeData)
    setExpandedRowIds(allIds)
  }, [filteredTreeData])

  const handleCollapseAll = useCallback(() => {
    setExpandedRowIds(new Set())
  }, [])

  const handleClearFilter = useCallback((nodeId: string) => {
    setExplicitFilters(prev => {
      const next = { ...prev }
      if (next[nodeId] !== undefined) {
        delete next[nodeId]
      }
      return next
    })
  }, [])



  if (isLoading) return <div className="p-8 text-muted-foreground">Loading scans...</div>
  if (error) return <div className="p-8 text-destructive">Error loading scans.</div>

  const isAnyFilterActive = Object.keys(explicitFilters).some(key => key !== 'global-root-id' && !explicitFilters[key].includes('all')) || !explicitFilters['global-root-id']?.includes('all')

  return (
    <div className="fixed inset-0 w-full flex flex-col bg-background">
      <div className="px-6 py-4 shrink-0 border-b border-border bg-muted/30 flex justify-between items-center">
        <div>
          <h1 className="text-xl font-bold tracking-tight">Topology Scan Results</h1>
          <p className="text-muted-foreground text-xs font-mono">
            {/* @ts-ignore */}
            {data?.metadata?.total_targets_scanned || 0} IPs scanned • {data?.metadata?.scan_duration_seconds || 0}s duration
          </p>
        </div>
      </div>
      
      <div className="px-6 py-2 shrink-0 bg-muted/10 flex items-center gap-3 flex-wrap border-b border-border shadow-sm">
        <div className="flex items-center gap-4 shrink-0">
          {isSavingView ? (
            <div className="flex items-center gap-2">
              <span className="text-muted-foreground text-sm font-semibold">Save View:</span>
              <input
                type="text"
                placeholder="View name..."
                autoFocus
                value={newViewName}
                onChange={(e) => setNewViewName(e.target.value)}
                className="bg-background text-foreground border border-border rounded px-3 py-1 text-xs font-mono font-semibold focus:outline-none focus:ring-1 focus:ring-ring w-48"
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleSaveViewSubmit()
                  if (e.key === 'Escape') setIsSavingView(false)
                }}
              />
              <button onClick={handleSaveViewSubmit} className="bg-primary text-primary-foreground px-2 py-1 rounded text-xs hover:bg-primary/90 font-semibold">✓ Save</button>
              <button onClick={() => {setIsSavingView(false); setActiveViewId('view-default');}} className="bg-background text-foreground px-2 py-1 rounded text-xs border border-border hover:bg-muted font-semibold">✕ Cancel</button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <span className="text-muted-foreground text-sm font-semibold">Global View:</span>
              <select
                value={activeViewId}
                onChange={(e) => handleSelectSavedView(e.target.value)}
                className="bg-background text-foreground border border-border rounded px-3 py-1 text-xs font-mono font-semibold focus:outline-none focus:ring-1 focus:ring-ring cursor-pointer max-w-[220px]"
              >
                {savedViews.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.name}
                  </option>
                ))}
              </select>
              <button
                onClick={() => setIsSavingView(true)}
                className="bg-background text-foreground px-2 py-1 rounded text-xs border border-border hover:bg-muted font-semibold"
                title="Save Current View"
              >
                + Create
              </button>
              <button
                onClick={handleDeleteView}
                disabled={!activeViewId || activeViewId === 'view-default' || activeViewId === 'custom' || activeViewId === 'custom-new'}
                className="bg-background text-destructive px-2 py-1 rounded text-xs border border-border hover:bg-muted font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
                title="Delete this view locally"
              >
                ✕ Delete
              </button>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2 min-w-[200px] max-w-sm ml-auto">
          <input 
            type="text"
            placeholder="Search IP, Domain, Headers..."
            value={globalSearch}
            onChange={(e) => setGlobalSearch(e.target.value)}
            className="w-full bg-background border border-border px-3 py-1.5 rounded-md text-sm shadow-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>

        <div className="flex items-center gap-2 mr-2">
          <button 
            onClick={handleExpandAll}
            className="text-xs font-semibold px-2 py-1.5 rounded-md bg-background border border-border hover:bg-muted text-muted-foreground transition-colors shadow-sm"
          >
            Expand All
          </button>
          <button 
            onClick={handleCollapseAll}
            className="text-xs font-semibold px-2 py-1.5 rounded-md bg-background border border-border hover:bg-muted text-muted-foreground transition-colors shadow-sm"
          >
            Collapse All
          </button>
        </div>

        <button 
          title="Clear All Filters"
          disabled={!isAnyFilterActive}
          onClick={() => {
            setExplicitFilters({ 'global-root-id': ['all'] })
          }}
          className={`flex items-center justify-center w-8 h-8 rounded-md transition-all ${
            isAnyFilterActive
              ? 'bg-muted border border-border text-foreground hover:bg-background shadow-sm cursor-pointer'
              : 'bg-transparent border border-transparent text-muted-foreground/40 cursor-not-allowed'
          }`}
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
        </button>

        <span className="text-sm font-semibold text-muted-foreground pl-1">Filters:</span>
        <div className="flex bg-muted/30 border border-border p-1 rounded-lg shadow-sm font-mono text-sm">
          {(['all', 'active', 'warning', 'failed', 'ghost', 'void']).map((f) => (
            <button
              key={f}
              onClick={() => handleGlobalFilterClick(f)}
              className={`px-4 py-1.5 rounded-md capitalize transition-all ${
                (explicitFilters['global-root-id'] || ['all']).includes(f)
                  ? 'bg-background shadow-sm font-bold text-foreground'
                  : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>
      
      <div className="flex-1 overflow-hidden">
        <HierarchicalTable 
          expandedRowIds={expandedRowIds} 
          onToggleRow={handleToggleRow}
          sortBy={sortBy}
          sortDir={sortDir}
          onSortChange={(by, dir) => {
            setSortBy(by)
            setSortDir(dir)
          }}
        >
          {filteredTreeData.map(node => (
            <RenderTreeNode 
              key={node.id} 
              node={node} 
              onStatusClick={handleStatusClick}
              onClearFilter={handleClearFilter}
            />
          ))}
        </HierarchicalTable>
      </div>
    </div>
  )
}
