/**
 * <ScriptCard> — 脚本健康度卡片(仪表盘 + 脚本列表共用)
 *
 * 设计契约:
 *   - `进度/设计/前端UI设计.md` § 3.3(仪表盘卡片)、§ 3.4(脚本列表卡片)、§ 4
 *   - StatusBadge 在 components/common/StatusBadge.tsx(由 5A agent 维护)
 *
 * 视觉:
 *   - rounded-xl border bg-card,min-h 220 / p-5
 *   - 顶部:左 icon 48x48(lucide 占位)+ 中间名/描述/版本 + 右上 status dot
 *   - 元信息行:实例数 / 下次执行 / 上次执行
 *   - 底部 actions:[运行 / 配置](按需 by props)
 *
 * 不直接依赖 StatusBadge.tsx 的状态映射(它只支持 6 种,缺 error/timeout/cancelled)
 *   → 内部用 dotColorByStatus 自己映射
 */
import { memo, type ComponentType } from 'react';
import { Calendar, Clock, Layers, Play, Settings2, type LucideProps } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { formatRelative } from '@/lib/format';
import { cn } from '@/lib/utils';

export interface ScriptCardData {
  slug: string;
  name: string;
  description?: string | null;
  version?: string;
  enabled?: boolean;
  /** 该脚本下实例汇总 */
  instance_count?: number;
  instance_enabled_count?: number;
  /** 上次执行情况 */
  last_run_status?:
    | 'success'
    | 'failure'
    | 'error'
    | 'timeout'
    | 'pending'
    | 'running'
    | 'cancelled'
    | null;
  last_run_at?: string | null;
  next_run_at?: string | null;
  /** 7 天成功率(0~1),null = 没数据 */
  success_rate_7d?: number | null;
}

export interface ScriptCardProps {
  script: ScriptCardData;
  onTrigger?: (slug: string) => void;
  onConfigure?: (slug: string) => void;
  onClick?: (slug: string) => void;
  /** 自定义 icon 组件,默认用脚本首字母 + chart-N 取色 */
  icon?: ComponentType<LucideProps>;
  className?: string;
}

/** 把后端 7 状态映射到 dot color 的 Tailwind class */
function dotColorByStatus(status: ScriptCardData['last_run_status']): string {
  switch (status) {
    case 'success':
      return 'text-success';
    case 'running':
    case 'pending':
      return 'text-info';
    case 'failure':
      return 'text-danger';
    case 'error':
      return 'text-danger';
    case 'timeout':
      return 'text-warning';
    case 'cancelled':
      return 'text-muted-foreground';
    default:
      return 'text-muted-foreground/50';
  }
}

function statusLabel(status: ScriptCardData['last_run_status']): string {
  switch (status) {
    case 'success':
      return '上次成功';
    case 'failure':
      return '上次失败';
    case 'error':
      return '上次错误';
    case 'timeout':
      return '上次超时';
    case 'pending':
      return '等待中';
    case 'running':
      return '执行中';
    case 'cancelled':
      return '已取消';
    default:
      return '尚未执行';
  }
}

/** 取脚本首字符(中/英),用作 fallback icon */
function initials(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return '·';
  // 优先汉字 → 取第 1 字;英文 → 取首字母(大写)
  const first = trimmed[0];
  if (!first) return '·';
  return /[A-Za-z]/.test(first) ? first.toUpperCase() : first;
}

/** 由 slug 派生 chart-N(1~5)取色 */
function variantBySlug(slug: string): 1 | 2 | 3 | 4 | 5 {
  let h = 0;
  for (let i = 0; i < slug.length; i += 1) h = (h * 31 + slug.charCodeAt(i)) | 0;
  return ((Math.abs(h) % 5) + 1) as 1 | 2 | 3 | 4 | 5;
}

