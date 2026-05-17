/**
 * <PageHeader> — 统一页头
 *
 * 设计契约:`进度/设计/前端UI设计.md` § 4(公共组件清单)、§ 3(关键页面 wireframe)。
 *
 * 结构:
 *   [可选 breadcrumb]
 *   ┌──────────────────────────────────────┐
 *   │ Title                       [actions] │
 *   │ description(muted, 小字)             │
 *   └──────────────────────────────────────┘
 *   ─── 底部 border-b ───
 *
 * 用法:
 *   <PageHeader
 *     title="脚本"
 *     description="已发现 12 个插件,启用 8 个"
 *     breadcrumb={[{ label: '首页', to: '/dashboard' }, { label: '脚本' }]}
 *     actions={<><Button variant="outline">扫描</Button><Button>新建实例</Button></>}
 *   />
 */
import { Fragment } from 'react';
import { Link } from 'react-router';
import type { ReactNode } from 'react';
import { ChevronRight } from 'lucide-react';

import { cn } from '@/lib/utils';

export interface BreadcrumbItem {
  label: string;
  /** 不传则不可点击(当前页) */
  to?: string;
}

export interface PageHeaderProps {
  title: string;
  description?: string;
  breadcrumb?: BreadcrumbItem[];
  actions?: ReactNode;
  className?: string;
}

export function PageHeader({
  title,
  description,
  breadcrumb,
  actions,
  className,
}: PageHeaderProps) {
  return (
    <header
      className={cn(
        'flex flex-col gap-3 border-b border-border pb-5 mb-6',
        className,
      )}
    >
      {breadcrumb && breadcrumb.length > 0 ? (
        <nav
          aria-label="breadcrumb"
          className="flex items-center gap-1 text-xs text-muted-foreground"
        >
          {breadcrumb.map((item, i) => {
            const isLast = i === breadcrumb.length - 1;
            return (
              <Fragment key={`${item.label}-${i}`}>
                {item.to && !isLast ? (
                  <Link
                    to={item.to}
                    className="rounded px-1 py-0.5 transition-colors hover:bg-accent hover:text-foreground"
                  >
                    {item.label}
                  </Link>
                ) : (
                  <span
                    className={cn(
                      'px-1 py-0.5',
                      isLast && 'font-medium text-foreground',
                    )}
                    aria-current={isLast ? 'page' : undefined}
                  >
                    {item.label}
                  </span>
                )}
                {!isLast ? (
                  <ChevronRight
                    size={12}
                    strokeWidth={1.75}
                    className="text-muted-foreground/60"
                    aria-hidden
                  />
                ) : null}
              </Fragment>
            );
          })}
        </nav>
      ) : null}

      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex min-w-0 flex-col gap-1.5">
          <h1 className="text-2xl font-semibold tracking-tight text-foreground sm:text-[28px]">
            {title}
          </h1>
          {description ? (
            <p className="text-sm leading-relaxed text-muted-foreground">
              {description}
            </p>
          ) : null}
        </div>
        {actions ? (
          <div className="flex shrink-0 items-center gap-2">{actions}</div>
        ) : null}
      </div>
    </header>
  );
}

export default PageHeader;
