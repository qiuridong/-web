# 签到脚本聚合管理面板

> 把零散的签到脚本统一到一个 Web 控制台。服务器 7×24 自动调度,浏览器一站式管理,失败可推通知。
>
> **个人 / 小团队自用**,Ubuntu 24 + Docker Compose 单机部署。

## 🆚 vs 青龙面板(为什么不是再造一个青龙)

> **"青龙是仓库,签到管家是精装公寓"**
> 青龙优先**生态广度**(任意脚本能跑、社区共享),签到管家优先**架构深度**(强契约 / 字段加密 / 沙箱隔离 / 结构化诊断 / 业务弹性)。

| 维度 | 青龙面板 | **签到管家** |
|---|---|---|
| **每脚本配置** | 全局 env 表 + 手动关联 | **manifest fields → 自动生成 UI 表单**(11 种字段类型) |
| **字段加密** | env plaintext | **Fernet 字段级 + 主密钥 600 权限** |
| **子进程沙箱** | 容器内直跑 | **独立 sandbox_runner + 进程组 killpg + sys.path 隔离防 import app.*** |
| **失败诊断** | stderr 自己看 | **结构化 RunResult.data**(category/error_class/endpoint/body_preview/status_code) |
| **业务弹性** | 基本无 | **重试 + session 复用 + cookies TTL 自管理 + 业务 marker 兜底** |
| **多节点(MVP-1)** | 单机为主 | **Pull Agent + Long Polling**(类 GitHub Actions self-hosted runner) |
| **UI** | 2020-2022 风 | **shadcn + Tailwind v4 + OKLCH 配色 + 深浅色 + ⌘K 命令面板** |
| **通知** | 9 种内置 | **apprise 80+ 渠道** |
| **学习曲线** | 全局 env 找半天 | **复制现有 manifest.yaml 改 30 分钟一个新脚本** |
| 适合谁 | 想要现成脚本社区生态 | **个人/小团队、在意 UI + 安全、愿意自己写脚本** |

## ✨ 核心特性

- 🧩 **插件化脚本**:扔目录就识别(扫描即入库),无需改主程序代码
- 📋 **强契约 manifest**:**11 字段类型**(string/secret/integer/boolean/select/multiselect/multiline/cron/url/json/file)→ **UI 表单 + 后端校验自动生成**
- ⏰ **可视化 cron 调度**:每脚本独立时间(cron 实时人话翻译 + 未来 5 次执行预览),支持多实例多账号
- 🎨 **现代 UI**:React 18 + shadcn/ui + Tailwind v4,深浅模式一等公民,⌘K 命令面板
- 🔒 **字段级加密**:`type: secret` 字段 Fernet 加密落库,API 响应自动脱敏,**主密钥永不出主面板**
- 🧰 **子进程沙箱**:独立 `sandbox_runner.py` + 进程组超时强杀(`killpg SIGTERM→SIGKILL`)+ sys.path 隔离防 `import app.*` 拿密钥
- 🔔 **通知集成**:apprise **80+ 渠道**(Telegram / 钉钉 / 飞书 / Server酱 / 企微 / Bark / Pushover / SMTP / Discord / ...)
- 📊 **实时日志**:SSE 推送 + xterm.js 终端体验
- 🛡 **业务弹性**:**重试 + session 复用 + cookies TTL 自管理 + 业务 marker 兜底**(JM v1.1.0 集大成验证)
- 🌐 **多节点 agent**(MVP-1):Pull Agent + Long Polling(类 GitHub Actions self-hosted runner),签到任务可绑节点跑
- 📝 **Web 上传脚本**(MVP-5):浏览器拖 zip 上传 + 在线 CodeMirror 编辑 + 自动 dry-run 校验
- 🔍 **结构化失败诊断**:`RunResult.data` 含完整 endpoint / status / body_preview / elapsed_ms,前端 /runs 5 秒定位 bug
- 🚀 **一键部署**:Docker Compose + nginx 反代 + Let's Encrypt + systemd 开机自启

## 📦 已内置精装脚本(N=3,覆盖 3 种典型反爬模式)

| Slug | 站点 | 框架 | 反爬强度 | 凭证类型 | 资源占用 |
|---|---|---|---|---|---|
| **coklw** | https://coklw.net | WordPress | 弱(CF 灰云) | 单 cookie | < 30 MB / < 5s |
| **ptfans** | https://ptfans.cc | NexusPHP PT 站 | 中(CF + 业务层) | `c_secure_pass` cookie(1-2 年有效) | < 30 MB / < 5s |
| **jmcomic** | https://18comic.vip | NexusPHP + Cloudflare Turnstile | **重(JS Challenge + 业务层反爬)** | 用户名 + 密码(SeleniumBase UC + Xvfb 自动过 CF) | ~1.5 GB / 60-120s |

3 个脚本覆盖了从"最简 cookie 站"到"最难 CF Turnstile 站"的全谱系,**验证 manifest 契约对完全不同复杂度的脚本通用**。

## 📚 文档体系

- 📋 [**docs/SCRIPT-FIELDS-REFERENCE.md**](docs/SCRIPT-FIELDS-REFERENCE.md) — **manifest 11 字段类型完整速查 + 真实例 yaml**(写新脚本必看)
- 📖 [项目说明.md](项目说明.md) — 完整中文项目介绍 + 脚本开发规范
- 🛠 [scripts/coklw/](scripts/coklw/), [scripts/ptfans/](scripts/ptfans/), [scripts/jmcomic/](scripts/jmcomic/) — 3 个真签到精装范例,直接参考改写
- 📊 [agent/README.md](agent/README.md) — 远程多节点 agent 部署指南(MVP-1)
- 📝 [进度/](进度/) — 完整开发档案(README 索引 + 设计稿 + 决策 ADR + 13+ 变更档案)

