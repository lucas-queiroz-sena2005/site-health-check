import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { ReactFlow, Background, Controls, MiniMap, useNodesState, useEdgesState, Handle, Position } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

// --- DATA PROCESSING & CLASSIFICATION GROUPING ---

function getSmartClassification(ipStr, p443) {
   let textToAnalyze = '';
   if (p443 && p443.tls_certificate && p443.tls_certificate.domains_discovered_sans) {
      textToAnalyze += p443.tls_certificate.domains_discovered_sans.join(' ');
   }
   if (p443 && p443.http_routing_checks) {
      textToAnalyze += Object.keys(p443.http_routing_checks).join(' ');
   }
   textToAnalyze = textToAnalyze.toLowerCase();

   if (!textToAnalyze && (!p443 || p443.tcp_status !== 'open')) return 'unreachable';
   
   if (textToAnalyze.includes('gitlab')) return 'source_control';
   if (textToAnalyze.includes('db') || textToAnalyze.includes('sql') || textToAnalyze.includes('postgres')) return 'databases';
   if (textToAnalyze.includes('fw') || textToAnalyze.includes('vpn') || textToAnalyze.includes('firewall')) return 'network_security';
   if (textToAnalyze.includes('mail') || textToAnalyze.includes('smtp')) return 'mail_servers';
   if (textToAnalyze.includes('susy') || textToAnalyze.includes('grades') || textToAnalyze.includes('moodle')) return 'academic_services';
   if (textToAnalyze.includes('admin') || textToAnalyze.includes('panel')) return 'management';
   
   if (p443 && p443.tcp_status === 'open') return 'web_services';
   
   return 'infrastructure';
}

function groupIpsByClassification(nodes) {
  const groupedNodes = [];
  let unassigned = [...nodes];
  
  while (unassigned.length > 0) {
     const counts = {};
     unassigned.forEach(node => {
        (node.classifications || []).forEach(c => {
           counts[c] = (counts[c] || 0) + 1;
        });
     });
     
     let bestClass = null;
     let maxCount = 0;
     Object.entries(counts).forEach(([c, count]) => {
        if (count > maxCount) {
           maxCount = count;
           bestClass = c;
        }
     });
     
     if (maxCount >= 2) {
        const members = unassigned.filter(n => (n.classifications || []).includes(bestClass));
        unassigned = unassigned.filter(n => !(n.classifications || []).includes(bestClass));
        
        groupedNodes.push({
           id: `group-${bestClass}-${Date.now()}-${Math.random()}`,
           label: `Class: ${bestClass}`,
           type: 'Classification',
           status: 'slate', 
           children: members
        });
     } else {
        break;
     }
  }
  
  groupedNodes.push(...unassigned);
  return groupedNodes;
}

function compressNode(node) {
  if (!node.children || node.children.length === 0) {
    return node;
  }
  
  let newChildren = node.children.map(compressNode);
  
  if (['CIDR Target', 'Pool', 'Classification'].includes(node.type)) {
     return { ...node, children: newChildren };
  }
  
  if (newChildren.length === 1) {
    const child = newChildren[0];
    const statusPriority = { 'red': 3, 'amber': 2, 'green': 1, 'slate': 0 };
    const myP = statusPriority[node.status] || 0;
    const childP = statusPriority[child.status] || 0;
    const mergedStatus = childP >= myP ? child.status : node.status;
    
    return {
      ...child,
      id: node.id,
      label: `${node.label} ➔ ${child.label}`,
      type: `${node.type} ➔ ${child.type}`,
      status: mergedStatus,
      latency: child.latency && child.latency !== 'TIMEOUT' ? child.latency : node.latency,
      tlsExpiration: (child.tlsExpiration && child.tlsExpiration !== '—') ? child.tlsExpiration : node.tlsExpiration,
      subLabel: child.subLabel || node.subLabel,
      details: { ...(node.details || {}), ...(child.details || {}) }
    };
  }
  
  return { ...node, children: newChildren };
}

function propagateStatus(node) {
  const statusPriority = { 'red': 3, 'amber': 2, 'green': 1, 'slate': 0 };

  if (!node.children || node.children.length === 0) return node.status || 'slate';
  
  let maxPriority = -1;
  let worstStatus = 'slate';
  
  node.children.forEach(child => {
      const childStatus = propagateStatus(child);
      const p = statusPriority[childStatus] || 0;
      if (p > maxPriority) {
          maxPriority = p;
          worstStatus = childStatus;
      }
  });
  
  if (['CIDR Target', 'Pool', 'Classification'].includes(node.type)) {
      node.status = worstStatus;
  }
  
  return node.status || 'slate';
}

function propagateStats(node, ghostWindowHours) {
  if (!node.children || node.children.length === 0) {
    const isGhost = node.type.includes('Ghost') || (node.lastSeenHoursAgo && node.lastSeenHoursAgo <= ghostWindowHours);
    const isVoid = node.type.includes('Void');
    const isFailed = node.status === 'red';
    node.nodeStats = {
       active: (!isGhost && !isVoid && !isFailed) ? 1 : 0,
       failed: (isFailed && !isGhost) ? 1 : 0,
       ghost: isGhost ? 1 : 0,
       void: isVoid ? 1 : 0
    };
    return node.nodeStats;
  }
  
  const agg = { active: 0, failed: 0, ghost: 0, void: 0 };
  node.children.forEach(child => {
     const childStats = propagateStats(child, ghostWindowHours);
     agg.active += childStats.active;
     agg.failed += childStats.failed;
     agg.ghost += childStats.ghost;
     agg.void += childStats.void;
  });
  
  node.nodeStats = agg;
  return agg;
}

function generateTreeFromData(jsonData) {
  const targets = {};
  
  const allIps = Object.keys(jsonData);
  allIps.forEach(ip => {
    const parts = ip.split('.');
    if (parts.length === 4) {
      const clonedIp = `${parts[0]}.${parts[1]}.8.${parts[3]}`;
      jsonData[clonedIp] = JSON.parse(JSON.stringify(jsonData[ip]));
    }
  });

  Object.entries(jsonData).forEach(([ip, data]) => {
    const parts = ip.split('.');
    if (parts.length !== 4) return;
    const cidr = `${parts[0]}.${parts[1]}.${parts[2]}.0/24`;
    
    if (!targets[cidr]) {
      targets[cidr] = {
        id: `target-${cidr}`,
        label: cidr,
        type: 'CIDR Target',
        status: 'slate',
        tlsExpiration: '—',
        stats: '0 active / 0 ghosts / 0 void',
        details: { scope: `Unicamp Subnet ${cidr}` },
        pools: { active: [], ghost: [], void: [] }
      };
    }
    
    const isClosed = !data.ports || !data.ports['443'] || data.ports['443'].tcp_status !== 'open';
    
    let ipType = 'IP';
    let ipStatus = 'green';
    let lastSeenHoursAgo = undefined;
    let latency = data.ports?.['443']?.tcp_latency_ms ? `${data.ports['443'].tcp_latency_ms}ms` : 'TIMEOUT';
    
    const hash = ip.split('.').reduce((sum, n) => sum + parseInt(n, 10), 0);
    const classesForIp = [getSmartClassification(ip, data.ports?.['443'])];

    if (isClosed) {
      if (hash % 11 === 0) {
        ipType = 'Ghost';
        ipStatus = 'red';
        lastSeenHoursAgo = (hash % 20) * 12 + 4;
        latency = 'TIMEOUT';
      } else {
        ipType = 'Void';
        ipStatus = 'slate';
        latency = 'REFUSED';
      }
    }
    
    const ports = [];
    if (data.ports && data.ports['443'] && data.ports['443'].tcp_status === 'open') {
      const p443 = data.ports['443'];
      
      const portNode = {
        id: `port-${ip}-443`,
        label: 'Port 443 (HTTPS)',
        type: 'Port',
        status: 'green',
        tlsExpiration: p443.tls_certificate?.valid ? `${p443.tls_certificate.expires_in_days} days left` : '—',
        subLabel: 'TLS Handshake Valid',
        details: { issuer: p443.tls_certificate?.issuer || 'Unknown' },
        children: []
      };
      
      if (p443.tls_certificate && p443.tls_certificate.expires_in_days < 30) {
         portNode.status = 'amber';
         ipStatus = 'amber';
      }
      if (p443.tls_certificate?.valid === false) {
         portNode.status = 'red';
         ipStatus = 'red';
         portNode.subLabel = 'TLS Invalid / Expired';
      }
      
      p443.tls_certificate?.domains_discovered_sans?.forEach((san) => {
        portNode.children.push({
          id: `san-${san}`, label: `SAN: ${san}`, type: 'SAN', status: 'slate'
        });
      });
      
      if (p443.http_routing_checks) {
        Object.entries(p443.http_routing_checks).forEach(([domain, check]) => {
          portNode.children.push({
            id: `http-${domain}`, 
            label: `HTTP ${check.status_code || 'Err'} (${domain})`, 
            type: 'HTTP', 
            status: (!check.status_code || check.status_code >= 400) ? 'red' : 'green', 
            details: check
          });
        });
      }
      
      ports.push(portNode);
    }
    
    const ipNode = {
      id: `ip-${ip}`,
      label: ip,
      type: ipType,
      status: ipStatus,
      classifications: classesForIp, 
      tlsExpiration: '—',
      latency,
      details: { ip, lastSeenHoursAgo: lastSeenHoursAgo ? `${lastSeenHoursAgo}h ago` : undefined },
      lastSeenHoursAgo,
      children: ports.length > 0 ? ports : null
    };
    
    if (ipType === 'IP') targets[cidr].pools.active.push(ipNode);
    else if (ipType === 'Ghost') targets[cidr].pools.ghost.push(ipNode);
    else targets[cidr].pools.void.push(ipNode);
  });
  
  const rawTree = Object.values(targets).map(target => {
    target.children = [];
    
    const groupedActive = groupIpsByClassification(target.pools.active);
    const groupedGhost = groupIpsByClassification(target.pools.ghost);

    if (groupedActive.length > 0) {
      target.children.push({
        id: `${target.id}-pool-active`, label: `Active Pool (${target.pools.active.length} IPs)`, type: 'Pool', status: 'slate', children: groupedActive
      });
    }
    if (groupedGhost.length > 0) {
      target.children.push({
        id: `${target.id}-pool-ghost`, label: `Ghost Pool (${target.pools.ghost.length} IPs)`, type: 'Pool', status: 'slate', children: groupedGhost
      });
    }
    if (target.pools.void.length > 0) {
      target.children.push({
        id: `${target.id}-pool-void`, label: `Void Space (${target.pools.void.length} IPs)`, type: 'Void', status: 'slate', children: [] 
      });
    }
    
    target.stats = `${target.pools.active.length} active / ${target.pools.ghost.length} ghosts / ${target.pools.void.length} void`;
    
    delete target.pools;
    return target;
  });

  rawTree.forEach(propagateStatus);
  return rawTree;
}

