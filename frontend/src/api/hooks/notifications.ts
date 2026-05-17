/**
 * Notifications 数据 hooks(渠道 + 规则)
 *
 * 设计契约:
 *   - 后端 API:`进度/设计/后端架构.md` § 2.5
 *   - 前端 wireframe:`进度/设计/前端UI设计.md` § 3.9
 *
 * Query keys:
 *   ['notifications', 'channels', filter]
 *   ['notifications', 'channels', id]
 *   ['notifications', 'rules', filter]
 *   ['notifications', 'rules', id]
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

export interface NotificationChannel {
  id: number;
  name: string;
  type: string; // 'apprise' v1 only
  /** GET 时脱敏(scheme://***\/***);POST/PATCH 时传明文 */
  apprise_url?: string | null;
  enabled: boolean;
  description?: string | null;
  last_test_at?: string | null;
  last_test_ok?: boolean | null;
  created_at?: string;
  updated_at?: string;
}

export interface ChannelCreatePayload {
  name: string;
  type?: string;
  apprise_url: string;
  description?: string;
  enabled?: boolean;
}

export interface ChannelUpdatePayload {
  name?: string;
  type?: string;
  /** 不传 → 后端保持原值 */
  apprise_url?: string;
  description?: string;
  enabled?: boolean;
}

export interface ChannelTestPayload {
  title?: string;
  body?: string;
}

export interface ChannelTestResult {
  ok: boolean;
  error?: string;
  latency_ms?: number;
}

export type NotificationScope = 'global' | 'script' | 'instance';
export type NotificationEvent = 'success' | 'failure' | 'error' | 'timeout' | 'any';

export interface NotificationRule {
  id: number;
  name: string;
  scope: NotificationScope;
  script_id?: number | null;
  instance_id?: number | null;
  event: NotificationEvent;
  channel_id: number;
  template?: string | null;
  min_interval_sec: number;
  last_fired_at?: string | null;
  enabled: boolean;
  created_at?: string;
  updated_at?: string;
  /** 后端可能 join 出来的关联信息 */
  channel?: { id: number; name: string; type?: string };
  script?: { id: number; slug: string; name: string };
  instance?: { id: number; name: string };
}

export interface RuleCreatePayload {
  name: string;
  scope: NotificationScope;
  script_id?: number;
  instance_id?: number;
  event: NotificationEvent;
  channel_id: number;
  template?: string;
  min_interval_sec?: number;
  enabled?: boolean;
}

export interface RuleUpdatePayload {
  name?: string;
  scope?: NotificationScope;
  script_id?: number | null;
  instance_id?: number | null;
  event?: NotificationEvent;
  channel_id?: number;
  template?: string | null;
  min_interval_sec?: number;
  enabled?: boolean;
}

export interface RulePreviewResult {
  title?: string;
  body: string;
}

export interface ChannelsFilter {
  enabled?: boolean;
}

export interface RulesFilter {
  scope?: NotificationScope;
  script_id?: number;
  instance_id?: number;
  channel_id?: number;
}

// ====================== 内部工具 ======================

function unwrapList<T>(raw: unknown): T[] {
  if (Array.isArray(raw)) return raw as T[];
  if (raw && typeof raw === 'object' && Array.isArray((raw as { items?: unknown[] }).items)) {
    return (raw as { items: T[] }).items;
  }
  return [];
}

function buildQs(filter: Record<string, unknown>): string {
  const search = new URLSearchParams();
  for (const [k, v] of Object.entries(filter)) {
    if (v !== undefined && v !== null && v !== '') {
      search.set(k, String(v));
    }
  }
  const qs = search.toString();
  return qs ? `?${qs}` : '';
}

// ====================== Channel API ======================