## 🏗 技术栈

| 层 | 选择 |
|---|---|
| 后端 | Python 3.11 + FastAPI + APScheduler 3.x + SQLAlchemy 2 + SQLite(WAL) |
| 调度 / 通知 | APScheduler + apprise + cryptography.Fernet + bcrypt |
| 前端 | React 18 + Vite + TypeScript + React Router 7 |
| UI 库 | shadcn/ui + Tailwind CSS v4 + lucide-react |
| 数据可视化 | Recharts + Tremor + Framer Motion |
| 实时日志 | sse-starlette(后端)+ @microsoft/fetch-event-source + xterm.js(前端) |
| 部署 | Caddy 2(反代 + 自动 HTTPS)+ Docker Compose + Ubuntu 24 |

## 🚀 快速开始

### 生产部署(Ubuntu 24)

```bash
# 1. 准备
sudo apt update && sudo apt install -y docker.io docker-compose-plugin git
git clone <repo-url> /opt/signin-panel
cd /opt/signin-panel

# 2. 配置环境
cp .env.example .env
vim .env                              # 改 DOMAIN / ACME_EMAIL / UID / GID

# 3. 准备目录(host 文件属主与容器内 UID/GID 对齐)
mkdir -p data scripts logs frontend/dist
sudo chown -R 1000:1000 data scripts logs

# 4. 前端构建产物(本机或 CI 跑 pnpm build,把 dist/ 推到这里)
#    或直接在服务器:cd frontend && pnpm install && pnpm build

# 5. 起服务
docker compose up -d

# 6. 浏览器打开 https://<你的域名>,首次访问引导设置管理员密码
```

### 本地开发

```bash
# 后端
cd backend
uv venv --python 3.12
uv pip install -e ".[dev]"
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000 --workers 1

# 前端(另一终端)
cd frontend
pnpm install
pnpm gen:api                          # 从 backend OpenAPI 拉类型
pnpm dev                              # 默认 http://localhost:5173,proxy 到 backend
```

## 📂 目录结构

```
.
├── backend/                 # FastAPI 后端
│   ├── app/                 # 应用代码
│   ├── alembic/             # DB 迁移
│   ├── tests/
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/                # React 前端
│   ├── src/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── components.json      # shadcn CLI 配置
│   └── Dockerfile
├── scripts/                 # 签到脚本插件(每个一目录)
│   ├── bilibili-daily/
│   │   ├── manifest.yaml
│   │   ├── main.py
│   │   └── README.md
│   └── ...
├── data/                    # 运行时数据(不入 git)
│   ├── db.sqlite3
│   ├── scheduler.db
│   ├── encryption.key       # ⚠️ 主密钥,务必离线备份
│   └── scripts/<slug>/<instance_id>/   # 每脚本数据目录
├── logs/                    # 应用日志
├── docker-compose.yml
├── Caddyfile
├── .env.example
├── .gitignore
└── 进度/                    # 项目交接文档(给协作者/AI 读)
    ├── README.md            # 进度索引,30 秒接手
    ├── 决策.md              # ADR-lite 决策日志
    ├── 分支/main.md
    ├── 变更/                # 重大变更逐次记录
    └── 设计/                # 后端架构 / 前端 UI / 技术调研详细设计稿
```

## 🛠 写一个新签到脚本

1. 在 `scripts/` 下建目录 `scripts/<slug>/`(slug 用 `[a-z0-9-]`)
2. 写 `manifest.yaml`(定义元信息 + 字段 schema):

```yaml
slug: bilibili-daily
name: B站每日签到
description: B 站每日登录、看视频、投币
version: 1.0.0
default_cron: "0 8 * * *"
default_timeout_sec: 300

fields:
  - { key: sessdata, label: SESSDATA, type: secret, required: true }
  - { key: bili_jct, label: bili_jct, type: secret, required: true }
  - { key: coin_count, label: 投币数, type: integer, default: 1, min: 0, max: 5 }
```

3. 写 `main.py`,实现 `run(config, context) -> RunResult`:

```python
from dataclasses import dataclass

@dataclass
class RunResult:
    success: bool
    message: str = ""
    data: dict | None = None

def run(config: dict, context) -> RunResult:
    # config 已解密,context 有 run_id / data_dir / logger / notify 等
    context.logger.info("开始签到...")
    # ... 你的签到逻辑 ...
    return RunResult(success=True, message="签到成功 +15 经验", data={"exp": 15})
```

4. 在 Web 界面点"扫描脚本",新脚本入库,创建实例填配置即可调度。

详细规范见 [`进度/设计/后端架构.md`](进度/设计/后端架构.md) § 3。

## 💾 备份

主密钥 `data/encryption.key` 是**所有加密配置的命根子**,丢失即所有 cookie/token 失效:

- **立即备份**到密码管理器 / 加密 U 盘 / 打印纸保险柜(至少两份)
- 服务器上推荐 `restic` 定时增量备份 `data/` 整个目录到远端(S3/B2/SFTP)
- 备份脚本示例见 [`进度/设计/技术调研.md`](进度/设计/技术调研.md) § 6.7

## 📜 许可

MIT

## 🤖 给 AI/协作者

如果你是接手项目的 AI 或新成员,**第一件事**:打开 [`进度/README.md`](进度/README.md) 读 30 秒就能上手。所有设计稿、决策日志、当前 todo 都在 `进度/` 下。
