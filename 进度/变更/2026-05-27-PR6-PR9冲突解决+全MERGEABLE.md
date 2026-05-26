---
date: 2026-05-27
type: 变更 / Merge
title: PR #8 merged 后 PR #6/#9 解 main 冲突,全 MERGEABLE
---

# 2026-05-27 凌晨 · PR #8 merged 后 PR #6/#9 解 main 冲突,全 MERGEABLE

> 用户 merge PR #8(super-PR 含 PR #7,commit `d6bf149`)→ PR #6 和 PR #9 都自动跟 main 冲突 → 本次依次解决。

## TL;DR

| PR | 冲突类型 | 解法 | merge commit | 状态 |
|---|---|---|---|---|
| #6 彻底删除 | 2 文件(进度文档) | `--theirs` main.md(已含 PR #6 引用)+ 手动 Edit README | `53a2e37` | ✅ MERGEABLE/CLEAN |
| #9 code-review 14 fixes | **6 文件代码 +** 2 文件文档 | **全 `--ours`** 接受 PR #9 superset 版本 | `f4f3461` | ✅ MERGEABLE/CLEAN |

frontend build hash `index-C7rQPvNW.js` 跟 PR #9 之前 build 一致,**确认 14 fixes 完整保留**(merge 没回退任何 review fix)。

## 1. PR #6 冲突(文档)

冲突文件:
- `进度/README.md`
- `进度/分支/main.md`

冲突原因:PR #6 base 是较早 main(PR #4/#5 之前),后续 PR #4/#5/#8 推动 main 加了不少进度文档段。

### 解法

- **`进度/分支/main.md`** — `git checkout --theirs`(直接用 origin/main 完整版,已经在 PR #8 的进度文档里引用了 PR #6 的变更档案)
- **`进度/README.md`** — Edit 手动融合:保留 origin/main 的所有"当前状态"段(完整时间线),把 PR #6 的状态段插入到 PR #8 段之前(时间顺序对)

merge commit:`53a2e37`

## 2. PR #9 冲突(代码 + 文档)

冲突文件 6 个代码:
- `backend/app/services/settings_service.py`(PR #9 加 XSS validator + deepcopy)
- `frontend/src/api/hooks/appearance.ts`(PR #9 加 BroadcastChannel + 字符串兜底)
- `frontend/src/components/common/DataTable.tsx`(PR #9 改 overflow-auto)
- `frontend/src/components/layout/AppLayout.tsx`(PR #9 加 favicon cleanup + palette deps + querySelectorAll + safeOpacity/safeBlur + resize listener + overlay 反转默认)
- `frontend/src/components/ui/sheet.tsx`(PR #9 改 backdrop 48px)
- `frontend/src/pages/settings/Settings.tsx`(PR #9 加 dirty 守卫 + AlertDialog + appearanceEqual)

冲突原因:PR #9 是从 `feat/appearance-settings` 分支(PR #8 super-PR)切出,**HEAD 已含 PR #8 全部代码 + 14 review fixes**(superset);main 上 PR #8 merge commit 是同等内容但 hash 不同 → git auto-merge 看到两边都改同一行,标冲突。

### 解法

**关键决策**:HEAD vs theirs 怎么选?
- HEAD = PR #9 分支(PR #8 内容 + 14 review fixes)
- theirs = origin/main(PR #8 内容,无 review fixes)
- 用 HEAD 是 **superset**:既保留 PR #8 代码,又保留 PR #9 的 review fixes

`git checkout --ours` 6 个代码文件 → 全用 PR #9 HEAD 版本

### 验证

- `pnpm build` ✓ → hash `index-C7rQPvNW.js`(**跟 PR #9 之前 build 一致**)
- 关键 fix 文件 grep 确认 14 fixes 仍在:dirty 守卫 / `data:image/` validator / `deepcopy` / BroadcastChannel / favicon cleanup `cancelled` flag / querySelectorAll / AlertDialog reset / `min(calc(100vw-3rem),24rem)` / `safeOpacity`/`safeBlur` / matchMedia resize listener / overlay 默认白罩

merge commit:`f4f3461`

## 3. 关键经验

### 决策矩阵:HEAD vs theirs 怎么选

```
PR 跟 main 冲突时:

1. 文档(README / main.md / 变更档案)
   → 通常 main 已经累计了所有 PR 引用,用 theirs 接受 main
   → 若 PR 自己加了 main 没有的段,手动 Edit 融合
   → 永远不要 ours 文档(会丢 main 上其他 PR 的进度)

2. 代码 — 看 PR 是 superset 还是 subset:
   → superset(PR 是从 main 后续分支切出 + 加新东西)→ ours 安全
   → subset(PR 是从早 main 切出 + 改了 main 也改过的)→ 手动融合,不能简单 ours
   → 双方各加各的(PR 加 A 行,main 加 B 行)→ 手动融合 / merge 工具

3. 判断 superset 的方法:
   → 看 PR 分支的 base commit(`git merge-base HEAD origin/main`)
   → 若 base 早于 main 上冲突文件最后改动 → 不是 superset
   → 若 base 晚于(或 base 就是)冲突 commit → 是 superset
```

### PR review 流程下的多 PR 工作流

5 个 PR(#6 #7 #8 #9)同时存在 + 改重叠文件,**串行 merge 顺序**:

```
PR #4 #5 (无冲突) → merged
  ↓
PR #6 (独立改 ScriptList) → 等 merge
PR #7 (改 AppLayout sidebar) → merge PR #8 时一起 merge
PR #8 (super-PR PR #7+#8) → merged 后 main 有 PR #7+#8 全部
  ↓
PR #6 跟 main 文档冲突 → 解(本次)
PR #9 跟 main 6 文件冲突 → 解(本次)
  ↓
2 个 PR 都 MERGEABLE,按节奏 merge
```

下次教训:**code-review PR 应该基于 PR #8(后续 base),而不是基于 main**,这样跟 PR #8 merge 后是天然 fast-forward,不需要解冲突。但本次因为 PR #9 是修 PR #8 引入的 bug,基于 PR #8 也合理(只是 GitHub UI 会在 PR #8 merge 后强制 PR #9 跟新 main 比对)。

## 4. 文件清单

**本次改动**(纯进度文档 + git merge commits,**无代码改动**):
- `进度/README.md`(当前状态加 2026-05-27 段)
- `进度/分支/main.md`(末尾追加 2026-05-27 一行)
- `进度/变更/2026-05-27-PR6-PR9冲突解决+全MERGEABLE.md`(本文件,新建)

**Git history**:
- `53a2e37` PR #6 merge main
- `f4f3461` PR #9 merge main

## 5. 后续

| 步骤 | 谁做 |
|---|---|
| Review + merge PR #6 | 用户(GitHub UI 已 MERGEABLE) |
| Review + merge PR #9 | 用户(同上) |
| backend docker rebuild + frontend dist scp 部署生产 | 我(等用户 merge 完) |
| 真测 14 review fixes 中前 5 个 HIGH | 用户(硬刷 + 试 XSS / dirty 守卫 / multi-tab) |
| 决定下一步功能 | 用户 |
