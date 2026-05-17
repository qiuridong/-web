# 签到管家 · 前端

React 18 + Vite 6 + TypeScript 5.7 + shadcn/ui + Tailwind v4 + Recharts + Framer Motion。

## 快速开始

```bash
# 1. 安装依赖(首次)
pnpm install

# 2. 启动后端(另一个终端,在 backend/ 下)
cd ../backend
uv run uvicorn app.main:app --port 8000 --reload --workers 1

# 3. 生成 OpenAPI 类型(后端起来后跑一次,以后契约变更再跑)
pnpm gen:api

# 4. 启动前端开发服务器
pnpm dev
# → http://localhost:5173
```

## 常用脚本

| 命令 | 用途 |
|---|---|
| `pnpm dev` | 启动 Vite 开发服(端口 5173,代理 `/api` → `localhost:8000`) |
| `pnpm build` | 类型检查 + 生产构建,产物在 `dist/` |
| `pnpm preview` | 本地预览 build 产物 |
| `pnpm typecheck` | 仅做 TypeScript 类型检查,不输出文件 |
| `pnpm lint` | ESLint 检查(零警告策略) |
| `pnpm test` | Vitest 单元测试(一次性) |
| `pnpm test:ui` | Vitest UI 模式 |
| `pnpm gen:api` | 从后端 `/openapi.json` 生成 `src/api/schema.d.ts` |
| `pnpm shadcn add <name>` | 添加 shadcn/ui 组件,产物到 `src/components/ui/` |

## 添加 shadcn 组件

```bash
# 一次添加全部基础组件(批次 4 Frontend-Foundation agent 会做):
pnpm dlx shadcn@latest add \
  button card dialog sheet dropdown-menu tabs \
  input label select switch textarea badge alert sonner \
  skeleton table tooltip popover collapsible separator \
  scroll-area command form slider checkbox radio-group \
  progress hover-card avatar breadcrumb sidebar \
  accordion alert-dialog toggle-group pagination
```

详见 `进度/设计/前端UI设计.md` § 11.3。

## 目录结构

```
frontend/
├── public/                  # favicon / logo (空,等接手填充)
├── src/
│   ├── main.tsx             # 入口:挂 Provider 与 Router
│   ├── App.tsx              # (RouterProvider 模式下基本不用)
│   ├── app/
│   │   ├── router.tsx       # createBrowserRouter,目前仅占位
│   │   └── index.css        # Tailwind v4 + @theme + 全部 OKLCH CSS vars
│   ├── api/
│   │   ├── client.ts        # openapi-fetch + middleware
│   │   ├── query-client.ts  # TanStack Query QueryClient 单例
│   │   └── schema.d.ts      # openapi-typescript 自动生成(占位)
│   ├── components/
│   │   ├── ui/              # shadcn add 目标(空,等批次 4 填)
│   │   ├── common/          # 业务公共组件(空)
│   │   ├── layout/          # 布局组件(空)
│   │   └── theme/           # ThemeProvider(已实现)
│   ├── stores/              # Zustand stores
│   ├── lib/                 # 纯函数:cn / format / error
│   ├── hooks/               # 自定义 hook(空)
│   ├── types/               # 业务类型(空)
│   ├── styles/              # 额外样式(空)
│   └── vite-env.d.ts
├── components.json          # shadcn config
├── tailwind.config.ts       # v4 主要靠 @theme,仅放 plugin
├── postcss.config.mjs
├── tsconfig.json / tsconfig.app.json / tsconfig.node.json
├── vite.config.ts
├── eslint.config.js
└── package.json
```

## 当前状态(本骨架)

本骨架由 **批次 1D · Frontend-Skeleton agent** 写入(2026-05-16)。完成项:

- ✅ 全部根配置文件(package.json / vite / tsconfig / postcss / tailwind / components.json / Dockerfile / eslint / .gitignore / .env.example / index.html)
- ✅ 全部 OKLCH CSS vars(`src/app/index.css`,严格按设计稿 § 1.5,浅深色完整)
- ✅ 入口文件 `main.tsx`(Provider 链路 + 字体 + 路由)
- ✅ `<ThemeProvider>` next-themes 包装
- ✅ `<App.tsx>` 占位(RouterProvider 模式下基本不用)
- ✅ 路由表占位(`/login` / `/dashboard` / `*` 三个文字页)
- ✅ openapi-fetch client + middleware 占位(401 dispatchEvent / >=500 toast)
- ✅ TanStack Query QueryClient 单例
- ✅ Zustand UIStore(persist)+ AuthStore 占位
- ✅ `cn()` / `formatDate` / `formatBytes` / `isUnauthorized` 工具
- ✅ 全部子目录 `.gitkeep` 占位

接手者跑 `pnpm install && pnpm dev` 应能看到:
- http://localhost:5173 自动跳 `/login`(loader redirect)
- "Login (TODO · 等 Frontend-Auth-Pages agent)" 文字
- `/dashboard` 直接访问 → 同样占位文字
- 主题切换 hook 可用(暂未挂 UI 控件)
- 控制台无 TS / ESLint error

## 已知限制

- `src/api/schema.d.ts` 是空文件 + TODO 注释,需后端起来后运行 `pnpm gen:api` 自动生成
- `src/components/ui/` 还没有 shadcn 组件;由批次 4 `Frontend-Foundation` agent 用 shadcn CLI 批量 add
- 实际页面内容由批次 5 三个 React agent 编写

## 设计契约位置

| 内容 | 文件 |
|---|---|
| 视觉风格 / OKLCH 配色 | `进度/设计/前端UI设计.md` § 1 |
| Tailwind v4 `@theme` 完整骨架 | `进度/设计/前端UI设计.md` § 1.5 |
| 路由表 | `进度/设计/前端UI设计.md` § 2 |
| 页面 wireframe | `进度/设计/前端UI设计.md` § 3 |
| 公共组件清单 | `进度/设计/前端UI设计.md` § 4 |
| 状态管理 | `进度/设计/前端UI设计.md` § 5 |
| API 封装 | `进度/设计/前端UI设计.md` § 6 |
| 推荐目录结构 | `进度/设计/前端UI设计.md` § 9 |
| 关键依赖完整列表 | `进度/设计/前端UI设计.md` § 10 |
| shadcn 安装与组件清单 | `进度/设计/前端UI设计.md` § 11 |
| 后端 API 路由清单 | `进度/设计/后端架构.md` § 2 |
| SSE 端点详细设计 | `进度/设计/后端架构.md` § 2.4.1 |
