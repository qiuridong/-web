---
name: 签到脚本聚合管理面板
description: 项目总索引,所有 AI/协作者第一文件
type: index
---

# 签到脚本聚合管理面板 · 进度索引

> 这个文件是**所有接手者的入口**。读完它就能开干。
> 大段设计文档在 `设计/` 子目录,本索引只放高层目录与必读速查。

---

## 项目身份

- **名称**:签到脚本聚合管理面板(暂定中文名"签到管家")
- **目标**:把零散的 Python 签到脚本统一到一个 Web 控制台,服务器 7×24 调度 + 浏览器一站式管理 + 通知推送
- **仓库**:**https://github.com/qiuridong/-web**(2026-05-17 首次 push,237 文件,commit `704b47f`)
- **默认分支**:`main`(待 init)
- **提交规范**:Conventional Commits(`feat: ` / `fix: ` / `chore: ` 等)
- **推送命令**:本仓库未配置 remote

### 生产部署目标(2026-05-16 确定)

- **域名**:`jb.aijiaxia.cc` → A 记录指向 `154.9.238.144`,Cloudflare 灰云(直连,不走 CDN),Let's Encrypt HTTP-01 challenge 可通
- **服务器**:`154.9.238.144`(美国节点,Ubuntu 24)
- **SSH 用户**:`root`
- **SSH 密钥(本地)**:`J:\密钥\美国质量8-8\vcs-deploy-rsa`(OpenSSH RSA 私钥)
- **连接命令**:`ssh -i "J:\密钥\美国质量8-8\vcs-deploy-rsa" root@154.9.238.144`
- **部署目录**(规划):`/opt/signin-panel`
- **生产 URL**(部署后):`https://jb.aijiaxia.cc`