async function fetchChannels(
  filter: ChannelsFilter,
  signal?: AbortSignal,
): Promise<NotificationChannel[]> {
  const { data, error, response } = await apiClient.GET(
    `/api/v1/notifications/channels${buildQs(filter as Record<string, unknown>)}` as never,
    { signal } as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
  return unwrapList<NotificationChannel>(data);
}

async function fetchChannel(id: number, signal?: AbortSignal): Promise<NotificationChannel> {
  const { data, error, response } = await apiClient.GET(
    `/api/v1/notifications/channels/${id}` as never,
    { signal } as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
  return (data ?? {}) as NotificationChannel;
}

async function postChannel(payload: ChannelCreatePayload): Promise<NotificationChannel> {
  const { data, error, response } = await apiClient.POST(
    '/api/v1/notifications/channels' as never,
    { body: payload } as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
  return (data ?? {}) as NotificationChannel;
}

async function patchChannel(
  id: number,
  payload: ChannelUpdatePayload,
): Promise<NotificationChannel> {
  const { data, error, response } = await apiClient.PATCH(
    `/api/v1/notifications/channels/${id}` as never,
    { body: payload } as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
  return (data ?? {}) as NotificationChannel;
}

async function deleteChannelApi(id: number): Promise<void> {
  const { error, response } = await apiClient.DELETE(
    `/api/v1/notifications/channels/${id}` as never,
    {} as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
}

async function postTestChannel(
  id: number,
  payload: ChannelTestPayload = {},
): Promise<ChannelTestResult> {
  const { data, error, response } = await apiClient.POST(
    `/api/v1/notifications/channels/${id}/test` as never,
    { body: payload } as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
  return (data ?? { ok: false }) as ChannelTestResult;
}

// ====================== Rule API ======================

async function fetchRules(filter: RulesFilter, signal?: AbortSignal): Promise<NotificationRule[]> {
  const { data, error, response } = await apiClient.GET(
    `/api/v1/notifications/rules${buildQs(filter as Record<string, unknown>)}` as never,
    { signal } as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
  return unwrapList<NotificationRule>(data);
}

async function fetchRule(id: number, signal?: AbortSignal): Promise<NotificationRule> {
  const { data, error, response } = await apiClient.GET(
    `/api/v1/notifications/rules/${id}` as never,
    { signal } as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
  return (data ?? {}) as NotificationRule;
}

async function postRule(payload: RuleCreatePayload): Promise<NotificationRule> {
  const { data, error, response } = await apiClient.POST(
    '/api/v1/notifications/rules' as never,
    { body: payload } as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
  return (data ?? {}) as NotificationRule;
}

async function patchRule(id: number, payload: RuleUpdatePayload): Promise<NotificationRule> {
  const { data, error, response } = await apiClient.PATCH(
    `/api/v1/notifications/rules/${id}` as never,
    { body: payload } as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
  return (data ?? {}) as NotificationRule;
}

async function deleteRuleApi(id: number): Promise<void> {
  const { error, response } = await apiClient.DELETE(
    `/api/v1/notifications/rules/${id}` as never,
    {} as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
}

async function postPreviewRule(id: number): Promise<RulePreviewResult> {
  const { data, error, response } = await apiClient.POST(
    `/api/v1/notifications/rules/${id}/preview` as never,
    {} as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
  return (data ?? { body: '' }) as RulePreviewResult;
}

// ====================== Query keys ======================

export const notificationsQueryKeys = {
  channels: {
    all: ['notifications', 'channels'] as const,
    list: (filter: ChannelsFilter = {}) =>
      ['notifications', 'channels', 'list', filter] as const,
    detail: (id: number) => ['notifications', 'channels', 'detail', id] as const,
  },
  rules: {
    all: ['notifications', 'rules'] as const,
    list: (filter: RulesFilter = {}) =>
      ['notifications', 'rules', 'list', filter] as const,
    detail: (id: number) => ['notifications', 'rules', 'detail', id] as const,
  },
};

// ====================== Hooks · Channels ======================

export function useNotificationChannels(
  filter: ChannelsFilter = {},
): UseQueryResult<NotificationChannel[], Error> {
  return useQuery({
    queryKey: notificationsQueryKeys.channels.list(filter),
    queryFn: ({ signal }) => fetchChannels(filter, signal),
    staleTime: 30_000,
  });
}

export function useNotificationChannel(
  id: number | undefined,
): UseQueryResult<NotificationChannel, Error> {
  return useQuery({
    queryKey: notificationsQueryKeys.channels.detail(id ?? -1),
    queryFn: ({ signal }) => fetchChannel(id as number, signal),
    enabled: id !== undefined && id > 0,
    staleTime: 30_000,
  });
}

export function useCreateChannel(): UseMutationResult<
  NotificationChannel,
  Error,
  ChannelCreatePayload
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload) => postChannel(payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: notificationsQueryKeys.channels.all });
      toast.success('渠道已创建');
    },
  });
}

export function useUpdateChannel(): UseMutationResult<
  NotificationChannel,
  Error,
  { id: number; payload: ChannelUpdatePayload }
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }) => patchChannel(id, payload),
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: notificationsQueryKeys.channels.all });
      void qc.invalidateQueries({ queryKey: notificationsQueryKeys.channels.detail(vars.id) });
      toast.success('渠道已更新');
    },
  });
}

