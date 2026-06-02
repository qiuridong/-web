/**
 * 资源 URL 构造(直接给 <img src> / 下载 / 复制 / 跨站导入用)。
 */

/** 签到管家地址,用于「导入到管家」跳转。 */
export const MANAGER_URL: string = import.meta.env.VITE_MANAGER_URL ?? 'https://jb.aijiaxia.cc';

/** 图标接口(相对路径即可,走 vite proxy / 同源)。 */
export function iconUrl(slug: string): string {
  return `/api/scripts/${encodeURIComponent(slug)}/icon`;
}

/** bundle.zip 相对路径(用于触发下载)。 */
export function bundlePath(slug: string): string {
  return `/api/scripts/${encodeURIComponent(slug)}/bundle.zip`;
}

/** bundle.zip 的完整绝对 URL(用于复制链接 / 跨站导入,需带 origin)。 */
export function bundleAbsoluteUrl(slug: string): string {
  return `${window.location.origin}${bundlePath(slug)}`;
}

/** 「导入到管家」跳转 URL:管家 /scripts?import=<货架 bundle 绝对地址>。 */
export function managerImportUrl(slug: string): string {
  const bundle = bundleAbsoluteUrl(slug);
  return `${MANAGER_URL}/scripts?import=${encodeURIComponent(bundle)}`;
}
