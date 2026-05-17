/**
 * /instances — 全局实例列表
 *
 * 设计契约:`进度/设计/前端UI设计.md` § 3.5、§ 4(公共组件)、§ 8(状态点 / 派色)。
 *
 * 与脚本详情页的「实例 Tab」(InstancesPanel) 不同:
 *   - 这里跨脚本聚合,顶部筛选 script_slug / enabled / status
 *   - 表格视图(DataTable),列展示 icon + name + slug + cron + 上次/下次 + 总数 + 操作菜单
 *   - 点行 → 跳 /scripts/:slug/instances/:id(实例详情路由)
 *   - "新建实例" → InstanceFormSheet,需要先选 script_slug
 */
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router';
import {
  Activity,
  Boxes,
  CalendarClock,
  Clock,
  Loader2,
  MoreHorizontal,
  Pause,
  Play,
  PlayCircle,
  RefreshCw,
  RotateCcw,
  Search,
  Settings2,
  Sparkles,
  Trash2,
  TriangleAlert,
} from 'lucide-react';
import type { ColumnDef } from '@tanstack/react-table';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
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
import InstanceFormSheet from '@/components/common/InstanceFormSheet';
import PageHeader from '@/components/common/PageHeader';
import StatusBadge, { type Status } from '@/components/common/StatusBadge';

import {
  useDeleteInstance,
  useDisableInstance,
  useEnableInstance,
  useInstances,
  usePauseInstance,
  useResumeInstance,
  useTriggerInstance,
  type InstanceListItem,
} from '@/api/hooks/instances';
import { useScript, useScripts } from '@/api/hooks/scripts';
import { useDebounce } from '@/hooks/useDebounce';
import { formatRelative } from '@/lib/format';
import { cn } from '@/lib/utils';

type EnabledFilter = 'all' | 'enabled' | 'disabled' | 'paused';

function instanceStatusToBadge(s?: string | null): Status {
  switch (s) {
    case 'success':
      return 'success';
    case 'failure':
    case 'error':
    case 'timeout':
    case 'cancelled':
      return 'failure';
    case 'running':
      return 'running';
    case 'pending':
      return 'pending';
    default:
      return 'unknown';
  }
}

function isPausedActive(inst: InstanceListItem): boolean {
  return !!inst.paused_until && new Date(inst.paused_until).getTime() > Date.now();
}

/** slug → chart-1..5 派色一致,与 ScriptCard / ScriptList 行内 icon 同算法 */
function slugVariant(slug: string): number {
  let h = 0;
  for (let i = 0; i < slug.length; i += 1) h = (h * 31 + slug.charCodeAt(i)) | 0;
  return (Math.abs(h) % 5) + 1;
}

function getInstanceSlug(inst: InstanceListItem): string {
  return inst.script?.slug ?? inst.script_slug ?? '';
}

