export { cn } from "cn"

export async function extractApiErrorMessage(res: Response, fallback: string): Promise<string> {
  try {
    const data = await res.json()
    if (typeof data?.detail === 'string' && data.detail.trim()) {
      return data.detail.trim()
    }
    if (Array.isArray(data?.detail) && data.detail.length > 0) {
      return data.detail
        .map((item: { msg?: string; loc?: Array<string | number> }) => {
          const rawMsg = typeof item?.msg === 'string' ? item.msg : String(item)
          return rawMsg.replace(/^Value error,\s*/i, '').trim()
        })
        .filter(Boolean)
        .join(' • ')
    }
    if (typeof data?.error === 'string' && data.error.trim()) {
      return data.error.trim()
    }
  } catch {
    // Ignore JSON parse errors and fall back
  }
  return fallback
}

export function formatBytes(bytes: number, decimals = 1): string {
  if (bytes <= 0) return '0 B'
  const k = 1024
  const dm = decimals < 0 ? 0 : decimals
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`
}
