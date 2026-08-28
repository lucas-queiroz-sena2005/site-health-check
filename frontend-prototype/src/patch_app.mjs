import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const appPath = path.join(__dirname, 'App.jsx');

let content = fs.readFileSync(appPath, 'utf8');

// 1. propagateStats ghostWindowHours param & memo move
content = content.replace(
    'function propagateStats(node) {',
    'function propagateStats(node, ghostWindowHours) {'
);
content = content.replace(
    "const isGhost = node.type.includes('Ghost');",
    "const isGhost = node.type.includes('Ghost') || (node.lastSeenHoursAgo && node.lastSeenHoursAgo <= ghostWindowHours);"
);
content = content.replace(
    'const childStats = propagateStats(child);',
    'const childStats = propagateStats(child, ghostWindowHours);'
);
content = content.replace(
    'compressedTree.forEach(propagateStats);\n  return compressedTree;',
    'return compressedTree;'
);

// 2. handleStatusClick rewrite
const old_handle_click = `  const handleStatusClick = (nodeId, statusKey) => {
    const newFilters = { search: '', statuses: [statusKey] };
    setExplicitFilters(prev => ({
      ...prev,
      [nodeId]: newFilters
    }));

    const idsToExpand = { [nodeId]: true };

    const traverseAndCollect = (items, parentMatches) => {
      items.forEach(item => {
        const isTargetNode = item.id === nodeId;
        const isUnderTarget = parentMatches || isTargetNode;
        
        let shouldExpand = false;
        if (isUnderTarget) {
          let matchesStatus = false;
          const itemStatus = item.status || 'slate';
          if (newFilters.statuses.includes('active') && (itemStatus === 'green' || itemStatus === 'amber')) matchesStatus = true;
          if (newFilters.statuses.includes('failed') && itemStatus === 'red') matchesStatus = true;
          if (newFilters.statuses.includes('ghost') && (item.type.includes('Ghost') || (item.lastSeenHoursAgo && item.lastSeenHoursAgo <= ghostWindowHours))) matchesStatus = true;
          if (newFilters.statuses.includes('void') && item.type.includes('Void')) matchesStatus = true;
          
          if (matchesStatus || (item.children && item.children.length > 0)) {
             idsToExpand[item.id] = true;
             shouldExpand = true;
          }
        }
        
        if (item.children) {
          traverseAndCollect(item.children, isUnderTarget && shouldExpand);
        }
      });
    };
    
    traverseAndCollect(treeData, false);
    
    setExpandedNodes(prev => ({ ...prev, ...idsToExpand }));
  };`;

const new_handle_click = `  const handleStatusClick = (nodeId, statusKey) => {
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
  };`;
content = content.replace(old_handle_click, new_handle_click);

// 3. Void badge - remove onClick
content = content.replace(
`            {vCount > 0 && (
              <button
                onClick={(e) => { e.stopPropagation(); data.onStatusClick(data.id, 'void'); }}
                className="flex items-center gap-1.5 px-1.5 py-0.5 rounded bg-[var(--bg-elevated)] text-[var(--text-dim)] border border-[var(--border-color)] hover:text-[var(--text-main)] transition-all text-[9px] font-bold uppercase"
              >
                <span className="w-1.5 h-1.5 rounded-sm bg-[var(--text-dim)]" /> {vCount} Void
              </button>
            )}`,
`            {vCount > 0 && (
              <span
                title="Void Space IPs have no scan history"
                className="flex items-center gap-1.5 px-1.5 py-0.5 rounded bg-[var(--bg-elevated)] text-[var(--text-dim)] border border-[var(--border-color)] cursor-default text-[9px] font-bold uppercase"
              >
                <span className="w-1.5 h-1.5 rounded-sm bg-[var(--text-dim)]" /> {vCount} Void
              </span>
            )}`
);
content = content.replace(
`                {vCount > 0 && (
                  <button
                    onClick={(e) => { e.stopPropagation(); onStatusClick(item.id, 'void'); }}
                    className="inline-flex items-center gap-1.5 px-1.5 py-0.5 text-[9px] font-bold uppercase rounded bg-[var(--bg-elevated)] text-[var(--text-dim)] border border-[var(--border-color)] hover:text-[var(--text-main)] transition-all shrink-0"
                  >
                    <span className="w-1.5 h-1.5 rounded-sm bg-[var(--text-dim)]" /> {vCount} Void
                  </button>
                )}`,
`                {vCount > 0 && (
                  <span
                    title="Void Space IPs have no scan history"
                    className="inline-flex items-center gap-1.5 px-1.5 py-0.5 text-[9px] font-bold uppercase rounded bg-[var(--bg-elevated)] text-[var(--text-dim)] border border-[var(--border-color)] cursor-default shrink-0"
                  >
                    <span className="w-1.5 h-1.5 rounded-sm bg-[var(--text-dim)]" /> {vCount} Void
                  </span>
                )}`
);

