import type { TreeNode } from '../types'

/**
 * Recursively compresses single-child chains (e.g. Host -> Port -> HTTP) into a single row.
 * Preserves structural root nodes like CIDR / Target strings naturally because they 
 * have multiple children (Active + Void).
 */
export function compressTreeNodes(node: TreeNode): TreeNode {
  // Recursively compress children first
  const compressedChildren = node.children.map(compressTreeNodes)

  // If exactly 1 child, merge this node with its child
  if (compressedChildren.length === 1) {
    const singleChild = compressedChildren[0]
    
    // If we are merging a Port with an HTTP/TLS leaf, the leaf label is usually 
    // a redundant IP address. In this case, we just keep the parent's label (e.g. "80/tcp")
    // For other merges (like Target ➔ Host), we concatenate them.
    const isLeafMerge = singleChild.type === 'HTTP' || singleChild.type === 'TLS'
    const newLabel = isLeafMerge ? node.label : `${node.label} ➔ ${singleChild.label}`
    
    return {
      id: `${node.id}->${singleChild.id}`,
      label: newLabel,
      type: isLeafMerge ? singleChild.type : `${node.type} / ${singleChild.type}`,
      status: singleChild.status,
      latencyMs: singleChild.latencyMs || node.latencyMs,
      tlsInfo: singleChild.tlsInfo || node.tlsInfo,
      children: singleChild.children,
      rawPayload: singleChild.rawPayload || node.rawPayload,
      nodeStats: singleChild.nodeStats || node.nodeStats
    }
  }

  return { ...node, children: compressedChildren }
}
