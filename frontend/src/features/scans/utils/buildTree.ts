import type { TreeNode, TreeNodeStatus } from '../types'

const STATUS_PRIORITY: Record<TreeNodeStatus, number> = {
  error: 4,
  warning: 3,
  success: 2,
  neutral: 1,
  empty: 0
}

function propagateStatus(node: TreeNode): TreeNodeStatus {
  if (!node.children || node.children.length === 0) {
    return node.status || 'neutral'
  }

  let worstStatus: TreeNodeStatus = node.status || 'neutral'
  let activeCount = 0
  let failedCount = 0
  let ghostCount = 0
  let voidCount = 0

  node.children.forEach(child => {
    const childStatus = propagateStatus(child)
    
    // Bubble up worst status
    if ((STATUS_PRIORITY[childStatus] || 0) > (STATUS_PRIORITY[worstStatus] || 0)) {
      worstStatus = childStatus
    }

    // Aggregate stats from children
    if (child.type === 'Void') {
      voidCount += (child.nodeStats?.void || 1)
    } else if (child.type === 'Host') {
      // CIDR level counting Hosts
      if (child.nodeStats) {
        if (child.nodeStats.active > 0) activeCount++
        else if (child.nodeStats.failed > 0) failedCount++
        else if (child.nodeStats.ghost > 0) ghostCount++
      }
    } else if (child.type === 'Port') {
      // Host level counting Ports
      if (childStatus === 'error') failedCount++
      else if (childStatus === 'success' || childStatus === 'warning') activeCount++
    }
  })

  node.status = worstStatus
  
  if (node.type === 'Host' || node.type === 'CIDR') {
    if (node.type === 'Host' && activeCount === 0 && failedCount === 0 && node.children.length === 0) {
      ghostCount = 1
    }
    node.nodeStats = {
      active: activeCount,
      failed: failedCount,
      ghost: ghostCount,
      void: voidCount
    }
  }

  return node.status
}

export function buildTreeData(hosts: any[]): TreeNode[] {
  const cidrGroups = new Map<string, any[]>()
  
  hosts.forEach(host => {
    const cidr = host.metadata?.resolved_from || 'Unknown Target'
    if (!cidrGroups.has(cidr)) cidrGroups.set(cidr, [])
    cidrGroups.get(cidr)!.push(host)
  })

  const rootNodes: TreeNode[] = []

  for (const [cidr, groupHosts] of cidrGroups.entries()) {
    const hostNodes: TreeNode[] = []

    groupHosts.forEach((host, hostIdx) => {
      const isVoidAgg = host.ip_address?.startsWith('Void')
      
      if (isVoidAgg) {
        const match = host.ip_address.match(/\d+/)
        const numVoid = match ? parseInt(match[0], 10) : 1
        hostNodes.push({
          id: `host-${cidr}-${hostIdx}-void`,
          type: 'Void',
          label: host.ip_address,
          status: 'neutral',
          nodeStats: { active: 0, failed: 0, ghost: 0, void: numVoid },
          children: []
        })
        return
      }

      const ipLabel = host.ip_address || 'Unknown IP'
      const hostNode: TreeNode = {
        id: `host-${cidr}-${host.ip_address}-${hostIdx}`,
        type: 'Host',
        label: ipLabel,
        status: 'neutral',
        children: []
      }

      const portsArray = host.ports ? Object.entries(host.ports).map(([pn, pData]) => ({ port_number: pn, ...(pData as any) })) : []
      
      portsArray.forEach((port: any) => {
        const portIdStr = `port-${hostNode.id}-${port.port_number}`
        const portStatus: TreeNodeStatus = port.tcp_status === 'open' ? 'success' : 'error'
        
        let tlsInfoStr = undefined
        if (port.tls_certificate) {
          tlsInfoStr = port.tls_certificate.valid ? `${port.tls_certificate.expires_in_days}d` : 'Invalid'
        }

        const portNode: TreeNode = {
          id: portIdStr,
          type: 'Port',
          label: `${port.port_number}/tcp`,
          status: portStatus,
          latencyMs: port.tcp_latency_ms,
          tlsInfo: tlsInfoStr,
          children: []
        }

        if (port.http_routing_checks) {
          Object.entries(port.http_routing_checks).forEach(([domain, http]: [string, any], httpIdx) => {
            let httpStatus: TreeNodeStatus = 'error'
            let statusCodeStr = 'Error'
            
            if (http.status_code) {
              statusCodeStr = `HTTP ${http.status_code}`
              if (http.status_code >= 200 && http.status_code < 300) httpStatus = 'success'
              else if (http.status_code >= 300 && http.status_code < 400) httpStatus = 'warning'
              else httpStatus = 'error'
            }

            portNode.children.push({
              id: `http-${portIdStr}-${domain}-${httpIdx}`,
              type: 'HTTP',
              label: `${statusCodeStr} (${domain})`,
              status: httpStatus,
              latencyMs: http.http_latency_ms,
              children: [],
              rawPayload: http
            })
          })
        }
        hostNode.children.push(portNode)
      })
      hostNodes.push(hostNode)
    })

    const cidrNode: TreeNode = {
      id: `cidr-${cidr}`,
      type: 'CIDR',
      label: cidr,
      status: 'neutral',
      children: hostNodes
    }
    rootNodes.push(cidrNode)
  }

  rootNodes.forEach(propagateStatus)
  return rootNodes
}
