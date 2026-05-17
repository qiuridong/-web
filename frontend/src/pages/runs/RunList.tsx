/**
 * /runs — 全局执行历史
 *
 * 设计契约:`进度/设计/前端UI设计.md` § 3.7、§ 8。
 *
 * 工具栏:
 *   - script_slug Select(从 useScripts 拉)
 *   - status Select(单选;后端 RunsFilter 只支持单 status)
 *   - trigger_type Select
 *   - 日期范围(Popover + 2 个 date input + presets);未装 react-day-picker,用原生
 *   - "实时跟随" toggle(refetchInterval=3000)
 *   - "清理旧记录" 按钮(AlertDialog 选 keep_days 7/14/30)
 *
 * 主表:status / script_slug / 实例 / 触发 / started_at / duration / result_message / 操作
 * 点行 → 打开 RunDetailSheet
 * /runs/:id 路由直达 → 自动 setSelected
 */
import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { useNavigate, useParams } from 'react-router';
import {
  Activity,
  Ban,
  CalendarRange,
  Clock,
  Eraser,
  Eye,
  History,
  Loader2,
  MoreHorizontal,
  Play,
  RefreshCw,
  Repeat,
  Sparkles,
  Timer,
  Wifi,
  WifiOff,
  X,
} from 'lucide-react';
import type { ColumnDef } from '@tanstack/react-table';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
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
import { Switch } from '@/components/ui/switch';

import DataTable from '@/components/common/DataTable';
import EmptyState from '@/components/common/EmptyState';
import PageHeader from '@/components/common/PageHeader';
import RunDetailSheet from '@/components/common/RunDetailSheet';
import StatusBadge, { type Status } from '@/components/common/StatusBadge';

import {
  useCancelRun,
  useCleanupRuns,
  useRuns,
  type RunListItem,
  type RunStatus,
  type RunTriggerType,
  type RunsFilter,
} from '@/api/hooks/runs';
import { useScripts } from '@/api/hooks/scripts';
import { formatDate, formatDuration, formatRelative } from '@/lib/format';
import { cn } from '@/lib/utils';

type StatusFilter = 'all' | RunStatus;
type TriggerFilter = 'all' | RunTriggerType;

const STATUS_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: 'all', label: '全部状态' },
  { value: 'success', label: '成功' },
  { value: 'failure', label: '失败' },
  { value: 'error', label: '错误' },
  { value: 'timeout', label: '超时' },
  { value: 'cancelled', label: '已取消' },
  { value: 'running', label: '运行中' },
  { value: 'pending', label: '等待中' },
];

const TRIGGER_OPTIONS: { value: TriggerFilter; label: string }[] = [
  { value: 'all', label: '全部触发' },
  { value: 'manual', label: '手动' },
  { value: 'scheduled', label: '计划' },
  { value: 'retry', label: '重试' },
  { value: 'api', label: 'API' },
];

