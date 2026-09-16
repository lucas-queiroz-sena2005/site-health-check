import React from 'react'

export interface DetailsPanelProps {
  payload?: Record<string, any>
}

function Section({ title, data }: { title: string, data: Record<string, any> }) {
  if (!data || Object.keys(data).length === 0) return null
  return (
    <div className="bg-background border border-border rounded-lg overflow-hidden shadow-sm flex flex-col">
      <div className="bg-muted px-4 py-2 border-b border-border font-bold text-[10px] uppercase text-muted-foreground tracking-wider">
        {title}
      </div>
      <div className="p-4 grid grid-cols-2 gap-x-6 gap-y-3">
        {Object.entries(data).map(([key, value]) => {
          if (typeof value === 'object' && value !== null) {
             return (
               <div key={key} className="col-span-2 flex flex-col gap-1">
                 <span className="font-medium text-muted-foreground capitalize text-[10px] uppercase tracking-wider">{key.replace(/_/g, ' ')}</span>
                 <pre className="bg-muted/50 p-2 rounded border border-border text-[11px] font-mono break-words whitespace-pre-wrap">{JSON.stringify(value, null, 2)}</pre>
               </div>
             )
          }
          return (
            <div key={key} className="flex flex-col gap-0.5">
              <span className="font-medium text-muted-foreground capitalize text-[10px] uppercase tracking-wider">{key.replace(/_/g, ' ')}</span>
              <span className="text-foreground text-[13px] font-mono break-all">{String(value)}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export function DetailsPanel({ payload }: DetailsPanelProps) {
  if (!payload) return null

  // Extract structured details 
  const hostDetails = payload.host_details || payload.host_rogue_details
  const portDetails = payload.port_details
  const httpDetails = payload.http_details
  const voidDetails = payload.void_details
  
  // Extract target/root details by omitting the structured ones
  const rootDetails = { ...payload }
  delete rootDetails.host_details
  delete rootDetails.host_rogue_details
  delete rootDetails.port_details
  delete rootDetails.http_details
  delete rootDetails.void_details

  return (
    <tr className="bg-accent-bg/10 border-b border-border relative">
      <td colSpan={5} className="p-6">
        <div className="absolute left-0 top-0 bottom-0 w-1 bg-accent-border/50" />
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 items-start">
          <Section title="Target Summary" data={rootDetails} />
          {hostDetails && <Section title="Host Profile" data={hostDetails} />}
          {portDetails && <Section title="Port & TCP Layer" data={portDetails} />}
          {httpDetails && <Section title="HTTP Routing Layer" data={httpDetails} />}
          {voidDetails && <Section title="Void Configuration" data={voidDetails} />}
        </div>
      </td>
    </tr>
  )
}
