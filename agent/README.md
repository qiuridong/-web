# signin-agent — 签到管家远程节点 agent

> **v1.0.0**(2026-05-24)— 配合主面板 MVP-1 远程 agent 架构。
>
> 设计稿:[`进度/设计/远程VPS脚本执行调研.md`](../进度/设计/远程VPS脚本执行调研.md)

## 一句话定位

让主面板能跨 VPS 调度签到任务 — agent 装在远程 VPS(如 VPS-JM),主动 HTTPS long-polling 主面板拉任务,本地用 sandbox_runner 跑 v1 之类脚本,跑完回传结果。

## 架构

```
[ 主面板 jb.aijiaxia.cc (154.9.238.144) ]
    │
    │ HTTPS long-polling(agent 主动出站)
    ▼
[ VPS-JM (198.51.100.10) ]
    └ signin-agent (systemd)
        ├ GET /api/v1/agent/poll?wait=30 ← 拉 task
        ├ subprocess /opt/signin-agent/sandbox_runner.py < stdin
        │   └ exec scripts/jmcomic/main.py(v1.1)
        │       └ Chrome + Xvfb 过 CF → 真签到
        ├ POST /api/v1/agent/runs/{id}/stdout(增量日志)
        ├ POST /api/v1/agent/runs/{id}/result(终态)
        └ POST /api/v1/agent/heartbeat(每 30s)
```

## 一键安装(推荐)

### Step 1:主面板上注册节点拿 token

1. 打开 `https://jb.aijiaxia.cc/nodes`(MVP-1 前端节点页)
2. 点 **添加节点**
3. 填:
   - slug: `vps-jm`(只能小写字母数字连字符)
   - name: `VPS-JM(原 JMComic 节点)`
   - description: 可选
4. 提交 → 主面板返回**一次性明文 token**(形如 `sa_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`)
5. **立刻复制 + 保存**(刷新页面就再也看不到了,需要重新生成 token)

### Step 2:scp 安装包到目标 VPS

```bash
# 从主面板 / 本机 上传 agent/ 目录 + sandbox_runner.py 到目标 VPS
scp -r agent/ root@VPS-JM_IP:/tmp/
scp backend/sandbox_runner.py root@VPS-JM_IP:/tmp/agent/
```

### Step 3:在目标 VPS 执行 install.sh

```bash
ssh root@VPS-JM_IP
cd /tmp/agent
sudo bash install.sh \
  --master https://jb.aijiaxia.cc \
  --token sa_REPLACE_WITH_REAL_TOKEN \
  --node-slug vps-jm
```

install.sh 自动:
- 装 `httpx + PyYAML`(系统 pip)
- 创建目录 `/opt/signin-agent` + `/etc/signin-agent` + `/var/log/signin-agent` + `/var/lib/signin-agent/data`
- 部署 `signin_agent.py` + `sandbox_runner.py` 到 `/opt/signin-agent/`
- 写 `/etc/signin-agent/config.yaml`(chmod 600)
- 写 systemd unit + `systemctl enable --now`

### Step 4:部署脚本到 agent 节点

```bash
# 主面板 → agent 节点,把 scripts/jmcomic 同步过去
scp -r /opt/signin-panel/scripts/jmcomic root@VPS-JM_IP:/opt/signin-agent/scripts/
```

### Step 5:验证

```bash
# 在目标 VPS:
systemctl status signin-agent           # 看运行状态
journalctl -u signin-agent -f           # 实时日志
tail -f /var/log/signin-agent/agent.log # 文件日志
```

成功状态长这样:
```
[INFO] signin-agent 1.0.0 启动,master=https://jb.aijiaxia.cc
[INFO] ✓ python_bin: /usr/bin/python3
[INFO] ✓ sandbox_runner: /opt/signin-agent/sandbox_runner.py
[INFO] ✓ scripts_dir: /opt/signin-agent/scripts (已部署 1 个: ['jmcomic'])
[INFO] ✓ data_dir: /var/lib/signin-agent/data
[INFO] ✓ 主面板连通,节点 id=2 slug=vps-jm
```

