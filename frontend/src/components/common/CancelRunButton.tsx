/**
 * CancelRunButton — 取消一个 pending / running 的 run
 *
 * 复用于:实时日志 tab(ScriptLogConsole)、运行详情抽屉(RunDetailSheet)。
 * 仅当 run 状态是 pending / running 时渲染;其它状态返回 null。
 *
 * 取消语义(后端 `POST /runs/{id}/cancel` + `run_service.cancel_run` 已有):
 *   - pending            → 任务还没派给节点,取消后永不执行(干净取消)
 *   - running · 本地节点  → executor 直接 SIGTERM → SIGKILL 子进程(真终止)
 *   - running · 远程节点  → 仅翻 DB 状态为 cancelled;agent 单线程串行,当前 run
 *     的子进程会跑完(结果上报时被识别为 already_cancelled 而丢弃)。所以远程
 *     "运行中"是软取消 —— 弹窗里向用户说清楚,避免误以为脚本立刻停了。
 */
import { useState } from 'react';
import { Ban, Loader2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
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
import { useCancelRun, type RunStatus } from '@/api/hooks/runs';
import { cn } from '@/lib/utils';

interface CancelRunButtonProps {
  runId: number;
  status: RunStatus | undefined;
  /** 按钮尺寸(默认 sm) */
  size?: 'sm' | 'default' | 'icon';
  /** 额外 class */
  className?: string;
  /** 紧凑模式:只显示图标(列表行内用) */
  iconOnly?: boolean;
  /** 取消成功回调(如关闭抽屉 / 刷新) */
  onCancelled?: () => void;
}

const CANCELLABLE: RunStatus[] = ['pending', 'running'];

export function CancelRunButton({
  runId,
  status,
  size = 'sm',
  className,
  iconOnly = false,
  onCancelled,
}: CancelRunButtonProps) {
  const [open, setOpen] = useState(false);
  const cancel = useCancelRun();

  // 只有 pending / running 才能取消
  if (!status || !CANCELLABLE.includes(status)) return null;

  return (
    <>
      <Button
        variant="outline"
        size={size}
        className={cn(
          'border-danger/30 text-danger hover:bg-danger/10 hover:text-danger',
          className,
        )}
        onClick={(e) => {
          e.stopPropagation();
          setOpen(true);
        }}
        aria-label={`取消运行 #${runId}`}
      >
        <Ban className="size-4" strokeWidth={1.75} />
        {!iconOnly && <span className="ml-1.5">取消运行</span>}
      </Button>

      <AlertDialog open={open} onOpenChange={setOpen}>
        <AlertDialogContent onClick={(e) => e.stopPropagation()}>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <Ban className="size-5 text-danger" strokeWidth={1.75} />
              取消运行 #{runId}?
            </AlertDialogTitle>
            <AlertDialogDescription>
              {status === 'pending'
                ? '该任务还在排队、尚未派发到节点,取消后将不会执行。'
                : '将向执行该任务的节点发送取消信号,并把这次运行标记为「已取消」。'}
            </AlertDialogDescription>
          </AlertDialogHeader>

          {status === 'running' ? (
            <div className="rounded-md border border-warning/30 bg-warning/10 px-3 py-2 text-xs leading-relaxed text-foreground">
              注:远程节点为单线程串行执行 —— 若脚本已在运行(如随机延迟中),
              当前这一次会跑完后才停,运行结果会被丢弃。本地节点则会立即终止子进程。
            </div>
          ) : null}

          <AlertDialogFooter>
            <AlertDialogCancel disabled={cancel.isPending}>返回</AlertDialogCancel>
            <AlertDialogAction
              className="bg-danger text-danger-foreground hover:bg-danger/90"
              disabled={cancel.isPending}
              onClick={(e) => {
                e.preventDefault();
                cancel.mutate(runId, {
                  onSuccess: () => {
                    setOpen(false);
                    onCancelled?.();
                  },
                });
              }}
            >
              {cancel.isPending ? (
                <Loader2 className="mr-1.5 size-4 animate-spin" strokeWidth={1.75} />
              ) : (
                <Ban className="mr-1.5 size-4" strokeWidth={1.75} />
              )}
              确认取消
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

export default CancelRunButton;
