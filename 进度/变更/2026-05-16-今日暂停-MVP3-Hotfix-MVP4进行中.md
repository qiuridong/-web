---
name: 2026-05-16 · 今日暂停(MVP-3 上线 + Hotfix + MVP-4 进行中)
description: 用户结束今天工作前的完整收尾;明天接手只读本文件就能继续
type: change
---

# 2026-05-16 · 今日暂停 ⏸

## 30 秒接手摘要(明天读这段就够)

1. **生产已稳定上线** https://jb.aijiaxia.cc — admin/`admin1234ABC`(用户可能在浏览器改过,以浏览器为准)
2. 最新 JS hash:**`index-BIPAwks0.js`**(含侧栏 CSS Grid 重构 + 品牌区可点击 toggle + ThemeProvider 去 disableTransitionOnChange + ScriptCard 跳详情 + 各种 .map 防御)
3. **明天第一件事**:让用户**用 PC 无痕模式**打开生产测一次改密页 → 确认 `insertBefore Failed` 是不是浏览器扩展(Dark Reader / Grammarly / Microsoft Editor / 沉浸式翻译之类)导致的
4. **MVP-4 backend fix agent 被 TaskStop**(audit Critical/High 6 项)— 还没完成 + 没部署;需要重派或继续
5. **coklw 实例配置帮用户改**:让用户去 `/scripts/coklw` 实例 Tab 改 prod-empty-test 的 `timeout_sec=3900` 或 `random_delay_sec=0`(否则签到必超时)

## 完成的工作(今天主要进展)

### MVP-3 全部上线
- **MVP-3A 后端**:dashboard schema 补 sparkline_7d_*/notifications_24h/next_run_at 4 字段;executor 真调 dispatch_run_event 推通知;**103 断言全过 + apprise 路径 verified**
- **MVP-3B 前端**:`/instances` `/runs` 全局列表页;cron-parser 5.x;react-colorful 主题色 picker;LogViewer 主题热刷;vite manualChunks 拆 13 chunks(主 bundle 2095KB→252KB,降 88%);⌘K 命令面板
- 部署到 https://jb.aijiaxia.cc 经验证

### 代码综合审计
- opus agent 出报告:`进度/变更/2026-05-16-代码审计报告.md`
- **50 issue**:3 Critical + 12 High + 21 Medium + 14 Low
- 评级:架构 A / 安全 C+ / 性能 B / UX B+ / 工程化 C+

### 多轮 Hotfix(本会话内做的)
1. Dashboard 顶级 `.map(undefined)` 崩 → useDashboardOverview/Timeline 加 adapter 补缺字段 + 兼容 `{items}` 包装
2. nginx index.html 加 `Cache-Control: no-cache`(根治浏览器缓存老 dist)
3. nginx 路由错乱 + 证书串站 → deploy/nginx 贴定完整配置(含 80→443 redirect + 443 ssl http2 + 显式 ssl_certificate 路径),不再依赖 certbot --nginx 二次改
4. **AppLayout 彻底重构成纯 CSS Grid 2 列**(`gridTemplateColumns: 240px 1fr`)— 抛弃 shadcn SidebarProvider/Sidebar/SidebarInset 14 组件;**真根因**:用户精准观察"PC 端遮挡,手机端不遮挡" → shadcn sidebar peer div 没 flex-shrink-0 在 PC flex 容器被 SidebarInset(flex-1)挤到 0 宽度,fixed div overlay 主内容
5. **侧栏品牌区可点击 toggle**(点 logo 或"签到管家"切折叠/展开)— 删 Topbar 重复的 toggle 按钮,UX 更自然
6. Dashboard + ScriptList 的 ScriptCard `onRun` 占位 toast → 改成 `navigate('/scripts/<slug>?tab=instances')` 跳详情让用户选 instance
7. 加 `<RouteErrorBoundary>` 全局兜底(以后 React 崩友好降级而非白屏)
8. index.html 加 `<meta name="google" content="notranslate">` + body/root `translate="no"` 阻止翻译扩展改 DOM
9. **去掉 next-themes `disableTransitionOnChange`**(怀疑是 PC 端 `insertBefore Failed` 真凶 — 它注入 head `<style>` 与 Dark Reader 等扩展冲突)
10. coklw 脚本:`default_timeout_sec` 从 120 改 3900(覆盖 1 小时随机延迟 + 5 分钟签到余量)+ main.py 加 sanity check(`if delay > timeout - 60: cap delay + warn`)

### MVP-4 backend fix agent(已 stop,**未完成**)
派 opus 跑 audit Critical+High 6 项,**已 TaskStop**(用户休息),从 agent 输出看:
- Critical #1 子进程沙箱密钥隔离 — **已写新文件 `backend/sandbox_runner.py`**(独立 Python 文件,不在 app/ 树下)
- Critical #2 cancel_run 真杀 — **改了 `backend/app/scheduler/executor.py`**(具体修法待 review)
- High #4 #5 #6 #11 — 未确认
- 新建 `backend/_verify_mvp4_audit_fixes.py` — 待跑测验证

