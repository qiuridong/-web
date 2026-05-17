/**
 * TanStack Query QueryClient 单例
 *
 * 设计契约:`进度/设计/前端UI设计.md` § 5、§ 6。
 *
 * defaults:
 *   - staleTime 30s:30 秒内不重复请求(对仪表盘/列表足够)
 *   - gcTime 5min:5 分钟未引用的缓存被回收
 *   - refetchOnWindowFocus:用户切回标签页主动刷新
 *   - retry:401 不重试;>= 2 次失败放弃
 *   - mutation onError:全局 toast(避免每个 mutation 都写 onError)
 */
import { QueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { formatError, isUnauthorized } from '@/lib/error';

/**
 * 判断是否是 fetch 主动 cancel 的 abort 错误。
 * React Query 在组件 unmount / refetch 抢占 / staleTime 内重复请求时
 * 会主动 abort pending fetch,这是正常行为,不能当业务错误 toast 给用户。
 *
 * 历史 bug:用户做任何修改时(切页面 / 关 dialog / 快速点保存)都可能
 * 触发 abort,被 toast 出来误导用户以为"操作失败"。
 */
function isAbortError(err: unknown): boolean {
  if (!err || typeof err !== 'object') return false;
  const e = err as { name?: string; message?: string; code?: string };
  const msg = e.message ?? '';
  return (
    e.name === 'AbortError' ||
    e.code === 'ERR_CANCELED' ||
    msg.includes('aborted') ||
    msg.includes('signal is aborted') ||
    msg.includes('The user aborted')
  );
}

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 5 * 60_000,
      refetchOnWindowFocus: true,
      refetchOnReconnect: 'always',
      retry: (failureCount: number, err: unknown) => {
        if (isUnauthorized(err)) return false;
        if (isAbortError(err)) return false; // abort 不重试,直接放过
        return failureCount < 2;
      },
    },
    mutations: {
      retry: false,
      onError: (err: unknown) => {
        // 不在 401 时再 toast(client.ts errorMiddleware 已处理跳转)
        if (isUnauthorized(err)) return;
        // 不在 abort 时 toast(React Query 主动 cancel 是正常行为)
        if (isAbortError(err)) return;
        toast.error(formatError(err));
      },
    },
  },
});
