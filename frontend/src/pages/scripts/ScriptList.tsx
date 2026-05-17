/**
 * /scripts — 脚本列表页
 *
 * 设计契约:`进度/设计/前端UI设计.md` § 3.4(脚本列表 wireframe)、§ 4、§ 8。
 *
 * 页面结构:
 *   PageHeader(标题/描述/扫描按钮)
 *   工具栏(搜索 Input + 状态 Select + 视图切换 Tabs)
 *   ┌──────────── Tabs ────────────┐
 *   │ 卡片视图 → ScriptCard grid    │
 *   │ 表格视图 → DataTable          │
 *   └───────────────────────────────┘
 *
 * 数据 hooks:useScripts / useScanScripts / useEnableScript / useDisableScript / useDeleteScript
 *
 * 删除走 AlertDialog 二次确认,确认后调 DELETE /api/v1/scripts/{slug}?confirm=true。
 */
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router';
import { useDebounce } from '@/hooks/useDebounce';
import {
  Boxes,
  ExternalLink,
  Eye,
  LayoutGrid,
  Loader2,
  MoreHorizontal,
  Pause,
  PlayCircle,
  RefreshCw,
  Search,
  Table as TableIcon,
  Trash2,
  TriangleAlert,
} from 'lucide-react';
import type { ColumnDef } from '@tanstack/react-table';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

import DataTable from '@/components/common/DataTable';
import EmptyState from '@/components/common/EmptyState';
import PageHeader from '@/components/common/PageHeader';
import { ScriptCard, type ScriptCardData } from '@/components/common/ScriptCard';

import {
  useDeleteScript,
  useDisableScript,
  useEnableScript,
  useScanScripts,
  useScripts,
  type ScriptListItem,
} from '@/api/hooks/scripts';
import { formatRelative } from '@/lib/format';
import { cn } from '@/lib/utils';

type ViewMode = 'card' | 'table';
type EnabledFilter = 'all' | 'enabled' | 'disabled';

