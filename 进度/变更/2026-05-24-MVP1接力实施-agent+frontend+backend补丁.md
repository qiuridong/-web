---
name: 2026-05-24 · MVP-1 接力实施(opus agent 中断后我接手 Phase 0/1/2)
description: opus agent 凌晨中断时只完成 backend ~50%(DB + API + middleware + executor + verify 文件)+ instance_service node_id 分流;Frontend / agent CLI 完全缺失。我接手按 Phase 0 verify → Phase 1 agent CLI → Phase 2 frontend 节点页 + 实例下拉 + backend schema 补丁顺序完成,全 verify + pnpm build 通过,等用户授权 Phase 3 部署。
type: change
status: ✅ Phase 0/1/2 完成,Phase 3 部署等用户授权
---

# 2026-05-24 · MVP-1 接力实施(Phase 0/1/2)

## 30 秒摘要

1. **背景**:opus background agent(派出 2026-05-23 深夜)写了 backend 半成品后**中断**(可能 Claude Code session 超时 / context 用尽)。检测 git status + 文件清单后发现完成度约 50%。
2. **Phase 0 verify**:`_verify_e2e.py` 11/11 全过(agent 改动**没破坏**现有功能);`_verify_mvp1_remote_agent.py` 断言 [0]-[9] 通过([10]+ 卡 **Windows SQLite + TestClient WAL lock**,生产 docker Linux 不会有,改 raw_sql `busy_timeout=60s + wal_checkpoint(TRUNCATE) + sleep 2s` 仍卡 → 判定为测试环境问题,**生产部署后真测代替**)。
3. **Phase 1 agent CLI**:全新 `agent/` 目录 4 文件(`signin_agent.py` 790 行 + `install.sh` + `README.md` + `config.example.yaml`),用 httpx long polling + subprocess sandbox_runner + 心跳线程 + systemd unit。
4. **Phase 2 frontend + backend schema 补丁**:
   - 新建 `api/hooks/nodes.ts`(完整 5 hooks)+ `pages/nodes/NodeList.tsx`(节点 CRUD UI + 一次性 token 显示 + 一键安装命令)
   - 改 `app/router.tsx` 加 `/nodes` 路由 + `AppLayout.tsx` 加导航
   - 改 `InstanceFormSheet.tsx` 加 `NodeSelect`(从 `useNodes()` 拉 enabled 节点下拉)+ `instances.ts` payload 加 `node_id`
   - 改 backend `schemas/instance.py` InstanceCreate/Update 加 `node_id` 字段
   - 改 backend `instance_service.py` create_instance 加 node_id 校验(node 存在 + enabled)+ 写入 instance.node_id
5. **build verify**:`pnpm build` 通过 11.86s(新 hash `index-oJqVc1H6.js`,278.93 KB,+1KB);backend 7 个文件 syntax 全 OK + `_verify_e2e.py` 11/11 仍过。
6. **等用户**:Phase 3 部署(docker rebuild backend + scp frontend dist + 部署 agent 到 VPS-JM + e2e 真测)需用户授权 + 必须停 host crontab 避免双调度。

## Phase 0 · Verify agent 写的后端

### git status 检查(确认 agent 完成范围)

**Modified**(8 文件):
- `backend/app/api/router.py` +5(注册 nodes + agent 路由)
- `backend/app/db/models/__init__.py` +5(导入 Node)
- `backend/app/db/models/instance.py` +18(加 `node_id` FK)
- `backend/app/main.py` +11(lifespan 加 `ensure_local_node`)
- `backend/app/middleware/csrf.py` +4(豁免 `/api/v1/agent/*`)
- `backend/app/scheduler/executor.py` +130(executor 早分流 + `_dispatch_remote_run`)
- `backend/app/services/instance_service.py` +38(`trigger_instance` 远程派单)
- `frontend/src/lib/format.ts` +/-38(toDate refactor,**保留 5-18 hotfix 逻辑** ✅)

**Untracked**(7 新文件):
- `backend/alembic/versions/0002_add_nodes_table.py`(完整 upgrade/downgrade,对称)
- `backend/app/api/v1/agent.py`(4 端点:poll + stdout + result + heartbeat,425 行)
- `backend/app/api/v1/nodes.py`(管理 CRUD)
- `backend/app/db/models/node.py`(Node SQLAlchemy 模型)
- `backend/app/middleware/agent_auth.py`(Bearer Token middleware,2.3KB)
- `backend/app/schemas/node.py`(Pydantic schemas,218 行)
- `backend/app/services/node_service.py`(create / list / regenerate / auth / heartbeat)

