import { useTheme } from '@/components/theme-provider'
import { Button } from '@/components/ui/button'

export function ThemeSwitch() {
  const { resolvedTheme, setTheme } = useTheme()
  const isDark = resolvedTheme === 'dark'

  return (
    <Button
      variant="secondary"
      size="lg"
      onClick={() => setTheme(isDark ? 'light' : 'dark')}
    >
      {isDark ? 'Light Mode' : 'Dark Mode'}
    </Button>
  )
}
