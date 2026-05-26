/**
 * <DataTable> — 基于 TanStack Table 8 + shadcn <Table> 的通用数据表
 *
 * 设计契约:`进度/设计/前端UI设计.md` § 4(公共组件清单)、§ 8(表格美化)。
 * 参考:https://ui.shadcn.com/docs/components/data-table
 *
 * 支持:
 *   - 泛型 columns / data
 *   - loading skeleton(8 行)
 *   - 客户端分页 / 服务端分页(显式传 pagination prop)
 *   - 列排序(列头点击,降序 / 升序 / 无)
 *   - 列可见性切换(右上角下拉)
 *   - 行 hover 高亮(shadcn 默认)
 *   - 空状态展示(emptyState ReactNode)
 *   - 行点击(onRowClick;不要与列内按钮冲突,内层按钮请 stopPropagation)
 *
 * 用法:
 *   ```tsx
 *   const cols: ColumnDef<MyRow>[] = [
 *     { accessorKey: 'name', header: '名称' },
 *     { accessorKey: 'count', header: '数量', enableSorting: true },
 *   ];
 *   <DataTable
 *     columns={cols}
 *     data={rows}
 *     loading={isLoading}
 *     empty={<EmptyState ... />}
 *     onRowClick={(row) => navigate(`/x/${row.id}`)}
 *   />
 *   ```
 *
 * 注意:
 *   - 不强制要求服务端分页;若 pagination prop 缺省,启用 TanStack Table 内置客户端分页(默认 10/页)
 *   - 服务端分页时把 `manualPagination` 与 `pageCount` 配置好;本组件根据 pagination.total 推算 pageCount
 *   - columnVisibility 状态留在组件内部(不 persist;persist 可由调用方包 useLocalStorage 注入)
 */