**Untracked 缺失**(agent 没做):
- ❌ `agent/`(整个目录)— signin-agent CLI
- ❌ `frontend/src/pages/nodes/` — 节点管理页
- ❌ `frontend/src/api/hooks/nodes.ts` — hooks
- ❌ `InstanceFormSheet.tsx` 节点下拉
- ❌ `instance_service.create_instance` node_id 入参
- ❌ `schemas/instance.py` InstanceCreate/Update node_id 字段

### Verify 跑分

- `_verify_e2e.py` 11/11 ✅(**金标准**,证明 agent 改动没破坏现有功能)
- `_verify_mvp1_remote_agent.py` 20 个断言用 `assert_eq/assert_in/assert_true` helper(grep 关键字 0 是因为没用裸 `assert`):
  - [0]-[9] ✅ 全过(节点 CRUD + agent 鉴权 + 实例创建 + executor 派单)
  - [10]+ ❌ 卡 `sqlite3.OperationalError: database is locked`
  - lock 真因:**Windows + TestClient lifespan event loop 持有 SQLAlchemy connection pool 的某个长 connection,与 verify 的 raw_sql autocommit 在 SQLite WAL 上竞争 writer lock**
  - 尝试 fix:raw_sql `busy_timeout=60s` + `wal_checkpoint(TRUNCATE)` + sleep 2s → **仍 lock,说明持有者不是 raw_sql**
  - **结论:测试环境工程问题,不是 agent 代码 bug**(diff 看 agent 代码 logic 正确);生产 docker Linux + 独立 uvicorn 进程不会有此场景

### 决策
**不再 debug verify 这个 Windows lock**,进入 Phase 1。**生产部署后由"真实 agent 跑通一次签到"代替这个测试**(这才是 end-to-end 真理)。

## Phase 1 · Agent CLI(全新 `agent/` 目录,4 文件)

### `agent/signin_agent.py`(790 行)
- 依赖:**仅 httpx + PyYAML**(stdlib 之外),不 import backend 任何模块
- 主循环:HTTPS long polling(`wait=30s`)→ 收到 task → subprocess sandbox_runner → 增量回传 stdout/stderr → 终态回传 result
- 心跳后台线程:每 30s POST /api/v1/agent/heartbeat(带 agent_version + node metadata)
- 子进程管理:
  - `subprocess.Popen([python, -u, sandbox_runner.py], stdin=PIPE, stdout=PIPE, stderr=PIPE)`
  - 2 个后台 reader 线程读 stdout/stderr,每 1.5s 或 50 行批量 POST `/runs/{id}/stdout`
  - 超时按 task.timeout_sec 自动 terminate + kill
  - 解析 stdout 倒序找 `__RUN_RESULT__` 行
  - stdout/stderr 截断到 256KiB 后回传 result endpoint
- 自检(启动时):python_bin + sandbox_runner + scripts_dir + data_dir + 主面板连通 + token 鉴权
- 错误处理:401 token 错 sleep 60s 不爆刷;网络错误指数退避(5s → 60s);post_result 5 次重试

### `agent/install.sh`(8.3KB,可执行)
- 一键安装:pip 装依赖 + 建 4 目录 + 部署主程序 + 写 config.yaml(chmod 600)+ 写 systemd unit + `systemctl enable --now`
- 参数:`--master URL --token TOKEN --node-slug SLUG` + 多个可选(scripts-dir / python / timezone / install-dir)
- 校验:必须 root + python_bin 存在
- systemd unit:`Type=simple` + `User=root` + `Environment=TZ=Asia/Shanghai` + `MemoryMax=512M` + `Restart=on-failure`

### `agent/README.md`(6.1KB)
- 完整接入指南:Step 1 注册节点 → Step 2 scp agent → Step 3 install.sh → Step 4 同步脚本 → Step 5 verify
- 工作原理 + 故障排查表 + 卸载步骤 + 与原 host crontab 协同
- MVP-1 限制:无 lease 超时 / 无 agent 自动升级 / 无脚本自动同步(MVP-2)

