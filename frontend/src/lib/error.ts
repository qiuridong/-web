/**
 * 错误工具
 *
 * 设计契约:openapi-fetch middleware 在 401 时 dispatchEvent('app:unauthorized'),
 *          >= 500 时 sonner toast。本文件提供识别与展示工具。
 */

/**
 * openapi-fetch 错误对象的最小形状(从 client error 字段拿)。
 * 也兼容 fetch Response、普通 Error 对象。
 */
export interface ApiErrorLike {
  status?: number;
  statusCode?: number;
  message?: string;
  detail?: string | { message?: string } | unknown;
  response?: { status?: number };
}

function getStatus(err: unknown): number | undefined {
  if (!err || typeof err !== 'object') return undefined;
  const e = err as ApiErrorLike;
  if (typeof e.status === 'number') return e.status;
  if (typeof e.statusCode === 'number') return e.statusCode;
  if (e.response && typeof e.response.status === 'number') return e.response.status;
  return undefined;
}

/**
 * 401 / 403 视为未授权(对于本应用,403 通常也跳登录)。
 */
export function isUnauthorized(err: unknown): boolean {
  const s = getStatus(err);
  return s === 401 || s === 403;
}

/**
 * 5xx 视为服务端错误。
 */
export function isServerError(err: unknown): boolean {
  const s = getStatus(err);
  return typeof s === 'number' && s >= 500 && s < 600;
}

/**
 * 提取人类可读错误信息。优先级:
 *   detail.message > detail(string) > message > 状态码描述 > '未知错误'
 */
export function formatError(err: unknown): string {
  if (!err) return '未知错误';
  if (typeof err === 'string') return err;
  if (err instanceof Error) return err.message || err.name || '未知错误';
  if (typeof err === 'object') {
    const e = err as ApiErrorLike;
    if (e.detail) {
      if (typeof e.detail === 'string') return e.detail;
      if (typeof e.detail === 'object' && 'message' in e.detail && typeof e.detail.message === 'string') {
        return e.detail.message;
      }
    }
    if (typeof e.message === 'string') return e.message;
    const s = getStatus(err);
    if (typeof s === 'number') return `请求失败(HTTP ${s})`;
  }
  return '未知错误';
}
