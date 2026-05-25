/**
 * Instances 数据 hooks
 *
 * 设计契约:
 *   - 后端 API:`进度/设计/后端架构.md` § 2.3(`/api/v1/instances/*`)
 *   - 前端 wireframe:`进度/设计/前端UI设计.md` § 3.5、§ 3.6、§ 5.2
 *
 * Query keys:
 *   ['instances']                        — root
 *   ['instances', 'list', filter]        — 列表
 *   ['instances', 'detail', id]          — 详情(含 _secret_set)
 *
 * 注意:
 *   - GET 详情时 secret 字段为 null,_secret_set: { field_name: bool } 指示该字段是否已配置
 *   - PATCH 时若 secret 字段为 undefined,后端保持原值;前端 SecretInput / DynamicForm 应正确处理
 *   - mutation 成功后 invalidate 全家(实例数变化影响 scripts 列表与 dashboard)
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

export type InstanceStatus =
  | 'success'
  | 'failure'
  | 'error'
  | 'timeout'
  | 'cancelled'
  | 'pending'
  | 'running';

export interface InstanceListItem {
  id: number;
  name: string;
  description?: string | null;
  script: {
    slug: string;
    name: string;
  };
  /** 同时兼容后端可能仅返回 script_slug 的情况 */
  script_slug?: string;
  cron_expr?: string | null;
  timeout_sec?: number | null;
  enabled: boolean;
  paused_until?: string | null;
  last_run_id?: number | null;
  last_run_status?: InstanceStatus | null;
  last_run_at?: string | null;
  next_run_at?: string | null;
  total_runs: number;
  total_successes: number;
  created_at?: string;
  updated_at?: string;
}

export interface InstanceDetail extends InstanceListItem {
  max_retries?: number;
  retry_interval_sec?: number;
  /** secret 字段后端返回 null;非 secret 字段返回原值 */
  config: Record<string, unknown>;
  /** 标记哪些 secret 字段后端已存值(用于 SecretInput 占位文案) */
  _secret_set?: Record<string, boolean>;
  /** MVP-1 远程 agent:实例绑定的节点 ID(1=local) */
  node_id?: number | null;
}

export interface InstanceCreatePayload {
  script_slug: string;
  name: string;
  description?: string;
  cron_expr?: string;
  timeout_sec?: number;
  max_retries?: number;
  retry_interval_sec?: number;
  config: Record<string, unknown>;
  /** MVP-1 远程 agent:节点 ID,默认 1 = local */
  node_id?: number;
}

export interface InstanceUpdatePayload {
  name?: string;
  description?: string;
  cron_expr?: string;
  timeout_sec?: number;
  max_retries?: number;
  retry_interval_sec?: number;
  /** 未提交的 secret 字段保持原值;部分更新 */
  config?: Record<string, unknown>;
  /** MVP-1:改节点(只改 DB,下次触发才生效) */
  node_id?: number;
}

export interface InstancePausePayload {
  /** ISO8601;到期后自动 resume */
  until: string;
}

export interface InstanceTriggerResponse {
  run_id: number;
}

export interface InstancesFilter {
  script_slug?: string;
  enabled?: boolean;
  status?: InstanceStatus | string;
  page?: number;
  page_size?: number;
}

// ====================== 内部工具 ======================

function unwrapList<T>(raw: unknown): T[] {
  if (Array.isArray(raw)) return raw as T[];
  if (raw && typeof raw === 'object' && Array.isArray((raw as { items?: unknown[] }).items)) {
    return (raw as { items: T[] }).items;
  }
  return [];
}

function buildListPath(filter: InstancesFilter): string {
  const search = new URLSearchParams();
  if (filter.script_slug) search.set('script_slug', filter.script_slug);
  if (filter.enabled !== undefined) search.set('enabled', String(filter.enabled));
  if (filter.status) search.set('status', String(filter.status));
  if (filter.page) search.set('page', String(filter.page));
  if (filter.page_size) search.set('page_size', String(filter.page_size));
  const qs = search.toString();
  return qs ? `/api/v1/instances?${qs}` : '/api/v1/instances';
}

async function fetchInstances(
  filter: InstancesFilter,
  signal?: AbortSignal,
): Promise<InstanceListItem[]> {
  const path = buildListPath(filter);
  const { data, error, response } = await apiClient.GET(path as never, { signal } as never);
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
  return unwrapList<InstanceListItem>(data);
}