import { useMemo, useState, type ReactNode } from 'react';
import {
  flexRender,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type PaginationState,
  type SortingState,
  type Table as TanstackTable,
  type VisibilityState,
} from '@tanstack/react-table';
import {
  ArrowDown,
  ArrowUp,
  ChevronLeft,
  ChevronRight,
  ChevronsUpDown,
  Settings2,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { cn } from '@/lib/utils';

export interface DataTablePagination {
  /** 当前页(0-based 内部,1-based 外部)— 外部传 1-based,内部按 TanStack 0-based 处理 */
  page: number;
  pageSize: number;
  total: number;
  onChange: (next: { page: number; pageSize: number }) => void;
  /** 可选自定义页码大小选项 */
  pageSizeOptions?: number[];
}

export interface DataTableProps<TData, TValue> {
  columns: ColumnDef<TData, TValue>[];
  data: TData[];
  loading?: boolean;
  /** 服务端分页时传;不传则使用客户端分页 */
  pagination?: DataTablePagination;
  /** 空数据态:推荐传 <EmptyState />;若不传则用默认文字 */
  empty?: ReactNode;
  /** 行点击;无 → 行不可点 */
  onRowClick?: (row: TData) => void;
  /** 表格右上工具栏(在 column visibility 下拉左侧);例如视图切换、筛选下拉 */
  toolbar?: ReactNode;
  /** 显式隐藏 column visibility 下拉(简化场景) */
  hideColumnVisibility?: boolean;
  /** 表格最外层类名 */
  className?: string;
  /** 行 id 提取(用于 key 与 selection;不传则用 index) */
  getRowId?: (row: TData, index: number) => string;
}

export function DataTable<TData, TValue>({
  columns,
  data,
  loading = false,
  pagination,
  empty,
  onRowClick,
  toolbar,
  hideColumnVisibility = false,
  className,
  getRowId,
}: DataTableProps<TData, TValue>) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>({});

  const isServerPaginated = !!pagination;

  // 内部分页 state(仅在客户端分页时使用)
  const [internalPagination, setInternalPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 10,
  });

  // 当 pagination prop 存在 → 服务端模式,使用 prop 控制
  const tablePagination: PaginationState = useMemo(() => {
    if (pagination) {
      return {
        pageIndex: Math.max(0, pagination.page - 1),
        pageSize: pagination.pageSize,
      };
    }
    return internalPagination;
  }, [pagination, internalPagination]);

  const pageCount = useMemo(() => {
    if (pagination) {
      return Math.max(1, Math.ceil(pagination.total / Math.max(1, pagination.pageSize)));
    }
    return undefined; // 客户端模式 → TanStack 自己算
  }, [pagination]);

  const table = useReactTable<TData>({
    data,
    columns,
    state: {
      sorting,
      columnVisibility,
      pagination: tablePagination,
    },
    onSortingChange: setSorting,
    onColumnVisibilityChange: setColumnVisibility,
    onPaginationChange: (updater) => {
      const next =
        typeof updater === 'function' ? updater(tablePagination) : updater;
      if (isServerPaginated && pagination) {
        pagination.onChange({
          page: next.pageIndex + 1,
          pageSize: next.pageSize,
        });
      } else {
        setInternalPagination(next);
      }
    },
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: isServerPaginated ? undefined : getPaginationRowModel(),
    manualPagination: isServerPaginated,
    pageCount,
    getRowId: getRowId
      ? (row, idx) => getRowId(row, idx)
      : undefined,
  });

  const rows = table.getRowModel().rows;
  const showEmpty = !loading && rows.length === 0;
  const totalRowsLabel = isServerPaginated
    ? pagination!.total
    : data.length;

  return (
    <div className={cn('flex w-full flex-col gap-3', className)}>
      {/* 顶部工具条:左侧用户传入的 toolbar,右侧列可见性 */}
      {toolbar || !hideColumnVisibility ? (
        <div className="flex items-center justify-between gap-3">
          <div className="flex flex-1 items-center gap-2">{toolbar}</div>
          {hideColumnVisibility ? null : (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="outline"
                  size="sm"
                  className="ml-auto h-8 gap-1.5"
                >
                  <Settings2 className="size-3.5" strokeWidth={1.75} />
                  <span>列</span>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-40">
                <DropdownMenuLabel className="text-xs">显隐</DropdownMenuLabel>
                <DropdownMenuSeparator />
                {table
                  .getAllColumns()
                  .filter((c) => c.getCanHide())
                  .map((c) => (
                    <DropdownMenuCheckboxItem
                      key={c.id}
                      className="capitalize"
                      checked={c.getIsVisible()}
                      onCheckedChange={(v) => c.toggleVisibility(!!v)}
                    >
                      {flexHeaderLabel(c.columnDef.header) || c.id}
                    </DropdownMenuCheckboxItem>
                  ))}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      ) : null}

      {/* 表格 — 外层保留 rounded-xl + overflow-hidden 给 border-radius,
            内层 overflow-auto 让 mobile 列多时可横滚 + 大 pageSize 时可纵滚
            🟢 LOW · code-review #14:改 overflow-x-auto → overflow-auto
            外层 overflow-hidden 只 clip border-radius;若 pageSize 高 + DataTable
            放进 fixed-height 容器,外层裁会丢底行 → 内层接管 y 才安全。
            对小 pageSize(默认 10)+ 无 fixed-height 容器场景行为不变(无副作用) */}
      <div className="overflow-hidden rounded-xl border border-border bg-card shadow-xs">
        <div className="overflow-auto">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((hg) => (
              <TableRow
                key={hg.id}
                className="bg-muted/30 hover:bg-muted/30"
              >
                {hg.headers.map((h) => {
                  const canSort = h.column.getCanSort();
                  const sort = h.column.getIsSorted();
                  return (
                    <TableHead
                      key={h.id}
                      className={cn(
                        'h-10 text-xs font-medium text-muted-foreground',
                        canSort && 'cursor-pointer select-none',
                      )}
                      onClick={
                        canSort
                          ? () => h.column.toggleSorting(sort === 'asc')
                          : undefined
                      }
                    >
                      <span className="inline-flex items-center gap-1">
                        {h.isPlaceholder
                          ? null
                          : flexRender(
                              h.column.columnDef.header,
                              h.getContext(),
                            )}
                        {canSort ? (
                          <span aria-hidden className="text-muted-foreground/60">
                            {sort === 'asc' ? (
                              <ArrowUp className="size-3" strokeWidth={1.75} />
                            ) : sort === 'desc' ? (
                              <ArrowDown className="size-3" strokeWidth={1.75} />
                            ) : (
                              <ChevronsUpDown className="size-3" strokeWidth={1.75} />
                            )}
                          </span>
                        ) : null}
                      </span>
                    </TableHead>
                  );
                })}
              </TableRow>
            ))}
          </TableHeader>

          <TableBody>
            {loading ? (
              <DataTableSkeletonRows
                rows={8}
                columns={table.getVisibleLeafColumns().length}
              />
            ) : showEmpty ? (
              <TableRow className="hover:bg-transparent">
                <TableCell
                  colSpan={table.getVisibleLeafColumns().length}
                  className="p-0"
                >
                  {empty ?? (
                    <div className="flex w-full items-center justify-center px-6 py-16 text-sm text-muted-foreground">
                      暂无数据
                    </div>
                  )}
                </TableCell>
              </TableRow>
            ) : (
              rows.map((row) => (
                <TableRow
                  key={row.id}
                  className={cn(
                    'transition-colors',
                    onRowClick && 'cursor-pointer',
                  )}
                  onClick={onRowClick ? () => onRowClick(row.original) : undefined}
                  data-state={row.getIsSelected() ? 'selected' : undefined}
                >
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id} className="py-3 align-middle">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
        </div>
      </div>

      {/* 分页栏 — 仅当数据 > 0 或在服务端模式下显示 */}
      {!loading && (rows.length > 0 || isServerPaginated) ? (
        <DataTablePaginationBar
          table={table}
          totalRows={totalRowsLabel}
          isServer={isServerPaginated}
          pageSizeOptions={pagination?.pageSizeOptions}
        />
      ) : null}
    </div>
  );
}

// ---------- 内部小组件 ----------

function DataTableSkeletonRows({
  rows,
  columns,
}: {
  rows: number;
  columns: number;
}) {
  return (
    <>
      {Array.from({ length: rows }).map((_, i) => (
        <TableRow key={`sk-${i}`} className="hover:bg-transparent">
          {Array.from({ length: columns }).map((__, j) => (
            <TableCell key={`sk-${i}-${j}`} className="py-3">
              <Skeleton className="h-4 w-full max-w-[120px]" />
            </TableCell>
          ))}
        </TableRow>
      ))}
    </>
  );
}

function DataTablePaginationBar<TData>({
  table,
  totalRows,
  isServer,
  pageSizeOptions,
}: {
  table: TanstackTable<TData>;
  totalRows: number;
  isServer: boolean;
  pageSizeOptions?: number[];
}) {
  const pageIndex = table.getState().pagination.pageIndex;
  const pageSize = table.getState().pagination.pageSize;
  const pageCount = table.getPageCount();
  const sizeOptions = pageSizeOptions ?? [10, 20, 50, 100];

  const from = totalRows === 0 ? 0 : pageIndex * pageSize + 1;
  const to = Math.min(totalRows, (pageIndex + 1) * pageSize);

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-muted-foreground">
      <div className="tabular-nums">
        共 <span className="font-medium text-foreground">{totalRows}</span> 条
        {totalRows > 0 ? (
          <span className="ml-2 text-muted-foreground/70">
            · 当前 {from}–{to}
          </span>
        ) : null}
      </div>
      <div className="flex items-center gap-2">
        <select
          className="h-7 rounded-md border border-input bg-background px-2 text-xs focus:outline-none focus:ring-2 focus:ring-ring"
          value={pageSize}
          onChange={(e) => table.setPageSize(Number(e.target.value))}
        >
          {sizeOptions.map((opt) => (
            <option key={opt} value={opt}>
              {opt}/页
            </option>
          ))}
        </select>
        <span className="tabular-nums">
          第 {pageIndex + 1} / {Math.max(1, pageCount)} 页
        </span>
        <div className="flex items-center gap-1">
          <Button
            variant="outline"
            size="sm"
            className="size-7 p-0"
            disabled={!table.getCanPreviousPage()}
            onClick={() => table.previousPage()}
            aria-label="上一页"
          >
            <ChevronLeft className="size-3.5" strokeWidth={1.75} />
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="size-7 p-0"
            disabled={!table.getCanNextPage() && !isServer}
            onClick={() => table.nextPage()}
            aria-label="下一页"
          >
            <ChevronRight className="size-3.5" strokeWidth={1.75} />
          </Button>
        </div>
      </div>
    </div>
  );
}

/**
 * Column header 可能是 string / 函数 / ReactNode;
 * column visibility 菜单只取得能展示的字符串 label;
 * 复杂自定义 header(函数)时直接返回空让上层兜底用 column.id。
 */
function flexHeaderLabel(header: unknown): string {
  if (typeof header === 'string') return header;
  return '';
}

export default DataTable;
