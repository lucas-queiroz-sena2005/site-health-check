import { useState } from 'react'
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

export type FieldSchema = {
  name: string
  title: string
  type: 'boolean' | 'number' | 'list'
  default: any
}

export const EXECUTION_FLAGS_SCHEMA: FieldSchema[] = [
  { name: 'check_tcp', title: 'Check TCP/TLS', type: 'boolean', default: true },
  { name: 'check_http', title: 'Check HTTP Routing', type: 'boolean', default: true },
  { name: 'recursive_san', title: 'Recursive SAN Check', type: 'boolean', default: false },
  { name: 'out_of_scope_depth', title: 'Out-of-Scope Depth', type: 'number', default: 0 },
  { name: 'check_virtual_hosts', title: 'Check Virtual Hosts', type: 'boolean', default: false },
  { name: 'spoof_user_agent', title: 'Spoof User Agent', type: 'boolean', default: false },
  { name: 'timeout', title: 'Timeout (seconds)', type: 'number', default: 10 },
  { name: 'expected', title: 'Expected HTML Strings', type: 'list', default: null },
  { name: 'undesired', title: 'Undesired HTML Strings', type: 'list', default: null },
  { name: 'workers', title: 'Workers', type: 'number', default: 100 },
  { name: 'delay', title: 'Worker Delay', type: 'number', default: 0.0 },
]

export const DEFAULT_NEW_SCAN = {
  name: 'New Scheduled Scan',
  cron_expression: '0 0 * * *',
  targets: [],
  ports: [80, 443],
  flags: { check_tcp: true, check_http: true, check_virtual_hosts: false, timeout: 10, workers: 100, delay: 0 },
}

