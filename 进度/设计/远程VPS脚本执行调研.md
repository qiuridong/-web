# 远程 VPS 脚本执行(Multi-Node)调研

> **状态**:📝 调研稿(2026-05-19),**不动手实施**,等用户看完做选型。
>
> **需求来源**:用户希望"主面板能管理跨 VPS 的脚本",理由:多 VPS 分散签到 IP 避免风控集中 / 用其他地区 VPS 解锁地区限制 / 资源隔离 / 多账号分机器。
>
> **本调研不下结论,列 6 种方案 + 利弊 + 工程量,最后给推荐 + MVP 切片建议。最终选型由用户拍板**。

---

## 1. 需求理解

### 1.1 用户场景(推断)

```
[ jb.aijiaxia.cc 主面板 ] ←— 浏览器(管理员)
     │
     ├─ 本机 VPS-A (154.9.238.144)  ← 当前:跑 coklw + ptfans
     ├─ 远程 VPS-B (X.X.X.X)        ← 想加:跑别的脚本 / 同脚本不同账号
     ├─ 远程 VPS-C (Y.Y.Y.Y)        ← 想加
     └─ ...
```

**用户视角期望**:
- 浏览器打开 `/scripts/ptfans/instances` → 看到所有 VPS 上的 ptfans 实例(VPS-A 一个、VPS-B 一个),可分别配 cookie / cron
- 点"立即运行" → 在该实例所属 VPS 上跑
- 看日志、改配置、改 cron → 都是统一界面,不需要 SSH 到各 VPS
- 通知规则统一,所有节点失败都汇总到主面板,推到 Telegram / 微信

### 1.2 业务驱动(为什么不能"在每个 VPS 部署一份完整面板")

| 驱动 | 痛点 |
|---|---|
| 统一管理 | N 个 VPS = N 个面板登录 = 心智成本爆炸 |
| 统一历史 | 各机各 DB,无法横向看"所有签到今日成功率" |
| 统一通知 | 各机配各通知渠道,推送会爆炸/漏 |
| 统一升级 | 改一处代码,N 个面板都要 deploy |
| 节省资源 | 远程 VPS 不需要完整 React + nginx + cron 引擎,只需要"执行器" |

---

## 2. 6 种架构选项

### 选项 A · **Agent 探针式 + 长连接(WebSocket)**

```
┌── 主面板 jb.aijiaxia.cc ──┐         ┌── 远程 VPS-B ──┐
│  FastAPI + Scheduler      │ ←─────→ │ signin-agent   │
│  Web UI / API             │  ws/wss │ (Python 单 bin)│
│  DB (instances/runs)      │         │ httpx / asyncio│
└───────────────────────────┘         └────────────────┘
```

**通信**:agent 启动后主动 dial 主面板的 `/ws/agent/{node_id}`,**长连接挂着**。主面板要触发任务时,通过这条连接 push `{ "type": "run", "instance_id": 5, "config": {...} }`。agent 跑完回传 `{ "type": "result", "run_id": ..., "stdout": ..., "status": "success" }`。

**类似项目**:
- **哪吒探针(nezha)** — 主流,Go 写,gRPC 双向流(理念一致,实现细节不同)
- **Portainer Edge Agent** — Docker 多主机管理
- **Sentry / DataDog agent** — 监控类

**优点**:
- 实时性最好(主面板 push 立刻到 agent)
- 单连接 keep-alive,流量低
- 跨网络无障碍(agent 主动出站到主面板 ws,**不需要 VPS-B 有公网入站**,适配 NAT / 防火墙)

**缺点**:
- 长连接断开重连逻辑复杂(网络抖动 / 主面板重启)
- 主面板需要 WebSocket 路由 + 连接池
- 日志流式回传需要分块设计
- WS 鉴权要做(token / mTLS / IP 白名单)

**工程量**:🟡 **中等-高**(40-60 小时)
- agent CLI(~500 行 Python):配置加载 / WS client / 任务执行 / 日志回传 / 心跳 / 重连
- 主面板侧:WS 路由 + 节点注册 / 任务派发 / 状态聚合(~600 行)
- 协议设计(JSON Lines over WS)
- DB schema:新增 `nodes` 表 + `instances.node_id` 外键

