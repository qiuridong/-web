/**
 * 脚本上传 hook(MVP-5)
 *
 * 设计契约:`进度/设计/Web脚本编辑器.md` § 2.2(`POST /api/v1/scripts/upload`)。
 *
 * 为什么用 XHR 而非 fetch:
 *   - 需要 `upload.onprogress` 拿到上传进度(大 zip 用户要看进度条)
 *   - fetch + ReadableStream upload 还在 origin-trial 阶段,兼容性差
 *
 * 暴露:
 *   - `useScriptUpload()` → { upload, progress, isUploading, error, reset }
 *   - `upload(file, opts)` 返回 Promise<UploadResponse>
 *
 * 错误处理:
 *   - 网络层失败 → throw Error(中文 message)
 *   - HTTP 非 2xx → throw Error,带 status + detail(包含后端 422 字段错误 raw)
 *   - 不在这里 toast(由调用方决定;UploadScriptDialog 在自己面板里渲染错误,不再 toast)
 */
import { useCallback, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';

export interface UploadOptions {
  /** 留空则后端用 manifest.yaml 里的 slug */
  slug?: string;
  /** slug 已存在时是否覆盖,默认 false */
  force?: boolean;
  /** 是否上传前自动 dry-run,默认 true */
  dry_run?: boolean;
}

export interface DryRunResult {
  passed: boolean;
  exit_code: number;
  duration_ms: number;
  stdout_excerpt: string;
  stderr_excerpt: string;
  timed_out: boolean;
}

export interface UploadResponse {
  slug: string;
  saved_path: string;
  files_written: string[];
  total_bytes: number;
  dry_run: DryRunResult | null;
  script_record: Record<string, unknown> | null;
}

export class UploadError extends Error {
  status: number;
  detail: unknown;
  constructor(message: string, status: number, detail: unknown) {
    super(message);
    this.name = 'UploadError';
    this.status = status;
    this.detail = detail;
  }
}

interface UseScriptUploadReturn {
  upload: (files: File | File[] | FileList, opts?: UploadOptions) => Promise<UploadResponse>;
  /** 0-100,未上传时 0 */
  progress: number;
  isUploading: boolean;
  error: UploadError | Error | null;
  reset: () => void;
  /** 调用方主动取消(用户点"取消"按钮) */
  abort: () => void;
}

/**
 * 从后端 FastAPI 422 / 400 错误响应里抽出人类可读消息。
 *
 * 后端可能形态:
 *   { "detail": "manifest.yaml 缺失" }
 *   { "detail": [{loc: [...], msg: "..."}] }  ← pydantic 校验错误
 *   { "message": "..." }
 */
function extractErrorMessage(payload: unknown, status: number): string {
  if (!payload || typeof payload !== 'object') {
    return `HTTP ${status}`;
  }
  const p = payload as Record<string, unknown>;
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

export function useScriptUpload(): UseScriptUploadReturn {
  const [progress, setProgress] = useState(0);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<UploadError | Error | null>(null);
  const xhrRef = useRef<XMLHttpRequest | null>(null);
  const qc = useQueryClient();

  const reset = useCallback(() => {
    setProgress(0);
    setIsUploading(false);
    setError(null);
    xhrRef.current = null;
  }, []);

  const abort = useCallback(() => {
    if (xhrRef.current) {
      xhrRef.current.abort();
      xhrRef.current = null;
    }
    setIsUploading(false);
  }, []);

  const upload = useCallback(
    (
      files: File | File[] | FileList,
      opts: UploadOptions = {},
    ): Promise<UploadResponse> => {
      // 归一化为 File[]
      const fileArr: File[] = Array.isArray(files)
        ? files
        : files instanceof FileList
          ? Array.from(files)
          : [files];

      // 构造 query string
      const qs = new URLSearchParams();
      if (opts.slug) qs.set('slug', opts.slug);
      if (opts.force) qs.set('force', 'true');
      // 默认开 dry_run
      qs.set('dry_run', String(opts.dry_run ?? true));
      const url = `/api/v1/scripts/upload?${qs.toString()}`;

      return new Promise<UploadResponse>((resolve, reject) => {
        setProgress(0);
        setIsUploading(true);
        setError(null);

        const xhr = new XMLHttpRequest();
        xhrRef.current = xhr;
        xhr.open('POST', url, true);
        xhr.withCredentials = true; // 带 cookie
        xhr.setRequestHeader('X-Requested-With', 'fetch');
        xhr.setRequestHeader('Accept', 'application/json');

        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) {
            setProgress(Math.min(99, Math.round((e.loaded / e.total) * 100)));
          }
        };

        xhr.onload = () => {
          xhrRef.current = null;
          const status = xhr.status;
          let payload: unknown = null;
          try {
            payload = xhr.responseText ? JSON.parse(xhr.responseText) : null;
          } catch {
            payload = xhr.responseText;
          }
          if (status >= 200 && status < 300) {
            setProgress(100);
            setIsUploading(false);
            // 上传成功后让 scripts 列表 / 详情都刷新
            void qc.invalidateQueries({ queryKey: ['scripts'] });
            resolve(payload as UploadResponse);
          } else {
            const msg = extractErrorMessage(payload, status);
            const err = new UploadError(msg, status, payload);
            setError(err);
            setIsUploading(false);
            reject(err);
          }
        };

        xhr.onerror = () => {
          xhrRef.current = null;
          const err = new Error('网络错误 / 请检查后端是否在运行');
          setError(err);
          setIsUploading(false);
          reject(err);
        };

        xhr.onabort = () => {
          xhrRef.current = null;
          setIsUploading(false);
          // 主动 abort 不算 error,silently reject 让调用方决定
          reject(new DOMException('上传已取消', 'AbortError'));
        };

        // 决定 content-type:
        //   - 单文件且是 .zip → application/zip
        //   - 其它(多文件 / 文件夹)→ multipart/form-data
        if (fileArr.length === 1 && /\.zip$/i.test(fileArr[0]!.name)) {
          xhr.setRequestHeader('Content-Type', 'application/zip');
          xhr.send(fileArr[0]);
        } else {
          const fd = new FormData();
          fileArr.forEach((f) => {
            // 用 webkitRelativePath(若拖文件夹则带相对路径,后端要保留目录结构)
            const relPath =
              (f as File & { webkitRelativePath?: string }).webkitRelativePath || f.name;
            fd.append('files', f, relPath);
          });
          // 注意:这里 **不要** 手动设 Content-Type,让浏览器自动加 boundary
          xhr.send(fd);
        }
      });
    },
    [qc],
  );

  return { upload, progress, isUploading, error, reset, abort };
}
