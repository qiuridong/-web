---
name: feat/ui-fullbg-mobile-runcancel 分支进度
description: 全屏壁纸背景统一 + 手机端响应式收尾 + 运行取消 + 删除脚本(两会话并行)
type: project
---

# 分支:feat/ui-fullbg-mobile-runcancel

## 目标

一批前端体验改进。分支名拆开 = **full-bg + mobile + run-cancel**,实际涵盖 4 件:

1. **全屏壁纸背景统一** — 外观功能(PR #8)的背景图只铺在 `<main>` 内容区,侧栏/顶栏仍是纯色 `bg-card`/`bg-background`,视觉割裂。目标:壁纸铺满整个 app shell(侧栏 + 顶栏 + 内容统一),侧栏/顶栏改半透明毛玻璃让壁纸透出。
2. **手机端响应式收尾** — 含「手机端访问最右边大片白块」(疑似溢出 / 未铺背景);Phase 2 polish(ScriptCard / 工具栏折行 / 44×44 触控)。
3. **运行取消** — 取消「等待执行 / 执行中」的 run(后端 `cancel_run` 早有,缺前端入口)。
4. **删除已上传脚本** — 用户自主清理上传到 VPS 的脚本(基础设施 `deployed_scripts` / `pending_actions.delete` 已就绪;GitHub PR #6 `fix/script-list-delete-with-files` 仍 OPEN)。

## 分工(两会话并行,共享同一工作树 `E:\签到脚本多合一`)

- **本会话(接手前端体验)**:#1 壁纸背景统一 + #2 手机端(含右侧白块)。
- **另一会话**:#3 运行取消 + #4 删除脚本。⚠️ 本会话不碰。

> ⚠️ **协作风险**:两 Claude 会话同一工作树,未提交改动互相可见。#1 和 #3 都可能改 `AppLayout.tsx`(顶栏加取消入口?),有覆盖风险。开工前需用户确认边界(见 README「当前状态」A/B/C)。

## 最近迭代

- 2026-05-30 · **接手 + 进度核实** — 分支从 main@`9bfaaa9` 切出(= main,无新 commit)。工作树有**未提交 WIP**:`frontend/src/components/layout/AppLayout.tsx`(+41/−31,另一会话)= **已实现 #1 壁纸统一雏形**:Sidebar 加 `translucent` prop(半透明 `bg-card/65` + `backdrop-blur-xl`);背景图从 `<main>` 内层上提到**根容器**(整个 shell `h-screen overflow-hidden` → 等效 viewport 固定背景);overlay 改 `absolute inset:0 z-0` 铺满 shell;侧栏/顶栏/主区 `relative z-10` 浮其上;`<main>` 改 `overflow-y-auto overflow-x-hidden`(注释明写「顺带修手机端右侧白块」)。**即用户要我做的事已在 WIP**,待用户定夺是接管细化还是另一会话继续。本会话先只核实/修进度,不动代码。

## 待办 / Blockers

- [ ] 确认 #1/#2 边界:接管现有 `AppLayout.tsx` WIP 细化,还是从头?(避免与另一会话 #3 撞同一文件)
- [ ] #1 壁纸统一:验证 WIP 雏形是否覆盖所有露白处 —— 登录页 `PublicLayout`?移动 Sheet 抽屉 sidebar 是否也半透明?滚动条 gutter?Outlet 内各页自身 `bg-card`?
- [ ] #2 手机端右侧白块:真机 / Claude Preview 复现 + 确认 `overflow-x-hidden` 是否根治,还是有具体宽元素撑出横向滚动
- [ ] 验证后部署:`pnpm build` → scp `frontend/dist` 到 `154.9.238.144:/opt/signin-panel/`(动后端才需 `docker compose build backend`)
- [ ] JM 机器重启后有 pending run 等执行(用户刚开机),与本分支无关但留意是否正常拉起
