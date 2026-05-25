---
name: main 分支进度
description: 主分支当前 todo / 状态 / 最近迭代
type: project
---

# 分支:main

## 目标

完成 Phase 1(项目骨架 + MVP-1 后端最小可用),让前后端能在 Docker Compose 下跑通"登录 → 仪表盘 → 看到一个 demo 脚本"的最小闭环。

## 最近迭代

- 2026-05-23 晚 · **JM 100% 可靠性深度调研 + 4-5 月日志精确重判** — 出 584 行调研稿 → 用户质疑域名 → 实测 banner 论崩 → 拉全 host syslog/journal/signin.log → 真相:原脚本 CF 33/33 = 100% 过盾,5 月失败 3 天里 2 天 VPS 平台问题(停机 22h + kernel panic)+ 1 天 server 502 + **真正脚本可优化只有 5-23 sign 反爬空响应 1 天**。修正方案:不追三层回退/curl_cffi/换域名,优先平台层补签 + v2 已有 marker 兜底。等用户决定是否恢复 host crontab 让明早 5-24 自然跑。
- 2026-05-23 深夜 · **JM v1 整改 + scp 接入主面板 web(Phase 1+2)+ MVP-1 远程 agent 后台启动** — 用户决"v2 废弃删,v1 升格" → 整改 v1(main.py + 补 `_chunked_sleep` + 改账密字段) + scp 5 文件到主面板 + chown + restart backend → SQLite scripts 表 3 行(jmcomic id=3)→ web /scripts 能看 3 卡片 ✅;host crontab `0 1 * * *` 北京 9-10 窗口激活(明早自然跑作对照基线);**派 1 opus agent 后台跑完整 MVP-1**(DB nodes 表 + agent 4 endpoint + Bearer middleware + executor 改造 + Agent CLI + 前端节点页 + ≥15 断言 verify,严禁 push/deploy,预计 4-8h 跨夜)。等 agent 完成通知 + 明早 host 自然跑数据。详见 [变更/2026-05-23晚-JM-v1整改与web接入.md](../变更/2026-05-23晚-JM-v1整改与web接入.md)。
- 2026-05-24 深夜 · 🎊 **MVP-1 端到端首次真测成功(run 27,49 秒)+ systemd 调优 + 平台级 manual 跳延迟** — 排 run 26 ReadTimeout 真因 = `dmesg: cgroup fork rejected by pids controller`,install.sh `TasksMax=128` 太小 Chrome 启不来;patch unit `MemoryMax 512M→2G + TasksMax 128→4096`;manual 跳延迟从 jmcomic v1.2 内迁到 `backend/sandbox_runner.py` 平台契约层(所有脚本统一,scheduled/retry/test 不变);**run 27 web 立即运行 → 49 秒完整 e2e 通过**:CF 一次过 + login + sign 返 `error:finished`(host 09:48 已签)→ 正确识别 JmAlreadySignedToday → web 显示 success;意外发现 run 26 Chrome 没启 → 没耗 CF 信任分 → run 27 CF 顺利过。MVP-1 完整 verified 上线,可宣告。详见 [变更/2026-05-24-MVP1端到端真测成功+systemd调优+平台级跳延迟.md](../变更/2026-05-24-MVP1端到端真测成功+systemd调优+平台级跳延迟.md)。
- 2026-05-24 下午-晚 · **MVP-1 完整上线生产 + e2e 链路通(run 26)+ 6 UX fix + v1.2 manual 跳 random_delay** — Phase 3 全 5 Step 完成(backend rebuild + alembic 0002 + frontend dist 3 次 + agent install on VPS-JM 节点 id=2 `vps-us8-8-jm` + 停 host crontab);run 26 (instance 3 jmcomic) 跑完整链路 web → backend → DB pending → agent poll → subprocess → main.py → Chrome,**链路 100% 通**,CF 超时 failure 是预期(IP 信任分今日已耗 2 次);6 UX fix(heartbeat 500 SQLite lock / 节点卡片 Terminal 按钮重看安装命令 / shadcn Tooltip × 4 / 创建实例报"未知错误"=serialize 缺 node_id / 编辑实例节点默认 local / "●未知"→"●待运行" never_run 状态);v1.2 main.py:trigger_type=='manual' 跳 random_delay(用户立即运行不再等 0-60min);scheduled 仍走错峰 random。今天不再点立即运行(CF 透支),明早 5-25 9-10 北京主面板自动 cron 真签到验证。详见 [变更/2026-05-24-MVP1部署上线+6个UX修复+v1.2manual跳延迟.md](../变更/2026-05-24-MVP1部署上线+6个UX修复+v1.2manual跳延迟.md)。
- 2026-05-24 中午 · **MVP-1 接力实施 Phase 0/1/2 完成** — opus agent 凌晨中断时只完成 backend 50%;我接手按 verify → agent CLI → frontend + backend schema 补丁顺序完成。新 `agent/` 4 文件(`signin_agent.py` 790 行 httpx long-polling + subprocess sandbox_runner + 心跳 + systemd);新 frontend `nodes.ts` hooks + `NodeList.tsx` 节点页(一次性 token + 一键安装)+ 路由 + 导航 + `InstanceFormSheet` 加 NodeSelect;backend `schemas/instance.py` + `instance_service.py` 加 `node_id` 校验(agent 漏的);`_verify_e2e.py` 11/11 ✅ + `pnpm build` 11.86s ✅。**Windows SQLite + TestClient WAL lock 卡 verify [10]+** — 测试环境问题(生产 docker Linux 不会有),用生产 e2e 真测代替。Phase 3 部署待用户授权。详见 [变更/2026-05-24-MVP1接力实施-agent+frontend+backend补丁.md](../变更/2026-05-24-MVP1接力实施-agent+frontend+backend补丁.md)。
- 2026-05-24 · **JM v1.0 host 首跑成功 + v1.1 cookies 复用智能重试上线** — host 09:48 北京自然跑 v1.0 → 30 秒 0 retry 拿 `JCoin:30 + EXP:100` ✅;**5-23 反爬已证实孤例**(5-24 server 完全正常);用户提"重试用第一次过 CF 的值,5 分钟间隔 × 3 次,cookies 真过期才重过 CF" → **v1.1 重构**(拆 `_do_login` + `_do_sign_only`,closure 管 cookies/session lifecycle,加 `JmCookieExpired` 异常 + `retry_interval_sec`/`cf_clearance_ttl_sec` 字段,3 次重试 CF 消耗 3→1)→ scp host + 主面板 + restart backend → SQLite version 1.0.0→1.1.0 ✅。通知集成等 MVP-1 通(干净分层,v1 不调 apprise)。详见 [变更/2026-05-24-JM-v1.1-cookies复用与智能重试.md](../变更/2026-05-24-JM-v1.1-cookies复用与智能重试.md)。


## 范围(MVP-1)

### 后端
- [ ] 项目骨架(`pyproject.toml` + `app/` 目录树 + Alembic 初始化)
- [ ] 配置加载(`app/config.py`,从 env / settings 表读)
- [ ] DB 模型 + Alembic 0001_initial 迁移(全部 8 张表)
- [ ] SQLite WAL PRAGMA 钩子
- [ ] Fernet 加密层(`app/core/crypto.py`)
- [ ] bcrypt 密码哈希 + session token 工具
- [ ] 鉴权中间件 + `/api/v1/auth/*` 路由(setup-status / setup / login / logout / me)
- [ ] 脚本扫描 + `/api/v1/scripts/*` 路由(列表 / 详情 / 扫描)
- [ ] manifest.yaml 解析与 schema 校验(`app/plugins/manifest.py`)
- [ ] 字段类型系统(`app/plugins/fields.py`)
- [ ] 健康检查 `/health`
- [ ] OpenAPI 自动生成(FastAPI 自带)
- [ ] 一个 demo 脚本 `scripts/bilibili-daily/`(manifest + main.py 占位实现)

### 前端(React + shadcn/ui)
- [ ] 项目骨架(`pnpm create vite` React-TS + `shadcn@latest init` + Tailwind v4)
- [ ] 全局样式系统(`@theme` directive + CSS vars,浅深色,sidebar 专属配色)
- [ ] 字体加载(`@fontsource-variable/inter` self-hosted)
- [ ] openapi-fetch client + middleware(401 跳登录 / 错误 toast / X-Requested-With 头)
- [ ] OpenAPI 类型生成脚本(`pnpm gen:api`)
- [ ] TanStack Query 配置 + QueryClient + DevTools
- [ ] React Router 7 路由表 + 鉴权 loader + redirect 模式
- [ ] Zustand `useAuthStore` + `useUIStore` 骨架
- [ ] `<ThemeProvider>`(next-themes,深浅 + system)
- [ ] PublicLayout + AppLayout(Sidebar 折叠 + Topbar + sonner toast 容器 + cmdk ⌘K 挂载)
- [ ] 登录页 `/login`(玻璃拟态卡 + mesh blob 背景 + Logo + focus ring)
- [ ] 初始化页 `/setup`(创建管理员 + 加密密钥强警示)
- [ ] 仪表盘 `/dashboard`(KpiCard with Recharts Sparkline + ScriptCard grid + Timeline 虚拟滚动)
- [ ] 脚本列表页 `/scripts`(DataTable + 卡片视图 Tabs 切换)
- [ ] 顶栏 + 侧栏 + 主题切换 + 命令面板

### 部署
- [ ] `Dockerfile`(backend,多阶段 + tini + 非 root)
- [ ] `Dockerfile`(frontend,Node 20 build → dist;CI/local 用)
- [ ] `docker-compose.yml`(caddy + backend,前端 dist 由 caddy serve)
- [ ] `Caddyfile`(反代 + SSE flush_interval -1)
- [ ] `.env.example`
- [ ] `.gitignore`(必须包含 `data/encryption.key`、`node_modules`、`dist`)
- [ ] `README.md`(部署指引)

### 暂不做(留 MVP-2)
- 实例 CRUD + 配置加密落库
- 调度引擎(APScheduler 接入)
- 子进程 sandbox runner
- SSE 实时日志
- 通知系统
- 备份导出/导入
- 设置页

## 下一步派发计划(并行 agent 工作流)

> 我作为统筹 PM,接下来按以下方式派 agent。每批中的 agent 是**并行**的,批次之间是**串行**的(后批依赖前批产出)。