// 4. Header CIDR count
content = content.replace(
    "{treeData.length > 0 ? `${Object.keys(treeData[0]?.pools || {}).length || 0} Target CIDRs Active` : 'Scanner active'}",
    "{treeData.length > 0 ? `${treeData.length} Target CIDR${treeData.length > 1 ? 's' : ''} Loaded` : 'No data'}"
);

// 5. Saved views replace window.prompt
content = content.replace(/const \[activeViewId, setActiveViewId\] = useState\('view-default'\);/, "const [activeViewId, setActiveViewId] = useState('view-default');\n  const [isSavingView, setIsSavingView] = useState(false);\n  const [newViewName, setNewViewName] = useState('');");
content = content.replace(/sortBy:\s*'none'/g, "tableSortBy: 'none'");
content = content.replace(/sortBy:\s*'status'/g, "tableSortBy: 'status'");
content = content.replace(/sortDir:\s*'asc'/g, "tableSortDir: 'asc'");
content = content.replace(/sortDir:\s*'desc'/g, "tableSortDir: 'desc'");

const old_handle_select = `  const handleSelectSavedView = (viewId) => {
    setActiveViewId(viewId);
    if (viewId === 'custom-new') {
      const name = prompt('Name for custom saved view:');
      if (name) {
        const id = \`view-\${Date.now()}\`;
        setSavedViews((prev) => [...prev, { id, name: \`⭐ \${name}\`, search: globalSearch, statuses: globalStatuses, sortBy, sortDir }]);
        setActiveViewId(id);
      }
      return;
    }
    const view = savedViews.find((v) => v.id === viewId);
    if (view) {
      setGlobalSearch(view.search);
      setGlobalStatuses(view.statuses || ['all']);
      setSortBy(view.sortBy || 'none');
      setSortDir(view.sortDir || 'asc');
      setExplicitFilters({});
    }
  };`;
const new_handle_select = `  const handleSelectSavedView = (viewId) => {
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
    }
  };
  
  const handleSaveViewSubmit = () => {
    if (newViewName.trim()) {
      const id = \`view-\${Date.now()}\`;
      setSavedViews((prev) => [...prev, { id, name: \`⭐ \${newViewName.trim()}\`, search: globalSearch, statuses: globalStatuses, tableSortBy, tableSortDir }]);
      setActiveViewId(id);
    }
    setIsSavingView(false);
    setNewViewName('');
  };`;
content = content.replace(old_handle_select, new_handle_select);

