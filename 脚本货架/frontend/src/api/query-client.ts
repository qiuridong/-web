import { QueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { ApiError } from './client';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: (failureCount, error) => {
        // 401 / 404 不重试;其它最多 1 次
        if (error instanceof ApiError && (error.status === 401 || error.status === 404)) {
          return false;
        }
        return failureCount < 1;
      },
      refetchOnWindowFocus: false,
    },
    mutations: {
      onError: (error) => {
        if (error instanceof ApiError) {
          // 401 由各调用处引导登录,这里只对非鉴权错误弹 toast
          if (!error.isUnauthorized) {
            toast.error(error.message);
          }
          return;
        }
        toast.error(error instanceof Error ? error.message : '操作失败');
      },
    },
  },
});
