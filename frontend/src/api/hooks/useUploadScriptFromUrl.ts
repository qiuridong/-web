/**
 * 从 URL 下载脚本 zip 并入库的 hook(脚本货架对接 · M3)
 *
 * 对接后端 ``POST /api/v1/scripts/upload-from-url?zip_url=...&force=&dry_run=&sync_to_nodes=``。
 * 后端服务端下载 zip → 复用与 ``/upload`` 完全相同的校验/落盘/入库流程。
 *
 * 两条使用路径:
 *   1. 脚本市场页「安装」:zip_url = ${VITE_HUB_URL}/api/scripts/{slug}/bundle.zip
 *   2. 货架「导入到管家」跳 /scripts?import=<bundle url> → UploadScriptDialog 的「从 URL 导入」分支
 *
 * 与 useScriptUpload(XHR 上传本地文件)互补:这里是服务端拉远端 zip,不走文件,
 * 故用 apiClient.POST 即可(无需上传进度条)。复用 useScriptUpload 的响应/错误类型保持一致。
 */
import {
  useMutation,
  useQueryClient,
  type UseMutationResult,
} from '@tanstack/react-query';

import { apiClient } from '@/api/client';
import {
  UploadError,
  type UploadResponse,
} from '@/api/hooks/useScriptUpload';

export interface UploadFromUrlVars {
  /** 远端标准脚本 zip 的 URL(http/https) */
  zip_url: string;
  /** slug 已存在时是否覆盖,默认 false */
  force?: boolean;
  /** 是否入库前自动 dry-run,默认 true */
  dry_run?: boolean;
  /**
   * 入库后立即推送到这些节点(仅 enabled + 非 local 的会被实际加入推送队列)。
   * 与本地上传的 sync_to_nodes 语义一致。
   */
  sync_to_nodes?: number[];
}

/**
 * 从后端错误包络 ``{ error: { code, message, details } }`` 里抽人类可读消息。
 *
 * 也兼容 FastAPI 原生 ``{ detail: ... }`` / ``{ message: ... }`` 形态。
 */
function extractErrorMessage(payload: unknown, status: number): string {
  if (!payload || typeof payload !== 'object') return `HTTP ${status}`;
  const p = payload as Record<string, unknown>;
  // 本项目统一错误包络
  if (p.error && typeof p.error === 'object') {
    const e = p.error as { message?: string };
    if (typeof e.message === 'string' && e.message) return e.message;
  }
  if (typeof p.detail === 'string') return p.detail;
  if (Array.isArray(p.detail)) {
    const first = p.detail[0] as { msg?: string; loc?: unknown[] } | undefined;
    if (first?.msg) {
      const loc = Array.isArray(first.loc) ? first.loc.join('.') : '';
      return loc ? `${loc}: ${first.msg}` : first.msg;
    }
  }
  if (typeof p.message === 'string') return p.message;
  return `HTTP ${status}`;
}

async function uploadFromUrl(vars: UploadFromUrlVars): Promise<UploadResponse> {
  const qs = new URLSearchParams();
  qs.set('zip_url', vars.zip_url);
  if (vars.force) qs.set('force', 'true');
  qs.set('dry_run', String(vars.dry_run ?? true));
  if (vars.sync_to_nodes && vars.sync_to_nodes.length > 0) {
    qs.set('sync_to_nodes', vars.sync_to_nodes.join(','));
  }

  const { data, error, response } = await apiClient.POST(
    `/api/v1/scripts/upload-from-url?${qs.toString()}` as never,
    {} as never,
  );

  if (error) {
    const status = response?.status ?? 0;
    throw new UploadError(extractErrorMessage(error, status), status, error);
  }
  return data as unknown as UploadResponse;
}

/**
 * useUploadScriptFromUrl — 从 URL 安装/导入脚本。
 *
 * 成功后自动 invalidate ['scripts'] 让列表/详情刷新。
 * 错误统一抛 UploadError(.message 已解包 + .detail 保留完整 body 供 UI 渲染细节)。
 * 不在此处 toast —— 由调用方(市场页 / Dialog)决定如何呈现成功/失败。
 */
export function useUploadScriptFromUrl(): UseMutationResult<
  UploadResponse,
  UploadError | Error,
  UploadFromUrlVars
> {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: uploadFromUrl,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['scripts'] });
      void qc.invalidateQueries({ queryKey: ['dashboard'] });
    },
  });
}
