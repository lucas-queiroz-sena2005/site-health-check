import type { ScanRunResponse } from '../types'
import { RunStatusBadge } from './StatusBadge'
import { RunHistorySheet } from './RunHistorySheet'

export interface RunSummaryHeaderProps {
  selectedRunId: string | null
  run?: ScanRunResponse
  isRunActive: boolean
  onSelectRun: (id: string | null) => void
}

export function RunSummaryHeader({
  selectedRunId,
  run,
  isRunActive,
  onSelectRun,
}: RunSummaryHeaderProps) {
  const summary = run?.metrics_json?.summary

  return (
    <div className="px-6 py-4 shrink-0 border-b border-border bg-muted/30 flex justify-between items-center">
      <div className="flex items-center gap-6">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Run ID</span>
            <span className="text-sm font-mono font-bold bg-background border px-2 py-0.5 rounded">
              {selectedRunId || 'Latest'}
            </span>
            {run?.status && <RunStatusBadge status={run.status} />}
            {isRunActive && (
              <span className="text-xs font-mono text-muted-foreground flex items-center gap-1">
                <span>(Live • refreshing every 3s)</span>
              </span>
            )}
            {run?.scan_name && (
              <span className="text-sm font-semibold text-foreground ml-1">
                ({run.scan_name})
              </span>
            )}
          </div>
          <p className="text-muted-foreground text-sm font-mono font-semibold">
            <span className="text-foreground">{run?.metrics_json?.total_targets_scanned || 0}</span> IPs scanned •{' '}
            <span className="text-foreground">{run?.metrics_json?.scan_duration_seconds || 0}s</span> duration
          </p>
        </div>

        <div className="h-8 w-px bg-border mx-2" />

        {summary && (
          <div className="flex items-center gap-3 text-xs font-mono font-bold">
            <div className="flex items-center gap-1.5 bg-green-500/10 text-green-600 dark:text-green-400 px-2 py-1 rounded border border-green-500/20">
              <span className="uppercase tracking-wider opacity-70">Active</span>
              <span>{summary.active ?? 0}</span>
            </div>
            <div className="flex items-center gap-1.5 bg-yellow-500/10 text-yellow-600 dark:text-yellow-400 px-2 py-1 rounded border border-yellow-500/20">
              <span className="uppercase tracking-wider opacity-70">Warning</span>
              <span>{summary.warning ?? 0}</span>
            </div>
            <div className="flex items-center gap-1.5 bg-red-500/10 text-red-600 dark:text-red-400 px-2 py-1 rounded border border-red-500/20">
              <span className="uppercase tracking-wider opacity-70">Failed</span>
              <span>{summary.failed ?? 0}</span>
            </div>
            <div className="flex items-center gap-1.5 bg-purple-500/10 text-purple-600 dark:text-purple-400 px-2 py-1 rounded border border-purple-500/20">
              <span className="uppercase tracking-wider opacity-70">Ghost</span>
              <span>{summary.ghost ?? 0}</span>
            </div>
            <div className="flex items-center gap-1.5 bg-slate-500/10 text-slate-600 dark:text-slate-400 px-2 py-1 rounded border border-slate-500/20">
              <span className="uppercase tracking-wider opacity-70">Void</span>
              <span>{summary.void ?? 0}</span>
            </div>
          </div>
        )}
      </div>

      <div className="flex items-center gap-3">
        <RunHistorySheet
          selectedRunId={selectedRunId}
          onSelectRun={onSelectRun}
        />
      </div>
    </div>
  )
}
