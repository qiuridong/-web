/**
 * <RunDetailSheet> — 单次 run 详情右抽屉
 *
 * 设计契约:`进度/设计/前端UI设计.md` § 3.7。
 *
 * 内容:
 *   - run 元信息(状态 / 触发 / 开始 / 结束 / 时长 / exit_code / message)
 *   - stdout / stderr collapsible(默认展开第一段 200 行)
 *   - 复制按钮(分别复制 stdout / stderr)
 *   - 截断提示(stdout_truncated / stderr_truncated)
 */
import { useState, type ReactNode } from 'react';
import { ChevronDown, Copy, Loader2 } from 'lucide-react';
import { toast } from 'sonner';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';

import StatusBadge, { type Status } from '@/components/common/StatusBadge';
import { useRun, type RunStatus } from '@/api/hooks/runs';
import { formatDate, formatDuration, formatRelative } from '@/lib/format';
import { cn } from '@/lib/utils';

export interface RunDetailSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  runId: number | undefined;
}

function runStatusToBadgeStatus(status: RunStatus | string | null | undefined): Status {
  switch (status) {
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

export function RunDetailSheet({ open, onOpenChange, runId }: RunDetailSheetProps) {
  const { data: run, isLoading } = useRun(runId);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="flex w-full flex-col gap-0 overflow-hidden p-0 sm:max-w-2xl">
        <SheetHeader className="border-b border-border px-6 py-4">
          <SheetTitle>执行详情</SheetTitle>
          <SheetDescription>
            {run ? `Run #${run.id}` : runId ? `Run #${runId}` : '—'}
          </SheetDescription>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto px-6 py-5">
          {isLoading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" strokeWidth={1.75} />
              加载中…
            </div>
          ) : !run ? (
            <p className="text-sm text-muted-foreground">无数据</p>
          ) : (
            <div className="space-y-6">
              <div className="grid grid-cols-2 gap-x-6 gap-y-4 text-sm">
                <Field label="状态">
                  <StatusBadge status={runStatusToBadgeStatus(run.status)} label={run.status} />
                </Field>
                <Field label="触发">
                  <Badge variant="outline" className="font-mono">
                    {run.trigger_type}
                  </Badge>
                </Field>
                <Field label="开始">
                  <span className="tabular-nums" title={formatDate(run.started_at)}>
                    {formatRelative(run.started_at)}
                  </span>
                </Field>
                <Field label="结束">
                  <span className="tabular-nums" title={formatDate(run.finished_at)}>
                    {run.finished_at ? formatRelative(run.finished_at) : '—'}
                  </span>
                </Field>
                <Field label="时长">
                  <span className="tabular-nums">{formatDuration(run.duration_ms)}</span>
                </Field>
                <Field label="exit_code">
                  <code className="font-mono text-xs">
                    {run.exit_code !== null && run.exit_code !== undefined ? run.exit_code : '—'}
                  </code>
                </Field>
                <Field label="脚本">
                  <code className="font-mono text-xs">{run.script_slug ?? '—'}</code>
                </Field>
                <Field label="主机">
                  <code className="font-mono text-xs">{run.host ?? '—'}</code>
                </Field>
                {run.result_message ? (
                  <div className="col-span-2">
                    <div className="mb-1 text-[11px] uppercase tracking-wider text-muted-foreground/70">
                      result_message
                    </div>
                    <div className="rounded-md border border-border bg-muted/40 p-3 text-xs">
                      {run.result_message}
                    </div>
                  </div>
                ) : null}
              </div>

              <CollapsibleSection
                title="stdout"
                content={run.stdout ?? ''}
                truncated={!!run.stdout_truncated}
                emptyText="(无 stdout 输出)"
              />

              <CollapsibleSection
                title="stderr"
                content={run.stderr ?? ''}
                truncated={!!run.stderr_truncated}
                emptyText="(无 stderr 输出)"
                streamColor="text-danger"
              />

              {run.result_data_json ? (
                <CollapsibleSection
                  title="result_data"
                  content={run.result_data_json}
                  emptyText="(无)"
                />
              ) : null}
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <div className="mb-1 text-[11px] uppercase tracking-wider text-muted-foreground/70">
        {label}
      </div>
      <div className="text-sm">{children}</div>
    </div>
  );
}

function CollapsibleSection({
  title,
  content,
  truncated,
  emptyText,
  streamColor,
}: {
  title: string;
  content: string;
  truncated?: boolean;
  emptyText: string;
  streamColor?: string;
}) {
  const [open, setOpen] = useState(true);

  async function handleCopy() {
    if (!content) {
      toast.info(`${title} 为空`);
      return;
    }
    try {
      await navigator.clipboard.writeText(content);
      toast.success(`${title} 已复制`);
    } catch {
      toast.error('复制失败');
    }
  }

  return (
    <Collapsible open={open} onOpenChange={setOpen} className="space-y-2">
      <div className="flex items-center justify-between">
        <CollapsibleTrigger className="flex items-center gap-1 text-sm font-semibold">
          <ChevronDown
            className={cn(
              'size-4 text-muted-foreground transition-transform',
              !open && '-rotate-90',
            )}
            strokeWidth={1.75}
          />
          <span className={streamColor}>{title}</span>
          {truncated ? (
            <Badge variant="outline" className="ml-1.5 border-warning/30 bg-warning/10 text-warning">
              已截断
            </Badge>
          ) : null}
        </CollapsibleTrigger>
        <Button variant="ghost" size="sm" className="h-7 gap-1 px-2 text-xs" onClick={handleCopy}>
          <Copy className="size-3.5" strokeWidth={1.75} />
          复制
        </Button>
      </div>
      <CollapsibleContent>
        {content ? (
          <pre className="max-h-[40vh] overflow-auto rounded-md border border-border bg-muted/40 p-3 font-mono text-xs leading-relaxed">
            {content}
          </pre>
        ) : (
          <p className="rounded-md border border-dashed border-border bg-card/30 p-3 text-xs text-muted-foreground">
            {emptyText}
          </p>
        )}
      </CollapsibleContent>
    </Collapsible>
  );
}

export default RunDetailSheet;
