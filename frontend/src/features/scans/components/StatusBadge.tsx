
export function EntityStatusBadge({ status }: { status: string }) {
  const s = status.toLowerCase()
  if (s === 'ok' || s === 'active') {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-green-500/10 text-green-600 dark:text-green-400 border border-green-500/20">
        OK
      </span>
    )
  }
  if (s === 'warning') {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-yellow-500/10 text-yellow-600 dark:text-yellow-400 border border-yellow-500/20">
        Warning
      </span>
    )
  }
  if (s === 'failed') {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-red-500/10 text-red-600 dark:text-red-400 border border-red-500/20">
        Failed
      </span>
    )
  }
  if (s === 'ghost') {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20">
        Ghost
      </span>
    )
  }
  if (s === 'void') {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-slate-500/10 text-slate-600 dark:text-slate-400 border border-slate-500/20">
        Void
      </span>
    )
  }
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-muted text-muted-foreground border border-border">
      {status}
    </span>
  )
}

export function FindingBadge({ code, finding }: { code?: string; finding?: string }) {
  const c = (code || finding || '').toUpperCase()
  if (!c) return null

  let color = 'bg-yellow-500/10 text-yellow-600 dark:text-yellow-400 border-yellow-500/20'
  if (
    c.includes('5XX') ||
    c.includes('FAIL') ||
    c.includes('INVALID') ||
    c.includes('EXPIRED') ||
    c.includes('CLOSED') ||
    c.includes('ERROR')
  ) {
    color = 'bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/20'
  } else if (c.includes('GHOST')) {
    color = 'bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/20'
  }
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono font-bold border ${color}`}>
      {c}
    </span>
  )
}

export function FormatLatency({ latency, ms }: { latency?: number | null; ms?: number | null }) {
  const value = latency !== undefined ? latency : ms
  if (value === null || value === undefined) {
    return <span className="text-muted-foreground/60">—</span>
  }
  return <span className="font-mono text-xs">{value} ms</span>
}

export function FormatTlsExpiry({ days }: { days?: number | null }) {
  if (days === null || days === undefined) {
    return <span className="text-muted-foreground/60">—</span>
  }
  if (days < 0) {
    return (
      <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[11px] font-mono font-bold bg-red-500/10 text-red-600 dark:text-red-400 border border-red-500/20">
        expired {-days}d
      </span>
    )
  }
  if (days < 30) {
    return (
      <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[11px] font-mono font-bold bg-yellow-500/10 text-yellow-600 dark:text-yellow-400 border border-yellow-500/20">
        {days}d
      </span>
    )
  }
  return (
    <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[11px] font-mono font-bold bg-green-500/10 text-green-600 dark:text-green-400 border border-green-500/20">
      {days}d
    </span>
  )
}

export function FormatTlsVersion({ version }: { version?: string | null }) {
  if (!version) {
    return <span className="text-muted-foreground/60">—</span>
  }
  const isDeprecated = version === 'TLSv1' || version === 'TLSv1.0' || version === 'TLSv1.1' || version.startsWith('SSL')
  return (
    <span
      className={`inline-flex items-center px-1.5 py-0.5 rounded text-[11px] font-mono font-bold border ${
        isDeprecated
          ? 'bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/20'
          : 'bg-background border-border text-foreground'
      }`}
    >
      {version}
    </span>
  )
}

export function FormatHttpStatus({ status, code }: { status?: number | null; code?: number | null }) {
  const value = status !== undefined ? status : code
  if (value === null || value === undefined) {
    return <span className="text-muted-foreground/60">—</span>
  }
  let color = 'bg-green-500/10 text-green-600 dark:text-green-400 border-green-500/20'
  if (value >= 500) {
    color = 'bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/20'
  } else if (value >= 400) {
    color = 'bg-yellow-500/10 text-yellow-600 dark:text-yellow-400 border-yellow-500/20'
  } else if (value >= 300) {
    color = 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20'
  }
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[11px] font-mono font-bold border ${color}`}>
      {value}
    </span>
  )
}
