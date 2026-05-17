---
name: 2026-05-17 · 前端 abort 错误 toast 静默 hotfix(用户创建实例时被误导)
description: client.ts onError 没过滤 AbortError 导致 React Query 主动 cancel 也红色提示
type: change
status: ✅ 已修 + 已部署 dist(`index-JmCKC6a4.js`)
---

# 2026-05-17 晚 · 前端 abort toast 静默 hotfix

## 30 秒摘要

1. 用户成功创建 PTFans 实例(后端 200 + 绿色 toast `实例「PTFans」已创建`)
2. **同时**红色 toast `signal is aborted without reason` 误导用户以为失败
3. **真因**:`frontend/src/api/client.ts` 的 `onError` 没过滤 `AbortError`,React Query 在组件 unmount / refetch 抢占时主动 abort pending fetch 是正常行为,不该 toast
4. fix:在 onError 顶部 early return 过滤 5 种 abort 情况(`AbortError` / `ERR_CANCELED` / message 含 `aborted` 或 `signal is aborted` 或 `The user aborted`)
5. `pnpm build` 10s → 新 hash `index-JmCKC6a4.js`(原 `BIPAwks0.js`)→ scp 2.8MB dist 包 → 解压到 `/opt/signin-panel/frontend/dist/`(nginx Cache-Control: no-cache,用户硬刷新拿)

## 用户场景重现

- 用户在 `/scripts/ptfans` 点"创建实例"
- 第一次没填**名称**(必填字段),提交后 422,前端只显示"未知错误"(没把 422 details.errors 抽出来)
- 第二次填了名称,提交后 200 成功,实例真的创建了
- **同时**前端某个 GET refetch 被 React Query cancel(因为 dialog 关闭 / 表单 unmount),`onError` 抓到 AbortError 当作业务错误 toast

## 改的文件

| 文件 | 改动 |
|---|---|
| `frontend/src/api/client.ts` | `onError` 顶部加 14 行 early return,过滤 abort 错误 |
| `frontend/dist/*` (build 产物) | 新 bundle hash `index-JmCKC6a4.js` |

## 部署

```bash
cd frontend && pnpm build                       # 10s,vite 13 chunks
tar czf /tmp/frontend-dist.tar.gz -C frontend dist
scp ... /tmp/frontend-dist.tar.gz root@154.9.238.144:/tmp/
ssh ... "cd /opt/signin-panel/frontend && rm -rf dist && tar xzf /tmp/frontend-dist.tar.gz"
# nginx 自动 serve 新 dist(不用 reload,nginx 静态文件实时读)
# 用户 Ctrl+F5 硬刷新拿新 hash
```

部署时长:约 30 秒(不动 backend / docker,仅替换 nginx 静态文件)。

## 没修的(独立 UX bug,等下次)

### 1. "名字必填但提交前不提示"

后端 `InstanceCreate.name` 是 `Field(..., min_length=1, max_length=128)`,留空 422。前端表单**没 client-side required 校验**,也**没把 422 的 details.errors 显示给用户**(只显示通用 "未知错误")。

修法两个层次:
- **快(3 分钟)**:`client.ts onResponse` 加 422 case,把 `details.errors` 第一条用 toast 显示
- **完整(15 分钟)**:前端表单加 react-hook-form + zod schema,客户端先校验必填字段

### 2. error_handler.py 后端 log 太简略

`backend/app/middleware/error_handler.py:121` 只 log `errors=<count>`,没 log 具体字段错误。PM 诊断时只能猜或者用户给 F12。改成 log 每个 error 的 `loc + msg` 会方便后期诊断。

## 影响范围

| 维度 | 影响 |
|---|---|
| 用户体验 | 重大改善 — 不再有"操作成功但红色 toast 显示失败"的误导 |
| 后端 | 0 影响,纯前端改动 |
| 数据 | 0 影响,用户之前提交的实例都是真的(后端 200) |
| 部署 | dist 一次性替换,约 30 秒,生产无中断 |
| breaking | 无 |

## 关联

- 用户截图同时看到了 ✅ "实例「PTFans」已创建" + ❌ "signal is aborted without reason"
- 后端 logs:多次 `POST /api/v1/instances -> 422 (5ms)` 加最后一次 200(用户填了名字之后)
- 触发本 hotfix 的对话上下文:用户问"是不是最新的没有部署到服务器上"+ "现在无论修改什么都会出现这个错误提示"

## 后续

等用户:
1. **硬刷新拿新 dist** 验证 abort toast 消失
2. **去 /scripts/ptfans 实例 Tab** 看 PTFans 实例已存在 → 点"立即运行"看签到结果
3. 选是否修复"name 未填没提示"的 UX bug(方案 A 快 / B 完整)

---

## ⚠️ v2 修复(第一版漏了关键一层)

### 用户反馈
> "abort 错误是经常出现,不管我做什么修改都有可能出现,哪怕正常修改"

### 真因(我之前漏的)
v1 只修了 `frontend/src/api/client.ts`(openapi-fetch middleware 那层)。但项目里**还有第二层 toast 入口** —— `frontend/src/api/query-client.ts` 的 TanStack QueryClient.defaultOptions.mutations.onError(第 32-36 行):

```typescript
mutations: {
  retry: false,
  onError: (err) => {
    if (isUnauthorized(err)) return;
    toast.error(formatError(err));  // ← 这里直接 toast 任何 mutation 错误,包括 abort
  },
},
```

任何 useMutation(创建实例 / 改配置 / 立即运行 / 删除等所有"修改"操作)的错误都会落到这里。React Query 在用户连续操作 / 切页面 / 关 dialog 时主动 abort pending mutation 也会触发,被错误地 toast。

### v2 fix
- 抽出通用函数 `isAbortError(err)` 集中判定 5 种 abort 错误(`AbortError` / `ERR_CANCELED` / msg 含 `aborted` / `signal is aborted` / `The user aborted`)
- 在 `query-client.ts` **三处**用上:
  1. `mutations.onError` 早期 return 不 toast
  2. `queries.retry` 返回 false(abort 不重试,省请求)
- `client.ts` 的 v1 逻辑保留(防御性两层兜底)

### v2 部署
- `pnpm build` 10.29s → 新 hash **`index-CP_QytwL.js`**(从 v1 的 `index-JmCKC6a4.js` 升级)
- scp 2.8MB dist → 解压 `/opt/signin-panel/frontend/dist/`
- 用户 Ctrl+F5 硬刷新拿新 hash

### 教训
做这类全局错误处理 fix,**必须 grep 整个 src/ 所有 `toast.error` + `QueryClient` + `onError` 入口**,不能只看一个 middleware 就以为修完。

```bash
# fix 前应该跑:
grep -rn "toast.error\|onError\|defaultOptions" frontend/src
# 集中所有错误处理入口,统一过滤策略
```
