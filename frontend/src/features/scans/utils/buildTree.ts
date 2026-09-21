import type { TreeNode, TreeNodeStatus } from '../types'

const STATUS_PRIORITY: Record<TreeNodeStatus, number> = {
  error: 5,
  warning: 4,
  success: 3,
  ghost: 2,
  neutral: 1,
  empty: 0
}

function propagateStatus(node: TreeNode): TreeNodeStatus {
  if (!node.children || node.children.length === 0) {
    return node.status || 'neutral'
  }

  let worstStatus: TreeNodeStatus = node.status || 'neutral'
  let activeCount = 0
  let warningCount = 0
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
    } else if (child.type === 'Host' || child.type === 'CIDR' || child.type === 'Target' || child.type === 'CIDR Target') {
      // Parent level counting children stats
      if (child.nodeStats) {
        if (child.nodeStats.active > 0) activeCount += child.nodeStats.active
        if (child.nodeStats.warning > 0) warningCount += child.nodeStats.warning
        if (child.nodeStats.failed > 0) failedCount += child.nodeStats.failed
        if (child.nodeStats.ghost > 0) ghostCount += child.nodeStats.ghost
      }
    } else if (child.type === 'Port') {
      // Host level counting Ports
      if (child.status === 'success') activeCount++
      else if (child.status === 'warning') warningCount++
      else if (child.status === 'error') failedCount++
    }
  })

  node.status = worstStatus
  
  if (node.type === 'Host' || node.type === 'CIDR' || node.type === 'GlobalRoot' || node.type === 'Target' || node.type === 'CIDR Target') {
    if (node.type === 'Host' && !node.label.startsWith('Void')) {
      const hasOpenPort = node.children.some(child => child.rawPayload?.tcp_status === 'open')
      if (!hasOpenPort) {
        ghostCount = Math.max(1, node.children.length)
        failedCount = 0
        activeCount = 0
        warningCount = 0
        node.status = 'ghost'
        node.children.forEach(child => { child.status = 'ghost' })
      }
    }
    node.nodeStats = {
      active: activeCount,
      warning: warningCount,
      failed: failedCount,
      ghost: ghostCount,
      void: voidCount
    }
  }

  return node.status
}

