import { HierarchicalTable } from './index'
import { useTableContext } from './TableContext'
import type { TreeNode, TreeNodeStatus } from '../../types'

function getStatusBadgeClasses(status: TreeNodeStatus) {
  switch (status) {
    case 'success': return 'bg-green-500/15 text-green-500 border border-green-500/40'
    case 'error': return 'bg-red-500/15 text-red-500 border border-red-500/40'
    case 'warning': return 'bg-yellow-500/15 text-yellow-600 border border-yellow-500/40'
    case 'neutral': return 'bg-slate-500/15 text-slate-500 border border-slate-500/40'
    case 'ghost': return 'bg-red-500/15 text-red-500 border border-red-500/40'
    case 'empty':
    default:
      return 'bg-muted text-muted-foreground'
  }
}

import React from 'react'

const RenderTreeNodeInner = ({ 
  node, 
  depth = 0,
  onStatusClick,
  onClearFilter
}: { 
  node: TreeNode, 
  depth?: number
  onStatusClick?: (nodeId: string, status: string) => void
  onClearFilter?: (nodeId: string) => void
}) => {
  const { toggleDetail } = useTableContext()
  // Reactive Visual Compression logic
  let displayLabel = node.label
  let displayType = node.type
  let displayLatency = node.latencyMs
  let displayTls = node.tlsInfo
  let displayPayload = node.rawPayload ? { ...node.rawPayload } : undefined
  let curr = node
  let isCompressed = false
  
  while (curr.children?.length === 1 && !curr.children[0].isExplicitFilter && curr.type !== 'GlobalRoot') {
    const child = curr.children[0]
    
    // Deduplicate exact matches or prefixed matches
    if (displayLabel !== child.label && !child.label.startsWith(`${displayLabel} ➔`) && !child.label.startsWith(`${displayLabel} `)) {
      displayLabel = `${displayLabel} ➔ ${child.label}`
    } else {
      displayLabel = child.label // if it matches or prefixes, we just adopt the child's label
    }
    
    displayType = `${displayType} / ${child.type}`
    displayLatency = child.latencyMs !== undefined ? child.latencyMs : displayLatency
    displayTls = child.tlsInfo || displayTls
    
    if (child.rawPayload) {
      displayPayload = displayPayload || {}
      displayPayload[`${child.type.toLowerCase()}_details`] = child.rawPayload
    }
    
    curr = child
    isCompressed = true
  }

  const isLeaf = !curr.children || curr.children.length === 0

  return (
    <HierarchicalTable.Row 
      id={node.id} 
      depth={depth} 
      isLeaf={isLeaf} 
      rawPayload={displayPayload}
      subRows={
        !isLeaf ? curr.children.map(child => (
          <RenderTreeNode 
            key={child.id} 
            node={child} 
            depth={depth + 1} 
            onStatusClick={onStatusClick} 
            onClearFilter={onClearFilter}
          />
        )) : null
      }
    >
      <HierarchicalTable.Cell width="w-[35%]">
        <div className="flex flex-col overflow-hidden">
          <span className="truncate" title={displayLabel}>{displayLabel}</span>
          {node.appliedFilter && node.appliedFilter !== 'all' && (node.isExplicitFilter || curr.children.length > 0 || isCompressed) && (
            <div className="flex items-center gap-2 mt-1">
              <span className="text-[9px] font-mono text-blue-500 uppercase font-bold">
                ↳ Filter: {node.appliedFilter}
              </span>
              <button
                onClick={(e) => { e.stopPropagation(); onClearFilter?.(node.id); }}
                className="text-[9px] font-mono text-muted-foreground hover:text-foreground underline decoration-muted-foreground/30 hover:decoration-foreground/50 transition-colors"
              >
                Clear
              </button>
            </div>
          )}
        </div>
      </HierarchicalTable.Cell>
      <HierarchicalTable.Cell width="w-[15%]">
        <span className="bg-muted px-2 py-1 rounded text-[10px] uppercase font-bold text-muted-foreground">{displayType}</span>
      </HierarchicalTable.Cell>
      <HierarchicalTable.Cell width="w-[15%]">{displayTls || '-'}</HierarchicalTable.Cell>
      <HierarchicalTable.Cell width="w-[15%]">{displayLatency ? `${displayLatency}ms` : '-'}</HierarchicalTable.Cell>
      <HierarchicalTable.Cell width="w-[20%]">
        <div className="flex flex-wrap gap-1.5 items-center">
          {node.status && node.status !== 'empty' && node.status !== 'neutral' && !node.nodeStats && (
            <span className={`px-2 py-1 rounded text-[9px] font-bold uppercase ${getStatusBadgeClasses(node.status)}`}>
              {node.status === 'error' ? 'failed' : node.status}
            </span>
          )}
          {node.nodeStats && (
            <>
              {(node.nodeStats.active || 0) > 0 && (
                <button 
                  onClick={(e) => { e.stopPropagation(); onStatusClick?.(node.id, 'active'); }}
                  className="bg-green-500/15 text-green-500 border border-green-500/40 px-1.5 py-0.5 rounded text-[9px] font-bold uppercase hover:border-green-500 transition-colors flex items-center gap-1.5 shrink-0"
                >
                  <span className="w-1.5 h-1.5 rounded-sm bg-green-500" /> {node.nodeStats.active} Active
                </button>
              )}
              {(node.nodeStats.failed || 0) > 0 && (
                <button 
                  onClick={(e) => { e.stopPropagation(); onStatusClick?.(node.id, 'failed'); }}
                  className="bg-red-500/15 text-red-500 border border-red-500/40 px-1.5 py-0.5 rounded text-[9px] font-bold uppercase hover:border-red-500 transition-colors flex items-center gap-1.5 shrink-0"
                >
                  <span className="w-1.5 h-1.5 rounded-sm bg-red-500" /> {node.nodeStats.failed} Failed
                </button>
              )}
              {(node.nodeStats.ghost || 0) > 0 && (
                <button 
                  onClick={(e) => { e.stopPropagation(); onStatusClick?.(node.id, 'ghost'); }}
                  className="bg-red-500/15 text-red-500 border border-red-500/40 px-1.5 py-0.5 rounded text-[9px] font-bold uppercase hover:border-red-500 transition-colors flex items-center gap-1.5 shrink-0"
                >
                  <span className="w-1.5 h-1.5 rounded-sm bg-red-500" /> {node.nodeStats.ghost} Ghost
                </button>
              )}
            </>
          )}
          
          <button
            onClick={(e) => { e.stopPropagation(); toggleDetail(node.id); }}
            className="ml-auto p-1 text-muted-foreground hover:text-foreground hover:bg-muted rounded transition-colors"
            title="View Raw JSON Details"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
            </svg>
          </button>
        </div>
      </HierarchicalTable.Cell>
    </HierarchicalTable.Row>
  )
}

export const RenderTreeNode = React.memo(RenderTreeNodeInner)