// --- LAYERED RECURSIVE FILTER FUNCTION ---
function filterTree(items, parentFilter, explicitFilters, ghostWindowHours, overrideSearch = false, parentMatchesStatus = true) {
  if (!items) return [];
  
  const searchStr = parentFilter.search.trim();
  let regex = null;
  if (searchStr) {
      try {
          regex = new RegExp(searchStr, 'i');
      } catch (e) {
      }
  }
  
  return items.map(item => {
    let matchesStatus = false;
    const itemStatus = item.status || 'slate';
    
    if (parentFilter.statuses.includes('all')) {
      matchesStatus = true;
    } else {
      if (parentFilter.statuses.includes('active') && (itemStatus === 'green' || itemStatus === 'amber')) matchesStatus = true;
      if (parentFilter.statuses.includes('failed') && itemStatus === 'red') matchesStatus = true;
      if (parentFilter.statuses.includes('ghost') && (item.type.includes('Ghost') || (item.lastSeenHoursAgo && item.lastSeenHoursAgo <= ghostWindowHours))) matchesStatus = true;
      if (parentFilter.statuses.includes('void') && item.type.includes('Void')) matchesStatus = true;
      
      if (['CIDR Target', 'Pool', 'Classification', 'Port', 'SAN', 'HTTP'].includes(item.type)) {
         matchesStatus = parentMatchesStatus;
      }
    }
      
    let matchesSearch = true;
    if (searchStr) {
        const searchableText = `${item.label} ${item.subLabel || ''} ${item.type} ${JSON.stringify(item.details || {})} ${(item.classifications || []).join(' ')}`.toLowerCase();
        if (regex) {
            matchesSearch = regex.test(searchableText);
        } else {
            matchesSearch = searchableText.includes(searchStr.toLowerCase());
        }
    }

    const filterForChildren = explicitFilters[item.id] || parentFilter;
    const forceIncludeChildren = overrideSearch || (searchStr && matchesSearch);
    
    const filteredChildren = filterTree(item.children, filterForChildren, explicitFilters, ghostWindowHours, forceIncludeChildren, matchesStatus);

    if ((matchesStatus && (matchesSearch || overrideSearch)) || filteredChildren.length > 0) {
      return { 
        ...item, 
        children: filteredChildren, 
        appliedFilter: filterForChildren,
        isSearchResult: !!(searchStr && matchesSearch)
      };
    }
    return null;
  }).filter(Boolean);
}

function sortTree(items, sortBy, sortDir) {
  if (!items || items.length === 0) return items;
  
  let sorted = [...items];
  
  if (sortBy !== 'none') {
    sorted.sort((a, b) => {
       let valA = 0;
       let valB = 0;
       
       if (sortBy === 'status') {
           const p = { 'red': 3, 'amber': 2, 'green': 1, 'slate': 0 };
           valA = p[a.status || 'slate'] || 0;
           valB = p[b.status || 'slate'] || 0;
       } else if (sortBy === 'latency') {
           const parseLat = (l) => {
               if (l === 'TIMEOUT' || l === 'REFUSED') return 999999;
               if (!l) return 0;
               return parseInt(l.replace('ms', ''), 10) || 0;
           };
           valA = parseLat(a.latency);
           valB = parseLat(b.latency);
       } else if (sortBy === 'tls') {
           const parseTls = (t) => {
               if (!t || t === '—') return 999999;
               return parseInt(t.split(' ')[0], 10) || 999999;
           };
           valA = parseTls(a.tlsExpiration);
           valB = parseTls(b.tlsExpiration);
       } else if (sortBy === 'label') {
           valA = a.label.toLowerCase();
           valB = b.label.toLowerCase();
       } else if (sortBy === 'type') {
           valA = a.type.toLowerCase();
           valB = b.type.toLowerCase();
       }
       
       if (valA < valB) return sortDir === 'asc' ? -1 : 1;
       if (valA > valB) return sortDir === 'asc' ? 1 : -1;
       return 0;
    });
  }
  
  return sorted.map(item => ({ ...item, children: sortTree(item.children, sortBy, sortDir) }));
}

// --- DYNAMIC TREE AUTO-LAYOUT CALCULATOR WITH DAG CROSS-LINKING ---
function computeAutoLayout(treeData, expandedNodes, inlineDetailNodes, onToggleExpand, onToggleInlineDetail, onStatusClick, onClearNodeFilter) {
  const NODE_WIDTH = 280;
  const H_GAP = 60;  
  const V_GAP = 180; 

  const widthMap = {};
  const globalSeenIds = new Set();
  
  function computeWidthPass(node) {
      if (globalSeenIds.has(node.id)) return 0;
      globalSeenIds.add(node.id);
      
      const isExpanded = !!expandedNodes[node.id];
      if (!node.children || node.children.length === 0 || !isExpanded) {
          widthMap[node.id] = NODE_WIDTH + H_GAP;
          return widthMap[node.id];
      }
      
      const childrenWidth = node.children.reduce((sum, child) => sum + computeWidthPass(child), 0);
      widthMap[node.id] = Math.max(NODE_WIDTH + H_GAP, childrenWidth);
      return widthMap[node.id];
  }

  treeData.forEach(rootNode => computeWidthPass(rootNode));

  const flowNodes = [];
  const flowEdges = [];
  const drawnIds = new Set();

  function assignCoordinates(nodeList, startX, currentY, parentId) {
    let currentX = startX;

    nodeList.forEach((node) => {
      if (drawnIds.has(node.id)) {
          if (parentId) {
             flowEdges.push({
                 id: `edge-${parentId}-${node.id}-crosslink`,
                 source: parentId,
                 target: node.id,
                 animated: true,
                 style: { stroke: 'var(--color-blue)', strokeWidth: 1.5, strokeDasharray: '4,4' }
             });
          }
          return;
      }
      
      drawnIds.add(node.id);

      const subtreeWidth = widthMap[node.id] || (NODE_WIDTH + H_GAP);
      const isExpanded = !!expandedNodes[node.id];
      const showDetails = !!inlineDetailNodes[node.id];
      const hasChildren = node.children && node.children.length > 0;

      const nodeX = currentX + subtreeWidth / 2 - NODE_WIDTH / 2;
      const nodeY = currentY;

      flowNodes.push({
        id: node.id,
        type: 'custom',
        position: { x: nodeX, y: nodeY },
        data: {
          id: node.id,
          label: node.label,
          type: node.type,
          status: node.status,
          nodeStats: node.nodeStats,
          subLabel: node.subLabel || node.stats,
          hasChildNodes: hasChildren,
          childCount: node.children?.length || 0,
          isExpanded: isExpanded,
          showDetails: showDetails,
          details: node.details,
          appliedFilter: node.appliedFilter,
          onToggleExpand: onToggleExpand,
          onToggleInlineDetail: onToggleInlineDetail,
          onStatusClick: onStatusClick,
          onClearNodeFilter: onClearNodeFilter
        }
      });

      if (parentId) {
         flowEdges.push({
             id: `edge-${parentId}-${node.id}`,
             source: parentId,
             target: node.id,
             style: {
                 stroke: node.status === 'red' ? 'var(--color-red)' : 'var(--border-bright)',
                 strokeWidth: 1.5
             }
         });
      }

      if (isExpanded && hasChildren) {
        const nextY = currentY + V_GAP + (showDetails ? 120 : 0);
        assignCoordinates(node.children, currentX, nextY, node.id);
      }

      currentX += subtreeWidth;
    });
  }

  assignCoordinates(treeData, 40, 40, null);

  return { flowNodes, flowEdges };
}