export function InstanceList() {
  const navigate = useNavigate();

  // 搜索 / 筛选 state
  const [searchRaw, setSearchRaw] = useState('');
  const search = useDebounce(searchRaw, 250);
  const [scriptFilter, setScriptFilter] = useState<string>('__all__');
  const [enabledFilter, setEnabledFilter] = useState<EnabledFilter>('all');

  const filterArg = useMemo(
    () => ({
      ...(scriptFilter !== '__all__' ? { script_slug: scriptFilter } : {}),
      ...(enabledFilter === 'enabled' ? { enabled: true } : {}),
      ...(enabledFilter === 'disabled' ? { enabled: false } : {}),
    }),
    [scriptFilter, enabledFilter],
  );

  const { data: rawInstances, isLoading, isFetching, refetch } = useInstances(filterArg);
  const { data: scripts } = useScripts();

  // 客户端 name 模糊 + paused 过滤(后端 enabled=true 仍包含 paused)
  const instances = useMemo(() => {
    let out = rawInstances ?? [];
    if (enabledFilter === 'paused') {
      out = out.filter(isPausedActive);
    }
    if (search && search.trim()) {
      const q = search.trim().toLowerCase();
      out = out.filter(
        (i) =>
          i.name.toLowerCase().includes(q) ||
          getInstanceSlug(i).toLowerCase().includes(q) ||
          (i.description ?? '').toLowerCase().includes(q),
      );
    }
    return out;
  }, [rawInstances, search, enabledFilter]);

  const total = rawInstances?.length ?? 0;
  const enabledCount = (rawInstances ?? []).filter((i) => i.enabled).length;
  const pausedCount = (rawInstances ?? []).filter(isPausedActive).length;

  // 操作
  const enable = useEnableInstance();
  const disable = useDisableInstance();
  const pause = usePauseInstance();
  const resume = useResumeInstance();
  const trigger = useTriggerInstance();
  const remove = useDeleteInstance();

  // 新建/编辑/删除 state
  const [sheetOpen, setSheetOpen] = useState(false);
  const [createScriptSlug, setCreateScriptSlug] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<InstanceListItem | null>(null);
  const [pauseTarget, setPauseTarget] = useState<InstanceListItem | null>(null);

  // 当用户点了"新建实例"按钮:若已筛选 script_slug → 直接打开 sheet,否则用一个小弹窗让用户选脚本
  const [pickScriptOpen, setPickScriptOpen] = useState(false);
  // 加载选中脚本详情(InstanceFormSheet 需要 fields_schema)
  const { data: createScript } = useScript(createScriptSlug ?? undefined);

  function openCreate() {
    if (scriptFilter !== '__all__') {
      setCreateScriptSlug(scriptFilter);
      setSheetOpen(true);
    } else {
      setPickScriptOpen(true);
    }
  }

  function handleSheetChange(open: boolean) {
    setSheetOpen(open);
    if (!open) {
      setCreateScriptSlug(null);
    }
  }

  async function handlePauseConfirm() {
    if (!pauseTarget) return;
    const until = new Date(Date.now() + 60 * 60 * 1000).toISOString();
    await pause.mutateAsync({
      id: pauseTarget.id,
      payload: { until },
      scriptSlug: getInstanceSlug(pauseTarget),
    });
    setPauseTarget(null);
  }

  // ============ columns ============
  const columns = useMemo<ColumnDef<InstanceListItem>[]>(
    () => [
      {
        id: 'name',
        accessorKey: 'name',
        header: '实例',
        enableSorting: true,
        cell: ({ row }) => {
          const inst = row.original;
          const slug = getInstanceSlug(inst);
          const variant = slugVariant(slug);
          const initial = (inst.name ?? slug).trim()[0] ?? '·';
          return (
            <div className="flex min-w-0 items-center gap-2.5">
              <div
                className="flex size-8 shrink-0 items-center justify-center rounded-md text-sm font-medium"
                style={{
                  background: `color-mix(in oklch, var(--chart-${variant}) 14%, transparent)`,
                  color: `var(--chart-${variant})`,
                }}
                aria-hidden
              >
                {initial.toUpperCase()}
              </div>
              <div className="min-w-0">
                <div className="truncate text-sm font-medium text-foreground">
                  {inst.name}
                </div>
                <div className="truncate font-mono text-[11px] text-muted-foreground/80">
                  {slug || '—'}
                </div>
              </div>
            </div>
          );
        },
      },
      {
        accessorKey: 'cron_expr',
        header: 'cron',
        enableSorting: false,
        cell: ({ getValue }) => {
          const v = getValue() as string | null | undefined;
          return v ? (
            <code className="truncate rounded bg-muted px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground">
              {v}
            </code>
          ) : (
            <span className="text-[11px] text-muted-foreground/60">—</span>
          );
        },
      },
      {
        id: 'last_run',
        header: '上次执行',
        enableSorting: false,
        cell: ({ row }) => {
          const r = row.original;
          return (
            <div className="flex min-w-0 items-center gap-2">
              <StatusBadge status={instanceStatusToBadge(r.last_run_status)} dotOnly />
              <span className="truncate text-xs text-muted-foreground tabular-nums">
                {r.last_run_at ? formatRelative(r.last_run_at) : '—'}
              </span>
            </div>
          );
        },
      },
      {
        accessorKey: 'next_run_at',
        header: '下次',
        enableSorting: false,
        cell: ({ getValue }) => {
          const v = getValue() as string | null | undefined;
          return (
            <span className="text-xs text-muted-foreground tabular-nums">
              {v ? formatRelative(v) : '—'}
            </span>
          );
        },
      },
      {
        id: 'totals',
        header: '执行 / 成功',
        enableSorting: false,
        cell: ({ row }) => {
          const r = row.original;
          return (
            <span className="text-xs tabular-nums">
              <span className="font-medium text-foreground">{r.total_runs ?? 0}</span>
              <span className="mx-0.5 text-muted-foreground/60">/</span>
              <span className="text-success">{r.total_successes ?? 0}</span>
            </span>
          );
        },
      },
      {
        id: 'status',
        header: '状态',
        enableSorting: false,
        cell: ({ row }) => {
          const r = row.original;
          if (isPausedActive(r)) {
            return (
              <Badge variant="outline" className="border-warning/30 bg-warning/10 text-warning">
                <Pause className="mr-1 size-3" strokeWidth={1.75} />
                暂停中
              </Badge>
            );
          }
          if (r.enabled) {
            return (
              <Badge variant="outline" className="border-success/30 bg-success/10 text-success">
                启用
              </Badge>
            );
          }
          return (
            <Badge variant="outline" className="text-muted-foreground">
              禁用
            </Badge>
          );
        },
      },
      {
        id: 'actions',
        header: '',
        enableHiding: false,
        cell: ({ row }) => {
          const inst = row.original;
          const slug = getInstanceSlug(inst);
          const paused = isPausedActive(inst);
          return (
            <div className="flex justify-end">
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
                  <DropdownMenuLabel className="text-xs">实例操作</DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    onClick={(e) => {
                      e.stopPropagation();
                      navigate(`/scripts/${slug}/instances/${inst.id}`);
                    }}
                  >
                    <Settings2 className="mr-2 size-3.5" strokeWidth={1.75} />
                    详情
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    onClick={(e) => {
                      e.stopPropagation();
                      trigger.mutate({ id: inst.id, scriptSlug: slug });
                    }}
                    disabled={trigger.isPending}
                  >
                    {trigger.isPending ? (
                      <Loader2 className="mr-2 size-3.5 animate-spin" strokeWidth={1.75} />
                    ) : (
                      <Play className="mr-2 size-3.5" strokeWidth={1.75} />
                    )}
                    立即运行
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    onClick={(e) => {
                      e.stopPropagation();
                      if (inst.enabled) {
                        disable.mutate({ id: inst.id, scriptSlug: slug });
                      } else {
                        enable.mutate({ id: inst.id, scriptSlug: slug });
                      }
                    }}
                  >
                    {inst.enabled ? (
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
                  {paused ? (
                    <DropdownMenuItem
                      onClick={(e) => {
                        e.stopPropagation();
                        resume.mutate({ id: inst.id, scriptSlug: slug });
                      }}
                    >
                      <RotateCcw className="mr-2 size-3.5" strokeWidth={1.75} />
                      立即恢复
                    </DropdownMenuItem>
                  ) : (
                    <DropdownMenuItem
                      onClick={(e) => {
                        e.stopPropagation();
                        setPauseTarget(inst);
                      }}
                    >
                      <Pause className="mr-2 size-3.5" strokeWidth={1.75} />
                      暂停 1 小时
                    </DropdownMenuItem>
                  )}
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    className="text-danger focus:text-danger"
                    onClick={(e) => {
                      e.stopPropagation();
                      setDeleteTarget(inst);
                    }}
                  >
                    <Trash2 className="mr-2 size-3.5" strokeWidth={1.75} />
                    删除实例
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          );
        },
      },
    ],
    [disable, enable, navigate, resume, trigger],
  );

  const description =
    total > 0
      ? `共 ${total} 个实例 · 启用 ${enabledCount} 个${pausedCount > 0 ? ` · 暂停 ${pausedCount} 个` : ''}`
      : '尚未创建任何实例,先去脚本页选一个脚本';
  const hasFilter =
    scriptFilter !== '__all__' || enabledFilter !== 'all' || !!search;

  return (
    <div className="mx-auto w-full max-w-[1440px] px-6 py-8">
      <PageHeader
        title="实例"
        description={description}
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
            <Button onClick={openCreate}>
              <Sparkles className="size-4" strokeWidth={1.75} />
              <span className="ml-1.5">新建实例</span>
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
            placeholder="搜索实例名 / slug / 备注..."
            className="h-9 pl-8 text-sm"
          />
        </div>
        <Select value={scriptFilter} onValueChange={(v) => setScriptFilter(v)}>
          <SelectTrigger className="h-9 w-[200px] text-sm">
            <SelectValue placeholder="脚本" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">全部脚本</SelectItem>
            {(scripts ?? []).map((s) => (
              <SelectItem key={s.slug} value={s.slug}>
                {s.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          value={enabledFilter}
          onValueChange={(v) => setEnabledFilter(v as EnabledFilter)}
        >
          <SelectTrigger className="h-9 w-[120px] text-sm">
            <SelectValue placeholder="状态" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部状态</SelectItem>
            <SelectItem value="enabled">已启用</SelectItem>
            <SelectItem value="disabled">已禁用</SelectItem>
            <SelectItem value="paused">暂停中</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* 表格 / 空态 */}
      {!isLoading && instances.length === 0 && !hasFilter ? (
        <div className="rounded-xl border-2 border-dashed border-border bg-card/30">
          <EmptyState
            icon={Boxes}
            title="尚未创建实例"
            description="实例是脚本的具体配置(账号/cookie/cron/超时);先去脚本页选一个脚本"
            action={
              <Button onClick={() => navigate('/scripts')}>
                <Activity className="size-4" strokeWidth={1.75} />
                <span className="ml-1.5">去脚本页</span>
              </Button>
            }
          />
        </div>
      ) : !isLoading && instances.length === 0 && hasFilter ? (
        <div className="rounded-xl border-2 border-dashed border-border bg-card/30">
          <EmptyState
            icon={Search}
            title="没有匹配的实例"
            description="尝试清空搜索或调整筛选"
            action={
              <Button
                variant="outline"
                onClick={() => {
                  setSearchRaw('');
                  setScriptFilter('__all__');
                  setEnabledFilter('all');
                }}
              >
                清空筛选
              </Button>
            }
          />
        </div>
      ) : (
        <DataTable<InstanceListItem, unknown>
          columns={columns}
          data={instances}
          loading={isLoading}
          onRowClick={(row) =>
            navigate(`/scripts/${getInstanceSlug(row)}/instances/${row.id}`)
          }
          getRowId={(row) => String((row as InstanceListItem).id)}
          empty={
            <EmptyState
              icon={Boxes}
              title="尚未创建实例"
              description="点击右上角「新建实例」开始,或先去脚本页"
            />
          }
        />
      )}

      {/* 选脚本 dialog(用户没选筛选 script,点新建时弹) */}
      <AlertDialog open={pickScriptOpen} onOpenChange={setPickScriptOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <Sparkles className="size-5 text-primary" strokeWidth={1.75} />
              选择脚本
            </AlertDialogTitle>
            <AlertDialogDescription>
              新建实例前需要选择目标脚本(实例承载具体账号 / cookie / cron)。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="py-2">
            <Select
              value={createScriptSlug ?? ''}
              onValueChange={(v) => setCreateScriptSlug(v)}
            >
              <SelectTrigger className="h-10 w-full">
                <SelectValue placeholder="选择脚本..." />
              </SelectTrigger>
              <SelectContent>
                {(scripts ?? []).map((s) => (
                  <SelectItem key={s.slug} value={s.slug}>
                    {s.name}{' '}
                    <span className="ml-1 font-mono text-xs text-muted-foreground">
                      ({s.slug})
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel
              onClick={() => {
                setCreateScriptSlug(null);
              }}
            >
              取消
            </AlertDialogCancel>
            <AlertDialogAction
              disabled={!createScriptSlug}
              onClick={(e) => {
                e.preventDefault();
                if (!createScriptSlug) return;
                setPickScriptOpen(false);
                setSheetOpen(true);
              }}
            >
              下一步
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* 创建实例 sheet — 仅在 createScript 加载完后挂载,避免 fields_schema 缺失 */}
      {sheetOpen && createScript ? (
        <InstanceFormSheet
          open={sheetOpen}
          onOpenChange={handleSheetChange}
          mode="create"
          script={createScript}
        />
      ) : null}

      {/* 删除二确 */}
      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={(o) => {
          if (!o) setDeleteTarget(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <TriangleAlert className="size-5 text-danger" strokeWidth={1.75} />
              确认删除实例「{deleteTarget?.name}」?
            </AlertDialogTitle>
            <AlertDialogDescription>
              <strong className="text-foreground">将级联删除该实例的所有执行记录(run)</strong>
              ;操作不可恢复。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={remove.isPending}>取消</AlertDialogCancel>
            <AlertDialogAction
              className="bg-danger text-danger-foreground hover:bg-danger/90"
              disabled={remove.isPending}
              onClick={(e) => {
                e.preventDefault();
                if (!deleteTarget) return;
                remove.mutate(
                  {
                    id: deleteTarget.id,
                    scriptSlug: getInstanceSlug(deleteTarget),
                  },
                  { onSuccess: () => setDeleteTarget(null) },
                );
              }}
            >
              {remove.isPending ? (
                <Loader2 className="mr-1.5 size-4 animate-spin" strokeWidth={1.75} />
              ) : (
                <Trash2 className="mr-1.5 size-4" strokeWidth={1.75} />
              )}
              确认删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* 暂停二确(默认 1 小时) */}
      <AlertDialog
        open={!!pauseTarget}
        onOpenChange={(o) => {
          if (!o) setPauseTarget(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <Clock className="size-5 text-warning" strokeWidth={1.75} />
              暂停实例「{pauseTarget?.name}」?
            </AlertDialogTitle>
            <AlertDialogDescription>
              将临时暂停调度,1 小时后自动恢复。期间不会触发任何 cron 计划。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault();
                void handlePauseConfirm();
              }}
            >
              <CalendarClock className="mr-1.5 size-4" strokeWidth={1.75} />
              确认暂停
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

export default InstanceList;
