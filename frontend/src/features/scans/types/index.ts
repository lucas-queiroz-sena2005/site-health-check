import { z } from 'zod'

export const PortStateSchema = z.object({
  port: z.number(),
  protocol: z.string(),
  state: z.string(),
  service: z.string().optional(),
})

export const HostStateSchema = z.object({
  ip: z.string(),
  hostname: z.string().optional(),
  status: z.string(),
  ports: z.array(PortStateSchema),
})

export const ScanResultSchema = z.object({
  id: z.string(),
  timestamp: z.string(),
  hosts: z.array(HostStateSchema),
})

export type PortState = z.infer<typeof PortStateSchema>
export type HostState = z.infer<typeof HostStateSchema>
export type ScanResult = z.infer<typeof ScanResultSchema>
