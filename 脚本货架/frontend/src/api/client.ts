/**
 * 轻量 fetch 封装。
 * - 所有请求带 credentials: 'include'(cookie 鉴权)。
 * - 统一解析后端错误体 {error:{code,message,details}},抛 ApiError。
 * - 提供 get/post/put/patch/del + uploadFile(multipart)。
 */
import type { ApiErrorBody } from './types';

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }

  get isUnauthorized(): boolean {
    return this.status === 401;
  }
}

async function parseError(res: Response): Promise<ApiError> {
  let code = `http_${res.status}`;
  let message = res.statusText || `请求失败 (${res.status})`;
  let details: unknown;
  try {
    const body = (await res.json()) as Partial<ApiErrorBody>;
    if (body && typeof body === 'object' && body.error) {
      code = body.error.code ?? code;
      message = body.error.message ?? message;
      details = body.error.details;
    }
  } catch {
    // body 非 JSON(如 zip / svg / 空体),保留默认信息
  }
  return new ApiError(res.status, code, message, details);
}

interface RequestOptions {
  signal?: AbortSignal;
}

async function request<T>(method: string, path: string, body?: unknown, opts?: RequestOptions): Promise<T> {
  const headers: Record<string, string> = {};
  let payload: BodyInit | undefined;

  if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    payload = JSON.stringify(body);
  }

  const res = await fetch(path, {
    method,
    headers,
    body: payload,
    credentials: 'include',
    signal: opts?.signal,
  });

  if (!res.ok) {
    throw await parseError(res);
  }

  // 204 / 空体
  if (res.status === 204 || res.headers.get('content-length') === '0') {
    return undefined as T;
  }

  const ct = res.headers.get('content-type') ?? '';
  if (ct.includes('application/json')) {
    return (await res.json()) as T;
  }
  return (await res.text()) as unknown as T;
}

export const api = {
  get: <T>(path: string, opts?: RequestOptions) => request<T>('GET', path, undefined, opts),
  post: <T>(path: string, body?: unknown, opts?: RequestOptions) => request<T>('POST', path, body, opts),
  put: <T>(path: string, body?: unknown, opts?: RequestOptions) => request<T>('PUT', path, body, opts),
  patch: <T>(path: string, body?: unknown, opts?: RequestOptions) =>
    request<T>('PATCH', path, body, opts),
  del: <T>(path: string, opts?: RequestOptions) => request<T>('DELETE', path, undefined, opts),

  /** multipart 上传(字段名 file)。 */
  async uploadFile<T>(path: string, file: File, fieldName = 'file'): Promise<T> {
    const form = new FormData();
    form.append(fieldName, file);
    const res = await fetch(path, {
      method: 'POST',
      body: form,
      credentials: 'include',
    });
    if (!res.ok) {
      throw await parseError(res);
    }
    return (await res.json()) as T;
  },
};