---

### 选项 B · **Agent + 短轮询(Pull 模式)**

```
┌── 主面板 ──┐                ┌── 远程 VPS-B ──┐
│  HTTP API  │ ←——HTTPS poll—— │ signin-agent   │
│            │  every 10-30s    │                │
└────────────┘                  └────────────────┘
```

**通信**:agent 定期(10-30 秒)HTTPS GET `/api/v1/agent/{node_id}/pending`,看主面板有没有派发给自己的任务。有就拉下来执行,跑完 POST `/api/v1/agent/{node_id}/runs/{run_id}/result` 回传。

**类似项目**:
- **GitHub Actions self-hosted runner** — 完美类比!HTTP long-polling + agent
- **GitLab Runner** — 同上
- **Drone CI agent** — 同上

**优点**:
- 实现极简(纯 HTTP,无 WS)
- 网络穿透好(agent 主动出站,适配 NAT)
- 错误恢复自然(下一次 poll 就重试)
- 主面板侧无状态(不维护连接池)
- 安全模型简单(HTTPS + Bearer Token 完事)

**缺点**:
- 实时性差(平均延迟 = poll 间隔 / 2)
- 立即运行体验:用户点按钮 → 等待 5-15 秒(下次 poll 才取到任务)
- 大量节点时 poll 流量浪费

**实时性优化**:long polling(请求挂 30 秒,有任务立刻返回,没任务超时返回 empty),实时性接近 WS,实现仍简单。

**工程量**:🟢 **中等**(25-40 小时)
- agent CLI(~400 行):配置 / HTTP client / poll loop / 任务执行 / 日志回传
- 主面板:5-6 个 agent 专用端点 + 任务队列(可以直接用 DB 的 runs 表 status='pending')
- DB schema:nodes 表 + instances.node_id

---

### 选项 C · **主面板 SSH 远程执行(无 Agent)**

```
┌── 主面板 ──┐                ┌── 远程 VPS-B ──┐
│ paramiko / │ ——SSH key——→  │ 系统 sshd      │
│ asyncssh   │  立即运行时连接 │ 临时跑 python  │
└────────────┘                └────────────────┘
```

**通信**:主面板存所有 VPS 的 SSH 私钥,触发任务时:
1. SSH 连接 VPS-B
2. `scp` 推送脚本代码(或者预先 rsync 全部 scripts/ 到 VPS-B)
3. `ssh ... python /tmp/sandbox_runner.py < config.json > result.json`
4. SSH 回传 result.json + stdout/stderr
5. 关连接

**优点**:
- **零 agent 安装**(VPS 只要 sshd + python)
- 适合临时实验性 VPS(开新 VPS → 加 SSH key → 立刻能管)
- 实现极简
- 利用现有 sandbox_runner.py,无需新协议

**缺点**:
- 主面板存所有 VPS 的 SSH 私钥 = **单点泄露 = 所有 VPS 沦陷**
- 长任务(coklw 30 分钟随机延迟)需要保持 SSH 连接 = 网络不稳容易崩
- 日志实时回传困难(SSH stdout 走 PTY 缓冲)
- 无心跳 / 离线感知(只有触发才知道 VPS 死没死)
- VPS 状态(在线 / CPU / 内存)看不到

**工程量**:🟢 **低**(15-25 小时)
- 主面板装 `asyncssh` / `paramiko`
- 加 nodes 表(存 host:port / SSH user / private key path)
- executor.py 加 `RemoteSshExecutor`
- 没有 agent 要写

**最大风险**:主面板被入侵 → 所有 VPS 的 SSH key 在 `data/` 下 → 攻击者 SSH 进所有 VPS。

---

### 选项 D · **Reverse SSH Tunnel + 选项 C 的 SSH 执行**

```
┌── 主面板 ──┐               ┌── VPS-B(NAT/无公网)──┐
│ sshd 监听  │ ←—tunnel from— │  autossh 反向出站      │
│ tunnel 端  │   VPS-B          │  把本地 22 转发到主面板│
└────────────┘                 └────────────────────────┘
```

