import {
  createBrowserRouter,
  createRoutesFromElements,
  Route,
  Navigate,
} from 'react-router-dom'
import { RootLayout } from '@/components/layout/RootLayout'
import { HostTablePage } from '@/pages/HostTablePage'
import { LiveScanPage } from '@/pages/LiveScanPage'
import { ScheduledScansPage } from '@/pages/ScheduledScansPage'
import { SettingsPage } from '@/pages/SettingsPage'
import { ErrorPage } from '@/pages/ErrorPage'

export const router = createBrowserRouter(
  createRoutesFromElements(
    <Route path="/" element={<RootLayout />} errorElement={<ErrorPage />}>
      <Route index element={<HostTablePage />} />
      <Route path="scan" element={<LiveScanPage />} />
      <Route path="scheduled-scans" element={<ScheduledScansPage />} />
      <Route path="scheduled-runs" element={<ScheduledScansPage />} />
      <Route path="schedules" element={<Navigate to="/scheduled-runs" replace />} />
      <Route path="settings" element={<SettingsPage />} />
      <Route path="*" element={<ErrorPage />} />
    </Route>
  )
)
