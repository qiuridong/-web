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

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 5 * 60_000,
      refetchOnWindowFocus: true,
      refetchOnReconnect: 'always',
      retry: (failureCount: number, err: unknown) => {
        if (isUnauthorized(err)) return false;
        return failureCount < 2;
      },
    },
    mutations: {
      retry: false,
      onError: (err: unknown) => {
        // 不在 401 时再 toast(client.ts errorMiddleware 已处理跳转)
        if (isUnauthorized(err)) return;
        toast.error(formatError(err));
      },
    },
  },
});
