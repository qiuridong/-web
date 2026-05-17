/**
 * Settings 数据 hooks
 *
 * 设计契约:
 *   - 后端 API:`进度/设计/后端架构.md` § 2.6
 *   - 前端 wireframe:`进度/设计/前端UI设计.md` § 3.10
 *
 * Query keys:
 *   ['settings']                  — 全部 KV
 *   ['settings', key]             — 单项
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';
import { toast } from 'sonner';

import { apiClient } from '@/api/client';
import { formatError } from '@/lib/error';

// ====================== 类型 ======================

export interface SettingValue {
  key: string;
  value: unknown;
  description?: string | null;
  is_secret: boolean;
  updated_at?: string;
}

export type SettingsMap = Record<string, SettingValue>;

export interface ChangePasswordPayload {
  old_password: string;
  new_password: string;
}

// ====================== 内部工具 ======================

async function fetchSettings(signal?: AbortSignal): Promise<SettingsMap> {
  const { data, error, response } = await apiClient.GET(
    '/api/v1/settings' as never,
    { signal } as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
  // 后端可能返回 [{key, value, ...}] 或 {key1: {value...}, ...}
  if (Array.isArray(data)) {
    const m: SettingsMap = {};
    for (const it of data as SettingValue[]) {
      if (it && typeof it.key === 'string') m[it.key] = it;
    }
    return m;
  }
  if (data && typeof data === 'object' && 'items' in (data as object)) {
    const items = (data as { items: SettingValue[] }).items ?? [];
    const m: SettingsMap = {};
    for (const it of items) {
      if (it && typeof it.key === 'string') m[it.key] = it;
    }
    return m;
  }
  return (data ?? {}) as SettingsMap;
}

async function fetchSetting(key: string, signal?: AbortSignal): Promise<SettingValue> {
  const { data, error, response } = await apiClient.GET(
    `/api/v1/settings/${key}` as never,
    { signal } as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
  return (data ?? { key, value: null, is_secret: false }) as SettingValue;
}

async function putSetting(key: string, value: unknown): Promise<SettingValue> {
  const { data, error, response } = await apiClient.PUT(
    `/api/v1/settings/${key}` as never,
    { body: { value } } as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
  return (data ?? { key, value, is_secret: false }) as SettingValue;
}

async function postChangePassword(payload: ChangePasswordPayload): Promise<void> {
  const { error, response } = await apiClient.POST(
    '/api/v1/auth/change-password' as never,
    { body: payload } as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
}

/**
 * 导出备份 — 流式下载 zip;在浏览器内触发 file download
 * 不走 apiClient 是因为 openapi-fetch 不友好处理 binary blob;改 fetch 直调
 */
async function downloadBackup(): Promise<void> {
  const res = await fetch('/api/v1/settings/backup/export', {
    method: 'POST',
    credentials: 'include',
    headers: { 'X-Requested-With': 'fetch', Accept: 'application/zip' },
  });
  if (!res.ok) {
    throw new Error(`备份导出失败 (HTTP ${res.status})`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  const ts = new Date().toISOString().replace(/[:.]/g, '-');
  a.download = `signin-panel-backup-${ts}.zip`;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    URL.revokeObjectURL(url);
    a.remove();
  }, 1500);
}

async function uploadRestore(file: File, overwrite: boolean): Promise<void> {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('overwrite', String(overwrite));
  const res = await fetch('/api/v1/settings/backup/import', {
    method: 'POST',
    credentials: 'include',
    headers: { 'X-Requested-With': 'fetch' },
    body: fd,
  });
  if (!res.ok) {
    let detail = '';
    try {
      detail = (await res.json()).detail ?? '';
    } catch {
      // ignore
    }
    throw new Error(`备份恢复失败 (HTTP ${res.status})${detail ? `:${detail}` : ''}`);
  }
}

// ====================== Query keys ======================

export const settingsQueryKeys = {
  all: ['settings'] as const,
  detail: (key: string) => ['settings', key] as const,
};

// ====================== Hooks ======================

export function useSettings(): UseQueryResult<SettingsMap, Error> {
  return useQuery({
    queryKey: settingsQueryKeys.all,
    queryFn: ({ signal }) => fetchSettings(signal),
    staleTime: 60_000,
  });
}

export function useSetting(key: string | undefined): UseQueryResult<SettingValue, Error> {
  return useQuery({
    queryKey: settingsQueryKeys.detail(key ?? ''),
    queryFn: ({ signal }) => fetchSetting(key as string, signal),
    enabled: !!key,
    staleTime: 60_000,
  });
}

export function useUpdateSetting(): UseMutationResult<
  SettingValue,
  Error,
  { key: string; value: unknown }
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ key, value }) => putSetting(key, value),
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: settingsQueryKeys.all });
      void qc.invalidateQueries({ queryKey: settingsQueryKeys.detail(vars.key) });
      toast.success(`已更新 ${vars.key}`);
    },
  });
}

export function useChangePassword(): UseMutationResult<void, Error, ChangePasswordPayload> {
  return useMutation({
    mutationFn: (payload) => postChangePassword(payload),
    onSuccess: () => {
      toast.success('密码已更新,请重新登录');
    },
  });
}

export function useBackupExport(): UseMutationResult<void, Error, void> {
  return useMutation({
    mutationFn: () => downloadBackup(),
    onSuccess: () => {
      toast.success('备份已下载');
    },
  });
}

export function useBackupImport(): UseMutationResult<
  void,
  Error,
  { file: File; overwrite: boolean }
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ file, overwrite }) => uploadRestore(file, overwrite),
    onSuccess: () => {
      void qc.invalidateQueries();
      toast.success('备份已恢复;部分配置可能需要重启或重新登录');
    },
  });
}
