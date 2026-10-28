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
  { name: 'check_http', title: 'Check HTTP Routing', type: 'boolean', default: true },
  { name: 'recursive_san', title: 'Recursive SAN Check', type: 'boolean', default: false },
  { name: 'out_of_scope_depth', title: 'Out-of-Scope Depth', type: 'number', default: 0 },
  { name: 'check_virtual_hosts', title: 'Check Virtual Hosts', type: 'boolean', default: false },
  { name: 'timeout', title: 'Timeout (seconds)', type: 'number', default: 10 },
  { name: 'workers', title: 'Workers', type: 'number', default: 100 },
  { name: 'rate', title: 'Rate Limit (req/s)', type: 'number', default: 50.0 },
]

export const DEFAULT_NEW_SCAN = {
  name: 'New Scheduled Scan',
  cron_expression: '0 0 * * *',
  targets: [],
  ports: [80, 443],
  flags: { check_http: true, check_virtual_hosts: false, timeout: 10, workers: 100, rate: 50.0 },
  ghost_window: '7d',
  tls_warning_days: 30,
  alert_config: {
    webhook_url: '',
    alert_on_failure: true,
    alert_on_ghost: true,
    alert_on_warning: true,
    alert_on_abort: true,
    alert_on_void: false,
    notify_on_healthy: false,
  },
}

