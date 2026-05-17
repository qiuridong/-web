/**
 * <EmptyState> — 通用空态
 *
 * 设计契约:`进度/设计/前端UI设计.md` § 4(公共组件清单)、§ 8(美化关键手法)。
 *
 * 用法:
 *   <EmptyState
 *     icon={Inbox}
 *     title="还没有脚本"
 *     description="点击右上角扫描按钮,自动发现 scripts/ 目录下的所有插件"
 *     action={<Button onClick={...}>立即扫描</Button>}
 *   />
 *
 * 视觉:
 *   - 居中布局,垂直堆叠(icon → title → description → action)
 *   - icon 64px 描边 1.5(比正文 1.75 略细,空态柔和不抢戏)+ muted-foreground
 *   - title 中号粗体 + tracking-tight
 *   - description 小字 + muted-foreground + max-w-md(避免长句撑满)
 *   - action 与 description 间距 6,与外框间距足够呼吸
 */
import type { LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';

import { cn } from '@/lib/utils';

export interface EmptyStateProps {
  /** lucide 图标组件(传入组件本身,不是 JSX) */
  icon: LucideIcon;
  /** 主标题 */
  title: string;
  /** 补充说明,可省略 */
  description?: string;
  /** 主操作(通常是一个 <Button>),可省略 */
  action?: ReactNode;
  /** 额外类名,覆盖最外层 */
  className?: string;
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        'flex w-full flex-col items-center justify-center gap-3 px-6 py-16 text-center',
        className,
      )}
    >
      <div className="mb-2 rounded-full bg-muted/60 p-4 text-muted-foreground">
        <Icon size={48} strokeWidth={1.5} aria-hidden />
      </div>
      <h3 className="text-base font-semibold tracking-tight text-foreground">
        {title}
      </h3>
      {description ? (
        <p className="max-w-md text-sm leading-relaxed text-muted-foreground">
          {description}
        </p>
      ) : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

export default EmptyState;