function ScriptCardImpl({
  script,
  onTrigger,
  onConfigure,
  onClick,
  icon: Icon,
  className,
}: ScriptCardProps) {
  const variant = variantBySlug(script.slug);
  const isPulse = script.last_run_status === 'running' || script.last_run_status === 'pending';
  const dotColor = dotColorByStatus(script.last_run_status);
  const successRate = typeof script.success_rate_7d === 'number'
    ? `${(script.success_rate_7d * 100).toFixed(1)}%`
    : '—';

  return (
    <Card
      className={cn(
        'group relative flex min-h-[220px] flex-col gap-4 p-5',
        'transition-all duration-200 ease-[cubic-bezier(0.25,1,0.5,1)]',
        'hover:-translate-y-0.5 hover:shadow-md',
        onClick && 'cursor-pointer',
        className,
      )}
      onClick={onClick ? () => onClick(script.slug) : undefined}
    >
      {/* 顶部:icon + 名称 + 状态点 */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          {Icon ? (
            <div
              className="flex size-12 shrink-0 items-center justify-center rounded-xl border border-border/50"
              style={{ background: `color-mix(in oklch, var(--chart-${variant}) 12%, transparent)` }}
            >
              <Icon className="size-6" strokeWidth={1.75} style={{ color: `var(--chart-${variant})` }} />
            </div>
          ) : (
            <div
              className="flex size-12 shrink-0 items-center justify-center rounded-xl text-base font-semibold"
              style={{
                background: `color-mix(in oklch, var(--chart-${variant}) 14%, transparent)`,
                color: `var(--chart-${variant})`,
              }}
              aria-hidden
            >
              {initials(script.name)}
            </div>
          )}
          <div className="min-w-0 flex-1">
            <h3 className="truncate text-base font-semibold leading-tight text-foreground">
              {script.name}
            </h3>
            <p className="mt-1 truncate font-mono text-[11px] text-muted-foreground/80">
              {script.slug}
              {script.version ? <span className="ml-1.5 text-muted-foreground/50">v{script.version}</span> : null}
            </p>
          </div>
        </div>

        <span
          className={cn('relative isolate mt-1 inline-flex size-2 shrink-0', dotColor)}
          title={statusLabel(script.last_run_status)}
        >
          <span
            className={cn('block size-2 rounded-full bg-current', isPulse && 'dot-pulse')}
          />
        </span>
      </div>

      {/* 描述 */}
      {script.description ? (
        <p className="line-clamp-2 text-sm leading-relaxed text-muted-foreground">
          {script.description}
        </p>
      ) : (
        <p className="line-clamp-2 text-sm italic leading-relaxed text-muted-foreground/50">
          (无描述)
        </p>
      )}

      {/* 元信息 */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs text-muted-foreground/90">
        <div className="flex items-center gap-1.5">
          <Layers className="size-3.5 text-muted-foreground/60" strokeWidth={1.75} />
          <span className="tabular-nums">
            {script.instance_count ?? 0} 实例
            {typeof script.instance_enabled_count === 'number' && script.instance_count !== script.instance_enabled_count
              ? ` · ${script.instance_enabled_count} 启用`
              : ''}
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <Clock className="size-3.5 text-muted-foreground/60" strokeWidth={1.75} />
          <span className="tabular-nums">7d {successRate}</span>
        </div>
        <div className="col-span-2 flex items-center gap-1.5">
          <Calendar className="size-3.5 text-muted-foreground/60" strokeWidth={1.75} />
          <span className="tabular-nums">
            上次 {formatRelative(script.last_run_at)}
            <span className="mx-1.5 text-muted-foreground/40">·</span>
            下次 {formatRelative(script.next_run_at)}
          </span>
        </div>
      </div>

      {/* 底部:状态 badge + actions */}
      <div className="mt-auto flex items-center justify-between gap-2 pt-1">
        <Badge variant="outline" className="font-normal text-muted-foreground">
          {statusLabel(script.last_run_status)}
        </Badge>
        <div className="flex items-center gap-1.5">
          {onConfigure ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                onConfigure(script.slug);
              }}
              aria-label="配置"
            >
              <Settings2 className="size-4" strokeWidth={1.75} />
            </Button>
          ) : null}
          {onTrigger ? (
            <Button
              variant="default"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                onTrigger(script.slug);
              }}
            >
              <Play className="mr-1 size-3.5" strokeWidth={2} />
              运行
            </Button>
          ) : null}
        </div>
      </div>
    </Card>
  );
}

export const ScriptCard = memo(ScriptCardImpl);
