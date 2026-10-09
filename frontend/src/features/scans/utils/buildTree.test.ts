import { describe, it, expect } from 'vitest'
import { buildTreeData } from './buildTree'

describe('buildTreeData with Subruns', () => {
  it('should create Subrun nodes from summaries, with [FETCH] capability', () => {
    const summaries = [
      { target: '10.0.0.0/16', subrun_id: '10.0.0.0/24', total_ips: 256, active_ips: 0 },
      { target: '10.0.0.0/16', subrun_id: '10.0.1.0/24', total_ips: 256, active_ips: 10 },
    ]
    
    // We only fetched hosts for the second subrun
    const hosts = [
      { 
        ip_address: '10.0.1.5', 
        metadata: { resolved_from: '10.0.0.0/16', subrun_id: '10.0.1.0/24' }, 
        ports: { 443: { tcp_status: 'open' } } 
      }
    ]

    const tree = buildTreeData(hosts, summaries)
    
    expect(tree).toHaveLength(1)
    const root = tree[0]
    
    expect(root.children).toHaveLength(1)
    const targetNode = root.children[0]
    expect(targetNode.type).toBe('CIDR Target')
    expect(targetNode.label).toBe('10.0.0.0/16')
    
    expect(targetNode.children).toHaveLength(2)
    
    const subrun1 = targetNode.children.find((c: any) => c.label === '10.0.0.0/24')
    expect(subrun1).toBeDefined()
    expect(subrun1!.type).toBe('Subrun')
    expect(subrun1!.children).toHaveLength(0)
    expect(subrun1!.rawPayload.isFetched).toBe(false)
    
    const subrun2 = targetNode.children.find((c: any) => c.label === '10.0.1.0/24')
    expect(subrun2).toBeDefined()
    expect(subrun2!.type).toBe('Subrun')
    expect(subrun2!.children).toHaveLength(2)
    expect(subrun2!.children[0].label).toBe('10.0.1.5')
    expect(subrun2!.children[1].type).toBe('Void')
    expect(subrun2!.rawPayload.isFetched).toBe(true)
  })
})
