const fs = require('fs');

function compressTreeNodes(node) {
  const compressedChildren = (node.children || []).map(compressTreeNodes);
  const isProtectedStructure = node.type === 'GlobalRoot';

  if (!isProtectedStructure && compressedChildren.length === 1 && !node.isExplicitFilter && !compressedChildren[0].isExplicitFilter) {
    const singleChild = compressedChildren[0];
    let newLabel = `${node.label} ➔ ${singleChild.label}`;
    
    // De-duplicate if identical
    if (node.label === singleChild.label || singleChild.label.startsWith(node.label + " ➔")) {
        // wait, let's just log what it WOULD do
    }
    
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
    };
  }

  return { ...node, children: compressedChildren };
}

const host143 = {
  id: "host-1",
  type: "Host",
  label: "143.106.1.6",
  status: "neutral",
  children: [
    {
      id: "port-1",
      type: "Port",
      label: "443/tcp",
      status: "success",
      children: [
        {
          id: "http-1",
          type: "HTTP",
          label: "HTTP 200 (legacy.unicamp.br)",
          status: "success",
          children: []
        }
      ]
    }
  ]
};

console.log(JSON.stringify(compressTreeNodes(host143), null, 2));
