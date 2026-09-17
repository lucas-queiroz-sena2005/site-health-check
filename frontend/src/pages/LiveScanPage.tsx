import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { ScanConfigForm, DEFAULT_NEW_SCAN } from '@/components/scans/ScanConfigForm'
import { Button } from '@/components/ui/button'

export function LiveScanPage() {
  const [logs, setLogs] = useState<string[]>([])
  const [isScanning, setIsScanning] = useState(false)
  const [isFinished, setIsFinished] = useState(false)
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

  const handleLaunch = (data: any) => {
    setIsScanning(true)
    setIsFinished(false)
    setLogs([`[INFO] Scanner initialized. Targeting: ${data.targets.length > 0 ? data.targets.join(', ') : 'None'}`])
    
    // Generate ~150 lines of mock logs
    const mockLines: string[] = []
    const targetCount = data.targets.length || 1
    
    mockLines.push(`[INFO] Resolving DNS for ${targetCount} targets...`)
    mockLines.push(`[INFO] Discovered 24 internal IPs from CIDR expansion.`)
    mockLines.push(`[INFO] Beginning L4 TCP probe across 24 nodes on ports [80, 443]...`)
    
    for (let i = 1; i <= 24; i++) {
      const ip = `10.0.0.${i + 10}`
      mockLines.push(`[DEBUG] Handshake initiated with ${ip}:80`)
      mockLines.push(`[DEBUG] Handshake initiated with ${ip}:443`)
      
      if (i % 4 === 0) {
        mockLines.push(`[WARN] Connection refused on ${ip}:80 - marking port closed.`)
        mockLines.push(`[INFO] ${ip}:443 established in ${Math.floor(Math.random() * 20 + 5)}ms`)
        mockLines.push(`[INFO] Extracting TLS Certificate from ${ip}:443...`)
        mockLines.push(`[SUCCESS] TLS Valid: Subject Alternative Names found for ${ip}`)
        mockLines.push(`[INFO] Executing HTTP GET / on ${ip}:443`)
        mockLines.push(`[DEBUG] 302 Redirect encountered to /login on ${ip}`)
      } else if (i % 7 === 0) {
        mockLines.push(`[ERROR] Timeout on ${ip}:443 after 10.0s`)
        mockLines.push(`[ERROR] Timeout on ${ip}:80 after 10.0s`)
        mockLines.push(`[WARN] Node ${ip} is entirely unreachable (Void Space).`)
      } else {
        mockLines.push(`[INFO] ${ip}:80 established in ${Math.floor(Math.random() * 20 + 5)}ms`)
        mockLines.push(`[INFO] ${ip}:443 established in ${Math.floor(Math.random() * 20 + 5)}ms`)
        mockLines.push(`[INFO] Executing HTTP GET / on ${ip}:80`)
        mockLines.push(`[SUCCESS] HTTP 200 OK received from ${ip}:80 in ${Math.floor(Math.random() * 50 + 10)}ms`)
      }
    }
    
    mockLines.push(`[INFO] Performing recursive SAN checks on discovered domains...`)
    for (let i = 0; i < 15; i++) {
      mockLines.push(`[DEBUG] Recursive check ${i+1}/15: Scanning extracted SAN internal-api-${i}.local`)
    }
    
    mockLines.push(`[INFO] Aggregating results and checking historical diffs...`)
    mockLines.push(`[SUCCESS] Job completed successfully in 4.82s`)

    let step = 0
    const interval = setInterval(() => {
      if (step < mockLines.length) {
        // Push 1 to 3 lines at a time for a more realistic bursty output
        const burstSize = Math.floor(Math.random() * 3) + 1
        const nextLines = mockLines.slice(step, step + burstSize)
        setLogs(prev => [...prev, ...nextLines])
        step += burstSize
      } else {
        setIsScanning(false)
        setIsFinished(true)
        clearInterval(interval)
      }
    }, 40) // Fast interval for ~150 lines
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
                onClick={() => navigate('/?run=mock-run-id')}
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
