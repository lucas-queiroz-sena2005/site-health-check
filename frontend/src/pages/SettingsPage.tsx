import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
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
import { formatBytes } from '@/lib/utils'

interface SystemSettings {
  retention_days: number
  db_size_bytes: number
  total_runs: number
  total_hosts: number
  total_scans: number
}

export function SettingsPage() {
  const queryClient = useQueryClient()
  const [retentionDays, setRetentionDays] = useState<number>(0)
  const [statusMessage, setStatusMessage] = useState<string | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const [purgeOpen, setPurgeOpen] = useState(false)
  const [resetOpen, setResetOpen] = useState(false)

  const { data: settings, isLoading } = useQuery<SystemSettings>({
    queryKey: ['system-settings'],
    queryFn: async () => {
      const res = await fetch('/api/system/settings')
      if (!res.ok) throw new Error('Failed to fetch system settings')
      return res.json()
    },
  })

  useEffect(() => {
    if (settings) {
      setRetentionDays(settings.retention_days)
    }
  }, [settings])

  const saveMutation = useMutation({
    mutationFn: async (days: number) => {
      setStatusMessage(null)
      setErrorMessage(null)
      const res = await fetch('/api/system/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ retention_days: days }),
      })
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        throw new Error(errData.detail || 'Failed to update retention policy')
      }
      return res.json()
    },
    onSuccess: (data: SystemSettings) => {
      queryClient.setQueryData(['system-settings'], data)
      setStatusMessage('Retention policy updated successfully.')
      setTimeout(() => setStatusMessage(null), 4000)
    },
    onError: (err: Error) => {
      setErrorMessage(err.message)
    },
  })

  const purgeMutation = useMutation({
    mutationFn: async () => {
      setStatusMessage(null)
      setErrorMessage(null)
      const res = await fetch('/api/system/purge-runs', { method: 'POST' })
      if (!res.ok) throw new Error('Failed to purge scan runs')
      return res.json()
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['system-settings'] })
      queryClient.invalidateQueries({ queryKey: ['runs'] })
      setPurgeOpen(false)
      setStatusMessage(data.message || 'Scan history purged successfully.')
      setTimeout(() => setStatusMessage(null), 5000)
    },
    onError: (err: Error) => {
      setErrorMessage(err.message)
    },
  })

  const resetMutation = useMutation({
    mutationFn: async () => {
      setStatusMessage(null)
      setErrorMessage(null)
      const res = await fetch('/api/system/reset-db', { method: 'POST' })
      if (!res.ok) throw new Error('Failed to reset database')
      return res.json()
    },
    onSuccess: () => {
      queryClient.clear()
      setResetOpen(false)
      setStatusMessage('Database reset to factory defaults successfully.')
      setTimeout(() => setStatusMessage(null), 5000)
    },
    onError: (err: Error) => {
      setErrorMessage(err.message)
    },
  })

  const handleSaveRetention = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const form = e.currentTarget
    const input = form.elements.namedItem('retention_days') as HTMLInputElement | null
    const days = input ? Math.max(0, parseInt(input.value, 10) || 0) : retentionDays
    saveMutation.mutate(days)
  }

  return (
    <div className="p-8 w-full h-full max-w-5xl mx-auto flex flex-col gap-8">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">System Settings</h2>
        <p className="text-muted-foreground mt-1">
          Monitor persistent database storage and configure automated data retention policies.
        </p>
      </div>

      {statusMessage && (
        <div
          role="status"
          className="rounded-lg border-2 border-green-500/30 bg-green-500/10 px-4 py-3 text-sm font-semibold text-green-700 dark:text-green-400"
        >
          {statusMessage}
        </div>
      )}

      {errorMessage && (
        <div
          role="alert"
          className="rounded-lg border-2 border-destructive/40 bg-destructive/10 px-4 py-3 text-sm font-semibold text-destructive"
        >
          {errorMessage}
        </div>
      )}

      {/* Storage & Statistics */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card className="border-2 border-border shadow-sm">
          <CardHeader className="pb-2">
            <CardDescription className="font-bold uppercase tracking-wider text-[11px]">Database Size</CardDescription>
            <CardTitle className="text-2xl font-extrabold font-mono text-primary">
              {isLoading ? '...' : formatBytes(settings?.db_size_bytes || 0)}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card className="border-2 border-border shadow-sm">
          <CardHeader className="pb-2">
            <CardDescription className="font-bold uppercase tracking-wider text-[11px]">Total Runs</CardDescription>
            <CardTitle className="text-2xl font-extrabold font-mono">
              {isLoading ? '...' : settings?.total_runs ?? 0}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card className="border-2 border-border shadow-sm">
          <CardHeader className="pb-2">
            <CardDescription className="font-bold uppercase tracking-wider text-[11px]">Indexed Hosts</CardDescription>
            <CardTitle className="text-2xl font-extrabold font-mono">
              {isLoading ? '...' : settings?.total_hosts ?? 0}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card className="border-2 border-border shadow-sm">
          <CardHeader className="pb-2">
            <CardDescription className="font-bold uppercase tracking-wider text-[11px]">Schedules</CardDescription>
            <CardTitle className="text-2xl font-extrabold font-mono">
              {isLoading ? '...' : settings?.total_scans ?? 0}
            </CardTitle>
          </CardHeader>
        </Card>
      </div>

      {/* Data Retention Policy */}
      <Card className="border-2 border-border shadow-sm">
        <CardHeader>
          <CardTitle className="text-lg font-bold">Data Retention Policy</CardTitle>
          <CardDescription>
            Automatically purge completed, failed, and aborted scan runs older than a set number of days.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSaveRetention} className="space-y-4 max-w-md">
            <div className="space-y-2">
              <Label htmlFor="retention_days" className="font-semibold text-sm">
                Retention Period (Days)
              </Label>
              <Input
                id="retention_days"
                name="retention_days"
                type="number"
                min={0}
                value={retentionDays}
                onChange={(e) => setRetentionDays(Math.max(0, parseInt(e.target.value) || 0))}
                className="font-mono text-base"
              />
              <p className="text-xs text-muted-foreground">
                Set to <strong>0</strong> to disable automatic purging and retain all history forever.
              </p>
            </div>
            <Button type="submit" disabled={saveMutation.isPending} className="font-semibold shadow-sm">
              {saveMutation.isPending ? 'Saving...' : 'Save Retention Policy'}
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Danger Zone */}
      <Card className="border-2 border-destructive/30 bg-destructive/5 shadow-sm">
        <CardHeader>
          <CardTitle className="text-lg font-bold text-destructive">Danger Zone</CardTitle>
          <CardDescription className="text-muted-foreground">
            Irreversible maintenance operations affecting stored database records.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-destructive/20">
            <div>
              <h4 className="font-bold text-sm text-foreground">Purge Run History</h4>
              <p className="text-xs text-muted-foreground mt-0.5">
                Permanently delete all historical scan runs, hosts, and port results. Scheduled scans and views are preserved.
              </p>
            </div>
            <AlertDialog open={purgeOpen} onOpenChange={setPurgeOpen}>
              <AlertDialogTrigger render={
                <Button variant="outline" className="border-destructive/40 text-destructive hover:bg-destructive hover:text-destructive-foreground font-semibold shrink-0">
                  Purge History
                </Button>
              } />
              <AlertDialogContent className="border-2 border-border shadow-xl">
                <AlertDialogHeader>
                  <AlertDialogTitle className="text-xl font-extrabold text-destructive">
                    Purge All Scan History?
                  </AlertDialogTitle>
                  <AlertDialogDescription className="text-sm mt-2 font-medium">
                    This will permanently delete all scan runs, host discovery lineages, certificates, and routing checks from SQLite.
                    Your scheduled scans and saved views will NOT be deleted. This cannot be undone.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter className="mt-4">
                  <AlertDialogCancel className="font-semibold" disabled={purgeMutation.isPending}>
                    Cancel
                  </AlertDialogCancel>
                  <AlertDialogAction
                    className="bg-destructive text-destructive-foreground hover:bg-destructive/90 font-bold"
                    disabled={purgeMutation.isPending}
                    onClick={() => purgeMutation.mutate()}
                  >
                    {purgeMutation.isPending ? 'Purging...' : 'Confirm Purge'}
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>

          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <h4 className="font-bold text-sm text-foreground">Factory Reset Database</h4>
              <p className="text-xs text-muted-foreground mt-0.5">
                Drop all tables, recreate schema from scratch, and reset system settings. All data is wiped.
              </p>
            </div>
            <AlertDialog open={resetOpen} onOpenChange={setResetOpen}>
              <AlertDialogTrigger render={
                <Button variant="destructive" className="font-bold shrink-0">
                  Factory Reset DB
                </Button>
              } />
              <AlertDialogContent className="border-2 border-border shadow-xl">
                <AlertDialogHeader>
                  <AlertDialogTitle className="text-xl font-extrabold text-destructive">
                    Factory Reset Database?
                  </AlertDialogTitle>
                  <AlertDialogDescription className="text-sm mt-2 font-medium">
                    This will completely drop and recreate all SQLite tables and vacuum the disk database. All scheduled scans, run histories, views, and settings will be permanently lost.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter className="mt-4">
                  <AlertDialogCancel className="font-semibold" disabled={resetMutation.isPending}>
                    Cancel
                  </AlertDialogCancel>
                  <AlertDialogAction
                    className="bg-destructive text-destructive-foreground hover:bg-destructive/90 font-bold"
                    disabled={resetMutation.isPending}
                    onClick={() => resetMutation.mutate()}
                  >
                    {resetMutation.isPending ? 'Resetting...' : 'Confirm Factory Reset'}
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
