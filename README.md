# 签到脚本聚合管理面板

> 把零散的签到脚本统一到一个 Web 控制台。服务器 7×24 自动调度,浏览器一站式管理,失败可推通知。
>
> **个人 / 小团队自用**,Ubuntu 24 + Docker Compose 单机部署。

## ✨ 特性

- 🧩 **插件化脚本**:扔目录就识别,无需改主程序代码
- ⏰ **可视化 cron 调度**:每脚本独立时间,支持多实例多账号
- 🎨 **现代 UI**:React 18 + shadcn/ui + Tailwind v4,深浅模式一等公民
- 🔒 **配置加密**:cookie / token 等敏感字段 Fernet 加密落库
- 🔔 **通知集成**:apprise 一库覆盖 Telegram / 钉钉 / 飞书 / Server酱 / 企微 等 80+ 渠道
- 📊 **实时日志**:SSE 推送 + xterm.js 终端体验
- 🚀 **一键部署**:Caddy 自动 HTTPS,`docker compose up -d` 即可

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