export function ScriptList() {
  const navigate = useNavigate();

  // === 状态:搜索 / 筛选 / 视图 ===
  const [searchRaw, setSearchRaw] = useState('');
  const search = useDebounce(searchRaw, 250);
  const [enabledFilter, setEnabledFilter] = useState<EnabledFilter>('all');
  const [view, setView] = useState<ViewMode>('card');

  // === 数据 ===
  const filter = useMemo(
    () => ({
      ...(enabledFilter === 'enabled'
        ? { enabled: true }
        : enabledFilter === 'disabled'
          ? { enabled: false }
          : {}),
      ...(search ? { search } : {}),
    }),
    [enabledFilter, search],
  );
  const { data: scripts, isLoading, isFetching, refetch } = useScripts(filter);

  // === Mutations ===
  const scan = useScanScripts();
  const enable = useEnableScript();
  const disable = useDisableScript();
  const remove = useDeleteScript();

  // === 删除二次确认 ===
  const [deleteTarget, setDeleteTarget] = useState<ScriptListItem | null>(null);

  // === 派生 ===
  const isEmpty = !isLoading && (!scripts || scripts.length === 0);
  const showFiltered = enabledFilter !== 'all' || !!search;

  // === 列定义(卡片视图不用,但表格视图用) ===
  const columns = useMemo<ColumnDef<ScriptListItem>[]>(
    () => [
      {
        id: 'name',
        accessorKey: 'name',
        header: '脚本',
        enableSorting: true,
        cell: ({ row }) => {
          const s = row.original;
          return (
            <div className="flex min-w-0 items-center gap-2.5">
              <ScriptInitial slug={s.slug} name={s.name} />
              <div className="min-w-0">
                <div className="truncate text-sm font-medium text-foreground">
                  {s.name}
                </div>
                <div className="truncate font-mono text-[11px] text-muted-foreground/80">
                  {s.slug}
                </div>
              </div>
            </div>
          );
        },
      },
      {
        accessorKey: 'version',
        header: '版本',
        enableSorting: true,
        cell: ({ getValue }) => (
          <span className="font-mono text-xs text-muted-foreground tabular-nums">
            v{(getValue() as string) ?? '—'}
          </span>
        ),
      },
      {
        accessorKey: 'instance_count',
        header: '实例',
        enableSorting: true,
        cell: ({ row }) => {
          const c = row.original.instance_count ?? 0;
          const e = row.original.instance_enabled_count ?? 0;
          return (
            <span className="tabular-nums text-sm text-foreground">
              {c}
              {c !== e ? (
                <span className="ml-1 text-xs text-muted-foreground">
                  ({e} 启用)
                </span>
              ) : null}
            </span>
          );
        },
      },
      {
        accessorKey: 'last_run_status',
        header: '上次执行',
        enableSorting: false,
        cell: ({ row }) => {
          const s = row.original.last_run_status;
          const at = row.original.last_run_at;
          return (
            <div className="flex items-center gap-2">
              <StatusDot status={s} />
              <span className="text-xs text-muted-foreground tabular-nums">
                {at ? formatRelative(at) : '—'}
              </span>
            </div>
          );
        },
      },
      {
        accessorKey: 'default_cron',
        header: 'cron',
        enableSorting: false,
        cell: ({ getValue }) => (
          <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground">
            {(getValue() as string) ?? '—'}
          </code>
        ),
      },
      {
        accessorKey: 'enabled',
        header: '状态',
        enableSorting: true,
        cell: ({ getValue }) =>
          (getValue() as boolean) ? (
            <Badge
              variant="outline"
              className="border-success/30 bg-success/10 font-normal text-success"
            >
              启用
            </Badge>
          ) : (
            <Badge
              variant="outline"
              className="border-muted-foreground/20 font-normal text-muted-foreground"
            >
              禁用
            </Badge>
          ),
      },
      {
        id: 'actions',
        header: '',
        enableHiding: false,
        cell: ({ row }) => {
          const s = row.original;
          return (
            <div className="flex justify-end">
              <ScriptRowMenu
                script={s}
                onView={() => navigate(`/scripts/${s.slug}`)}
                onToggle={() => {
                  if (s.enabled) {
                    disable.mutate(s.slug);
                  } else {
                    enable.mutate(s.slug);
                  }
                }}
                onDelete={() => setDeleteTarget(s)}
              />
            </div>
          );
        },
      },
    ],
    [navigate, enable, disable],
  );

  // === 操作:统一封装,卡片视图也复用 ===
  const handleScan = () => {
    scan.mutate();
  };

  return (
    <div className="mx-auto w-full max-w-[1440px] px-6 py-8">
      <PageHeader
        title="脚本"
        description={
          scripts && scripts.length > 0
            ? `已发现 ${scripts.length} 个插件,启用 ${scripts.filter((s) => s.enabled).length} 个`
            : '点击「扫描脚本」从 scripts/ 目录发现可用插件'
        }
        actions={
          <>
            <Button
              variant="outline"
              size="sm"
              onClick={() => refetch()}
              disabled={isFetching}
            >
              <RefreshCw
                className={cn('size-4', isFetching && 'animate-spin')}
                strokeWidth={1.75}
              />
              <span className="ml-1.5 hidden sm:inline">刷新</span>
            </Button>
            <Button onClick={handleScan} disabled={scan.isPending}>
              {scan.isPending ? (
                <Loader2 className="size-4 animate-spin" strokeWidth={1.75} />
              ) : (
                <RefreshCw className="size-4" strokeWidth={1.75} />
              )}
              <span className="ml-1.5">扫描脚本</span>
            </Button>
          </>
        }
      />

      {/* 工具栏 */}
      <div className="mb-5 flex flex-wrap items-center gap-2">
        <div className="relative min-w-0 flex-1 sm:max-w-sm">
          <Search
            className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground"
            strokeWidth={1.75}
          />
          <Input
            value={searchRaw}
            onChange={(e) => setSearchRaw(e.target.value)}
            placeholder="搜索脚本名 / slug / 描述..."
            className="h-9 pl-8 text-sm"
          />
        </div>
        <Select
          value={enabledFilter}
          onValueChange={(v) => setEnabledFilter(v as EnabledFilter)}
        >
          <SelectTrigger className="h-9 w-[120px] text-sm">
            <SelectValue placeholder="状态" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部</SelectItem>
            <SelectItem value="enabled">已启用</SelectItem>
            <SelectItem value="disabled">已禁用</SelectItem>
          </SelectContent>
        </Select>
        <div className="ml-auto">
          <Tabs value={view} onValueChange={(v) => setView(v as ViewMode)}>
            <TabsList className="h-9">
              <TabsTrigger
                value="card"
                className="h-7 gap-1.5 px-2.5 text-xs"
                aria-label="卡片视图"
              >
                <LayoutGrid className="size-3.5" strokeWidth={1.75} />
                卡片
              </TabsTrigger>
              <TabsTrigger
                value="table"
                className="h-7 gap-1.5 px-2.5 text-xs"
                aria-label="表格视图"
              >
                <TableIcon className="size-3.5" strokeWidth={1.75} />
                表格
              </TabsTrigger>
            </TabsList>
          </Tabs>
        </div>
      </div>

      {/* 空状态(无过滤时)*/}
      {isEmpty && !showFiltered ? (
        <div className="rounded-xl border-2 border-dashed border-border bg-card/30">
          <EmptyState
            icon={Boxes}
            title="还没有脚本"
            description="在 scripts/ 目录放入 manifest.yaml + main.py,然后点击下方按钮触发扫描"
            action={
              <Button onClick={handleScan} disabled={scan.isPending}>
                {scan.isPending ? (
                  <Loader2 className="size-4 animate-spin" strokeWidth={1.75} />
                ) : (
                  <RefreshCw className="size-4" strokeWidth={1.75} />
                )}
                <span className="ml-1.5">立即扫描</span>
              </Button>
            }
          />
        </div>
      ) : isEmpty && showFiltered ? (
        <div className="rounded-xl border-2 border-dashed border-border bg-card/30">
          <EmptyState
            icon={Search}
            title="没有匹配的脚本"
            description="尝试清空搜索或调整状态筛选"
            action={
              <Button
                variant="outline"
                onClick={() => {
                  setSearchRaw('');
                  setEnabledFilter('all');
                }}
              >
                清空筛选
              </Button>
            }
          />
        </div>
      ) : view === 'card' ? (
        <ScriptCardGrid
          scripts={scripts ?? []}
          loading={isLoading}
          onView={(slug) => navigate(`/scripts/${slug}`)}
          onRun={(slug) => navigate(`/scripts/${slug}?tab=instances`)}
          onConfigure={(slug) => navigate(`/scripts/${slug}`)}
        />
      ) : (
        <DataTable<ScriptListItem, unknown>
          columns={columns}
          data={scripts ?? []}
          loading={isLoading}
          onRowClick={(row) => navigate(`/scripts/${row.slug}`)}
          empty={
            <EmptyState
              icon={Boxes}
              title="没有匹配的脚本"
              description="尝试清空筛选或扫描"
            />
          }
        />
      )}

      {/* 删除二次确认 */}
      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <TriangleAlert
                className="size-5 text-danger"
                strokeWidth={1.75}
              />
              确认从登记中移除「{deleteTarget?.name}」?
            </AlertDialogTitle>
            <AlertDialogDescription>
              将级联删除此脚本下的所有实例与运行记录。
              <strong className="ml-1 text-foreground">
                磁盘文件不会被删除
              </strong>
              ,下次扫描仍可重新发现。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={remove.isPending}>
              取消
            </AlertDialogCancel>
            <AlertDialogAction
              className="bg-danger text-danger-foreground hover:bg-danger/90"
              disabled={remove.isPending}
              onClick={(e) => {
                e.preventDefault();
                if (!deleteTarget) return;
                remove.mutate(deleteTarget.slug, {
                  onSuccess: () => setDeleteTarget(null),
                });
              }}
            >
              {remove.isPending ? (
                <Loader2 className="mr-1.5 size-4 animate-spin" strokeWidth={1.75} />
              ) : (
                <Trash2 className="mr-1.5 size-4" strokeWidth={1.75} />
              )}
              确认移除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

// ============== 子组件 ==============

interface ScriptCardGridProps {
  scripts: ScriptListItem[];
  loading: boolean;
  onView: (slug: string) => void;
  onRun: (slug: string) => void;
  onConfigure: (slug: string) => void;
}

function ScriptCardGrid({
  scripts,
  loading,
  onView,
  onRun,
  onConfigure,
}: ScriptCardGridProps) {
  if (loading) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <div
            key={`sk-${i}`}
            className="h-[220px] animate-pulse rounded-xl border border-border bg-muted/30"
          />
        ))}
      </div>
    );
  }
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {scripts.map((s) => (
        <ScriptCard
          key={s.slug}
          script={toCardData(s)}
          onClick={onView}
          onTrigger={onRun}
          onConfigure={onConfigure}
        />
      ))}
    </div>
  );
}

