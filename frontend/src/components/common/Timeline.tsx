/**
 * <Timeline> — 实时活动时间线(虚拟滚动)
 *
 * 设计契约:`进度/设计/前端UI设计.md` § 3.3(仪表盘 Timeline section)、§ 4。
 *
 * 用 `@tanstack/react-virtual` 虚拟化每行,容器固定高(默认 480),滚动 only 渲染可见行。
 * 单行点击 → 展开下方一段 stdout 摘要(Collapsible);hover 显示完整 result_message。
 *
 * 设计要点:
 *   - 行高估算 56(收起)/ 当展开时 react-virtual 自动 measure 重排
 *   - 列布局:[time | dot | script · instance | duration | trigger]
 *   - 状态点用 dot-pulse 配合 pending/running
 */
import { useCallback, useRef, useState } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { ChevronDown, Terminal } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from '@/components/ui/hover-card';
import { formatDate, formatDuration, formatRelative } from '@/lib/format';
import { cn } from '@/lib/utils';

export interface TimelineRowData {
  run_id: number;
  timestamp: string;
  script_slug: string;
  script_name: string;
  instance_id: number;
  instance_name: string;
  status: 'pending' | 'running' | 'success' | 'failure' | 'error' | 'timeout' | 'cancelled';
  duration_ms: number | null;
  trigger_type: 'manual' | 'scheduled' | 'retry' | 'api';
  stdout_preview?: string;
  result_message?: string | null;
}

export interface TimelineProps {
  rows: TimelineRowData[];
  /** 容器高(px) */
  height?: number;
  className?: string;
}

function statusDotColor(status: TimelineRowData['status']): string {
  switch (status) {
    case 'success':
      return 'text-success';
    case 'running':
    case 'pending':
      return 'text-info';
    case 'failure':
    case 'error':
      return 'text-danger';
    case 'timeout':
      return 'text-warning';
    case 'cancelled':
      return 'text-muted-foreground';
    default:
      return 'text-muted-foreground';
  }
}

function statusLabel(status: TimelineRowData['status']): string {
  const map: Record<TimelineRowData['status'], string> = {
    success: '成功',
    failure: '失败',
    error: '错误',
    timeout: '超时',
    pending: '等待',
    running: '运行',
    cancelled: '取消',
  };
  return map[status];
}

function triggerLabel(t: TimelineRowData['trigger_type']): string {
  const map: Record<TimelineRowData['trigger_type'], string> = {
    manual: '手动',
    scheduled: '定时',
    retry: '重试',
    api: 'API',
  };
  return map[t];
}

const ROW_COLLAPSED_HEIGHT = 56;
const ROW_EXPANDED_EXTRA = 132; // 展开 stdout 时增加的高度估算

