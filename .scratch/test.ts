import { compressTreeNodes } from '../frontend/src/features/scans/utils/compressTree'
import type { TreeNode } from '../frontend/src/features/scans/types'

const host143: TreeNode = {
  id: "host-1",
  type: "Host",
  label: "143.106.1.6",
  status: "neutral",
  children: [
    {
      id: "port-1",
      type: "Port",
      label: "443/tcp",
      status: "success",
      children: [
        {
          id: "http-1",
          type: "HTTP",
          label: "HTTP 200 (legacy.unicamp.br)",
          status: "success",
          children: []
        }
      ]
    }
  ]
}

const compressed = compressTreeNodes(host143)
console.log(JSON.stringify(compressed, null, 2))
