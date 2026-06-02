/**
 * 鉴权上下文:cookie session。
 * - 启动拉 /api/auth/me 判断登录态(401 = 未登录,静默)。
 * - 拉 /api/auth/setup 判断是否需初始化管理员。
 * - 暴露 login / setup / logout。
 */
import * as React from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { api, ApiError } from '@/api/client';
import type { SetupStateResponse, UserResponse } from '@/api/types';

interface AuthContextValue {
  user: UserResponse | null;
  isLoading: boolean;
  setupRequired: boolean;
  login: (username: string, password: string) => Promise<void>;
  setup: (username: string, password: string, displayName?: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = React.createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const qc = useQueryClient();

  const meQuery = useQuery<UserResponse | null>({
    queryKey: ['auth', 'me'],
    queryFn: async () => {
      try {
        return await api.get<UserResponse>('/api/auth/me');
      } catch (e) {
        if (e instanceof ApiError && e.isUnauthorized) return null;
        throw e;
      }
    },
    staleTime: 60_000,
    retry: false,
  });

  const setupQuery = useQuery<SetupStateResponse>({
    queryKey: ['auth', 'setup'],
    queryFn: () => api.get<SetupStateResponse>('/api/auth/setup'),
    staleTime: 60_000,
    retry: false,
  });

  const refreshAuth = React.useCallback(async () => {
    await Promise.all([
      qc.invalidateQueries({ queryKey: ['auth', 'me'] }),
      qc.invalidateQueries({ queryKey: ['auth', 'setup'] }),
    ]);
  }, [qc]);

  const login = React.useCallback(
    async (username: string, password: string) => {
      await api.post<UserResponse>('/api/auth/login', { username, password });
      await refreshAuth();
    },
    [refreshAuth],
  );

  const setup = React.useCallback(
    async (username: string, password: string, displayName?: string) => {
      await api.post<UserResponse>('/api/auth/setup', {
        username,
        password,
        display_name: displayName || undefined,
      });
      await refreshAuth();
    },
    [refreshAuth],
  );

  const logout = React.useCallback(async () => {
    try {
      await api.post('/api/auth/logout');
    } finally {
      qc.setQueryData(['auth', 'me'], null);
      await refreshAuth();
    }
  }, [qc, refreshAuth]);

  const value = React.useMemo<AuthContextValue>(
    () => ({
      user: meQuery.data ?? null,
      isLoading: meQuery.isLoading || setupQuery.isLoading,
      setupRequired: setupQuery.data?.setup_required ?? false,
      login,
      setup,
      logout,
    }),
    [meQuery.data, meQuery.isLoading, setupQuery.data, setupQuery.isLoading, login, setup, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = React.useContext(AuthContext);
  if (!ctx) throw new Error('useAuth 必须在 <AuthProvider> 内使用');
  return ctx;
}
