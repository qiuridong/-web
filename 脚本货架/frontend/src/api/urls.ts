/**
 * 资源 URL 构造（直接给 <img src> / 下载 / 复制用）。
 * 「我的管家地址」+「导入到管家」逻辑见 src/lib/manager.ts（货架是公共仓库，
 * 每个访问者的管家域名不同，故不在 build 时硬编码管家地址）。
 */

/** 图标接口（相对路径即可，走同源 / vite proxy）。 */
export function iconUrl(slug: string): string {
  return `/api/scripts/${encodeURIComponent(slug)}/icon`;
}

/** bundle.zip 相对路径（用于触发下载）。 */
export function bundlePath(slug: string): string {
  return `/api/scripts/${encodeURIComponent(slug)}/bundle.zip`;
}

/** bundle.zip 的完整绝对 URL（用于复制链接 / 跨站导入，需带 origin）。 */
export function bundleAbsoluteUrl(slug: string): string {
  return `${window.location.origin}${bundlePath(slug)}`;
}