function toCardData(s: ScriptListItem): ScriptCardData {
  return {
    slug: s.slug,
    name: s.name,
    description: s.description ?? null,
    version: s.version,
    enabled: s.enabled,
    instance_count: s.instance_count,
    instance_enabled_count: s.instance_enabled_count,
    last_run_status: s.last_run_status,
    last_run_at: s.last_run_at,
    next_run_at: s.next_run_at,
    success_rate_7d: s.success_rate_7d,
  };
}

function ScriptInitial({ slug, name }: { slug: string; name: string }) {
  // 与 ScriptCard 派色一致(slug → chart-N)
  let h = 0;
  for (let i = 0; i < slug.length; i += 1) h = (h * 31 + slug.charCodeAt(i)) | 0;
  const variant = (Math.abs(h) % 5) + 1;
  const first = name.trim()[0] ?? slug[0] ?? '·';
  const isAscii = /[A-Za-z]/.test(first);
  return (
    <div
      className="flex size-8 shrink-0 items-center justify-center rounded-md text-sm font-medium"
      style={{
        background: `color-mix(in oklch, var(--chart-${variant}) 14%, transparent)`,
        color: `var(--chart-${variant})`,
      }}
      aria-hidden
    >
      {isAscii ? first.toUpperCase() : first}
    </div>
  );
}

