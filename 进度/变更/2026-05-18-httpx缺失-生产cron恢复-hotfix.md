---
name: 2026-05-18 · 生产 scheduled cron 100% 失败(httpx 缺失)hotfix
description: audit Critical #1 过头修复(一刀切禁 PYTHONPATH 透传)→ 生产容器 /deps 路径不透传 → 子进程 ModuleNotFoundError → 所有 scheduled 触发都炸
type: change
status: ✅ 热补丁部署生产,等 MVP-5 时完整 docker build 永久带上
---

# 2026-05-18 · httpx 缺失 hotfix

## 30 秒摘要

1. **P0 bug**:用户报告 coklw + ptfans **scheduled** 触发都失败,错误统一 `ModuleNotFoundError: No module named 'httpx'`(coklw 失败 17 小时前,ptfans 失败 9 小时前 = 都是 9:00 cron 触发)。
2. **Root cause**:audit Critical #1(2026-05-16)修复时,作者把 `PYTHONPATH` 加进 `_FORBIDDEN` 严禁透传(目的:防脚本 `import app.*`)。但生产 Dockerfile 走 `uv pip install --target /deps` + `ENV PYTHONPATH=/deps`(本机开发是 `backend/.venv/Lib/site-packages` 走 site-packages 不依赖 PYTHONPATH)。子进程没继承 → import httpx 失败。
3. **修法**:`executor._build_env` 改为**白名单透传** PYTHONPATH —— 过滤掉指向 `backend/` 的路径(防 `import app.*`),保留 `/deps` 等纯第三方依赖路径。
4. **部署方式**:`docker cp executor.py 进容器` 热补丁(不 build,避免和 MVP-5 后端 agent 半成品冲突)+ `docker compose restart backend`。
5. **验证**:用户手动点"立即运行" → Run #7 stderr 显示 `随机延迟 38 秒后开始签到` → httpx 已加载,脚本进入 `run()` 函数 ✅(后续失败是 cookie 过期问题,与本 hotfix 无关)。

## 真实失败 stderr(修复前)

```
脚本加载失败 ModuleNotFoundError: No module named 'httpx'
```

PT 站(NexusPHP)/ WordPress 站脚本都靠 httpx,所有 scheduled 触发 100% 失败。

## 根因详细

