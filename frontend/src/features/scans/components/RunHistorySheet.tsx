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

const MOCK_RUNS = Array.from({ length: 65 }).map((_, i) => {
  const date = new Date(Date.now() - i * 3600000 * 2.5 - 100000) // spread over a week
  return {
    id: `mock-run-${i}`,
    scan_name: i % 3 === 0 ? 'Daily Perimeter Sweep' : (i % 7 === 0 ? 'Weekly Deep Inspection' : null),
    status: i % 8 === 0 ? 'FAILED' : (i % 5 === 0 ? 'RUNNING' : 'COMPLETED'),
    targets: Array(Math.floor(Math.random() * 20) + 1).fill('target'),
    started_at: date.toISOString(),
  }
})

export function RunHistorySheet({ 
  selectedRunId, 
  onSelectRun 
}: { 
  selectedRunId: string | null
  onSelectRun: (id: string | null) => void 
}) {
  const [open, setOpen] = useState(false)
  const [runs, setRuns] = useState<any[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [hasMore, setHasMore] = useState(true)
  const [offset, setOffset] = useState(0)

  const fetchRuns = async (currentOffset: number, append: boolean) => {
    setIsLoading(true)
    try {
      // Simulate network delay
      await new Promise(r => setTimeout(r, 400))
      
      const chunk = MOCK_RUNS.slice(currentOffset, currentOffset + 20)
      
      if (append) {
        setRuns(prev => [...prev, ...chunk])
      } else {
        setRuns(chunk)
      }
      if (chunk.length < 20) {
        setHasMore(false)
      }
    } catch (err) {
      console.error(err)
    } finally {
      setIsLoading(false)
    }
  }

  // Reload when opened
  useEffect(() => {
    if (open) {
      setOffset(0)
      setHasMore(true)
      fetchRuns(0, false)
    }
  }, [open])

  const handleLoadMore = () => {
    const nextOffset = offset + 20
    setOffset(nextOffset)
    fetchRuns(nextOffset, true)
  }

  const getRunLabel = (id: string | null) => {
    if (!id) return "Loading Latest Run..."
    if (id === 'mock-run-id') return "Ad-hoc (Just now)"
    if (id === 'mock-run-id-2') return "Scheduled (2 hrs ago)"
    
    // Find in loaded runs
    const run = runs.find(r => r.id === id)
    if (run) {
      return run.scan_name || 'Ad-hoc Scan'
    }
    
    return `Run: ${id.slice(0, 8)}...`
  }

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger 
        render={
          <Button variant="outline" className="min-w-[200px] justify-between border-2 border-border bg-background text-foreground shadow-sm font-semibold hover:border-primary/50 transition-colors">
            <div className="flex items-center gap-2">
              <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="size-4 opacity-70"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
              <span>{getRunLabel(selectedRunId)}</span>
            </div>
            <span className="opacity-40 text-xs ml-4 uppercase tracking-wider">History</span>
          </Button>
        }
      />
      <SheetContent side="right" className="w-[400px] sm:w-[540px] flex flex-col h-full border-l-2">
        <SheetHeader className="pb-4 border-b-2">
          <SheetTitle className="text-xl font-bold">Scan History</SheetTitle>
          <SheetDescription>Select a past scan run to view its isolated results.</SheetDescription>
        </SheetHeader>
        
        <div className="flex-1 overflow-y-auto py-4 flex flex-col gap-3 pr-4">

          {runs.map(run => (
            <div 
              key={run.id}
              onClick={() => {
                onSelectRun(run.id)
                setOpen(false)
              }}
              className={`p-3 rounded-md border-2 cursor-pointer transition-colors ${
                selectedRunId === run.id 
                  ? 'border-primary bg-primary/10' 
                  : 'border-border hover:border-primary/50 bg-card'
              }`}
            >
              <div className="flex justify-between items-start mb-2">
                <span className="font-bold text-sm tracking-tight">{run.scan_name || 'Ad-hoc Scan'}</span>
                <span className={`text-[10px] font-mono px-2 py-0.5 rounded-full font-bold ${
                  run.status === 'COMPLETED' ? 'bg-green-500/20 text-green-700 dark:text-green-400' :
                  run.status === 'FAILED' ? 'bg-red-500/20 text-red-700 dark:text-red-400' :
                  'bg-yellow-500/20 text-yellow-700 dark:text-yellow-400'
                }`}>
                  {run.status}
                </span>
              </div>
              <div className="text-xs text-muted-foreground flex flex-col gap-1 font-mono">
                <span>Targets: <strong className="text-foreground">{run.targets?.length || 0}</strong></span>
                <span>Started: <strong className="text-foreground">{run.started_at ? new Date(run.started_at).toLocaleString() : 'N/A'}</strong></span>
              </div>
            </div>
          ))}
          
          {isLoading && (
            <div className="text-center py-4 text-sm text-muted-foreground font-semibold">Loading runs...</div>
          )}
          
          {hasMore && !isLoading && runs.length > 0 && (
            <Button variant="ghost" onClick={handleLoadMore} className="mt-2 w-full font-bold border-2 border-transparent hover:border-border">
              Load More ↓
            </Button>
          )}
          {!hasMore && runs.length > 0 && (
            <div className="text-center py-4 text-xs text-muted-foreground opacity-60 font-semibold tracking-widest uppercase">End of history</div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}
