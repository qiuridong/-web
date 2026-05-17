/**
 * openapi-fetch HTTP 客户端 + middleware
 *
 * 设计契约:`进度/设计/前端UI设计.md` § 6(API 封装层)。
 *
 * Middleware 责任:
 *   - csrfMiddleware:非 GET/HEAD 请求加 `X-Requested-With: fetch` 头
 *   - errorMiddleware:401/403 → dispatchEvent('app:unauthorized')(由路由 listener 跳登录)
 *                     >= 500 → 全局 sonner toast
 *
 * TODO(此文件):后端起来后跑 `pnpm gen:api` 生成 src/api/schema.d.ts,
 *               然后把下面的 createClient<any> 改回 createClient<paths>,
 *               并把 import 改为:
 *                 import type { paths } from './schema';
 *               同时把每个 query/mutation 的 client.GET<'/api/v1/...'>(...) 用上类型推导。
 */
import createClient, { type Middleware } from 'openapi-fetch';
import { toast } from 'sonner';

import { formatError, isServerError, isUnauthorized } from '@/lib/error';

// TODO: 后端生成 schema.d.ts 后,把 any 换成 paths
// import type { paths } from './schema';

const baseUrl: string = import.meta.env.VITE_API_BASE ?? '';

/**
 * CSRF / 身份标记 middleware
 *
 * - 添加 X-Requested-With:用于后端区分 fetch 调用与表单提交,简单 CSRF 防护
 * - 总是带 cookie(credentials: 'include' 在 createClient 中已设置)
 */
const csrfMiddleware: Middleware = {
  async onRequest({ request }) {
    const method = request.method.toUpperCase();
    if (method !== 'GET' && method !== 'HEAD') {
      request.headers.set('X-Requested-With', 'fetch');
    }
    return request;
  },
};

/**
 * 全局错误 middleware
 *
 * 401/403 → 派发 'app:unauthorized' 自定义事件,由顶层路由 listener 决定跳转到 /login
 *           (避免在 lib 层直接拿 router 做副作用,保持解耦)
 * >= 500  → toast 提示。
 */
const errorMiddleware: Middleware = {
  async onResponse({ response }) {
    if (response.ok) return response;
    if (response.status === 401 || response.status === 403) {
      window.dispatchEvent(
        new CustomEvent('app:unauthorized', { detail: { status: response.status } }),
      );
      // 不 toast 401(用户体验:静默跳登录),只在 5xx 提示
    } else if (response.status >= 500) {
      try {
        // 尝试读取后端 detail,避免 body lock 影响后续 .json()
        const cloned = response.clone();
        let detail: unknown;
        try {
          detail = await cloned.json();
        } catch {
          detail = await cloned.text();
        }
        const msg = formatError({ status: response.status, detail });
        toast.error(msg);
      } catch {
        toast.error(`请求失败(HTTP ${response.status})`);
      }
    }
    return response;
  },
  async onError({ error }): Promise<void> {
    // 网络层错误(断网、CORS、超时等);只 sniff,不替换原始 error
    if (isUnauthorized(error)) {
      window.dispatchEvent(new CustomEvent('app:unauthorized'));
    } else if (isServerError(error)) {
      toast.error(formatError(error));
    } else {
      // 其他网络错误也提示一次,避免静默
      const msg = formatError(error);
      if (msg && msg !== '未知错误') {
        toast.error(msg);
      }
    }
    // return undefined → openapi-fetch 让原错误继续抛
  },
};

// TODO: schema.d.ts 生成后改为 createClient<paths>
export const apiClient = createClient<any>({
  baseUrl,
  credentials: 'include',
  headers: {
    Accept: 'application/json',
  },
});

apiClient.use(csrfMiddleware);
apiClient.use(errorMiddleware);

export default apiClient;