export function ScanConfigForm({ 
  initialData = DEFAULT_NEW_SCAN, 
  onSave, 
  onCancel, 
  mode = 'schedule', 
  isCreating = false,
  isScanning = false
}: { 
  initialData?: any, 
  onSave: (data: any) => void, 
  onCancel?: () => void,
  mode?: 'schedule' | 'live',
  isCreating?: boolean,
  isScanning?: boolean
}) {
  const [form, setForm] = useState(initialData)
  const [isAlertOpen, setIsAlertOpen] = useState(false)

  const handleFlagChange = (name: string, value: any) => {
    setForm((prev: any) => ({
      ...prev,
      flags: {
        ...prev.flags,
        [name]: value,
      },
    }))
  }

  // Common wrapper class for form fields to improve contrast in light mode
  const fieldWrapperClass = "flex flex-col gap-2 rounded-lg border-2 border-black/10 dark:border-border p-4 shadow-sm bg-black/[0.03] dark:bg-card/50"
  const switchWrapperClass = "flex flex-row items-center justify-between rounded-lg border-2 border-black/10 dark:border-border p-4 shadow-sm bg-black/[0.03] dark:bg-card/50"

  return (
    <div className={`space-y-8 ${isCreating || mode === 'live' ? '' : 'bg-background p-6 rounded-lg border shadow-sm max-w-4xl'}`}>
      {mode === 'schedule' && (
        <div className="grid grid-cols-2 gap-6">
          <div className="space-y-2">
            <Label htmlFor="name" className="text-sm font-semibold">Scan Name</Label>
            <Input
              id="name"
              value={form?.name || ''}
              className="border-2 border-black/15 dark:border-white/10 bg-background shadow-sm h-11"
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="schedule" className="text-sm font-semibold">Cron Schedule</Label>
            <Input
              id="schedule"
              value={form?.cron_expression || ''}
              onChange={(e) => setForm({ ...form, cron_expression: e.target.value })}
              className="font-mono text-primary border-2 border-black/15 dark:border-white/10 bg-background shadow-sm h-11"
            />
          </div>
        </div>
      )}

      <div className="space-y-4">
        <h4 className="text-sm font-bold uppercase text-primary tracking-wider border-b-2 border-border/50 pb-2">
          Execution Config
        </h4>
        <div className="grid grid-cols-2 gap-x-8 gap-y-4">
          <div className={fieldWrapperClass}>
            <Label className="text-sm font-semibold">Targets (comma-separated)</Label>
            <Input
              type="text"
              defaultValue={initialData?.targets?.join(', ') || ''}
              className="bg-background border-black/15 dark:border-white/10"
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
          <div className={fieldWrapperClass}>
            <Label className="text-sm font-semibold">Ports (comma-separated)</Label>
            <Input
              type="text"
              defaultValue={initialData?.ports?.join(', ') || ''}
              className="bg-background border-black/15 dark:border-white/10"
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
        <h4 className="text-sm font-bold uppercase text-primary tracking-wider border-b-2 border-border/50 pb-2">
          Engine Flags
        </h4>
        <div className="grid grid-cols-2 gap-x-8 gap-y-4">
          {EXECUTION_FLAGS_SCHEMA.map((field) => {
            const val = form?.flags[field.name] !== undefined ? form.flags[field.name] : field.default

            if (field.type === 'boolean') {
              return (
                <div key={field.name} className={switchWrapperClass}>
                  <div className="space-y-0.5">
                    <Label className="text-sm font-semibold">{field.title}</Label>
                  </div>
                  <Switch checked={val} onCheckedChange={(c) => handleFlagChange(field.name, c)} />
                </div>
              )
            }

            if (field.type === 'number') {
              return (
                <div key={field.name} className={fieldWrapperClass}>
                  <Label className="text-sm font-semibold">{field.title}</Label>
                  <div className="flex items-center gap-1 mt-1">
                    <Button
                      variant="outline"
                      size="icon"
                      className="h-10 w-10 shrink-0 border-2"
                      onClick={() => handleFlagChange(field.name, field.name === 'workers' ? Math.max(1, Number(val) - 1) : Number(val) - 1)}
                    >
                      -
                    </Button>
                    <Input
                      type="number"
                      value={val}
                      className="text-center font-mono border-2 border-black/15 dark:border-white/10 bg-background h-10"
                      onChange={(e) => handleFlagChange(field.name, field.name === 'workers' ? Math.max(1, Number(e.target.value)) : Number(e.target.value))}
                    />
                    <Button
                      variant="outline"
                      size="icon"
                      className="h-10 w-10 shrink-0 border-2"
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
                <div key={field.name} className={`${fieldWrapperClass} col-span-2`}>
                  <Label className="text-sm font-semibold">{field.title} (comma-separated)</Label>
                  <Input
                    type="text"
                    defaultValue={strVal}
                    className="bg-background border-black/15 dark:border-white/10"
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

      <div className="flex justify-end gap-3 pt-6 border-t-2 border-border/50">
        {onCancel && (
          <Button variant="ghost" className="hover:bg-muted" onClick={onCancel} disabled={isScanning}>
            Cancel
          </Button>
        )}
        
        {mode === 'live' ? (
          <AlertDialog open={isAlertOpen} onOpenChange={setIsAlertOpen}>
            <AlertDialogTrigger 
              render={
                <Button size="lg" className="px-8 font-semibold shadow-sm" disabled={isScanning}>
                  {isScanning ? 'Scanning...' : '▶ Launch Live Scan'}
                </Button>
              } 
            />
            <AlertDialogContent className="border-2 border-border shadow-xl">
              <AlertDialogHeader>
                <AlertDialogTitle className="text-xl font-extrabold tracking-tight text-primary">Confirm Live Scan</AlertDialogTitle>
                <AlertDialogDescription className="text-sm mt-2 font-medium">
                  You are about to launch an ad-hoc live scan against <strong className="text-foreground">{form?.targets?.length || 0}</strong> targets.
                  This will consume engine workers and generate immediate network traffic. Proceed?
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter className="mt-4">
                <AlertDialogCancel className="border-2 font-bold">Cancel</AlertDialogCancel>
                <AlertDialogAction className="font-bold" onClick={() => { setIsAlertOpen(false); onSave(form); }}>Launch Scan</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        ) : (
          <Button size="lg" className="px-8 font-semibold shadow-sm" onClick={() => onSave(form)}>
            {isCreating ? 'Create Schedule' : 'Save Changes'}
          </Button>
        )}
      </div>
    </div>
  )
}