**stop 前 agent 最后一句**:"用户约束说不动进度文档,让我删掉它" — 它可能尝试改了某个进度文件,需要 review;但应该没污染设计稿(它只看,不改)

## 待用户做(明天回来 5 步)

### 1. 测改密 `insertBefore` 是不是扩展(关键)
**PC 无痕模式**打开 https://jb.aijiaxia.cc → 登录 → /settings/account → 改密码走一遍

- 无痕**不崩** → 是浏览器扩展(关 Dark Reader / Grammarly / Microsoft Editor / 沉浸式翻译/任何动 DOM 的扩展)
- 无痕**还崩** → 是代码 race,需要我深入查 commitMutationEffects stack

### 2. 调 coklw 实例避免超时
浏览器 → `/scripts/coklw` → 实例 Tab → 编辑 `prod-empty-test`:
- 把 **timeout(秒)从 60 改到 3900**(覆盖 1 小时随机延迟 + 余量)
- 或者把 **random_delay_sec 改到 0**(立即跑测试)
- 二选一,然后保存
- 点"立即运行"验证

### 3. 浏览器拿最新 dist
**Ctrl+Shift+R** 硬刷新 → 拿 `index-BIPAwks0.js`(含侧栏品牌可点击 + ThemeProvider 修复)

### 4. 改强密码(P0 待办)
`/settings/account` 改密码(当前 `admin1234ABC` 太弱)

### 5. 给 coklw 填真 cookie(用户上次粘的 cookie 已过期或失效请重新拿)
浏览器登录 https://coklw.net/ → F12 → Application → Cookies → `wordpress_logged_in_*` + `wordpress_sec_*` 粘到 cookie 字段

## 明天 PM(我)接手要做的

按优先级:

### P0(必须做)
1. **完成 MVP-4 backend fix**:重派 opus agent(prompt 见本会话历史 或 audit 报告 Critical/High 段),让它接着改 sandbox_runner.py + executor.py + 跑 4 个 verify(应当 100+ 断言全过)
2. **部署 MVP-4 backend 到生产**:rsync + docker compose build + restart + 生产验证(curl + 触发实例 + 看 logs)

### P1(基于用户无痕测结果决定)
3. 如果无痕也崩 → 深入查 `commitMutationEffects` 真凶(可能是某个 Radix Portal 或 next-themes 残留)
4. 如果无痕不崩 → 加 `MutationObserver` 在 root 监听外部 DOM 修改 + 用户文档建议关哪些扩展

### P2(MVP-5 候选)
5. 处理 audit 报告 High #7 #8 #9 #10 #12 #13 #14 #15(7 项 — `/openapi.json` 生产无鉴权 / cron PATCH 预校验 / scheduler 503 误报 / RunsFilter.order 静默失效 / dispatcher tie-break 文档 / backup/import 假成功 等)
6. Medium 21 / Low 14 按需

## 后台任务状态(全停)

| Agent / Task | 状态 |
|---|---|
| MVP-4 backend fix opus agent | ⏸ TaskStop(部分文件已落:sandbox_runner.py / executor.py 改 / _verify_mvp4_audit_fixes.py 新)|

## 关键文件(明天接手 grep 路径)

- 主入口:`进度/README.md`(本变更对应"当前状态"段已加 ⏸ 标记)
- audit 报告:`进度/变更/2026-05-16-代码审计报告.md`(360 行,Critical/High/Medium/Low 4 段)
- 已确定但未处理的部分修复(在生产已部署的最新代码):本文件 § 完成的工作 列出
- coklw 脚本:`scripts/coklw/manifest.yaml`(default_timeout=3900) + `main.py`(sanity check)
- 前端 AppLayout:`frontend/src/components/layout/AppLayout.tsx`(CSS Grid 2 列 + 品牌区可点 toggle)
- 后端待 review(MVP-4 agent 写一半):`backend/sandbox_runner.py` 新增 / `backend/app/scheduler/executor.py` 改

## ⚠️ 风险与隐患

- **MVP-4 agent 改了 backend 但未跑 verify** — 重启后可能崩(尤其 executor.py 改 cancel_run 后);**部署前必须本机 TestClient 跑 11+10+57+25 = 103 断言全过再上线**
- **本机 backend uvicorn 没在跑**(之前 Bash 后台 timeout 退了);明天重启需要 `cd backend && .venv/Scripts/python.exe -m uvicorn app.main:app --port 8000 --workers 1`
- 生产 backend 仍是 MVP-3 版本(MVP-4 改动未部署)— 生产稳定,无需紧急动