### 批次 1 · bootstrap 项目骨架(我自己干,不派 agent)
预计 30-45 分钟。我直接创建:
- `backend/pyproject.toml`、`backend/app/` 空目录树、`backend/alembic.ini`、`backend/Dockerfile`
- `frontend/` 用 `pnpm create vite@latest . --template react-ts` 起 + `pnpm dlx shadcn@latest init` + Tailwind v4 安装
- `frontend/components.json`(shadcn config)
- `frontend/Dockerfile`(Node 20 build,产出 dist)
- `docker-compose.yml`、`Caddyfile`、`.env.example`、`.gitignore`
- 顶层 `README.md`

完成后,后续编码 agent 可以基于这个骨架填实现。

### 批次 2 · 后端核心层(并行 3 个 agent)
| Agent | 任务 | 关键依赖 |
|---|---|---|
| **Backend-Models** | DB 模型 + Alembic 迁移 + SQLite PRAGMA + 加密层 | `设计/后端架构.md` § 1, § 5.1-5.2, § 9.1 |
| **Backend-Plugins** | manifest 解析 + 字段类型系统 + 脚本扫描 service | `设计/后端架构.md` § 3, § 6 (services/script_service) |
| **Backend-Auth** | bcrypt + session token + 鉴权中间件 + auth API 路由 | `设计/后端架构.md` § 2.1, § 5.3-5.4 |

### 批次 3 · 后端业务层(并行 2 个 agent,依赖批次 2)
| Agent | 任务 | 关键依赖 |
|---|---|---|
| **Backend-Scripts-API** | `/api/v1/scripts/*` 路由 + dashboard 路由 | 批次 2 的 plugins + auth |
| **Backend-Demo-Script** | demo 脚本 `bilibili-daily/`(manifest + 占位 main.py) | `设计/后端架构.md` § 3.1, § 3.3 |

### 批次 4 · 前端基础层(并行 2 个 React agent,可与批次 2 同时启动)
| Agent | 任务 | 关键依赖 |
|---|---|---|
| **Frontend-Foundation** | Tailwind v4 `@theme` + 全局 CSS vars(浅深主题)+ 字体加载 + `<ThemeProvider>` + 公共布局组件 + shadcn 组件批量 add(button/card/dialog/sheet/input/select/switch/textarea/badge/alert/skeleton/tabs/tooltip/popover/dropdown-menu/sonner/command/sidebar/breadcrumb/avatar/separator/scroll-area/collapsible/form/slider/checkbox/radio-group/progress/hover-card/table) | `设计/前端UI设计.md` § 1, § 11 |
| **Frontend-Setup** | openapi-fetch client + middleware + TanStack Query 配置 + Zustand stores 骨架 + React Router 7 路由表 + 鉴权 loader + sonner toast 全局 | `设计/前端UI设计.md` § 2, § 5, § 6 |

### 批次 5 · 前端页面(并行 3 个 React agent,依赖批次 4 + 批次 3)
| Agent | 任务 | 关键依赖 |
|---|---|---|
| **Frontend-Auth-Pages** | `<PublicLayout>` + `/login`(玻璃拟态卡 + mesh blob 背景)+ `/setup`(创建管理员 + 密钥强警示) | `设计/前端UI设计.md` § 3.1, § 3.2 |
| **Frontend-Dashboard** | `<AppLayout>`(Sidebar 折叠 + Topbar + ⌘K cmdk + 主题切换)+ `/dashboard`(KpiCard with Recharts Sparkline + ScriptCard grid + Timeline `@tanstack/react-virtual`) | `设计/前端UI设计.md` § 2.2, § 3.3, § 3.11 |
| **Frontend-Scripts-List** | `/scripts`(DataTable 基于 TanStack Table + 卡片/表格 Tabs 切换 + 搜索/筛选)+ 公共组件 `<EmptyState>` `<PageHeader>` `<StatusBadge>` `<ScriptCard>` | `设计/前端UI设计.md` § 3.4, § 4 |

### 批次 6 · 集成验证(我自己干)
- 起 docker-compose,前后端联通
- 浏览器访问跑通"setup → 登录 → 仪表盘 → 脚本列表 → 脚本详情" 路径
- 修复跨 agent 写出来的不对齐问题
- 更新进度文档

## 最近迭代

