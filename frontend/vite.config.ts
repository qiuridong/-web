import path from 'node:path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// https://vitejs.dev/config/
// 注意:Tailwind v4 通过 PostCSS 接管(见 postcss.config.mjs),不需要 vite 插件。
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
      // 普通 REST 请求 → FastAPI
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        // SSE 流不要被代理缓冲
        // 见 vite/proxy(http-proxy):流式响应默认即透传,无需特殊处理。
        // 但显式禁用 timeout / proxyTimeout 避免长连接 SSE 被中断。
        timeout: 0,
        proxyTimeout: 0,
        configure: (proxy) => {
          // 透传 SSE:不缓冲、不压缩
          proxy.on('proxyRes', (proxyRes) => {
            // 让浏览器按 stream 处理 text/event-stream
            const ct = proxyRes.headers['content-type'];
            if (typeof ct === 'string' && ct.includes('text/event-stream')) {
              proxyRes.headers['x-accel-buffering'] = 'no';
            }
          });
        },
      },
      // 后端 OpenAPI / health(供本地脚本与开发期访问)
      '/openapi.json': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/docs': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
    target: 'es2022',
    cssCodeSplit: true,
    reportCompressedSize: false,
    // 主 bundle 过大警告阈值(MVP-3B 拆包前 ~2095 KB;目标 ≤ 600 KB)
    chunkSizeWarningLimit: 700,
    rollupOptions: {
      output: {
        /**
         * MVP-3B manualChunks — 把大型第三方拆分到独立 vendor chunk,
         * 并行加载、长缓存,避免主包随业务代码一起膨胀。
         *
         * 顺序很重要:第一个命中即采用,所以特定 ecosystem 写前面,
         * 其余三方包兜底 vendor-misc。
         */
        manualChunks(id: string) {
          if (!id.includes('node_modules')) return undefined;
          // 归一化 path,Windows 反斜杠也能命中;同时去掉 .pnpm/xxx/node_modules 前缀干扰
          const p = id.replace(/\\/g, '/');
          // pnpm 实际包路径:.../node_modules/.pnpm/<name>@<ver>_<hash>/node_modules/<name>/...
          // 这里我们关心末尾那段 <name>/...,所以单独提取
          const inPkg = (name: string): boolean =>
            p.includes(`/node_modules/${name}/`);

          if (
            inPkg('react') ||
            inPkg('react-dom') ||
            inPkg('react-router') ||
            inPkg('scheduler')
          ) {
            return 'vendor-react';
          }
          if (
            inPkg('recharts') ||
            inPkg('recharts-scale') ||
            inPkg('victory-vendor') ||
            inPkg('internmap') ||
            inPkg('react-smooth') ||
            inPkg('decimal.js-light') ||
            inPkg('fast-equals') ||
            inPkg('react-is') ||
            /\/node_modules\/d3-[^/]+\//.test(p)
          ) {
            return 'vendor-charts';
          }
          if (
            p.includes('/node_modules/@xterm/') ||
            inPkg('xterm') ||
            p.includes('/node_modules/@microsoft/fetch-event-source/')
          ) {
            return 'vendor-xterm';
          }
          if (
            inPkg('react-markdown') ||
            inPkg('unified') ||
            inPkg('react-syntax-highlighter') ||
            inPkg('refractor') ||
            /\/node_modules\/remark-[^/]+\//.test(p) ||
            /\/node_modules\/mdast-[^/]+\//.test(p) ||
            /\/node_modules\/micromark[^/]*\//.test(p) ||
            /\/node_modules\/hast-[^/]+\//.test(p) ||
            /\/node_modules\/unist-[^/]+\//.test(p) ||
            inPkg('property-information') ||
            inPkg('space-separated-tokens') ||
            inPkg('comma-separated-tokens') ||
            inPkg('html-url-attributes') ||
            inPkg('decode-named-character-reference') ||
            inPkg('character-entities') ||
            inPkg('character-entities-html4') ||
            inPkg('character-reference-invalid') ||
            inPkg('estree-util-is-identifier-name') ||
            inPkg('inline-style-parser') ||
            inPkg('style-to-js') ||
            inPkg('style-to-object') ||
            inPkg('markdown-table') ||
            inPkg('longest-streak') ||
            inPkg('trim-lines') ||
            inPkg('ccount') ||
            inPkg('devlop') ||
            inPkg('vfile') ||
            inPkg('vfile-message') ||
            p.includes('/node_modules/@ungap/structured-clone/') ||
            inPkg('bail') ||
            inPkg('trough') ||
            inPkg('extend') ||
            inPkg('is-plain-obj') ||
            inPkg('zwitch')
          ) {
            return 'vendor-markdown';
          }
          if (p.includes('/node_modules/@tanstack/')) {
            return 'vendor-tanstack';
          }
          if (
            p.includes('/node_modules/@radix-ui/') ||
            p.includes('/node_modules/@floating-ui/') ||
            inPkg('aria-hidden') ||
            inPkg('react-remove-scroll') ||
            inPkg('react-remove-scroll-bar') ||
            inPkg('react-style-singleton') ||
            inPkg('get-nonce')
          ) {
            return 'vendor-radix';
          }
          // 大型独立库:动画 / 图标 / 表单 / 时间 / cron 各自成 chunk
          if (
            inPkg('framer-motion') ||
            inPkg('motion-dom') ||
            inPkg('motion-utils')
          ) {
            return 'vendor-motion';
          }
          if (inPkg('lucide-react')) {
            return 'vendor-icons';
          }
          if (
            inPkg('react-hook-form') ||
            p.includes('/node_modules/@hookform/') ||
            inPkg('zod')
          ) {
            return 'vendor-forms';
          }
          if (
            inPkg('date-fns') ||
            inPkg('cron-parser') ||
            inPkg('cronstrue') ||
            inPkg('luxon')
          ) {
            return 'vendor-time';
          }
          if (inPkg('cmdk')) {
            return 'vendor-cmdk';
          }
          // MVP-5:CodeMirror + 语言包 + 间接依赖一起进 chunk,React.lazy 触发才加载。
          // 注意 crelt / style-mod / w3c-keyname / @lezer/* / @marijn/* / @uiw/codemirror-* 都是
          // codemirror 运行时 peer dep,不归这里会被 vendor-misc 兜底 → 形成
          // vendor-codemirror -> vendor-misc -> vendor-codemirror 循环。
          if (
            p.includes('/node_modules/@codemirror/') ||
            p.includes('/node_modules/@lezer/') ||
            p.includes('/node_modules/@marijn/') ||
            p.includes('/node_modules/@uiw/react-codemirror/') ||
            p.includes('/node_modules/@uiw/codemirror-') ||
            inPkg('codemirror') ||
            inPkg('crelt') ||
            inPkg('style-mod') ||
            inPkg('w3c-keyname') ||
            inPkg('js-yaml')
          ) {
            return 'vendor-codemirror';
          }
          if (inPkg('react-dropzone') || inPkg('attr-accept') || inPkg('file-selector')) {
            return 'vendor-dropzone';
          }
          // 其余三方一律归入 vendor-misc(小工具:clsx / tailwind-merge / sonner / zustand 等)
          return 'vendor-misc';
        },
      },
    },
  },
  preview: {
    port: 5173,
  },
});
