import { buildTreeData } from './buildTree';
// @ts-ignore
import fs from 'fs';

const mockDataPath = '/home/lucasse/Documents/site-health-check/frontend/public/mock-mid-size-result.json';
const rawMap = JSON.parse(fs.readFileSync(mockDataPath, 'utf8'));

const mockHosts = Object.entries(rawMap).map(([ip, data]: [string, any]) => ({
  ...data,
  ip_address: ip
}));

const tree = buildTreeData(mockHosts);

function filterTree(nodes: any[], explicitFilters: Record<string, string[]>, parentFilter: string[] = ['all']): any[] {
  return nodes.map(node => {
    const filterForChildren = explicitFilters[node.id] || parentFilter
    let matchesStatus = false
    
    if (filterForChildren.includes('all')) {
      matchesStatus = true
    } else {
      for (const f of filterForChildren) {
        if (f === 'active' && (node.status === 'success' || (node.type === 'HTTP' && node.status === 'neutral'))) matchesStatus = true
        if (f === 'warning' && node.status === 'warning') matchesStatus = true
        if (f === 'failed' && (node.status === 'error')) matchesStatus = true
        if (f === 'ghost' && (node.status === 'ghost' || (node.nodeStats?.ghost || 0) > 0)) matchesStatus = true
        if (f === 'void' && node.type === 'Void') matchesStatus = true
        if (matchesStatus) break
      }
    }

    const filteredChildren = filterTree(node.children || [], explicitFilters, filterForChildren)
    
    if (matchesStatus || filteredChildren.length > 0) {
      const hasExplicit = explicitFilters[node.id] !== undefined
      const isRedundant = hasExplicit && JSON.stringify(explicitFilters[node.id].sort()) === JSON.stringify(parentFilter.sort())
      return { ...node, children: filteredChildren, appliedFilter: filterForChildren, isExplicitFilter: hasExplicit && !isRedundant }
    }
    return null
  }).filter((n) => n !== null)
}

// Global root is tree[0]
const ghostFiltered = filterTree(tree, { [tree[0].id]: ['ghost'] });

function printTree(nodes: any[], indent = '') {
  for (const n of nodes) {
    console.log(`${indent}${n.type} ${n.label} (appliedFilter: ${n.appliedFilter}, isExplicit: ${n.isExplicitFilter})`);
    if (n.children) printTree(n.children, indent + '  ');
  }
}

printTree(ghostFiltered);
