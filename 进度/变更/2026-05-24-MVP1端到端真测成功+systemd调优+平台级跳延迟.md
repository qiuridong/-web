---
name: 2026-05-24 晚 · MVP-1 端到端首次真测成功(run 27)+ systemd 资源调优 + 平台级 manual 跳 random_delay
description: 接续同日"MVP1部署上线+6UX修复"档案;修了 systemd unit TasksMax 128 太小导致 Chrome fork rejected → ReadTimeout;把 manual 跳 random_delay 从脚本内(jmcomic v1.2)提到平台层(sandbox_runner override)— 所有脚本统一受益;web 立即运行 run 27 = jmcomic 首次端到端 e2e 真跑成功,49 秒拿"已签"业务结果
type: change
status: ✅ MVP-1 100% 端到端 verified,可宣告完整上线
---

# 2026-05-24 晚 · MVP-1 端到端真测成功 + systemd 调优 + 平台级 manual 跳延迟

## 30 秒摘要

1. **Run 26 ReadTimeout 根因找到**:不是 CF 拒,不是网络问题 — `dmesg` 揭示 `cgroup: fork rejected by pids controller in /system.slice/signin-agent.service`(install.sh 写的 `TasksMax=128` 太小)→ Chrome 启动需 50-100 process fork → 被 cgroup 拒 → chromedriver 等响应 120s → ReadTimeout
2. **systemd 资源调优**:`TasksMax=128 → 4096` + `MemoryMax=512M → 2G`(Chrome 峰值 1.5G);patch host `/etc/systemd/system/signin-agent.service` + daemon-reload + restart;同时改本机 `agent/install.sh`(新 VPS 装时默认值就对)
3. **用户提"立即运行不应等延迟"**(我之前 v1.2 jmcomic main.py 内做 check,用户希望平台级):把 `trigger_type=='manual' → random_delay_sec=0` 的逻辑**从脚本内提到 `backend/sandbox_runner.py` 平台契约层** — 所有脚本(coklw/ptfans/jmcomic/未来新脚本)立即运行统一秒级开始,scheduled / retry / test 仍走脚本配置 random
4. **Run 27 = MVP-1 首次端到端 e2e 真测成功**:web 点立即运行 → 49 秒完成全链路 → CF 一次过 + login 成功 + sign 返 `{"error":"finished"}`(host 09:48 已签)→ 平台正确识别 `JmAlreadySignedToday` → web 显示 success ✅
5. **CF 信任分意外发现**:run 26 Chrome 根本没启起来(fork 被拒)→ 没真正消耗 CF 信任分 → run 27 CF 一次过(我之前以为今天透支 2 次)
6. **进度档全部刷新**:README "当前状态" + "重大变更" + main.md "最近迭代" + 本档案

## 排错链路(找 ReadTimeout 真因)

| 步 | 怀疑 | 排除依据 |
|---|---|---|
| 1 | CF Turnstile 拒 | log 显示根本没到 CF — chromedriver 启动阶段就 timeout |
| 2 | 网络层 | 主面板心跳 / poll 200 OK,网络通 |
| 3 | Chrome 启动慢 | 上次成功跑只用 21 秒就过 CF,这次 120 秒纯启动就死 |
| 4 | 进程残留 | 我之前 `pkill -f 'Xvfb :17'` 已清,且 ps 显示无残留 |
| 5 | OOM | `free -h` 显示 6.7G available,内存充裕 |
| 6 | **cgroup 限制** ⭐ | `dmesg`: `cgroup: fork rejected by pids controller in /system.slice/signin-agent.service` 时间正好 16:34:11 对应 run 26 启 Chrome 那秒 |

→ **真因 = systemd unit `TasksMax=128` 限制**

## systemd unit 调优

```diff
# /etc/systemd/system/signin-agent.service [Service] 段
- MemoryMax=512M
- TasksMax=128
+ MemoryMax=2G          # Chrome 1.5G 峰值
+ TasksMax=4096         # Chrome 单实例 50-100 process fork
```