export function useDeleteChannel(): UseMutationResult<void, Error, number> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => deleteChannelApi(id),
    onSuccess: (_data, id) => {
      void qc.invalidateQueries({ queryKey: notificationsQueryKeys.channels.all });
      void qc.invalidateQueries({ queryKey: notificationsQueryKeys.rules.all });
      qc.removeQueries({ queryKey: notificationsQueryKeys.channels.detail(id) });
      toast.success('渠道已删除');
    },
  });
}

export function useTestChannel(): UseMutationResult<
  ChannelTestResult,
  Error,
  { id: number; payload?: ChannelTestPayload }
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }) => postTestChannel(id, payload),
    onSuccess: (data, vars) => {
      void qc.invalidateQueries({ queryKey: notificationsQueryKeys.channels.detail(vars.id) });
      if (data.ok) {
        toast.success(`测试发送成功(${data.latency_ms ?? '-'} ms)`);
      } else {
        toast.error(`测试失败:${data.error ?? '未知错误'}`);
      }
    },
  });
}

// ====================== Hooks · Rules ======================

export function useNotificationRules(
  filter: RulesFilter = {},
): UseQueryResult<NotificationRule[], Error> {
  return useQuery({
    queryKey: notificationsQueryKeys.rules.list(filter),
    queryFn: ({ signal }) => fetchRules(filter, signal),
    staleTime: 30_000,
  });
}

export function useNotificationRule(
  id: number | undefined,
): UseQueryResult<NotificationRule, Error> {
  return useQuery({
    queryKey: notificationsQueryKeys.rules.detail(id ?? -1),
    queryFn: ({ signal }) => fetchRule(id as number, signal),
    enabled: id !== undefined && id > 0,
    staleTime: 30_000,
  });
}

export function useCreateRule(): UseMutationResult<NotificationRule, Error, RuleCreatePayload> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload) => postRule(payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: notificationsQueryKeys.rules.all });
      toast.success('规则已创建');
    },
  });
}

export function useUpdateRule(): UseMutationResult<
  NotificationRule,
  Error,
  { id: number; payload: RuleUpdatePayload }
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }) => patchRule(id, payload),
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: notificationsQueryKeys.rules.all });
      void qc.invalidateQueries({ queryKey: notificationsQueryKeys.rules.detail(vars.id) });
      toast.success('规则已更新');
    },
  });
}

export function useDeleteRule(): UseMutationResult<void, Error, number> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id) => deleteRuleApi(id),
    onSuccess: (_data, id) => {
      void qc.invalidateQueries({ queryKey: notificationsQueryKeys.rules.all });
      qc.removeQueries({ queryKey: notificationsQueryKeys.rules.detail(id) });
      toast.success('规则已删除');
    },
  });
}

export function usePreviewRule(): UseMutationResult<RulePreviewResult, Error, number> {
  return useMutation({
    mutationFn: (id) => postPreviewRule(id),
  });
}