// Toolbar Ghost & flex-wrap & View save
const old_toolbar = `      {currentView !== 'scans' && (
        <div className="h-11 bg-[var(--bg-header)]/90 border-b border-[var(--border-color)] px-6 flex items-center justify-between text-xs gap-4 z-20 font-sans shrink-0">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <span className="text-[var(--text-muted)] font-semibold">Global View:</span>
              <select
                value={activeViewId}
                onChange={(e) => handleSelectSavedView(e.target.value)}
                className="bg-[var(--bg-main)] text-[var(--color-blue)] border border-[var(--border-color)] rounded px-3 py-1 text-xs font-mono font-semibold focus:outline-none focus:border-[var(--color-blue)] cursor-pointer"
              >
                {savedViews.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.name}
                  </option>
                ))}
                <option disabled>──────────</option>
                <option value="custom-new">➕ Save current view...</option>
              </select>
            </div>

            <div className="h-4 w-px bg-[var(--border-color)] mx-1" />

            <div className="flex items-center gap-2">
              <input
                type="text"
                placeholder="Search /regex/, IP, port, host..."
                value={globalSearch}
                onChange={(e) => {
                  setGlobalSearch(e.target.value);
                  setActiveViewId('custom');
                }}
                className="bg-[var(--bg-main)] text-[var(--text-main)] border border-[var(--border-color)] rounded px-3 py-1.5 text-xs font-mono focus:outline-none focus:border-[var(--color-blue)] w-64 shadow-inner"
              />
              {globalSearch && (
                <button onClick={() => setGlobalSearch('')} className="text-[var(--text-muted)] hover:text-[var(--text-main)]">
                  ✕
                </button>
              )}
            </div>
          </div>

          <div className="flex items-center gap-4 font-sans shrink-0">
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

            <div className="h-4 w-px bg-[var(--border-color)] mx-1" />

            <div className="flex items-center gap-1 bg-[var(--bg-main)] p-0.5 rounded border border-[var(--border-color)] text-xs shrink-0 whitespace-nowrap">`;
const new_toolbar = `      {currentView !== 'scans' && (
        <div className="min-h-[44px] h-auto py-1.5 bg-[var(--bg-header)]/90 border-b border-[var(--border-color)] px-6 flex items-center justify-between flex-wrap text-xs gap-y-2 gap-x-4 z-20 font-sans shrink-0">
          <div className="flex items-center gap-4 flex-wrap">
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
                <select
                  value={activeViewId}
                  onChange={(e) => handleSelectSavedView(e.target.value)}
                  className="bg-[var(--bg-main)] text-[var(--color-blue)] border border-[var(--border-color)] rounded px-3 py-1 text-xs font-mono font-semibold focus:outline-none focus:border-[var(--color-blue)] cursor-pointer"
                >
                  {savedViews.map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.name}
                    </option>
                  ))}
                  <option disabled>──────────</option>
                  <option value="custom-new">➕ Save current view...</option>
                </select>
              </div>
            )}

            <div className="h-4 w-px bg-[var(--border-color)] mx-1 hidden sm:block" />

            <div className="flex items-center gap-2">
              <input
                type="text"
                placeholder="Search /regex/, IP, port, host..."
                value={globalSearch}
                onChange={(e) => {
                  setGlobalSearch(e.target.value);
                  setActiveViewId('custom');
                }}
                className="bg-[var(--bg-main)] text-[var(--text-main)] border border-[var(--border-color)] rounded px-3 py-1.5 text-xs font-mono focus:outline-none focus:border-[var(--color-blue)] w-64 shadow-inner"
              />
              {globalSearch && (
                <button onClick={() => setGlobalSearch('')} className="text-[var(--text-muted)] hover:text-[var(--text-main)]">
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
            <div className="flex items-center gap-1 bg-[var(--bg-main)] p-0.5 rounded border border-[var(--border-color)] text-xs shrink-0 whitespace-nowrap">`;
content = content.replace(old_toolbar, new_toolbar);

// 6. Sorting
const old_sort_state = `  // Sorting State
  const [sortBy, setSortBy] = useState('none');
  const [sortDir, setSortDir] = useState('asc');

  const handleSort = (column) => {
     if (sortBy === column) {
        if (sortDir === 'asc') setSortDir('desc');
        else {
           setSortBy('none');
           setSortDir('asc');
        }
     } else {
        setSortBy(column);
        setSortDir('asc');
     }
  };`;
const new_sort_state = `  // Sorting State
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
  };`;
content = content.replace(old_sort_state, new_sort_state);

// 6.1 propagateStats in memo & Sort fixes
const old_filtered_memo = `  const filteredData = useMemo(() => {
    const parentFilter = { search: globalSearch, statuses: globalStatuses };
    const filtered = filterTree(treeData, parentFilter, explicitFilters, ghostWindowHours);
    return sortTree(filtered, sortBy, sortDir);
  }, [treeData, globalSearch, globalStatuses, explicitFilters, ghostWindowHours, sortBy, sortDir]);`;