async function fetchInstance(id: number, signal?: AbortSignal): Promise<InstanceDetail> {
  const { data, error, response } = await apiClient.GET(
    `/api/v1/instances/${id}` as never,
    { signal } as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
  return (data ?? {}) as InstanceDetail;
}

async function postCreate(payload: InstanceCreatePayload): Promise<InstanceDetail> {
  const { data, error, response } = await apiClient.POST(
    '/api/v1/instances' as never,
    { body: payload } as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
  return (data ?? {}) as InstanceDetail;
}

async function patchUpdate(
  id: number,
  payload: InstanceUpdatePayload,
): Promise<InstanceDetail> {
  const { data, error, response } = await apiClient.PATCH(
    `/api/v1/instances/${id}` as never,
    { body: payload } as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
  return (data ?? {}) as InstanceDetail;
}

async function deleteInstance(id: number): Promise<void> {
  const { error, response } = await apiClient.DELETE(
    `/api/v1/instances/${id}` as never,
    {} as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
}

async function postEnable(id: number): Promise<void> {
  const { error, response } = await apiClient.POST(
    `/api/v1/instances/${id}/enable` as never,
    {} as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
}

async function postDisable(id: number): Promise<void> {
  const { error, response } = await apiClient.POST(
    `/api/v1/instances/${id}/disable` as never,
    {} as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
}

async function postPause(id: number, payload: InstancePausePayload): Promise<void> {
  const { error, response } = await apiClient.POST(
    `/api/v1/instances/${id}/pause` as never,
    { body: payload } as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
}

async function postResume(id: number): Promise<void> {
  const { error, response } = await apiClient.POST(
    `/api/v1/instances/${id}/resume` as never,
    {} as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
}

async function postRun(id: number): Promise<InstanceTriggerResponse> {
  const { data, error, response } = await apiClient.POST(
    `/api/v1/instances/${id}/run` as never,
    {} as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
  return (data ?? {}) as InstanceTriggerResponse;
}

// ====================== Query keys ======================

export const instancesQueryKeys = {
  all: ['instances'] as const,
  list: (filter: InstancesFilter = {}) => ['instances', 'list', filter] as const,
  detail: (id: number) => ['instances', 'detail', id] as const,
};

// ====================== Hooks ======================

export function useInstances(
  filter: InstancesFilter = {},
  enabled = true,
): UseQueryResult<InstanceListItem[], Error> {
  return useQuery({
    queryKey: instancesQueryKeys.list(filter),
    queryFn: ({ signal }) => fetchInstances(filter, signal),
    enabled,
    staleTime: 15_000,
  });
}

export function useInstance(
  id: number | undefined,
): UseQueryResult<InstanceDetail, Error> {
  return useQuery({
    queryKey: instancesQueryKeys.detail(id ?? -1),
    queryFn: ({ signal }) => fetchInstance(id as number, signal),
    enabled: id !== undefined && id > 0,
    staleTime: 15_000,
  });
}

/** alias 与设计稿一致 */
export const useInstanceDetail = useInstance;

function invalidateAllInstanceRelated(qc: ReturnType<typeof useQueryClient>, scriptSlug?: string) {
  void qc.invalidateQueries({ queryKey: instancesQueryKeys.all });
  void qc.invalidateQueries({ queryKey: ['scripts'] });
  void qc.invalidateQueries({ queryKey: ['dashboard'] });
  if (scriptSlug) {
    void qc.invalidateQueries({ queryKey: ['scripts', 'detail', scriptSlug] });
  }
}

export function useCreateInstance(): UseMutationResult<
  InstanceDetail,
  Error,
  InstanceCreatePayload
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload) => postCreate(payload),
    onSuccess: (data, variables) => {
      invalidateAllInstanceRelated(qc, variables.script_slug);
      toast.success(`实例「${data.name ?? variables.name}」已创建`);
    },
  });
}

export function useUpdateInstance(): UseMutationResult<
  InstanceDetail,
  Error,
  { id: number; payload: InstanceUpdatePayload; scriptSlug?: string }
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }) => patchUpdate(id, payload),
    onSuccess: (data, vars) => {
      invalidateAllInstanceRelated(qc, vars.scriptSlug);
      void qc.invalidateQueries({ queryKey: instancesQueryKeys.detail(vars.id) });
      toast.success(`实例「${data.name}」已更新`);
    },
  });
}

export function useDeleteInstance(): UseMutationResult<
  void,
  Error,
  { id: number; scriptSlug?: string }
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id }) => deleteInstance(id),
    onSuccess: (_data, vars) => {
      invalidateAllInstanceRelated(qc, vars.scriptSlug);
      qc.removeQueries({ queryKey: instancesQueryKeys.detail(vars.id) });
      toast.success('实例已删除');
    },
  });
}

export function useEnableInstance(): UseMutationResult<
  void,
  Error,
  { id: number; scriptSlug?: string }
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id }) => postEnable(id),
    onSuccess: (_data, vars) => {
      invalidateAllInstanceRelated(qc, vars.scriptSlug);
      void qc.invalidateQueries({ queryKey: instancesQueryKeys.detail(vars.id) });
      toast.success('已启用');
    },
  });
}

export function useDisableInstance(): UseMutationResult<
  void,
  Error,
  { id: number; scriptSlug?: string }
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id }) => postDisable(id),
    onSuccess: (_data, vars) => {
      invalidateAllInstanceRelated(qc, vars.scriptSlug);
      void qc.invalidateQueries({ queryKey: instancesQueryKeys.detail(vars.id) });
      toast.success('已禁用');
    },
  });
}

export function usePauseInstance(): UseMutationResult<
  void,
  Error,
  { id: number; payload: InstancePausePayload; scriptSlug?: string }
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }) => postPause(id, payload),
    onSuccess: (_data, vars) => {
      invalidateAllInstanceRelated(qc, vars.scriptSlug);
      void qc.invalidateQueries({ queryKey: instancesQueryKeys.detail(vars.id) });
      toast.success('已暂停');
    },
  });
}

export function useResumeInstance(): UseMutationResult<
  void,
  Error,
  { id: number; scriptSlug?: string }
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id }) => postResume(id),
    onSuccess: (_data, vars) => {
      invalidateAllInstanceRelated(qc, vars.scriptSlug);
      void qc.invalidateQueries({ queryKey: instancesQueryKeys.detail(vars.id) });
      toast.success('已恢复');
    },
  });
}

export function useTriggerInstance(): UseMutationResult<
  InstanceTriggerResponse,
  Error,
  { id: number; scriptSlug?: string }
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id }) => postRun(id),
    onSuccess: (data, vars) => {
      invalidateAllInstanceRelated(qc, vars.scriptSlug);
      void qc.invalidateQueries({ queryKey: ['runs'] });
      toast.success(`已触发运行(run #${data.run_id})`);
    },
  });
}
