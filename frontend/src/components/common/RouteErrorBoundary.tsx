/**
 * 路由级 ErrorBoundary — 兜住 React Router 子路由 throw 的错(运行时 / loader / action)
 *
 * 挂在 layout 路由的 `errorElement`,替换 React Router 默认的"unexpected application error"
 * 丑陋兜底页。设计稿调性:克制 + 中文 + 给出有效操作按钮(返回 / 回首页 / 刷新)。
 */
import { useNavigate, useRouteError, isRouteErrorResponse } from 'react-router';
import { AlertTriangle, RotateCw, Home, ArrowLeft } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export function RouteErrorBoundary() {
  const navigate = useNavigate();
  const error = useRouteError();

  // 解析错误信息(兼容多种形态)
  let title = '页面出错了';
  let message = '抱歉,这个页面遇到了未预期的问题。';
  let detail = '';
  if (isRouteErrorResponse(error)) {
    title = `HTTP ${error.status}`;
    message = error.statusText || message;
    detail = typeof error.data === 'string' ? error.data : JSON.stringify(error.data ?? '');
  } else if (error instanceof Error) {
    detail = error.message;
    if (error.stack) {
      detail += '\n\n' + error.stack.split('\n').slice(0, 6).join('\n');
    }
  } else if (typeof error === 'string') {
    detail = error;
  }

  return (
    <div
      className={cn(
        'flex min-h-[60vh] w-full items-center justify-center px-6 py-12',
      )}
    >
      <div className="mx-auto w-full max-w-xl text-center">
        <div className="mx-auto mb-5 flex size-14 items-center justify-center rounded-full bg-destructive/10 text-destructive">
          <AlertTriangle size={28} strokeWidth={1.75} />
        </div>

        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        <p className="mt-2 text-sm text-muted-foreground">{message}</p>

        {detail ? (
          <details className="mt-6 rounded-lg border border-border bg-muted/30 p-4 text-left">
            <summary className="cursor-pointer text-xs font-medium text-muted-foreground hover:text-foreground">
              错误详情(开发者请将以下信息提供给维护者)
            </summary>
            <pre className="mt-3 overflow-auto whitespace-pre-wrap break-all text-[11px] leading-relaxed text-muted-foreground">
              {detail}
            </pre>
          </details>
        ) : null}

        <div className="mt-6 flex flex-wrap items-center justify-center gap-2">
          <Button variant="outline" size="sm" onClick={() => window.location.reload()}>
            <RotateCw size={14} strokeWidth={1.75} className="mr-1.5" />
            刷新页面
          </Button>
          <Button variant="outline" size="sm" onClick={() => navigate(-1)}>
            <ArrowLeft size={14} strokeWidth={1.75} className="mr-1.5" />
            返回上一页
          </Button>
          <Button size="sm" onClick={() => navigate('/dashboard')}>
            <Home size={14} strokeWidth={1.75} className="mr-1.5" />
            回首页
          </Button>
        </div>
      </div>
    </div>
  );
}

export default RouteErrorBoundary;
