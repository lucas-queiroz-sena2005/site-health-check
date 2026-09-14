import { HierarchicalTable } from './index'
import type { TreeNode, TreeNodeStatus } from '../../types'

function getStatusBadgeClasses(status: TreeNodeStatus) {
  switch (status) {
    case 'success': return 'bg-green-500/15 text-green-500 border border-green-500/40'
    case 'error': return 'bg-red-500/15 text-red-500 border border-red-500/40'
    case 'warning': return 'bg-yellow-500/15 text-yellow-600 border border-yellow-500/40'
    case 'neutral': return 'bg-slate-500/15 text-slate-500 border border-slate-500/40'
    case 'empty':
    default:
      return 'bg-muted text-muted-foreground'
  }
}

export function RenderTreeNode({ 
  node, 
  depth = 0,
  onStatusClick,
  onClearFilter
}: { 
  node: TreeNode, 
  depth?: number,
  onStatusClick?: (nodeId: string, status: string) => void,
  onClearFilter?: (nodeId: string) => void
}) {
  const isLeaf = node.children.length === 0

  return (
    <HierarchicalTable.Row 
      id={node.id} 
      depth={depth} 
      isLeaf={isLeaf} 
      rawPayload={node.rawPayload}
      subRows={
        !isLeaf ? node.children.map(child => (
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
        <div className="flex flex-col">
          <span>{node.label}</span>
          {node.appliedFilter && node.appliedFilter !== 'all' && (
            <div className="flex items-center gap-2 mt-1">
              <span className="text-[9px] font-mono text-blue-500 uppercase font-bold">
                ↳ Filter: {node.appliedFilter}
              </span>
              <button
                onClick={(e) => { e.stopPropagation(); onClearFilter?.(node.id); }}
                className="text-[9px] font-bold text-muted-foreground hover:text-destructive uppercase border border-border rounded px-1 bg-muted/30"
              >
                Clear
              </button>
            </div>
          )}
        </div>
      </HierarchicalTable.Cell>
      <HierarchicalTable.Cell width="w-[15%]">
        <span className="bg-muted px-2 py-1 rounded text-[10px] uppercase font-bold text-muted-foreground">{node.type}</span>
      </HierarchicalTable.Cell>
      <HierarchicalTable.Cell width="w-[15%]">{node.tlsInfo || '-'}</HierarchicalTable.Cell>
      <HierarchicalTable.Cell width="w-[15%]">{node.latencyMs ? `${node.latencyMs}ms` : '-'}</HierarchicalTable.Cell>
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
        </div>
      </HierarchicalTable.Cell>
    </HierarchicalTable.Row>
  )
}