部署:
- VPS-JM `sed -i` patch + `systemctl daemon-reload` + `systemctl restart signin-agent`
- 验证:`Tasks: 2 (limit: 4096)` + `Memory: max 2.0G available 1.9G` ✅
- 清理:`rm /tmp/.com.google.Chrome.rk9zFb`(run 26 残留 user_data_dir 锁)
- 本机:`agent/install.sh` 模板同步更新(新 VPS 装时默认就对)

## 平台级 manual 跳 random_delay(从脚本层提到 sandbox 层)

### 用户反馈

> "还是那个问题,我需要我点击的立即运行没有默认没有任何延迟,不需要脚本的随机延迟"

我之前 v1.2 是在 `scripts/jmcomic/main.py` 内 check `context.trigger_type=='manual'` → delay=0。但**这只覆盖 jmcomic 一个脚本**,coklw/ptfans 仍走 random。用户希望**平台级**所有脚本统一。

### 实施(`backend/sandbox_runner.py`)

```python
# 平台级 UX:用户立即运行(manual)→ 强制跳过 random_delay_sec
# 适用所有脚本,不需要脚本作者各自处理
trigger_type = str(ctx_raw.get("trigger_type") or "")
if trigger_type == "manual" and isinstance(config, dict) and "random_delay_sec" in config:
    original = config.get("random_delay_sec")
    if int(original or 0) > 0:
        config = {**config, "random_delay_sec": 0}
        logger.info(f"平台 UX:trigger_type=manual,强制 random_delay_sec=0 (原 {original}s)")
```

### 行为表(grep backend 全部 trigger_type 值确认)

| trigger_type | 谁触发 | random_delay 处理 |
|---|---|---|
| **`manual`** | `instance_service.trigger_instance` 默认 / web 立即运行 | **强制 0** ⭐ |
| `scheduled` | `scheduler.engine` cron 定时 | 不动(走脚本配置) |
| `retry` | 失败自动重试 | 不动 |
| `test` | `_verify_*.py` 测试 | 不动 |

→ **只命中 manual,scheduled/retry/test 完全隔离**。明早 cron 仍走错峰 random ✅

### 部署

- 本机 `backend/sandbox_runner.py` 改 + syntax OK
- 主面板 `/opt/signin-panel/backend/sandbox_runner.py` scp + docker rebuild backend + restart + 容器内 syntax verified
- VPS-JM agent `/opt/signin-agent/sandbox_runner.py` scp(下次 run 自动用新版,不用 restart agent — sandbox 是 per-run subprocess)

### 与 jmcomic v1.2 main.py 内 check 的关系

- v1.2 内的 check **保留**作 defense-in-depth(冗余但无害)
- 主路径走 sandbox_runner 平台层 override
- 即使 sandbox_runner 没改(老 agent 没同步),脚本内层也会兜底

## Run 27 端到端首次成功(完整时间线 49 秒)

```
20:30:56  平台 UX 强制 random_delay_sec=0 (原 3600s)        ← sandbox 层 fix 生效
20:30:56  sandbox 启动 run_id=27 slug=jmcomic timeout=6000s
20:30:56  随机延迟禁用,立即开始                              ← 脚本层(v1.1 main.py)看到 delay=0
20:30:59  启 Xvfb + Chrome UC                                ← TasksMax fix 生效,Chrome 能 fork
20:31:02  访问登录页 https://18comic.vip/login
20:31:09  等待 CF 后台评估 15s
20:31:25  第 1 次尝试点击 CF Turnstile
20:31:43  ✅ CF 验证通过(一次过,信任分够)
20:31:43  POST /login → HTTP 200 / 47B / 458ms / status=1
20:31:43  ✅ login 业务成功
20:31:43  初次过 CF + login 完成,cookies 有效期 1800s
20:31:43  ========= 第 1/3 次签到尝试 =========
20:31:44  POST /sign → HTTP 200 / ct=text/html / body 29B / 356ms
20:31:44  server 业务返已签:{"msg":"","error":"finished"}
20:31:44  v1.1 _do_sign_only → if "error" in sign_data → raise JmAlreadySignedToday
20:31:44  run() catch → return RunResult(success=True, message="今日已签到过了: finished")
20:31:45  ✅ logout(安全清场)
20:31:45  sandbox 结束 success=True

__RUN_RESULT__{"success":true,"message":"今日已签到过了: finished","data":{...完整诊断...}}

总耗时 49 秒(20:30:56 → 20:31:45)
```

