/// <reference types="vite/client" />

interface ImportMetaEnv {
  /**
   * 后端 API 基地址。
   *
   * - 本地开发:留空,走 vite.config.ts 中的 proxy 转发到 http://localhost:8000
   * - 直连开发:VITE_API_BASE=http://localhost:8000
   * - 生产:留空,与前端同源由 Caddy 反代
   */
  readonly VITE_API_BASE: string;

  /**
   * 脚本货架(Script Hub)基地址,供「脚本市场」页拉列表 + 拼 bundle.zip 安装 URL。
   *
   * - 默认(未设):https://hub.aijiaxia.cc(生产货架)
   * - 本地联调:VITE_HUB_URL=http://localhost:8100(货架后端直连;需货架 CORS 放行管家 origin)
   */
  readonly VITE_HUB_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

/**
 * 自定义事件类型扩展
 *
 * 'app:unauthorized' — openapi-fetch errorMiddleware 在 401/403 时派发,
 *                      由顶层 router listener 监听后触发跳转 /login。
 */
declare global {
  interface WindowEventMap {
    'app:unauthorized': CustomEvent<{ status?: number }>;
  }
}

export {};
