import {
  createBrowserRouter,
  createRoutesFromElements,
  Route,
} from 'react-router-dom'
import { RootLayout } from '@/components/layout/RootLayout'
import { HostTablePage } from '@/pages/HostTablePage'
import { LiveScanPage } from '@/pages/LiveScanPage'
import { ClassificationsPage } from '@/pages/ClassificationsPage'
import { ScheduledScansPage } from '@/pages/ScheduledScansPage'

export const router = createBrowserRouter(
  createRoutesFromElements(
    <Route path="/" element={<RootLayout />}>
      <Route index element={<HostTablePage />} />
      <Route path="scan" element={<LiveScanPage />} />
      <Route path="classifications" element={<ClassificationsPage />} />
      <Route path="scheduled-scans" element={<ScheduledScansPage />} />
    </Route>
  )
)