export function ScanConfigForm({ 
  initialData = DEFAULT_NEW_SCAN, 
  onSave, 
  onCancel, 
  mode = 'schedule', 
  isCreating = false,
  isScanning = false,
  isSubmitting = false,
  errorMessage = null,
}: { 
  initialData?: any, 
  onSave: (data: any) => void | Promise<any>, 
  onCancel?: () => void,
  mode?: 'schedule' | 'live',
  isCreating?: boolean,
  isScanning?: boolean,
  isSubmitting?: boolean,
  errorMessage?: string | null,
}) {
  const [form, setForm] = useState(initialData)
  const [isAlertOpen, setIsAlertOpen] = useState(false)
  const [testingWebhook, setTestingWebhook] = useState(false)
  const [testStatus, setTestStatus] = useState<{ success: boolean; message: string } | null>(null)

  const clampFlagValue = (name: string, rawVal: number) => {
    if (Number.isNaN(rawVal)) return 0
    if (name === 'workers' || name === 'timeout') return Math.max(1, rawVal)
    if (name === 'rate') return Math.max(0.1, Number(rawVal.toFixed(2)))
    if (name === 'out_of_scope_depth') return Math.max(0, rawVal)
    return rawVal
  }

  const handleTestWebhook = async () => {
    const url = form?.alert_config?.webhook_url
    if (!url) return
    setTestingWebhook(true)
    setTestStatus(null)
    try {
      const resp = await fetch('/api/alerts/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ webhook_url: url }),
      })
      const data = await resp.json()
      if (data.success) {
        setTestStatus({ success: true, message: '✓ Test ping delivered successfully!' })
      } else {
        setTestStatus({ success: false, message: `✗ Failed: ${data.error || 'Unknown error'}` })
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      setTestStatus({ success: false, message: `✗ Network error: ${msg}` })
    } finally {
      setTestingWebhook(false)
    }
  }

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
              placeholder="e.g. 192.168.1.0/24, 10.0.0.1-10.0.0.50, github.com"
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
              placeholder="e.g. 80, 443, 8080-8090"
              onChange={(e) => {
                const arr = e.target.value
                  .split(',')
                  .map((s) => s.trim())
                  .filter(Boolean)
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
                      onClick={() => handleFlagChange(field.name, clampFlagValue(field.name, Number(val) - 1))}
                    >
                      -
                    </Button>
                    <Input
                      type="number"
                      value={val}
                      className="text-center font-mono border-2 border-black/15 dark:border-white/10 bg-background h-10"
                      onChange={(e) => handleFlagChange(field.name, clampFlagValue(field.name, Number(e.target.value)))}
                    />
                    <Button
                      variant="outline"
                      size="icon"
                      className="h-10 w-10 shrink-0 border-2"
                      onClick={() => handleFlagChange(field.name, clampFlagValue(field.name, Number(val) + 1))}
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

      <div className="space-y-4">
        <h4 className="text-sm font-bold uppercase text-primary tracking-wider border-b-2 border-border/50 pb-2">
          Evaluation Settings
        </h4>
        <div className="grid grid-cols-2 gap-x-8 gap-y-4">
          <div className={fieldWrapperClass}>
            <Label htmlFor="ghost_window" className="text-sm font-semibold">Ghost Window</Label>
            <Input
              id="ghost_window"
              value={form?.ghost_window || '7d'}
              className="bg-background border-black/15 dark:border-white/10"
              placeholder="e.g. 7d, 24h, 30m"
              onChange={(e) => setForm({ ...form, ghost_window: e.target.value })}
            />
            <span className="text-xs text-muted-foreground">Historical window to detect unresponsive hosts that were active</span>
          </div>
          <div className={fieldWrapperClass}>
            <Label htmlFor="tls_warning_days" className="text-sm font-semibold">TLS Expiry Warning (Days)</Label>
            <Input
              id="tls_warning_days"
              type="number"
              min={0}
              value={form?.tls_warning_days !== undefined ? form.tls_warning_days : 30}
              className="bg-background border-black/15 dark:border-white/10"
              placeholder="e.g. 30"
              onChange={(e) => setForm({ ...form, tls_warning_days: Math.max(0, Number(e.target.value)) })}
            />
            <span className="text-xs text-muted-foreground">Threshold to classify certificate expiration as a Warning</span>
          </div>
        </div>
      </div>

      {mode === 'schedule' && (
        <div className="space-y-4">
          <h4 className="text-sm font-bold uppercase text-primary tracking-wider border-b-2 border-border/50 pb-2">
            Alert Configuration
          </h4>
          <div className="space-y-4">
            <div className={fieldWrapperClass}>
              <Label htmlFor="webhook_url" className="text-sm font-semibold">Webhook URL (Google Chat / Slack)</Label>
              <div className="flex gap-2">
                <Input
                  id="webhook_url"
                  type="url"
                  value={form?.alert_config?.webhook_url || ''}
                  className="bg-background border-black/15 dark:border-white/10 flex-1"
                  placeholder="https://chat.googleapis.com/... or https://hooks.slack.com/..."
                  onChange={(e) => setForm({
                    ...form,
                    alert_config: {
                      ...(form.alert_config || {}),
                      webhook_url: e.target.value,
                    }
                  })}
                />
                <Button
                  type="button"
                  variant="outline"
                  disabled={!form?.alert_config?.webhook_url || testingWebhook}
                  onClick={handleTestWebhook}
                  className="shrink-0"
                >
                  {testingWebhook ? 'Testing...' : 'Test Webhook'}
                </Button>
              </div>
              {testStatus && (
                <div className={`text-xs mt-1 font-medium ${testStatus.success ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                  {testStatus.message}
                </div>
              )}
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className={switchWrapperClass}>
                <div className="space-y-0.5">
                  <Label className="text-sm font-semibold">Alert on Failures</Label>
                  <p className="text-xs text-muted-foreground">Host unreachable, port closed, or HTTP 5xx</p>
                </div>
                <Switch
                  checked={form?.alert_config?.alert_on_failure ?? true}
                  onCheckedChange={(c) => setForm({
                    ...form,
                    alert_config: { ...(form.alert_config || {}), alert_on_failure: c }
                  })}
                />
              </div>

              <div className={switchWrapperClass}>
                <div className="space-y-0.5">
                  <Label className="text-sm font-semibold">Alert on Ghost Hosts</Label>
                  <p className="text-xs text-muted-foreground">Inactive host with past open ports</p>
                </div>
                <Switch
                  checked={form?.alert_config?.alert_on_ghost ?? true}
                  onCheckedChange={(c) => setForm({
                    ...form,
                    alert_config: { ...(form.alert_config || {}), alert_on_ghost: c }
                  })}
                />
              </div>

              <div className={switchWrapperClass}>
                <div className="space-y-0.5">
                  <Label className="text-sm font-semibold">Alert on Warnings</Label>
                  <p className="text-xs text-muted-foreground">TLS certificate expiring soon or invalid</p>
                </div>
                <Switch
                  checked={form?.alert_config?.alert_on_warning ?? true}
                  onCheckedChange={(c) => setForm({
                    ...form,
                    alert_config: { ...(form.alert_config || {}), alert_on_warning: c }
                  })}
                />
              </div>

              <div className={switchWrapperClass}>
                <div className="space-y-0.5">
                  <Label className="text-sm font-semibold">Alert on Abort / Crash</Label>
                  <p className="text-xs text-muted-foreground">Scan process terminated or crashed</p>
                </div>
                <Switch
                  checked={form?.alert_config?.alert_on_abort ?? true}
                  onCheckedChange={(c) => setForm({
                    ...form,
                    alert_config: { ...(form.alert_config || {}), alert_on_abort: c }
                  })}
                />
              </div>

              <div className={switchWrapperClass}>
                <div className="space-y-0.5">
                  <Label className="text-sm font-semibold">Alert on Void Hosts</Label>
                  <p className="text-xs text-muted-foreground">Unresponsive host with no past activity</p>
                </div>
                <Switch
                  checked={form?.alert_config?.alert_on_void ?? false}
                  onCheckedChange={(c) => setForm({
                    ...form,
                    alert_config: { ...(form.alert_config || {}), alert_on_void: c }
                  })}
                />
              </div>

              <div className={switchWrapperClass}>
                <div className="space-y-0.5">
                  <Label className="text-sm font-semibold">Notify on Healthy Runs</Label>
                  <p className="text-xs text-muted-foreground">Send notification when all checks pass</p>
                </div>
                <Switch
                  checked={form?.alert_config?.notify_on_healthy ?? false}
                  onCheckedChange={(c) => setForm({
                    ...form,
                    alert_config: { ...(form.alert_config || {}), notify_on_healthy: c }
                  })}
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {errorMessage && (
        <div
          role="alert"
          data-testid="form-error-banner"
          className="rounded-lg border-2 border-destructive/40 bg-destructive/10 px-4 py-3 text-sm font-semibold text-destructive shadow-sm"
        >
          {errorMessage}
        </div>
      )}

      <div className="flex justify-end gap-3 pt-6 border-t-2 border-border/50">
        {onCancel && (
          <Button variant="ghost" className="hover:bg-muted" disabled={isSubmitting} onClick={onCancel}>
            {mode === 'live' ? 'Detach' : 'Cancel'}
          </Button>
        )}
        
        {mode === 'live' ? (
          <AlertDialog open={isAlertOpen} onOpenChange={setIsAlertOpen}>
            <AlertDialogTrigger 
              render={
                <Button
                  size="lg"
                  className="px-8 font-semibold shadow-sm"
                  disabled={isScanning || isSubmitting || !form?.targets || form.targets.length === 0}
                >
                  {isScanning ? 'Scanning...' : isSubmitting ? 'Launching...' : '▶ Launch Live Scan'}
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
                <AlertDialogCancel className="border-2 font-bold" disabled={isSubmitting}>Cancel</AlertDialogCancel>
                <AlertDialogAction
                  className="font-bold"
                  disabled={isSubmitting || isScanning}
                  onClick={async () => {
                    try {
                      await onSave(form)
                    } finally {
                      setIsAlertOpen(false)
                    }
                  }}
                >
                  {isSubmitting ? 'Launching...' : 'Launch Scan'}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        ) : (
          <Button
            size="lg"
            className="px-8 font-semibold shadow-sm"
            disabled={isSubmitting}
            onClick={() => onSave(form)}
          >
            {isSubmitting
              ? isCreating
                ? 'Creating...'
                : 'Saving...'
              : isCreating
                ? 'Create Schedule'
                : 'Save Changes'}
          </Button>
        )}
      </div>
    </div>
  )
}
