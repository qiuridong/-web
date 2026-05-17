/**
 * <ThemeProvider> — next-themes 包装。
 *
 * 设计契约:`进度/设计/前端UI设计.md` § 1.2.2(深色模式作为一等公民)、§ 5。
 *
 * 关键约定:
 *   - attribute="class"  → 切换 <html class="dark">
 *   - defaultTheme="system" + enableSystem → 跟随 prefers-color-scheme
 *
 * 注意(2026-05-16):**已移除 `disableTransitionOnChange`**
 *   原因:它会临时往 `<head>` 注入 `<style>*{transition: none !important}</style>` 再移除,
 *   这种 head DOM mutation 与 Dark Reader / Grammarly / Microsoft Editor 等扩展冲突,
 *   导致 React reconciler 找不到原节点 → 整页 `insertBefore Failed` 崩。
 *   牺牲是切主题时有 ~200ms transition 跟着变,体验上完全可接受。
 *
 * index.html 顶部已经有 inline script 提前给 html 加 .dark,防 FOUC。
 */
import type { ReactNode } from 'react';
import { ThemeProvider as NextThemesProvider, type ThemeProviderProps } from 'next-themes';

type Props = Omit<ThemeProviderProps, 'children'> & { children: ReactNode };

export function ThemeProvider({ children, ...props }: Props) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      storageKey="theme"
      {...props}
    >
      {children}
    </NextThemesProvider>
  );
}