export function buildTreeData(hosts: any[]): TreeNode[] {
  const cidrGroups = new Map<string, any[]>()
  const rogueHosts: any[] = []
  
  hosts.forEach(host => {
    const cidr = host.metadata?.resolved_from
    if (cidr) {
      if (!cidrGroups.has(cidr)) cidrGroups.set(cidr, [])
      cidrGroups.get(cidr)!.push(host)
    } else {
      rogueHosts.push(host)
    }
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
          nodeStats: { active: 0, warning: 0, failed: 0, ghost: 0, void: numVoid },
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
        children: [],
        rawPayload: { ...host, ports: undefined }
      }

      const portsArray = host.ports ? Object.entries(host.ports).map(([pn, pData]) => ({ port_number: pn, ...(pData as any) })) : []
      
      portsArray.forEach((port: any) => {
        const portIdStr = `port-${hostNode.id}-${port.port_number}`
        let portStatus: TreeNodeStatus = port.tcp_status === 'open' ? 'success' : 'error'
        
        let tlsInfoStr = undefined
        if (port.tls_certificate) {
          tlsInfoStr = port.tls_certificate.valid ? `${port.tls_certificate.expires_in_days}d` : 'Invalid'
          if (port.tls_certificate.valid === false) {
            portStatus = 'warning'
          } else if (port.tls_certificate.expires_in_days < 30) {
            portStatus = 'warning'
          }
        }

        const portNode: TreeNode = {
          id: portIdStr,
          type: 'Port',
          label: `${port.port_number}/tcp`,
          status: portStatus,
          latencyMs: port.tcp_latency_ms,
          tlsInfo: tlsInfoStr,
          children: [],
          rawPayload: { ...port, http_routing_checks: undefined }
        }


        if (port.http_routing_checks) {
          Object.entries(port.http_routing_checks).forEach(([domain, http]: [string, any], httpIdx) => {
            let httpStatus: TreeNodeStatus = 'error'
            let statusCodeStr = 'Error'
            
            if (http.status_code) {
              statusCodeStr = `HTTP ${http.status_code}`
              if (http.status_code >= 200 && http.status_code < 300) httpStatus = 'success'
              else if (http.status_code >= 300 && http.status_code < 400) httpStatus = 'neutral'
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
    const totalPossibleHosts = groupHosts[0]?.metadata?.total_hosts || groupHosts.length
    const totalVoid = Math.max(0, totalPossibleHosts - groupHosts.length)
    
    if (totalVoid > 0) {
      hostNodes.push({
        id: `void-${cidr}`,
        type: 'Void',
        label: `Void Space (${totalVoid} IPs)`,
        status: 'neutral',
        nodeStats: { active: 0, warning: 0, failed: 0, ghost: 0, void: totalVoid },
        children: [],
        rawPayload: { description: `${totalVoid} IPs did not respond to the scan.` }
      })
    }

    const isCidr = cidr.includes('/')
    
    if (!isCidr && hostNodes.length === 1 && hostNodes[0].label === cidr) {
      rootNodes.push(hostNodes[0])
    } else {
      const targetType = isCidr ? 'CIDR Target' : 'Target'
      const targetNode: TreeNode = {
        id: `target-${cidr}`,
        type: targetType,
        label: cidr,
        status: 'neutral',
        children: hostNodes,
        rawPayload: { target: cidr, total_hosts: totalPossibleHosts }
      }
      rootNodes.push(targetNode)
    }
  }

  // Process rogue hosts (no CIDR) directly into rootNodes
  rogueHosts.forEach((host, hostIdx) => {
    const isVoidAgg = host.ip_address?.startsWith('Void')
    
    if (isVoidAgg) {
      const match = host.ip_address.match(/\d+/)
      const numVoid = match ? parseInt(match[0], 10) : 1
      rootNodes.push({
        id: `host-rogue-${hostIdx}-void`,
        type: 'Void',
        label: host.ip_address,
        status: 'neutral',
        nodeStats: { active: 0, warning: 0, failed: 0, ghost: 0, void: numVoid },
        children: []
      })
      return
    }

    const ipLabel = host.ip_address || 'Unknown IP'
    const hostNode: TreeNode = {
      id: `host-rogue-${host.ip_address}-${hostIdx}`,
      type: 'Host',
      label: ipLabel,
      status: 'neutral',
      children: [],
      rawPayload: { ...host, ports: undefined }
    }

    const portsArray = host.ports ? Object.entries(host.ports).map(([pn, pData]) => ({ port_number: pn, ...(pData as any) })) : []
    
    portsArray.forEach((port: any) => {
      const portIdStr = `port-${hostNode.id}-${port.port_number}`
      let portStatus: TreeNodeStatus = port.tcp_status === 'open' ? 'success' : 'error'
      
      let tlsInfoStr = undefined
      if (port.tls_certificate) {
        tlsInfoStr = port.tls_certificate.valid ? `${port.tls_certificate.expires_in_days}d` : 'Invalid'
        if (port.tls_certificate.valid === false) {
          portStatus = 'warning'
        } else if (port.tls_certificate.expires_in_days < 30) {
          portStatus = 'warning'
        }
      }

      const portNode: TreeNode = {
        id: portIdStr,
        type: 'Port',
        label: `${port.port_number}/tcp`,
        status: portStatus,
        latencyMs: port.tcp_latency_ms,
        tlsInfo: tlsInfoStr,
        children: [],
        rawPayload: { ...port, http_routing_checks: undefined }
      }


      if (port.http_routing_checks) {
        Object.entries(port.http_routing_checks).forEach(([domain, http]: [string, any], httpIdx) => {
          let httpStatus: TreeNodeStatus = 'error'
          let statusCodeStr = 'Error'
          
          if (http.status_code) {
            statusCodeStr = `HTTP ${http.status_code}`
            if (http.status_code >= 200 && http.status_code < 300) httpStatus = 'success'
            else if (http.status_code >= 300 && http.status_code < 400) httpStatus = 'neutral'
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
    rootNodes.push(hostNode)
  })

  rootNodes.forEach(propagateStatus)
  
  const globalRoot: TreeNode = {
    id: 'global-root-id',
    type: 'GlobalRoot',
    label: 'Global Root',
    status: 'neutral',
    children: rootNodes,
    rawPayload: { total_cidrs: rootNodes.length }
  }
  
  propagateStatus(globalRoot)
  
  return [globalRoot]
}