const new_filtered_memo = `  const filteredData = useMemo(() => {
    const parentFilter = { search: globalSearch, statuses: globalStatuses };
    const filtered = filterTree(treeData, parentFilter, explicitFilters, ghostWindowHours);
    const cloned = JSON.parse(JSON.stringify(filtered));
    cloned.forEach(node => propagateStats(node, ghostWindowHours));
    
    if (currentView === 'table') {
      return sortTree(cloned, tableSortBy, tableSortDir);
    } else {
      return sortTree(cloned, topologySortBy, topologySortDir);
    }
  }, [treeData, globalSearch, globalStatuses, explicitFilters, ghostWindowHours, tableSortBy, tableSortDir, topologySortBy, topologySortDir, currentView]);`;
content = content.replace(old_filtered_memo, new_filtered_memo);

// 6.2 Sort dropdowns in HierarchicalTable & Topology
content = content.replace(/sortBy=\{sortBy\}/g, 'sortBy={tableSortBy}');
content = content.replace(/sortDir=\{sortDir\}/g, 'sortDir={tableSortDir}');
content = content.replace(
`                <select
                  value={sortBy}
                  onChange={(e) => {
                     if (e.target.value === 'none') {
                        setSortBy('none');
                     } else {
                        setSortBy(e.target.value);
                        setSortDir('asc');
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
                  onClick={() => setSortDir(d => d === 'asc' ? 'desc' : 'asc')}
                  disabled={sortBy === 'none'}
                  className="px-1 text-xs font-bold text-[var(--color-blue)] hover:text-[var(--text-main)] transition-colors disabled:opacity-50"
                >
                  {sortDir === 'asc' ? '⬆' : '⬇'}
                </button>`,
`                <select
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
                </button>`
);

// 7. Table padding cap & table-auto
content = content.replace(
`          <table className="w-full text-left border-collapse table-fixed">
            <thead className="bg-[var(--bg-header)] text-[var(--text-muted)] text-[10px] font-sans font-bold uppercase sticky top-0 border-b border-[var(--border-color)] z-10 select-none">
              <tr>
                <th onClick={() => onSort('label')} className="py-2 px-4 w-[40%] cursor-pointer hover:bg-[var(--bg-elevated)] hover:text-[var(--text-main)] group transition-colors">
                  Resource Path <span className="ml-1 inline-block w-3">{getSortIcon('label')}</span>
                </th>
                <th onClick={() => onSort('type')} className="py-2 px-4 w-[15%] cursor-pointer hover:bg-[var(--bg-elevated)] hover:text-[var(--text-main)] group transition-colors">
                  Type <span className="ml-1 inline-block w-3">{getSortIcon('type')}</span>
                </th>
                <th onClick={() => onSort('tls')} className="py-2 px-4 w-[120px] cursor-pointer hover:bg-[var(--bg-elevated)] hover:text-[var(--text-main)] group transition-colors">
                  TLS <span className="ml-1 inline-block w-3">{getSortIcon('tls')}</span>
                </th>
                <th onClick={() => onSort('latency')} className="py-2 px-4 w-[120px] cursor-pointer hover:bg-[var(--bg-elevated)] hover:text-[var(--text-main)] group transition-colors">
                  Latency <span className="ml-1 inline-block w-3">{getSortIcon('latency')}</span>
                </th>
                <th onClick={() => onSort('status')} className="py-2 px-4 w-[25%] cursor-pointer hover:bg-[var(--bg-elevated)] hover:text-[var(--text-main)] group transition-colors">
                  <span className="mr-1 inline-block w-3">{getSortIcon('status')}</span> Node Status
                </th>
              </tr>
            </thead>`,
`          <div className="overflow-x-auto w-full h-full">
            <table className="w-full text-left border-collapse table-auto">
              <thead className="bg-[var(--bg-header)] text-[var(--text-muted)] text-[10px] font-sans font-bold uppercase sticky top-0 border-b border-[var(--border-color)] z-10 select-none">
                <tr>
                  <th onClick={() => onSort('label')} className="py-2 px-4 min-w-[260px] cursor-pointer hover:bg-[var(--bg-elevated)] hover:text-[var(--text-main)] group transition-colors">
                    Resource Path <span className="ml-1 inline-block w-3">{getSortIcon('label')}</span>
                  </th>
                  <th onClick={() => onSort('type')} className="py-2 px-4 min-w-[100px] max-w-[160px] cursor-pointer hover:bg-[var(--bg-elevated)] hover:text-[var(--text-main)] group transition-colors">
                    Type <span className="ml-1 inline-block w-3">{getSortIcon('type')}</span>
                  </th>
                  <th onClick={() => onSort('tls')} className="py-2 px-4 min-w-[110px] cursor-pointer hover:bg-[var(--bg-elevated)] hover:text-[var(--text-main)] group transition-colors">
                    TLS <span className="ml-1 inline-block w-3">{getSortIcon('tls')}</span>
                  </th>
                  <th onClick={() => onSort('latency')} className="py-2 px-4 min-w-[90px] cursor-pointer hover:bg-[var(--bg-elevated)] hover:text-[var(--text-main)] group transition-colors">
                    Latency <span className="ml-1 inline-block w-3">{getSortIcon('latency')}</span>
                  </th>
                  <th onClick={() => onSort('status')} className="py-2 px-4 min-w-[180px] cursor-pointer hover:bg-[var(--bg-elevated)] hover:text-[var(--text-main)] group transition-colors">
                    <span className="mr-1 inline-block w-3">{getSortIcon('status')}</span> Node Status
                  </th>
                </tr>
              </thead>`
);

