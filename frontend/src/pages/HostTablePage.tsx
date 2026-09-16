import { useMemo, useState, useCallback } from 'react'
import { 
  useScanResults, 
  HierarchicalTable, 
  buildTreeData,
  RenderTreeNode
} from '@/features/scans'
import type { TreeNode } from '@/features/scans/types'

function filterTree(nodes: TreeNode[], explicitFilters: Record<string, string[]>, parentFilter: string[] = ['all']): TreeNode[] {
  return nodes.map(node => {
    // A child doesn't merge with parent. If explicit exists, it overrides completely.
    const filterForChildren = explicitFilters[node.id] || parentFilter
    let matchesStatus = false
    
    if (filterForChildren.includes('all')) {
      matchesStatus = true
    } else {
      for (const f of filterForChildren) {
        if (f === 'active' && (node.status === 'success' || (node.type === 'HTTP' && node.status === 'neutral'))) matchesStatus = true
        if (f === 'warning' && node.status === 'warning') matchesStatus = true
        if (f === 'failed' && (node.status === 'error')) matchesStatus = true
        if (f === 'ghost' && node.status === 'ghost') matchesStatus = true
        if (f === 'void' && node.type === 'Void') matchesStatus = true
        if (matchesStatus) break
      }
    }

    const filteredChildren = filterTree(node.children, explicitFilters, filterForChildren)
    
    if (matchesStatus || filteredChildren.length > 0) {
      const hasExplicit = explicitFilters[node.id] !== undefined
      // check if redundant by comparing arrays
      const isRedundant = hasExplicit && JSON.stringify(explicitFilters[node.id].sort()) === JSON.stringify(parentFilter.sort())
      return { ...node, children: filteredChildren, appliedFilter: filterForChildren, isExplicitFilter: hasExplicit && !isRedundant } as TreeNode
    }
    return null
  }).filter((n) => n !== null) as TreeNode[]
}

export function HostTablePage() {
  const { data, isLoading, error } = useScanResults()
  const [explicitFilters, setExplicitFilters] = useState<Record<string, string[]>>({
    'global-root-id': ['all']
  })
  const [expandedRowIds, setExpandedRowIds] = useState<Set<string>>(new Set())

  // Build tree
  const rawTree = useMemo(() => {
    if (!data?.hosts) return []
    return buildTreeData(data.hosts)
  }, [data])

  const filteredTreeData = useMemo(() => {
    // The rawTree is an array containing [globalRootNode]
    const filtered = filterTree(rawTree, explicitFilters)
    // We only want to render the children of the global root
    return filtered[0]?.children || []
  }, [rawTree, explicitFilters])

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
            const tempFiltered = filterTree(rawTree, newFilters)
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
      
      <div className="px-6 py-2 shrink-0 bg-muted/10 flex items-center justify-end gap-3">
        <button 
          title="Clear All Filters"
          disabled={!isAnyFilterActive}
          onClick={() => {
            setExplicitFilters({ 'global-root-id': ['all'] })
            setExpandedRowIds(new Set())
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
        <HierarchicalTable expandedRowIds={expandedRowIds} onToggleRow={handleToggleRow}>
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
