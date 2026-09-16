import { buildTreeData } from '../frontend/src/features/scans/utils/buildTree'
import { compressTreeNodes } from '../frontend/src/features/scans/utils/compressTree'
import mockData from '../frontend/public/mock-mid-size-result.json'
import type { TreeNode } from '../frontend/src/features/scans/types'

function filterTree(nodes: TreeNode[], explicitFilters: Record<string, string>, parentFilter: string = 'all'): TreeNode[] {
  return nodes.map(node => {
    const filterForChildren = explicitFilters[node.id] || parentFilter
    let matchesStatus = false
    
    if (filterForChildren === 'all') {
      matchesStatus = true
    } else {
      if (filterForChildren === 'active' && (node.status === 'success' || node.status === 'warning')) matchesStatus = true
      if (filterForChildren === 'failed' && node.status === 'error') matchesStatus = true
      if (filterForChildren === 'ghost' && (node.status === 'ghost' || (node.nodeStats?.ghost || 0) > 0)) matchesStatus = true
      if (filterForChildren === 'void' && node.type === 'Void') matchesStatus = true
    }

    const filteredChildren = filterTree(node.children, explicitFilters, filterForChildren)
    
    if (matchesStatus || filteredChildren.length > 0) {
      const hasExplicit = explicitFilters[node.id] !== undefined
      const isRedundant = hasExplicit && explicitFilters[node.id] === parentFilter
      return { ...node, children: filteredChildren, appliedFilter: filterForChildren, isExplicitFilter: hasExplicit && !isRedundant } as TreeNode
    }
    return null
  }).filter((n) => n !== null) as TreeNode[]
}

const mockHosts = Object.entries(mockData).map(([ip, data]: [string, any]) => ({
  ip_address: ip,
  ...data
}))

const rawTree = buildTreeData(mockHosts)

const filteredAll = filterTree(rawTree, { 'global-root-id': 'all' })
const compressedAll = filteredAll[0]?.children.map(compressTreeNodes) || []

const target143 = compressedAll.find(n => n.label === '143.106.1.0/24')
const host143_6 = target143?.children.find(n => n.label === '143.106.1.6' || n.label.includes('143.106.1.6 ➔'))

console.log("FILTER ALL:")
console.log(JSON.stringify(host143_6, null, 2))

const filteredFailed = filterTree(rawTree, { 'global-root-id': 'failed' })
const compressedFailed = filteredFailed[0]?.children.map(compressTreeNodes) || []

const targetFailed143 = compressedFailed.find(n => n.label === '143.106.1.0/24')
const hostFailed143_6 = targetFailed143?.children.find(n => n.label === '143.106.1.6' || n.label.includes('143.106.1.6 ➔'))

console.log("\nFILTER FAILED:")
console.log(JSON.stringify(hostFailed143_6, null, 2))