// --- TRADITIONAL HIGH-CONTRAST NODE WITH INTERACTIVE STATUS CLICK ---
const CustomNode = ({ data }) => {
  let borderColor = 'border-[var(--border-bright)]';
  let badgeStyle = 'bg-[var(--bg-elevated)] text-[var(--text-main)] border border-[var(--border-color)]';

  if (data.status === 'red' || data.type.includes('Ghost')) {
    borderColor = 'border-[var(--color-red)]';
    badgeStyle = 'bg-[var(--color-red)]/15 text-[var(--color-red)] border border-[var(--color-red)]/40';
  } else if (data.status === 'amber') {
    borderColor = 'border-[var(--color-yellow)]';
    badgeStyle = 'bg-[var(--color-yellow)]/15 text-[var(--color-yellow)] border border-[var(--color-yellow)]/40';
  } else if (data.status === 'slate' || data.type.includes('Void')) {
    borderColor = 'border-[var(--border-bright)] border-dashed';
    badgeStyle = 'bg-[var(--bg-surface)] text-[var(--text-dim)] border border-[var(--border-color)]';
  }

  const { active, failed, ghost, void: vCount } = data.nodeStats || {};

  return (
    <div
      onClick={() => data.onToggleInlineDetail(data.id)}
      className={`px-4 py-3 rounded-lg border ${borderColor} bg-[var(--bg-surface)] text-[var(--text-main)] min-w-[280px] max-w-[340px] shadow-md cursor-pointer transition-all hover:border-[var(--color-blue)] ${data.isSearchResult ? 'outline outline-2 outline-dashed outline-[var(--text-main)] outline-offset-2' : ''}`}
    >
      {!data.type.includes('CIDR Target') && (
        <Handle type="target" position={Position.Top} className="!bg-[var(--text-muted)] !w-2.5 !h-2.5 !border-0" />
      )}

      <div className="flex flex-col gap-2 mb-1">
        <div className="flex items-start justify-between gap-3">
          <div className="flex flex-col min-w-0">
            <span className="font-mono text-xs font-bold text-[var(--text-main)] truncate max-w-[180px]">{data.label}</span>
            <span className={`mt-1 text-[10px] px-1.5 py-0.5 rounded font-sans uppercase font-semibold inline-block truncate max-w-full w-fit ${badgeStyle}`}>
              {data.type}
            </span>
          </div>
          
          <div className="flex flex-col gap-1 shrink-0 items-end">
            {active > 0 && (
              <button
                onClick={(e) => { e.stopPropagation(); data.onStatusClick(data.id, 'active'); }}
                className="flex items-center gap-1.5 px-1.5 py-0.5 rounded bg-[var(--color-green)]/15 text-[var(--color-green)] border border-[var(--color-green)]/40 hover:border-[var(--color-green)] transition-all text-[9px] font-bold uppercase"
              >
                <span className="w-1.5 h-1.5 rounded-sm bg-[var(--color-green)]" /> {active} Active
              </button>
            )}
            {failed > 0 && (
              <button
                onClick={(e) => { e.stopPropagation(); data.onStatusClick(data.id, 'failed'); }}
                className="flex items-center gap-1.5 px-1.5 py-0.5 rounded bg-[var(--color-red)]/15 text-[var(--color-red)] border border-[var(--color-red)]/40 hover:border-[var(--color-red)] transition-all text-[9px] font-bold uppercase"
              >
                <span className="w-1.5 h-1.5 rounded-sm bg-[var(--color-red)]" /> {failed} Failed
              </button>
            )}
            {ghost > 0 && (
              <button
                onClick={(e) => { e.stopPropagation(); data.onStatusClick(data.id, 'ghost'); }}
                className="flex items-center gap-1.5 px-1.5 py-0.5 rounded bg-[var(--color-red)]/15 text-[var(--color-red)] border border-[var(--color-red)]/40 hover:border-[var(--color-red)] transition-all text-[9px] font-bold uppercase"
              >
                <span className="w-1.5 h-1.5 rounded-sm bg-[var(--color-red)]" /> {ghost} Ghost
              </button>
            )}
            {vCount > 0 && (
              <span
                title="Void Space IPs have no scan history"
                className="flex items-center gap-1.5 px-1.5 py-0.5 rounded bg-[var(--bg-elevated)] text-[var(--text-dim)] border border-[var(--border-color)] cursor-default text-[9px] font-bold uppercase"
              >
                <span className="w-1.5 h-1.5 rounded-sm bg-[var(--text-dim)]" /> {vCount} Void
              </span>
            )}
          </div>
        </div>
      </div>
      
      {data.subLabel && <div className="text-xs text-[var(--text-muted)] font-sans truncate mt-2">{data.subLabel}</div>}

      {data.appliedFilter && !data.appliedFilter.statuses.includes('all') && (
        <div className="mt-1 flex items-center gap-2">
          <span className="text-[9px] font-mono text-[var(--color-blue)] uppercase font-bold">
            ↳ Filter: {data.appliedFilter.statuses.join(', ')}
          </span>
          <button
            onClick={(e) => { e.stopPropagation(); data.onClearNodeFilter(data.id); }}
            className="text-[9px] font-bold text-[var(--text-muted)] hover:text-[var(--color-red)] uppercase border border-[var(--border-color)] rounded px-1 ml-auto bg-[var(--bg-elevated)]"
          >
            Clear
          </button>
        </div>
      )}

      {data.hasChildNodes && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            data.onToggleExpand(data.id);
          }}
          className="mt-2.5 w-full py-1 px-2 text-[11px] font-sans font-semibold rounded bg-[var(--bg-elevated)] hover:bg-[var(--border-bright)] text-[var(--text-main)] transition-colors flex items-center justify-center gap-1 border border-[var(--border-color)]"
        >
          {data.isExpanded ? 'Collapse Children' : `Expand ${data.childCount} Children`}
        </button>
      )}

      {data.showDetails && data.details && (
        <div className="mt-3 pt-2.5 border-t border-[var(--border-bright)] text-[11px] text-[var(--text-muted)] space-y-1 font-mono bg-[var(--bg-main)]/60 p-2 rounded max-h-[140px] overflow-auto scrollbar-thin">
          <div className="font-sans font-bold text-[var(--color-blue)] text-[10px] uppercase">Inline Details:</div>
          {Object.entries(data.details).map(([k, v]) => (
            <div key={k} className="truncate">
              <span className="text-[var(--text-dim)] font-semibold">{k}: </span>
              <span className="text-[var(--text-main)]">
                {typeof v === 'object' ? JSON.stringify(v) : String(v)}
              </span>
            </div>
          ))}
        </div>
      )}

      {data.hasChildNodes && (
        <Handle type="source" position={Position.Bottom} className="!bg-[var(--text-muted)] !w-2.5 !h-2.5 !border-0" />
      )}
    </div>
  );
};

const nodeTypes = { custom: CustomNode };

