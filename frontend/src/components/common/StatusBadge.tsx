/**
 * <StatusBadge> — 语义化状态徽章 + 呼吸光晕点
 *
 * 设计契约:`进度/设计/前端UI设计.md` § 4(公共组件清单)、§ 8(状态点呼吸 / pulseDot)。
 *
 * 7 种状态:
 *   - success / failure / running / pending / disabled / unknown
 *   - 实际后端 RunStatus 还有 'cancelled' 与 'timeout',这里映射为 failure。
 *
 * 视觉:
 *   - 一个 8px 圆点 + 状态文字
 *   - running / pending 加 `.dot-pulse` 类(::before 伪元素 pulseDot 2s 呼吸)
 *   - badge 形态用 outline 风浅底,与卡片融合不抢色;dot 自己上色,文字偏深用 foreground
 *   - 全部尺寸 size-2(8px)圆点,与设计稿一致
 */
import { cn } from '@/lib/utils';

export type Status =
  | 'success'
  | 'failure'
  | 'running'
  | 'pending'
  | 'disabled'
  | 'unknown';

export interface StatusBadgeProps {
  status: Status;
  /** 自定义文字(覆盖默认中文标签) */
  label?: string;
  /** 仅显示圆点,不显示文字(用于表格行尾的紧凑场景) */
  dotOnly?: boolean;
  className?: string;
}

interface StatusMeta {
  label: string;
  /** 圆点颜色 class(用 text-* 让 currentColor 给 ::before 也染色) */
  dotColor: string;
  /** 是否呼吸 */
  pulse: boolean;
}

const STATUS_META: Record<Status, StatusMeta> = {
  success: { label: '成功', dotColor: 'text-success', pulse: false },
  failure: { label: '失败', dotColor: 'text-danger', pulse: false },
  running: { label: '运行中', dotColor: 'text-info', pulse: true },
  pending: { label: '等待中', dotColor: 'text-warning', pulse: true },
  disabled: { label: '已禁用', dotColor: 'text-muted-foreground', pulse: false },
  unknown: { label: '未知', dotColor: 'text-muted-foreground', pulse: false },
};

export function StatusBadge({
  status,
  label,
  dotOnly = false,
  className,
}: StatusBadgeProps) {
  const meta = STATUS_META[status];
  const text = label ?? meta.label;

  return (
    <span
      className={cn(
        'inline-flex items-center gap-2',
        dotOnly && 'gap-0',
        className,
      )}
      role="status"
      aria-label={text}
    >
      <span
        className={cn('relative inline-flex size-2 isolate', meta.dotColor)}
      >
        <span
          className={cn(
            'block size-2 rounded-full bg-current',
            meta.pulse && 'dot-pulse',
          )}
        />
      </span>
      {dotOnly ? null : (
        <span className="text-xs font-medium leading-none text-foreground">
          {text}
        </span>
      )}
    </span>
  );
}

export default StatusBadge;