**通信**:VPS-B 用 `autossh -R 2222:localhost:22 user@主面板`,主面板访问 `localhost:2222` 就等同 SSH 到 VPS-B。

**优点**:
- 解决 NAT 后 VPS 无公网入站问题
- 复用选项 C 的执行机制

**缺点**:
- 配置复杂(每个 VPS 一个不同的 tunnel 端口)
- 主面板需要管理一堆 sshd 监听端口
- 反向 tunnel 不稳定,需要 autossh 守护

**工程量**:🟡 **中等**(选项 C + 反向 tunnel 配置)

---

### 选项 E · **Federation 联邦(每个 VPS 跑完整 backend)**

```
┌── 主面板 jb.aijiaxia.cc ──┐
│  Web UI 聚合层             │
│  ↓ API 调用各节点          │
└─────┬──────┬──────┬───────┘
      │      │      │
   [VPS-A] [VPS-B] [VPS-C]  ← 每个都跑完整 FastAPI + scheduler
   完整后端 完整后端 完整后端
```

**通信**:主面板 UI 调用各 VPS 的 `/api/v1/instances` 等,自己只做聚合(类似 Mastodon 联邦)。

**类似项目**:
- **Mastodon** / **Pleroma** 联邦
- **Cluster API** / **Federated Prometheus**(metrics 联邦)

**优点**:
- 节点自治(VPS-B 挂了不影响别人)
- 横向扩展无瓶颈
- 复用现有代码(每个节点装当前面板就行)

**缺点**:
- 资源浪费(每 VPS 完整 React + FastAPI + nginx + APScheduler)
- UI 必须每次聚合多节点 API(慢、复杂)
- 配置漂移(各节点版本可能不一致)
- 跨节点鉴权 / 加密复杂(每节点一份 key)
- **完全是 overkill**,签到场景用不上联邦的核心价值

**工程量**:🔴 **极高**(80+ 小时,需要重写大部分 UI)

---

### 选项 F · **基于 Tailscale / Wireguard 组网 + 选项 A/B/C 之一**

```
┌── Tailnet(私有覆盖网络)───────────┐
│  jb.aijiaxia.cc → 100.x.x.1        │
│  VPS-B → 100.x.x.2                  │
│  VPS-C → 100.x.x.3                  │
└─────────────────────────────────────┘
   所有节点都能互相直连私有 IP
```

**通信**:不是独立方案,是给 A/B/C 加一层 transport。VPS 加入 Tailnet → 主面板用 Tailnet IP 调 VPS 的内部 API(不暴露公网),mTLS 自动由 Tailscale 处理。

**优点**:
- 网络层透明(对应用代码零侵入)
- 自动加密(WireGuard)
- NAT 穿透 / 公网 IP 都行
- Tailscale 免费版个人足够(20 节点)

**缺点**:
- 依赖 Tailscale(SaaS)或自建 Headscale(增加运维)
- 多一层依赖

**工程量**:🟢 **低**(Tailscale 安装 5 分钟一节点)+ A/B/C 之一

---

## 3. 类似项目对照表

| 项目 | 模式 | 通信 | 优势对你的项目 |
|---|---|---|---|
| **哪吒探针 nezha** | Agent + 长连接 | gRPC bidi | 完整生产成熟,代码可借鉴 |
| **GitHub Actions self-hosted runner** | Agent + 长轮询 | HTTPS poll | **架构与你需求极相似**(中心调度 + 远程执行) |
| **GitLab Runner** | Agent + 长轮询 | HTTPS poll | 同上 |
| **Portainer Edge Agent** | Agent + WebSocket | WSS | Docker 主机管理参考 |
| **Pterodactyl Wings** | Agent + WebSocket | WSS | 游戏面板,有日志流式 |
| **Mastodon Federation** | Federation | HTTP | 多节点理念参考 |
| **AWX / Ansible Tower** | Agent-less SSH | SSH | 类选项 C 的成熟实现 |
| **青龙面板** | **单机为主**,有"docker-cli 多机" | — | 不太适配你的场景 |

---

## 4. 推荐方案

