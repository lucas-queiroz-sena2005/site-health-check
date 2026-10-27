import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

export interface SavedView {
  id: string
  name: string
  search?: string | null
  statuses?: string[]
  table_sort_by?: string | null
  table_sort_dir?: string | null
}

const CANONICAL_FINDINGS = [
  'TCP_CLOSED',
  'TLS_INVALID',
  'TLS_EXPIRED',
  'TLS_EXPIRING_SOON',
  'TLS_DEPRECATED_VERSION',
  'HTTP_5XX',
  'HTTP_4XX',
  'HTTP_ERROR',
  'HOST_GHOST',
]

export interface ScanFilterToolbarProps {
  activeTab: 'hosts' | 'services' | 'checks'
  savedViews: SavedView[]
  activeViewId: string
  onSelectView: (viewId: string) => void
  onSaveView: (name: string) => void
  onDeleteView: () => void
  searchInput: string
  onSearchChange: (val: string) => void
  ipParam?: string
  onClearIp: () => void
  portParam?: number
  onPortChange: (port?: number) => void
  findingParam?: string
  onFindingChange: (finding?: string) => void
  includeClosed?: boolean
  onIncludeClosedChange: (val: boolean) => void
  statusParam: string
  onStatusToggle: (status: string) => void
}

export function ScanFilterToolbar({
  activeTab,
  savedViews,
  activeViewId,
  onSelectView,
  onSaveView,
  onDeleteView,
  searchInput,
  onSearchChange,
  ipParam,
  onClearIp,
  portParam,
  onPortChange,
  findingParam = '',
  onFindingChange,
  includeClosed = false,
  onIncludeClosedChange,
  statusParam,
  onStatusToggle,
}: ScanFilterToolbarProps) {
  const [isSavingView, setIsSavingView] = useState(false)
  const [newViewName, setNewViewName] = useState('')

  const handleSaveSubmit = () => {
    if (newViewName.trim()) {
      onSaveView(newViewName.trim())
      setNewViewName('')
      setIsSavingView(false)
    }
  }

  return (
    <div className="px-6 py-3 shrink-0 bg-muted/20 flex items-center gap-4 flex-wrap border-b border-border shadow-sm">
      {/* Saved Views */}
      <div className="flex items-center gap-2 shrink-0">
        {isSavingView ? (
          <div className="flex items-center gap-2">
            <span className="text-muted-foreground text-xs font-semibold">Save View:</span>
            <Input
              type="text"
              placeholder="View name..."
              autoFocus
              value={newViewName}
              onChange={(e) => setNewViewName(e.target.value)}
              className="bg-background text-foreground h-8 text-xs font-mono font-semibold w-40"
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleSaveSubmit()
                if (e.key === 'Escape') setIsSavingView(false)
              }}
            />
            <Button size="sm" onClick={handleSaveSubmit} className="h-8 px-2 text-xs font-semibold">
              ✓ Save
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                setIsSavingView(false)
                onSelectView('view-default')
              }}
              className="h-8 px-2 text-xs"
            >
              ✕ Cancel
            </Button>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <span className="text-muted-foreground text-xs font-semibold">Global View:</span>
            <select
              value={activeViewId}
              onChange={(e) => onSelectView(e.target.value)}
              className="bg-background text-foreground border border-border rounded px-2.5 py-1 text-xs font-mono font-semibold focus:outline-none focus:ring-1 focus:ring-primary cursor-pointer max-w-[200px]"
            >
              {savedViews.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name}
                </option>
              ))}
            </select>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsSavingView(true)}
              className="h-7 px-2 text-xs"
              title="Save Current View"
            >
              + Create
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={onDeleteView}
              disabled={!activeViewId || activeViewId === 'view-default'}
              className="h-7 px-2 text-xs text-destructive hover:text-destructive disabled:opacity-40"
              title="Delete View"
            >
              ✕
            </Button>
          </div>
        )}
      </div>

      {/* Search Input */}
      <div className="flex items-center gap-2 min-w-[220px] max-w-sm">
        <Input
          type="text"
          placeholder="Search IP, domain, issuer, findings..."
          value={searchInput}
          onChange={(e) => onSearchChange(e.target.value)}
          className="w-full bg-background border border-border h-8 text-xs placeholder:text-muted-foreground focus:ring-1 focus:ring-primary"
        />
      </div>

      {/* Active IP Filter Chip */}
      {ipParam && (
        <div
          data-testid="ip-filter-chip"
          className="inline-flex items-center gap-1.5 bg-primary/10 text-primary border border-primary/20 px-2 py-1 rounded-full text-xs font-mono font-semibold"
        >
          <span>Host: {ipParam}</span>
          <button
            type="button"
            aria-label="Clear IP filter"
            onClick={onClearIp}
            className="text-primary hover:text-primary/70 font-bold ml-1 cursor-pointer"
          >
            ×
          </button>
        </div>
      )}

      {/* Port Filter (Services & Checks) */}
      {(activeTab === 'services' || activeTab === 'checks') && (
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-muted-foreground font-semibold">Port:</span>
          <Input
            type="number"
            placeholder="e.g. 443"
            value={portParam !== undefined ? portParam : ''}
            onChange={(e) => {
              const val = e.target.value.trim()
              onPortChange(val ? Number(val) : undefined)
            }}
            className="w-20 bg-background border border-border h-8 text-xs font-mono"
          />
        </div>
      )}

      {/* Finding Code Filter */}
      <div className="flex items-center gap-1.5">
        <select
          value={findingParam}
          onChange={(e) => onFindingChange(e.target.value || undefined)}
          className="bg-background text-foreground border border-border rounded px-2 py-1 text-xs font-mono cursor-pointer"
        >
          <option value="">All Findings</option>
          {CANONICAL_FINDINGS.map((f) => (
            <option key={f} value={f}>
              {f}
            </option>
          ))}
        </select>
      </div>

      {/* Include Closed Ports (Services Tab) */}
      {activeTab === 'services' && (
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground font-semibold cursor-pointer">
          <input
            type="checkbox"
            checked={includeClosed}
            onChange={(e) => onIncludeClosedChange(e.target.checked)}
            className="rounded border-border text-primary focus:ring-primary h-3.5 w-3.5 cursor-pointer"
          />
          <span>Include Closed Ports</span>
        </label>
      )}

      {/* Status Toggle Pills */}
      <div className="flex items-center gap-1 ml-auto bg-muted/40 border border-border p-0.5 rounded-lg font-mono text-xs">
        {(['all', 'active', 'warning', 'failed', 'ghost'] as const).map((st) => {
          const isSelected =
            st === 'all'
              ? statusParam === 'all' || !statusParam
              : statusParam.split(',').includes(st)
          return (
            <button
              type="button"
              key={st}
              onClick={() => onStatusToggle(st)}
              className={`px-3 py-1 rounded capitalize transition-all cursor-pointer ${
                isSelected
                  ? 'bg-background shadow-sm font-bold text-foreground'
                  : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
              }`}
            >
              {st}
            </button>
          )
        })}
      </div>
    </div>
  )
}
