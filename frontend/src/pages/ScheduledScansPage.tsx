import React, { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
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

type FieldSchema = {
  name: string
  title: string
  type: 'boolean' | 'number' | 'list'
  default: any
}

const EXECUTION_FLAGS_SCHEMA: FieldSchema[] = [
  { name: 'check_tcp', title: 'Check TCP/TLS', type: 'boolean', default: true },
  { name: 'check_http', title: 'Check HTTP Routing', type: 'boolean', default: true },
  { name: 'recursive_san', title: 'Recursive SAN Check', type: 'boolean', default: false },
  { name: 'out_of_scope_depth', title: 'Out-of-Scope Depth', type: 'number', default: 0 },
  { name: 'check_virtual_hosts', title: 'Check Virtual Hosts', type: 'boolean', default: true },
  { name: 'spoof_user_agent', title: 'Spoof User Agent', type: 'boolean', default: false },
  { name: 'timeout', title: 'Timeout (seconds)', type: 'number', default: 10 },
  { name: 'expected', title: 'Expected HTML Strings', type: 'list', default: null },
  { name: 'undesired', title: 'Undesired HTML Strings', type: 'list', default: null },
  { name: 'workers', title: 'Async Workers', type: 'number', default: 100 },
  { name: 'delay', title: 'Worker Delay', type: 'number', default: 0.0 },
]

const DEFAULT_NEW_SCAN = {
  name: 'New Scheduled Scan',
  schedule: '0 0 * * *',
  targets: [],
  ports: [80, 443],
  flags: { check_tcp: true, check_http: true, check_virtual_hosts: true, timeout: 10, workers: 100, delay: 0 },
}

function ScheduleForm({
  initialData,
  onSave,
  onCancel,
  isCreating = false,
}: {
  initialData: any
  onSave: (data: any) => void
  onCancel: () => void
  isCreating?: boolean
}) {
  const [form, setForm] = useState(initialData)

  const handleFlagChange = (name: string, value: any) => {
    setForm((prev: any) => ({
      ...prev,
      flags: {
        ...prev.flags,
        [name]: value,
      },
    }))
  }

  return (
    <div className={`space-y-6 bg-background rounded-lg ${isCreating ? '' : 'p-6 border shadow-sm max-w-4xl'}`}>
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="name">Name</Label>
          <Input
            id="name"
            value={form?.name || ''}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="schedule">Cron Schedule</Label>
          <Input
            id="schedule"
            value={form?.schedule || ''}
            onChange={(e) => setForm({ ...form, schedule: e.target.value })}
            className="font-mono text-primary"
          />
        </div>
      </div>

      <div className="space-y-4">
        <h4 className="text-sm font-semibold uppercase text-muted-foreground tracking-wider border-b pb-2">
          Execution Config
        </h4>
        <div className="grid grid-cols-2 gap-x-8 gap-y-4">
          <div className="flex flex-col gap-2 rounded-lg border p-3 shadow-sm bg-card">
            <Label className="text-sm">Targets (comma-separated)</Label>
            <Input
              type="text"
              value={form?.targets?.join(', ') || ''}
              placeholder="e.g. 192.168.1.0/24, 10.0.0.1-50, github.com"
              onChange={(e) => {
                const arr = e.target.value
                  .split(',')
                  .map((s) => s.trim())
                  .filter(Boolean)
                setForm({ ...form, targets: arr })
              }}
            />
          </div>
          <div className="flex flex-col gap-2 rounded-lg border p-3 shadow-sm bg-card">
            <Label className="text-sm">Ports (comma-separated)</Label>
            <Input
              type="text"
              value={form?.ports?.join(', ') || ''}
              placeholder="e.g. 80, 443"
              onChange={(e) => {
                const arr = e.target.value
                  .split(',')
                  .map((s) => parseInt(s.trim(), 10))
                  .filter((n) => !isNaN(n))
                setForm({ ...form, ports: arr })
              }}
            />
          </div>
        </div>
      </div>

      <div className="space-y-4">
        <h4 className="text-sm font-semibold uppercase text-muted-foreground tracking-wider border-b pb-2">
          Engine Flags
        </h4>
        <div className={`grid grid-cols-2 gap-x-8 gap-y-4 ${isCreating ? 'max-h-[30vh] overflow-y-auto p-1' : ''}`}>
          {EXECUTION_FLAGS_SCHEMA.map((field) => {
            const val = form?.flags[field.name] !== undefined ? form.flags[field.name] : field.default

            if (field.type === 'boolean') {
              return (
                <div key={field.name} className="flex flex-row items-center justify-between rounded-lg border p-3 shadow-sm bg-card">
                  <div className="space-y-0.5">
                    <Label className="text-sm">{field.title}</Label>
                  </div>
                  <Switch checked={val} onCheckedChange={(c) => handleFlagChange(field.name, c)} />
                </div>
              )
            }

            if (field.type === 'number') {
              return (
                <div key={field.name} className="flex flex-col gap-2 rounded-lg border p-3 shadow-sm bg-card">
                  <Label className="text-sm">{field.title}</Label>
                  <div className="flex items-center gap-1">
                    <Button
                      variant="outline"
                      size="icon"
                      className="h-9 w-9 shrink-0"
                      onClick={() => handleFlagChange(field.name, Number(val) - 1)}
                    >
                      -
                    </Button>
                    <Input
                      type="number"
                      value={val}
                      className="text-center font-mono"
                      onChange={(e) => handleFlagChange(field.name, Number(e.target.value))}
                    />
                    <Button
                      variant="outline"
                      size="icon"
                      className="h-9 w-9 shrink-0"
                      onClick={() => handleFlagChange(field.name, Number(val) + 1)}
                    >
                      +
                    </Button>
                  </div>
                </div>
              )
            }

            if (field.type === 'list') {
              const strVal = Array.isArray(val) ? val.join(', ') : val || ''
              return (
                <div key={field.name} className="flex flex-col gap-2 rounded-lg border p-3 shadow-sm bg-card col-span-2">
                  <Label className="text-sm">{field.title} (comma-separated)</Label>
                  <Input
                    type="text"
                    value={strVal}
                    placeholder="e.g. login, dashboard"
                    onChange={(e) => {
                      const arr = e.target.value
                        .split(',')
                        .map((s) => s.trim())
                        .filter(Boolean)
                      handleFlagChange(field.name, arr.length > 0 ? arr : null)
                    }}
                  />
                </div>
              )
            }

            return null
          })}
        </div>
      </div>

      <div className="flex justify-end gap-2 pt-4 border-t mt-4">
        <Button variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        <Button onClick={() => onSave(form)}>
          {isCreating ? 'Create Schedule' : 'Save Changes'}
        </Button>
      </div>
    </div>
  )
}

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
          <DialogTrigger render={<Button>+ Create New Schedule</Button>} />
          <DialogContent className="sm:max-w-4xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle className="text-xl">Create New Scheduled Scan</DialogTitle>
            </DialogHeader>
            <div className="mt-4">
              <ScheduleForm
                initialData={DEFAULT_NEW_SCAN}
                onSave={handleCreate}
                onCancel={() => setIsCreateModalOpen(false)}
                isCreating={true}
              />
            </div>
          </DialogContent>
        </Dialog>
      </div>

      <div className="rounded-md border bg-card text-card-foreground shadow">
        <Table>
          <TableHeader className="bg-muted/50">
            <TableRow>
              <TableHead className="w-[30px]"></TableHead>
              <TableHead>Scan Name</TableHead>
              <TableHead>Cron Schedule</TableHead>
              <TableHead>Last Run</TableHead>
              <TableHead>Next Run</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {scans.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="h-24 text-center text-muted-foreground">
                  No scheduled scans found.
                </TableCell>
              </TableRow>
            ) : (
              scans.map((scan) => (
                <React.Fragment key={scan.id}>
                  <TableRow
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={() => {
                      setExpandedScanId(expandedScanId === scan.id ? null : scan.id)
                      if (editingScanId === scan.id) setEditingScanId(null)
                    }}
                  >
                    <TableCell className="p-4">
                      <svg
                        className={`w-4 h-4 transform transition-transform text-muted-foreground duration-200 ${
                          expandedScanId === scan.id ? 'rotate-90 text-foreground' : ''
                        }`}
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M9 5l7 7-7 7" />
                      </svg>
                    </TableCell>
                    <TableCell className="font-semibold">{scan.name}</TableCell>
                    <TableCell className="font-mono text-primary font-bold">{scan.schedule}</TableCell>
                    <TableCell className="text-muted-foreground">{scan.lastRun}</TableCell>
                    <TableCell className="font-semibold text-green-600 dark:text-green-500">{scan.nextRun}</TableCell>
                  </TableRow>
                  {expandedScanId === scan.id && (
                    <TableRow className="bg-muted/10 hover:bg-muted/10">
                      <TableCell colSpan={5} className="p-0">
                        <div className="p-6 border-b">
                          {editingScanId === scan.id ? (
                            <ScheduleForm
                              initialData={scan}
                              onSave={(data) => handleSaveInline(scan.id, data)}
                              onCancel={() => setEditingScanId(null)}
                            />
                          ) : (
                            <div className="flex items-start justify-between">
                              <div className="space-y-6 w-full pr-8">
                                <div className="grid grid-cols-2 gap-4">
                                  <div>
                                    <div className="text-xs font-bold text-muted-foreground uppercase tracking-wider mb-3">Targets & Ports</div>
                                    <div className="flex flex-col gap-2">
                                      <div className="bg-background border px-3 py-1.5 rounded-md text-xs shadow-sm flex items-start gap-2">
                                        <span className="text-muted-foreground mt-0.5">Targets:</span>
                                        <span className="font-bold text-foreground font-mono whitespace-pre-wrap break-all">
                                          {scan.targets.length > 0 ? scan.targets.join(', ') : 'None specified'}
                                        </span>
                                      </div>
                                      <div className="bg-background border px-3 py-1.5 rounded-md text-xs shadow-sm flex items-start gap-2">
                                        <span className="text-muted-foreground mt-0.5">Ports:</span>
                                        <span className="font-bold text-foreground font-mono">
                                          {scan.ports.length > 0 ? scan.ports.join(', ') : 'None specified'}
                                        </span>
                                      </div>
                                    </div>
                                  </div>
                                  <div>
                                    <div className="text-xs font-bold text-muted-foreground uppercase tracking-wider mb-2">Latest Run Metrics</div>
                                    <div className="bg-muted/50 px-4 py-3 rounded-lg text-sm text-foreground font-mono border max-w-3xl leading-relaxed">
                                      {scan.metrics ? (
                                        <div className="flex flex-col gap-1">
                                          <div><span className="text-muted-foreground">Scanned Targets:</span> {scan.metrics.total_targets_scanned}</div>
                                          <div><span className="text-muted-foreground">Duration:</span> {scan.metrics.scan_duration_seconds}s</div>
                                          <div className={scan.metrics.anomalies_found > 0 ? 'text-destructive font-bold' : 'text-green-600 dark:text-green-400 font-bold'}>
                                            <span className="text-muted-foreground font-normal">Anomalies:</span> {scan.metrics.anomalies_found}
                                          </div>
                                        </div>
                                      ) : (
                                        <span className="text-muted-foreground italic">No metrics available yet.</span>
                                      )}
                                    </div>
                                  </div>
                                </div>
                                
                                <div>
                                  <div className="text-xs font-bold text-muted-foreground uppercase tracking-wider mb-3">Engine Flags</div>
                                  <div className="flex flex-wrap gap-2">
                                    {Object.entries(scan.flags).length === 0 ? (
                                      <span className="text-sm text-muted-foreground italic">Using system defaults</span>
                                    ) : (
                                      Object.entries(scan.flags).map(([key, value]) => {
                                        const schema = EXECUTION_FLAGS_SCHEMA.find(s => s.name === key)
                                        const title = schema ? schema.title : key
                                        return (
                                          <div key={key} className="bg-background border px-3 py-1.5 rounded-md text-xs font-mono shadow-sm flex items-center gap-2">
                                            <span className="text-muted-foreground">{title}:</span>
                                            <span className="font-bold text-foreground">
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
                              <div className="flex flex-col gap-2 shrink-0">
                                <Button variant="outline" className="text-primary border-primary/30 hover:bg-primary/10">
                                  ▶ Scan Now
                                </Button>
                                <Button variant="outline" onClick={() => setEditingScanId(scan.id)}>
                                  ✎ Edit Schedule
                                </Button>
                                <AlertDialog>
                                  <AlertDialogTrigger render={
                                    <Button
                                      variant="outline"
                                      className="text-destructive hover:bg-destructive/10 hover:text-destructive border-border"
                                    >
                                      ✕ Delete
                                    </Button>
                                  } />
                                  <AlertDialogContent>
                                    <AlertDialogHeader>
                                      <AlertDialogTitle><span className="text-destructive">Are you absolutely sure?</span></AlertDialogTitle>
                                      <AlertDialogDescription>
                                        This will permanently delete the "{scan.name}" scheduled scan.
                                      </AlertDialogDescription>
                                    </AlertDialogHeader>
                                    <AlertDialogFooter>
                                      <AlertDialogCancel>Cancel</AlertDialogCancel>
                                      <AlertDialogAction onClick={() => handleDelete(scan.id)}>Delete</AlertDialogAction>
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
