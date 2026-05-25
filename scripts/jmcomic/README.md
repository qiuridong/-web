# JMComic(18comic.vip)每日签到 — selenium + 账密版

> **v1.0.0**(2026-05-23)— 基于 host VPS-JM 4-5 月 33 次验证过的 selenium + UC 流程改造,适配平台 sandbox_runner 协议。
>
> 历史:v2(cookie 复用 + 纯 httpx,因 cookie ↔ IP 强绑定 + cookie 失效需人工重抓,2026-05-23 废弃删除)。

## 工作流程

```
┌── 你 ──┐
│ 填账密 │ ──→ 主面板加密落库
└────────┘                  │
                            ↓ MVP-1 agent 派发
                  ┌── host Linux 节点(如 VPS-JM) ──┐
                  │ 1. Xvfb + Chrome UC 过 CF       │
                  │ 2. requests login                │
                  │ 3. POST /ajax/user_daily_sign    │
                  │ 4. 兜底 GET / 扫"已簽到"marker  │
                  │ 5. GET /logout                   │
                  └──────────────────────────────────┘
                            │
                            ↓ RunResult
                  ┌── 主面板 ──┐
                  │ /runs 详情 │
                  └────────────┘
```

## 部署节点要求(⚠️ 重要)

| 项 | 要求 | 推荐节点 |
|---|---|---|
| 操作系统 | Linux | Ubuntu 22.04 / 24.04 |
| 权限 | root / sudo(自动装 Chrome) | host 用户 |
| Python | ≥ 3.10 | 3.12 |
| 内存 | ≥ 1.5 GB | 2 GB+ |
| 磁盘 | ≥ 500 MB 余量 | — |
| 网络 | 能访问 18comic.vip + Chrome 下载 + apt source | — |
| **已实测节点** | **VPS-JM `38.55.132.186`** ✅ 33/33 验证 | **首选** |

### ❌ 主面板 Docker 容器**不能**直接跑

主面板 backend 跑在 Docker 容器里,**镜像没装 Chrome / Xvfb / seleniumbase**。
直接在主面板节点(`local`)创建实例 → 点立即运行 → 必失败。

**正确做法**:等 MVP-1 远程 agent 通了 → 把 jmcomic 实例的 `node_id` 绑定到 **VPS-JM**(那台 host 4 月起一直跑 selenium / Chrome 全套环境)。

## 准备工作(MVP-1 通了之后,2 分钟)

### Step 1:确认你的 JM 账号 + 密码

- 用户名 + 密码(就是登录 18comic.vip 那对凭证)

### Step 2:确认 VPS-JM 节点已注册到主面板

- 主面板"节点管理"页能看到 `vps-jm`(MVP-1 完成后会有)
- 状态 = `online`(agent 心跳正常)

### Step 3:创建实例

1. 主面板 → `/scripts/jmcomic` → 实例 Tab → 创建实例
2. **节点**:选 `vps-jm`(下拉)
3. **JM 用户名**:你的 JM 账号
4. **JM 密码**:你的 JM 密码(Fernet 加密落库,前端再不可见)
5. **随机延迟(秒)**:保持默认 3600(签到时刻落北京 09:00-10:00)
6. **Cron**:保持默认 `0 1 * * *`(UTC 01:00 = 北京 09:00)
7. 保存

### Step 4:第一次跑

- 实例 Tab 找到刚建的 → 点 **立即运行**
- /runs 详情页看 stdout:
  - 第一次会装 Chrome / Xvfb(~30 秒)
  - 然后正常签到流程
- 预期(账号未签):**绿色 success + message "签到成功: 您已經完成每日簽到,獲得 [ JCoin:N ] [ EXP:N ]"**
- 预期(账号已签):**绿色 success + message "今日已签到过了: ..."**

## 失效信号 → 处理速查表

