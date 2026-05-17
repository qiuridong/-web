/**
 * 占位组件 — 路由表里给未实现页面填空,供后续批次替换。
 *
 * 拆分独立文件原因:react-refresh/only-export-components 规则要求
 * 同文件不能混合导出组件与非组件(router.tsx 已导出 `router` 对象)。
 */
import type { ReactNode } from 'react';

export interface PlaceholderProps {
  title: string;
  hint?: ReactNode;
}

export function Placeholder({ title, hint }: PlaceholderProps) {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 px-6 text-center">
      <div className="flex items-center gap-2 text-xs uppercase tracking-widest text-muted-foreground">
        <span className="size-1.5 rounded-full bg-primary" />
        签到管家 · 骨架就绪
      </div>
      <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
      {hint ? (
        <p className="max-w-md text-sm text-muted-foreground">{hint}</p>
      ) : null}
      <div className="mt-2 rounded-md border border-border bg-muted/40 px-3 py-1.5 text-xs text-muted-foreground tabular-nums">
        TODO · 等待后续 Frontend 批次接手
      </div>
    </div>
  );
}

export function NotFoundPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 px-6 text-center">
      <h1 className="text-3xl font-semibold tracking-tight">404</h1>
      <p className="max-w-md text-sm text-muted-foreground">
        路径不存在。返回
        <a className="ml-1 underline" href="/dashboard">
          仪表盘
        </a>
        {' 或 '}
        <a className="underline" href="/login">
          登录
        </a>
        。
      </p>
    </div>
  );
}