// --- HIERARCHICAL TREE TABLE COMPONENT ---
const HierarchicalTable = ({ 
  data, expandedNodes, inlineDetailNodes, 
  onToggleNode, onToggleInlineDetail, onStatusClick, onClearNodeFilter,
  sortBy, sortDir, onSort, globalSearch
}) => {
  const renderRows = (items, depth = 0) => {
    return items.map((item) => {
      const hasChildren = item.children && item.children.length > 0;
      const isExpanded = !!expandedNodes[item.id];
      const showInlineDetails = !!inlineDetailNodes[item.id];
      
      const { active, failed, ghost, void: vCount } = item.nodeStats || {};

      let tlsCellContent = <span className="text-[var(--text-dim)]">—</span>;
      if (item.tlsExpiration && item.tlsExpiration !== '—') {
        let tlsColor = 'text-[var(--color-green)]';
        if (item.tlsExpiration.includes('left')) {
          tlsColor = 'text-[var(--color-green)]';
        } else if (item.tlsExpiration.includes('Expiring') || item.tlsExpiration.includes('Warning')) {
          tlsColor = 'text-[var(--color-yellow)] font-bold';
        } else if (item.tlsExpiration.includes('Unknown') || item.tlsExpiration.includes('Offline')) {
          tlsColor = 'text-[var(--color-red)]';
        }
        
        let tlsDisplay = item.tlsExpiration;
        tlsDisplay = tlsDisplay.replace(/ days? left/i, 'd').replace(/ hours? left/i, 'h');
        if (tlsDisplay.includes('Unknown')) tlsDisplay = 'nd';
        
        tlsCellContent = <span className={`font-mono text-xs ${tlsColor}`}>{tlsDisplay}</span>;
      }

      return (
        <React.Fragment key={item.id}>
          <tr
            onClick={() => hasChildren ? onToggleNode(item.id) : onToggleInlineDetail(item.id)}
            className={`hover:bg-[var(--bg-elevated)] bg-[var(--bg-surface)] border-b border-[var(--border-color)] text-xs transition-colors cursor-pointer ${item.isSearchResult ? 'outline outline-1 outline-dashed outline-[var(--text-main)] relative z-10' : ''}`}
          >
            <td className="py-2.5 px-4 w-[35%] overflow-hidden">
              <div className="flex items-center" style={{ paddingLeft: `${Math.min(depth, 8) * 16}px` }}>
                {hasChildren ? (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onToggleNode(item.id);
                    }}
                    className="mr-2 p-0.5 rounded hover:bg-[var(--bg-elevated)] text-[var(--text-muted)] hover:text-[var(--text-main)] transition-colors shrink-0"
                  >
                    <svg
                      className={`w-4 h-4 transform transition-transform duration-150 ${isExpanded ? 'rotate-90 text-[var(--text-main)]' : ''}`}
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" />
                    </svg>
                  </button>
                ) : (
                  <span className="w-4 mr-2 inline-block text-[var(--border-bright)] text-center font-mono font-bold shrink-0">│</span>
                )}

                <div className="flex flex-col min-w-0">
                  <span className={`font-semibold truncate ${
                    item.type.includes('Target')
                      ? 'font-mono text-[var(--text-main)] text-sm'
                      : item.type.includes('Port') || item.type.includes('➔')
                      ? 'font-mono text-[var(--color-blue)] font-bold text-[11px]'
                      : 'font-sans text-[var(--text-main)]'
                  }`}>
                    {item.label}
                  </span>
                  {item.appliedFilter && !item.appliedFilter.statuses.includes('all') && (
                    <span className="text-[9px] font-mono text-[var(--color-blue)] uppercase font-bold mt-0.5 flex items-center gap-2">
                      ↳ Filter: {item.appliedFilter.statuses.join(', ')}
                      <button
                        onClick={(e) => { e.stopPropagation(); onClearNodeFilter(item.id); }}
                        className="text-[var(--text-muted)] hover:text-[var(--color-red)] border border-[var(--border-color)] rounded px-1 bg-[var(--bg-elevated)] ml-1"
                      >
                        Clear
                      </button>
                    </span>
                  )}
                </div>
              </div>
            </td>

            <td className="py-2.5 px-4 font-sans text-[10px] text-[var(--text-muted)] font-semibold w-[15%]">
              <div className="truncate" title={item.type}>{item.type}</div>
            </td>

            <td className="py-2.5 px-4 font-sans text-xs w-[15%] truncate">
              {tlsCellContent}
            </td>

            <td className="py-2.5 px-4 font-mono text-xs text-[var(--text-muted)] w-[15%] truncate">
              {item.latency && (
                <span className={item.latency === 'TIMEOUT' || item.latency === 'REFUSED' ? 'text-[var(--color-red)] font-bold' : 'text-[var(--color-green)] font-semibold'}>
                  {item.latency}
                </span>
              )}
            </td>

            <td className="py-2 px-4 w-[20%] align-middle">
              <div className="flex flex-wrap gap-1.5 justify-start">
                {active > 0 && (
                  <button
                    onClick={(e) => { e.stopPropagation(); onStatusClick(item.id, 'active'); }}
                    className="inline-flex items-center gap-1.5 px-1.5 py-0.5 text-[9px] font-bold uppercase rounded bg-[var(--color-green)]/15 text-[var(--color-green)] border border-[var(--color-green)]/40 hover:border-[var(--color-green)] transition-all shrink-0"
                  >
                    <span className="w-1.5 h-1.5 rounded-sm bg-[var(--color-green)]" /> {active} Active
                  </button>
                )}
                {failed > 0 && (
                  <button
                    onClick={(e) => { e.stopPropagation(); onStatusClick(item.id, 'failed'); }}
                    className="inline-flex items-center gap-1.5 px-1.5 py-0.5 text-[9px] font-bold uppercase rounded bg-[var(--color-red)]/15 text-[var(--color-red)] border border-[var(--color-red)]/40 hover:border-[var(--color-red)] transition-all shrink-0"
                  >
                    <span className="w-1.5 h-1.5 rounded-sm bg-[var(--color-red)]" /> {failed} Failed
                  </button>
                )}
                {ghost > 0 && (
                  <button
                    onClick={(e) => { e.stopPropagation(); onStatusClick(item.id, 'ghost'); }}
                    className="inline-flex items-center gap-1.5 px-1.5 py-0.5 text-[9px] font-bold uppercase rounded bg-[var(--color-red)]/15 text-[var(--color-red)] border border-[var(--color-red)]/40 hover:border-[var(--color-red)] transition-all shrink-0"
                  >
                    <span className="w-1.5 h-1.5 rounded-sm bg-[var(--color-red)]" /> {ghost} Ghost
                  </button>
                )}
              </div>
            </td>
          </tr>

          {showInlineDetails && item.details && (
            <tr key={`${item.id}-inline-details`} className="bg-[var(--bg-header)]/80 border-b border-[var(--border-color)]">
              <td colSpan={5} className="py-3 px-6 max-w-0 overflow-hidden" style={{ paddingLeft: `${Math.min(depth, 8) * 16 + 36}px` }}>
                <div className="p-3 bg-[var(--bg-main)] rounded border border-[var(--border-color)] text-xs font-mono space-y-1.5 max-h-[300px] overflow-y-auto overflow-x-hidden max-w-full">
                  <div className="font-sans font-bold text-[var(--color-blue)] text-[11px] uppercase mb-1">
                    🔍 Detailed Inspection: {item.label}
                  </div>
                  {Object.keys(item.details).length === 0 ? (
                    <div className="text-[var(--text-dim)]">No extra diagnostic payloads recorded for this node.</div>
                  ) : (
                    Object.entries(item.details).map(([k, v]) => (
                      <div key={k} className="flex flex-col sm:flex-row sm:gap-2">
                        <span className="text-[var(--text-muted)] font-semibold w-36 shrink-0">{k}:</span>
                        <pre className="text-[var(--text-main)] bg-[var(--bg-surface)] p-2 rounded max-h-[200px] overflow-x-auto w-full scrollbar-thin">
                          {typeof v === 'object' ? JSON.stringify(v, null, 2) : String(v)}
                        </pre>
                      </div>
                    ))
                  )}
                </div>
              </td>
            </tr>
          )}

          {isExpanded && hasChildren && renderRows(item.children, depth + 1)}
        </React.Fragment>
      );
    });
  };

  const getSortIcon = (col) => {
     if (sortBy !== col) return <span className="text-[var(--text-dim)] opacity-0 group-hover:opacity-100 transition-opacity">↕</span>;
     return <span className="text-[var(--color-blue)]">{sortDir === 'asc' ? '⬆' : '⬇'}</span>;
  };

  return (
    <div className="w-full bg-[var(--bg-main)] flex flex-col h-full overflow-hidden">
      <div className="flex-1 overflow-auto">
        {data.length === 0 ? (
          <div className="p-12 text-center text-[var(--text-muted)] font-sans text-sm">
            {globalSearch ? `No targets matched the search '${globalSearch}'` : 'No matching targets or hosts found.'}
          </div>
        ) : (
          <table className="w-full text-left border-collapse table-fixed">
            <thead className="bg-[var(--bg-header)] text-[var(--text-muted)] text-[10px] font-sans font-bold uppercase sticky top-0 border-b border-[var(--border-color)] z-10 select-none">
              <tr>
                <th onClick={() => onSort('label')} className="py-2 px-4 w-[35%] cursor-pointer hover:bg-[var(--bg-elevated)] hover:text-[var(--text-main)] group transition-colors">
                  Resource Path <span className="ml-1 inline-block w-3">{getSortIcon('label')}</span>
                </th>
                <th onClick={() => onSort('type')} className="py-2 px-4 w-[15%] cursor-pointer hover:bg-[var(--bg-elevated)] hover:text-[var(--text-main)] group transition-colors">
                  Type <span className="ml-1 inline-block w-3">{getSortIcon('type')}</span>
                </th>
                <th onClick={() => onSort('tls')} className="py-2 px-4 w-[15%] cursor-pointer hover:bg-[var(--bg-elevated)] hover:text-[var(--text-main)] group transition-colors">
                  TLS Exp <span className="ml-1 inline-block w-3">{getSortIcon('tls')}</span>
                </th>
                <th onClick={() => onSort('latency')} className="py-2 px-4 w-[15%] cursor-pointer hover:bg-[var(--bg-elevated)] hover:text-[var(--text-main)] group transition-colors">
                  Latency <span className="ml-1 inline-block w-3">{getSortIcon('latency')}</span>
                </th>
                <th onClick={() => onSort('status')} className="py-2 px-4 w-[20%] cursor-pointer hover:bg-[var(--bg-elevated)] hover:text-[var(--text-main)] group transition-colors">
                  <span className="mr-1 inline-block w-3">{getSortIcon('status')}</span> Status
                </th>
              </tr>
            </thead>
            <tbody>{renderRows(data)}</tbody>
          </table>
        )}
      </div>
    </div>
  );
};

