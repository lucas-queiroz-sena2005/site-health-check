import { useTheme } from '@/components/theme-provider'
import { Switch } from '@/components/ui/switch'

export function ThemeSwitch() {
  const { resolvedTheme, setTheme } = useTheme()
  const isDark = resolvedTheme === 'dark'

  return (
    <Switch
      checked={isDark}
      onCheckedChange={(checked: boolean) =>
        setTheme(checked ? 'dark' : 'light')
      }
    />
  )
}
