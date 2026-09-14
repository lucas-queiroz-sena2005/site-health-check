export interface DetailsPanelProps {
  payload?: Record<string, any>
}

export function DetailsPanel({ payload }: DetailsPanelProps) {
  if (!payload) return null

  return (
    <tr className="bg-muted/50 border-b border-border">
      <td colSpan={5} className="p-4">
        <div className="grid grid-cols-2 gap-4 text-sm text-muted-foreground">
          {Object.entries(payload).map(([key, value]) => {
            // Basic formatting for arrays/objects
            const displayValue = typeof value === 'object' 
              ? JSON.stringify(value, null, 2) 
              : String(value)

            return (
              <div key={key} className="flex flex-col gap-1">
                <span className="font-medium text-foreground capitalize">
                  {key.replace(/_/g, ' ')}
                </span>
                <span className="break-all bg-background border border-border p-2 rounded-md font-mono text-xs">
                  {displayValue || '-'}
                </span>
              </div>
            )
          })}
        </div>
      </td>
    </tr>
  )
}
