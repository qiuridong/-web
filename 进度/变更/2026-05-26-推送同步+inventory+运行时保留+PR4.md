---
date: 2026-05-26
type: 变更
title: MVP-2 推送同步 + Inventory 报告 + 修运行时保留缺陷(PR #4)
---

# 2026-05-26 · MVP-2 推送同步 + Inventory 报告 + 修运行时保留缺陷(PR #4)

> 接 PR #3 的"按需 Pull 同步" 之后,**补完上传时立即推送同步**(用户原话:
> "我要的功能不是这个,而是上传到指定 vps 脚本的这个功能")+ 修 sync 全目录
> 替换会丢运行时产物的缺陷。
>
> 用户 5-26 凌晨原话:**"做层级 1,然后推送之后做一个管理,用户可以自主
> 清理删除上传在 web 项目 vps 的 zip 脚本。然后我们就继续完整外观增强"**
>
> → PR #4(本档)做"层级 1 推送 + 修运行时" / PR #5 做"节点脚本管理 UI" /
> PR #6 做"外观完整版"。**不要忘记进度的更新**(用户强调:这是唯一可靠的查询标准)。

## TL;DR

- **PR #3 落差暴露**:MVP 简化掉了"上传时立即推送同步",只做了 UI 多选 + 按需 Pull。
  上传后开发者无法立刻确认脚本到节点,要等"首次跑实例时"才会触发同步。
  用户明确反馈"我要的功能不是这个"。
- **本 PR 补完**:加 push 通道(主面板 → agent 通过 poll piggyback)+ agent
  端 inventory-report(单一事实源)+ 修 sync 全目录替换缺陷(保留运行时产物)。
- **无破坏 MVP-1 现有流程**:agent 不升级也能继续工作(老 agent 收不到 push,
  但实例跑时仍走按需 Pull)。
- **三端已部署**:
  - backend hash 0003_pending_actions migration 已 upgrade
  - frontend hash `index-BRM9k0Qo.js`
  - agent VPS-JM restart 后 sanity 全过 + 启动时 inventory-report 200
- **e2e 真测留给用户**:在 web `/scripts` 下载模板项目 → 拖回来勾选 vps-jm
  节点 → 上传 → 看 toast "已要求 1 个节点立即同步,最长 30 秒内完成" + 30s
  内 agent 日志显示 `⤓ 主面板推送指令: sync=['_test_xxx']` + ✓ 同步完成。

## 1. 5 个组件清单

| # | 组件 | 文件 | 行数 |
|---|---|---|---|
| 1 | alembic migration | `backend/alembic/versions/0003_nodes_pending_actions.py` | +60 |
| 2 | Node model + 字段 | `backend/app/db/models/node.py` | +15 |
| 3 | backend agent.py poll piggyback + inventory-report endpoint | `backend/app/api/v1/agent.py` | +130 |
| 4 | backend schemas:`PendingActions` / `AgentInventoryReport*` | `backend/app/schemas/node.py` | +60 |
| 5 | backend script_upload 接 `sync_to_nodes` query | `backend/app/api/v1/script_upload.py` + schemas | +110 |
| 6 | agent 处理 pending_actions + inventory + 修运行时保留 | `agent/signin_agent.py` | +220 |
| 7 | frontend `useScriptUpload` + UploadScriptDialog | `frontend/src/api/hooks/useScriptUpload.ts` + `UploadScriptDialog.tsx` | +30 |
| | **总** | **7 files** | **+625** |

## 2. 设计思路 — Push 通过 Poll piggyback

agent 是**纯 pull only** 不开 listening port,主面板无法主动 push。
方案:主面板把"待办指令"存在 `nodes.pending_actions JSON`,**agent 每次 poll
时主面板把它捎带在 response 里**(即使无 task 也带,30s long-poll 间隔)。

```
        ┌────────────────────────────────┐
        │ user 上传(选 vps-jm)         │
        └─────────────┬──────────────────┘
                      │
                      ▼
          ┌──────────────────────┐
          │ backend script_upload│
          │ append slug 到 node  │
          │ .pending_actions.sync│
          └──────────┬───────────┘
                     │ (写 DB)
                     ▼
        ┌────────────────────────┐    long-polling (≤30s)
        │ nodes.pending_actions  │ ◄──────────────────────┐
        │   {sync:[slug]}        │                        │
        └──────────┬─────────────┘                        │
                   │ next poll piggyback                  │
                   ▼                                      │
        ┌────────────────────────┐                        │
        │  agent.handle_pending  │                        │
        │  → _ensure_script_syncd│                        │
        │  → POST inventory-report                        │
        │     (acked + deployed) │                        │
        └──────────┬─────────────┘                        │
                   │ 主面板从 pending_actions 移除 acked  │
                   └──────────────────────────────────────┘
```

**优点**:
- 无新长连接 / 无 WebSocket / 无主面板 → agent push 方向连接
- 复用现有 poll(30s long-poll)— 最坏 30 秒 push 完成
- agent 处理失败下次 poll 重收(幂等 — sync 比对 sha256 是 no-op / delete 不存在是 no-op)