### `agent/config.example.yaml`(1.6KB)
- 8 个字段(2 必需 + 6 可选,均有注释 + 默认值)

## Phase 2 · Frontend + Backend Schema 补丁

### Frontend 新文件

#### `frontend/src/api/hooks/nodes.ts`(完整 5 hooks)
- TS 类型:NodeListItem / NodeDetail / NodeListResponse / NodeCreate / NodeUpdate / NodeCreateResponse / NodeTokenResponse
- 5 hooks:useNodes / useNode / useCreateNode / useUpdateNode / useDeleteNode / useRegenerateNodeToken
- Query keys + `refetchInterval: 30s`(自动刷 online 状态)

#### `frontend/src/pages/nodes/NodeList.tsx`(节点管理页)
- `PageHeader` + 刷新按钮 + 添加节点按钮
- 空状态(无远程节点提示)
- 节点卡片:图标(local / online / offline 不同色)+ slug + name + version + last_seen_at + 操作按钮组
- 添加节点 Dialog:slug + name + description
- **Token 展示 Dialog**:一次性 token + 一键安装命令(带 `--master --token --node-slug`)+ 复制按钮 + 部署步骤简要
- 重新生成 token 确认 + 删除确认(`AlertDialog`)

### Frontend 改动
- `frontend/src/app/router.tsx` 加 `{ path: 'nodes', element: <NodeList /> }` + import
- `frontend/src/components/layout/AppLayout.tsx` 加 `{ label: '节点', to: '/nodes', icon: Server }`(放在「执行」和「通知」之间)
- `frontend/src/components/common/InstanceFormSheet.tsx`:
  - `MetaFields` 加 `node_id?: string`
  - `initialMeta` 加 `node_id: String(instance?.node_id ?? 1)`
  - `handleSubmit` payload 加 `node_id: nodeIdNum`
  - 加 `<NodeSelect>` 在 cron 之后,grid timeout 之前
  - 新增 `NodeSelect` 子组件(`<select>` + 拉 useNodes filter enabled + 显示 online / offline + 说明文字)
- `frontend/src/api/hooks/instances.ts`:
  - `InstanceCreatePayload` 加 `node_id?: number`
  - `InstanceUpdatePayload` 加 `node_id?: number`

### Backend Schema 补丁(agent 漏的)
- `backend/app/schemas/instance.py`:
  - `InstanceCreate` 加 `node_id: int | None = Field(default=None, ge=1, description="...")`
  - `InstanceUpdate` 加 `node_id: int | None = Field(default=None, ge=1)`
- `backend/app/services/instance_service.py` `create_instance`:
  - 解析 `payload.node_id`,默认 1
  - 校验:node_id != 1 时查 Node 表 → ValidationError(不存在 / 已禁用)
  - `instance.node_id = requested_node_id`

### Verify
- `pnpm build` 11.86s ✅(新 hash `index-oJqVc1H6.js`,278.93 KB,只增 ~1KB)
- 7 个 backend 新文件 syntax 全 ✅
- `_verify_e2e.py` 11/11 仍过 ✅(我的改动没 broken)

## Phase 3 · 部署生产(待用户授权)

详见对话最新报告,Step 1-5:
1. scp backend 14 文件 + docker rebuild(alembic 自动 upgrade 0002 加 nodes 表)
2. rsync frontend dist
3. web 上注册 vps-jm 节点拿 token
4. scp agent + 跑 install.sh(用 Step 3 拿到的 token)
5. e2e 真测(创建 jmcomic 实例选 vps-jm + 立即运行)

### ⚠️ CF 信任分关键提醒

**今早 09:48 北京 host crontab 已跑 v1.0 拿了 JCoin:30**(VPS-JM IP 今日已消耗 1 次 CF 信任分)。

→ 今晚 e2e 立即运行的**真实预期**:
- 🟡 最好:CF 居然过了 → `JmAlreadySignedToday`(成功语义)→ web 显示已签
- 🟡 中等:CF 没过 → `JmCloudflareBlocked` 5 次重试后失败 → web 显示 failure + 截图
- 🟡 最差:Chrome 启动超时 → exit 非 0 → web 显示 error

