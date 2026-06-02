/**
 * 「我的管家地址」—— 货架是公共仓库，访问者各自的签到管家域名不同。
 * 用浏览器本地 localStorage 记住访问者自己的管家地址，「导入到管家」跳转到它。
 * 你自己设一次 https://jb.aijiaxia.cc，别人设他们自己的管家域名，互不影响。
 */
import { useSyncExternalStore } from 'react';

import { bundleAbsoluteUrl } from '@/api/urls';

const KEY = 'hub.manager_url';
const listeners = new Set<() => void>();

export function getManagerUrl(): string {
  try {
    return localStorage.getItem(KEY)?.trim() || '';
  } catch {
    return '';
  }
}

export function setManagerUrl(value: string): void {
  try {
    const v = value.trim().replace(/\/+$/, '');
    if (v) localStorage.setItem(KEY, v);
    else localStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
  listeners.forEach((l) => l());
}

function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  const onStorage = (e: StorageEvent) => {
    if (e.key === KEY) cb();
  };
  window.addEventListener('storage', onStorage);
  return () => {
    listeners.delete(cb);
    window.removeEventListener('storage', onStorage);
  };
}

/** 响应式读取「我的管家地址」（跨 tab + 同 tab 多组件同步）。 */
export function useManagerUrl(): string {
  return useSyncExternalStore(subscribe, getManagerUrl, () => '');
}

/** 「导入到管家」跳转 URL：<管家>/scripts?import=<货架 bundle 绝对地址>。 */
export function managerImportUrl(slug: string, managerUrl: string): string {
  const base = managerUrl.trim().replace(/\/+$/, '');
  return `${base}/scripts?import=${encodeURIComponent(bundleAbsoluteUrl(slug))}`;
}
