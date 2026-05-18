/**
 * 脚本文件 CRUD hooks(MVP-5)
 *
 * 设计契约:`进度/设计/Web脚本编辑器.md` § 2.3(`/scripts/{slug}/files/*`)。
 *
 * Query keys:
 *   ['script-files', slug]            — 文件列表
 *   ['script-file', slug, path]       — 单文件内容
 *
 * 删除整脚本(`delete_files=true`)走 scripts.ts 既有 useDeleteScript;
 * 本文件 useScriptFullDelete 是带 delete_files=true 版本的 wrapper(MVP-5 才有"是否删磁盘"选项)。
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

export interface ScriptFileItem {
  path: string;
  size: number;
  /** ISO 时间戳 */
  mtime: string;
  editable: boolean;
}

export interface ScriptFileListResponse {
  files: ScriptFileItem[];
}

export interface DryRunResult {
  passed: boolean;
  exit_code: number;
  duration_ms: number;
  stdout_excerpt: string;
  stderr_excerpt: string;
  timed_out: boolean;
}

export interface FileWriteResponse {
  saved: boolean;
  path: string;
  backup_path: string | null;
  dry_run: DryRunResult | null;
}

export interface SaveFilePayload {
  slug: string;
  path: string;
  content: string;
  /** 跳过 dry-run(危险,默认 false) */
  skip_dry_run?: boolean;
}

// ====================== Query keys ======================

export const scriptFilesQueryKeys = {
  list: (slug: string) => ['script-files', slug] as const,
  file: (slug: string, path: string) => ['script-file', slug, path] as const,
};

// ====================== Fetchers ======================

async function fetchScriptFiles(
  slug: string,
  signal?: AbortSignal,
): Promise<ScriptFileItem[]> {
  const { data, error, response } = await apiClient.GET(
    `/api/v1/scripts/${slug}/files` as never,
    { signal } as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
  const raw = (data ?? {}) as Partial<ScriptFileListResponse>;
  return Array.isArray(raw.files) ? raw.files : [];
}

/**
 * 读单文件,后端可能返回 text/plain 或 JSON 包装({path,size,mtime,content})。
 * 这里统一只关心**字符串内容**。
 */
async function fetchScriptFile(
  slug: string,
  path: string,
  signal?: AbortSignal,
): Promise<string> {
  // 走原生 fetch 而非 openapi-fetch:openapi-fetch 默认 JSON parse,
  // 但后端 GET 文件端点更易返 text/plain;原生 fetch 直接拿 text() 最稳。
  const encPath = path.split('/').map(encodeURIComponent).join('/');
  const resp = await fetch(`/api/v1/scripts/${slug}/files/${encPath}`, {
    credentials: 'include',
    headers: { Accept: 'text/plain, application/json' },
    signal,
  });
  if (!resp.ok) {
    let detail: unknown = null;
    try {
      detail = await resp.json();
    } catch {
      detail = await resp.text();
    }
    const err: Error & { status?: number; detail?: unknown } = new Error(
      typeof detail === 'string'
        ? detail
        : (detail && typeof detail === 'object' && 'detail' in detail
            ? String((detail as { detail: unknown }).detail)
            : `HTTP ${resp.status}`),
    );
    err.status = resp.status;
    err.detail = detail;
    throw err;
  }
  const ct = resp.headers.get('content-type') || '';
  if (ct.includes('application/json')) {
    const j = (await resp.json()) as { content?: string };
    return j.content ?? '';
  }
  return resp.text();
}

async function saveScriptFile(payload: SaveFilePayload): Promise<FileWriteResponse> {
  const encPath = payload.path.split('/').map(encodeURIComponent).join('/');
  const qs = new URLSearchParams();
  if (payload.skip_dry_run) qs.set('skip_dry_run', 'true');
  const url = `/api/v1/scripts/${payload.slug}/files/${encPath}${
    qs.toString() ? `?${qs.toString()}` : ''
  }`;
  const resp = await fetch(url, {
    method: 'PUT',
    credentials: 'include',
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
      'X-Requested-With': 'fetch',
      Accept: 'application/json',
    },
    body: payload.content,
  });
  if (!resp.ok) {
    let detail: unknown = null;
    try {
      detail = await resp.json();
    } catch {
      detail = await resp.text();
    }
    // 422 + dry-run 失败:把整个 detail 抛出去,UI 渲染 stderr 摘要
    const msg =
      typeof detail === 'object' && detail && 'detail' in detail
        ? typeof (detail as { detail: unknown }).detail === 'string'
          ? String((detail as { detail: string }).detail)
          : '保存失败'
        : typeof detail === 'string'
          ? detail
          : `HTTP ${resp.status}`;
    const err: Error & { status?: number; detail?: unknown } = new Error(msg);
    err.status = resp.status;
    err.detail = detail;
    throw err;
  }
  return (await resp.json()) as FileWriteResponse;
}

