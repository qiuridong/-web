import path from 'node:path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// 脚本货架前端 — 独立工程，不复用签到管家的 node_modules / 代码。
// dev 时把 /api 与 /health 代理到货架后端 FastAPI（127.0.0.1:8000）。
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    strictPort: false,
    host: true,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/health': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    target: 'es2022',
    reportCompressedSize: false,
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      output: {
        // 所有第三方归一个 vendor chunk —— 与 app 代码分离利于缓存，
        // 且避免按包细分时的跨 chunk 循环依赖（如 react-router ↔ @remix-run/router）。
        manualChunks(id: string) {
          if (id.includes('node_modules')) return 'vendor';
          return undefined;
        },
      },
    },
  },
  preview: {
    port: 5174,
  },
});
