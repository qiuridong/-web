/**
 * Scripts 数据 hooks
 *
 * 设计契约:
 *   - 后端 API:`进度/设计/后端架构.md` § 2.2(`/api/v1/scripts/*`)
 *   - 前端 wireframe:`进度/设计/前端UI设计.md` § 3.4 / § 3.5
 *
 * Query keys:
 *   ['scripts']                          — root,扫描后 invalidate
 *   ['scripts', 'list', filter]          — 列表
 *   ['scripts', 'detail', slug]          — 详情
 *
 * 注意:
 *   - 后端 schema.d.ts 还未由 `pnpm gen:api` 生成,本文件用 `apiClient.GET<any>` + 手写 TS 接口。
 *   - 列表暂留 fallback 到 mock 的逻辑(5B agent 的设定),仅在后端 5xx/网络错误时启用。
 *     401 会照旧抛出 → middleware 跳 /login。
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
import { formatError, isUnauthorized } from '@/lib/error';
import { mockScripts, type ScriptListItem } from '@/api/mocks/scripts.mocks';

export type { ScriptListItem } from '@/api/mocks/scripts.mocks';

// ====================== 类型(详情 + 字段 schema,对齐 § 3.1 / § 3.2)======================

export type ScriptFieldType =
  | 'string'
  | 'secret'
  | 'integer'
  | 'boolean'
  | 'select'
  | 'multiselect'
  | 'multiline'
  | 'cron'
  | 'url'
  | 'json';

export interface ScriptFieldOption {
  value: string;
  label: string;
  description?: string;
}

export interface ScriptField {
  key: string;
  label: string;
  type: ScriptFieldType;
  required?: boolean;
  description?: string;
  placeholder?: string;
  group?: string;
  default?: unknown;
  min?: number;
  max?: number;
  step?: number;
  min_length?: number;
  max_length?: number;
  pattern?: string;
  rows?: number;
  options?: ScriptFieldOption[];
  min_items?: number;
  max_items?: number;
  schemes?: string[];
  schema?: string;
}

export interface ScriptRuntime {
  python_version?: string;
  isolated?: boolean;
  env_passthrough?: string[];
  dependencies_file?: string;
}

/**
 * 详情响应,对齐 § 2.2:
 *   列表字段 + fields_schema(已解析数组)+ requirements_present(bool)+ readme_md + icon_url + runtime?
 *
 * 列表 ScriptListItem 来自 mocks 文件(5B agent 领地),未声明 `default_timeout_sec` /
 * `last_scanned_at` / `icon_url`;在详情类型这里补全(后端 § 2.2 列表 + 详情都会返这些字段)。
 */
export interface ScriptDetail extends ScriptListItem {
  default_timeout_sec?: number | null;
  last_scanned_at?: string | null;
  fields_schema: ScriptField[];
  requirements_present: boolean;
  readme_md?: string | null;
  icon_url?: string | null;
  runtime?: ScriptRuntime;
}

export interface ScanScriptsResponse {
  added: string[];
  updated: string[];
  removed: string[];
  errors: { slug: string; error: string }[];
}

export interface ScriptsFilter {
  enabled?: boolean;
  /** 关键字筛选,后端 `q` 参数;前端 fallback 时也做本地子串匹配 */
  search?: string;
}

// ====================== 内部工具 ======================

function applyFilter(items: ScriptListItem[], filter: ScriptsFilter): ScriptListItem[] {
  let out = items;
  if (filter.enabled !== undefined) {
    out = out.filter((s) => s.enabled === filter.enabled);
  }
  if (filter.search && filter.search.trim()) {
    const q = filter.search.trim().toLowerCase();
    out = out.filter(
      (s) =>
        s.slug.toLowerCase().includes(q) ||
        s.name.toLowerCase().includes(q) ||
        (s.description ?? '').toLowerCase().includes(q),
    );
  }
  return out;
}

function unwrapList(raw: unknown): ScriptListItem[] {
  if (Array.isArray(raw)) return raw as ScriptListItem[];
  if (raw && typeof raw === 'object' && Array.isArray((raw as { items?: unknown[] }).items)) {
    return (raw as { items: ScriptListItem[] }).items;
  }
  return [];
}

function buildListPath(filter: ScriptsFilter): string {
  const search = new URLSearchParams();
  if (filter.enabled !== undefined) search.set('enabled', String(filter.enabled));
  if (filter.search && filter.search.trim()) search.set('q', filter.search.trim());
  const qs = search.toString();
  return qs ? `/api/v1/scripts?${qs}` : '/api/v1/scripts';
}

async function fetchScripts(filter: ScriptsFilter, signal?: AbortSignal): Promise<ScriptListItem[]> {
  try {
    const path = buildListPath(filter);
    const { data, error, response } = await apiClient.GET(path as never, { signal } as never);
    if (error) {
      if (response && (response.status === 401 || response.status === 403)) throw error;
      console.warn('[scripts] /api/v1/scripts 后端错误,使用 mock:', error);
      return applyFilter(mockScripts, filter);
    }
    const items = unwrapList(data);
    // 后端可能尚未根据 q 过滤(只支持 enabled),前端再叠一层兜底
    return applyFilter(items, { search: filter.search });
  } catch (err) {
    if (isUnauthorized(err)) throw err;
    console.warn('[scripts] /api/v1/scripts 异常,使用 mock:', err);
    return applyFilter(mockScripts, filter);
  }
}

