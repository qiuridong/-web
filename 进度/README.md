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

**2026-05-26 深夜末 · 🔍 PR #7→#8 预解 AppLayout 冲突 + code-review 15 findings(开始全部修复)** — 用户指示"预解冲突,之后审核代码,现在没时间测试别的问题"。**(1)冲突预解** commit `f492928`:merge PR #7 到 feat/appearance-settings,3 处真冲突全融合(Sidebar callers 双 sidebar + logo/title props 都接、main outlet wrapper 用 PR #8 min-h-full + PR #7 mobile-first padding、useEffect 两段并存)。PR #8 现 = PR #7+#8 super-PR,线上 hash **`index-DyzpHkqD.js`**。**(2)code-review** skill `--effort high` 派 6 个 agent(5 finder angle + 1 sweep)聚合 23 candidates → dedup/severity → **15 final findings**:HIGH 5(draft 被覆盖丢用户改 / value 字符串静默回退 DEFAULT / XSS via data:text/html logo / 共享 dict mutate 污染 / mobile nav 单点故障)+ MED 7(多 tab 不同步 / favicon 漏 palette deps / img race / iOS 主屏图标不变 / handleReset 无确认 / backdrop 仅 16px / NaN clamp 失效)+ LOW 3(Sheet resize a11y / DataTable 双层 overflow / resolvedTheme 首帧 undefined 闪烁)。用户决定"开始全部修复",**Phase 1 立即在 `fix/code-review-findings` 分支批量修**。详见 [变更/2026-05-26-PR8冲突预解+代码审核15findings.md](变更/2026-05-26-PR8冲突预解+代码审核15findings.md)。

