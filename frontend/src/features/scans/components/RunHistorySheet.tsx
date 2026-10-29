import { useState, useEffect } from 'react'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet"
import { Button } from "@/components/ui/button"

import { useQuery, useQueryClient } from '@tanstack/react-query'
import type { ScanRunResponse } from '../types'
import { scanQueryKeys } from '../api/queryKeys'

export function RunHistorySheet({ 
  selectedRunId, 
  onSelectRun,
  triggerLabel,
  className,
}: { 
  selectedRunId: string | null
  onSelectRun: (id: string | null) => void 
  triggerLabel?: string
  className?: string
}) {
  const [open, setOpen] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const queryClient = useQueryClient()
  const { data: runs = [], isLoading, refetch } = useQuery<ScanRunResponse[]>({
    queryKey: scanQueryKeys.history(),
    queryFn: async () => {
      const res = await fetch(`/api/runs?limit=50`)
      if (!res.ok) throw new Error('Network error')
      return res.json()
    },
    enabled: true,
    staleTime: 0,
    refetchOnMount: 'always'
  })

  useEffect(() => {
    if (open) {
      refetch()
    }
  }, [open, refetch])

  const handleDeleteRun = async (e: React.MouseEvent, runId: string) => {
    e.stopPropagation()
    setDeletingId(runId)
    try {
      const res = await fetch(`/api/runs/${runId}`, { method: 'DELETE' })
      if (res.ok) {
        if (selectedRunId === runId) {
          onSelectRun(null)
        }
        await queryClient.invalidateQueries({ queryKey: scanQueryKeys.history() })
        refetch()
      }
    } finally {
      setDeletingId(null)
    }
  }

  const getRunLabel = (id: string | null) => {
    if (!id) return "Loading Latest Run..."
    if (id === 'mock-run-id') return "Ad-hoc (Just now)"
    if (id === 'mock-run-id-2') return "Scheduled (2 hrs ago)"
    
    // Find in loaded runs
    const run = Array.isArray(runs) ? runs.find((r) => r.id === id) : undefined
    if (run) {
      return run.scan_name || 'Ad-hoc Scan'
    }
    
    return `Run: ${id.slice(0, 8)}...`
  }

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger 
        render={
          <Button
            variant="outline"
            className={className || "min-w-[200px] justify-between border-2 border-border bg-background text-foreground shadow-sm font-semibold hover:border-primary/50 transition-colors"}
          >
            <div className="flex items-center gap-2">
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="size-4 opacity-70"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
              <span>{triggerLabel || getRunLabel(selectedRunId)}</span>
            </div>
            {!triggerLabel && <span className="opacity-40 text-xs ml-4 uppercase tracking-wider">History</span>}
          </Button>
        }
      />
      <SheetContent side="right" className="w-[400px] sm:w-[540px] flex flex-col h-full border-l-2">
        <SheetHeader className="pb-4 border-b-2">
          <SheetTitle className="text-xl font-bold">Scan History</SheetTitle>
          <SheetDescription>Select a past scan run to view its isolated results.</SheetDescription>
        </SheetHeader>
        
        <div className="flex-1 overflow-y-auto py-4 flex flex-col gap-3 pr-4">

          {runs.map((run) => {
            const targetsPreview = run.targets && run.targets.length > 0 ? run.targets.join(', ') : 'None'
            const isTerminal = run.status === 'COMPLETED' || run.status === 'FAILED' || run.status === 'ABORTED'

            return (
              <button 
                type="button"
                key={run.id}
                onClick={() => {
                  onSelectRun(run.id)
                  setOpen(false)
                }}
                className={`w-full text-left p-3 rounded-md border-2 cursor-pointer transition-colors ${
                  selectedRunId === run.id 
                    ? 'border-primary bg-primary/10' 
                    : 'border-border hover:border-primary/50 bg-card'
                }`}
              >
                <div className="flex justify-between items-start mb-2">
                  <span className="font-bold text-sm tracking-tight">{run.scan_name || 'Ad-hoc Scan'}</span>
                  <div className="flex items-center gap-1.5">
                    <span className={`text-[10px] font-mono px-2 py-0.5 rounded-full font-bold ${
                      run.status === 'COMPLETED' ? 'bg-green-500/20 text-green-700 dark:text-green-400' :
                      run.status === 'FAILED' ? 'bg-red-500/20 text-red-700 dark:text-red-400' :
                      run.status === 'ABORTED' ? 'bg-orange-500/20 text-orange-700 dark:text-orange-400' :
                      'bg-yellow-500/20 text-yellow-700 dark:text-yellow-400'
                    }`}>
                      {run.status}
                    </span>
                    {isTerminal && (
                      <span
                        role="button"
                        title="Delete Run"
                        tabIndex={0}
                        onClick={(e) => handleDeleteRun(e, run.id)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault()
                            handleDeleteRun(e as any, run.id)
                          }
                        }}
                        className={`p-1 rounded text-muted-foreground/60 hover:text-destructive hover:bg-destructive/10 transition-colors cursor-pointer ${
                          deletingId === run.id ? 'opacity-50 pointer-events-none' : ''
                        }`}
                      >
                        <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>
                        </svg>
                      </span>
                    )}
                  </div>
                </div>
                {run.status !== 'COMPLETED' && run.status !== 'PENDING' && run.status !== 'RUNNING' && (
                  <div className="text-[10px] bg-orange-500/10 text-orange-600 px-2 py-1 mb-2 rounded-sm border border-orange-500/30 font-bold uppercase tracking-widest w-fit">
                    Partial Results
                  </div>
                )}
                <div className="text-xs text-muted-foreground flex flex-col gap-1 font-mono">
                  <div className="flex items-center gap-1.5 overflow-hidden">
                    <span className="shrink-0 text-muted-foreground">Targets:</span>
                    <span className="font-semibold text-foreground truncate" title={targetsPreview}>
                      {targetsPreview}
                    </span>
                    {run.targets && run.targets.length > 1 && (
                      <span className="text-[10px] bg-muted px-1 rounded text-muted-foreground shrink-0">
                        ({run.targets.length})
                      </span>
                    )}
                  </div>
                  <span>Started: <strong className="text-foreground">{run.started_at ? new Date(run.started_at).toLocaleString() : 'N/A'}</strong></span>
                </div>
              </button>
            )
          })}
          
          {isLoading && (
            <div className="text-center py-4 text-sm text-muted-foreground font-semibold">Loading runs...</div>
          )}

          {!isLoading && runs.length === 0 && (
            <div className="text-center py-12 text-sm text-muted-foreground font-medium flex flex-col items-center gap-2">
              <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="opacity-40"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
              <span>No scan runs recorded yet.</span>
              <span className="text-xs text-muted-foreground/70">Execute a live scan or wait for a scheduled scan to populate history.</span>
            </div>
          )}
          
          {!isLoading && runs.length > 0 && (
            <div className="text-center py-4 text-xs text-muted-foreground opacity-60 font-semibold tracking-widest uppercase">End of history</div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}
