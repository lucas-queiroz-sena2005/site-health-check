import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { ScanConfigForm, DEFAULT_NEW_SCAN } from '@/components/scans/ScanConfigForm'
import { Button } from '@/components/ui/button'

export function LiveScanPage() {
  const [logs, setLogs] = useState<string[]>([])
  const [isScanning, setIsScanning] = useState(false)
  const [isFinished, setIsFinished] = useState(false)
  const [currentRunId, setCurrentRunId] = useState<string | null>(null)
  const terminalContainerRef = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()

  // Auto-scroll to bottom when logs change without forcing main window to scroll
  useEffect(() => {
    if (terminalContainerRef.current) {
      const container = terminalContainerRef.current
      const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 150
      
      if (isNearBottom || logs.length < 5) {
        // Manipulate scrollTop directly to prevent the browser window from scrolling down
        container.scrollTop = container.scrollHeight
      }
    }
  }, [logs])

  const handleLaunch = async (data: any) => {
    setIsScanning(true)
    setIsFinished(false)
    setCurrentRunId(null)
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
      setCurrentRunId(run.id)
      
      const eventSource = new EventSource(`/api/runs/${run.id}/stream`)
      
      eventSource.addEventListener('info', (e) => {
        const payload = JSON.parse(e.data)
        setLogs(prev => [...prev, `[INFO] ${payload.message}`])
      })
      
      eventSource.addEventListener('log', (e) => {
        const payload = JSON.parse(e.data)
        setLogs(prev => [...prev, payload.message])
      })
      
      eventSource.addEventListener('status', (e) => {
        const payload = JSON.parse(e.data)
        setLogs(prev => [...prev, `[STATUS] ${payload.message}`])
        setIsScanning(false)
        setIsFinished(true)
        eventSource.close()
      })
      
      eventSource.addEventListener('error', (e) => {
        if (e.data) {
          const payload = JSON.parse(e.data)
          setLogs(prev => [...prev, `[ERROR] ${payload.message}`])
        } else {
          setLogs(prev => [...prev, `[ERROR] Connection to log stream lost.`])
        }
        setIsScanning(false)
        setIsFinished(true)
        eventSource.close()
      })
      
    } catch (err: any) {
      setLogs(prev => [...prev, `[ERROR] ${err.message}`])
      setIsScanning(false)
      setIsFinished(true)
    }
  }

  const handleCancel = () => {
    setLogs([])
    setIsFinished(false)
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
          
          {/* Post-Scan Action */}
          {isFinished && (
            <div className="absolute bottom-6 right-6 flex items-center justify-end z-10">
              <Button 
                size="lg" 
                className="font-bold shadow-2xl border-2 border-primary/50 animate-in fade-in slide-in-from-bottom-4 duration-500"
                onClick={() => navigate(`/?run=${currentRunId}`)}
              >
                View Results in Dashboard →
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