function StatusDot({
  status,
}: {
  status: ScriptListItem['last_run_status'];
}) {
  let color = 'text-muted-foreground/40';
  let pulse = false;
  switch (status) {
    case 'success':
      color = 'text-success';
      break;
    case 'failure':
    case 'error':
      color = 'text-danger';
      break;
    case 'timeout':
      color = 'text-warning';
      break;
    case 'running':
    case 'pending':
      color = 'text-info';
      pulse = true;
      break;
    default:
      break;
  }
  return (
    <span className={cn('relative inline-flex size-2 isolate', color)}>
      <span
        className={cn(
          'block size-2 rounded-full bg-current',
          pulse && 'dot-pulse',
        )}
      />
    </span>
  );
}

interface ScriptRowMenuProps {
  script: ScriptListItem;
  onView: () => void;
  onToggle: () => void;
  onDelete: () => void;
}

function ScriptRowMenu({
  script,
  onView,
  onToggle,
  onDelete,
}: ScriptRowMenuProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className="size-7 p-0"
          aria-label="操作"
          onClick={(e) => e.stopPropagation()}
        >
          <MoreHorizontal className="size-4" strokeWidth={1.75} />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        className="w-44"
        onClick={(e) => e.stopPropagation()}
      >
        <DropdownMenuLabel className="text-xs">脚本操作</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onClick={(e) => {
            e.stopPropagation();
            onView();
          }}
        >
          <Eye className="mr-2 size-3.5" strokeWidth={1.75} />
          详情
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={(e) => {
            e.stopPropagation();
            onToggle();
          }}
        >
          {script.enabled ? (
            <>
              <Pause className="mr-2 size-3.5" strokeWidth={1.75} />
              禁用
            </>
          ) : (
            <>
              <PlayCircle className="mr-2 size-3.5" strokeWidth={1.75} />
              启用
            </>
          )}
        </DropdownMenuItem>
        {script.homepage ? (
          <DropdownMenuItem
            onClick={(e) => {
              e.stopPropagation();
              window.open(script.homepage!, '_blank', 'noopener,noreferrer');
            }}
          >
            <ExternalLink className="mr-2 size-3.5" strokeWidth={1.75} />
            主页
          </DropdownMenuItem>
        ) : null}
        <DropdownMenuSeparator />
        <DropdownMenuItem
          className="text-danger focus:text-danger"
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
        >
          <Trash2 className="mr-2 size-3.5" strokeWidth={1.75} />
          移除登记
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export default ScriptList;
