/**
 * <InstancesPanel> — 脚本详情页"实例"Tab 主体
 *
 * 设计契约:`进度/设计/前端UI设计.md` § 3.5。
 *
 * 渲染:
 *   - 顶部:总数 + 启用数 + "新建实例" 按钮
 *   - 卡片网格(每张:name / cron / 上次/下次 / 状态 / 操作菜单)
 *   - 操作:立即运行(跳转到日志 tab + 设置 runId)/ 编辑(打开 Sheet)/ 启用-禁用 / 暂停 / 恢复 / 删除
 *
 * 数据:useInstances({script_slug}) / useInstance(id)
 */
import { useState } from 'react';
import {
  Loader2,
  MoreHorizontal,
  Pause,
  PlayCircle,
  Play,
  RotateCcw,
  Settings2,
  Sparkles,
  Trash2,
  Clock,
  CalendarClock,
  TriangleAlert,
  RefreshCw,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
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
import { Skeleton } from '@/components/ui/skeleton';

import EmptyState from '@/components/common/EmptyState';
import InstanceFormSheet from '@/components/common/InstanceFormSheet';
import StatusBadge, { type Status } from '@/components/common/StatusBadge';

import {
  useDeleteInstance,
  useDisableInstance,
  useEnableInstance,
  useInstance,
  useInstances,
  usePauseInstance,
  useResumeInstance,
  useTriggerInstance,
  type InstanceListItem,
} from '@/api/hooks/instances';
import type { ScriptDetail } from '@/api/hooks/scripts';
import { formatDate, formatRelative } from '@/lib/format';
import { cn } from '@/lib/utils';

export interface InstancesPanelProps {
  script: ScriptDetail;
  /** 点击"立即运行"成功后回调,父组件可切到"实时日志"Tab 并 setRunId */
  onTriggered?: (instanceId: number, runId: number) => void;
}

function instanceStatusToBadge(s?: string | null): Status {
  // 区分:实例从未运行(null/undefined)→ 'never_run' "待运行"
  //       后端返了未识别字符串 → 'unknown' "未知"
  if (s === null || s === undefined || s === '') {
    return 'never_run';
  }
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

export function InstancesPanel({ script, onTriggered }: InstancesPanelProps) {
  const { data: instances, isLoading, isFetching, refetch } = useInstances({
    script_slug: script.slug,
  });

  const [sheetOpen, setSheetOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | undefined>(undefined);
  const [deleteTarget, setDeleteTarget] = useState<InstanceListItem | null>(null);
  const [pauseTarget, setPauseTarget] = useState<InstanceListItem | null>(null);

  // 加载 detail(供编辑模式用)
  const { data: editingInstance } = useInstance(editingId);

  const enable = useEnableInstance();
  const disable = useDisableInstance();
  const pause = usePauseInstance();
  const resume = useResumeInstance();
  const trigger = useTriggerInstance();
  const remove = useDeleteInstance();

  const total = instances?.length ?? 0;
  const enabledCount = (instances ?? []).filter((i) => i.enabled).length;

  function openCreate() {
    setEditingId(undefined);
    setSheetOpen(true);
  }

  function openEdit(id: number) {
    setEditingId(id);
    setSheetOpen(true);
  }

  function handleSheetChange(open: boolean) {
    setSheetOpen(open);
    if (!open) setEditingId(undefined);
  }

  async function handleTrigger(instanceId: number) {
    const res = await trigger.mutateAsync({ id: instanceId, scriptSlug: script.slug });
    onTriggered?.(instanceId, res.run_id);
  }

  async function handlePauseConfirm() {
    if (!pauseTarget) return;
    // 默认暂停 1 小时
    const until = new Date(Date.now() + 60 * 60 * 1000).toISOString();
    await pause.mutateAsync({
      id: pauseTarget.id,
      payload: { until },
      scriptSlug: script.slug,
    });
    setPauseTarget(null);
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-sm text-muted-foreground">
          {total > 0 ? (
            <>
              共 <span className="font-medium text-foreground tabular-nums">{total}</span> 个实例
              {' · '}
              已启用 <span className="font-medium text-foreground tabular-nums">{enabledCount}</span>
            </>
          ) : (
            <>暂未创建任何实例</>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => refetch()}
            disabled={isFetching}
            aria-label="刷新"
            title="刷新"
          >
            <RefreshCw
              className={cn('size-4', isFetching && 'animate-spin')}
              strokeWidth={1.75}
            />
            <span className="ml-1.5 hidden sm:inline">刷新</span>
          </Button>
          <Button size="sm" onClick={openCreate}>
            <Sparkles className="size-4" strokeWidth={1.75} />
            <span className="ml-1.5">新建实例</span>
          </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-[160px] rounded-xl" />
          ))}
        </div>
      ) : !instances || instances.length === 0 ? (
        <Card className="border-2 border-dashed border-border bg-card/30">
          <EmptyState
            icon={Settings2}
            title="尚未创建实例"
            description="实例是脚本的具体配置(账号/cookie/cron/超时),用于真正执行签到任务"
            action={
              <Button onClick={openCreate}>
                <Sparkles className="size-4" strokeWidth={1.75} />
                <span className="ml-1.5">新建实例</span>
              </Button>
            }
          />
        </Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {instances.map((inst) => (
            <InstanceCard
              key={inst.id}
              instance={inst}
              onEdit={() => openEdit(inst.id)}
              onTrigger={() => handleTrigger(inst.id)}
              onToggle={() => {
                if (inst.enabled) {
                  disable.mutate({ id: inst.id, scriptSlug: script.slug });
                } else {
                  enable.mutate({ id: inst.id, scriptSlug: script.slug });
                }
              }}
              onPause={() => setPauseTarget(inst)}
              onResume={() => resume.mutate({ id: inst.id, scriptSlug: script.slug })}
              onDelete={() => setDeleteTarget(inst)}
              triggerPending={trigger.isPending}
            />
          ))}
        </div>
      )}

      {/* 创建/编辑 Sheet */}
      <InstanceFormSheet
        open={sheetOpen}
        onOpenChange={handleSheetChange}
        mode={editingId ? 'edit' : 'create'}
        script={script}
        instance={editingId ? editingInstance : undefined}
      />

      {/* 删除确认 */}
      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
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
              ;该操作不可恢复。
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
                  { id: deleteTarget.id, scriptSlug: script.slug },
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

      {/* 暂停确认(默认 1 小时) */}
      <AlertDialog open={!!pauseTarget} onOpenChange={(open) => !open && setPauseTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>暂停实例「{pauseTarget?.name}」?</AlertDialogTitle>
            <AlertDialogDescription>
              将临时暂停调度,1 小时后自动恢复。
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
              确认暂停
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

interface InstanceCardProps {
  instance: InstanceListItem;
  onEdit: () => void;
  onTrigger: () => void;
  onToggle: () => void;
  onPause: () => void;
  onResume: () => void;
  onDelete: () => void;
  triggerPending: boolean;
}

function InstanceCard({
  instance,
  onEdit,
  onTrigger,
  onToggle,
  onPause,
  onResume,
  onDelete,
  triggerPending,
}: InstanceCardProps) {
  const pausedActive =
    instance.paused_until && new Date(instance.paused_until).getTime() > Date.now();

  return (
    <Card className="group flex flex-col gap-3 p-4 transition-shadow hover:shadow-md">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <h4 className="truncate text-sm font-semibold text-foreground" title={instance.name}>
            {instance.name}
          </h4>
          {instance.description ? (
            <p className="truncate text-xs text-muted-foreground" title={instance.description}>
              {instance.description}
            </p>
          ) : null}
        </div>
        <div className="flex items-center gap-1">
          {instance.enabled ? (
            <Badge variant="outline" className="border-success/30 bg-success/10 text-success">
              启用
            </Badge>
          ) : (
            <Badge variant="outline" className="text-muted-foreground">
              禁用
            </Badge>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs">
        <StatusBadge status={instanceStatusToBadge(instance.last_run_status)} />
        <span className="flex items-center gap-1 text-muted-foreground">
          <Clock className="size-3" strokeWidth={1.75} />
          上次 {formatRelative(instance.last_run_at)}
        </span>
        <span className="flex items-center gap-1 text-muted-foreground">
          <CalendarClock className="size-3" strokeWidth={1.75} />
          下次 {formatRelative(instance.next_run_at)}
        </span>
      </div>

      <div className="flex items-center gap-1.5">
        {instance.cron_expr ? (
          <code className="truncate rounded bg-muted px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground">
            {instance.cron_expr}
          </code>
        ) : (
          <span className="text-[11px] text-muted-foreground/60">无 cron</span>
        )}
        {pausedActive ? (
          <Badge variant="outline" className="ml-auto border-warning/30 bg-warning/10 text-warning">
            暂停至 {formatDate(instance.paused_until, 'MM-dd HH:mm')}
          </Badge>
        ) : null}
      </div>

      <div className="mt-1 flex items-center gap-1.5 border-t border-border/60 pt-3">
        <Button
          variant="default"
          size="sm"
          className="h-8 gap-1.5"
          onClick={onTrigger}
          disabled={triggerPending}
        >
          {triggerPending ? (
            <Loader2 className="size-3.5 animate-spin" strokeWidth={1.75} />
          ) : (
            <Play className="size-3.5" strokeWidth={1.75} />
          )}
          立即运行
        </Button>
        <Button variant="outline" size="sm" className="h-8 gap-1.5" onClick={onEdit}>
          <Settings2 className="size-3.5" strokeWidth={1.75} />
          编辑
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm" className="ml-auto size-8 p-0">
              <MoreHorizontal className="size-4" strokeWidth={1.75} />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-44">
            <DropdownMenuLabel className="text-xs">实例操作</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={onToggle}>
              {instance.enabled ? (
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
            {pausedActive ? (
              <DropdownMenuItem onClick={onResume}>
                <RotateCcw className="mr-2 size-3.5" strokeWidth={1.75} />
                立即恢复
              </DropdownMenuItem>
            ) : (
              <DropdownMenuItem onClick={onPause}>
                <Pause className="mr-2 size-3.5" strokeWidth={1.75} />
                暂停 1 小时
              </DropdownMenuItem>
            )}
            <DropdownMenuSeparator />
            <DropdownMenuItem
              className="text-danger focus:text-danger"
              onClick={onDelete}
            >
              <Trash2 className="mr-2 size-3.5" strokeWidth={1.75} />
              删除实例
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </Card>
  );
}

export default InstancesPanel;