async function deleteScriptFull(slug: string): Promise<void> {
  // 带 delete_files=true,删 DB + 磁盘文件(MVP-5 新增)
  const { error, response } = await apiClient.DELETE(
    `/api/v1/scripts/${slug}?confirm=true&delete_files=true` as never,
    {} as never,
  );
  if (error) {
    throw Object.assign(new Error(formatError(error)), {
      status: response?.status,
      detail: error,
    });
  }
}

// ====================== Hooks ======================

/**
 * GET /api/v1/scripts/{slug}/files — 文件列表
 */
export function useScriptFiles(
  slug: string | undefined,
): UseQueryResult<ScriptFileItem[], Error> {
  return useQuery({
    queryKey: scriptFilesQueryKeys.list(slug ?? ''),
    queryFn: ({ signal }) => fetchScriptFiles(slug as string, signal),
    enabled: !!slug,
    staleTime: 30_000,
  });
}

/**
 * GET /api/v1/scripts/{slug}/files/{path} — 单文件内容
 * 只在 enabled === true 时启动,适合在 Dialog 打开后 lazy fetch。
 */
export function useScriptFile(
  slug: string | undefined,
  path: string | undefined,
  enabled = true,
): UseQueryResult<string, Error> {
  return useQuery({
    queryKey: scriptFilesQueryKeys.file(slug ?? '', path ?? ''),
    queryFn: ({ signal }) => fetchScriptFile(slug as string, path as string, signal),
    enabled: enabled && !!slug && !!path,
    staleTime: 0, // 文件改完要立刻拿到最新版本,不缓存
    gcTime: 0,
    retry: false, // 文本读失败不要重试,UI 显示错误就好
  });
}

/**
 * PUT /api/v1/scripts/{slug}/files/{path} — 保存单文件 + 自动 dry-run
 */
export function useScriptFileSave(): UseMutationResult<
  FileWriteResponse,
  Error,
  SaveFilePayload
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: saveScriptFile,
    onSuccess: (data, vars) => {
      // 文件改了 → 失效列表(mtime/size 变了)
      void qc.invalidateQueries({ queryKey: scriptFilesQueryKeys.list(vars.slug) });
      // 单文件缓存也清(下次打开拿新内容,虽然 staleTime=0 也会拿)
      void qc.invalidateQueries({ queryKey: scriptFilesQueryKeys.file(vars.slug, vars.path) });
      // manifest.yaml 改了的话,脚本元数据也变,刷脚本详情
      if (vars.path === 'manifest.yaml') {
        void qc.invalidateQueries({ queryKey: ['scripts'] });
      }
      // 成功 toast 留给 Dialog 自己决定(避免静默成功)
      if (data.saved) {
        toast.success(
          data.backup_path
            ? '已保存(旧版备份到 .backups/)'
            : '已保存',
        );
      }
    },
    // onError 走全局,不重复 toast(query-client.ts 已统一);
    // 但 UploadDialog / FileEditDialog 自己读 error.detail 渲染细节
  });
}

/**
 * DELETE /api/v1/scripts/{slug}?confirm=true&delete_files=true
 *
 * 与 scripts.ts useDeleteScript 的区别:**会**真的删磁盘文件夹。
 * UI 必须二次确认 + 提示不可逆。
 */
export function useScriptFullDelete(): UseMutationResult<void, Error, string> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deleteScriptFull,
    onSuccess: (_data, slug) => {
      void qc.invalidateQueries({ queryKey: ['scripts'] });
      qc.removeQueries({ queryKey: ['scripts', 'detail', slug] });
      qc.removeQueries({ queryKey: scriptFilesQueryKeys.list(slug) });
      toast.success('脚本及其磁盘文件已删除');
    },
  });
}