## 配置

`/etc/signin-agent/config.yaml`(完整字段见 `config.example.yaml`):

| 字段 | 说明 | 默认 |
|---|---|---|
| `master_url` | 主面板地址 | (必填) |
| `node_token` | agent token,主面板创建节点时返回 | (必填) |
| `scripts_dir` | 脚本目录 | `/opt/signin-agent/scripts` |
| `python_bin` | Python 解释器 | `/usr/bin/python3` |
| `sandbox_runner` | sandbox_runner.py 路径 | `/opt/signin-agent/sandbox_runner.py` |
| `data_dir` | 实例 data_dir 根 | `/var/lib/signin-agent/data` |
| `timezone` | 时区(子进程 TZ env) | `Asia/Shanghai` |
| `log_level` | 日志级别 | `INFO` |

改完配置后必须 `systemctl restart signin-agent`。

## 工作原理

### 主循环
```
while True:
  task = GET /api/v1/agent/poll?wait=30
  if task:
    cwd = scripts_dir/<slug>/
    subprocess.run([python, sandbox_runner.py], stdin=json, cwd=cwd, ...)
    # 后台 2 个线程读 stdout/stderr,每 1.5s 批量 POST /runs/{id}/stdout
    parse __RUN_RESULT__ from stdout last line
    POST /runs/{id}/result {success, message, data, exit_code, stdout, stderr}
```

### 心跳
后台线程每 30s POST `/api/v1/agent/heartbeat`(带 agent_version + metadata),让主面板 `nodes.last_seen_at` 保持新鲜。

### 鉴权
所有请求带 `Authorization: Bearer <node_token>`。主面板 middleware bcrypt 校验。

## 故障排查

| 现象 | 可能原因 | 处理 |
|---|---|---|
| `heartbeat 401` | token 错 / 节点被 disabled | 检查 config.yaml + 主面板节点状态 |
| `脚本未部署到 agent 节点` | scripts_dir 缺 main.py | scp 主面板 scripts/<slug>/ 过来 |
| `子进程 exit=126 / 127` | python_bin 不存在 / 权限不对 | 检查 python_bin 配置 |
| `_RUN_RESULT__ 未输出` | 脚本 crash / 没用 sandbox_runner 协议 | 看 stderr + 检查脚本契约 |
| agent log 一直 `poll 网络错误` | 主面板不可达 / DNS 问题 | curl 测主面板 /health |

## 卸载

```bash
sudo systemctl disable --now signin-agent
sudo rm /etc/systemd/system/signin-agent.service
sudo rm -rf /opt/signin-agent /etc/signin-agent
sudo systemctl daemon-reload
# 保留日志和 data 目录(可手动删 /var/log/signin-agent + /var/lib/signin-agent)
```

## 与原 host crontab 协同

如果目标 VPS 上仍有原签到脚本(如 `/root/JMComic-Auto_Sign_in/run.sh` 的 crontab):
- **强烈建议先停掉 host crontab**,让主面板 web 实例独家调度
- 否则同 IP 同账号一天 2 次签到会撞 CF 信任分 + JM server daily flag

```bash
crontab -l > /root/.crontab.backup.pre-agent
crontab -e
# 注释掉 jmcomic 那行
```

## 限制 / MVP-2 范围

v1.0.0 不做:
- 任务 lease + 超时回收(agent 拉走 task 后崩 → run 永远 stuck running,需手动 cancel)
- agent 自动升级(改 signin_agent.py 后需手动 scp + restart)
- 脚本自动同步(scripts/ 改完需手动 scp,agent 不会从主面板拉)
- 多 agent 抢同一节点(假设一节点只装一份 agent)

以上都是 MVP-2 范围。
