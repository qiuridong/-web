/**
 * TanStack Query 鉴权 hooks
 *
 * 设计契约:`进度/设计/前端UI设计.md` § 5.2(query factory)、§ 6(API 封装)。
 * 后端契约:`进度/设计/后端架构.md` § 2.1。
 *
 * 端点(全部相对 baseUrl):
 *   GET    /api/v1/auth/setup-status   → { needs_setup: bool }
 *   POST   /api/v1/auth/setup          ← { username, password, display_name? }
 *   POST   /api/v1/auth/login          ← { username, password }
 *   POST   /api/v1/auth/logout         → 204
 *   GET    /api/v1/auth/me             → { id, username, display_name, is_admin, last_login_at }
 *
 * query key 命名:
 *   ['auth', 'setup-status']
 *   ['auth', 'me']
 *
 * 注意:apiClient 当前 createClient<any>(schema.d.ts 待生成),所以本文件用最小手写类型;
 *      后端起来跑 `pnpm gen:api` 后,可把这些手写类型替换成 `components['schemas']['XxxResponse']`。
 *
 *  - 401/403 由 client.ts middleware dispatchEvent('app:unauthorized'),
 *    AppLayout 监听后跳 /login,本文件不做副作用。
 *  - useCurrentUser:`retry: false`(未登录不要重试 3 次)。
 *  - useLogin / useSetup:成功后 invalidate ['auth'] 让 setup-status / me 立刻刷新。
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryOptions,
} from '@tanstack/react-query';

import apiClient from '@/api/client';
import type { AuthUser } from '@/stores/auth.store';

/* ============ 类型(后端 schema 生成后可替换) ============ */

export interface SetupStatus {
  needs_setup: boolean;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface SetupRequest {
  username: string;
  password: string;
  display_name?: string;
}

export interface MeResponse {
  id: number | string;
  username: string;
  display_name?: string | null;
  is_admin?: boolean;
  last_login_at?: string | null;
  created_at?: string | null;
}

export interface LoginResponse {
  user: MeResponse;
}

/* ============ query keys ============ */

export const authKeys = {
  all: ['auth'] as const,
  setupStatus: () => [...authKeys.all, 'setup-status'] as const,
  me: () => [...authKeys.all, 'me'] as const,
};

/* ============ 工具:MeResponse → AuthUser(store 兼容) ============ */

export function meToAuthUser(me: MeResponse): AuthUser {
  return {
    id: me.id,
    username: me.username,
    displayName: me.display_name ?? undefined,
    role: me.is_admin ? 'admin' : 'user',
    createdAt: me.created_at ?? undefined,
  };
}

/* ============ queries ============ */

/**
 * useSetupStatus — 首屏:是否需要初始化管理员
 *
 * staleTime Infinity:setup-status 在一个 session 内基本不变(只有 POST /setup 后会变 false);
 * 配合 useSetup onSuccess 主动 invalidate 即可。
 */
export function useSetupStatus(
  options?: Omit<UseQueryOptions<SetupStatus>, 'queryKey' | 'queryFn'>,
) {
  return useQuery<SetupStatus>({
    queryKey: authKeys.setupStatus(),
    queryFn: async ({ signal }) => {
      const { data, error, response } = await apiClient.GET(
        '/api/v1/auth/setup-status',
        { signal },
      );
      if (error || !data) {
        throw {
          status: response?.status,
          detail: error,
          message: '获取初始化状态失败',
        };
      }
      return data as SetupStatus;
    },
    staleTime: Number.POSITIVE_INFINITY,
    retry: 1,
    ...options,
  });
}

/**
 * useCurrentUser — 当前登录用户。401 → 抛错(不重试)。
 *
 * `enabled` 默认 true;调用方(loader / Layout)若已知未登录态可传 false 避免噪音。
 */
export function useCurrentUser(
  options?: Omit<UseQueryOptions<MeResponse>, 'queryKey' | 'queryFn'>,
) {
  return useQuery<MeResponse>({
    queryKey: authKeys.me(),
    queryFn: async ({ signal }) => {
      const { data, error, response } = await apiClient.GET(
        '/api/v1/auth/me',
        { signal },
      );
      if (error || !data) {
        throw {
          status: response?.status,
          detail: error,
          message: '获取当前用户失败',
        };
      }
      return data as MeResponse;
    },
    staleTime: 60_000,
    retry: false,
    ...options,
  });
}

/* ============ mutations ============ */

/**
 * useLogin — POST /auth/login
 *
 * 成功后:
 *   - invalidate ['auth'](让 setup-status / me 立刻刷新)
 *   - 不在此 hook 内跳路由,调用方(Login.tsx)决定去 /dashboard
 */
export function useLogin() {
  const qc = useQueryClient();
  return useMutation<LoginResponse, unknown, LoginRequest>({
    mutationFn: async (body) => {
      const { data, error, response } = await apiClient.POST(
        '/api/v1/auth/login',
        { body },
      );
      if (error || !data) {
        throw {
          status: response?.status,
          detail: error,
          message: '登录失败',
        };
      }
      return data as LoginResponse;
    },
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: authKeys.all });
    },
  });
}

/**
 * useSetup — POST /auth/setup
 *
 * 后端契约:成功后自动登录(返回 user)。
 */
export function useSetup() {
  const qc = useQueryClient();
  return useMutation<LoginResponse, unknown, SetupRequest>({
    mutationFn: async (body) => {
      const { data, error, response } = await apiClient.POST(
        '/api/v1/auth/setup',
        { body },
      );
      if (error || !data) {
        throw {
          status: response?.status,
          detail: error,
          message: '初始化失败',
        };
      }
      return data as LoginResponse;
    },
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: authKeys.all });
    },
  });
}

/**
 * useLogout — POST /auth/logout(204)
 *
 * 成功后:
 *   - removeQueries ['auth', 'me'](立即清缓存,避免下一次渲染拿旧 user)
 *   - invalidate setup-status(理论上不变,但保险)
 */
export function useLogout() {
  const qc = useQueryClient();
  return useMutation<void, unknown, void>({
    mutationFn: async () => {
      const { error, response } = await apiClient.POST(
        '/api/v1/auth/logout',
        {},
      );
      if (error && response?.status && response.status >= 400) {
        throw {
          status: response.status,
          detail: error,
          message: '退出失败',
        };
      }
    },
    onSuccess: () => {
      qc.removeQueries({ queryKey: authKeys.me() });
      qc.invalidateQueries({ queryKey: authKeys.setupStatus() });
    },
  });
}