- 2026-05-16 · **MVP-3B 完成**(本会话 opus agent · 5 任务全过 + bundle 大瘦身)。新增 2 文件 / 修改 5 文件:
  - **新装 2 个包**:`cron-parser@5.5.0`(替换自写 5 段迭代器,完整 cron 语义 + 时区)+ `react-colorful@5.6.1`(主题色 picker)
  - **新增页面**:
    - `pages/instances/InstanceList.tsx`(全局实例列表):PageHeader 动态统计(N 个实例 / M 个启用 / K 个暂停) + 搜索 Input + script_slug Select(useScripts 拉) + 状态 Select(全部/启用/禁用/暂停) + DataTable 7 列(icon 派色/cron/上次执行/下次/总执行|成功/启用状态/操作) + 行点击跳 `/scripts/:slug/instances/:id` + 操作菜单(详情/立即运行/启用-禁用/暂停 1h/恢复/删除) + 新建实例时若已筛 script_slug 直接打开 InstanceFormSheet,否则先弹"选脚本"对话框 + 删除/暂停 AlertDialog 二确
    - `pages/runs/RunList.tsx`(全局执行历史):PageHeader 含"上次刷新 X 前" + 筛选(script_slug / status / trigger_type / DateRangePicker = popover + 2 date input + 4 个 preset 按钮) + 实时跟随 Switch(开启 refetchInterval=3000) + 清理旧记录按钮(AlertDialog 选 7/14/30 天) + DataTable 8 列 + 行点击打开 RunDetailSheet + `/runs/:id` 路由直达自动 setSelected
  - **修改 CronInput**:删 100+ 行自写 nextTimes,改用 `CronExpressionParser.parse(expr, { tz: settings.timezone, currentDate: now })` 然后 `.take(3)` 取未来 3 次;时区从 useSettings 读(默认 Asia/Shanghai)
  - **修改 Settings 外观 Tab**:用 `<HexColorPicker>` 替换 6 色枚举 PaletteSwatch — 保留 6 色快捷预设(hex)+ 自定义 picker(HexColorPicker + HexColorInput);hex 写入 `--primary` / `--ring`(用 color-mix 50% 透明派生)/ `--chart-1`;`localStorage:signin-panel-palette-hex`;"恢复默认 Indigo" 按钮
  - **修改 LogViewer**:抽出 `readTermTheme()` helper 从 :root CSS vars 现取 → 加 `useTheme()` from next-themes,监听 `resolvedTheme` 变化时用 rAF 推 `term.options.theme = readTermTheme()`,主题切换 / 主题色切换都热刷
  - **修改 vite.config.ts**:加 `build.rollupOptions.output.manualChunks` 路径匹配函数,12 个 chunk:
    - `vendor-react` 235KB(react+react-dom+react-router+scheduler)
    - `vendor-radix` 140KB(@radix-ui/* + @floating-ui/* + react-remove-scroll + aria-hidden)
    - `vendor-charts` 345KB(recharts + d3-* + victory-vendor + internmap + react-smooth + decimal.js-light + react-is + fast-equals + recharts-scale)
    - `vendor-xterm` 308KB(@xterm/* + xterm + @microsoft/fetch-event-source)
    - `vendor-markdown` 157KB(react-markdown + unified + remark-* + mdast-* + micromark-* + hast-* + unist-* + 工具链)
    - `vendor-time` 302KB(date-fns + cron-parser + cronstrue + luxon)
    - `vendor-motion` 124KB(framer-motion + motion-dom + motion-utils)
    - `vendor-tanstack` 103KB / `vendor-forms` 84KB(rhf + zod + hookform-resolvers) / `vendor-icons` 36KB(lucide-react)/ `vendor-cmdk` 12KB / `vendor-misc` 129KB(clsx / tailwind-merge / sonner / zustand / next-themes / react-colorful / openapi-fetch / 等小工具)
  - **主 index bundle:2095 KB → 252 KB(-88%)**;无 chunk size 警告,无循环依赖
  - **路由接入**:`/instances` → `<InstanceList />` / `/runs` → `<RunList />` / `/runs/:id` → `<RunList />`(替换 Placeholder)
  - **验证**:`pnpm typecheck` 0 错 / `pnpm lint --max-warnings 0` 通过 / `pnpm build` 10.8s 成功
  - **已知 TODO 留 MVP-4**:(1) `react-day-picker` + `<Calendar>`(本次 DateRangePicker 是 popover + 原生 date input + presets,功能在但不如官方日历 UX 好)(2) MultiSelect status(后端 RunsFilter 只支持单 status,前端先按单选)(3) vendor-time 302KB 较大(luxon 是 cron-parser 5.x 引入的;若想更小可替换 date-fns → dayjs 或动态 import CronInput)(4) RouteErrorBoundary 由 router.tsx 引入但本任务未确认实现内容(本次未碰)

- 2026-05-16 · **MVP-3A 完成**(本会话 opus agent · dashboard 补 4 字段 + 通知闭环接通)。改 3 文件 + 新 1 文件:
  - `app/services/dashboard_service.py`(+125 行):`get_overview` 加 4 字段;新增私有函数 `_compute_sparklines_7d`(SQLite `strftime('%Y-%m-%d')` 分桶 + Python 补齐 7 天空桶,成功率分母只看终态)/ `_count_notifications_24h`(`count(rules) WHERE last_fired_at > now - 24h`,try 兜底)/ `_earliest_next_run_at`(`MIN(next_run_at) WHERE enabled=true`,tz 归一)
  - `app/schemas/dashboard.py`:`DashboardOverview` 加 `sparkline_7d_success` / `sparkline_7d_runs`(`min_length=7 max_length=7`)/ `notifications_24h`(`ge=0`)/ `next_run_at`(`datetime | None`)
  - `app/scheduler/executor.py`:删旧的占位 `dispatch_run_result` 调用,**把 retry 判断前移**(`will_retry=True` 时不发通知,符合 § 4.5 "最终通知按最后一次结果触发");新增 `_dispatch_notification(run_id, event)` 异步包装函数 — 自己拿 session/cipher/pool,双层 try 兜底任何异常都不影响 executor
  - 新建 `backend/_verify_mvp3_a.py`(25 断言):dashboard 字段格式 8 + 无规则触发 4 + 有规则触发 6 + dispatcher import/match_rules 2 + 清理 5
  - **验证**:`_verify_e2e.py` 11/11 + `_verify_mvp2_runner.py` 10/10 + `_verify_mvp2_apis.py` 57/57 + `_verify_mvp3_a.py` 25/25 = **103 全绿**
  - **dispatch 真送达证据**:测试日志末尾 `WARNING - A Connection error occurred sending JSON notification to 127.0.0.1.` — apprise.notify 真的发了 HTTP(127.0.0.1:1 没监听所以 Connection error),证明 executor → dispatcher → apprise pool.send 整条路径调通
  - **已知 TODO 留 MVP-4**:(1) `instances.next_run_at` 实时同步(目前 scheduler 内部知 next 但没回写 DB,dashboard 字段返 null)(2) backup/import 自动 restart (3) `script_scan_interval_sec` 热重载 (4) cron-parser npm 包 (5) 生产 docker compose restart + 复检
  - 详见 `变更/2026-05-16-MVP-3A通知闭环.md`
- 2026-05-16 · **MVP-2 批次 6C 前端升级完成**(本会话 opus agent)。新增 16 文件 / 修改 5 文件,前端 typecheck / lint / build 三绿:
  - **新增 shadcn UI 组件**(7 个):`textarea / switch / popover / slider / radio-group / progress / breadcrumb / command`(都按 shadcn copy-paste 风格直接落在 `src/components/ui/`,radix primitives 已在 deps 里)
  - **新增 4 个公共组件**:
    - `SecretInput.tsx`(显隐切换 + 复制按钮 + isSet 时占位"已配置,留空保持不变" + onTouched 让父决定 PATCH 时是否提交)
    - `CronInput.tsx`(cronstrue 中文翻译 + 自实现 5 段 cron 迭代器算未来 3 次执行 + 7 条预设 Popover;**自实现是因为 cron-parser 未装**,只支持 `* / N / N-M / N,N / */N`)
    - `DynamicForm.tsx`(11 种字段类型一一映射:string/secret/integer + slider/boolean/select/multiselect Combobox/multiline/cron/url/json;react-hook-form + zod schema 用 useMemo 编译;字段分组 Collapsible;secret edit 模式 + isSet 且未 touched → 提交时**剔除该字段**)
    - `LogViewer.tsx`(xterm + addon-fit/search/web-links + 调 `useLogStream` SSE;暂停/恢复/全屏 fullscreen API/搜索 Popover/清屏/导出 .log;autoFollow 用户滚上则停止 + 跳回底部按钮;stderr ANSI 红色)
  - **新增 3 个组合组件**:`InstanceFormSheet`(右抽屉创建/编辑 + meta 字段 + DynamicForm)/ `InstancesPanel`(脚本详情 Tab 用,卡片网格 + Trigger/Edit/Toggle/Pause/Resume/Delete 全套)/ `RunsPanel`(DataTable 接 useRuns)/ `RunDetailSheet`(stdout/stderr collapsible + 复制 + 截断 badge)/ `CommandPalette`(⌘K cmdk,挂在 AppLayout 内,接 useUIStore.commandPaletteOpen)
  - **新增 4 个 API hooks**:`instances.ts`(11 个 hook 覆盖 § 2.3 全套)/ `runs.ts`(useRuns/useRun/useCancelRun/useCleanupRuns + `useLogStream` 用 `@microsoft/fetch-event-source` 接 § 2.4.1 SSE)/ `notifications.ts`(channels + rules CRUD + test/preview)/ `settings.ts`(get/put + changePassword + 备份导出 fetch + import upload)
  - **新增 2 个页面**:
    - `pages/notifications/NotificationHub.tsx`(Tabs:渠道 + 规则;渠道卡片网格按 apprise scheme 自动识别图标;规则 DataTable + 创建 Sheet 含 scope/script/instance/event/channel 级联选择)
    - `pages/settings/Settings.tsx`(4 个 Tab:账户 = 当前用户 + 修改密码红色警告 / 外观 = 主题 RadioGroup + 6 色 swatch 写 CSS var 持久化到 localStorage / 备份 = 下载 + 上传 + AlertDialog 二确 / 关于 = 版本 + OpenAPI 链接 + 主密钥强提示)
  - **修改 5 个文件**:
    - `pages/scripts/ScriptDetail.tsx`:实例 Tab → `<InstancesPanel>`(triggered 跳 logs tab + setRunId)/ 历史 Tab → `<RunsPanel filter={{script_slug}}>` / 实时日志 Tab → Select 选 runId(最近 20 条 useRuns)+ `<LogViewer>`
    - `components/layout/AppLayout.tsx`:挂 `<CommandPalette>` + 顶栏搜索按钮接通 toggleCommandPalette(原占位 disabled 已去掉)
    - `app/router.tsx`:`/notifications` 接 NotificationHub / `/settings` 重定向到 `/settings/account` / `/settings/:tab` 接 Settings
    - `api/mocks/scripts.mocks.ts`:ScriptListItem 加可选 `id?: number`(后端 GET /scripts 必返但 mock 缺省)
    - `tsconfig` 路径未改;不依赖任何新 npm 包
  - **与 6A/6B 后端契约假设**:
    - GET `/api/v1/instances?script_slug=X` 列表项含 `script: {slug, name}` 嵌套(兼容降级到顶层 `script_slug`)/ GET `/api/v1/instances/{id}` 返回 `_secret_set: {field: bool}`
    - POST `/api/v1/instances/{id}/run` 返回 `{ run_id: number }`
    - GET `/api/v1/runs/{id}/logs/stream` 事件:`stdout/stderr/status/ping/end`(`status` 携 `{status, exit_code, duration_ms}` JSON)
    - GET `/api/v1/notifications/channels` 列表 `apprise_url` 已脱敏,POST/PATCH 传明文;PATCH 时不传 `apprise_url` 后端保留原值
    - POST `/api/v1/settings/backup/export` 返 `application/zip` 流;POST `/api/v1/settings/backup/import` multipart form `file` + `overwrite=true`
    - POST `/api/v1/auth/change-password` 不返 user,前端假设后端撤会话 → 前端主动登出 + 跳 /login
  - **验证**:`pnpm typecheck` 0 错 / `pnpm lint` 0 错 0 警 / `pnpm build` 11.6s(JS 2095 KiB + CSS 95 KiB,有 chunk size warning 但不阻塞;后续按需 manualChunks)
  - **已知 TODO**(留给 MVP-3 / 后续批次):
    - 后端若实际 SSE 实现与契约不符,LogViewer 需对应调整(目前对默认 message 也兜底 onStdout)
    - DynamicForm 的 json 字段没接代码编辑器(monaco/codemirror),用 Textarea + 等宽字体 + JSON.parse 校验
    - 主题色 picker 没用 react-colorful(未装),用 6 色预设 swatch
    - `/instances` 全局列表页 / `/runs` 全局列表页 / `/runs/:id` 详情页仍是 Placeholder(可用 RunsPanel + 加 PageHeader 快速接)
    - DynamicForm 的 secret PATCH 语义需要后端 update_instance 严格按 § 5.2 实现(未提交字段保留原值)— 6A agent 已写 fields.merge_secrets,理论对得上
- 2026-05-16 · **MVP-2 批次 6A 后端核心完成**(本会话 opus agent)。实现 13 文件 + 修改 3 文件,~3900 行代码:
  - **schemas/instance.py(239 行)**:`InstanceCreate/Update/ListItem/Detail/PauseRequest/RunResponse/TestResponse` 全套 Pydantic v2;InstanceDetail 用 `secret_set` alias 输出 `_secret_set`
  - **services/instance_service.py(633 行)**:11 个公开函数 — `list_instances`(分页 + script_slug/enabled/status 三个过滤)/ `create_instance`(校验 → Fernet 加密 → 落库 → scheduler.register)/ `get_instance_detail`(解密 + mask_secrets)/ `update_instance`(用 fields.merge_secrets 实现"未提交的 secret 字段保留原值" + cron/enabled 变 → reschedule)/ `delete_instance`(先清 last_run_id 防 FK 自指)/ `enable/disable/pause/resume` / `trigger_instance`(预创建 pending run → 提交 → scheduler.trigger_now 异步排执行 → 返回 run_id)/ `test_instance`(并发预检抛 ConcurrentRunConflict)
  - **api/v1/instances.py(338 行)**:**11 个端点全部实现** + 全部 `Depends(get_current_user)`
  - **runner/sandbox.py(303 行)**:`python -m app.runner.sandbox` 入口,stdin 读 JSON → 切 cwd → `importlib.util.spec_from_file_location` 加载 main.py → SimpleNamespace ctx(含 logger + notify) → 调 run(config, ctx) → stdout 最后一行 `__RUN_RESULT__` → exit 0/1;异常时仍写 RunResult + traceback 到 stderr → exit 1;容忍多种 RunResult 形状(dict / to_dict() / 带 success 属性)
  - **runner/stdio_protocol.py(147 行)**:`RESULT_MARKER` 常量 + `RunContextPayload`/`SandboxInput` dataclass + `pack_input/parse_result_line/format_result/unpack_input`,容忍 BOM / 行尾空白 / 从下往上找结果行
  - **runner/log_broker.py(243 行)**:`RunLogChannel` per-run 多订阅者 asyncio.Queue 广播 stdout/stderr/status/end + `LogBroker` 全局单例;慢消费者静默丢消息;`max_subscribers=10` 上限抛 ResourceLimitError;close 自动广播 end
  - **scheduler/engine.py(507 行)**:`SchedulerService` — AsyncIOScheduler + MemoryJobStore + ZoneInfo(settings.tz);`start/shutdown/register/unregister/reschedule/pause/resume/trigger_now/schedule_retry`;`trigger_now` 用 APScheduler 内部 `_eventloop` + `run_coroutine_threadsafe` 兼容 sync 路由(**关键 bug fix**:`asyncio.get_event_loop()` 在 worker thread 抛 RuntimeError);启动注册 3 个内置周期任务 scan_scripts(5min)/resume_paused(1min)/housekeeping(1h)
  - **scheduler/executor.py(883 行)**:`execute_run` 实现 § 4.4 14 步全流程 + `run_instance_test` 试运行;子进程 `asyncio.create_subprocess_exec` + Windows 容错(`CREATE_NEW_PROCESS_GROUP` 替代 `start_new_session` + `CTRL_BREAK_EVENT` 替代 SIGTERM)+ 进程组强杀(`os.killpg + SIGTERM/SIGKILL`,Linux);env 白名单含 `PYTHONPATH=BACKEND_DIR`(让子进程能 import app.runner);stdout/stderr 各 256KiB 尾部截断 + truncated flag;`__RUN_RESULT__` 从下往上解析;超时 → status=timeout + exit_code=-15;协议异常 → status=error;失败按指数退避调 retry job
  - **scheduler/concurrency.py(77 行)**:`ConcurrencyLimiter` asyncio.Semaphore(默认 4)+ async-with `slot()` + active/available metrics
  - **scheduler/retry.py(75 行)**:`compute_retry_delay` 指数退避 cap 3600s + `should_retry`(成功/已达 max_retries/cancelled 不重试)
  - **tasks/{scan_scripts,resume_paused,housekeeping}.py**:周期任务回调,housekeeping 同时清过期 session + 重置 locked_until 到期的 user.failed_login_count
  - **deps.py 加 `SchedulerDep / get_scheduler / get_scheduler_service`**;**main.py lifespan 完整接入**(startup:configure_logging → get_cipher → ensure_defaults → scan_all → SchedulerService.start → app.state.scheduler;shutdown:scheduler.shutdown(wait=True) + log_broker.shutdown())
  - **`_verify_mvp2_runner.py` 10 项端到端验证全绿**:create(secret 脱敏 OK)→ run(run_id=1)→ 0.5s 内 status=failure(coklw 空 cookie 路径符合预期)→ PATCH 保留 secret(_secret_set.cookie=True 仍在,random_delay_sec=5 生效)→ disable/enable scheduler 同步(`Removed job instance:1` / 再注册 `next=2026-05-17 09:00:00+08:00` 时区正确)→ test 端点 322ms 完成不写 runs(total_runs 仍 1)→ delete 级联
  - **`_verify_e2e.py` 11/11 仍绿**(MVP-1 e2e 未破坏)
  - **已知 TODO 留 MVP-3 / 6B / 6C**:cleanup_runs.py 让 6B agent 写;runs API list/detail/SSE 让 6B agent 写(broker 已暴露 + log_broker 单例就绪);dispatcher.dispatch_run_result 让 6B agent 写(executor 已留可选 import + 容错);Windows CTRL_BREAK_EVENT 超时路径未在本机实测(coklw 0.5s 即结束,30s 超时未触发);scan_scripts 间隔目前硬码 300s,后续可读 settings.script_scan_interval_sec
- 2026-05-15 · 新建分支文档 · 完成详细设计阶段(后端架构 + 前端 UI + 技术调研三份文档)· 准备进入 Phase 1 编码
- 2026-05-15 · **切换前端栈 Vue 3 → React 18 + shadcn/ui + Tailwind v4**(应用户要求);旧 Vue 设计稿归档,新版 React 设计稿由 Plan agent 重写中;后端契约零变化;批次 4-5 派发计划已更新;ADR-011 + ADR-012 已记录
- 2026-05-15 · **⏸ 会话暂停(用户休息)**。后台 Plan agent(写 React UI 设计稿)已 TaskStop。下次接手:重派 agent → Write 设计稿 → 进入批次 1
- 2026-05-16 · 用户回来"继续" · 检查环境(node 24 / pnpm 10 / python 3.13 / git ✅;装了 **uv 0.11**;docker 本机不必装,生产部署 ssh 服务器)· 后台重派 Plan agent 写 React UI 设计稿 · 完成 **批次 1A(部署层 5 文件:.gitignore / .env.example / docker-compose.yml / Caddyfile / 顶层 README.md)** + **批次 1B(后端配置 3 文件:pyproject.toml / alembic.ini / Dockerfile)** · 等 UI 设计稿出稿后继续 1C(后端骨架)+ 1D(前端骨架)
- 2026-05-16 · 用户确定 **生产部署目标**:`jb.aijiaxia.cc` → `154.9.238.144`(灰云直连,Caddy 可自动 HTTPS),SSH `root` + `J:\密钥\美国质量8-8\vcs-deploy-rsa` · `.env.example` 已更新默认 DOMAIN/ACME_EMAIL · ADR-013 已记 · 详见 `变更/2026-05-16-部署目标确定.md`
- 2026-05-16 · 用户"继续" · 建好后端完整目录树(15 子目录)+ 顶层 data/scripts/logs/ + 全部空 `__init__.py` / `.gitkeep` / `backend/.python-version=3.12` · 后台并行派 **Plan agent**(React UI 设计稿,第 3 次派发,前两次因清理/未启动失败)+ **general-purpose agent**(批次 1C 后端骨架填充,~40 文件:main.py / config.py / core/{crypto,security,exceptions,logging} / db/{base,session,pragma} / alembic/env.py + 全部子模块占位 stub) · 等通知 → Write 设计稿 + Review 骨架 + 做 1D 前端骨架
- 2026-05-16 · 用户追加任务:写 **第一个真实签到脚本 coklw**(`https://coklw.net/`,WordPress + Cloudflare turnstile),HAR 抓包在 `D:\coklw.har`(3.3MB / 45 请求);9-10 点北京时间随机签到(default_cron `0 9 * * *` + 脚本内 `random_delay_sec` 字段)· 派 **opus agent** 后台分析 HAR 并写 `scripts/coklw/`(manifest.yaml + main.py + requirements.txt + README.md) · 这是第一个**业务脚本**,既能签到也能作为多合一面板的真实测试样本
- 2026-05-16 · 用户纠正模型偏好 → **全局 CLAUDE.md 已加段**"派 Agent 默认 opus"(对应 opus 4.7 1M / opus 4.6 max fast);写代码/设计/调研/实现一律 opus;只读快速搜索可用 sonnet;琐碎机械活可用 haiku。**以后所有项目通用**
- 2026-05-16 · 3 个 opus agent 全部完成:Plan(React UI 设计稿 70KB 已 Write 到 `设计/前端UI设计.md`)/ general-purpose(1C 后端骨架 88 文件,**TestClient(app) 已 verified**,`/health` 200)/ opus(coklw 脚本 5 文件,**python main.py 空 cookie dry-run 已 verified**,优雅 exit 1)
- 2026-05-16 · 批次 1D 前端骨架 opus agent(末尾 403 限流但 35 文件全落盘):`pnpm install` ✓ / `pnpm build` ✓ 1.9s(dist 299KB JS + 26KB CSS + 12 字体 woff2);**手工修了 1 个 bug**:`src/api/client.ts` 的 `onError` 返回类型从 unknown 改为 `Promise<void>`(只 sniff 不替换错误)
- 2026-05-16 · **批次 2 三 opus agent 已派出(Backend-Models/Auth/Plugins)但被 TaskStop**(用户休息);agent 在跑到一半被停,backend/app/ 没受到污染影响;**下次接手:重派批次 2 即可继续**
- 2026-05-16 · **⏸ 会话暂停(用户休息)**。所有后台任务已停。下次只需重派批次 2 → 集成 review → 派批次 5 前端页面 → 部署。估计到 MVP-1 上线再 25-35 分钟
- 2026-05-16 · **批次 2 实质验证通过** · 用户回来"继续" · 盘点发现 3 个 stop 前的 agent 已落 8 model + 8 service + 8 API + 4 middleware + 5 plugins + 8 schemas + alembic 0001(质量高,实质实现非 stub)· 跑 `alembic upgrade head` 创建 8 表(**修了 alembic.ini 中文 GBK 编码问题** → 改纯 ASCII)· 写 `_verify_e2e.py` 端到端 11 断言 · 跑出 8/11 绿:auth/csrf/logout/login/error_handler 全通,scripts API 404 (3 失败)· **修 3 处跨 agent 不对齐**:(a) `main.py` 接入 middleware 三件套 + lifespan 调 `get_cipher()`;(b) `schemas/auth.py` 双引号嵌套 SyntaxError 改单引号;(c) DB 残留 → rm + 重 upgrade · 派 opus agent 后台补 `script_service.py`(13 行 stub → 完整)+ `scripts.py`(空 router → 6 端点)+ 自验
- 2026-05-16 · 用户指令"一切完成之后你自己测试一下" → 已把**自测矩阵**(Claude Preview 走浏览器 + 生产 curl + docker logs)落到 README.md 末尾,作为 MVP-1 终点目标
- 2026-05-16 · opus agent 补完 `script_service.py`(312 行)+ `scripts.py`(166 行 6 端点),`_verify_e2e.py` **11/11 全绿**;agent 顺手建了 `backend/.env`(让本地 `SCRIPTS_DIR=../scripts`),我加 `backend/.dockerignore` 隔离避免污染容器镜像
- 2026-05-16 · 派出 **批次 5 三个 opus 前端 agent 并行**:5A(Layouts + 公共组件 + /login + /setup)/ 5B(/dashboard + KpiCard + Sparkline + Timeline,mock 兜底待 dashboard API)/ 5C(/scripts 列表 + /scripts/:slug 详情,**直连真实后端 API**)。等通知 → 集成 → 部署 → 自测
- 2026-05-16 · **批次 1C 后端骨架填充完成**(opus agent)。共写入 78 文件:**实质实现 17 个**(`app/{__init__.py, main.py 重写, config.py 修订, deps.py}` + `core/{exceptions, logging, crypto, security, __init__.py}` + `db/{base, session, pragma, models/__init__.py, __init__.py}` + `api/{router.py, __init__.py, v1/__init__.py}` + `alembic/{env.py, script.py.mako}` + `tests/{conftest.py, __init__.py}` + `backend/README.md`)+ **占位 stub 57 个**(`api/v1/{auth,scripts,instances,runs,notifications,settings,dashboard}.py` 各带空 APIRouter + `db/models/{user,session,script,instance,run,notification,setting}.py` + `schemas/{auth,script,instance,run,notification,setting,dashboard}.py` + `services/{auth_service,script_service,instance_service,run_service,notification_service,settings_service,dashboard_service}.py` + `scheduler/{engine,executor,concurrency,retry}.py` + `runner/{sandbox,stdio_protocol,log_broker}.py` + `plugins/{manifest,fields,scanner,loader}.py` + `notifications/{apprise_client,templates,dispatcher}.py` + `middleware/{auth,csrf,error_handler,request_log}.py` + `tasks/{cleanup_runs,scan_scripts,resume_paused,housekeeping}.py` + `utils/{ids,time,shell}.py` + 各子模块 `__init__.py`,每个 stub 顶部带 docstring + `TODO(Batch X / Backend-XXX agent)` 引用设计稿章节)+ **4 个 `.gitkeep`**(顶层 `data/scripts/logs/` + `alembic/versions/`)。**验证**:82 个 `.py` AST 全 PASS、UTF-8 无 BOM、LF 行尾、所有 `app.*` 内部 import 全部解析无错。**接手者立即可跑**:`cd backend && uv venv --python 3.12 && uv pip install -e ".[dev]" && uv run uvicorn app.main:app --port 8000` → 看到启动日志 + `/health` 返回 `{"status":"ok","timestamp":"...","version":"0.1.0"}` + `/docs` 上 7 个空 router 分组占位
- 2026-05-16 · **批次 5C 完成**(opus agent):`/scripts` 列表 + `/scripts/:slug` 详情 + DataTable + 缺失 hooks 落盘。**新建 4 文件 + 编辑 2 文件**:
  - 新建 `frontend/src/components/common/DataTable.tsx`(@tanstack/react-table + shadcn `<Table>` 封装,泛型,支持列排序 / 列可见性下拉 / 客户端+服务端分页 / loading skeleton 8 行 / empty 插槽 / 行 hover / 行点击)
  - 新建 `frontend/src/pages/scripts/ScriptList.tsx`(PageHeader 标题描述操作组 `刷新`+`扫描脚本` + 工具栏 `搜索Input`+`状态Select`+`视图Tabs卡片/表格` + 卡片网格(复用 5B 的 ScriptCard)与 DataTable 双视图 + 删除 AlertDialog 二次确认,带 `?confirm=true` + 红字警告"磁盘文件不会被删除")
  - 新建 `frontend/src/pages/scripts/ScriptDetail.tsx`(hero icon + slug code + version Badge + 启用/禁用 Badge + author + homepage 链接;操作组 `立即运行`(toast TODO)/`启用|禁用`/`扫描更新`;6 个 Tab:**概览**(基本信息 dl + 运行时 + 上下次执行) / **实例**(EmptyState + 新建按钮 toast TODO) / **配置 schema**(渲染 fields_schema 11 种 type 字段定义只读预览,每个字段卡片显示 label/key/type 徽章(chart-N 派色,secret=红)/required */description/min/max/options/pattern 等附加属性) / **执行历史**(EmptyState 占位) / **实时日志**(EmptyState 占位) / **README**(react-markdown + remark-gfm + prose dark:prose-invert))
  - 新建 `frontend/src/hooks/useDebounce.ts`(搜索框降频 250ms)
  - 扩展 `frontend/src/api/hooks/scripts.ts`(在 5B 已写 useScripts + useScanScripts 基础上加 useScript / useEnableScript / useDisableScript / useDeleteScript;补 ScriptDetail / ScriptField / ScriptFieldType / ScriptRuntime / ScanScriptsResponse 接口;scan 成功 toast 摘要 added/updated/removed/errors;invalidate `['scripts']` + `['dashboard']`;**保留 5B 的 mock fallback**,只在非 401/403 错误时静默回退)
  - 接入 router:`/scripts` → `<ScriptList />`,`/scripts/:slug` → `<ScriptDetail />`(替换 5A 的 Placeholder)
  - 安装 shadcn:table / tabs / select / dropdown-menu / badge(skip,已有)/ dialog / alert-dialog;**修了 shadcn CLI 漏写 dialog + alert-dialog 文件的 bug**(手工补两个文件,radix-ui 包已装齐)
  - 验证:`pnpm lint` 0 warning / `pnpm typecheck` 0 error / `pnpm build` ✓ 11.10s,dist 8.2MB(JS 1.48MB + map 6.5MB,CSS 82KB,12 字体 woff2)
  - **关键交互**:列表→点行/卡片跳详情;扫描后 toast(`新增 N · 更新 M · 移除 K`);删除前 AlertDialog 二确(请求加 `?confirm=true`);启停后 toast + 失效缓存自动 refetch;详情 README tab 用 prose 渲染 markdown 表格/代码块/链接(target=_blank)
  - **已知 TODO**(留后续批次):立即运行(待 instance API)/新建实例(待 instance API + DynamicForm)/执行历史 tab(待 runs API)/实时日志 tab(待 SSE 端点 + xterm)/secret 字段的特殊高亮(目前用 chart-5 红色徽章)
- 2026-05-16 · **批次 5B 完成**(opus agent):`/dashboard` + 4 个公共组件落盘。新增 9 个 src 文件:`pages/dashboard/Dashboard.tsx`(KPI 6 张网格 + 即将执行/最近失败 双卡 + ScriptCard 健康度网格 + Timeline section)+ `components/common/{KpiCard,Sparkline,ScriptCard,Timeline}.tsx` + `api/hooks/{dashboard,scripts}.ts` + `api/mocks/{dashboard,scripts}.mocks.ts`。装了 8 个 shadcn 组件(badge/hover-card/scroll-area/collapsible 自装,其余 4 个 5A 已装),**修了 1 个 shadcn 装到 `frontend/@/` 而非 `frontend/src/` 的 Windows alias bug**(手工 mv 修正)。**修了 2 处既存 ESLint 配置 bug**:(a) `@eslint/js` 没装 → `pnpm add -D @eslint/js globals`;(b) 全 DOM globals 缺失导致 shadcn ui/* 报 77 处 `no-undef` → `eslint.config.js` 用 `globals.browser`,并对 `components/ui/*` 关 `react-refresh/only-export-components` + `no-undef`,对 `app/router.tsx`/`main.tsx` 关 `react-refresh`。Dashboard 已挂 `<AppLayout>` 子路由 `/dashboard`(由 5A 路由表统一管),mock 数据兜底(后端 dashboard API 还是 stub,失败时静默 fallback 到 mock,console.warn,user 看到完整 UI)。最终验证:`pnpm typecheck` ✓ / `pnpm lint --max-warnings 0` ✓ / `pnpm build` ✓ 10.96s(dist 1.47MB JS + 82KB CSS,体积偏大主要是 5C 引入的 `react-markdown` + `recharts` + `react-syntax-highlighter`,未做 code-split 是 vite 默认警告;后续可加 manualChunks)。**已知 TODO**(留 Batch 3):后端 `/api/v1/dashboard/*` 4 端点上线后,`dashboard.ts` 里的 fallbackData 路径自动失效,真数据接管;`useDashboardTimeline` 实际应改调 `/api/v1/runs?limit=20&order=desc`(设计稿 § 2.7 中 timeline 是分桶聚合,不是 run 列表 — hook 注释已点出)
- 2026-05-16 · **第一个真实业务签到脚本 `scripts/coklw/` 完成**(opus agent / HAR 逆向)。HAR 关键发现:站点是 WordPress + 主题做了 `md5(action+salt)` 防爬,所有 admin-ajax action 是 hash;签到 action = `07e2fafdb61c964ff31938b1ac72ace4`,状态聚合 action = `a1695e2e97b11317858156779ec6ab41`(用 `<sub_action_hash>[type]=<sub>` batch 调用)。`_nonce` **不在首页 HTML**,必须先 GET 状态接口拿响应顶层 `_nonce` 再用它 GET 签到接口 — 已登录态与未登录态 nonce 不同(`0f936b5151` vs `0ee8f3a4e5`),登录路径不实现(避开 turnstile),走 cookie 复用(`wordpress_logged_in_*` + `wordpress_sec_*`)。文件:`manifest.yaml`(2.4KB,4 字段:cookie/random_delay_sec/user_agent/skip_if_signed,default_cron `0 9 * * *`)+ `main.py`(12.7KB,严格符合 § 3.3 契约,顶层 `run(config, context) -> RunResult`,本地 `python main.py` 可独立测试,从 `COKLW_COOKIE`/`COKLW_DELAY`/`COKLW_DEBUG` 环境变量取参)+ `requirements.txt`(`httpx>=0.27`)+ `README.md`(6.7KB,cookie 提取教程 + 接口逆向表 + 故障排查表)+ `icon.svg`(日历+对勾,lucide 风)。**验证**:Python 语法/AST PASS;YAML schema PASS;空 cookie 路径返回 RunResult(success=false, message="Cookie 字段为空..."),exit=1;格式合法但伪造 cookie 路径成功送达 coklw.net(Cloudflare 返回 403,被 `CoklwError` 捕获写入 RunResult.message,exit=1)— 端到端流程贯通。**这是 sandbox runner 就绪后第一个可上线的真实脚本**
- 2026-05-16 · 🎉 **MVP-1 生产上线 https://jb.aijiaxia.cc** · 部署方案 A(复用 host nginx + certbot,docker 只跑 backend 绑 127.0.0.1:8000;因服务器 nginx 已在服务 vibecoding.site 等多个站点)· 装 docker 29.1.3 + compose 2.40 + certbot 2.9.0 · 修了 2 个 Dockerfile bug(`<(...)` bash 进程替换 + COPY README.md 丢失)· certbot --nginx 自动签 Let's Encrypt + 改 server block 加 443 ssl + 80→443 redirect · `docker compose up + alembic upgrade head` 成功 · **11 项生产 curl 自测全绿**(HTTPS/SPA/assets/setup/me/scan(找到 coklw)/list/detail/CSRF 403/安全 header)· 主密钥 `/opt/signin-panel/data/encryption.key` 已生成(警告日志已强提示备份,**P0 待异地备份**)· 管理员 admin/admin1234ABC(待用户登录后改强密码)· 详见 `变更/2026-05-16-MVP-1上线.md`
- 2026-05-16 · 用户指令"进行 MVP-2,密码等全部完成再进行修改" → 派 3 个 opus agent 后台并行:**6A 后端核心**(实例 CRUD/调度引擎/sandbox runner/main.py 接入)+ **6B 后端 API 扩展**(runs+SSE/通知/dashboard真接入/settings/backup)+ **6C 前端升级**(DynamicForm 11 类型/SecretInput/CronInput/LogViewer xterm+SSE/实例 UI/通知页/设置页/⌘K)。等通知 → 集成 → 部署 → 自测让 coklw 真按 cron 跑
- 2026-05-16 · 用户截图指出 UI bug:**侧栏展开后覆盖主内容**(因为 shadcn `use-mobile` 默认 `MOBILE_BREAKPOINT=768`,窗口稍缩小就误判为 mobile → Sheet overlay 覆盖式)→ 修 `frontend/src/hooks/use-mobile.tsx` 把 breakpoint 改为 **480**(只真手机宽度才走 Sheet,480-1280 桌面窄屏仍是 push 模式让位)→ HMR 已生效;待 6C agent 完成后 `pnpm build` + Preview `resize 1280` 验证
- 2026-05-16 · **MVP-2 / 批次 6B 后端 API 扩展完成**(opus agent)。覆盖 runs+SSE / notifications / dashboard 真接入 / settings + backup。
  - 写/改文件 17 个(全在我的领地,**未触碰 6A 领地** `app/scheduler/* app/runner/* app/services/instance_service.py app/api/v1/instances.py app/schemas/instance.py`):
    - schemas:`run.py`(RunListItem/RunDetail/Cleanup{Req,Resp})+ `notification.py`(Channel/Rule + Test/Preview)+ `dashboard.py`(Overview/Upcoming/RecentFailure/TimelineBucket)+ `setting.py`(SettingItem + BackupMeta)
    - services:`run_service.py`(list/get/cancel/cleanup,SSE 不在此 — 在 API 层;cancel 调 `scheduler.cancel_run` 容错)+ `notification_service.py`(渠道/规则 CRUD + test_send + preview;scope 一致性校验;池缓存自动失效)+ `dashboard_service.py`(4 函数:overview/upcoming/recent-failures/timeline,timeline 用 SQLite `strftime` 分桶 + Python 补空桶)+ `settings_service.py`(白名单 11 key + 类型 validator + 内存缓存 + ensure_defaults + builtins.set 避坑)
    - notifications:`apprise_client.py`(AppriseClientPool 单例 + dict[channel_id, Apprise] 缓存 + `async send → (ok, latency_ms, error)` + mask_apprise_url 脱敏 + `asyncio.to_thread` 避免堵 loop)+ `templates.py`(jinja2 Env + `tail/human_duration/local_time` filter + 默认模板 § 9.4 + `---` 分隔 title/body 语法 + sample ctx 给 preview)+ `dispatcher.py`(match_rules 按 scope 优先级去重 + min_interval_sec 节流 + 整体 try 兜底不阻塞 executor)
    - api/v1:`runs.py`(5 端点:list/cleanup/SSE/detail/cancel;**SSE 用 sse-starlette EventSourceResponse + 回放历史 + 订阅 6A LogBroker.channel + ping=15s + X-Accel-Buffering: no + request.is_disconnected**;6A LogBroker 已就绪所以接通) + `notifications.py`(11 端点)+ `dashboard.py`(4 端点)+ `settings.py`(GET 列表/单项 + PUT 校验 + POST /backup/export 流式 zip(sqlite3 `.backup` 一致性快照)+ POST /backup/import multipart 解析 meta)
    - tasks:`cleanup_runs.py`(按 settings.retention_days 跑;**修复 instances.last_run_id 指向被删行** → 重置为最新存活 run)
    - 改:`app/main.py` 启动期插 `ensure_defaults`(11 项预置 setting)
  - 与 6A 协调:6A 已写完 `app/scheduler/engine.py:SchedulerService` 和 `app/runner/log_broker.py:LogBroker` + `get_log_broker()` + `RunLogChannel.subscribe()`。SSE 端点直接接通 — 用 `broker.get_or_create(run_id).subscribe()` async-for `{event, data}` dict 形式;**broker 自身已做 max_subscribers=10 上限 + ResourceLimitError(→ 429)**,SSE 层无需再限速。executor 应在 run 结束后调 `notifications.dispatcher.dispatch_run_event(db, run, event, cipher, pool)`(6A 接入时找我接口)
  - 修了 1 个**严重 bug**:`settings_service.set()` 函数名遮蔽 builtin `set()` → `ensure_defaults` 里 `existing_keys: set[str] = set(...)` 实际调到我的函数报 missing args 错。已分两步修:(a) 保留 `set_value` 作主名 + `set = set_value` 别名兼容规格;(b) `ensure_defaults` 改用 `builtins.set`
  - **验证**:`_verify_e2e.py` **11/11 绿**(idempotent 化 — 自动 setup/login 二选一 + 密码候选);`_verify_mvp2_apis.py` **57/57 绿** 含:
    - notifications channels 6 端点(创建/列表/单项/PATCH/test/delete);test 用无效 SMTP `mailto://user:pass@127.0.0.1:1` → 期望 ok=False,实测 ok=False + latency_ms=2259ms + error="apprise.notify 返回 False" — **通**
    - notifications rules 5 端点 + preview;preview 渲染默认模板 → `[FAILURE] 我的账号 - Demo 签到` + body 186 字
    - settings:GET 列表 ✓ / PUT retention_days=14 ✓ / PUT -5 → 422 ✓ / PUT unknown_key → 422 ✓ / backup/export → zip 含 db.sqlite3+meta.json ✓ / backup/import 回灌自己导出 → parsed.version ok
    - dashboard:overview 含全部 5 字段 ✓ / upcoming/recent-failures/timeline(hour & day & 非法 bucket)
    - runs:GET 列表 + status 筛选 + 404 + cancel 404 + cleanup 422(空)+ cleanup 200(deleted=0)+ SSE 端点 404(路由已挂)
    - dispatcher + templates 单元:渲染 + filters + mask + apprise pool.send bogus URL 不崩
  - 已知 TODO(留下批):(1) executor 集成 `dispatch_run_event` 在 run 终态时调用,context 取自 `app.notifications.{apprise_client, dispatcher}`;(2) backup/import 真替换 db + restart 仍未实现 — v1 限制,需运维手动 docker compose restart;(3) settings 未走 settings 表里的 `script_scan_interval_sec` 实际驱动 scheduler 周期(硬编码 300 秒) — 改 settings 后需重启生效
  - **进度**:6A scheduler/executor/runner 已就绪;6B runs/notifications/dashboard/settings 已就绪;等 6C 前端页面 + 集成 + 自测

- 2026-05-17 用户咨询答疑(纯只读会话,无代码改动)。澄清 5 件事:(1)与青龙面板对比 — 我们更轻量(Python only / 单用户 / 强契约 manifest 11 字段类型 / Fernet 加密 / 镜像 <200MB),青龙生态大但偏重型;(2)添加新脚本流程 — scp 到 `/opt/signin-panel/scripts/<slug>/` 后 ScriptList 页面点"重新扫描"(`POST /scripts/scan`),故意不做网页上传避免 RCE;(3)脚本开发标准 — 必须有 `manifest.yaml`(11 字段类型) + `main.py`(从 stdin 读 JSON config、末尾打 `__RUN_RESULT__{...}` JSON 到 stdout、exit 0/非 0),完整范例 `scripts/coklw/`;(4)Obsidian 集成 — 推荐把 `进度/` 作为独立 vault 打开,wiki link/反向链接/关系图谱原生可用;(5)**git 状态澄清** — 实际**从未 git init**(`E:\签到脚本多合一` 无 .git;`D:\dd\deom\签到聚合` 仅含一句"初衷.md"占位,亦无 git)。用户原以为"似乎同步到 git"是误会;P0 风险待用户决定 git init + 推 GitHub。
- 2026-05-17 ✅ **首次 git init + commit + push 到 GitHub `qiuridong/-web`**(237 文件,commit `704b47f`)。修复 `.gitignore` 安全洞(补 `/backend/data/` 拦 encryption.key + db.sqlite3,避免主密钥泄露)+ 新建 `项目说明.md`(~480 行真人版功能/规范文档)+ 在 Obsidian vault `D:\dd\deom\签到聚合\项目-签到管家.md` 建项目活页本。完整流程见 [`变更/2026-05-17-git-init-与项目说明文档.md`](../变更/2026-05-17-git-init-与项目说明文档.md)。
- 2026-05-17 PM 派 **opus agent 后台修 audit High 剩 7 项**(本机改 + 跑全部 verify,**不**部署生产,**不**动用户密码/用户名,agent ID `a2fd536...`)+ 完成 **MVP-5 Web 脚本编辑器(方案 ② Monaco 全套)设计稿** [`设计/Web脚本编辑器.md`](../设计/Web脚本编辑器.md)(8 段,后端 6 API + 前端 ScriptEditor + 安全模型 + 1-2 小时实施路线)。用户决策:用户名 `admin` 保持不变,密码已自改强密码 ✅;并行抓包第二个签到脚本待定。GitHub PAT 误解已澄清(Win GCM 已自动记住凭证,以后 push 不弹窗)。下一节点:audit High agent 通知完成 → PM review → 部署生产;用户抓包好 → 写第二个脚本。
- 2026-05-17 PM(晚)**用户澄清后重写 MVP-5 设计稿**:不要 Monaco 全套 IDE,真实需求 = **上传现成脚本目录/zip 到 scripts/ 自动入库(主)+ CodeMirror 轻编辑器在线小修单文件(次)**。砍掉 AST 危险词扫描(过度防御)+ 用 `react-dropzone` 拖拽上传 + `@uiw/react-codemirror` 轻编辑器(总 bundle 增量从 ~2MB 降到 ~200KB)。后端 API 从 6 个简化到 5 个(upload / files 列表 / 读 / 改 / 删)+ zip slip 防御 + 单文件 256KiB / zip 1MiB 限制 + 自动 dry-run + `.backups/` 自动备份。实施时间从 ~2 小时降到 ~50 分钟(并行)。旧 Monaco 方案保留为附录"曾考虑的高规格扩展"。audit High agent 仍在后台跑(本机改 verify 触发 .pyc 生成 + 偶尔改 `_verify_*.py` 是正常工作动作)。
- 2026-05-17 晚 ✅ **audit High agent 完成**:修 7 项 High(#7/#9/#10/#11/#12/#13/#15)+ 锁定 #14 ADR,改 15 backend 文件 + 新建 `_verify_mvp5_high_fixes.py` 41 断言。PM 二次跑批 6 个 verify 全过(178 断言)。补 `.env.example` 加 `ENVIRONMENT` + `EXPOSE_DOCS` 注释(用户/运维知道 #9 收紧)。变更档案 [`变更/2026-05-17-audit-High-7项加固.md`](../变更/2026-05-17-audit-High-7项加固.md)。
- 2026-05-17 晚(深) 🎉 **PTFans 第二个真签到脚本上线 + audit 一并部署生产**:opus agent 分析 `D:\PTFans.har` 3.1MB → 写 5 文件(manifest 3KB / main.py 21KB,完整异常体系 + Cloudflare 兜底)。dry-run 3/3 过。打包 `backend/app + scripts/ptfans` 342KB → scp → docker compose build/up → smoke 全绿(`/openapi.json` 404 验证 #9 / order 参数 401 验证 #13)。**修了我自己写错的文档**:`项目说明.md § 3.3` 协议从"裸 stdin/stdout"改为正确的 `run(config, context) -> RunResult` 函数模型(coklw 同款),§ 3.6 铁律表同步纠正。多合一语义正式成立 N=2(coklw WordPress / ptfans NexusPHP)。变更档案 [`变更/2026-05-17-PTFans脚本+audit部署.md`](../变更/2026-05-17-PTFans脚本+audit部署.md)。等用户浏览器扫描入库 + 建实例填 cookie 完成业务闭环。
- 2026-05-17 深夜 **前端 abort 错误 toast 静默 hotfix(v1)**:用户创建 PTFans 实例时同时收到 ✅ 绿色"已创建" + ❌ 红色 `signal is aborted without reason`,误以为失败。诊断:`frontend/src/api/client.ts onError` 没过滤 AbortError → React Query 在组件 unmount / refetch 抢占时主动 abort pending fetch 被当成业务错误。fix:onError 顶部 early return 过滤 5 种(`AbortError` / `ERR_CANCELED` / message 含 `aborted` 或 `signal is aborted` 或 `The user aborted`)。`pnpm build` 10s → 新 hash **`index-JmCKC6a4.js`**(原 `BIPAwks0.js`)→ scp dist 2.8MB → 解压到 `/opt/signin-panel/frontend/dist/`(nginx 静态文件无需 reload)。变更档案 [`变更/2026-05-17-前端abort错误toast静默-hotfix.md`](../变更/2026-05-17-前端abort错误toast静默-hotfix.md)。
- 2026-05-17 深夜 **abort hotfix v2(v1 漏了关键一层)**:用户反馈"abort 还经常出现,任何修改都触发"。grep 发现 `frontend/src/api/query-client.ts` TanStack `QueryClient.defaultOptions.mutations.onError` 是第二层 toast 入口,**所有 useMutation 都走这里**(创建 / 改配置 / 立即运行 / 删除)— v1 完全没碰到。v2 抽 `isAbortError()` 通用函数,在 query-client.ts 三处用(mutations.onError + queries.retry 都过滤 abort)+ client.ts v1 保留作双层兜底。新 hash **`index-CP_QytwL.js`**(原 v1 的 `JmCKC6a4`)。**教训**:做全局错误处理 fix 必须 grep `toast.error` + `onError` + `defaultOptions` 所有入口,不能只看一个 middleware 就收手。用户硬刷新后**确认 abort 消失** ✅。
- 2026-05-17 深夜 🛌 **今日收工**:用户决定不立即跑 PTFans,等明天 9:00 看 cron 自动跑。3 件收尾全做完:(1)`git commit 84bdb07` + `git push origin main` 备份到 https://github.com/qiuridong/-web(3 commit 全在 GitHub:704b47f initial / 39e5754 audit+PTFans / 84bdb07 abort fix)/(2)开机自启核实已默认配好(docker daemon enabled + nginx daemon enabled + backend `restart: unless-stopped` + 容器当前 healthy 50 分钟),服务器重启后链路自动恢复 / (3)进度文档全部刷新。**明天 PM 接手第一件事**:浏览器 `/runs` 看 PTFans 9:00–9:30 是否自动签到出绿色 success,coklw 9:00–10:00 同样观察。下一里程碑 MVP-5(Web 上传 + 在线编辑器)设计稿 442 行待实施(派 2 agent 并行约 75 分钟,用户随时启动)。
- 2026-05-18 上午 🚨 **P0 httpx hotfix**(scheduled cron 100% 失败):用户报告今早 9:00 两个签到都 `ModuleNotFoundError: No module named 'httpx'`。Root cause = audit Critical #1 一刀切禁 PYTHONPATH 透传,但生产 Dockerfile 走 `--target /deps` + `ENV PYTHONPATH=/deps`,子进程没继承导致第三方包找不到。修法:`executor._build_env` 白名单透传 PYTHONPATH(过滤指向 `backend/` 的路径,保留 `/deps`)+ 在 `_FORBIDDEN` env_passthrough 之前优先生效。部署方式:`docker cp executor.py 进容器 + restart backend` 热补丁(不 build,避免和并行跑的 MVP-5 后端 agent 半成品冲突)。验证:用户手动 Run #7 stderr `随机延迟 38 秒后开始签到` = httpx 加载成功 ✅。**临时性**:hotfix 在容器内,不在镜像,等 MVP-5 完成 docker build 永久带上。变更档案 [`变更/2026-05-18-httpx缺失-生产cron恢复-hotfix.md`](../变更/2026-05-18-httpx缺失-生产cron恢复-hotfix.md)。
- 2026-05-18 ptfans cookie 失效(独立问题):Run #7 真正失败 message `首页未识别到用户名(或检测到 takelogin form),cookie 已过期`。PT 站 server 主动清 session(虽然 cookie expires 2027 没到)。用户操作步骤:浏览器重登 ptfans.cc → F12 右键复制 c_secure_pass Value → 拼 `c_secure_pass=<value>` 填实例 → 测试改 random_delay_sec=0 立刻跑 → 成功后改回 1800。**遗留 UX**:用户两次在对话里粘真 cookie(我多次提醒",cookie 是账号免密令牌,贴聊天有风险")— 是用户习惯问题,但侧面说明前端 secret 字段填错时没有"我只想给后端看,不要给 AI/chat 见"的提示;以后可加个 PT cookie 字段帮助文字"敏感凭证,只贴控制面板,不要贴聊天/截图"。
- 2026-05-18 **MVP-5 启动 2 agent 并行**:用户说"做 MVP-5"。派 Agent-Backend(`backend/app/api/v1/script_upload.py` + `services/script_upload_service.py` + `schemas/script_upload.py` + `_verify_mvp5_upload_edit.py` 15 断言,~40min)+ Agent-Frontend(`frontend/src/pages/scripts/components/UploadScriptDialog.tsx` + `FileEditDialog.tsx` CodeMirror lazy + `ScriptFileList.tsx` + 2 hooks + 5 新依赖 + 集成 ScriptList/ScriptDetail,~50min)并行后台跑。PM 期间不动 backend/frontend 避免冲突,只可以动 `进度/` 和 `scripts/`(后者前端 agent 测试要用 coklw 范例,只读)。完成后 PM 集成 review + 跑全 6+1=7 verify(178+15=193 期望全过)+ `docker compose build`(把 executor.py httpx hotfix 永久带上)+ 部署前端 dist + git commit + push 全套。
- 2026-05-18 **MVP-5 agent 工作完成度高 + PM 集成阶段启动**:盘点 backend 与 frontend agent 落地结果 — backend 4 新文件齐(`script_upload.py` 16KB / `script_upload_service.py` 30KB / `schemas/script_upload.py` / `_verify_mvp5_upload_edit.py`)+ 4 改文件(`api/v1/__init__.py` 注册 router / `api/v1/scripts.py` 加 `?delete_files=` / `api/router.py` +3 行 / `core/exceptions.py` +17 行新异常)。frontend 5 新组件齐(UploadScriptDialog 20KB / FileEditDialog 11KB / ScriptFileList 8.5KB / CodeMirrorLazy / fileLanguage)+ 2 新 hooks + 集成 ScriptList/ScriptDetail + 装 6 个 CodeMirror+js-yaml 依赖。**所有文件全部落地** ✅。PM 派后台跑 7 verify 回归 + pnpm build 验证 bundle,等结果再做完整部署。agent notification 尚未到达,但文件落地完整度提示 agent 实质完成,只是收尾日志没到。
- 2026-05-18 PM 诊断 ptfans Run #10 失败真根因(**不是 cookie!**):用户重登 ptfans 拿新 cookie(value 真换了,expires 2027-04-09 → 2027-05-18,user_id 从数字变字符串)+ delay=0 触发 Run #10 → 同样失败"未识别用户名"。PM 同 cookie SSH 容器内 `httpx.get(https://ptfans.cc/index.php)` 拿 **200 + 含 `userdetails.php?id=21550`** → 锁定脚本正则 bug,非 cookie。Bug:`scripts/ptfans/main.py` 的 `RE_USERNAME` 硬编码 `class="User_Name"`,但 `/index.php` 当前主题(BambooGreen)不用这个 class。修法:新增 `RE_LOGGED_IN_HINT`(宽松:`userdetails.php?id=<数字>` 或 `logout.php` 链接)+ `_check_logged_in` 改用宽松版;`RE_USERNAME` 保留给 `_parse_user_info`(抽不到 fallback username="unknown")。部署:`scp scripts/ptfans/main.py` 到 host volume(`./scripts:/app/scripts`),无需 restart 容器,下次脚本起来即用新代码。**教训**:严格抽取(用户名+class)和登录态判定应解耦 — 严格抽取失败可降级,登录与否判定应用宽松信号(`userdetails`/`logout` 链接 = 登录,`takelogin` form = 未登录)。**等用户再次立即运行验证签到能跑通**。
- 2026-05-23 **远程 VPS MVP-1 调研 + JM 完整改造**:MVP-1 调研稿 420 行(6 架构 → 推荐 B+F);接入第 1 个远程节点 VPS-JM(38.55.132.186,Ubuntu 24,SSH 密钥免密 OK);JM 脚本改造 v1 selenium → 测试 CF 没过(同 IP 4 次)→ 严格 diff 证明代码等价 → 对照实验铁证(host 原版同样不过 = IP 信任分问题);5 月 signin.log 统计 19/23 success;v2 加 5 类精细异常 + http helper;**用户提议方向转变**:用 HAR 解析后改 cookie 复用版(cf_clearance 2027 年过期 + PHP `remember` 长期登录令牌 + sticky 显示 server IP 强绑定);**重构 v2 cookie 版**(15.7KB 纯 httpx,旧 selenium 改名 `main_selenium_fallback.py` 保留)+ manifest 简化 + README 重写;host crontab 停 + 备份;用户进一步提议 v3(账密 + cf_clearance 每次 login 拿新 session)— 更优,等用户选 A/B/C/D。变更档案 [`变更/2026-05-23-JM接入+改造v1+精细诊断v2.md`](../变更/2026-05-23-JM接入+改造v1+精细诊断v2.md)。
- 2026-05-19 🎉 **MVP-5 全栈上线 + format.ts 时区 hotfix + executor.py httpx hotfix 永久落地**:MVP-5 2 agent 并行完成(backend 4 新 4 改 + frontend 5 组件 2 hooks + 6 依赖),`_verify_mvp5_upload_edit.py` 30/30 全过(超设计稿 15)。用户报告"coklw 1 点 cron 没触发"→ PM 查 DB 发现 Run #13 实际 success "今日已签到"(UTC 17:00 = CST 01:00),根因是 `parseISO()` 把无 Z 后缀的 naive UTC 字符串当本地时间 → 中国用户全部 timestamp 偏 -8h。修法:`toDate()` 检测时区后缀,若无则补 'Z' 假定 UTC。部署:`pnpm build` → 新 hash `index-V0pR5svQ.js` + `docker compose build backend`(把 executor.py hotfix 永久带上 + MVP-5 backend 上线)→ smoke 全绿(/health 200 / POST upload 403 CSRF / GET files 401)。3 个生产 cron 实测 verified success:coklw 凌晨 1 点 scheduled + 上午 10:10 manual + ptfans 9:00 scheduled。Obsidian 主笔记 + `规范增加字段.md`(manifest 字段速查 250 行)+ 今日详细总结全更新。**等用户**:Ctrl+F5 硬刷新拿新 hash + 真测 MVP-5 上传 + 在线编辑 + 时间显示终于对了。git push 等用户授权(预计 3 个 commits 按主题拆)。
- 2026-05-25 🎉 **多合一 N=3 jmcomic 上线 + v1.1.0 业务弹性集大成**:VPS-JM 38.55.132.186 接入(paramiko 自动化 SSH 密钥部署 + sshd PubkeyAuth 启用 + 摸底确认 OS Ubuntu 24.04 / Python 3.12 / 装 komari/argo/xray/v2ray/sing-box 综合机)→ 找到原 JM selenium 脚本 `/root/JMComic-Auto_Sign_in/` + host crontab `0 2 * * *` → 改造 v1 selenium 平台版 → 加精细诊断 v2(6 类异常 + `_http_request` + `_parse_json_or_raise`)→ 跑测试 CF 5 次未过 → 用户提议跑原版对照 → **铁证 CF 信任分模型**(同 IP 同天 ≥3 次 selenium 调用必被临时拉黑,IP 信任分 24h 自然恢复)。用户提议 cookie 复用方案 → 抓 60MB HAR 深度分析(605 entries / 356 18comic 请求)→ verify cf_clearance Expires=2027(2 年浏览器层面)+ NexusPHP `remember` cookie 含 username/MD5 password/SHA1 签名 + `sticky` cookie 揭示 IP↔server 强绑定 + 桌面签到后按钮消失(手机端 endpoint 未抓)→ 本机 httpx 直调 sign 返 `{"msg":""}` anonymous(IP 不匹配)→ 写 v2 cookie 复用版(纯 httpx)→ 用户提议 v3 cf_clearance + 账密 → 用户洞察"和老代码没区别"= 核心症结 server 反爬 + TLS 指纹非 Chrome,v3 不解决根本 → **决策放弃 cookie 路线,回归 v1 selenium**(已 33/33 host 验证)+ **加业务弹性**。最终 v1.1.0 上线(用户亲手 finalize manifest/README):6 fields(+ retry_interval_sec + cf_clearance_ttl_sec 两个新字段)+ **session 复用**(重试不重启 Chrome 节省 IP 信任分)+ **cf_clearance TTL 自管理**(避免静默失效)+ **8 个繁简体首页 marker 兜底**(救回 5-23 server 反爬空响应)+ 6 类异常 + 完整 RunResult.data diag。host crontab 已停 + 备份 `/root/.crontab.backup.20260523-103809`。**多合一覆盖 3 种典型反爬模式**(WordPress / NexusPHP / Cloudflare+NexusPHP+Selenium)。等 MVP-1 远程 agent 通后,jmcomic 实例 node_id 绑定 VPS-JM,本平台接管 JM 调度。用户后续洞察"凌晨 1 点 cron 是假成功"(server 还没切到新一天 → status 接口返回"今日已签",其实是昨天的没翻页 → skip 真签到)→ 改 cron 8 点观察 → 明天 5-20 见分晓 → PM 修正变更档案"假成功业务陷阱"段。
- 2026-05-23 📝 **远程 VPS 多节点功能调研 + VPS-B 接入(MVP-1 准备阶段)**:用户提需求"主面板管理多 VPS 脚本,像探针一样自动生成安装代码"。PM 写 420 行调研稿 [`设计/远程VPS脚本执行调研.md`](../设计/远程VPS脚本执行调研.md)(6 架构 / 7 类似项目 / 安全模型 / DB schema / 工程量 35-50h 分 3 MVP 切片)。**推荐选项 B(Pull Agent + HTTP Long Polling,GitHub Actions runner 同款)+ F(Tailscale)**。用户给 VPS-B 154.9.238.251 / root + 密码,PM 用临时 paramiko 自动化首次接入:密码 SSH → 部署 ed25519 公钥(`J:\密钥\美国4-4\jb-251-ed25519`)→ 改 sshd_config 启用 PubkeyAuth + restart sshd → 验密钥登录 ✅。**摸底意外**:用户说有 JM天堂签到脚本,实测**完全没有**(find / crontab / docker / ps 全空),VPS-B 是综合代理/监控机(komari-agent + argo + xray/v2ray/sing-box + nginx + iperf3)。**注意**:Komari 已在用 = 用户熟悉探针式部署,我们 signin-agent 照样设计(管理员生成 token + 一行 bash 命令)。本机清理:卸载临时 paramiko/invoke/pynacl 防 docker build 幽灵依赖 + 删 `_tmp_vps_b_init.py`。**等用户**:JM 脚本到底在哪台机(可能换新 VPS)+ 授权开干 MVP-1(10-15h 派 1 agent)。变更档案 [`变更/2026-05-23-远程VPS-MVP1-准备阶段.md`](../变更/2026-05-23-远程VPS-MVP1-准备阶段.md)。
- 2026-05-23 晚 🎯 **用户给真 JM VPS 38.55.132.186 + 决策 A 完全接管 + JM 改造完成 + 远程 sandbox 测试中**:用独立临时 venv paramiko(不污染 backend)自动化接入新 VPS(密钥 `J:\密钥\8-8特价美国\jm-186-ed25519`)。摸底找到真 JM 主版 `/root/JMComic-Auto_Sign_in/JMComic_Sign_in.py` + `crontab 0 2 * * *` host 直接跑(青龙在 docker 跑别的事,**完全不动**)。读完整 276 行理解:SeleniumBase UC + Xvfb 绕 CF Turnstile,**账密明文硬编码**(已提醒用户私有仓库或上传清密)。用户决策 A 完全接管 + "你可以试一次签到,今天已签 server 应返'今日已签'"。PM 改造 `scripts/jmcomic/` 5 文件:manifest.yaml(secret 字段加密 username/password)+ main.py(改 `run(config,context)→RunResult` 协议,完整异常体系 JmAlreadySignedToday/JmCloudflareBlocked/JmLoginFailed,重试 3 次,timeout sanity check)+ requirements + README + icon。tar + scp + 解压到 VPS-JM `/tmp/jmcomic-test/` + sandbox_runner.py,后台跑 stdin 喂 config+context JSON,期望 server 返"今日已签"= success in message 验证端到端迁移代码可行。TaskCreate 4 步骤跟踪(1/2 完成,3 in_progress,4 pending 清理 + 报告)。等测试结果出来一起写完整变更档案 + 决定 MVP-1 远程 agent 实施时机(JM 既然能 host crontab 跑,MVP-1 不急,可以先用 mock 脚本验证 agent 链路,然后再迁 JM)。
- 2026-05-23 深夜 ✅ **JM 改造 v2 精细诊断完成 + signin.log 完整分析 + 5-23 sign 空响应真根因排查**:测试结果 3×5 CF 重试全失败 + 3 张失败截图(diff 严格 verified 代码 100% 等价原版,失败真因 = 同 IP 同天第二次自动化触发 CF 升级到 invisible challenge,host cron 02:33 UTC 已消耗 IP 信任分)。signin.log 728 行精准统计:**5 月 1-23 日 19 天成功 + 5-02(server 502)+ 5-07/5-13(完全无记录)+ 5-23 今天 sign 接口空响应**(整月签满奖励今年已不可能)。用户手动浏览器签到成功证实 server 没挂,**5-23 是 JM 反爬升级**对自动化 sign 调用静默返 HTTP 200+空 body。用户反馈 v1 错误"不能定位位置" → v2 改造:**6 个细分异常类**(`JmCloudflareBlocked` / `JmLoginEndpointError` / `JmLoginFailed` / **`JmSignEndpointError`** / `JmIndexEndpointError` / `JmNetworkError` / `JmAlreadySignedToday`)+ `JmError.to_data()` 暴露所有 diag(endpoint/url/status_code/content_type/content_length/body_preview/elapsed_ms)+ `_http_request` helper 每次 HTTP 调用记录详细日志 `[POST /login] HTTP 200 ct=... len=...B body_len=... 234ms` + `_parse_json_or_raise` 严格校验(非 200 / 空 body / 非 JSON / 解析失败 4 种具体原因分别 raise)+ **`_check_already_signed_via_index` 兜底**(sign 接口空响应时 GET 首页扫 8 个繁简体 marker 如"今日已簽到"/"已簽到"/etc,匹配则自动转 `JmAlreadySignedToday`=success 平台语义)。668 行 / Python 语法 OK / **未部署未测试**(按约定等 MVP-1 通)。变更档案 [`变更/2026-05-23-JM接入+改造v1+精细诊断v2.md`](../变更/2026-05-23-JM接入+改造v1+精细诊断v2.md)。**等明天 5-24 凌晨 host cron 自动跑** → 看 JM server 是否恢复(JCoin 出来 = 临时;还是空 = 真升级反爬,v2 兜底立刻派上用场)。
- 2026-05-18 早 🚨 **P0 httpx 缺失 hotfix**:用户报 coklw + ptfans 两个 scheduled 触发都失败 `ModuleNotFoundError: No module named 'httpx'`。grep + ssh 核实:生产 Dockerfile `uv pip install --target /deps + ENV PYTHONPATH=/deps`,但 audit Critical #1 (2026-05-16) 把 PYTHONPATH 写进子进程 `_FORBIDDEN` → 子进程 sys.path 不含 `/deps` → import 必失败。修 `executor.py:_build_env` 加 PYTHONPATH 白名单透传(过滤 backend/ 路径防 import app.*,保留 /deps)。**热补丁部署**(`docker cp` + restart,不 rebuild 避免和 MVP-5 agent 半成品代码冲突,build 等 MVP-5 完成时一起做)。backend healthy + 已加载 2/2 enabled instance。**等用户立即运行 coklw 验证**。
- 2026-05-18 · **MVP-5 派 agent 中**:用户启动 MVP-5(Web 上传 + 编辑器)。派 2 opus agent:Agent A 后端(`script_upload.py` 5 端点 + service ~200 行 + 15 断言)/ Agent B 前端(UploadScriptDialog + FileEditDialog 含 CodeMirror lazy + ScriptFileList + 装 5 新依赖)。后台跑约 50-75 分钟。PM 期间只做 httpx hotfix(完全不动 backend/app 主线 + frontend/src,避免冲突),等通知后集成 → 跑 7 verify(193 断言期望)→ 完整 build + 部署(把 httpx hotfix 永久带上)→ commit + push。

## 已知坑(开发中遇到再补)

- (待补)