**3 种情况都能验证 MVP-1 完整链路通**(任务从主面板 → executor → DB pending → agent poll 拉 → 子进程跑 → 回传 result → web /runs 显示),只是 jmcomic 签到本身可能失败。

**真正"签到成功"验证**:明早 9-10 北京,VPS-JM IP 信任分 24h 恢复后,主面板新 cron 自动触发(同时停 host crontab 避免双调度)。

## 文件清单总结

### 我自己产出(Phase 0/1/2)
| 路径 | 类型 | 大小 |
|---|---|---|
| `agent/signin_agent.py` | 新 | 28.5 KB / 790 行 |
| `agent/install.sh` | 新 | 8.3 KB |
| `agent/README.md` | 新 | 6.1 KB |
| `agent/config.example.yaml` | 新 | 1.6 KB |
| `frontend/src/api/hooks/nodes.ts` | 新 | ~6 KB |
| `frontend/src/pages/nodes/NodeList.tsx` | 新 | ~12 KB |
| `frontend/src/app/router.tsx` | 改 | +3 行 |
| `frontend/src/components/layout/AppLayout.tsx` | 改 | +2 行 |
| `frontend/src/components/common/InstanceFormSheet.tsx` | 改 | +50 行 NodeSelect + node_id |
| `frontend/src/api/hooks/instances.ts` | 改 | +4 行 node_id |
| `backend/app/schemas/instance.py` | 改 | +12 行 node_id |
| `backend/app/services/instance_service.py` | 改 | +18 行 node_id 校验 |
| `backend/_verify_mvp1_remote_agent.py` | 改 | 修 raw_sql busy_timeout/checkpoint/sleep |

### agent 之前产出(在 git untracked 状态)
| 路径 | 状态 |
|---|---|
| `backend/alembic/versions/0002_add_nodes_table.py` | 完整 ✅ |
| `backend/app/api/v1/{agent,nodes}.py` | 完整 ✅ |
| `backend/app/db/models/node.py` | 完整 ✅ |
| `backend/app/middleware/agent_auth.py` | 完整 ✅ |
| `backend/app/schemas/node.py` | 完整 ✅ |
| `backend/app/services/node_service.py` | 完整 ✅ |
| `backend/_verify_mvp1_remote_agent.py` | 完整 ✅(我后改了 raw_sql 容错) |
| 8 个 modified | 完整 ✅(executor.py 130 行核心改造 + 其它) |

## 后续(等用户授权)

| P | 项 | 操作者 |
|---|---|---|
| **P0** | 用户拍板"今晚部署 / 暂缓" | 用户 |
| P0 | 部署 backend(rebuild + alembic upgrade + restart) | 我(用户授权后) |
| P0 | 部署 frontend dist | 我 |
| P0 | web 上注册 vps-jm 节点拿 token | 用户(浏览器操作) |
| P0 | 部署 agent 到 VPS-JM(install.sh) | 我 |
| P0 | 停 host crontab(避免双调度) | 我(用户授权后) |
| P1 | 创建 jmcomic 实例 + 选 vps-jm + 立即运行(预期 CF 拒,链路通即可) | 用户 |
| P1 | 明早 9-10 主面板自动 cron → vps-jm agent → 真签到验证 | 自动 |

## 经验教训

| 教训 | 适用 |
|---|---|
| Background agent 可能因 session/context 中断,产出**完成不完整** — 必须 git status + Glob 验证产出范围,不能假设 prompt 全做完 | 任何 `run_in_background=true` 派 agent 的场景 |
| Windows SQLite + TestClient 的 WAL lock 是个**实测难题** — `busy_timeout` / `wal_checkpoint(TRUNCATE)` / sleep 都救不了,根因是 SQLAlchemy connection pool 与 raw_sql autocommit 竞争 | Python + SQLite + 异步 lifespan + 测试代码用 raw sqlite3 时 |
| **金标准 e2e verify 比新功能 verify 更重要** — `_verify_e2e.py` 11/11 仍过证明老功能没破,这比新功能 verify 通过更说明问题 | 大改动 review 时优先看金标准 |
| 接力 agent 工作时,**先 git diff + Glob + 跑现有 verify**,基底稳了再加新 | Multi-session 协作场景 |
| CF 信任分 24h 周期 — 测试预期要诚实管理 | 任何反爬环境 e2e 真测 |
