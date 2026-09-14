import { HierarchicalTable as MainHierarchicalTable, type HierarchicalTableProps } from './HierarchicalTable'
import { TableRow } from './TableRow'
import { TableCell } from './TableCell'

type HierarchicalTableComponent = React.FC<HierarchicalTableProps> & {
  Row: typeof TableRow
  Cell: typeof TableCell
}

const HierarchicalTable = MainHierarchicalTable as HierarchicalTableComponent
HierarchicalTable.Row = TableRow
HierarchicalTable.Cell = TableCell

export { HierarchicalTable }
export type { HierarchicalTableProps } from './HierarchicalTable'
export type { TableRowProps } from './TableRow'
export type { TableCellProps } from './TableCell'
export { RenderTreeNode } from './RenderTreeNode'