// --- SCHEDULED SCANS VIEW ---
const ScheduledScansView = () => {
    const [scans, setScans] = useState([
        { id: 1, name: 'Daily Perimeter Sweep', schedule: '0 0 * * *', flags: '--fast --no-tls', lastRun: '2 hours ago', nextRun: 'In 22 hours' },
        { id: 2, name: 'Weekly Deep Inspection', schedule: '0 2 * * 0', flags: '--deep --all-ports', lastRun: '4 days ago', nextRun: 'In 3 days' },
        { id: 3, name: 'Datacenter Heartbeat', schedule: '*/15 * * * *', flags: '--ping-only', lastRun: '10 mins ago', nextRun: 'In 5 mins' }
    ]);

    const [expandedScanId, setExpandedScanId] = useState(null);
    const [editingScanId, setEditingScanId] = useState(null);

    const handleDelete = (id) => {
        if (window.confirm("Are you sure you want to delete this scheduled scan?")) {
            setScans(scans.filter(s => s.id !== id));
            if (expandedScanId === id) setExpandedScanId(null);
            if (editingScanId === id) setEditingScanId(null);
        }
    };

    return (
        <div className="p-8 w-full h-full overflow-auto text-[var(--text-main)] font-sans bg-[var(--bg-main)]">
            <div className="flex items-center justify-between mb-8 max-w-5xl mx-auto">
                <div>
                    <h2 className="text-xl font-bold font-mono">Scheduled Scans</h2>
                    <p className="text-sm text-[var(--text-muted)] mt-1">Manage and monitor automated periodic checks.</p>
                </div>
                <button className="bg-[var(--color-blue)] text-white px-4 py-2 rounded font-bold text-xs shadow hover:bg-[var(--color-blue)]/80 transition-colors">
                    + Create New Schedule
                </button>
            </div>

            <div className="bg-[var(--bg-surface)] border border-[var(--border-color)] rounded-lg shadow-sm overflow-hidden max-w-5xl mx-auto">
                <table className="w-full text-left">
                    <thead className="bg-[var(--bg-header)] border-b border-[var(--border-color)] text-[10px] uppercase font-bold text-[var(--text-muted)]">
                        <tr>
                            <th className="px-6 py-4">Scan Name</th>
                            <th className="px-6 py-4">Cron Schedule</th>
                            <th className="px-6 py-4">Last Run</th>
                            <th className="px-6 py-4">Next Run</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-[var(--border-color)]">
                        {scans.map(scan => (
                            <React.Fragment key={scan.id}>
                                <tr 
                                  onClick={() => {
                                      setExpandedScanId(expandedScanId === scan.id ? null : scan.id);
                                      setEditingScanId(null);
                                  }}
                                  className="hover:bg-[var(--bg-elevated)] transition-colors cursor-pointer"
                                >
                                    <td className="px-6 py-5 font-semibold text-sm flex items-center gap-2">
                                        <svg
                                          className={`w-4 h-4 transform transition-transform text-[var(--text-muted)] duration-150 ${expandedScanId === scan.id ? 'rotate-90 text-[var(--text-main)]' : ''}`}
                                          fill="none" stroke="currentColor" viewBox="0 0 24 24"
                                        >
                                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" />
                                        </svg>
                                        {scan.name}
                                    </td>
                                    <td className="px-6 py-5 font-mono text-xs text-[var(--color-blue)] font-bold">{scan.schedule}</td>
                                    <td className="px-6 py-5 text-xs text-[var(--text-muted)]">{scan.lastRun}</td>
                                    <td className="px-6 py-5 text-xs font-semibold text-[var(--color-green)]">{scan.nextRun}</td>
                                </tr>
                                {expandedScanId === scan.id && (
                                    <tr className="bg-[var(--bg-header)]/50 border-b border-[var(--border-color)]">
                                        <td colSpan={4} className="px-10 py-6">
                                            {editingScanId === scan.id ? (
                                                <div className="space-y-4 max-w-2xl bg-[var(--bg-main)] p-4 rounded border border-[var(--border-color)]">
                                                    <div className="flex flex-col gap-1">
                                                        <label className="text-xs font-bold text-[var(--text-muted)] uppercase">Name</label>
                                                        <input type="text" defaultValue={scan.name} className="bg-[var(--bg-surface)] border border-[var(--border-color)] rounded px-3 py-1.5 text-sm text-[var(--text-main)] focus:border-[var(--color-blue)] outline-none" />
                                                    </div>
                                                    <div className="flex flex-col gap-1">
                                                        <label className="text-xs font-bold text-[var(--text-muted)] uppercase">Cron Schedule</label>
                                                        <input type="text" defaultValue={scan.schedule} className="bg-[var(--bg-surface)] border border-[var(--border-color)] rounded px-3 py-1.5 text-sm font-mono text-[var(--color-blue)] focus:border-[var(--color-blue)] outline-none" />
                                                    </div>
                                                    <div className="flex flex-col gap-1">
                                                        <label className="text-xs font-bold text-[var(--text-muted)] uppercase">Config Flags</label>
                                                        <input type="text" defaultValue={scan.flags} className="bg-[var(--bg-surface)] border border-[var(--border-color)] rounded px-3 py-1.5 text-sm font-mono text-[var(--text-main)] focus:border-[var(--color-blue)] outline-none" />
                                                    </div>
                                                    <div className="flex justify-end gap-2 pt-2 border-t border-[var(--border-color)]">
                                                        <button onClick={() => setEditingScanId(null)} className="px-4 py-1.5 rounded text-xs font-bold text-[var(--text-muted)] hover:text-[var(--text-main)] hover:bg-[var(--bg-elevated)] transition-colors">
                                                            Cancel
                                                        </button>
                                                        <button onClick={() => setEditingScanId(null)} className="px-4 py-1.5 rounded text-xs font-bold bg-[var(--color-blue)] text-white hover:bg-[var(--color-blue)]/80 transition-colors">
                                                            Save Changes
                                                        </button>
                                                    </div>
                                                </div>
                                            ) : (
                                                <div className="flex items-start justify-between">
                                                    <div className="space-y-3">
                                                        <div>
                                                            <div className="text-[10px] font-bold text-[var(--text-muted)] uppercase mb-1">Configuration Flags</div>
                                                            <code className="bg-[var(--bg-main)] px-2 py-1 rounded text-xs text-[var(--text-main)] font-mono border border-[var(--border-color)]">
                                                                {scan.flags}
                                                            </code>
                                                        </div>
                                                        <div>
                                                            <div className="text-[10px] font-bold text-[var(--text-muted)] uppercase mb-1">Last Log Output</div>
                                                            <div className="bg-[var(--bg-main)] px-3 py-2 rounded text-xs text-[var(--text-dim)] font-mono border border-[var(--border-color)] max-w-xl">
                                                                [INFO] Scanner initialized. Targeting {scan.flags}
                                                                <br/>[INFO] 12 targets discovered. No anomalies found.
                                                                <br/>[SUCCESS] Job completed in 1.42s
                                                            </div>
                                                        </div>
                                                    </div>
                                                    <div className="flex flex-col gap-2 shrink-0">
                                                        <button className="px-4 py-1.5 bg-[var(--bg-surface)] border border-[var(--color-blue)]/30 rounded text-xs font-bold text-[var(--color-blue)] hover:bg-[var(--color-blue)]/10 transition-colors shadow-sm">
                                                            ▶ Scan Now
                                                        </button>
                                                        <button onClick={() => setEditingScanId(scan.id)} className="px-4 py-1.5 bg-[var(--bg-surface)] border border-[var(--border-color)] rounded text-xs font-bold hover:text-[var(--color-yellow)] hover:border-[var(--color-yellow)] transition-colors">
                                                            ✎ Edit Schedule
                                                        </button>
                                                        <button onClick={() => handleDelete(scan.id)} className="px-4 py-1.5 bg-[var(--bg-surface)] border border-[var(--border-color)] rounded text-xs font-bold hover:text-[var(--color-red)] hover:border-[var(--color-red)] transition-colors">
                                                            ✕ Delete
                                                        </button>
                                                    </div>
                                                </div>
                                            )}
                                        </td>
                                    </tr>
                                )}
                            </React.Fragment>
                        ))}
                        {scans.length === 0 && (
                            <tr>
                                <td colSpan="4" className="px-6 py-12 text-center text-[var(--text-muted)]">No scheduled scans found.</td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

// --- MAIN APPLICATION COMPONENT ---
export default function App() {
  const [currentView, setCurrentView] = useState('table');
  const [isDarkMode, setIsDarkMode] = useState(false);
  
  const [treeData, setTreeData] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [rfInstance, setRfInstance] = useState(null);

  useEffect(() => {
    setIsLoading(true);
    fetch('/unicamp_mapping.json')
      .then(res => res.json())
      .then(data => {
        const parsedTree = generateTreeFromData(data);
        setTreeData(parsedTree);
        setIsLoading(false);
      })
      .catch(err => {
        console.error("Failed to load JSON mapping:", err);
        setIsLoading(false);
      });
  }, []);

  const toggleTheme = () => {
    setIsDarkMode((prev) => {
      const next = !prev;
      if (next) {
        document.documentElement.classList.remove('light');
        document.documentElement.classList.add('dark');
      } else {
        document.documentElement.classList.remove('dark');
        document.documentElement.classList.add('light');
      }
      return next;
    });
  };

  const [expandedNodes, setExpandedNodes] = useState({});
  
  const toggleNode = (nodeId, forceState = null) => {
    setExpandedNodes((prev) => {
      const nextState = forceState !== null ? forceState : !prev[nodeId];
      if (nextState === false) {
         const nextExpanded = { ...prev, [nodeId]: false };
         const turnOffDescendants = (items, foundMatch) => {
            items.forEach(item => {
               const isMatch = foundMatch || item.id === nodeId;
               if (isMatch && item.id !== nodeId) {
                   nextExpanded[item.id] = false;
               }
               if (item.children) turnOffDescendants(item.children, isMatch);
            });
         };
         turnOffDescendants(treeData, false);
         return nextExpanded;
      }
      return { ...prev, [nodeId]: true };
    });
  };

  const [inlineDetailNodes, setInlineDetailNodes] = useState({});
  const toggleInlineDetail = (nodeId) => {
    setInlineDetailNodes((prev) => ({ ...prev, [nodeId]: !prev[nodeId] }));
  };

  const [ghostWindowHours, setGhostWindowHours] = useState(24);
  const [globalSearch, setGlobalSearch] = useState('');
  const [searchInput, setSearchInput] = useState('');

  useEffect(() => {
    const handler = setTimeout(() => {
      setGlobalSearch(searchInput);
    }, 400);
    return () => clearTimeout(handler);
  }, [searchInput]);
  const [globalStatuses, setGlobalStatuses] = useState(['all']);
  const [explicitFilters, setExplicitFilters] = useState({});
  
  // Sorting State
  const [tableSortBy, setTableSortBy] = useState('none');
  const [tableSortDir, setTableSortDir] = useState('asc');
  const [topologySortBy, setTopologySortBy] = useState('none');
  const [topologySortDir, setTopologySortDir] = useState('asc');

  const handleSort = (column) => {
     if (tableSortBy === column) {
        if (tableSortDir === 'asc') setTableSortDir('desc');
        else {
           setTableSortBy('none');
           setTableSortDir('asc');
        }
     } else {
        setTableSortBy(column);
        setTableSortDir('asc');
     }
  };

  const handleClearNodeFilter = (nodeId) => {
      setExplicitFilters(prev => {
          const next = { ...prev };
          delete next[nodeId];
          return next;
      });
  };

  const handleStatusClick = (nodeId, statusKey) => {
    const newFilters = { search: '', statuses: [statusKey] };
    setExplicitFilters(prev => ({
      ...prev,
      [nodeId]: newFilters
    }));

    const idsToExpand = { [nodeId]: true };

    const traverseAndCollect = (items, parentMatches) => {
      let anyMatch = false;
      items.forEach(item => {
        const isTargetNode = item.id === nodeId;
        const isUnderTarget = parentMatches || isTargetNode;
        
        let childMatched = false;
        if (item.children && item.children.length > 0) {
           childMatched = traverseAndCollect(item.children, isUnderTarget);
        }

        if (isUnderTarget) {
          let matchesStatus = false;
          const itemStatus = item.status || 'slate';
          if (newFilters.statuses.includes('active') && (itemStatus === 'green' || itemStatus === 'amber')) matchesStatus = true;
          if (newFilters.statuses.includes('failed') && itemStatus === 'red') matchesStatus = true;
          if (newFilters.statuses.includes('ghost') && (item.type.includes('Ghost') || (item.lastSeenHoursAgo && item.lastSeenHoursAgo <= ghostWindowHours))) matchesStatus = true;
          if (newFilters.statuses.includes('void') && item.type.includes('Void')) matchesStatus = true;
          
          if (matchesStatus || childMatched) {
             idsToExpand[item.id] = true;
             anyMatch = true;
          }
        }
      });
      return anyMatch;
    };
    
    traverseAndCollect(treeData, false);
    
    setExpandedNodes(prev => ({ ...prev, ...idsToExpand }));
  };

  const toggleGlobalStatusFilter = (status) => {
    setActiveViewId('custom');
    let next = [];
    if (status === 'all') {
      next = ['all'];
    } else {
      next = globalStatuses.filter((s) => s !== 'all');
      if (next.includes(status)) {
        next = next.filter((s) => s !== status);
      } else {
        next.push(status);
      }
      if (next.length === 0 || next.length === 4) {
        next = ['all'];
      }
    }
    setGlobalStatuses(next);
  };

  const [savedViews, setSavedViews] = useState([
    { id: 'view-default', name: 'Default View (All Targets)', search: '', statuses: ['all'], tableSortBy: 'none', tableSortDir: 'asc' },
    { id: 'view-ghosts', name: 'Critical Outages & Ghosts', search: '', statuses: ['ghost', 'failed'], tableSortBy: 'status', tableSortDir: 'desc' },
    { id: 'view-active-ghost', name: 'Active & Ghost Outages', search: '', statuses: ['active', 'ghost'], tableSortBy: 'none', tableSortDir: 'asc' },
    { id: 'view-datacenter', name: 'Datacenter Core Infrastructure', search: 'datacenter_core', statuses: ['all'], tableSortBy: 'none', tableSortDir: 'asc' }
  ]);
  const [activeViewId, setActiveViewId] = useState('view-default');
  const [isSavingView, setIsSavingView] = useState(false);
  const [newViewName, setNewViewName] = useState('');

  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const viewId = urlParams.get('view');
    if (viewId) {
      fetch(`/api/views/${viewId}`)
        .then(res => {
          if (res.ok) return res.json();
          throw new Error('View not found');
        })
        .then(data => {
          const id = data.id;
          setSavedViews(prev => {
            if (!prev.find(v => v.id === id)) {
               return [...prev, { id, name: `🔗 ${data.name}`, search: data.search || '', statuses: data.statuses || ['all'], tableSortBy: data.table_sort_by || 'none', tableSortDir: data.table_sort_dir || 'asc' }];
            }
            return prev;
          });
          setActiveViewId(id);
          setGlobalSearch(data.search || '');
          setGlobalStatuses(data.statuses || ['all']);
          setTableSortBy(data.table_sort_by || 'none');
          setTableSortDir(data.table_sort_dir || 'asc');
        })
        .catch(err => {
          console.error("Failed to load view from URL:", err);
        });
    }
  }, []);

  const handleSelectSavedView = (viewId) => {
    setActiveViewId(viewId);
    if (viewId === 'custom-new') {
      setIsSavingView(true);
      return;
    }
    const view = savedViews.find((v) => v.id === viewId);
    if (view) {
      setGlobalSearch(view.search);
      setGlobalStatuses(view.statuses || ['all']);
      setTableSortBy(view.tableSortBy || 'none');
      setTableSortDir(view.tableSortDir || 'asc');
      setExplicitFilters({});

      const newUrl = new URL(window.location);
      if (!viewId.startsWith('view-') && viewId !== 'custom' && viewId !== 'custom-new') {
         newUrl.searchParams.set('view', viewId);
      } else {
         newUrl.searchParams.delete('view');
      }
      window.history.pushState({}, '', newUrl);
    }
  };
  
  const handleDeleteView = () => {
     if (activeViewId && !activeViewId.startsWith('view-') && activeViewId !== 'custom' && activeViewId !== 'custom-new') {
        setSavedViews(prev => prev.filter(v => v.id !== activeViewId));
        handleSelectSavedView('view-default');
     }
  };
  
  const handleSaveViewSubmit = async () => {
    if (newViewName.trim()) {
      try {
        const payload = {
          name: newViewName.trim(),
          search: globalSearch,
          statuses: globalStatuses,
          table_sort_by: tableSortBy,
          table_sort_dir: tableSortDir
        };
        const response = await fetch('/api/views', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        
        if (response.ok) {
          const data = await response.json();
          const id = data.id;
          setSavedViews((prev) => [...prev, { id, name: `⭐ ${data.name}`, search: data.search, statuses: data.statuses, tableSortBy: data.table_sort_by, tableSortDir: data.table_sort_dir }]);
          setActiveViewId(id);
          
          const newUrl = new URL(window.location);
          newUrl.searchParams.set('view', id);
          window.history.pushState({}, '', newUrl);
        } else {
          console.error("Failed to save view via API, falling back to local storage");
          const id = `view-${Date.now()}`;
          setSavedViews((prev) => [...prev, { id, name: `⭐ ${newViewName.trim()}`, search: globalSearch, statuses: globalStatuses, tableSortBy, tableSortDir }]);
          setActiveViewId(id);
        }
      } catch (err) {
        console.error(err);
        const id = `view-${Date.now()}`;
        setSavedViews((prev) => [...prev, { id, name: `⭐ ${newViewName.trim()}`, search: globalSearch, statuses: globalStatuses, tableSortBy, tableSortDir }]);
        setActiveViewId(id);
      }
    }
    setIsSavingView(false);
    setNewViewName('');
  };

  const filteredData = useMemo(() => {
    const parentFilter = { search: globalSearch, statuses: globalStatuses };
    
    const clonedTree = JSON.parse(JSON.stringify(treeData));
    clonedTree.forEach(node => propagateStats(node, ghostWindowHours));

    let filtered = filterTree(clonedTree, parentFilter, explicitFilters, ghostWindowHours);
    filtered = filtered.map(compressNode);
    
    if (currentView === 'table') {
      return sortTree(filtered, tableSortBy, tableSortDir);
    } else {
      return sortTree(filtered, topologySortBy, topologySortDir);
    }
  }, [treeData, globalSearch, globalStatuses, explicitFilters, ghostWindowHours, tableSortBy, tableSortDir, topologySortBy, topologySortDir, currentView]);

  const handleExpandAll = () => {
    const next = { ...expandedNodes };
    const traverse = (items) => {
      items.forEach(item => {
        if (item.children && item.children.length > 0) {
          next[item.id] = true;
          traverse(item.children);
        }
      });
    };
    traverse(filteredData);
    setExpandedNodes(next);
  };

  const handleCollapseAll = () => {
    setExpandedNodes({});
  };

  // Auto-expand paths when searching
  useEffect(() => {
    if (globalSearch.trim() && treeData.length > 0) {
      const newExpanded = { ...expandedNodes };
      let anyNew = false;

      const traverse = (items) => {
        let hasMatch = false;
        items.forEach(item => {
           let childMatch = false;
           if (item.children) {
              childMatch = traverse(item.children);
           }
           
           const searchableText = `${item.label} ${item.subLabel || ''} ${item.type} ${JSON.stringify(item.details || {})} ${(item.classifications || []).join(' ')}`.toLowerCase();
           let matches = false;
           try {
             const regex = new RegExp(globalSearch.trim(), 'i');
             matches = regex.test(searchableText);
           } catch {
             matches = searchableText.includes(globalSearch.trim().toLowerCase());
           }

           if (matches || childMatch) {
              if (!newExpanded[item.id]) {
                 newExpanded[item.id] = true;
                 anyNew = true;
              }
              hasMatch = true;
           }
        });
        return hasMatch;
      };
      
      traverse(treeData);
      if (anyNew) {
         setExpandedNodes(newExpanded);
      }
    }
  }, [globalSearch, treeData]);

  const { flowNodes, flowEdges } = useMemo(() => {
    return computeAutoLayout(filteredData, expandedNodes, inlineDetailNodes, toggleNode, toggleInlineDetail, handleStatusClick, handleClearNodeFilter);
  }, [filteredData, expandedNodes, inlineDetailNodes]);

  const [nodes, setNodes, onNodesChange] = useNodesState(flowNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(flowEdges);

  useEffect(() => {
    setNodes(flowNodes);
    setEdges(flowEdges);
  }, [flowNodes, flowEdges]);

  useEffect(() => {
    document.documentElement.classList.remove('dark');
    document.documentElement.classList.add('light');
  }, []);

  if (isLoading) {
    return (
      <div className="w-screen h-screen flex flex-col items-center justify-center bg-[var(--bg-main)] text-[var(--text-main)] font-mono text-sm">
        <div className="w-6 h-6 border-2 border-[var(--color-blue)] border-t-transparent rounded-full animate-spin mb-4" />
        Ingesting network maps...
      </div>
    );
  }

  return (
    <div className="w-screen h-screen flex flex-col bg-[var(--bg-main)] text-[var(--text-main)] font-sans overflow-hidden transition-colors duration-150 relative">
      <header className="h-14 bg-[var(--bg-header)] border-b border-[var(--border-color)] px-6 flex items-center justify-between z-30 shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-7 h-7 rounded bg-[var(--color-blue)] text-white flex items-center justify-center font-bold text-xs font-mono">
            SH
          </div>
          <h1 className="font-bold text-sm tracking-wide text-[var(--text-main)] font-mono flex items-center gap-2">
            Site Health Check
            <span className="text-xs px-2 py-0.5 bg-[var(--bg-surface)] text-[var(--text-muted)] rounded font-normal font-sans border border-[var(--border-color)]">
              Control Plane
            </span>
          </h1>

          <div className="h-4 w-px bg-[var(--border-color)] mx-1" />

          <div className="flex items-center gap-1.5 text-xs text-[var(--color-green)] font-mono font-semibold">
            <span className="w-2.5 h-2.5 rounded-full bg-[var(--color-green)]" />
            {treeData.length > 0 ? `${treeData.length} Target CIDR${treeData.length > 1 ? 's' : ''} Loaded` : 'No data'}
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="flex items-center bg-[var(--bg-main)] p-1 rounded border border-[var(--border-color)]">
            <button
              onClick={() => setCurrentView('table')}
              className={`px-3 py-1 rounded text-xs font-mono font-semibold transition-all ${
                currentView === 'table' ? 'bg-[var(--bg-elevated)] text-[var(--text-main)] shadow-sm' : 'text-[var(--text-muted)] hover:text-[var(--text-main)]'
              }`}
            >
              Table
            </button>
            <button
              onClick={() => setCurrentView('topology')}
              className={`px-3 py-1 rounded text-xs font-mono font-semibold transition-all ${
                currentView === 'topology' ? 'bg-[var(--bg-elevated)] text-[var(--text-main)] shadow-sm' : 'text-[var(--text-muted)] hover:text-[var(--text-main)]'
              }`}
            >
              Topology
            </button>
            <button
              onClick={() => setCurrentView('scans')}
              className={`px-3 py-1 rounded text-xs font-mono font-semibold transition-all ${
                currentView === 'scans' ? 'bg-[var(--bg-elevated)] text-[var(--color-blue)] shadow-sm' : 'text-[var(--text-muted)] hover:text-[var(--text-main)]'
              }`}
            >
              ⏱️ Scheduled Scans
            </button>
          </div>

          <div className="h-4 w-px bg-[var(--border-color)] mx-1" />

          <button
            onClick={toggleTheme}
            className="flex items-center gap-1.5 px-3 py-1 text-xs font-mono font-semibold rounded bg-[var(--bg-surface)] hover:bg-[var(--bg-elevated)] text-[var(--text-main)] transition-colors border border-[var(--border-color)]"
          >
            {isDarkMode ? '🌙 Dark' : '☀️ Light'}
          </button>
        </div>
      </header>

      {currentView !== 'scans' && (
        <div className="min-h-[44px] h-auto py-1.5 bg-[var(--bg-header)]/90 border-b border-[var(--border-color)] px-6 flex items-center justify-between overflow-x-auto scrollbar-none whitespace-nowrap text-xs gap-y-2 gap-x-4 z-20 font-sans shrink-0">
          <div className="flex items-center gap-4 shrink-0">
            {isSavingView ? (
              <div className="flex items-center gap-2">
                <span className="text-[var(--text-muted)] font-semibold">Save View:</span>
                <input
                  type="text"
                  placeholder="View name..."
                  autoFocus
                  value={newViewName}
                  onChange={(e) => setNewViewName(e.target.value)}
                  className="bg-[var(--bg-main)] text-[var(--color-blue)] border border-[var(--border-color)] rounded px-3 py-1 text-xs font-mono font-semibold focus:outline-none focus:border-[var(--color-blue)] w-48"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleSaveViewSubmit();
                    if (e.key === 'Escape') setIsSavingView(false);
                  }}
                />
                <button onClick={handleSaveViewSubmit} className="bg-[var(--color-blue)] text-white px-2 py-1 rounded text-xs hover:bg-[var(--color-blue)]/80">✓ Save</button>
                <button onClick={() => {setIsSavingView(false); setActiveViewId('view-default');}} className="bg-[var(--bg-elevated)] text-[var(--text-main)] px-2 py-1 rounded text-xs border border-[var(--border-color)]">✕ Cancel</button>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <span className="text-[var(--text-muted)] font-semibold">Global View:</span>
                <div className="flex items-center">
                  <select
                    value={activeViewId}
                    onChange={(e) => handleSelectSavedView(e.target.value)}
                    className="bg-[var(--bg-main)] text-[var(--color-blue)] border border-[var(--border-color)] rounded-l px-3 py-1 text-xs font-mono font-semibold focus:outline-none focus:border-[var(--color-blue)] cursor-pointer"
                  >
                    {savedViews.map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.name}
                      </option>
                    ))}
                    <option disabled>──────────</option>
                    <option value="custom-new">➕ Save current view...</option>
                  </select>
                  {activeViewId && !activeViewId.startsWith('view-') && activeViewId !== 'custom' && activeViewId !== 'custom-new' && (
                    <button
                      onClick={handleDeleteView}
                      className="bg-[var(--bg-elevated)] text-[#ef4444] hover:bg-[#ef4444] hover:text-white border border-l-0 border-[var(--border-color)] rounded-r px-2 py-1 text-xs font-bold transition-colors"
                      title="Delete this view"
                    >
                      ✕
                    </button>
                  )}
                </div>
              </div>
            )}

            <div className="h-4 w-px bg-[var(--border-color)] mx-1 hidden sm:block" />

            <div className="flex items-center gap-1">
              <button 
                onClick={handleExpandAll}
                className="bg-[var(--bg-main)] text-[var(--text-main)] border border-[var(--border-color)] rounded px-2 py-1 text-xs font-mono font-semibold focus:outline-none hover:border-[var(--color-blue)] cursor-pointer"
                title="Expand All"
              >
                +
              </button>
              <button 
                onClick={handleCollapseAll}
                className="bg-[var(--bg-main)] text-[var(--text-main)] border border-[var(--border-color)] rounded px-2 py-1 text-xs font-mono font-semibold focus:outline-none hover:border-[var(--color-blue)] cursor-pointer"
                title="Collapse All"
              >
                -
              </button>
            </div>

            <div className="h-4 w-px bg-[var(--border-color)] mx-1 hidden sm:block" />

            <div className="flex items-center gap-2">
              <input
                type="text"
                placeholder="Search /regex/, IP, port, host..."
                value={searchInput}
                onChange={(e) => {
                  setSearchInput(e.target.value);
                  setActiveViewId('custom');
                }}
                className="bg-[var(--bg-main)] text-[var(--text-main)] border border-[var(--border-color)] rounded px-3 py-1.5 text-xs font-mono focus:outline-none focus:border-[var(--color-blue)] w-64 shadow-inner"
              />
              {searchInput && (
                <button onClick={() => { setSearchInput(''); setGlobalSearch(''); }} className="text-[var(--text-muted)] hover:text-[var(--text-main)]">
                  ✕
                </button>
              )}
            </div>

            <div className="h-4 w-px bg-[var(--border-color)] mx-1 hidden md:block" />

            <div className="flex items-center gap-1.5">
              <span className="text-[var(--text-muted)] font-semibold font-mono text-[11px]">Ghost Window:</span>
              <select
                value={ghostWindowHours}
                onChange={(e) => setGhostWindowHours(Number(e.target.value))}
                className="bg-[var(--bg-main)] text-[var(--text-main)] border border-[var(--border-color)] rounded px-2 py-1 text-xs font-mono focus:outline-none focus:border-[var(--color-blue)] cursor-pointer"
              >
                <option value={12}>12 Hours</option>
                <option value={24}>24 Hours</option>
                <option value={72}>72 Hours</option>
                <option value={168}>7 Days</option>
                <option value={336}>14 Days</option>
              </select>
            </div>
          </div>

          <div className="flex items-center gap-4 font-sans shrink-0 max-w-full overflow-x-auto scrollbar-none">
            <div className="flex items-center gap-1 bg-[var(--bg-main)] p-0.5 rounded border border-[var(--border-color)] text-xs shrink-0 whitespace-nowrap">
              <button
                onClick={() => toggleGlobalStatusFilter('all')}
                className={`px-2.5 py-1 rounded uppercase font-semibold transition-colors ${
                  globalStatuses.includes('all') ? 'bg-[var(--bg-elevated)] text-[var(--color-blue)]' : 'text-[var(--text-muted)] hover:text-[var(--text-main)]'
                }`}
              >
                All
              </button>
              {['active', 'failed', 'ghost', 'void'].map((st) => {
                const isSelected = globalStatuses.includes(st) && !globalStatuses.includes('all');
                return (
                  <button
                    key={st}
                    onClick={() => toggleGlobalStatusFilter(st)}
                    className={`px-2.5 py-1 rounded capitalize font-semibold transition-colors ${
                      isSelected
                        ? 'bg-[var(--bg-elevated)] text-[var(--color-blue)] border border-[var(--color-blue)]/50'
                        : 'text-[var(--text-muted)] hover:text-[var(--text-main)]'
                    }`}
                  >
                    {isSelected ? `✓ ${st}` : st}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      )}

      <div className="flex-1 w-full h-full relative overflow-hidden bg-[var(--bg-main)]">
        {currentView === 'scans' ? (
          <ScheduledScansView />
        ) : currentView === 'table' ? (
          <HierarchicalTable
            data={filteredData}
            expandedNodes={expandedNodes}
            inlineDetailNodes={inlineDetailNodes}
            onToggleNode={toggleNode}
            onToggleInlineDetail={toggleInlineDetail}
            onStatusClick={handleStatusClick}
            onClearNodeFilter={handleClearNodeFilter}
            sortBy={tableSortBy}
            sortDir={tableSortDir}
            onSort={handleSort}
            globalSearch={globalSearch}
          />
        ) : (
          <div className="w-full h-full absolute inset-0">
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              nodeTypes={nodeTypes}
              onInit={setRfInstance}
              fitView
              className="w-full h-full bg-[var(--bg-main)]"
              proOptions={{ hideAttribution: true }}
            >
              <Background variant="lines" gap={24} size={1} color="var(--grid-line)" />
              <Controls className="!bg-[var(--bg-surface)] !border-[var(--border-color)]" />
              <MiniMap className="!bg-[var(--bg-surface)] !border-[var(--border-color)]" maskColor="rgba(11, 15, 23, 0.7)" />
            </ReactFlow>

            <div className="absolute bottom-6 left-16 flex items-center gap-2 z-10 shadow-lg">
              <button
                onClick={() => {
                  if (rfInstance) {
                    rfInstance.fitView({ duration: 800, padding: 0.1 });
                  }
                }}
                className="flex items-center gap-2 px-4 py-2 text-xs font-mono font-bold rounded bg-[var(--bg-elevated)] hover:bg-[var(--bg-surface)] text-[var(--color-blue)] transition-colors border border-[var(--border-color)] hover:border-[var(--color-blue)]"
              >
                🔍 Center Graph
              </button>
              
              {/* Topology Inline Sort Dropdown */}
              <div className="flex items-center gap-1.5 px-3 py-2 bg-[var(--bg-elevated)] border border-[var(--border-color)] rounded shadow-sm">
                <span className="text-[10px] uppercase font-bold text-[var(--text-muted)]">Sort:</span>
                <select
                  value={topologySortBy}
                  onChange={(e) => {
                     if (e.target.value === 'none') {
                        setTopologySortBy('none');
                     } else {
                        setTopologySortBy(e.target.value);
                        setTopologySortDir('asc');
                     }
                  }}
                  className="bg-transparent text-[var(--text-main)] text-xs font-mono focus:outline-none cursor-pointer"
                >
                  <option value="none">Default</option>
                  <option value="latency">Latency</option>
                  <option value="tls">TLS Expiry</option>
                  <option value="status">Status</option>
                </select>
                <button
                  onClick={() => setTopologySortDir(d => d === 'asc' ? 'desc' : 'asc')}
                  disabled={topologySortBy === 'none'}
                  className="px-1 text-xs font-bold text-[var(--color-blue)] hover:text-[var(--text-main)] transition-colors disabled:opacity-50"
                >
                  {topologySortDir === 'asc' ? '⬆' : '⬇'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* FLOATING CLEAR ALL NODE FILTERS BUTTON */}
        {Object.keys(explicitFilters).length > 0 && currentView !== 'scans' && (
          <div className="absolute bottom-6 left-6 z-20">
            <button 
              onClick={() => setExplicitFilters({})} 
              className="flex items-center gap-2 px-4 py-2 rounded shadow-md bg-[var(--bg-surface)] text-[var(--text-main)] border border-[var(--border-color)] hover:bg-[var(--bg-elevated)] transition-all text-xs font-bold uppercase tracking-wider"
            >
              ✕ Clear All Node Filters
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
