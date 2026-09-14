import { useMemo, useState } from 'react'
import { 
  useScanResults, 
  HierarchicalTable, 
  compressTreeNodes,
  buildTreeData,
  RenderTreeNode
} from '@/features/scans'
import type { TreeNode } from '@/features/scans/types'

function filterTree(nodes: TreeNode[], explicitFilters: Record<string, string>, parentFilter: string = 'all'): TreeNode[] {
  return nodes.map(node => {
    const filterForChildren = explicitFilters[node.id] || parentFilter
    let matchesStatus = false
    
    if (filterForChildren === 'all') {
      matchesStatus = true
    } else {
      if (node.nodeStats) {
        if (filterForChildren === 'active' && (node.nodeStats.active || 0) > 0) matchesStatus = true
        if (filterForChildren === 'failed' && (node.nodeStats.failed || 0) > 0) matchesStatus = true
        if (filterForChildren === 'ghost' && (node.nodeStats.ghost || 0) > 0) matchesStatus = true
      } else {
        if (filterForChildren === 'active' && node.status === 'success') matchesStatus = true
        if (filterForChildren === 'failed' && node.status === 'error') matchesStatus = true
      }
    }

    const filteredChildren = filterTree(node.children, explicitFilters, filterForChildren)
    
    if (matchesStatus || filteredChildren.length > 0) {
      return { ...node, children: filteredChildren, appliedFilter: filterForChildren } as TreeNode
    }
    return null
  }).filter((n) => n !== null) as TreeNode[]
}

export function HostTablePage() {
  const { data, isLoading, error } = useScanResults()
  const [explicitFilters, setExplicitFilters] = useState<Record<string, string>>({})
  const [expandedRowIds, setExpandedRowIds] = useState<Set<string>>(new Set())

  const handleToggleRow = (id: string) => {
    setExpandedRowIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
        for (const openId of next) {
          if (openId.startsWith(`${id}-`)) {
            next.delete(openId)
          }
        }
      } else {
        next.add(id)
      }
      return next
    })
  }

  const handleStatusClick = (nodeId: string, st: string) => {
    setExplicitFilters(prev => ({
      ...prev,
      [nodeId]: st
    }))
  }

  const handleClearFilter = (nodeId: string) => {
    setExplicitFilters(prev => {
      const next = { ...prev }
      delete next[nodeId]
      return next
    })
  }

  // Build and compress tree
  const treeData = useMemo(() => {
    if (!data?.hosts) return []
    const rawTree = buildTreeData(data.hosts)
    return rawTree.map(compressTreeNodes)
  }, [data])

  const filteredTreeData = useMemo(() => {
    return filterTree(treeData, explicitFilters)
  }, [treeData, explicitFilters])

  // React to filter changes by auto-expanding matched rows (parents only!)
  useMemo(() => {
    if (Object.keys(explicitFilters).length === 0) {
      setExpandedRowIds(new Set())
    } else {
      const newExpanded = new Set<string>()
      const traverse = (nodes: TreeNode[]) => {
        for (const node of nodes) {
          if (node.children.length > 0) {
            newExpanded.add(node.id) // Only expand nodes that have children, so DetailsPanel won't open!
            traverse(node.children)
          }
        }
      }
      traverse(filteredTreeData)
      setExpandedRowIds(newExpanded)
    }
  }, [explicitFilters, filteredTreeData])

  if (isLoading) return <div className="p-8 text-muted-foreground">Loading scans...</div>
  if (error) return <div className="p-8 text-destructive">Error loading scans.</div>

  const isAnyFilterActive = Object.keys(explicitFilters).length > 0

  return (
    <div className="w-full flex-1 flex flex-col h-[calc(100vh-theme(spacing.14))] overflow-hidden bg-background">
      <div className="px-6 py-4 shrink-0 border-b border-border bg-muted/30 flex justify-between items-center">
        <h1 className="text-xl font-bold tracking-tight">Active Scans</h1>
        {isAnyFilterActive && (
          <button 
            onClick={() => setExplicitFilters({})}
            className="text-xs bg-muted border border-border px-3 py-1 rounded font-mono font-bold hover:bg-background transition-colors"
          >
            ✕ Clear All Filters
          </button>
        )}
      </div>
      
      <div className="flex-1 overflow-auto">
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