function runStatusToBadge(s?: string | null): Status {
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

function triggerIcon(t: RunTriggerType): ReactNode {
  switch (t) {
    case 'manual':
      return <Play className="size-3" strokeWidth={1.75} />;
    case 'scheduled':
      return <Clock className="size-3" strokeWidth={1.75} />;
    case 'retry':
      return <Repeat className="size-3" strokeWidth={1.75} />;
    case 'api':
      return <Sparkles className="size-3" strokeWidth={1.75} />;
    default:
      return null;
  }
}

function dateToInputValue(d: Date | null | undefined): string {
  if (!d) return '';
  // input[type=date] 要 yyyy-MM-dd
  const yr = d.getFullYear();
  const mo = String(d.getMonth() + 1).padStart(2, '0');
  const da = String(d.getDate()).padStart(2, '0');
  return `${yr}-${mo}-${da}`;
}

function inputValueToDate(v: string): Date | null {
  if (!v) return null;
  const d = new Date(v + 'T00:00:00');
  return Number.isNaN(d.getTime()) ? null : d;
}

interface DateRange {
  from: Date | null;
  to: Date | null;
}

export function RunList() {
  const navigate = useNavigate();
  const params = useParams<{ id?: string }>();

  // 路由参数 /runs/:id 时自动打开 detail sheet
  const [selected, setSelected] = useState<number | undefined>(undefined);
  useEffect(() => {
    if (params.id) {
      const idNum = Number(params.id);
      if (!Number.isNaN(idNum) && idNum > 0) {
        setSelected(idNum);
      }
    }
  }, [params.id]);

  // 关闭 sheet 时同步路由(回到 /runs)
  function handleDetailOpenChange(open: boolean) {
    if (!open) {
      setSelected(undefined);
      if (params.id) navigate('/runs', { replace: true });
    }
  }

  // 筛选 state
  const [scriptFilter, setScriptFilter] = useState<string>('__all__');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [triggerFilter, setTriggerFilter] = useState<TriggerFilter>('all');
  const [dateRange, setDateRange] = useState<DateRange>({ from: null, to: null });
  const [following, setFollowing] = useState(false);

  const filterArg = useMemo<RunsFilter>(() => {
    const out: RunsFilter = { page_size: 100 };
    if (scriptFilter !== '__all__') out.script_slug = scriptFilter;
    if (statusFilter !== 'all') out.status = statusFilter;
    if (triggerFilter !== 'all') out.trigger_type = triggerFilter;
    if (dateRange.from) {
      const from = new Date(dateRange.from);
      from.setHours(0, 0, 0, 0);
      out.started_after = from.toISOString();
    }
    if (dateRange.to) {
      const to = new Date(dateRange.to);
      to.setHours(23, 59, 59, 999);
      out.started_before = to.toISOString();
    }
    return out;
  }, [scriptFilter, statusFilter, triggerFilter, dateRange]);

  const {
    data: runs,
    isLoading,
    isFetching,
    refetch,
    dataUpdatedAt,
  } = useRuns(filterArg);

  // 实时跟随:开启时强制 3s 一次刷新
  useEffect(() => {
    if (!following) return;
    const id = setInterval(() => {
      void refetch();
    }, 3000);
    return () => clearInterval(id);
  }, [following, refetch]);

  const { data: scripts } = useScripts();

  // 操作 mutations
  const cancel = useCancelRun();
  const cleanup = useCleanupRuns();

  // 清理对话框
  const [cleanupOpen, setCleanupOpen] = useState(false);
  const [keepDays, setKeepDays] = useState<string>('14');

  // 派生
  const total = runs?.length ?? 0;
  const hasFilter =
    scriptFilter !== '__all__' ||
    statusFilter !== 'all' ||
    triggerFilter !== 'all' ||
    !!dateRange.from ||
    !!dateRange.to;

  // columns
  const columns = useMemo<ColumnDef<RunListItem>[]>(
    () => [
      {
        id: 'status',
        accessorKey: 'status',
        header: '状态',
        enableSorting: false,
        cell: ({ row }) => (
          <StatusBadge
            status={runStatusToBadge(row.original.status)}
            label={row.original.status}
          />
        ),
      },
      {
        id: 'script_slug',
        header: '脚本',
        enableSorting: false,
        cell: ({ row }) => {
          const r = row.original;
          const slug = r.script_slug ?? r.script?.slug ?? '—';
          return (
            <code className="truncate font-mono text-xs text-foreground">{slug}</code>
          );
        },
      },
      {
        id: 'instance',
        header: '实例',
        enableSorting: false,
        cell: ({ row }) => {
          const r = row.original;
          const name = r.instance?.name ?? `#${r.instance_id}`;
          return <span className="truncate text-sm text-foreground">{name}</span>;
        },
      },
      {
        accessorKey: 'trigger_type',
        header: '触发',
        enableSorting: false,
        cell: ({ getValue }) => {
          const v = (getValue() as RunTriggerType) ?? 'manual';
          return (
            <Badge variant="outline" className="gap-1 font-mono text-[11px]">
              {triggerIcon(v)}
              {v}
            </Badge>
          );
        },
      },
      {
        accessorKey: 'started_at',
        header: '开始时间',
        enableSorting: false,
        cell: ({ getValue }) => {
          const v = getValue() as string | undefined;
          return (
            <span className="text-xs text-muted-foreground tabular-nums" title={formatDate(v)}>
              {v ? formatRelative(v) : '—'}
            </span>
          );
        },
      },
      {
        accessorKey: 'duration_ms',
        header: '时长',
        enableSorting: false,
        cell: ({ getValue }) => (
          <span className="text-xs tabular-nums">
            {formatDuration((getValue() as number) ?? null)}
          </span>
        ),
      },
      {
        accessorKey: 'result_message',
        header: '消息',
        enableSorting: false,
        cell: ({ getValue }) => {
          const v = getValue() as string | null | undefined;
          if (!v) return <span className="text-muted-foreground/60">—</span>;
          const short = v.length > 60 ? v.slice(0, 60) + '…' : v;
          return (
            <span className="truncate text-xs text-muted-foreground" title={v}>
              {short}
            </span>
          );
        },
      },
      {
        id: 'actions',
        header: '',
        enableHiding: false,
        cell: ({ row }) => {
          const r = row.original;
          const canCancel = r.status === 'pending' || r.status === 'running';
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
                  className="w-40"
                  onClick={(e) => e.stopPropagation()}
                >
                  <DropdownMenuLabel className="text-xs">执行操作</DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    onClick={(e) => {
                      e.stopPropagation();
                      setSelected(r.id);
                    }}
                  >
                    <Eye className="mr-2 size-3.5" strokeWidth={1.75} />
                    详情
                  </DropdownMenuItem>
                  {canCancel ? (
                    <DropdownMenuItem
                      className="text-danger focus:text-danger"
                      onClick={(e) => {
                        e.stopPropagation();
                        cancel.mutate(r.id);
                      }}
                    >
                      <Ban className="mr-2 size-3.5" strokeWidth={1.75} />
                      取消
                    </DropdownMenuItem>
                  ) : null}
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          );
        },
      },
    ],
    [cancel],
  );

  const lastFetched = dataUpdatedAt ? formatRelative(new Date(dataUpdatedAt)) : '—';

  return (
    <div className="mx-auto w-full max-w-[1440px] px-6 py-8">
      <PageHeader
        title="执行历史"
        description={
          total > 0
            ? `共 ${total} 条记录 · 上次刷新 ${lastFetched}`
            : '尚无执行记录;触发一次实例即可看到结果'
        }
        actions={
          <>
            <div className="flex items-center gap-2 rounded-md border border-border bg-card px-2.5 py-1 text-xs">
              {following ? (
                <Wifi className="size-3.5 text-success" strokeWidth={1.75} />
              ) : (
                <WifiOff className="size-3.5 text-muted-foreground" strokeWidth={1.75} />
              )}
              <Label htmlFor="follow-toggle" className="cursor-pointer text-xs font-normal">
                实时跟随
              </Label>
              <Switch
                id="follow-toggle"
                checked={following}
                onCheckedChange={setFollowing}
                aria-label="实时跟随"
              />
            </div>
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
            <Button
              variant="outline"
              size="sm"
              onClick={() => setCleanupOpen(true)}
            >
              <Eraser className="size-4" strokeWidth={1.75} />
              <span className="ml-1.5">清理旧记录</span>
            </Button>
          </>
        }
      />

      {/* 工具栏 */}
      <div className="mb-5 flex flex-wrap items-center gap-2">
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
          value={statusFilter}
          onValueChange={(v) => setStatusFilter(v as StatusFilter)}
        >
          <SelectTrigger className="h-9 w-[130px] text-sm">
            <SelectValue placeholder="状态" />
          </SelectTrigger>
          <SelectContent>
            {STATUS_OPTIONS.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          value={triggerFilter}
          onValueChange={(v) => setTriggerFilter(v as TriggerFilter)}
        >
          <SelectTrigger className="h-9 w-[130px] text-sm">
            <SelectValue placeholder="触发" />
          </SelectTrigger>
          <SelectContent>
            {TRIGGER_OPTIONS.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <DateRangeButton value={dateRange} onChange={setDateRange} />
        {hasFilter ? (
          <Button
            variant="ghost"
            size="sm"
            className="h-9 text-xs"
            onClick={() => {
              setScriptFilter('__all__');
              setStatusFilter('all');
              setTriggerFilter('all');
              setDateRange({ from: null, to: null });
            }}
          >
            <X className="size-3.5" strokeWidth={1.75} />
            <span className="ml-1">清空筛选</span>
          </Button>
        ) : null}
      </div>

      {/* 表格 / 空态 */}
      {!isLoading && (runs?.length ?? 0) === 0 && !hasFilter ? (
        <div className="rounded-xl border-2 border-dashed border-border bg-card/30">
          <EmptyState
            icon={History}
            title="尚无执行历史"
            description="实例触发后,记录会出现在这里"
            action={
              <Button onClick={() => navigate('/scripts')}>
                <Activity className="size-4" strokeWidth={1.75} />
                <span className="ml-1.5">去触发一次</span>
              </Button>
            }
          />
        </div>
      ) : !isLoading && (runs?.length ?? 0) === 0 && hasFilter ? (
        <div className="rounded-xl border-2 border-dashed border-border bg-card/30">
          <EmptyState
            icon={History}
            title="没有匹配的记录"
            description="尝试清空筛选或扩大日期范围"
            action={
              <Button
                variant="outline"
                onClick={() => {
                  setScriptFilter('__all__');
                  setStatusFilter('all');
                  setTriggerFilter('all');
                  setDateRange({ from: null, to: null });
                }}
              >
                清空筛选
              </Button>
            }
          />
        </div>
      ) : (
        <DataTable<RunListItem, unknown>
          columns={columns}
          data={runs ?? []}
          loading={isLoading}
          onRowClick={(row) => setSelected(row.id)}
          getRowId={(row) => String((row as RunListItem).id)}
          empty={
            <EmptyState
              icon={History}
              title="尚无执行历史"
              description="实例触发后,记录会出现在这里"
            />
          }
        />
      )}

      <RunDetailSheet
        runId={selected}
        open={selected !== undefined}
        onOpenChange={handleDetailOpenChange}
      />

      {/* 清理对话框 */}
      <AlertDialog open={cleanupOpen} onOpenChange={setCleanupOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <Eraser className="size-5 text-warning" strokeWidth={1.75} />
              清理旧的执行记录
            </AlertDialogTitle>
            <AlertDialogDescription>
              将删除指定天数之前的所有记录(含 stdout / stderr)。该操作不可恢复。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="py-2">
            <Label className="mb-2 block text-sm">保留最近</Label>
            <Select value={keepDays} onValueChange={setKeepDays}>
              <SelectTrigger className="h-10 w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="7">7 天</SelectItem>
                <SelectItem value="14">14 天</SelectItem>
                <SelectItem value="30">30 天</SelectItem>
              </SelectContent>
            </Select>
            <p className="mt-2 text-xs text-muted-foreground">
              即清除 {keepDays} 天前的所有记录。
            </p>
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={cleanup.isPending}>取消</AlertDialogCancel>
            <AlertDialogAction
              className="bg-danger text-danger-foreground hover:bg-danger/90"
              disabled={cleanup.isPending}
              onClick={(e) => {
                e.preventDefault();
                cleanup.mutate(
                  { keep_days: Number(keepDays) },
                  {
                    onSuccess: () => setCleanupOpen(false),
                  },
                );
              }}
            >
              {cleanup.isPending ? (
                <Loader2 className="mr-1.5 size-4 animate-spin" strokeWidth={1.75} />
              ) : (
                <Timer className="mr-1.5 size-4" strokeWidth={1.75} />
              )}
              确认清理
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

// ============ DateRangeButton(popover + 2 个 date input + presets) ============

interface DateRangeButtonProps {
  value: DateRange;
  onChange: (next: DateRange) => void;
}

function DateRangeButton({ value, onChange }: DateRangeButtonProps) {
  const label = useMemo(() => {
    if (value.from && value.to) {
      return `${formatDate(value.from, 'MM-dd')} ~ ${formatDate(value.to, 'MM-dd')}`;
    }
    if (value.from) return `自 ${formatDate(value.from, 'MM-dd')}`;
    if (value.to) return `至 ${formatDate(value.to, 'MM-dd')}`;
    return '日期范围';
  }, [value]);

  function applyPreset(days: number) {
    const to = new Date();
    const from = new Date();
    from.setDate(from.getDate() - days + 1);
    onChange({ from, to });
  }

  function clear() {
    onChange({ from: null, to: null });
  }

  const active = !!(value.from || value.to);

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          className={cn(
            'h-9 gap-1.5 text-sm',
            active && 'border-primary/40 bg-primary/5 text-foreground',
          )}
        >
          <CalendarRange className="size-3.5" strokeWidth={1.75} />
          <span>{label}</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-72 p-3">
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="dr-from" className="text-xs">
              开始
            </Label>
            <Input
              id="dr-from"
              type="date"
              value={dateToInputValue(value.from)}
              onChange={(e) =>
                onChange({ ...value, from: inputValueToDate(e.target.value) })
              }
              className="h-9 text-sm tabular-nums"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="dr-to" className="text-xs">
              结束
            </Label>
            <Input
              id="dr-to"
              type="date"
              value={dateToInputValue(value.to)}
              onChange={(e) =>
                onChange({ ...value, to: inputValueToDate(e.target.value) })
              }
              className="h-9 text-sm tabular-nums"
            />
          </div>
          <div className="flex flex-wrap gap-1.5 border-t border-border pt-2">
            <PresetButton onClick={() => applyPreset(1)}>今天</PresetButton>
            <PresetButton onClick={() => applyPreset(7)}>近 7 天</PresetButton>
            <PresetButton onClick={() => applyPreset(14)}>近 14 天</PresetButton>
            <PresetButton onClick={() => applyPreset(30)}>近 30 天</PresetButton>
          </div>
          {active ? (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 w-full text-xs"
              onClick={clear}
            >
              <X className="mr-1 size-3" strokeWidth={1.75} />
              清空
            </Button>
          ) : null}
        </div>
      </PopoverContent>
    </Popover>
  );
}

function PresetButton({ children, onClick }: { children: ReactNode; onClick: () => void }) {
  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      className="h-7 px-2 text-xs"
      onClick={onClick}
    >
      {children}
    </Button>
  );
}

export default RunList;
