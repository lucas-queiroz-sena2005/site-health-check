import { NavLink } from 'react-router-dom'
import { buttonVariants } from '@/components/ui/button'
import { ThemeSwitch } from '@/components/ui/theme-switch'

export function Header() {
  return (
    <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="w-full px-8 flex h-20 items-center justify-between">
        <div className="flex items-center gap-8">
          <div className="flex items-center">
            <span className="text-2xl font-extrabold tracking-tighter leading-none font-mono">domain observability tool</span>
          </div>
          <nav className="flex items-center gap-4">
            <NavLink
              to="/"
              className={({ isActive }) =>
                buttonVariants({ variant: isActive ? 'default' : 'ghost', size: 'lg' })
              }
            >
              Dashboard
            </NavLink>
            <NavLink
              to="/scan"
              className={({ isActive }) =>
                buttonVariants({ variant: isActive ? 'default' : 'ghost', size: 'lg' })
              }
            >
              Live Scan
            </NavLink>
            <NavLink
              to="/scheduled-scans"
              className={({ isActive }) =>
                buttonVariants({ variant: isActive ? 'default' : 'ghost', size: 'lg' })
              }
            >
              Scheduled Scans
            </NavLink>
          </nav>
        </div>
        <div className="flex items-center justify-end">
          <ThemeSwitch />
        </div>
      </div>
    </header>
  )
}
