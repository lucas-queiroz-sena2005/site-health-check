import { useState, useRef, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { ScanConfigForm, DEFAULT_NEW_SCAN } from '@/components/scans/ScanConfigForm'
import { Button } from '@/components/ui/button'

export function LiveScanPage() {
  const [logs, setLogs] = useState<string[]>([])
  const [isScanning, setIsScanning] = useState(false)
  const [isFinished, setIsFinished] = useState(false)
  const [currentRunId, setCurrentRunId] = useState<string | null>(null)
  const [countdown, setCountdown] = useState<number | null>(null)
  const terminalContainerRef = useRef<HTMLDivElement>(null)
  const eventSourceRef = useRef<EventSource | null>(null)
  
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const runIdParam = searchParams.get('run')
  const queryClient = useQueryClient()

  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close()
      }
    }
  }, [])

  // Auto-scroll to bottom when logs change without forcing main window to scroll
  useEffect(() => {
    if (terminalContainerRef.current) {
      const container = terminalContainerRef.current
      const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 150
      
      if (isNearBottom || logs.length < 5) {
        container.scrollTop = container.scrollHeight
      }
    }
  }, [logs])

  const connectToStream = (runId: string) => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
    }
    setCurrentRunId(runId)
    setIsScanning(true)
    setIsFinished(false)
    setCountdown(null)

    const eventSource = new EventSource(`/api/runs/${runId}/stream`)
    eventSourceRef.current = eventSource

    eventSource.addEventListener('info', (e) => {
      try {
        const payload = JSON.parse(e.data)
        setLogs(prev => [...prev, `[INFO] ${payload.message}`])
      } catch {
        setLogs(prev => [...prev, `[INFO] ${e.data}`])
      }
    })

    eventSource.addEventListener('log', (e) => {
      try {
        const payload = JSON.parse(e.data)
        setLogs(prev => [...prev, payload.message])
      } catch {
        setLogs(prev => [...prev, e.data])
      }
    })

    eventSource.addEventListener('status', (e) => {
      try {
        const payload = JSON.parse(e.data)
        setLogs(prev => [...prev, `[STATUS] ${payload.message}`])
      } catch {
        setLogs(prev => [...prev, `[STATUS] ${e.data}`])
      }
      setIsScanning(false)
      setIsFinished(true)
      eventSource.close()
      queryClient.invalidateQueries({ queryKey: ['runs'] })
    })

    eventSource.addEventListener('error', (e: Event) => {
      const msgEvent = e as MessageEvent
      if (msgEvent.data) {
        try {
          const payload = JSON.parse(msgEvent.data)
          setLogs(prev => [...prev, `[ERROR] ${payload.message}`])
        } catch {
          setLogs(prev => [...prev, `[ERROR] ${msgEvent.data}`])
        }
      } else {
        setLogs(prev => [...prev, `[ERROR] Connection to log stream lost.`])
      }
      setIsScanning(false)
      setIsFinished(true)
      eventSource.close()
      queryClient.invalidateQueries({ queryKey: ['runs'] })
    })
  }

  // Connect automatically if runIdParam is present in URL
  useEffect(() => {
    if (runIdParam && runIdParam !== currentRunId) {
      setLogs([`[INFO] Attached to run ${runIdParam}...`])
      connectToStream(runIdParam)
    }
  }, [runIdParam])

  // Countdown timer for automatic redirection to dashboard
  useEffect(() => {
    if (isFinished && currentRunId) {
      setCountdown(3)
    }
  }, [isFinished, currentRunId])

  useEffect(() => {
    if (countdown === null) return

    if (countdown <= 0) {
      if (currentRunId) {
        navigate(`/?run=${currentRunId}`)
      }
      return
    }

    const timer = setTimeout(() => {
      setCountdown(prev => (prev !== null ? prev - 1 : null))
    }, 1000)

    return () => clearTimeout(timer)
  }, [countdown, currentRunId, navigate])

  const handleLaunch = async (data: any) => {
    setIsScanning(true)
    setIsFinished(false)
    setCurrentRunId(null)
    setCountdown(null)
    setLogs([`[INFO] Scanner initialized. Targeting: ${data.targets.length > 0 ? data.targets.join(', ') : 'None'}`])
    
    try {
      const response = await fetch('/api/runs/launch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      })
      
      if (!response.ok) {
        throw new Error('Failed to launch scan')
      }
      
      const run = await response.json()
      connectToStream(run.id)
    } catch (err: any) {
      setLogs(prev => [...prev, `[ERROR] ${err.message}`])
      setIsScanning(false)
      setIsFinished(true)
    }
  }

  const handleCancel = () => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
    setLogs([])
    setIsFinished(false)
    setCountdown(null)
  }

  return (
    <div className="p-8 w-full h-full max-w-screen-2xl mx-auto flex flex-col gap-6">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Live Scan</h2>
        <p className="text-muted-foreground mt-1">Run ad-hoc scans and watch the engine output in real-time.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 flex-1 items-start relative">
        {/* Left Column: Form */}
        <div className="flex flex-col lg:col-span-5 xl:col-span-4">
          <ScanConfigForm
            initialData={{ ...DEFAULT_NEW_SCAN, targets: ['10.0.0.1/24'] }}
            onSave={handleLaunch}
            onCancel={handleCancel}
            mode="live"
            isScanning={isScanning}
          />
        </div>

        {/* Right Column: Terminal Visual */}
        <div className="lg:col-span-7 xl:col-span-8 bg-[#0a0a0a] rounded-sm border-2 border-[#333] overflow-hidden flex flex-col shadow-2xl h-[85vh] min-h-[700px] sticky top-8 relative">
          <div 
            ref={terminalContainerRef}
            className="p-6 font-mono text-[13px] text-[#00ff00] overflow-y-auto flex-1 pb-24"
          >
            {logs.length === 0 ? (
              <span className="text-[#00ff00]/50 italic">Waiting for input...</span>
            ) : (
              logs.map((log, i) => (
                <div 
                  key={i} 
                  className={`mb-1 leading-tight whitespace-pre-wrap break-all ${
                    log.includes('[ERROR]') || log.includes('[WARN]') ? 'text-[#ff3333]' :
                    log.includes('[SUCCESS]') ? 'text-[#00ffff]' : 
                    log.includes('[DEBUG]') ? 'text-[#00ff00]/60' : ''
                  }`}
                >
                  {log}
                </div>
              ))
            )}
          </div>
          
          {/* Post-Scan Redirection & Action */}
          {isFinished && currentRunId && (
            <div className="absolute bottom-6 right-6 flex items-center gap-3 z-10 animate-in fade-in slide-in-from-bottom-4 duration-500 bg-card/95 backdrop-blur-md p-3.5 rounded-lg border-2 border-primary/30 shadow-2xl">
              <span className="text-sm font-semibold text-foreground flex items-center gap-2">
                <span className="inline-block w-2 h-2 rounded-full bg-green-500 animate-pulse"></span>
                {countdown !== null && countdown > 0 
                  ? `Redirecting to dashboard in ${countdown}s...`
                  : 'Redirecting to dashboard...'}
              </span>
              <Button 
                size="default" 
                className="font-bold shadow-sm"
                onClick={() => {
                  setCountdown(null)
                  navigate(`/?run=${currentRunId}`)
                }}
              >
                View Results Now →
              </Button>
              <Button 
                variant="ghost" 
                size="sm"
                onClick={() => setCountdown(null)}
                className="text-xs text-muted-foreground hover:text-foreground"
              >
                Stay here
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