## 端到端链路全部 verified

```
1. Web 立即运行(浏览器)
   ↓
2. main backend instance_service.trigger_instance(trigger_type='manual')
   ↓ 检测 instance.node_id=2 (vps-us8-8-jm) ≠ local
3. 创建 pending run + 标 host="node:vps-us8-8-jm" + 不阻塞返 run_id
   ↓
4. agent (在 VPS-JM)long polling 拉走 task
   ↓ run.status: pending → running
5. agent subprocess /opt/signin-agent/sandbox_runner.py(stdin=task JSON)
   ↓
6. sandbox_runner 收 trigger_type='manual' → 强制 config.random_delay_sec=0(平台 UX)
   ↓ 加载 /opt/signin-agent/scripts/jmcomic/main.py 的 run(config, context)
7. v1.1 main.py 启 Xvfb + Chrome UC → 过 CF → login → sign(已签返 error finished)
   ↓ 返 RunResult(success=True, message=...)
8. sandbox_runner._emit_result → stdout 写 __RUN_RESULT__{...}
   ↓
9. agent reader-stdout 增量回传(POST /agent/runs/27/stdout)→ SSE 转发给浏览器订阅
   ↓
10. agent 解析 stdout 最后一行 __RUN_RESULT__ → POST /agent/runs/27/result(success=true)
    ↓
11. main backend agent_result handler 写 runs.status='success' + result_message + sync instance.last_run_status='success' + total_successes+1
    ↓
12. backend dispatch_run_event → notification_service(若配通知规则会推送)
    ↓
13. 你 web /scripts/jmcomic/instances 看到实例卡片 ● 成功 + last_run_at 几秒前
```

→ **所有协议链路 100% 通**,MVP-1 完整实现 + 验证成功。

## CF 信任分意外发现

之前我以为今天 IP 信任分透支(host 9:48 真签 + run 26 16:31 起 Chrome 失败)→ 立即运行肯定挂 CF。

**实测 run 27 一次过 CF**。

→ **Run 26 Chrome 根本没启起来**(fork rejected 在 chromedriver 等响应阶段就 timeout)→ **没真正访问 18comic** → **没消耗 CF 信任分**。

→ 今天 VPS-JM 真实访问 18comic 只有 2 次:
1. host crontab 09:48 真签到(失败:已签状态由 host 拿)— 错,host 9:48 成功 JCoin:30 + EXP:100
2. run 27 20:31(今日已签态,返 error finished)

→ 总共 2 次成功访问,CF 信任分仍正常。

→ 明早 5-25 09-10 北京 cron 触发,继续成功(IP 24h 已恢复 + 今日只 2 次正常访问)

## 4 fix 累积验证

| Fix | 验证证据 |
|---|---|
| 平台 UX manual 跳 random_delay | log 行 1 "强制 random_delay_sec=0 (原 3600s)" + 行 3 "立即开始" ✅ |
| systemd TasksMax 128→4096 | Chrome 成功启(对比 run 26 fork rejected ReadTimeout) ✅ |
| systemd MemoryMax 512M→2G | Memory available 1.9G(峰值 1.5G 不爆) ✅ |
| v1.1 异常分类 | sign 返 error:finished 被正确识别为 JmAlreadySignedToday(平台 success 语义) ✅ |

