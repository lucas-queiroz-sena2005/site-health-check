import { RouterProvider } from 'react-router-dom'
import { router } from '@/routes/router'
import { ThemeProvider } from '@/components/theme-provider'

export default function App() {
  return (
    <ThemeProvider defaultTheme="dark" storageKey="site-health-theme">
      <RouterProvider router={router} />
    </ThemeProvider>
  )
}