### 🌟 推荐 — **选项 B(Pull Agent + Long Polling)** 作为主路线

**理由**:
1. 与你"个人 / 小团队"规模匹配(2-10 个 VPS,不是百节点)
2. 实施成本中等(25-40 小时),不像选项 A WS 那样复杂
3. **GitHub Actions runner 是黄金范本**,架构久经考验
4. agent 主动出站,VPS 不需要公网入站(NAT / 防火墙友好)
5. 主面板无状态,WS 连接池等复杂性都没有
6. 鉴权简单:HTTPS + Bearer Token,token 在 VPS 部署时生成
7. 实时性可以靠 long polling 提升到接近实时(用户点立即运行 → 1-2 秒延迟)

**可选叠加**:**+ Tailscale**(选项 F)给所有节点组私有覆盖网络,主面板和 agent 通信走 Tailnet,不暴露任何公网端口。零额外代码,但运维稳健性大幅提升。

### 🥈 备选 — **选项 C(SSH 远程执行)** 作为快速 MVP 验证

如果你想**先验证用户场景**(2-3 天搞个原型试试),选项 C 是最快路径:
- 工作量小(15-25 小时)
- 用户操作不变(主面板 UI 已有,只是 executor 多一种)
- **但安全性弱**(主面板存所有 VPS SSH key),不建议长期生产用

可以先 SSH MVP → 用户用一阵看是否真有跨 VPS 需求 → 满意了再上 agent 方案。

---

## 5. 安全模型(任何方案都必须满足)

| 风险 | 缓解 |
|---|---|
| 主面板被入侵 → 控制所有 VPS | agent token 只能"执行注册的脚本",不能"拿 shell"; secret 字段加密下发,VPS 解密后立刻 wipe |
| Agent token 泄露 | token 一节点一份(node_id 绑定),可单独 revoke;有 rate limit + IP 校验 |
| 主密钥 `encryption.key` 分发 | **不分发**!主面板加密 cookie/token,下发**已解密的明文**到 agent(走 TLS),agent 跑完立刻销毁。agent 永远拿不到主密钥 |
| 中间人攻击 | 强制 HTTPS;选项 F 走 WireGuard 自动加密;选项 A 可加 mTLS |
| Agent 自己被入侵 | agent 用 unprivileged user(非 root)跑;agent 进程隔离(像主面板那样的 sandbox_runner)|
| 网络分区 / 主面板挂掉 | agent 可独立维持"上次拿到的任务计划"在本地 cron 跑(降级模式)— 但本期 MVP 可不做 |

---

## 6. 工程量估算(选项 B + 适度 MVP 切片)

### MVP-1(最小可用,~10-15 小时)

**目标**:1 个远程 VPS,1 个脚本,能立即运行 + 看日志

- [ ] 后端:`nodes` 表 + `instances.node_id` 外键
- [ ] 后端:`/api/v1/agent/poll` + `/api/v1/agent/result` 2 个端点(Bearer token 鉴权)
- [ ] 后端:executor 改造,instance.node_id != local → 派给 agent,instance.node_id == local → 走现有 sandbox
- [ ] Agent:Python CLI ~200 行,从 token 配置 / poll loop / 执行 / 回传
- [ ] 前端:实例编辑表单加"节点"下拉(默认本机)
- [ ] 部署 agent 到 VPS-B(单文件 + systemd unit)
- [ ] Smoke test:在 VPS-B 上跑一次 coklw

### MVP-2(加固生产,~10-15 小时)

- [ ] 节点心跳 + 在线状态(`/dashboard` 显示节点列表)
- [ ] 日志流式回传(SSE 转发 agent stdout)
- [ ] 节点离线处理(任务超时 → 标 failure / 自动转移到其他节点)
- [ ] Agent 自动升级机制(主面板下发新版本)
- [ ] 多节点 RR / Pin 调度策略(同一脚本多账号自动分配到不同节点)

### MVP-3(高级,~15-20 小时)

- [ ] 节点资源监控(CPU / 内存 / 上次签到时间)
- [ ] 节点间脚本同步(主面板上传脚本 → 自动 rsync 到所有 agent)
- [ ] 多区域路由(脚本声明 `prefer_region: "us"`,自动选 us 节点)
- [ ] Web UI 节点管理(添加 / 删除 / 改名 / revoke token)

