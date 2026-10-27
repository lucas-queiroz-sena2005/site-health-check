export interface ScanTabsNavProps {
  activeTab: 'hosts' | 'services' | 'checks'
  onTabChange: (tab: 'hosts' | 'services' | 'checks') => void
  hostsCount: number
  servicesCount: number
  checksCount: number
}

export function ScanTabsNav({
  activeTab,
  onTabChange,
  hostsCount,
  servicesCount,
  checksCount,
}: ScanTabsNavProps) {
  return (
    <div className="px-6 pt-3 shrink-0 border-b border-border bg-background flex items-center gap-2" role="tablist">
      <button
        type="button"
        role="tab"
        aria-selected={activeTab === 'hosts'}
        onClick={() => onTabChange('hosts')}
        className={`flex items-center gap-2 px-4 py-2 border-b-2 font-semibold text-sm transition-colors cursor-pointer ${
          activeTab === 'hosts'
            ? 'border-primary text-primary'
            : 'border-transparent text-muted-foreground hover:text-foreground'
        }`}
      >
        <span>Hosts</span>
        <span className="bg-muted px-2 py-0.5 rounded-full text-xs font-mono text-foreground font-bold">
          {hostsCount}
        </span>
      </button>

      <button
        type="button"
        role="tab"
        aria-selected={activeTab === 'services'}
        onClick={() => onTabChange('services')}
        className={`flex items-center gap-2 px-4 py-2 border-b-2 font-semibold text-sm transition-colors cursor-pointer ${
          activeTab === 'services'
            ? 'border-primary text-primary'
            : 'border-transparent text-muted-foreground hover:text-foreground'
        }`}
      >
        <span>Services</span>
        <span className="bg-muted px-2 py-0.5 rounded-full text-xs font-mono text-foreground font-bold">
          {servicesCount}
        </span>
      </button>

      <button
        type="button"
        role="tab"
        aria-selected={activeTab === 'checks'}
        onClick={() => onTabChange('checks')}
        className={`flex items-center gap-2 px-4 py-2 border-b-2 font-semibold text-sm transition-colors cursor-pointer ${
          activeTab === 'checks'
            ? 'border-primary text-primary'
            : 'border-transparent text-muted-foreground hover:text-foreground'
        }`}
      >
        <span>HTTP Checks</span>
        <span className="bg-muted px-2 py-0.5 rounded-full text-xs font-mono text-foreground font-bold">
          {checksCount}
        </span>
      </button>
    </div>
  )
}