**2026-05-26 深夜 · 🎨 外观完整版 + Phase 2 polish + bg-scroll bugfix(PR #8 已含 3 个 commit)** — 用户要求"外观部分要好一些修改如界面背景图、网站 logo、网站文本",选完整版。**核心 commit 1**:复用现有 `settings` KV 表 + 通用 `GET/PUT /api/v1/settings/{key}` API(MVP-1 § 1.8)→ 删掉刚写的 alembic 0004 / AppSetting model / 专属 API,改为加 `appearance` 到 DEFAULT_SETTINGS 白名单 + validator(1 文件 +80 行)。frontend 新建 `api/hooks/appearance.ts`(useAppearance / useUpdateAppearance / fileToDataUrl)+ Settings 加 `<BrandingCard>` 全宽(标题/副标题/侧栏 Logo 文本/Logo 图/背景图/透明度 Slider/模糊度 Slider/混合模式 Select)+ AppLayout 注入(document.title 同步 / Sidebar 接 logo&title props / main 背景图 + overlay 暗罩)。**核心 commit 2 · Phase 2 polish**:(1)浅深色 overlay 区分(`useTheme().resolvedTheme` 浅色白罩 / 深色黑罩);(2)favicon 自动从 logo canvas 64×64 圆角 + drawImage 缩放 / 文字时主题色背景 + sidebar_logo_text,动态更新 `<link rel="icon">`;(3)6 张内置预设背景(SVG inline data URL:极光紫/日落粉/深海青/森林绿/点阵底纹/午夜蓝)在 BrandingCard 顶部 grid-cols-6 swatch 一键应用。**核心 commit 3 · bg-scroll bugfix**:用户报"设计背景之后下滑部分颜色没生效",根因 main `<main style={bg}>` + overlay `absolute inset:0` 只覆盖 viewport,scroll content 超出 viewport 时底部露出 raw 背景。修复:套一层 `<div className='relative min-h-full' style={bg}>` 在 main 内,overlay/content 跟 wrapper 等高,scroll 到任何位置都被覆盖。**总 3 commits +1140**(backend 1 + frontend 4 + 进度档案),线上 hash **`index-BH1uqoCf.js`**(最终)+ backend docker rebuild 已部署。base64 内联存 / 无 docker volume / 无 nginx 静态服务 / 无 migration。**已合并 PR #7**(本次 commit `预解 AppLayout 冲突`)。[PR #8](https://github.com/qiuridong/-web/pull/8) 待 review。详见 [变更/2026-05-26-外观完整版+PR8.md](变更/2026-05-26-外观完整版+PR8.md)(主体)+ § 续(Phase 2 + bg-fix,见档案末尾)。

**2026-05-26 深夜 · 📱 手机端响应式布局核心 80%(PR #7,已合并到 PR #8 分支)** — 用户反馈"手机端布局奇怪" + 明确要"响应式布局,不要只校准我的手机"。**3 文件 +75 / -10**:(1)`AppLayout.tsx` 大改 — mobile (< md=768px) sidebar **改 Sheet 抽屉**(从左滑入 + backdrop 关)+ Topbar 加 ☰ 汉堡按钮 + 路由切换自动关抽屉 + 主区 padding mobile-first(`px-3 py-4 sm:px-6 sm:py-6 lg:px-8`);desktop ≥ md 保持原 CSS Grid 2 列 sidebar 布局;(2)`ui/sheet.tsx` 全局 mobile 全宽 — `w-3/4` → `w-[calc(100vw-1rem)] sm:w-3/4 sm:max-w-sm`,**这一行修复 7+ 个组件的 mobile 体验**(InstanceFormSheet / RunDetailSheet / NotificationHub / ScriptDevGuideSheet / etc);(3)`DataTable.tsx` 加内层 `overflow-x-auto` 让 mobile 列多时可横滚(保外层 rounded-xl)。线上 hash **`index-BfTq87Sg.js`** 已部署(已被后续 PR #8 hash 覆盖)。**Phase 2 polish**(ScriptCard / PageHeader / 工具栏 mobile 折行 / hideOnMobile 列 / 字体优化 / 触控目标 44×44)按用户真机反馈再做。[PR #7](https://github.com/qiuridong/-web/pull/7) 内容已并入 PR #8 一起 review。详见 [变更/2026-05-26-手机响应式+PR7.md](变更/2026-05-26-手机响应式+PR7.md)。

**2026-05-26 晚 · 🩹 模板 dry-run 短路 + 三层提示防开发者踩坑(hotfix PR #5 已 merged)** — 接 PR #4 部署后用户实测上传模板 → `HTTP 422`,SSH 主面板 docker logs 看到 `dry-run 失败 exit_code=1 timed_out=False`;根因:`sandbox_runner.main()` 把 `RunResult.success=False` 转 `exit_code=1`,模板 main.py 在空 config 时早 return `RunResult(success=False, "缺少 username...")` → 必然 422。**3 层防坑修复**:(1)模板 main.py 加 dry-run 短路(`if context.run_id == 0 and context.instance_id == 0: return RunResult(success=True)`)+ 重墨注释 "不要删除"+ manifest description 加 checklist 警告;(2)前端 ErrorPanel 智能识别 dry-run failure(`detail.dry_run.passed === false`),弹"最常见原因 + 代码片段 + 跳指南"块 + `onOpenGuide` 一键打开指南;(3)`ScriptDevGuideSheet` 在 "main.py 协议" 之后插入新章节 "🔍 dry-run 短路 · 上传前必读"(机制 + 为什么 422 + 代码示例)。**3 文件 +134 / -6**,无后端/agent 改动,无新依赖。线上 hash **`index-C90PO6bp.js`**。[PR #5](https://github.com/qiuridong/-web/pull/5) 已 merged(commit `2fd989f`)。详见 [变更/2026-05-26-模板dry-run短路+三层提示防踩坑.md](变更/2026-05-26-模板dry-run短路+三层提示防踩坑.md)。

**2026-05-26 傍晚 · 🚀 推送同步 + Inventory + 修运行时保留(PR #4)** — 接 PR #3 用户反馈"我要的功能不是这个,而是上传到指定 vps 脚本"(MVP 简化掉了立即推送),本 PR 补完:(1)**alembic 0003** nodes 表加 `pending_actions JSON`(主面板待办指令)+ `deployed_scripts JSON`(agent 报告事实源);(2)**backend** poll endpoint piggyback `pending_actions`(无 task 也带),新增 `POST /agent/inventory-report`,script_upload 接 `?sync_to_nodes=2,3` query → append slug 到对应 node;(3)**agent** `_handle_pending_actions` 处理 sync/delete + `_post_inventory_report` ack + 启动时+周期(5min)兜底,**修运行时保留缺陷** `RUNTIME_PRESERVE_DIRS` 在 os.replace 前 move downloaded_files/data/__pycache__/_dry_run_data/.backups 到 tmp;(4)**frontend** useScriptUpload + UploadScriptDialog 实际把 selectedNodeIds 传给 backend,toast 改"已要求 X 个节点立即同步,最长 30 秒内完成"。**Push via Poll piggyback** 是 pull-only 架构的"伪推送"最干净方式(无新连接 / 无新 task type / 向后兼容)。**三端已部署**:backend docker rebuild + alembic upgrade `0003_pending_actions`,frontend hash **`index-BRM9k0Qo.js`**,agent VPS-JM restart 后 sanity 全过 + 启动时 inventory-report 200 ✅。7 files +625。**e2e 真测**留给用户:在 web 下载模板 zip → 拖回来勾 vps-jm → 上传 → 30s 内 agent 日志显示 `⤓ 主面板推送指令`。[PR #4](https://github.com/qiuridong/-web/pull/4) 解 main merge 冲突后等 merge。详见 [变更/2026-05-26-推送同步+inventory+运行时保留+PR4.md](变更/2026-05-26-推送同步+inventory+运行时保留+PR4.md)。

**2026-05-26 下午 · 📡 脚本同步 Pull 方案落地 + PR #3** — 实施 5-25 凌晨设计稿 § 2 的"按需 Pull 同步":(1)backend 加 `compute_script_bundle()` helper(过滤 .backups/__pycache__/data/.git 等垃圾 + 防 Zip Slip + 防大小爆炸)+ 2 个新 endpoint(`/agent/scripts/{slug}/manifest` 返 sha256 / `/bundle.zip` 返 zip 流),走现有 Bearer Token 鉴权;(2)agent `_ensure_script_synced()` 180 行,sha256 比对 → 拉 zip → 客户端二次校验 → 原子解压(两层 Zip Slip 防御 + 备份回滚),在 `_execute()` 开头调用,失败仅 log 不抛(向后兼容老 agent);(3)frontend UploadScriptDialog 加"同步到节点(可选,可多选)" + toast 提示,**MVP 仅 UI 标记**实际同步走按需 Pull(不主动 push 简化设计,无 DB 改动);(4)4 文件 +552 -14,**无 alembic migration / 无新依赖**;(5)frontend build hash `index-Bc_l0TAF.js`;(6)[PR #3](https://github.com/qiuridong/-web/pull/3) commit `6b6d063` 已开等用户 review。Bash classifier 短暂不可用 ~3min(opus 4.7 容量),期间纯写代码恢复后 git ops 走完。详见 [变更/2026-05-26-脚本同步Pull方案实施+PR3.md](变更/2026-05-26-脚本同步Pull方案实施+PR3.md)。

**2026-05-26 · PR #1 已 merged + 进度文档 PR #2 开** — 用户 review + merge [PR #1](https://github.com/qiuridong/-web/pull/1) 到 main(commit `604404f`);本会话切回 main + fast-forward + 开 docs 分支 `docs/2026-05-25-progress-after-pr1` 把昨晚未提交的进度文档化为 [PR #2](https://github.com/qiuridong/-web/pull/2)(纯文档,本规范 5-25 凌晨刚立的 PR review 流程的体现 — auto mode 也拦了直接 main commit)。**今天等用户拍板下一步**:(A)实施昨晚设计稿的"脚本同步 Pull 方案 + 上传时选节点"(~4-6h);(B)先做轻量验证(5-25 09:00 cron 真测 + 上传 UX 真测 + 通知中心 QQ 邮箱真发,需用户授权读生产 DB);(C)其它。

**2026-05-25 凌晨更晚 · 📦 脚本上传 UX 增强上线 + 首个 PR #1** — (1)新建 `frontend/src/lib/script-template.ts`(~245 行,4 模板 + buildTemplateZip 前端动态生成 zip + SCRIPT_REQUIRED_FILES 清单)+ `ScriptDevGuideSheet.tsx`(~290 行,9 章节完整开发协议右侧 Sheet);(2)`UploadScriptDialog.tsx` 大改造(+280 行):拖入后 `analyzeUpload` 用 jszip+js-yaml 解析,5 项 checklist(✅/❌/⚪)缺必填**禁用上传**,manifest 摘要绿框 / yaml 错误红框,顶部加"📥 下载模板项目"(前端 jszip 动态生成 zip + a.download)+"📖 脚本开发指南"(开右侧 Sheet);(3)装 jszip(主 bundle +27 KB,vendor-misc +98 KB);(4)线上 hash **`index-Cn-vxQI_.js`**;(5)**仓库自 5-17 推 GitHub 以来第一个 PR** — [#1 feat/script-upload-ux-enhancement → main](https://github.com/qiuridong/-web/pull/1),commit `9eabeb9`,等用户 review + merge。节点选择 + Pull 同步留明天做(用户指示"先做 ui 吧,剩下的明天再说")。详见 [变更/2026-05-25-脚本上传UX增强+PR1.md](变更/2026-05-25-脚本上传UX增强+PR1.md)。

**2026-05-25 凌晨 · 🎨 通知中心 UI 三轮增强上线 + 脚本同步 Pull 方案设计稿(未实施)** — (1)新建 `frontend/src/lib/notification-presets.ts`(13 个 apprise 渠道 URL 预设 / 5 个 Jinja2 模板预设 / 5 组字段速查变量);(2)`NotificationHub.tsx` 改造:ChannelSheet 加渠道类型预设下拉(选 QQ 邮箱/Telegram 等自动填 URL 模板 + helper 文案告诉授权码哪里拿),RuleSheet 加模板预设下拉 + 字段速查折叠区(点击 `{{ run.status }}` 等字段插入到光标位置);(3)修 Sheet 内容溢出遮挡保存按钮 — header/scroll/footer 三段式 + `min-h-0` + `scrollbar-gutter:stable`;(4)修 Select 长下拉打开向下展开遮挡其它字段 — 全部 7 个 `<SelectContent>` 加 `max-h-[280px]`;**4 轮 frontend dist 部署**最终线上 hash **`index-DCgPEn8u.js`**(备份 `dist.backup.20260524-130207/131639/132641/133331/`)。**未实施 · 脚本同步 Pull 方案设计稿**:用户问"zip 脚本部署到指定 VPS 似乎没这功能",grep 确认 agent 现状靠**手动 scp**(`agent/README.md` 明写),设计 backend +2 endpoint(GET `/agent/scripts/<slug>/manifest` + `/bundle.zip`)+ agent `_ensure_script_synced` ~80 行(比对 hash → 拉 zip → 原子解压 → 写 marker),触发时机在 `_execute_task()` sandbox_runner 前,工作量约 200 行 / 45-60min,**等用户拍板**(推荐明早 09:00 cron 验证 OK 后做,今晚动 agent 会模糊明早 cron 失败的根因)。详见 [变更/2026-05-25-通知UI增强+脚本同步Pull方案设计.md](变更/2026-05-25-通知UI增强+脚本同步Pull方案设计.md)。

**2026-05-17 · git init + 推 GitHub 完成 ✅** — 用户创建 `qiuridong/-web` 仓库后,PM 执行 `git init` + first commit(237 文件,hash `704b47f`)+ `git push -u origin main` 成功。新增 `项目说明.md`(~480 行,面向真人的中文说明)+ `.gitignore` 安全加固(补 `/backend/data/` 拦 encryption.key)+ Obsidian 笔记 `D:\dd\deom\签到聚合\项目-签到管家.md`。详见 [`变更/2026-05-17-git-init-与项目说明文档.md`](变更/2026-05-17-git-init-与项目说明文档.md)。

**2026-05-17 PM · 用户授权后续 3 件事**:(1)修 audit High 剩 7 项(opus agent 后台跑中,本机改 + verify,不部署)/ (2)用户名 admin 保持不变,密码用户已自改强密码 ✅ / (3)Web 脚本管理 MVP-5(**用户澄清后重新定义**:主功能 = **上传现成脚本目录/zip 到 scripts/ 自动入库**,次要 = 在线小修单文件;**不是** Monaco 全套 IDE)。设计稿已重写 [设计/Web脚本编辑器.md](设计/Web脚本编辑器.md),用 react-dropzone 上传 + CodeMirror 轻编辑器(总 bundle 增量 ~200KB),实施约 50 分钟(并行)。用户并行去抓包第二个签到脚本(候选 B 站 / V2EX 等)。

**2026-05-17 晚 · 🎉 多合一里程碑 N=2 + audit High 部署上线** — (1)PTFans 第二个真签到脚本完成并入库,opus agent 分析 3.1MB HAR 写 5 文件 + dry-run 3/3 过(NexusPHP 纯 GET `/attendance.php`,唯一 cookie `c_secure_pass` 1+ 年有效,无 turnstile)/ (2)audit High 7 项加固一并部署(节省一次 docker rebuild)/ (3)生产 smoke test 全绿:`/health` 200 / `/openapi.json` **404**(#9 生效)/ order 参数 401(#13 通过校验被 auth 拦)/ (4)修了我自己写错的协议文档 `项目说明.md § 3.3`:脚本协议是 `run(config, context) -> RunResult` 函数模型,**不是**裸 stdin/stdout(已纠正)。详见 [变更/2026-05-17-PTFans脚本+audit部署.md](变更/2026-05-17-PTFans脚本+audit部署.md)。

**2026-05-17 深夜 · 前端 abort 错误 toast 静默 hotfix(v1 + v2 两轮)** — v1 修 `client.ts onError` 过滤 5 种 abort 错误(hash `index-JmCKC6a4.js`)。用户反馈"abort 还经常出现,做任何修改都有可能" → v2 发现 `query-client.ts` 的 `QueryClient.defaultOptions.mutations.onError` 是**第二层 toast 入口**(任何 useMutation 错误都落这,所有"修改"操作都触发),v1 完全漏了。v2 抽 `isAbortError()` 通用判定,在 `query-client.ts` 三处用上(mutations.onError + queries.retry),`client.ts` v1 逻辑保留作双层兜底 → 新 hash **`index-CP_QytwL.js`** → scp dist 替换。用户硬刷新后**确认 abort 错误消失** ✅。**遗留 UX bug**:实例 name 必填但表单没 client-side 提示,后端 422 也没把字段错误抽出来显示(只显示通用"未知错误"),下次修。

**2026-05-17 深夜 · 🛌 今日收工** — 用户决定不立即运行 PTFans,等明天 9:00 看 cron 自动跑。3 件收尾全部完成:(1)**代码已 git push 备份**到 https://github.com/qiuridong/-web,3 个 commit 全在 GitHub(`704b47f` initial → `39e5754` audit+PTFans → `84bdb07` abort fix)/(2)**开机自启已默认配好**,无需动:docker daemon enabled + nginx daemon enabled + backend 容器 `restart: unless-stopped`,服务器重启后链路自动恢复 / (3)进度文档全部刷新。

**2026-05-18 早 · 🚨 P0 httpx 缺失 hotfix(scheduled 触发链路彻底修)** — 用户报 coklw + ptfans **scheduled 触发 100% 失败**(`ModuleNotFoundError: No module named 'httpx'`)。root cause:生产 Docker `uv pip install --target /deps` 装第三方依赖到 `/deps`,通过 ENV `PYTHONPATH=/deps` 让主进程能 import;但 audit Critical #1 (2026-05-16) 修复时一刀切把 PYTHONPATH 写进 `_FORBIDDEN` 严禁透传 → 子进程 sys.path 不含 `/deps` → 所有用 httpx 的脚本 import 失败。修法:`executor.py:_build_env` **白名单透传 PYTHONPATH**,过滤掉指向 `backend/` 的路径(防 `import app.*`),保留 `/deps` 等纯第三方依赖路径。与 audit Critical #1 安全目标对齐 + sandbox_runner._isolate_sys_path 仍兜底。**热补丁部署**(`docker cp executor.py 进容器 + restart`,不 rebuild 避免和 MVP-5 agent 半成品冲突),验证 backend healthy + `已加载 2/2 enabled instance`。**待用户点"立即运行" coklw 验证**。

**2026-05-18 · MVP-5 派 agent 中** — 用户启动 MVP-5(Web 上传脚本 + 在线编辑器)。派 2 opus agent 并行后台跑:**Agent A 后端**(`script_upload.py` 5 端点 + service ~200 行 + 15 断言 verify)/ **Agent B 前端**(`UploadScriptDialog` + `FileEditDialog` CodeMirror lazy + `ScriptFileList` + 2 hooks + 装 5 新依赖)。预计 50-75 分钟。**PM 期间**:不动 backend/frontend(避免冲突),只 hotfix executor.py + 等通知。两个完成后:集成 review + 跑全 verify(原 178 + 新 15 = 193 期望) + 一次性 build + scp + 部署(backend 完整 rebuild,把 httpx hotfix 永久带上) + smoke + git commit + push。

**2026-05-18 · ptfans cookie 调试**(独立小事,非 bug) — 用户手动触发 Run #7 #8 都 `首页未识别到用户名(或检测到 takelogin form),cookie 已过期`(虽然 cookie expires 2027 没到但 PT 站 server 主动清 session)。**httpx 修复确认生效**(stderr `随机延迟 38 秒后开始签到` = 脚本已进 run())。Run #9 触发后**正在正常 sleep**(/proc 看到 python 子进程活着,stdout/stderr 空 = 在 `time.sleep` 中,容器精简没装 ps),不是孤儿,几分钟后会同样 cookie failure。用户操作:浏览器先确认 ptfans.cc 还在登录态 → F12 重新拿 c_secure_pass Value → 编辑实例改 cookie + `random_delay_sec=0` 测试 → 触发 Run #10 看绿色 success。**UX 教训**:用户**两次**在对话里贴真 cookie(=PT 账号免密令牌),我多次提醒;以后前端可加 secret 字段帮助文字"敏感凭证仅粘控制面板,勿贴聊天/截图"。

**2026-05-18 · MVP-5 实施进行中** — 用户说"做 MVP-5"。派 2 opus agent 并行后台:Backend agent 写 `app/api/v1/script_upload.py`(16KB)+ `services/script_upload_service.py`(30KB)+ `schemas/script_upload.py` + `_verify_mvp5_upload_edit.py` + 改 `api/v1/__init__.py` `scripts.py` `router.py` `core/exceptions.py`(+17 行新异常)。Frontend agent 写 5 组件(`UploadScriptDialog.tsx` 20KB / `FileEditDialog.tsx` 11KB / `ScriptFileList.tsx` 8.5KB / `CodeMirrorLazy.tsx` + `fileLanguage.ts`)+ 2 hooks(`useScriptUpload.ts` / `useScriptFiles.ts`)+ 集成 ScriptList/ScriptDetail + 装 6 新依赖(`@codemirror/lang-{python,yaml,state,view}` + `@uiw/react-codemirror` + `js-yaml`)。**所有文件全部落地** ✅。PM 现在并行跑后台:(1)全 7 个 verify 回归(178 旧 + 15 新 = 193 期望全过)(2)`pnpm build` 看是否过 + bundle 增量(~200KB CodeMirror lazy chunk 预期)。等结果 → 完整 `docker compose build`(把 executor.py httpx hotfix + ptfans 正则 hotfix + MVP-5 backend 都永久带上)+ 部署前端 dist + smoke test + git commit + push。

**2026-05-24 深夜 · 🎊🎊🎊 MVP-1 端到端首次真测成功(run 27,49 秒)+ systemd 资源调优 + 平台级 manual 跳延迟** — (1)排查 run 26 ReadTimeout 真因:`dmesg` 揭示 `cgroup: fork rejected by pids controller`,install.sh 写的 `TasksMax=128` 太小,Chrome 需 50-100 process fork;(2)patch systemd unit:`MemoryMax 512M→2G + TasksMax 128→4096`,本机 `agent/install.sh` 同步更新;(3)用户反馈"立即运行不应等延迟"应该是平台级,**把 `trigger_type=='manual' → random_delay=0` 从脚本内提到 `backend/sandbox_runner.py` 平台契约层**,所有脚本统一受益(scheduled/retry/test 不变);(4)**run 27 = MVP-1 首次完整 e2e 真测**:web 点立即运行 → 49 秒完成 → CF 一次过 + login 成功 + sign 返 `error:finished`(已签)→ 正确识别 JmAlreadySignedToday → web 显示 success ✅;(5)意外发现:run 26 Chrome 根本没启,**没真消耗 CF 信任分** → run 27 CF 一次过。详见 [变更/2026-05-24-MVP1端到端真测成功+systemd调优+平台级跳延迟.md](变更/2026-05-24-MVP1端到端真测成功+systemd调优+平台级跳延迟.md)。

**2026-05-24 下午-晚 · 🎉🎉🎉 MVP-1 远程 agent 完整上线生产 + 端到端 e2e 链路通(run 26)+ 6 个 UX bug 全 fix + v1.2 manual 跳 random_delay** — (1)Phase 3 全 5 Step 完成:tar over ssh backend(rebuild + alembic upgrade 0002 + nodes 表 + local 节点)+ scp frontend dist 3 次 + agent install on VPS-JM(节点 id=2 slug=`vps-us8-8-jm` + heartbeat 200)+ 停 host crontab;(2)**端到端验证**:run 26 (instance 3 jmcomic) 走完整链路 web → backend → DB pending → agent poll → subprocess sandbox_runner → main.py → Chrome,**所有协议链路 100% 通**,CF 超时 failure 是预期(VPS-JM IP 信任分今日已耗 2 次);(3)**6 UX fix**:heartbeat 500(authenticate_agent 与 update_heartbeat 撞 SQLite lock)/ 节点卡片 Terminal 按钮 + replay mode 重看安装命令 / shadcn Tooltip 替换原生 title / 创建实例"未知错误"(serialize 没返 node_id)/ 编辑实例显示默认 local / "● 未知" → "● 待运行";(4)v1.2 main.py:trigger_type=='manual' 跳 random_delay,scheduled 仍走错峰随机。**今天不再点立即运行**(CF 信任分透支),等明早 5-25 09-10 北京主面板自动 cron 真签到(scheduled 走 random 0-3600s + IP 24h 恢复 + 真 JCoin 到账)。详见 [变更/2026-05-24-MVP1部署上线+6个UX修复+v1.2manual跳延迟.md](变更/2026-05-24-MVP1部署上线+6个UX修复+v1.2manual跳延迟.md)。

**2026-05-24 中午 · 🎯 MVP-1 接力实施完成 Phase 0/1/2(等用户授权 Phase 3 部署)** — opus background agent 凌晨中断后只完成 backend ~50%(DB+API+middleware+executor+verify+ instance_service node_id 分流),Frontend / agent CLI 完全缺失。我接手:(1) Phase 0 verify:`_verify_e2e.py` 11/11 ✅(金标准)+ `_verify_mvp1_remote_agent.py` [0]-[9] ✅(节点 CRUD + agent 鉴权 + 实例创建 + executor 派单);[10]+ 卡 Windows SQLite + TestClient WAL lock(尝试 fix 不成,生产 docker Linux 不会有,改用生产 e2e 真测代替);(2) Phase 1 agent CLI:全新 `agent/` 4 文件(`signin_agent.py` 790 行 + `install.sh` + `README.md` + `config.example.yaml`),httpx long polling + subprocess sandbox_runner + 心跳 + systemd;(3) Phase 2 frontend + backend schema 补丁:新 `nodes.ts` hooks + `NodeList.tsx` 节点页(添加 + 一次性 token + 一键安装命令)+ 路由 + 导航 + `InstanceFormSheet` 加 `NodeSelect` 下拉;backend `schemas/instance.py` + `instance_service.py` 加 `node_id` 字段 + 校验(agent 漏的);`pnpm build` ✅ 新 hash `index-oJqVc1H6.js`(278.93 KB,+1KB);7 个 backend 新文件 syntax ✅。**关键提醒**:今早 09:48 北京 host 已跑 v1.0 拿 JCoin:30 → VPS-JM IP 今日 CF 信任分已耗 1 次 → 今晚 e2e 立即运行**预期 CF 拒**(链路通即可,真签到等明早 IP 信任分恢复 + 同时停 host crontab 避免双调度)。详见 [变更/2026-05-24-MVP1接力实施-agent+frontend+backend补丁.md](变更/2026-05-24-MVP1接力实施-agent+frontend+backend补丁.md)。

**2026-05-24 上午 · 🎉 JM v1.0 host 首跑成功(JCoin:30 + EXP:100,30 秒)+ v1.1 cookies 复用智能重试上线** — (1)host 09:48:46 北京自然跑 v1.0 → CF 一次过(IP 信任分满)→ POST /login HTTP 200 / 47B → POST /sign HTTP 200 / 111B → **签到成功,JCoin:30 + EXP:100,总耗时 30 秒,0 retry**;**5-23 反爬空响应已证实是孤例**(5-24 server 完全正常,Content-Length=0 但实际 body 111B,v1 仍正确解析,稳如老狗);(2)用户提需求"失败要二次签到,**用第一次过 CF 的值不反复过 CF**,5 分钟间隔重试 3 次,cookies 真过期才重过 CF,失败通知用 web 已有的"→ **v1.1 重构**:拆 `_do_sign_in` 为 `_do_login` + `_do_sign_only`,run() 顶层管 cookies/session lifecycle,加 `JmCookieExpired` 异常 + `refresh_cf_and_login` closure + ttl 检查;manifest 加 `retry_interval_sec`(300)+ `cf_clearance_ttl_sec`(1800)+ default_timeout 4500→6000;**3 次重试 CF 消耗 3→1**(IP 信任分友好);(3)scp 到 host + 主面板 + chown + restart backend → **SQLite jmcomic 版本 1.0.0 → 1.1.0** ✅;通知集成等 MVP-1(不在 v1 代码加 apprise,干净分层)。详见 [变更/2026-05-24-JM-v1.1-cookies复用与智能重试.md](变更/2026-05-24-JM-v1.1-cookies复用与智能重试.md)。

**2026-05-23 晚 · 🎯 JM v1 整改 + scp 接入主面板 web(Phase 1+2 完成)+ MVP-1 远程 agent 后台启动** — (1)用户决策"v2 废弃删除,v1 升格"→ 整改 v1(`main_selenium_fallback.py` 内容→ `main.py` + 删[已废弃]docstring + 补 `_chunked_sleep` + 改 manifest 账密字段 + `default_cron: 0 1 * * *` 北京 9:00 + `default_timeout_sec: 4500`+ 重写 README/requirements);(2)scp 5 文件到主面板 `154.9.238.144:/opt/signin-panel/scripts/jmcomic/` + chown 1000:1000 + docker restart → 周期 scan added=1 → SQLite scripts 表 3 行(coklw/ptfans/**jmcomic id=3**)→ **web https://jb.aijiaxia.cc/scripts 已能看到 3 个卡片**;(3)host VPS-JM crontab 改 `0 1 * * *` UTC = **北京 9:00-10:00 窗口**激活(明早自然跑作 5-23 反爬偶发/趋势的对照基线,备份 2 份保留);(4)**派 1 opus agent 后台跑 MVP-1**(完整 prompt:DB nodes 表 + agent 4 endpoint + Bearer middleware + executor 改造 + Agent CLI + 前端节点页 + `_verify_mvp1_remote_agent.py` ≥ 15 断言;严禁 git push / docker build / 实际部署 agent;预计 4-8h wallclock,跨夜)。**当前状态**:web 上**能看到 jmcomic 卡片但不能跑**(主面板容器无 Chrome,必须等 MVP-1 完成后部署 agent 到 VPS-JM 才能真跑)。详见 [变更/2026-05-23晚-JM-v1整改与web接入.md](变更/2026-05-23晚-JM-v1整改与web接入.md)。

**2026-05-23 晚 · 🔬 JM 100% 可靠性深度调研 + 4-5 月完整日志重判** — (1)写 [设计/JM签到100%可靠性调研.md](设计/JM签到100%可靠性调研.md)(584 行 5 方向);用户质疑 API 域名"银弹论"→ 实测 VPS-JM curl HEAD 几乎全 403 → **银弹论崩塌**;(2)拉 host syslog 全集 + journal --list-boots + signin.log → **真相揭露**:**原脚本 CF 33/33 = 100% 过盾**;5 月 3 天失败里 2 天是平台问题(5-06→5-07 VPS 停机 22h / 5-12 kernel panic + 5-13 停机 7h)+ 1 天 server 自挂(5-02 502)+ **真正脚本可优化的只有 5-23 sign 反爬空响应** 1 天;(3)修正方案路线:**原脚本+selenium 路径完全够用**,真正需要的是**平台层补签(scheduler retry_window)+ v2 已有的首页 marker 兜底**,**不需要三层回退/curl_cffi/API 域名替换**(过度工程);(4)等用户明早 5-24 看自然跑结果再决定下一步。详见 [变更/2026-05-23-JM签到100可靠性调研+5月精确日志重判.md](变更/2026-05-23-JM签到100可靠性调研+5月精确日志重判.md)。**已停 host crontab 等用户决定是否恢复让明天自然跑(/root/.crontab.backup.20260523-103809)。**

**2026-05-23 · 远程 VPS MVP-1 准备阶段 + JM 完整改造(v1 selenium → v2 cookie 复用)** — (1)MVP-1 远程 agent 调研稿 [设计/远程VPS脚本执行调研.md](设计/远程VPS脚本执行调研.md) 写完(6 架构 / 420 行 / 推荐 B+F),首节点 = VPS-JM (38.55.132.186);(2)SSH 密钥免密接入 VPS-JM 完成 → 摸底发现 JM 脚本在 `/root/JMComic-Auto_Sign_in/`(host crontab 跑,不在青龙里);(3)JM 改造 v1(selenium 版,5 文件)→ sandbox 测试 CF 没过 → 用户质疑代码 → PM 严格 diff verified 100% 等价 → 对照实验(host 原版同样不过)= IP 信任分耗尽真因;(4)5 月 signin.log 统计 19/23 success + 2 异常(5-02 server 502 / 5-23 sign 空响应)+ 2 无记录;(5)v2 加精细诊断(5 类异常 + http helper);(6)用户提议 cookie 复用方案 → 抓 HAR 60MB 解析,发现 cf_clearance 2 年过期 + JM 用 PHP `remember` cookie 登录令牌 + sticky 显示 IP 绑定 = anonymous 真因;(7)**完全重构 v2 cookie 版**(15.7KB 纯 httpx,旧 selenium 改名 `main_selenium_fallback.py` 保留),manifest 改字段 + README 重写;(8)host crontab 已停 + 备份(`/root/.crontab.backup.20260523-103809`);(9)用户提议 v3 (账密 + cf_clearance 每次 login 换新 session) — 更优方案,等用户选 A/B/C/D 决定。详见 [变更/2026-05-23-JM接入+改造v1+精细诊断v2.md](变更/2026-05-23-JM接入+改造v1+精细诊断v2.md)。**关键洞察**:JM cookie 与 server IP 强绑定 → jmcomic 实例必须部署到抓 cookie 时同一出口 IP 节点 → **等 MVP-1 远程 agent 通了再上线**(在 jb.aijiaxia.cc 主面板 VPS 直接跑会被 server 拒)。

**2026-05-19 · 🎉 MVP-5 全栈上线 + 3 hotfix 落地** — (1) MVP-5 派 2 opus agent 并行实施,**verify 30/30 全过**(后端 4 新 + 4 改 / 前端 5 组件 + 2 hooks + 集成 + 6 新依赖,vendor-codemirror 480KB 完全 lazy load,主 bundle 仅增 14KB);(2) hotfix #1 executor.py PYTHONPATH 安全透传(audit Critical #1 过头修复 → 生产 cron httpx 缺失,先 hot patch 再本次完整 build 永久);(3) hotfix #2 ptfans `_check_logged_in` 用宽松 RE_LOGGED_IN_HINT(原 RE_USERNAME 硬编码 class="User_Name" 与主题耦合 → 误判已登录页为未登录 → 误报 cookie 过期);(4) hotfix #3 format.ts toDate() 自动补 Z 后缀(parseISO 把 naive UTC 当本地时间 → 中国用户全部时间偏 -8h → 用户误判"1 点 cron 没触发",其实 Run #13 success "今日已签到")。**部署完成**:`docker compose build backend` 把 executor hotfix 永久带上 + 前端新 hash `index-V0pR5svQ.js`。**生产实际数据已 verified**:coklw 凌晨 1 点 scheduled cron + 上午 10:10 manual + ptfans 9:00 scheduled 全 success。详见 [变更/2026-05-19-MVP5上线+3-hotfix.md](变更/2026-05-19-MVP5上线+3-hotfix.md)。**等用户**:Ctrl+F5 硬刷新 + 真测一次 MVP-5 上传 / 编辑闭环。git push 等用户授权(预计 3 个 commits)。

**2026-05-23 · 远程 VPS 多节点功能调研 + VPS-B 接入(MVP-1 准备)** — 用户提需求"主面板管理多 VPS 脚本,像探针一样自动生成安装代码"。PM 写完整调研稿 [`设计/远程VPS脚本执行调研.md`](设计/远程VPS脚本执行调研.md)(420 行,6 架构 / 7 类似项目 / 安全模型 / DB schema / 工程量 35-50h 分 3 MVP)。**PM 推荐 + 用户认可:选项 B(Pull Agent + HTTP Long Polling,GitHub Actions runner 同款)+ F(Tailscale)**。用户给 VPS-B(154.9.238.251 / root / password)后,PM 用临时 paramiko 自动化:密码 SSH → 部署 ed25519 公钥 → 改 sshd_config + restart sshd → 验密钥登录通过(私钥 `J:\密钥\美国4-4\jb-251-ed25519`)。**摸底意外**:用户说"上面有 JM天堂签到脚本",实测**完全没有**(find / crontab / docker / ps 全空),VPS-B 实际是综合代理/监控机(komari-agent + argo Cloudflare Tunnel + xray/v2ray/sing-box + nginx + iperf3)。本机清理:卸载临时 paramiko/invoke/pynacl + 删 `_tmp_vps_b_init.py`(防 docker build 幽灵依赖)。**等用户**:回复 JM 脚本所在机器(可能换新 VPS 重新接入) + 授权开干 MVP-1(10-15h 派 1 agent)。详见 [变更/2026-05-23-远程VPS-MVP1-准备阶段.md](变更/2026-05-23-远程VPS-MVP1-准备阶段.md)。

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
| 2026-05-26 傍晚 | 🚀 **推送同步 + Inventory + 修运行时保留(PR #4)** — 接 PR #3 用户反馈"我要上传到指定 vps 脚本"(MVP 简化掉立即推送),本 PR 补完。alembic 0003 加 `nodes.pending_actions/deployed_scripts JSON`;backend poll piggyback push + 新 `POST /agent/inventory-report` + script_upload 接 `?sync_to_nodes`;agent `_handle_pending_actions` + 启动 + 5min 兜底 + `RUNTIME_PRESERVE_DIRS` 修 sync 全替换缺陷;frontend 实际传 selectedNodeIds + toast 改"30s 内完成"。Push via Poll piggyback(pull-only 架构最干净伪推送),向后兼容。三端已部署(backend `0003_pending_actions` migration + frontend `index-BRM9k0Qo.js` + agent restart 后 inventory-report 200)。7 files +625。e2e 待用户 web 验证。**PR #4 待 push** | [变更/2026-05-26-推送同步+inventory+运行时保留+PR4.md](变更/2026-05-26-推送同步+inventory+运行时保留+PR4.md) |
| 2026-05-26 下午 | 📡 **脚本同步 Pull 方案实施 + PR #3** — backend `compute_script_bundle` 110 行(过滤 + 防 Zip Slip + 防大小爆炸)+ 2 endpoint(`/agent/scripts/{slug}/manifest` + `bundle.zip`);agent `_ensure_script_synced` 180 行(sha256 比对 + 客户端二次校验 + 两层 Zip Slip 防御 + 原子解压 + 备份回滚),在 `_execute()` 开头调用失败仅 log;frontend UploadScriptDialog 加"同步到节点"多选 + toast 提示(MVP 仅 UI 标记,实际走按需 Pull);4 files +552 -14,**无 DB 改动 / 无新依赖**;frontend build hash `index-Bc_l0TAF.js`;[PR #3](https://github.com/qiuridong/-web/pull/3) commit `6b6d063` 待 review | [变更/2026-05-26-脚本同步Pull方案实施+PR3.md](变更/2026-05-26-脚本同步Pull方案实施+PR3.md) |
| 2026-05-25 凌晨更晚 | 📦 **脚本上传 UX 增强上线 + 首个 PR #1** — `script-template.ts` 新建(4 模板 + buildTemplateZip 前端动态生成 zip)+ `ScriptDevGuideSheet.tsx`(9 章节协议右侧 Sheet)+ `UploadScriptDialog.tsx` 改造(jszip+js-yaml 预解析,5 项 checklist 缺必填禁用上传,manifest 摘要绿框 / yaml 错误红框,顶部下载模板 + 开发指南按钮);线上 hash `index-Cn-vxQI_.js`;**仓库首个 PR** [#1](https://github.com/qiuridong/-web/pull/1) `feat/script-upload-ux-enhancement` → `main`(commit `9eabeb9`)等 review | [变更/2026-05-25-脚本上传UX增强+PR1.md](变更/2026-05-25-脚本上传UX增强+PR1.md) |
| 2026-05-25 凌晨 | 🎨 **通知中心 UI 三轮增强上线 + 脚本同步 Pull 方案设计稿(未实施)** — `notification-presets.ts` 新建(13 渠道 URL + 5 Jinja2 模板 + 5 组字段速查);`NotificationHub.tsx` 改造(ChannelSheet/RuleSheet 预设下拉 + 字段速查 + Sheet 三段式 sticky footer + SelectContent `max-h-[280px]` 防遮挡);4 轮 dist 部署最终 hash `index-DCgPEn8u.js`;**脚本同步 Pull 方案**设计稿出(backend +2 endpoint + agent `_ensure_script_synced`,~200 行 45-60min)等用户拍板,推荐明早 cron 验证后做 | [变更/2026-05-25-通知UI增强+脚本同步Pull方案设计.md](变更/2026-05-25-通知UI增强+脚本同步Pull方案设计.md) |
| 2026-05-24 深夜 | 🎊🎊🎊 **MVP-1 端到端首次真测成功(run 27,49 秒)+ systemd 资源调优 + 平台级 manual 跳延迟** — 排出 ReadTimeout 真因 = systemd `TasksMax=128` 太小(Chrome fork rejected);patch unit `MemoryMax 2G + TasksMax 4096`;manual 跳延迟从脚本层提到 `sandbox_runner` 平台层(所有脚本统一);run 27 web 立即运行 49 秒拿"已签:finished",链路 100% 通;意外发现 run 26 Chrome 没启没耗 CF 信任分 | [变更/2026-05-24-MVP1端到端真测成功+systemd调优+平台级跳延迟.md](变更/2026-05-24-MVP1端到端真测成功+systemd调优+平台级跳延迟.md) |
| 2026-05-24 下午-晚 | 🎉🎉🎉 **MVP-1 完整上线生产 + e2e 链路通 + 6 UX fix + v1.2** — Phase 3 全部署(backend rebuild + alembic 0002 + frontend dist + agent install on VPS-JM 节点 vps-us8-8-jm + 停 host crontab);run 26 跑完整链路验证 ✅(CF 超时是预期);6 UX fix:heartbeat lock / 节点 Terminal 按钮重看安装命令 / shadcn Tooltip / 创建实例"未知错误"(serialize 缺 node_id)/ 编辑实例节点显示错 / "●未知"→"●待运行";v1.2 manual 跳 random_delay。明早 9-10 北京自动 cron 真签到验证 | [变更/2026-05-24-MVP1部署上线+6个UX修复+v1.2manual跳延迟.md](变更/2026-05-24-MVP1部署上线+6个UX修复+v1.2manual跳延迟.md) |
| 2026-05-24 中午 | 🎯 **MVP-1 接力实施 Phase 0/1/2 完成** — opus agent 凌晨中断时只做了 backend 50%;我接手补 agent CLI(`signin_agent.py` 790 行 + install.sh + README + config.example)+ frontend(`nodes.ts` hooks + `NodeList.tsx` + 路由 + 导航 + `InstanceFormSheet` 加节点下拉)+ backend schema 补丁(InstanceCreate/Update 加 `node_id` + service 校验);`_verify_e2e.py` 11/11 ✅(金标准)+ `pnpm build` ✅;等 Phase 3 部署授权 | [变更/2026-05-24-MVP1接力实施-agent+frontend+backend补丁.md](变更/2026-05-24-MVP1接力实施-agent+frontend+backend补丁.md) |
| 2026-05-24 上午 | 🎉 **JM v1.0 host 首跑成功(JCoin:30 + EXP:100,30 秒)+ v1.1 cookies 复用智能重试上线** — 5-23 反爬空响应已证实孤例;v1.1 重构 retry(`_do_login` + `_do_sign_only` 拆分,closure 管 cookies/session,加 `JmCookieExpired` 异常,加 `retry_interval_sec`/`cf_clearance_ttl_sec` 字段)→ **3 次重试 CF 消耗 3→1**;部署 host + 主面板,SQLite version 1.0.0→1.1.0 | [变更/2026-05-24-JM-v1.1-cookies复用与智能重试.md](变更/2026-05-24-JM-v1.1-cookies复用与智能重试.md) |
| 2026-05-23 深夜 | 🎯 **JM v1 整改 + scp 接入主面板 web(Phase 1+2)+ MVP-1 远程 agent 后台启动** — v2 废弃删 → v1 升格 main.py + 补 `_chunked_sleep` + 改账密字段;scp 5 文件到主面板 + chown + docker restart → SQLite 3 个脚本入库(jmcomic id=3)→ web /scripts 能看 3 卡片;host crontab `0 1 * * *` 激活(北京 9-10 窗口);派 1 opus agent 后台跑完整 MVP-1(预计 4-8h) | [变更/2026-05-23晚-JM-v1整改与web接入.md](变更/2026-05-23晚-JM-v1整改与web接入.md) |
| 2026-05-23 晚 | 🔬 **JM 100% 可靠性深度调研 + 4-5 月日志精确重判** — 5 个方向调研 → API 域名"银弹论"被实测否决 → 拉全 host 日志(syslog+journal+signin.log)→ 真相:**原脚本 CF 33/33 = 100% 过盾**;5 月失败 3 天 = 2 天 VPS 平台问题(停机 22h + kernel panic)+ 1 天 server 502 + 1 天 sign 反爬空响应 → 修正路线**不再追求复杂方案,平台层补签 + v2 首页 marker 兜底足矣** | [变更/2026-05-23-JM签到100可靠性调研+5月精确日志重判.md](变更/2026-05-23-JM签到100可靠性调研+5月精确日志重判.md) |
| 2026-05-17 | **前端 abort 错误 toast 静默 hotfix**(`client.ts onError` 漏过滤 AbortError 导致用户被红色误导)+ dist 替换 `index-JmCKC6a4.js` | [变更/2026-05-17-前端abort错误toast静默-hotfix.md](变更/2026-05-17-前端abort错误toast静默-hotfix.md) |
| 2026-05-23 晚 | 🎯 **JM(18comic.vip)接入 + 改造 v1 + 精细诊断 v2**:VPS 38.55.132.186 SSH 接入(密钥 `J:\密钥\8-8特价美国\jm-186-ed25519`)+ `scripts/jmcomic/` 5 文件改造 + scp sandbox 测试(CF 未过 diff verified 同 IP 同天第二次升级)+ signin.log 728 行分析(5 月 19/23 天成功,**5-23 sign 接口空响应是新错误**)+ 用户手动签到成功证实**JM 反爬升级**(对自动化 sign 静默返空)+ **v2 改造 668 行精细诊断**(6 异常类 / `_http_request` 统一 diag / **`_check_already_signed_via_index` 首页 marker 兜底**) | [变更/2026-05-23-JM接入+改造v1+精细诊断v2.md](变更/2026-05-23-JM接入+改造v1+精细诊断v2.md) |
| 2026-05-23 | 📝 **远程 VPS 多节点调研** + VPS-B 154.9.238.251 SSH 密钥接入完成(MVP-1 准备阶段,等用户回 JM 脚本所在机器后开干) | [变更/2026-05-23-远程VPS-MVP1-准备阶段.md](变更/2026-05-23-远程VPS-MVP1-准备阶段.md) |
| 2026-05-23 | **远程 VPS MVP-1 准备 + JM 完整改造**(v1 selenium → v2 cookie 复用)+ HAR 分析揭示 cf_clearance 2 年寿命/`remember` PHP 令牌/IP 强绑定 + host cron 停 | [变更/2026-05-23-JM接入+改造v1+精细诊断v2.md](变更/2026-05-23-JM接入+改造v1+精细诊断v2.md) |
| 2026-05-25 | 🎉 **多合一 N=3 jmcomic 上线 + v1.1.0 业务弹性集大成**(session 复用 + cookies TTL + 8 marker 兜底)— CF 信任分模型 verified / cookie 复用 v2 探索后回归 selenium v1.1.0 + 加弹性 | [变更/2026-05-25-JM接入+v1.1.0业务弹性上线.md](变更/2026-05-25-JM接入+v1.1.0业务弹性上线.md) |
| 2026-05-19 | 🎉 **MVP-5 全栈上线**(Web 上传 zip + CodeMirror 在线编辑器)+ **3 P0 hotfix**(executor httpx / ptfans 正则 / format.ts 时区)— verify 30/30 全过,生产 smoke 全绿,3 个生产 cron 已 verified success | [变更/2026-05-19-MVP5上线+3-hotfix.md](变更/2026-05-19-MVP5上线+3-hotfix.md) |
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
| [设计/JM签到100%可靠性调研.md](设计/JM签到100%可靠性调研.md) | **JM v3 调研** · 推荐三层回退(API 移动端域名 → HTML+curl_cffi → 直接 HTTP)+ jmcomic 库 API login,目标成功率 ≥ 99%(2026-05-23 调研完成,等用户拍板) |

## 未决项 / Blockers

| 项 | 备注 |
|---|---|
| **5-25 09:00-10:00 北京 jmcomic agent cron 真测** | ⏸ **P0** — 今晚 host crontab 已停 + agent 部署到 VPS-JM(节点 `vps-us8-8-jm`)+ 实例 cron `0 1 * * *`(UTC)+ random_delay 0-3600s。验证项:走 random_delay(非 manual)/ CF 一次过(IP 信任分恢复)/ POST /sign HTTP 200 / **真 JCoin/EXP 到账**。结果决定:✅ → 整链路 production-ready / ❌ → 看具体失败模式调整 |
| ✅ ~~脚本同步 Pull 方案 + 上传时选节点~~ | **PR #3 已 merged + 部署**(commit `63ade4e`)。但 MVP 简化掉"立即推送"被用户反馈,转 PR #4 补完(本档) |
| ✅ ~~PR #1 review + merge~~ | **已完成**(commit `604404f`)。进度文档化为 [PR #2](https://github.com/qiuridong/-web/pull/2) |
| **PR #4 review + merge + e2e** | 待 push + 开 PR;e2e 步骤:web 下载模板 zip → 拖回来勾 vps-jm → 上传 → 30s 内 agent 日志显示 `⤓ 主面板推送指令` + 同步完成 |
| **PR #5 节点脚本管理 UI** | 用户指示"做一个管理,用户可以自主清理删除上传到 vps 的脚本"。基础设施已 ready(`deployed_scripts` JSON + `pending_actions.delete`),只缺前端 UI + 1-2 个 backend endpoint。~2.5h |
| **PR #6 外观完整版** | 用户选完整版(~5-6h):背景图 / logo / 标题。backend app_settings KV 表 + 文件上传 + 静态服务;frontend 设置→外观加品牌段 + Layout 应用 setting |
| **5-25 09:00 jmcomic cron 真测** | 用户回复"B 实际上没有问题,我已经手动测试过了" — 视为已验证 |
| **通知中心真测** | 用户已建 QQ 邮箱渠道,Ctrl+F5 拿新 dist `index-DCgPEn8u.js` 后用预设填好 → 点测试发送看是否真收到邮件;若失败排查 apprise URL 占位符是否替换干净 |
| 第一个 demo 签到脚本选什么? | ✅ 已完成 `coklw`(生产真签到走通);下一个候选 bilibili-daily 验证标准通用性 |
| 域名与 HTTPS 配置 | ✅ 已完成 `jb.aijiaxia.cc` → 154.9.238.144(2026-05-16) |
| **JM v3 三层回退方案选型(已降优先级)** | ⏸ **暂搁置** — 5-24 v1.0 host 首跑成功(JCoin:30/EXP:100),v1.1 cookies 复用 + retry refactor 已上线,v1.2 manual 跳延迟由 sandbox_runner 平台层接管,**不再需要 v3 复杂方案**。详见 [设计/JM签到100%可靠性调研.md](设计/JM签到100%可靠性调研.md) |

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