> ⚠️ 密钥**文件本身**不在 git 里(放在外部 `J:\密钥\`),路径只用于本地操作引用。

### 是否提交进度文件
- **`.gitignore` 是否包含 `进度/`**:否(进度即交接产物)

## 30 秒接手区(必读)

1. **技术栈已锁定**:Python 3.11 + FastAPI + APScheduler 3.x + SQLite(WAL) + **React 18 + Vite + TS + shadcn/ui + Tailwind v4 + Recharts + Framer Motion** + Caddy + Docker Compose
2. **架构核心契约**:看 [设计/后端架构.md](设计/后端架构.md) 中"§3 脚本插件接口规范" + "§4 调度引擎方案" — 所有编码 agent 必须遵守
3. **UI 视觉契约**:看 [设计/前端UI设计.md](设计/前端UI设计.md) 中"§1 视觉风格指南" + "§3 关键页面 wireframe" — 所有前端编码 agent 必须遵守

**必跑两条命令**(等代码就绪后):
```bash
docker compose up -d                # 起服务
docker compose logs -f backend      # 看日志
```

## 当前状态

**2026-05-17 · git init + 推 GitHub 完成 ✅** — 用户创建 `qiuridong/-web` 仓库后,PM 执行 `git init` + first commit(237 文件,hash `704b47f`)+ `git push -u origin main` 成功。新增 `项目说明.md`(~480 行,面向真人的中文说明)+ `.gitignore` 安全加固(补 `/backend/data/` 拦 encryption.key)+ Obsidian 笔记 `D:\dd\deom\签到聚合\项目-签到管家.md`。详见 [`变更/2026-05-17-git-init-与项目说明文档.md`](变更/2026-05-17-git-init-与项目说明文档.md)。

**2026-05-17 PM · 用户授权后续 3 件事**:(1)修 audit High 剩 7 项(opus agent 后台跑中,本机改 + verify,不部署)/ (2)用户名 admin 保持不变,密码用户已自改强密码 ✅ / (3)Web 脚本管理 MVP-5(**用户澄清后重新定义**:主功能 = **上传现成脚本目录/zip 到 scripts/ 自动入库**,次要 = 在线小修单文件;**不是** Monaco 全套 IDE)。设计稿已重写 [设计/Web脚本编辑器.md](设计/Web脚本编辑器.md),用 react-dropzone 上传 + CodeMirror 轻编辑器(总 bundle 增量 ~200KB),实施约 50 分钟(并行)。用户并行去抓包第二个签到脚本(候选 B 站 / V2EX 等)。

**2026-05-17 晚 · 🎉 多合一里程碑 N=2 + audit High 部署上线** — (1)PTFans 第二个真签到脚本完成并入库,opus agent 分析 3.1MB HAR 写 5 文件 + dry-run 3/3 过(NexusPHP 纯 GET `/attendance.php`,唯一 cookie `c_secure_pass` 1+ 年有效,无 turnstile)/ (2)audit High 7 项加固一并部署(节省一次 docker rebuild)/ (3)生产 smoke test 全绿:`/health` 200 / `/openapi.json` **404**(#9 生效)/ order 参数 401(#13 通过校验被 auth 拦)/ (4)修了我自己写错的协议文档 `项目说明.md § 3.3`:脚本协议是 `run(config, context) -> RunResult` 函数模型,**不是**裸 stdin/stdout(已纠正)。详见 [变更/2026-05-17-PTFans脚本+audit部署.md](变更/2026-05-17-PTFans脚本+audit部署.md)。

**2026-05-17 深夜 · 前端 abort 错误 toast 静默 hotfix(v1 + v2 两轮)** — v1 修 `client.ts onError` 过滤 5 种 abort 错误(hash `index-JmCKC6a4.js`)。用户反馈"abort 还经常出现,做任何修改都有可能" → v2 发现 `query-client.ts` 的 `QueryClient.defaultOptions.mutations.onError` 是**第二层 toast 入口**(任何 useMutation 错误都落这,所有"修改"操作都触发),v1 完全漏了。v2 抽 `isAbortError()` 通用判定,在 `query-client.ts` 三处用上(mutations.onError + queries.retry),`client.ts` v1 逻辑保留作双层兜底 → 新 hash **`index-CP_QytwL.js`** → scp dist 替换。**用户下一步**:Ctrl+F5 硬刷新拿 `CP_QytwL` 验证彻底静默 → 去 `/scripts/ptfans` 实例 Tab 点"立即运行"。详见 [变更/2026-05-17-前端abort错误toast静默-hotfix.md](变更/2026-05-17-前端abort错误toast静默-hotfix.md)(末尾 v2 段)。**遗留 UX bug**:实例 name 必填但表单没 client-side 提示,后端 422 也没把字段错误抽出来显示(只显示通用"未知错误"),下次修。**教训**:做全局错误处理 fix,必须 grep 所有 `toast.error` + `onError` 入口,不能只看一个 middleware 就收手。

**MVP-4 已上线** — 在 2026-05-16 后段部署到生产,137 后端断言全过 + coklw 真签到走通。

**⏸ 2026-05-16 · 今日暂停**(用户休息,明天继续)。完整接手单文件:[`变更/2026-05-16-今日暂停-MVP3-Hotfix-MVP4进行中.md`](变更/2026-05-16-今日暂停-MVP3-Hotfix-MVP4进行中.md)。

**MVP-3 已生产上线** → **https://jb.aijiaxia.cc**(最新 JS hash `index-BIPAwks0.js`,含 AppLayout CSS Grid 重构 + 品牌可点切换 + ThemeProvider 防扩展冲突修复 + 多轮 hotfix)。

- ✅ MVP-1 / MVP-2 / MVP-3 后端 **238 断言全过** + 实例 CRUD + Fernet 加密 + sandbox 子进程 + SSE 实时日志 + apprise 通知 + dashboard 真接入 + executor → dispatch_run_event 通知闭环
- ✅ 前端 13 chunks 拆分(主 bundle 240KB)+ /instances + /runs 全局页 + cron-parser + react-colorful 主题色 + LogViewer 主题热刷 + ⌘K 命令面板 + RouteErrorBoundary 兜底
- ✅ **代码审计完成**(50 issue:3 Critical / 12 High / 21 Medium / 14 Low),详见 [`变更/2026-05-16-代码审计报告.md`](变更/2026-05-16-代码审计报告.md)
- ✅ **AppLayout 彻底重构成纯 CSS Grid 2 列**(2026-05-16,放弃 shadcn SidebarProvider/Sidebar/SidebarInset 14 组件)。**真根因**:用户精准观察"PC 端遮挡,手机端不遮挡"→ shadcn sidebar peer div 是 `block` 没 flex-shrink-0,在 PC flex 布局里被 SidebarInset(flex-1)挤到 0 宽度,fixed 显示 div 浮在主内容上 z-10 overlay → CSS Grid `gridTemplateColumns: 240px 1fr` 强制列宽不被挤,彻底根治。手机端原本反而正常因为 hidden md:block 让 sidebar display:none + Sheet 弹出后关闭即正常
- 🔄 **MVP-4 backend fix agent 后台跑中**:audit Critical#1(子进程沙箱密钥隔离)+ #2(cancel_run 真杀子进程)+ High #4 #5 #6 #11(next_run_at 回写 / dashboard 含 script_name / runs N+1 / disable_script 同步 scheduler)

> **Hotfix**(2026-05-16):用户报 `/dashboard` 顶级 `.map(undefined)` 崩溃 → 根因后端 dashboard.overview 缺 mock 用的 sparkline_7d_*/notifications_24h/next_run_at 字段 → 前端 `useDashboardOverview` + `useDashboardTimeline` 加 adapter 补缺字段 + 兼容真后端 `{items}` 包装 → 重 build dist + rsync 上传 → 生产 `index-CNOKxb6D.js` 已上线 ✓
>
> **MVP-3 进行中**:2 个 opus agent 后台并行 — **3A 后端**(dashboard schema 真补全 sparkline 等 + executor 接 dispatch_run_event 让通知真发,目前正写 `_verify_mvp3_a.py` 自验)+ **3B 前端**(`/instances` `/runs` 全局列表页 + cron-parser 升级 CronInput + react-colorful 主题色 picker + LogViewer 主题热刷 + vite manualChunks 拆 vendor)
>
> **教训已落 ADR-014**:Dashboard `.map(undefined)` 崩根因是 agent 间契约不对齐(6B 后端 schema vs 6C 前端 mock 假设)。新规则:派 agent 前 PM 必须 grep 上游真实符号名,回来后做"字段归属表"review。当前 in-flight 已确认 1 个 prompt 小瑕(`get_apprise_pool` 实际是 `get_pool` — 但 agent 跑 `_verify_*` ImportError 会自修)。

> 期间已修一个 UI bug:`frontend/src/hooks/use-mobile.tsx` 把 `MOBILE_BREAKPOINT` 从 shadcn 默认 768 改为 480 — 桌面窗口缩小到 480-1280px 不再被误判为 mobile(原行为是侧栏 Sheet 覆盖主内容,现在是 push 让位)。
> 6B 顺手把 `_verify_e2e.py` 升级为 **idempotent** — 多次重跑都过(setup OR login 二选一,setup 后会自动用 admin/admin1234,绕过"DB 残留导致 409"问题)。

**MVP-1 已生产上线** → **https://jb.aijiaxia.cc**(11 项自测全绿,本节往下是 MVP-1 状态留档)。

- ✅ 后端 11/11 e2e + 前端 pnpm build + Claude Preview 本机闭环全过
- ✅ 部署架构:**复用 host nginx + certbot**(因服务器已有 nginx 在服务其它站点,不能停)+ docker 跑 backend 绑 127.0.0.1:8000
- ✅ certbot 已签 Let's Encrypt 证书,HTTPS 工作中;主密钥已生成在 `/opt/signin-panel/data/encryption.key`(**待异地备份 P0**)
- ✅ 11 项生产 curl 自测全绿:setup→login→scan(找到 coklw)→list→detail / CSRF 403 / 安全 header 全在 / SPA + assets 200
- ⏳ MVP-2 待做:实例 CRUD + 调度引擎 + sandbox runner + SSE 日志 + apprise 通知 + dashboard API 真接入
- 详见 [`变更/2026-05-16-MVP-1上线.md`](变更/2026-05-16-MVP-1上线.md)

- ✅ Phase 0(详细设计):后端架构 / 前端 UI 设计 / 技术调研 三份 markdown 落地
- ✅ 批次 1A(部署层 5 文件)+ 1B(后端配置 3 文件)+ 部署目标登记 + 全局 CLAUDE.md "默认 opus" 偏好
- ✅ 批次 1C 后端骨架(88 文件)— `TestClient(app)` lifespan OK / `/health` 200 / `/openapi.json` 200
- ✅ 批次 1D 前端骨架(35 文件)— `pnpm install` ✓ / `pnpm build` ✓ 1.9s(dist 299KB JS + 26KB CSS + 12 字体 woff2)
- ✅ coklw 签到脚本(5 文件)— `python main.py` 空 cookie dry-run 优雅返回 RunResult JSON / exit 1
- ⏸ **批次 2(3 个 opus agent)已派出但 TaskStop**:Backend-Models / Backend-Auth / Backend-Plugins
  - 从 stop 时 agent 摘要看,**已有部分文件落盘**:
    - Backend-Models:8 张表模型可能已写完(它当时在 debug `backend/data/` 目录不存在导致 alembic 失败的小问题 — 建一下目录或改 settings 默认值即可)
    - Backend-Auth:在写 API 路由 / middleware 的中途
    - Backend-Plugins:在写 scanner.py 的中途
  - **下次接手第一步:`ls backend/app/db/models/ backend/app/services/ backend/app/api/v1/` 看实际落盘情况**,决定是"补完缺的"还是"重派"

- ✅ 用户需求确认:Ubuntu 24 全自建、UI 美化、多 agent 协作开发
- ✅ 技术选型锁定(后端 + 前端 + 部署)
- ✅ 后端详细架构出稿([设计/后端架构.md](设计/后端架构.md))
- ✅ 前端 UI/UX 详细设计出稿([设计/前端UI设计.md](设计/前端UI设计.md))
- ✅ 关键技术点调研完毕([设计/技术调研.md](设计/技术调研.md))
- 🔄 下一步:bootstrap 项目骨架(backend/ + frontend/ + docker-compose + Caddyfile)

## 环境与命令

> 待项目骨架建好后填充。规划如下:

| 用途 | 命令 |
|---|---|
| 起开发栈(host) | `docker compose -f docker-compose.dev.yml up -d` |
| 后端单独跑 | `cd backend && uv run uvicorn app.main:app --reload --port 8000 --workers 1` |
| 前端单独跑 | `cd frontend && pnpm dev` |
| 后端测试 | `cd backend && uv run pytest` |
| 前端测试 | `cd frontend && pnpm test`(Vitest) |
| 前端类型生成 | `cd frontend && pnpm gen:api`(从 backend OpenAPI 拉) |
| 加 shadcn 组件 | `cd frontend && pnpm dlx shadcn@latest add <component>` |
| 数据库迁移 | `cd backend && uv run alembic upgrade head` |
| 生产部署 | `docker compose up -d --build` |

## 复用决策(自写轮子登记)

| 项 | 选择 | 理由 |
|---|---|---|
| 调度 | **APScheduler 3.11**(库) | 不自己写 cron 引擎;4.x alpha 风险大 |
| 通知 | **apprise**(库) | 一库覆盖 80+ 渠道,不重复造 |
| 鉴权 | 手写 session + bcrypt | 单用户场景,FastAPI Users 过度设计 |
| 加密 | **cryptography.Fernet**(库) | 不自己拼 AES |
| OpenAPI → TS 类型 | **openapi-typescript**(库) | 不手抄类型 |
| 前端 UI 基底 | **shadcn/ui**(copy-paste 源码到本仓库) | 不锁版本依赖,完全可定制;美化天花板 |
| 前端表单 | **react-hook-form + zod**(库) | 性能 + 类型安全,不手写校验 |
| 前端状态 | **Zustand**(全局) + **TanStack Query 5**(服务端缓存) | 不写 Redux 模板;TQ 处理 loading/error 一站式 |
| 前端模板 | `pnpm create vite + shadcn init`,从 cal.com / shadcn examples 偷思路 | 不 fork starter,体量小自己装可控 |

## 禁区

| 项 | 颜色 | 原因 |
|---|---|---|
| `data/encryption.key` | 🔴 禁止入 git / 入镜像 / 入日志 | 主密钥泄露 = 所有加密配置作废 |
| uvicorn `--workers > 1` | 🔴 必须 1 | APScheduler 同进程模式,多 worker 会重复触发任务 |
| `secret` 字段进 GET 响应 | 🔴 禁止 | API 响应必须自动脱敏为 `null` + `_secret_set` |
| 删除 `scripts/<slug>/` 磁盘文件 | 🟡 谨慎 | DELETE 接口只删 DB 行,**不动磁盘** |
| 在 `runs.stdout/stderr` 字段塞超大日志 | 🟡 谨慎 | 各 256 KiB 上限,超出截断 |

## 活跃分支

| 分支 | 状态 | 文件 |
|---|---|---|
| `main` | 🔄 设计完成,等开干 | [分支/main.md](分支/main.md) |

## 重大变更(新→旧)

| 日期 | 标题 | 文件 |
|---|---|---|
| 2026-05-17 | **前端 abort 错误 toast 静默 hotfix**(`client.ts onError` 漏过滤 AbortError 导致用户被红色误导)+ dist 替换 `index-JmCKC6a4.js` | [变更/2026-05-17-前端abort错误toast静默-hotfix.md](变更/2026-05-17-前端abort错误toast静默-hotfix.md) |
| 2026-05-17 | 🎉 **PTFans 真签到脚本上线**(多合一 N=2,NexusPHP)+ **audit High 7 项加固一并部署**,生产 smoke 全绿 | [变更/2026-05-17-PTFans脚本+audit部署.md](变更/2026-05-17-PTFans脚本+audit部署.md) |
| 2026-05-17 | audit High 7 项加固本机完成 + 178 断言全过(已部署见上条) | [变更/2026-05-17-audit-High-7项加固.md](变更/2026-05-17-audit-High-7项加固.md) |
| 2026-05-17 | 🎉 **git init + 推 GitHub 完成**(`qiuridong/-web`,237 文件)+ 项目说明.md + .gitignore 安全加固 + Obsidian 笔记 | [变更/2026-05-17-git-init-与项目说明文档.md](变更/2026-05-17-git-init-与项目说明文档.md) |
| 2026-05-16 | **MVP-3A · dashboard 4 字段补齐 + executor→dispatcher 通知闭环**(本机 25 新增断言全过,合计 103) | [变更/2026-05-16-MVP-3A通知闭环.md](变更/2026-05-16-MVP-3A通知闭环.md) |
| 2026-05-16 | 🎉🎉 **MVP-2 生产上线**(实例 CRUD + 调度 + sandbox + SSE + 通知 + 完整 UI · 135 断言全过 + 生产端到端 verified)| [变更/2026-05-16-MVP-2上线.md](变更/2026-05-16-MVP-2上线.md) |
| 2026-05-16 | 🎉 **MVP-1 生产上线** https://jb.aijiaxia.cc(11/11 自测全绿) | [变更/2026-05-16-MVP-1上线.md](变更/2026-05-16-MVP-1上线.md) |
| 2026-05-16 | **部署目标确定**(jb.aijiaxia.cc / 154.9.238.144 / 原计划 Caddy → 实际复用 nginx) | [变更/2026-05-16-部署目标确定.md](变更/2026-05-16-部署目标确定.md) |
| 2026-05-15 | **切换前端栈到 React**(替换 Vue 3) | [变更/2026-05-15-切换前端栈到React.md](变更/2026-05-15-切换前端栈到React.md) |
| 2026-05-15 | 项目立项与详细设计完成 | [变更/2026-05-15-项目立项与详细设计.md](变更/2026-05-15-项目立项与详细设计.md) |

## 关键决策(ADR-lite)

详见 [决策.md](决策.md)。摘要:

- **后端语言**:Python(签到脚本几乎都是 Python,同语言执行最丝滑)
- **调度模式**:同进程 AsyncIOScheduler,uvicorn `--workers 1`
- **脚本执行**:子进程 + JSON over stdio + 进程组超时强杀
- **存储**:SQLite WAL 模式,业务库与 scheduler jobstore 分两个文件
- **加密**:Fernet 字段级,主密钥 `data/encryption.key`,文件权限 600
- **鉴权**:Server-side session + HttpOnly Cookie(不用 JWT)
- **前端 UI**:React 18 + shadcn/ui + Tailwind v4 + Recharts + Framer Motion,深色模式一等公民,Linear/Vercel 同款基底
- **反代**:Caddy 2(自动 HTTPS,反代 SSE 默认正确)
- **部署**:Docker Compose 三服务(caddy + backend + frontend dist)

## 详细设计文档

| 文档 | 内容 |
|---|---|
| [设计/后端架构.md](设计/后端架构.md) | 数据模型 / API 路由 / 插件接口 / 调度引擎 / 安全加密 / 目录结构 / 异常体系 |
| [设计/前端UI设计.md](设计/前端UI设计.md) | **React + shadcn/ui** 版:视觉风格 / 配色(OKLCH CSS vars)/ 字体 / 页面 wireframe / 组件清单 / 美化关键手法 / Tailwind v4 配置 |
| [设计/前端UI设计-旧Vue版.md](设计/前端UI设计-旧Vue版.md) | (历史)Vue + Element Plus 版,设计语言相同,仅技术栈不同 |
| [设计/技术调研.md](设计/技术调研.md) | APScheduler/子进程/apprise/Vue 脚手架/SSE/Docker/加密 七大主题最佳实践 |
| [设计/Web脚本编辑器.md](设计/Web脚本编辑器.md) | **MVP-5 主功能** · Monaco 在线编辑器写 manifest + main.py + sandbox dry-run 校验(2026-05-17 设计完成,待开工) |

## 未决项 / Blockers

| 项 | 备注 |
|---|---|
| 第一个 demo 签到脚本选什么? | ✅ 已完成 `coklw`(生产真签到走通);下一个候选 bilibili-daily 验证标准通用性 |
| 域名与 HTTPS 配置 | 待用户提供生产域名;开发阶段用 localhost |

## 交接备忘(给下一个 AI / 协作者)

> 30 秒读完,你就能继续干活。

1. **现在卡在哪**:后端 11/11 绿,批次 5 三 opus 前端 agent(5A 布局+鉴权页 / 5B 仪表盘 / 5C 脚本列表+详情)后台并行跑。等通知 → 集成 `pnpm build` → Claude Preview 本机闭环 → 部署 jb.aijiaxia.cc → 自测。可能要修 `components/common/` 共享区 agent 冲突(EmptyState/PageHeader/StatusBadge/ScriptCard 可能被多个 agent 同时写)。
2. **上一步做了什么**(2026-05-16):
   - 派出并完成 3 个 opus agent:Plan(React UI 设计稿)/ general-purpose(1C 后端骨架 88 文件)/ opus(coklw 脚本,分析 3.3MB HAR)
   - 派出并完成 1 个 opus agent(末尾 403 限流但文件全落盘):1D 前端骨架 35 文件
   - **手工 review verified**:
     - 后端:`python -m uv venv --python 3.12`(注意!**uv 必须用 `python -m uv` 调,直接 `uv` 找不到**)→ `uv pip install --python .venv/Scripts/python.exe -e ".[dev]"` → `TestClient(app)` 跑 `/health` 200 + `/openapi.json` 200
     - 前端:`pnpm install` ✓ → `pnpm build` ✓(1.9s,dist 299KB JS + 26KB CSS + Inter/JetBrainsMono 字体 self-hosted woff2)
     - coklw:`python main.py` 空 cookie → 优雅打印 ERROR + 返回 RunResult JSON + exit 1
   - **修了一个小 bug**:`frontend/src/api/client.ts` 的 openapi-fetch `onError` 返回类型不对(返回 unknown),改为 `Promise<void>`(只 sniff,不替换错误)
   - 派出批次 2 三个 opus agent,但**用户休息前主动 TaskStop**(避免完成时打扰)
3. **下一步要做什么**(用户回来直接做):
   - **重派批次 2 三个 opus agent**(prompt 还在对话历史里 / 也可参照 [分支/main.md](分支/main.md) "批次 2"段重写):
     - Backend-Models:8 张表 SQLAlchemy 2.x 模型 + Alembic 0001 迁移
     - Backend-Auth:auth_service + auth API 6 端点 + AuthMiddleware + CSRFMiddleware + ErrorHandler
     - Backend-Plugins:manifest 解析 + 字段类型 + scripts 扫描 + scripts API 6 端点
   - 批次 2 完成 → 集成 review(端到端 TestClient:setup→login→scan→list scripts)
   - 批次 5:Frontend-Auth-Pages + Frontend-Dashboard + Frontend-Scripts-List 三个前端页面 agent(并行)
   - 集成 + 部署到 jb.aijiaxia.cc(scp + ssh + docker compose up)
   - **估计到 MVP-1 上线还需 25-35 分钟**(假设 agent 都顺利,不再 403 限流)
4. **重要约束**(违反就回炉):
   - 阅读 `设计/后端架构.md` § 3、4、5 后再写后端代码
   - 阅读 `设计/前端UI设计.md` § 1、3 后再写前端组件
   - 前端栈是 **React 18 + shadcn/ui + Tailwind v4**(Vue 版已废弃)
   - uvicorn 必须 `--workers 1`,docker-compose 与 Dockerfile 都已固化
   - `data/encryption.key` 已在 `.gitignore`,**绝不**解除
   - 派 Agent 默认 opus(全局 CLAUDE.md 已固化)
   - **uv 调用陷阱**:`uv` 不在 PATH(以 module 装的),必须 `python -m uv ...`;venv 路径要显式 `--python .venv/Scripts/python.exe`,否则装到系统 Python
5. **可直接复用的命令**:
   - 跑后端:`cd backend && .venv\Scripts\python.exe -m uvicorn app.main:app --port 8000 --workers 1`
   - 跑前端:`cd frontend && pnpm dev`(http://localhost:5173,proxy /api → 8000)
   - 后端测试:`cd backend && .venv\Scripts\python.exe -m pytest`(目前 conftest 占位,无实际用例)
   - 后端 e2e:`cd backend && PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe _verify_e2e.py`(TestClient 跑 11 断言)
   - alembic 应用迁移:`cd backend && .venv/Scripts/python.exe -m alembic upgrade head`(注:alembic.ini 必须纯 ASCII,中文注释会让 Python 3.12 + Windows GBK locale 报 UnicodeDecodeError)
   - 重置 DB:`cd backend && rm -f data/db.sqlite3 && .venv/Scripts/python.exe -m alembic upgrade head`
   - 前端 build:`cd frontend && pnpm build`(产物 dist/ 给 Caddy serve)
   - coklw dry-run:`cd scripts\coklw && COKLW_DELAY=0 COKLW_COOKIE="" PYTHONIOENCODING=utf-8 ..\..\backend\.venv\Scripts\python.exe main.py`

## 自测矩阵(用户硬要求 — 完成后我必须自动跑)

**本机阶段**:
- `_verify_e2e.py` 11/11 绿
- `Claude Preview` (`preview_start` `preview_click` `preview_fill` `preview_screenshot`) 真浏览器走闭环:setup→登录→仪表盘→脚本列表→coklw 详情→创建实例→手动 run
- 每个页面截图存档,对照设计稿调性(克制/现代/精致)review

**生产阶段(部署到 jb.aijiaxia.cc 后)**:
- `curl -I https://jb.aijiaxia.cc/health` → 200
- `Claude Preview` 开 `https://jb.aijiaxia.cc` 重复一遍闭环 + 截图
- `ssh root@154.9.238.144 'docker compose logs --tail=50 backend'` 看无 ERROR
- 验证 Caddy 拿到 Let's Encrypt 证书(无 ACME 报错)

### 临时探测脚本说明
集成 review 期间 `backend/` 根目录下会出现 `_verify_e2e.py` / `_probe_*.py` 等本地工具,**`.gitignore` 已排除**。正式 smoke test 待 MVP-2 整理到 `backend/tests/smoke/` 入 git。
5. **快速找东西**:
   - 数据模型表结构 → `设计/后端架构.md` § 1
   - API 路由清单 → `设计/后端架构.md` § 2
   - manifest.yaml 格式 → `设计/后端架构.md` § 3.1
   - 配色/字号/圆角 token → `设计/前端UI设计.md` § 1.2-1.7
   - 页面 wireframe → `设计/前端UI设计.md` § 3
   - APScheduler 集成代码 → `设计/技术调研.md` § 1
   - 子进程超时强杀 → `设计/技术调研.md` § 2
   - Caddyfile 范例 → `设计/技术调研.md` § 6.4