| 链路 | 状态 |
|---|---|
| backend Dockerfile `uv pip install --target /deps` | 第三方依赖装在 `/deps`(非 site-packages) |
| backend Dockerfile `ENV PYTHONPATH=/deps` | backend 主进程 import 靠 PYTHONPATH 找 |
| executor.py `_FORBIDDEN = {"PYTHONPATH", ...}`(audit Critical #1) | 子进程 env 严禁含 PYTHONPATH |
| executor 启动 sandbox_runner 子进程 | env 不含 PYTHONPATH → sys.path 不含 /deps |
| sandbox 子进程 `import httpx` | `ModuleNotFoundError` ❌ |

## 修法

`backend/app/scheduler/executor.py` `_build_env` 函数加 PYTHONPATH 安全透传段:

```python
parent_pythonpath = os.environ.get("PYTHONPATH", "")
if parent_pythonpath:
    safe_paths: list[str] = []
    for p in parent_pythonpath.split(os.pathsep):
        if not p:
            continue
        try:
            abs_p = Path(p).resolve()
        except (OSError, ValueError):
            continue
        # 拒绝 backend/ 本身(防 import app)
        if abs_p == _BACKEND_DIR:
            continue
        # 拒绝 backend/ 任何子路径(兜底)
        try:
            if abs_p.is_relative_to(_BACKEND_DIR):
                continue
        except (ValueError, AttributeError):
            if str(abs_p).startswith(str(_BACKEND_DIR) + os.sep):
                continue
        safe_paths.append(p)
    if safe_paths:
        env["PYTHONPATH"] = os.pathsep.join(safe_paths)
```

`_FORBIDDEN` 保留(防 `env_passthrough` 再覆盖),但白名单透传逻辑放在它之前,优先生效。

### 安全性 vs audit Critical #1

| 攻击向量 | 是否仍被防御 |
|---|---|
| 脚本直接 `import app` | ✅ `backend/` 路径被过滤,sandbox_runner 也兜底 `_isolate_sys_path` 摘 backend |
| 脚本 `from app.core.crypto import Fernet` | ✅ 同上 |
| 脚本 import 第三方包(httpx / requests / lxml 等) | ✅ `/deps` 路径透传后 import 成功 |
| 攻击者把 `backend/app` 加进 PYTHONPATH 试图绕过 | ✅ `is_relative_to(_BACKEND_DIR)` 兜底过滤 |

## 部署方式(临时热补丁)

```bash
# 1. scp 单个文件到 host /tmp
scp executor.py root@154.9.238.144:/tmp/executor-hotfix.py

# 2. docker cp 进运行中的容器(不 build 镜像)
ssh root@... "docker cp /tmp/executor-hotfix.py signin-panel-backend:/app/app/scheduler/executor.py"

# 3. restart backend(uvicorn 不带 --reload,需手动)
ssh root@... "cd /opt/signin-panel && docker compose restart backend"

# 4. 验证:容器 healthy + /health 200
```

**为什么不 build**:同时 MVP-5 后端 agent 在后台改 backend 文件(新增 `script_upload.py` / 改 `__init__.py` / 改 `scripts.py`),如果现在 `docker compose build` 会把 agent 半成品打进镜像,可能 import error 让容器起不来。热补丁绕开镜像,直接改运行中的容器代码 + restart 让新代码生效。

## ⚠️ 临时性 + 后续

- 热补丁的修改**写在运行中的容器内**,**不在镜像里**。下次 `docker compose build` 会用镜像内的旧 executor.py(本机源码已永久修了,但镜像是 build 时 COPY 一次的快照)。
- **预期持久化路径**:MVP-5 完成时,PM 做完整 `docker compose build`,本机最新 `executor.py`(含本 hotfix)会被永久 build 进镜像。
- 期间(几小时)只要容器不被 rebuild,hotfix 持续生效。

## 验证

| 项 | 结果 |
|---|---|
| `docker compose restart backend` | ✅ Up 6 seconds (healthy) |
| backend 启动 logs `已加载 2 / 2 个 enabled instance` | ✅ |
| `/health` 200 | ✅ |
| 用户手动点"立即运行" → Run #7 stderr `随机延迟 38 秒后开始签到` | ✅ 脚本进入 run() 函数(httpx 已加载,否则在 import 阶段就炸) |

(Run #7 最后失败是 cookie 过期 `首页未识别到用户名(或检测到 takelogin form)` — 与本 hotfix 无关,见 README 当前状态段)

## 教训

1. **audit Critical #1 修复时假设单一路径模型**(`backend/.venv/Lib/site-packages`),没考虑生产容器走 `/deps` + ENV PYTHONPATH 注入这条路径。
2. **本来应该的做法**:audit Critical #1 修复后,应当跑一次"完整生产 scheduled 触发"验证(不只是本机 TestClient),会暴露 ModuleNotFoundError。
3. **本来还应该的做法**:写 audit 修复时,review 生产 Dockerfile 的 ENV 配置,理解第三方依赖是怎么被 import 的(`--target /deps` vs site-packages 是关键差异)。
4. **以后 PR review 标准**:任何动 subprocess env / sys.path 的 PR,必须跑一次"生产容器内手动 sandbox_runner 测试" + "scheduled cron 触发 sandbox" 才算合格。

## 关联文件

- `backend/app/scheduler/executor.py`(本机已修,等 MVP-5 完成 build 永久带上)
- `backend/Dockerfile`(未改,但是这次 bug 的"另一半"环境依赖,以后看 executor.py 修复要带上对它的理解)
- 之前的 audit Critical #1 修复:`进度/变更/2026-05-16-MVP-1上线.md` 与 MVP-4 hotfix 变更档案
