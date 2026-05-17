/**
 * 入口:挂 Provider 链路 + Router + 全局 Toaster
 *
 * 设计契约:`进度/设计/前端UI设计.md` § 5(状态管理)、§ 6(API 封装)。
 * Provider 顺序(外 → 内):
 *   StrictMode → QueryClientProvider → ThemeProvider → RouterProvider
 *   Toaster 挂在 body 直接子节点(由 sonner 自己 portal)
 */
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { RouterProvider } from 'react-router';
import { Toaster } from 'sonner';

// 字体:self-hosted variable fonts(不走 Google Fonts CDN)
import '@fontsource-variable/inter';
import '@fontsource-variable/jetbrains-mono';

// 全局样式 + Tailwind v4 + @theme + CSS vars
import './app/index.css';

import { router } from './app/router';
import { queryClient } from './api/query-client';
import { ThemeProvider } from './components/theme/ThemeProvider';

const rootEl = document.getElementById('root');
if (!rootEl) {
  throw new Error('找不到 #root 挂载点;检查 index.html');
}

createRoot(rootEl).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <RouterProvider router={router} />
        <Toaster
          position="top-right"
          richColors
          closeButton
          toastOptions={{
            classNames: {
              toast:
                'group toast group-[.toaster]:bg-popover group-[.toaster]:text-popover-foreground group-[.toaster]:border group-[.toaster]:shadow-lg',
              description: 'group-[.toast]:text-muted-foreground',
              actionButton:
                'group-[.toast]:bg-primary group-[.toast]:text-primary-foreground',
              cancelButton:
                'group-[.toast]:bg-muted group-[.toast]:text-muted-foreground',
            },
          }}
        />
      </ThemeProvider>
      {import.meta.env.DEV && <ReactQueryDevtools initialIsOpen={false} />}
    </QueryClientProvider>
  </StrictMode>,
);
