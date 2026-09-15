import type { TreeNode } from '../types'

/**
 * Recursively compresses single-child chains (e.g. Host -> Port -> HTTP) into a single row.
 * Preserves structural root nodes like CIDR / Target strings naturally because they 
 * have multiple children (Active + Void).
 */
export function compressTreeNodes(node: TreeNode): TreeNode {
  // Recursively compress children first
  const compressedChildren = node.children.map(compressTreeNodes)

  // Enforce ADR 0007 Rule 3: Root structural groupings are strictly prohibited from path compression
  const isProtectedStructure = ['CIDR', 'Pool', 'Classification', 'GlobalRoot'].includes(node.type)

  // If exactly 1 child and neither has an explicit filter, merge this node with its child
  if (!isProtectedStructure && compressedChildren.length === 1 && !node.isExplicitFilter && !compressedChildren[0].isExplicitFilter) {
    const singleChild = compressedChildren[0]
    
    // If we are merging a Port with an HTTP/TLS leaf, the leaf label is usually 
    // a redundant IP address. In this case, we just keep the parent's label (e.g. "80/tcp")
    // For other merges (like Target ➔ Host), we concatenate them.
    const newLabel = `${node.label} ➔ ${singleChild.label}`
    
    return {
      id: `${node.id}->${singleChild.id}`,
      originalNodeId: node.originalNodeId || node.id,
      label: newLabel,
      type: `${node.type} / ${singleChild.type}`,
      status: node.status,
      latencyMs: singleChild.latencyMs || node.latencyMs,
      tlsInfo: singleChild.tlsInfo || node.tlsInfo,
      children: singleChild.children,
      rawPayload: singleChild.rawPayload || node.rawPayload,
      nodeStats: singleChild.nodeStats || node.nodeStats,
      appliedFilter: singleChild.appliedFilter || node.appliedFilter,
      isExplicitFilter: singleChild.isExplicitFilter || node.isExplicitFilter
    }
  }

  return { ...node, children: compressedChildren }
}