| message 形态 | 真因 | 处理 |
|---|---|---|
| `username 或 password 字段为空` | 实例配置缺字段 | 编辑实例补字段 |
| `登录失败 status=2 errors=...` | 账密错(或 server 业务校验失败) | 重置 JM 密码,实例配置更新 |
| `经过 5 次重试仍未获取到 cf_clearance` | CF 没过(IP 信任分耗尽 / CF 升级) | 等 24h 自然恢复;若多日不行,**换节点 IP** |
| `sign 接口空响应 ... 疑似 server 反爬静默拒绝` | server 对自动化 sign 返空(5-23 事件) | 兜底首页 marker 会自动 fallback 转 success;若兜底也认未签,等 24h 再试 |
| `网络错误 ConnectTimeout / SSLError` | 节点 → 18comic.vip 网络异常 | 看节点网络;若节点在国内,可能要配置代理 |
| `依赖安装失败(可能权限不足或网络问题)` | apt 失败(无 root / 镜像源问题) | 节点需 root + 能访问 apt 源 |

每次失败时,Chrome 截图存到 `data_dir/cf_error_<ts>.jpg`,可在详情页 / 文件浏览查看。

## 字段诊断(/runs 详情页)

每次失败的 `RunResult.data` 会含完整诊断,可直接定位:

```json
{
  "category": "exhausted_retries",
  "error_class": "JmSignEndpointError",
  "endpoint": "POST /ajax/user_daily_sign",
  "url": "https://18comic.vip/ajax/user_daily_sign",
  "method": "POST",
  "status_code": 200,
  "content_type": "text/html; charset=UTF-8",
  "content_length": 0,
  "body_preview": "<empty>",
  "body_len": 0,
  "elapsed_ms": 156
}
```

## 平台协议遵循

- 入口:顶级 `run(config, context) -> RunResult`
- `success=True`:今日已签 / 真签到成功 — 都返 success(任务目标达成)
- `success=False`:CF 未过 / 账密错 / sign 接口异常 / 网络 / 依赖安装失败
- `data` 字段:含完整结构化诊断,前端 /runs 详情页可见
- 长 sleep 用 `_chunked_sleep`(支持 SIGTERM 中途中断)

## 安全说明

- `password` 字段 `type: secret` → Fernet 加密落库,API 响应自动脱敏为 `null + _secret_set`
- sandbox 子进程拿明文 config,跑完即销毁;**主密钥永不离开主面板**(MVP-1 agent 也只拿明文当次任务)
- ⚠️ JM 账号建议:
  - 开 2FA(若支持)
  - 使用与日常账号**不同的密码**
  - **不要**把账密贴到聊天 / 截图 / 公开 git 仓库

## 与 host 原脚本的关系

| 项 | host `/root/JMComic-Auto_Sign_in/` 原脚本 | 本插件(主面板 v1.0.0) |
|---|---|---|
| 代码来源 | GitHub `huo0yan/JMComic-Auto_Sign_in` | 改造自原脚本 |
| 凭证 | 硬编码 USERNAME/PASSWORD 在 .py 里 | 从实例 config 取(Fernet 加密) |
| 调度 | host crontab `0 1 * * *` | 平台 APScheduler(实例 cron 字段) |
| 日志 | 追加到 signin.log | 落 runs 表,前端 /runs 可视化 |
| 通知 | 无 | apprise 集成(可配 Telegram / 微信) |
| 多账号 | 不支持 | 支持(建多个实例) |
| 失败重试 | 3 次(硬编码) | max_retries 字段(可调) |
| 异常诊断 | 笼统打印 | 6 类异常 + 完整 diag 落 RunResult.data |
| 兜底首页 marker | 无 | ✅ 8 个繁简体 marker(5-23 关键修复) |
| 失败截图 | 写脚本目录 | 写实例独立 data_dir |

**强烈建议**:本插件上线后,**停掉 host crontab**(`crontab -e` 注释那行),避免双调度消耗 IP 信任分。

## 历史变更

- **v1.0.0** (2026-05-23):本版,基于 host 33/33 验证的 selenium + 账密流程,加 6 类异常 + diag + 首页 marker 兜底
- **v2(已删除)**:cookie 复用 + 纯 httpx 版,因 cookie ↔ IP 强绑定 + 失效需人工重抓,2026-05-23 决策废弃