## 3. 关键数据结构

### `nodes.pending_actions JSON`

```json
{
  "sync": ["jmcomic", "v2ex"],
  "delete": ["old-script"]
}
```

- 主面板 → agent 的"待办指令"
- 上传时若选了节点 → service 把 slug append 到 `sync`
- 未来"删除"功能(PR #5)同理 append 到 `delete`

### `nodes.deployed_scripts JSON`

```json
{
  "jmcomic": {
    "sha256": "a2156b75...",
    "deployed_at": "2026-05-26T11:09:00+00:00"
  }
}
```

- agent 通过 inventory-report **覆盖**(agent 是单一事实源)
- 节点详情页(PR #5)用它列"已部署脚本"

### `AgentPollResponse` 新增字段

```python
class AgentPollResponse(BaseModel):
    task: AgentTaskPayload | None = None
    pending_actions: PendingActions | None = None  # MVP-2 新增

class PendingActions(BaseModel):
    sync: list[str] = []
    delete: list[str] = []
```

- 无 task 也带 pending_actions(若非空)
- 都为空时返 `null`,agent 跳过(避免噪音 log)

### `POST /api/v1/agent/inventory-report`

```python
class AgentInventoryReport(BaseModel):
    deployed_scripts: dict[str, dict[str, Any]]  # 本地实际情况
    acked_actions: PendingActions                # 刚处理完的 slug

class AgentInventoryResponse(BaseModel):
    ok: bool = True
    pending_actions_after: PendingActions        # ack 后剩余
```

调用时机:
- agent 启动后(sanity 通过) → 报告本地状态,无 ack
- agent 处理完 pending_actions 后 → 报告 + ack
- 周期兜底(每 5 min)→ 报告本地状态,无 ack(防 push 漏掉)

## 4. agent 处理 pending_actions 流程

```python
def _handle_pending_actions(self, actions):
    acked_sync, acked_delete = [], []
    for slug in actions.get("sync", []):
        try:
            self._ensure_script_synced(slug)
            acked_sync.append(slug)
        except Exception as e:
            self.logger.error(f"推送同步失败 slug={slug}: {e}")

    for slug in actions.get("delete", []):
        target = scripts_dir / slug
        if target.is_dir():
            shutil.rmtree(target)
        acked_delete.append(slug)

    self._post_inventory_report(acked_sync, acked_delete)
```

幂等性:
- sync 失败 → 下次 poll 再收到 → 再试(sha256 一致则 no-op)
- delete 失败 → 下次 poll 再收到 → 再试(目录不存在则视为成功)

## 5. 修运行时保留缺陷

PR #3 暴露的问题(5-26 e2e 比对发现):agent `_ensure_script_synced` 是**全
目录替换**(`os.replace(tmp_dir, script_dir)`),如果 vps-jm 上 jmcomic 目录里有 selenium
生成的 `downloaded_files/` (chromedriver lock)或者实例 cookies cache,
sync 后会丢失(被搬到 backup 目录)。

实测影响 = 0(都是 0 字节 lock 文件,seleniumbase 重生成),但**设计上是 bug**。

修复:加 `RUNTIME_PRESERVE_DIRS`:
```python
RUNTIME_PRESERVE_DIRS = frozenset({
    "downloaded_files",
    "data",
    "__pycache__",
    "_dry_run_data",
    ".backups",
})
```

`_ensure_script_synced` 在 `os.replace(tmp_dir, script_dir)` **之前**,
把 `script_dir` 里这些目录 `os.replace` 到 `tmp_dir` 对应位置(bundle 过滤了
这些目录,tmp_dir 必然不冲突)。这样 replace 后运行时产物 100% 保留。

## 6. 三端部署清单

### Backend
```bash
# 6 文件 scp 到主面板
scp backend/app/api/v1/{agent,script_upload}.py     → /opt/signin-panel/backend/app/api/v1/
scp backend/app/db/models/node.py                    → /opt/signin-panel/backend/app/db/models/
scp backend/app/schemas/{node,script_upload}.py      → /opt/signin-panel/backend/app/schemas/
scp backend/alembic/versions/0003_nodes_pending_actions.py
                                                     → /opt/signin-panel/backend/alembic/versions/

# rebuild + alembic upgrade
docker compose up -d --build backend
docker compose exec -T backend python -m alembic upgrade head
# → "Running upgrade 0002_add_nodes -> 0003_pending_actions"
# → alembic current: 0003_pending_actions (head) ✅
```

### Frontend
- `pnpm build` → hash `index-BRM9k0Qo.js`
- `tar dist → scp → 解压` → 备份 `dist.backup.20260526-040406/`

### Agent (VPS-JM 38.55.132.186)
```
scp agent/signin_agent.py → /opt/signin-agent/signin_agent.py
systemctl restart signin-agent
```

启动日志(关键时间点):
```
12:04:37 signin-agent 1.0.0 启动
12:04:37 ✓ python_bin / sandbox_runner / scripts_dir(已部署 1 个: ['jmcomic']) / data_dir
12:04:37 ✓ 主面板连通,节点 id=2 slug=vps-us8-8-jm
12:04:38 POST /api/v1/agent/inventory-report 200  ← 新 endpoint 启动时自动报告
12:04:38 heartbeat 200 OK
```

## 7. e2e 真测步骤(留给用户在 web 操作)

1. Ctrl+F5 硬刷 `https://jb.aijiaxia.cc/scripts`(拿 hash `index-BRM9k0Qo.js`)
2. 点"添加脚本" → 顶部"📥 下载模板项目" → 下载 `my-script-template.zip`
3. 拖回上传区 → 清单全 ✅ → **勾选下方"同步到节点(可选,可多选)"里的 vps-jm**
4. 点"开始上传"
5. 看 toast:**"已要求 1 个节点(vps-us8-8-jm)立即同步,最长 30 秒内完成"** ✅
6. 30 秒内,SSH 到 vps-jm `tail -f /var/log/signin-agent/agent.log` 看到:
   ```
   ⤓ 主面板推送指令: sync=['my-script-template'] delete=[]
   ⤓ 同步脚本 my-script-template: local=(无) → remote=xxx (xxxx bytes)
   ✓ 脚本同步完成 my-script-template sha=xxx
   POST /api/v1/agent/inventory-report 200
   ```
7. `ls /opt/signin-agent/scripts/` → 多了 `my-script-template/` ✅

如果 e2e 全过,说明 push 通道完全工作。如果失败,看 agent.log + backend logs 定位。

## 8. 异常处理矩阵

| 场景 | 行为 |
|---|---|
| poll 拿到 pending_actions 但 sync 失败(网络抖动) | log error,**不 ack**;下次 poll 再收到再试 |
| poll 拿到 delete 但目录不存在 | log info,正常 ack(幂等) |
| inventory-report 失败(网络) | 下次 poll 时**主面板还会发同样的 pending_actions**(因为没 ack);再试 |
| 主面板 sql 写 pending_actions 失败 | upload endpoint 抛 500,前端显示错误 |
| agent 升级前的老版本拿到 pending_actions | 忽略(老 agent 不知道这个字段),下次 poll 同样 — 直到 agent 升级 |
| agent 处理时间 > 30s(long-poll 超时) | 不影响:agent 处理完才 next poll;期间主面板写新 sync 也行,会一起处理 |

## 9. 向后兼容性

| 场景 | 行为 |
|---|---|
| 老 agent + 新 backend | poll response 多了 `pending_actions` 字段,agent 忽略(用 .get) |
| 新 agent + 老 backend | poll response 缺 `pending_actions`,agent 用 .get 拿 None;启动时 inventory-report 调老 backend 404,agent log warning 继续 |
| 老 frontend + 新 backend | UploadScriptDialog 不传 sync_to_nodes,upload endpoint 走老逻辑(不 push) |

向后兼容 ✅,可以**逐端升级**。

## 10. 后续(PR #5 / PR #6)

### PR #5 节点脚本管理(~2.5h)

- backend `/api/v1/nodes/{id}/deployed-scripts` GET 返 `nodes.deployed_scripts`
- backend `/api/v1/nodes/{id}/scripts/{slug}` DELETE → append 到 pending_actions.delete
- frontend `/nodes/{id}` 详情页加"已部署脚本"tab + 删除按钮

### PR #6 外观完整版(~5-6h)

- backend `app_settings` KV 表 + 文件上传 endpoint + 静态目录
- frontend 设置→外观 加"品牌与背景"段(Dropzone + 实时预览)
- frontend Layout 应用 setting

## 11. Git / PR

| 分支 | Commit | 状态 |
|---|---|---|
| `feat/push-sync-and-runtime-preserve` | (待 commit) | ⏸ 待 push + 开 PR |

无 alembic migration 冲突(下一次 head 为 0003)。无新 Python 依赖。

## 12. 教训

- **不要 over-MVP**:5-25 设计 PR #3 时我自作主张做了"UI 标记不主动推送"的简化,用户明确反馈"我要的不是这个"。**关键 UX 路径不能简化** — 用户的"上传选节点 = 立刻推送"是直觉,不能违背。
- **Push via Poll piggyback** 是 pull-only 架构里"伪推送"的最干净方式 — 无新连接、无新 task type、无 DB 大改、向后兼容。
- **单一事实源**:agent 是 deployed_scripts 的唯一事实源(via inventory-report),主面板只是镜像。避免主面板和 agent 双向写产生不一致。
- **幂等性是 push 的基石**:sync/delete 都设计成幂等(sha256 比对 / rm 不存在视为成功),失败重试天然安全。
- **进度文档不能漏**(用户明确强调):每个 PR 同分支带变更档案 + README + 分支 main.md 更新,这是唯一可靠的查询标准。