async function fetchScriptDetail(slug: string, signal?: AbortSignal): Promise<ScriptDetail> {
  const { data, error, response } = await apiClient.GET(
    `/api/v1/scripts/${slug}` as never,
    { signal } as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
  // 容错:后端尚未实现完整详情时,fields_schema 缺省给空数组
  const detail = (data ?? {}) as Partial<ScriptDetail>;
  if (!Array.isArray(detail.fields_schema)) {
    detail.fields_schema = [];
  }
  if (detail.requirements_present === undefined) {
    detail.requirements_present = false;
  }
  return detail as ScriptDetail;
}

async function postScanScripts(): Promise<ScanScriptsResponse> {
  const { data, error, response } = await apiClient.POST(
    '/api/v1/scripts/scan' as never,
    {} as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
  // 兼容后端 stub 阶段返回空对象 / 旧字段
  const raw = (data ?? {}) as Partial<ScanScriptsResponse> & {
    scanned?: number;
    new?: number;
    updated?: number;
  };
  if (Array.isArray(raw.added) || Array.isArray(raw.updated) || Array.isArray(raw.removed)) {
    return {
      added: raw.added ?? [],
      updated: Array.isArray(raw.updated) ? raw.updated : [],
      removed: raw.removed ?? [],
      errors: raw.errors ?? [],
    };
  }
  // 旧 stub 字段 -> 转 added 数组占位
  return {
    added: raw.new ? Array.from({ length: raw.new }, (_, i) => `new-${i}`) : [],
    updated: typeof raw.updated === 'number' && raw.updated > 0
      ? Array.from({ length: raw.updated }, (_, i) => `updated-${i}`)
      : [],
    removed: [],
    errors: [],
  };
}

async function postEnableScript(slug: string): Promise<void> {
  const { error, response } = await apiClient.POST(
    `/api/v1/scripts/${slug}/enable` as never,
    {} as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
}

async function postDisableScript(slug: string): Promise<void> {
  const { error, response } = await apiClient.POST(
    `/api/v1/scripts/${slug}/disable` as never,
    {} as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
}

async function deleteScriptApi(slug: string): Promise<void> {
  const { error, response } = await apiClient.DELETE(
    `/api/v1/scripts/${slug}?confirm=true` as never,
    {} as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
}

// ====================== Query keys ======================

export const scriptsQueryKeys = {
  all: ['scripts'] as const,
  list: (filter: ScriptsFilter = {}) => ['scripts', 'list', filter] as const,
  detail: (slug: string) => ['scripts', 'detail', slug] as const,
};

// ====================== Hooks ======================

/**
 * GET /api/v1/scripts — 列表
 */
export function useScripts(
  filter: ScriptsFilter = {},
): UseQueryResult<ScriptListItem[], Error> {
  return useQuery({
    queryKey: scriptsQueryKeys.list(filter),
    queryFn: ({ signal }) => fetchScripts(filter, signal),
    staleTime: 30_000,
    placeholderData: (prev) => prev ?? applyFilter(mockScripts, filter),
  });
}

/**
 * GET /api/v1/scripts/{slug} — 详情
 */
export function useScript(slug: string | undefined): UseQueryResult<ScriptDetail, Error> {
  return useQuery({
    queryKey: scriptsQueryKeys.detail(slug ?? ''),
    queryFn: ({ signal }) => fetchScriptDetail(slug as string, signal),
    enabled: !!slug,
    staleTime: 30_000,
  });
}

/**
 * POST /api/v1/scripts/scan — 触发全量扫描
 */
export function useScanScripts(): UseMutationResult<ScanScriptsResponse, Error, void> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => postScanScripts(),
    onSuccess: (data) => {
      void qc.invalidateQueries({ queryKey: scriptsQueryKeys.all });
      void qc.invalidateQueries({ queryKey: ['dashboard'] });
      const parts: string[] = [];
      if (data.added.length) parts.push(`新增 ${data.added.length}`);
      if (data.updated.length) parts.push(`更新 ${data.updated.length}`);
      if (data.removed.length) parts.push(`移除 ${data.removed.length}`);
      if (data.errors.length) parts.push(`错误 ${data.errors.length}`);
      const msg = parts.length > 0 ? parts.join(' · ') : '无变化';
      if (data.errors.length > 0) {
        toast.warning(`扫描完成:${msg}`);
      } else {
        toast.success(`扫描完成:${msg}`);
      }
    },
  });
}

/**
 * POST /api/v1/scripts/{slug}/enable
 */
export function useEnableScript(): UseMutationResult<void, Error, string> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (slug: string) => postEnableScript(slug),
    onSuccess: (_data, slug) => {
      void qc.invalidateQueries({ queryKey: scriptsQueryKeys.all });
      void qc.invalidateQueries({ queryKey: scriptsQueryKeys.detail(slug) });
      toast.success('已启用');
    },
  });
}

/**
 * POST /api/v1/scripts/{slug}/disable
 */
export function useDisableScript(): UseMutationResult<void, Error, string> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (slug: string) => postDisableScript(slug),
    onSuccess: (_data, slug) => {
      void qc.invalidateQueries({ queryKey: scriptsQueryKeys.all });
      void qc.invalidateQueries({ queryKey: scriptsQueryKeys.detail(slug) });
      toast.success('已禁用');
    },
  });
}

/**
 * DELETE /api/v1/scripts/{slug}?confirm=true
 *
 * **注意**:仅删 DB 登记,不动磁盘文件(后端 § 2.2 + 禁区约束)。
 */
export function useDeleteScript(): UseMutationResult<void, Error, string> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (slug: string) => deleteScriptApi(slug),
    onSuccess: (_data, slug) => {
      void qc.invalidateQueries({ queryKey: scriptsQueryKeys.all });
      qc.removeQueries({ queryKey: scriptsQueryKeys.detail(slug) });
      toast.success('脚本已从登记中移除(磁盘文件未删)');
    },
  });
}