**总计**:**~35-50 小时**(选项 B 完整路线)

---

## 7. DB Schema 增量(任何方案都要做)

```sql
-- 节点表
CREATE TABLE nodes (
    id INTEGER PRIMARY KEY,
    slug VARCHAR(64) UNIQUE NOT NULL,  -- 'local' / 'vps-b' / 'vps-c'
    name VARCHAR(128),                  -- 显示名
    description TEXT,
    is_local BOOLEAN DEFAULT 0,         -- True = 主面板自己
    auth_token_hash VARCHAR(128),       -- agent token bcrypt
    last_seen_at TIMESTAMP,             -- 最近心跳
    version VARCHAR(32),                -- agent 版本
    metadata_json TEXT,                 -- IP / region / CPU 等
    enabled BOOLEAN DEFAULT 1,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

-- 实例加节点关联
ALTER TABLE instances ADD COLUMN node_id INTEGER
    REFERENCES nodes(id) DEFAULT 1;  -- 默认 1=local

-- runs.host 已有,可直接用作 "在哪个 node 跑的" 标记
```

迁移:`alembic revision -m "add_nodes_table"` + 一条 SQL 插入 `local` 节点(id=1, slug='local', is_local=1)。

---

## 8. 未决 / 等用户拍板

按优先级降序:

| 问题 | 选项 | PM 建议 |
|---|---|---|
| **架构方案** | A / B / C / D / E / F | **B + F**(Pull agent + 可选 Tailscale) |
| **是否做 MVP-1 快速验证** | SSH(选项 C)先做 OR 直接上 agent | 用户场景明确就直接 B;不确定就先 C MVP 验证 |
| **支持几个 VPS** | 2-3 / 10 / 50+ | 设计支持 10,实际 2-3 起步 |
| **节点掉线策略** | 任务挂起 / 失败 / 迁移别节点 | 默认"挂起 + 主面板告警",失败和迁移做开关 |
| **是否同步 secret** | 加密下发 / 节点自存 | **加密下发**(主面板单点负责加密,agent 拿明文跑完即销毁,主密钥永不出主面板) |
| **agent 部署方式** | 单 Python 文件 / Docker / .deb | **单 Python 文件 + systemd unit**(最轻) |
| **agent 鉴权** | Bearer token / mTLS | **Bearer token**(运维简单);**Tailscale 提供网络层加密** |
| **是否给 agent 用 web UI** | 是 / 否 | 否,agent 纯无界面,管理走主面板 |
| **首期支持的脚本类型** | 与本地完全一致 / 子集 | 完全一致(agent 装 backend 的 sandbox_runner + 跑相同脚本目录) |
| **agent 与 backend 代码版本** | 必须一致 / 兼容 | 兼容(major.minor 匹配即可,patch 不限) |

---

## 9. 关键技术细节(选项 B 详解)

### 9.1 Agent 启动 + 注册

```bash
# VPS-B 上
wget https://jb.aijiaxia.cc/agent/signin-agent.py
python signin-agent.py register \
  --master https://jb.aijiaxia.cc \
  --token <一次性注册 token,管理员在主面板 UI 生成> \
  --node-name vps-hk-01

# agent 生成长期 token,落地 /etc/signin-agent/config.yaml
# 创建 systemd unit /etc/systemd/system/signin-agent.service
systemctl enable --now signin-agent
```

主面板侧:`/api/v1/agent/register` 端点,校验一次性 token,生成长期 token + 落 nodes 表 + 返回。

### 9.2 任务派发(Long Polling)

```python
# agent 端
while True:
    try:
        # GET /api/v1/agent/poll?node_id=X&wait=30
        # 主面板:有任务立刻返,无任务挂 30 秒后返 empty
        r = httpx.get(f"{MASTER}/api/v1/agent/poll",
                      headers={"Authorization": f"Bearer {TOKEN}"},
                      timeout=35)
        if r.status_code == 200 and r.json().get("task"):
            task = r.json()["task"]
            execute_task(task)  # 调用本地 sandbox_runner
    except (httpx.NetworkError, httpx.TimeoutException):
        time.sleep(5)
```