export function Timeline({ rows, height = 480, className }: TimelineProps) {
  const parentRef = useRef<HTMLDivElement>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const estimateSize = useCallback(
    (index: number) => {
      const row = rows[index];
      if (!row) return ROW_COLLAPSED_HEIGHT;
      const isOpen = row.run_id === expandedId;
      return isOpen ? ROW_COLLAPSED_HEIGHT + ROW_EXPANDED_EXTRA : ROW_COLLAPSED_HEIGHT;
    },
    [rows, expandedId],
  );

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize,
    overscan: 6,
    getItemKey: (index) => rows[index]?.run_id ?? index,
  });

  const items = virtualizer.getVirtualItems();
  const totalSize = virtualizer.getTotalSize();

  // 当 expanded 变化时,重排(react-virtual 自动响应 estimateSize 变化,但稳妥 measure 一次)
  // 注意:点击行调用 setExpandedId 后下一帧 estimateSize 会用新值,这里不需要手动 measure。

  if (rows.length === 0) {
    return (
      <div
        className={cn(
          'flex w-full items-center justify-center rounded-xl border border-dashed border-border/70 py-10 text-sm text-muted-foreground/60',
          className,
        )}
        style={{ height }}
      >
        <Terminal className="mr-2 size-4 opacity-50" strokeWidth={1.5} />
        暂无活动记录
      </div>
    );
  }

  return (
    <div
      ref={parentRef}
      className={cn(
        'w-full overflow-auto rounded-xl border border-border bg-card',
        className,
      )}
      style={{ height }}
    >
      <div style={{ height: totalSize, width: '100%', position: 'relative' }}>
        {items.map((vi) => {
          const row = rows[vi.index];
          if (!row) return null;
          const isOpen = row.run_id === expandedId;
          const dotCls = statusDotColor(row.status);
          const isPulse = row.status === 'pending' || row.status === 'running';

          return (
            <div
              key={vi.key}
              ref={virtualizer.measureElement}
              data-index={vi.index}
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                transform: `translateY(${vi.start}px)`,
              }}
            >
              <TimelineItem
                row={row}
                isOpen={isOpen}
                onToggle={() => setExpandedId(isOpen ? null : row.run_id)}
                dotCls={dotCls}
                isPulse={isPulse}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}

interface TimelineItemProps {
  row: TimelineRowData;
  isOpen: boolean;
  onToggle: () => void;
  dotCls: string;
  isPulse: boolean;
}

function TimelineItem({ row, isOpen, onToggle, dotCls, isPulse }: TimelineItemProps) {
  const canExpand = Boolean(row.stdout_preview || row.result_message);
  return (
    <div
      className={cn(
        'group flex flex-col border-b border-border/60 last:border-b-0',
        'transition-colors hover:bg-accent/30',
        canExpand && 'cursor-pointer',
      )}
      onClick={canExpand ? onToggle : undefined}
    >
      {/* 单行 56px */}
      <div className="flex h-14 items-center gap-4 px-4">
        {/* 时间(相对 + hover 看绝对) */}
        <HoverCard openDelay={300} closeDelay={50}>
          <HoverCardTrigger asChild>
            <span className="w-24 shrink-0 tabular-nums text-xs text-muted-foreground/80">
              {formatRelative(row.timestamp)}
            </span>
          </HoverCardTrigger>
          <HoverCardContent side="top" align="start" className="w-auto px-3 py-2 text-xs">
            {formatDate(row.timestamp, 'yyyy-MM-dd HH:mm:ss')}
          </HoverCardContent>
        </HoverCard>

        {/* 状态点 */}
        <span className={cn('relative inline-flex size-2 shrink-0 isolate', dotCls)}>
          <span className={cn('block size-2 rounded-full bg-current', isPulse && 'dot-pulse')} />
        </span>

        {/* 脚本 · 实例 */}
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2 truncate text-sm">
            <span className="truncate font-medium text-foreground">{row.script_name}</span>
            <span className="text-muted-foreground/50">·</span>
            <span className="truncate text-muted-foreground">{row.instance_name}</span>
          </div>
          {row.result_message ? (
            <p className="truncate text-xs text-muted-foreground/70">{row.result_message}</p>
          ) : null}
        </div>

        {/* status badge + trigger + duration */}
        <Badge
          variant="outline"
          className={cn('shrink-0 text-[10px] uppercase tracking-wider', dotCls, 'border-current/30')}
        >
          {statusLabel(row.status)}
        </Badge>
        <span className="hidden shrink-0 text-xs text-muted-foreground/60 sm:inline">
          {triggerLabel(row.trigger_type)}
        </span>
        <span className="w-16 shrink-0 text-right tabular-nums text-xs text-muted-foreground/70">
          {formatDuration(row.duration_ms ?? 0)}
        </span>

        {canExpand ? (
          <ChevronDown
            className={cn(
              'size-4 shrink-0 text-muted-foreground/50 transition-transform',
              isOpen && 'rotate-180',
            )}
            strokeWidth={1.75}
            aria-hidden
          />
        ) : (
          <span className="size-4 shrink-0" aria-hidden />
        )}
      </div>

      {/* 展开区 */}
      {isOpen ? (
        <div className="border-t border-border/40 bg-muted/30 px-4 py-3">
          {row.result_message ? (
            <p className="mb-2 text-xs text-foreground/80">{row.result_message}</p>
          ) : null}
          {row.stdout_preview ? (
            <pre className="max-h-24 overflow-auto whitespace-pre-wrap rounded-md border border-border/50 bg-background/70 p-2 font-mono text-[11px] leading-relaxed text-foreground/90">
              {row.stdout_preview}
            </pre>
          ) : (
            <p className="text-xs italic text-muted-foreground/60">(无 stdout 输出)</p>
          )}
        </div>
      ) : null}
    </div>
  );
}

export default Timeline;
