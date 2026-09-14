import type { TreeNode, TreeNodeStatus } from '../types'

export function buildTreeData(hosts: any[]): TreeNode[] {
  // 1. Group hosts by CIDR (metadata.resolved_from)
  const cidrGroups = new Map<string, any[]>()
  
  hosts.forEach(host => {
    const cidr = host.metadata?.resolved_from || 'Unknown Target'
    if (!cidrGroups.has(cidr)) cidrGroups.set(cidr, [])
    cidrGroups.get(cidr)!.push(host)
  })

  // 2. Build the TreeNode structure
  const rootNodes: TreeNode[] = []

  for (const [cidr, groupHosts] of cidrGroups.entries()) {
    let cidrActive = 0
    let cidrFailed = 0
    let cidrGhost = 0
    let cidrVoid = 0

    // Host Nodes (Level 2)
    const hostNodes: TreeNode[] = []

    groupHosts.forEach((host, hostIdx) => {
      const isVoidAgg = host.ip_address?.startsWith('Void')
      
      if (isVoidAgg) {
        // Extract the number from "Void (252)" or "Void (252 IPs)"
        const match = host.ip_address.match(/\d+/)
        if (match) cidrVoid += parseInt(match[0], 10)
        else cidrVoid += 1
        
        const numVoid = match ? parseInt(match[0], 10) : 1
        hostNodes.push({
          id: `host-${cidr}-${hostIdx}-void`,
          type: 'Void',
          label: host.ip_address,
          status: 'neutral',
          nodeStats: { active: 0, failed: 0, ghost: 0, void: numVoid },
          children: []
        })
        return // Skip port processing for Void summary nodes
      }

      // Check ports to determine Host status
      const portsArray = host.ports ? Object.entries(host.ports).map(([pn, pData]) => ({ port_number: pn, ...(pData as any) })) : []
      let hostActivePorts = 0
      let hostFailedPorts = 0
      
      portsArray.forEach((p: any) => {
        if (p.tcp_status === 'open') hostActivePorts++
        else hostFailedPorts++
      })

      if (hostActivePorts > 0) {
        cidrActive++
      }
      if (hostFailedPorts > 0) {
        if (hostActivePorts === 0) {
          cidrFailed++
        }
      }
      if (hostActivePorts === 0 && hostFailedPorts === 0) {
        cidrGhost++
      }

      const ipLabel = host.ip_address || 'Unknown IP'
      const hostLabel = ipLabel

      const hostNode: TreeNode = {
        id: `host-${cidr}-${host.ip_address}-${hostIdx}`,
        type: 'Host',
        label: hostLabel,
        status: 'neutral',
        nodeStats: {
          active: hostActivePorts,
          failed: hostFailedPorts,
          ghost: hostActivePorts === 0 && hostFailedPorts === 0 ? 1 : 0,
          void: 0
        },
        children: []
      }

      // Port Nodes (Level 3)
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

        // HTTP Checks (Level 4 Leaf)
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

    const cidrLabel = cidr

    // CIDR Root Node (Level 1)
    const cidrNode: TreeNode = {
      id: `cidr-${cidr}`,
      type: 'CIDR',
      label: cidrLabel,
      status: 'neutral',
      nodeStats: {
        active: cidrActive,
        failed: cidrFailed,
        ghost: cidrGhost,
        void: cidrVoid
      },
      children: hostNodes
    }

    rootNodes.push(cidrNode)
  }

  return rootNodes
}