### 9.3 主面板派发逻辑

```python
# scheduler.executor 改造
def execute_run(instance, run_id, ...):
    if instance.node_id is None or instance.node.is_local:
        # 走现有本地 sandbox(零改动)
        return _local_execute(...)
    else:
        # 远程节点:在 DB 标 run.status=pending + node_id=X
        # agent 下次 poll 时拿走
        run.status = "pending"
        run.assigned_node_id = instance.node_id
        db.commit()
```

### 9.4 结果回传

```python
# agent 跑完 sandbox_runner
result = subprocess.run([...], ...)
# POST /api/v1/agent/runs/{run_id}/result
httpx.post(f"{MASTER}/api/v1/agent/runs/{run_id}/result",
           json={"status": "success", "stdout": ..., "stderr": ..., "exit_code": 0, ...},
           headers={"Authorization": f"Bearer {TOKEN}"})
```

### 9.5 日志流式(SSE 转发)

主面板 `/api/v1/runs/{run_id}/stream` 用户连 SSE:
- 本地 run:主面板自己 tail 子进程 stdout
- 远程 run:**主面板把这个 SSE 阻塞在数据库 `run.stdout` 字段变化上**(agent 每 1-2 秒 POST 部分 stdout 增量,主面板 SSE 推给浏览器)

---

## 10. 风险与陷阱

| 风险 | 严重度 | 缓解 |
|---|---|---|
| Agent 部署后忘记升级,与主面板协议不兼容 | 中 | API 版本号 header + 主面板拒绝旧 agent + UI 显示节点版本 |
| Agent 跑的脚本 import 不存在的库 | 高(常见!) | agent 安装时附带本地依赖管理(`uv pip install -r scripts/<slug>/requirements.txt`)|
| 时区不一致 | 中 | agent 端不做 cron 调度,只接受主面板派发的"现在跑"指令 |
| 网络不稳长任务中断 | 中 | agent 跑 30 分钟任务,中途网络断了 → 跑完后下次 poll 时回传(本地持久化结果到 spool/) |
| 主面板挂了,所有节点等待 | 高 | agent 加"独立模式 fallback"—— 上次拿到的任务计划本地缓存,主面板挂期间按缓存自跑(MVP-2 再做) |
| Secret 在 agent 端 swap 到磁盘 | 低 | agent 用 mlock / 写完就 close;sandbox 子进程一旦退出环境变量被回收 |

---

## 11. 不做的事(明确边界)

- ❌ **不做 K8s / Docker Swarm**(对 2-10 节点的签到场景是 overkill)
- ❌ **不做 service mesh**(Istio / Linkerd,完全不必要)
- ❌ **不做跨节点共享存储**(agent 各自维护本地数据目录,不需要 NFS / Ceph)
- ❌ **不做节点间互相调用**(只有主面板↔节点,无 mesh)
- ❌ **不做"agent 反向当 master"**(主面板就是单 master,挂了所有人都挂)
- ❌ **不做多 master 高可用**(个人项目,master 挂了就挂了,有数据备份就行)

---

## 12. 一句话总结

**推荐路线**:

> 上 **选项 B(Pull Agent + Long Polling)** 走完整路线,工程量 35-50 小时分 3 个 MVP 切。
> 若想 2-3 天先验证场景,先做 **选项 C(SSH MVP)**,用满意后再升级到 B。
> 任何方案叠加 **选项 F(Tailscale)** 网络层零代码提升安全和稳定性。

**等用户回**:

1. **A / B / C / D / E / F 选哪个?**
2. 要不要先做 C 的 SSH MVP 快速验证?
3. 第一个真实远程 VPS 在哪里(地区 / 提供商 / IP)?有几台?
4. 预算工程量:你能接受多少小时投入?
   - 10 小时 → 选项 C SSH MVP(单节点)
   - 25-40 小时 → 选项 B MVP-1(完整 agent + 单节点真用)
   - 50+ 小时 → 完整 B + 多节点 + 监控 + 自动升级