content = content.replace(
`            </tbody>
          </table>`,
`            </tbody>
            </table>
          </div>`
);

content = content.replace(
`<td className="py-2.5 px-4 w-[40%]">
              <div className="flex items-center" style={{ paddingLeft: \`\${depth * 22}px\` }}>`,
`<td className="py-2.5 px-4 min-w-[260px]">
              <div className="flex items-center" style={{ paddingLeft: \`\${Math.min(depth, 8) * 16}px\` }}>`
);
content = content.replace('w-[15%]', 'min-w-[100px] max-w-[160px]');
content = content.replace('w-[120px]', 'min-w-[110px]');
content = content.replace('w-[120px]', 'min-w-[90px]');
content = content.replace('w-[25%]', 'min-w-[180px]');

// 8. Inline details panel
content = content.replace(
`            <tr key={\`\${item.id}-inline-details\`} className="bg-[var(--bg-header)]/80 border-b border-[var(--border-color)]">
              <td colSpan={5} className="py-3 px-6" style={{ paddingLeft: \`\${depth * 22 + 36}px\` }}>
                <div className="p-3 bg-[var(--bg-main)] rounded border border-[var(--border-color)] text-xs font-mono space-y-1.5 max-h-[300px] overflow-auto">
                  <div className="font-sans font-bold text-[var(--color-blue)] text-[11px] uppercase mb-1">
                    🔍 Detailed Inspection: {item.label}
                  </div>
                  {Object.keys(item.details).length === 0 ? (
                    <div className="text-[var(--text-dim)]">No extra diagnostic payloads recorded for this node.</div>
                  ) : (
                    Object.entries(item.details).map(([k, v]) => (
                      <div key={k} className="flex gap-2">
                        <span className="text-[var(--text-muted)] font-semibold w-36 shrink-0">{k}:</span>
                        <span className="text-[var(--text-main)] whitespace-pre-wrap break-all">
                          {typeof v === 'object' ? JSON.stringify(v, null, 2) : String(v)}
                        </span>
                      </div>
                    ))
                  )}
                </div>
              </td>
            </tr>`,
`            <tr key={\`\${item.id}-inline-details\`} className="bg-[var(--bg-header)]/80 border-b border-[var(--border-color)]">
              <td colSpan={5} className="py-3 px-6 max-w-0 overflow-hidden" style={{ paddingLeft: \`\${Math.min(depth, 8) * 16 + 36}px\` }}>
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
            </tr>`
);

fs.writeFileSync(appPath, content);