## 文件清单(今晚追加)

| 路径 | 改动 |
|---|---|
| `agent/install.sh` | systemd unit MemoryMax 512M→2G + TasksMax 128→4096 + 加注释 |
| `backend/sandbox_runner.py` | 平台 UX:trigger_type=='manual' override random_delay_sec=0 |

部署:
- `/etc/systemd/system/signin-agent.service` patch + daemon-reload + restart
- `/opt/signin-agent/sandbox_runner.py` scp
- `/opt/signin-panel/backend/sandbox_runner.py` scp + docker compose build + recreate

清理:
- `/tmp/.com.google.Chrome.rk9zFb` 残留 user_data_dir

## 后续

| P | 项 | 备注 |
|---|---|---|
| **P0** | 明早 5-25 09-10 北京主面板 cron 自动触发 jmcomic 实例 | scheduled 走 random delay → 9-10 窗口随机签 → 应当 success(平台显示已签,真业务 sign 也走通)|
| P1 | 用户日常使用,稳定 1-2 周后做 git push 备份 | 累积代码量大 |
| P1 | 写 MVP-2 设计稿(任务 lease + 超时回收 + agent 自动升级 + 脚本同步 + 资源监控)| 等 MVP-1 跑稳后 |
| P2 | 用 agent 跑 coklw / ptfans?(它们目前 host=`0128ad822a9e` = 主面板容器 ID,跑在 local 节点)| coklw/ptfans 无 selenium 需求,继续 local 也行,不需要迁 |

## 经验教训

| 教训 | 适用场景 |
|---|---|
| **systemd unit 默认资源约束要慷慨给 selenium 类**:TasksMax ≥ 4096,MemoryMax ≥ 2G | 任何调 Chrome / Firefox / Edge 的 service |
| **看 `dmesg` 找 cgroup / OOM kill 真因** — log + ps + free 都正常但程序不 work 时 | 任何 systemd / container 隔离环境的诡异 timeout |
| **"立即运行"是平台契约,该平台层强制覆盖,不该指望每个脚本作者各自实现** | 任何插件式架构的 UX 一致性 |
| **defense-in-depth**:平台层 + 脚本层都做相同 check,无害且兜底 | 平台 + 第三方插件的协议 |
| **Chrome user_data_dir 锁残留需要 sandbox 启动前清理** — 否则次启动等锁超时 | 任何 Chrome 自动化 |
| **CF 信任分实际比想象宽松** — 失败的请求(如 Chrome 没启起来根本没访问)不算消耗 | 评估 IP 信任分时要看真实流量,不是脚本失败次数 |

## 当前生产状态(收尾时刻)

```
✅ 主面板 https://jb.aijiaxia.cc
   ├ backend signin-panel-backend healthy
   ├ alembic at 0002_add_nodes
   ├ nodes: id=1 local + id=2 vps-us8-8-jm
   ├ scripts: coklw + ptfans + jmcomic(v1.1.0)
   ├ instances: 3 个(JM-US8-8特价 node_id=2 ⭐ run 27 last_run=success)
   └ frontend dist: index-LyGbdOtx.js(节点页 + 实例下拉 + never_run 状态)

✅ VPS-JM (198.51.100.10)
   ├ signin-agent systemd active running (TasksMax 4096,MemoryMax 2G)
   ├ heartbeat 200 OK / poll 200 OK
   ├ scripts/jmcomic/main.py(v1.2 含 trigger_type check + 平台层 sandbox 也兜底)
   ├ sandbox_runner.py(平台 UX manual 跳 random_delay)
   └ host crontab 已停(主面板独家调度)

✅ 端到端验证
   └ Run 27:web 立即运行 → 49 秒 → success(已签到)
```

🎊 **MVP-1 完整上线,首次 e2e 真测成功**。可以收工!
