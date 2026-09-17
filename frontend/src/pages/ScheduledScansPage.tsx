import React, { useState } from 'react'
import { Button } from '@/components/ui/button'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { ScanConfigForm, EXECUTION_FLAGS_SCHEMA, DEFAULT_NEW_SCAN } from '@/components/scans/ScanConfigForm'

export function ScheduledScansPage() {
  const [scans, setScans] = useState([
    {
      id: 1,
      name: 'Daily Perimeter Sweep',
      schedule: '0 0 * * *',
      targets: ['github.com', 'google.com'],
      ports: [80, 443],
      flags: { check_tcp: true, check_http: true, check_virtual_hosts: false, timeout: 5 },
      lastRun: '2 hours ago',
      nextRun: 'In 22 hours',
      metrics: {
        total_targets_scanned: 12,
        scan_duration_seconds: 1.42,
        anomalies_found: 0,
      },
    },
    {
      id: 2,
      name: 'Weekly Deep Inspection',
      schedule: '0 2 * * 0',
      targets: ['internal.network.local'],
      ports: [22, 80, 443, 3306],
      flags: { check_tcp: true, check_http: true, recursive_san: true, out_of_scope_depth: 2, workers: 200 },
      lastRun: '4 days ago',
      nextRun: 'In 3 days',
      metrics: {
        total_targets_scanned: 45,
        scan_duration_seconds: 14.5,
        anomalies_found: 2,
      },
    },
    {
      id: 3,
      name: 'Datacenter Heartbeat',
      schedule: '*/15 * * * *',
      targets: ['10.0.0.1/24'],
      ports: [443],
      flags: { check_tcp: true, check_http: false, timeout: 2 },
      lastRun: '10 mins ago',
      nextRun: 'In 5 mins',
      metrics: {
        total_targets_scanned: 254,
        scan_duration_seconds: 0.8,
        anomalies_found: 0,
      },
    },
  ])

  const [expandedScanId, setExpandedScanId] = useState<number | null>(null)
  const [editingScanId, setEditingScanId] = useState<number | null>(null)
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false)

  const handleDelete = (id: number) => {
    setScans(scans.filter((s) => s.id !== id))
    if (expandedScanId === id) setExpandedScanId(null)
    if (editingScanId === id) setEditingScanId(null)
  }

  const handleCreate = (data: any) => {
    const newScan = {
      ...data,
      id: Math.max(...scans.map((s) => s.id), 0) + 1,
      lastRun: 'Never',
      nextRun: 'Pending',
      metrics: null,
    }
    setScans([...scans, newScan])
    setIsCreateModalOpen(false)
  }

  const handleSaveInline = (id: number, data: any) => {
    setScans(
      scans.map((s) =>
        s.id === id
          ? {
              ...s,
              ...data,
            }
          : s
      )
    )
    setEditingScanId(null)
  }

  return (
    <div className="p-8 w-full h-full max-w-6xl mx-auto flex flex-col gap-8">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Scheduled Scans</h2>
          <p className="text-muted-foreground mt-1">Manage and monitor automated periodic checks.</p>
        </div>
        
        <Dialog open={isCreateModalOpen} onOpenChange={setIsCreateModalOpen}>
          <DialogTrigger render={<Button size="lg" className="font-semibold shadow-sm">+ Create New Schedule</Button>} />
          <DialogContent className="sm:max-w-4xl max-h-[90vh] overflow-y-auto p-8 border-2 border-border shadow-xl">
            <DialogHeader className="text-center pb-6 border-b-2 border-border/50 mb-6">
              <DialogTitle className="text-3xl font-extrabold tracking-tight">Create New Scheduled Scan</DialogTitle>
            </DialogHeader>
            <div className="mt-2">
              <ScanConfigForm
                initialData={DEFAULT_NEW_SCAN}
                onSave={handleCreate}
                onCancel={() => setIsCreateModalOpen(false)}
                mode="schedule"
                isCreating={true}
              />
            </div>
          </DialogContent>
        </Dialog>
      </div>

      <div className="rounded-xl border-2 border-border bg-card text-card-foreground shadow-sm overflow-hidden">
        <Table>
          <TableHeader className="bg-muted/40">
            <TableRow className="border-b-2 border-border/50">
              <TableHead className="w-[40px]"></TableHead>
              <TableHead className="font-bold text-foreground">Scan Name</TableHead>
              <TableHead className="font-bold text-foreground">Cron Schedule</TableHead>
              <TableHead className="font-bold text-foreground">Last Run</TableHead>
              <TableHead className="font-bold text-foreground">Next Run</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {scans.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="h-32 text-center text-muted-foreground font-medium">
                  No scheduled scans found.
                </TableCell>
              </TableRow>
            ) : (
              scans.map((scan) => (
                <React.Fragment key={scan.id}>
                  <TableRow
                    className="cursor-pointer hover:bg-muted/30 transition-colors border-b-2 border-border/40 last:border-0"
                    onClick={() => {
                      setExpandedScanId(expandedScanId === scan.id ? null : scan.id)
                      if (editingScanId === scan.id) setEditingScanId(null)
                    }}
                  >
                    <TableCell className="p-4 pl-6">
                      <svg
                        className={`w-5 h-5 transform transition-transform text-muted-foreground duration-300 ${
                          expandedScanId === scan.id ? 'rotate-90 text-primary' : ''
                        }`}
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" />
                      </svg>
                    </TableCell>
                    <TableCell className="font-bold text-[15px]">{scan.name}</TableCell>
                    <TableCell className="font-mono text-primary font-bold bg-primary/5 px-3 py-1 rounded-md inline-block mt-3 mb-2 border border-primary/20">{scan.schedule}</TableCell>
                    <TableCell className="text-muted-foreground font-medium">{scan.lastRun}</TableCell>
                    <TableCell className="font-bold text-green-600 dark:text-green-500">{scan.nextRun}</TableCell>
                  </TableRow>
                  {expandedScanId === scan.id && (
                    <TableRow className="bg-muted/10 hover:bg-muted/10 border-b-2 border-border/40">
                      <TableCell colSpan={5} className="p-0">
                        <div className="p-8 border-t-2 border-primary/10 shadow-inner">
                          {editingScanId === scan.id ? (
                            <ScanConfigForm
                              initialData={scan}
                              onSave={(data) => handleSaveInline(scan.id, data)}
                              onCancel={() => setEditingScanId(null)}
                              mode="schedule"
                            />
                          ) : (
                            <div className="flex items-start justify-between">
                              <div className="space-y-8 w-full pr-12">
                                <div className="grid grid-cols-2 gap-8">
                                  <div className="space-y-4">
                                    <div className="text-sm font-extrabold text-primary uppercase tracking-widest border-b-2 border-border/50 pb-2">Targets & Ports</div>
                                    <div className="flex flex-col gap-3">
                                      <div className="bg-background border-2 border-border p-3 rounded-lg shadow-sm flex flex-col gap-1.5">
                                        <span className="text-xs text-muted-foreground font-bold uppercase tracking-wider">Targets</span>
                                        <span className="font-bold text-foreground font-mono whitespace-pre-wrap break-all text-sm">
                                          {scan.targets.length > 0 ? scan.targets.join(', ') : 'None specified'}
                                        </span>
                                      </div>
                                      <div className="bg-background border-2 border-border p-3 rounded-lg shadow-sm flex flex-col gap-1.5">
                                        <span className="text-xs text-muted-foreground font-bold uppercase tracking-wider">Ports</span>
                                        <span className="font-bold text-foreground font-mono text-sm">
                                          {scan.ports.length > 0 ? scan.ports.join(', ') : 'None specified'}
                                        </span>
                                      </div>
                                    </div>
                                  </div>
                                  <div className="space-y-4">
                                    <div className="text-sm font-extrabold text-primary uppercase tracking-widest border-b-2 border-border/50 pb-2">Latest Run Metrics</div>
                                    <div className="bg-muted/40 p-5 rounded-lg text-sm text-foreground font-mono border-2 border-border shadow-sm leading-relaxed h-full">
                                      {scan.metrics ? (
                                        <div className="flex flex-col gap-3">
                                          <div className="flex justify-between border-b border-border/50 pb-2"><span className="text-muted-foreground font-semibold">Scanned Targets:</span> <span className="font-bold">{scan.metrics.total_targets_scanned}</span></div>
                                          <div className="flex justify-between border-b border-border/50 pb-2"><span className="text-muted-foreground font-semibold">Duration:</span> <span className="font-bold">{scan.metrics.scan_duration_seconds}s</span></div>
                                          <div className={`flex justify-between ${scan.metrics.anomalies_found > 0 ? 'text-destructive' : 'text-green-600 dark:text-green-400'}`}>
                                            <span className="font-semibold text-muted-foreground">Anomalies:</span> <span className="font-extrabold">{scan.metrics.anomalies_found}</span>
                                          </div>
                                        </div>
                                      ) : (
                                        <div className="h-full flex items-center justify-center text-muted-foreground italic">No metrics available yet.</div>
                                      )}
                                    </div>
                                  </div>
                                </div>
                                
                                <div className="space-y-4">
                                  <div className="text-sm font-extrabold text-primary uppercase tracking-widest border-b-2 border-border/50 pb-2">Engine Flags</div>
                                  <div className="flex flex-wrap gap-3">
                                    {Object.entries(scan.flags).length === 0 ? (
                                      <span className="text-sm text-muted-foreground italic px-2">Using system defaults</span>
                                    ) : (
                                      Object.entries(scan.flags).map(([key, value]) => {
                                        const schema = EXECUTION_FLAGS_SCHEMA.find(s => s.name === key)
                                        const title = schema ? schema.title : key
                                        return (
                                          <div key={key} className="bg-background border-2 border-border px-3 py-2 rounded-lg text-xs font-mono shadow-sm flex items-center gap-2">
                                            <span className="text-muted-foreground font-semibold">{title}:</span>
                                            <span className="font-bold text-foreground text-sm">
                                              {typeof value === 'boolean' ? (value ? 'Yes' : 'No') : 
                                               Array.isArray(value) ? value.join(', ') : String(value)}
                                            </span>
                                          </div>
                                        )
                                      })
                                    )}
                                  </div>
                                </div>
                              </div>
                              <div className="flex flex-col gap-3 shrink-0 min-w-[140px]">
                                <Button variant="outline" className="text-primary border-2 border-primary/20 hover:bg-primary/10 hover:border-primary/40 font-bold justify-start px-4">
                                  ▶ Scan Now
                                </Button>
                                <Button variant="outline" className="border-2 border-border font-bold justify-start px-4" onClick={() => setEditingScanId(scan.id)}>
                                  ✎ Edit Schedule
                                </Button>
                                <AlertDialog>
                                  <AlertDialogTrigger render={
                                    <Button
                                      variant="outline"
                                      className="text-destructive hover:bg-destructive/10 hover:text-destructive border-2 border-destructive/20 hover:border-destructive/40 font-bold justify-start px-4"
                                    >
                                      ✕ Delete
                                    </Button>
                                  } />
                                  <AlertDialogContent className="border-2 border-border shadow-xl">
                                    <AlertDialogHeader>
                                      <AlertDialogTitle className="text-xl"><span className="text-destructive font-extrabold tracking-tight">Are you absolutely sure?</span></AlertDialogTitle>
                                      <AlertDialogDescription className="text-sm mt-2">
                                        This will permanently delete the <strong className="text-foreground">{scan.name}</strong> scheduled scan and clear its history.
                                      </AlertDialogDescription>
                                    </AlertDialogHeader>
                                    <AlertDialogFooter className="mt-4">
                                      <AlertDialogCancel className="border-2 font-bold">Cancel</AlertDialogCancel>
                                      <AlertDialogAction className="font-bold" onClick={() => handleDelete(scan.id)}>Delete</AlertDialogAction>
                                    </AlertDialogFooter>
                                  </AlertDialogContent>
                                </AlertDialog>
                              </div>
                            </div>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  )}
                </React.Fragment>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
