# 子项目 · 脚本货架（Script Hub）

> 父索引：[../README.md](../README.md)
> 创建日期：2026-06-02
> 基于：工作树未提交，当前 git 分支 `feat/ui-fullbg-mobile-runcancel @ 3e7e2db`
> 状态：🔄 进行中（**M1 ✅ 全闭环 + M2 ✅** 已验证；M3 对接 / M4 部署待做）

---

## 目标

把散落在主项目 `scripts/` 的签到脚本，抽到一个**独立的「脚本货架」网站**集中存储、浏览、管理（上传/编辑/删除），并产出与签到管家**完全兼容**的标准 zip，供管家三种方式导入。作为主项目的**附属子项目**，代码隔离在 `脚本货架/` 子目录。

**范围限制（隔离边界）**：
- 🔴 **不碰** `backend/` `frontend/`（管家生产代码）—— 仅 M3 对接阶段动，独立分支单独 review
- 🔴 **不动** `scripts/`（管家生产运行源）—— 仅初始化时只读复制 3 个脚本作种子
- 货架独立工程、独立 SQLite、独立端口（8100）、独立子域名（hub.aijiaxia.cc）
- 货架只存脚本源码 + 元数据（非敏感）→ **无 encryption.key**，迁移无密钥负担

---

## 架构

- **货架 = 全集存储/分发中心**；管家 `scripts/` = 运行子集；单向流动（货架产 zip → 管家导入）。
- **技术栈**：FastAPI + SQLite（WAL）+ **React + Vite + TS + shadcn/ui + Tailwind + react-query**（前端与管家同款气质）。
- **数据**：`backend/data/hub.sqlite3`（hub_scripts + users + user_sessions）+ `backend/data/scripts/<slug>/`（脚本源，结构同管家）。
- **读公开、写登录**（bcrypt + httponly cookie）。

```
脚本货架/
├── backend/   FastAPI（app/{config,deps,main,core,db,services,schemas,api}）+ seed_admin.py + seed_scripts.py + seed/scripts/（3 种子）+ Dockerfile
├── frontend/  Vite+React+TS+shadcn（画廊/详情/管理/登录，build 通过）
├── docker-compose.yml          backend-only（127.0.0.1:8100，host nginx 反代）
├── docker-compose.install.yml  caddy+backend 自包含（新机用）
├── Caddyfile / install-hub.sh / migrate-hub.sh / 一键部署指南.md
```

---

## 任务清单（里程碑）

- [x] **M1 后端** — 骨架 + 移植 bundle/manifest/鉴权 + 19 路由 CRUD API — 2026-06-02（smoke 19/19 ✅）
- [x] **M1 前端** — 画廊 + 详情 + 管理 + 登录（shadcn 全栈）— 2026-06-02（build 干净 + Preview 全验证 ✅）
- [x] **M1 验证闭环** — 后端在跑 + 前端 dev + Preview 走完整闭环 — 2026-06-02 ✅
- [x] **M2 部署/迁移脚本** — install-hub.sh + migrate-hub.sh + 2 compose + Caddyfile + Dockerfile + 指南 — 2026-06-02（bash -n + export 验证 ✅，VPS 实测留 M4）
- [ ] **M3 对接管家** — upload-from-url + ?import 拦截 + 脚本市场页 + CORS（独立分支改管家）
- [ ] **M4 部署上线** — DNS + host nginx vhost + certbot + 生产 smoke
- [ ] 进度 README 索引登记

---

## 关键改动（按主题）

### 后端移植（与管家保持同口径，确保 zip 兼容）
- **bundle 打包 / zip 安全 / slug 校验**：`backend/app/services/bundle.py` ← 移植自管家 `script_upload_service.py`（`compute_script_bundle` / `validate_zip_safety` / `extract_zip_to_tmp` / `validate_slug` 字母开头长 41 / `validate_script_dir`）。常量一致（单文件 256KiB / 总 1MiB / 文件数 200 / 排除 .backups·__pycache__·data）。
- **manifest 解析**：`app/services/manifest.py` ← 移植管家 `plugins/manifest.py`，**去掉 apscheduler 依赖**（不校验 cron 语法），保留 slug + SemVer 严格校验。
- **bcrypt 鉴权 + SQLite WAL**：`app/core/security.py` / `app/db/{session,pragma}.py` ← 移植，去掉 Fernet/scheduler。
- **seed_admin.py** 移植管家版（幂等建首管理员，SEED_OK/SKIP/ERR）。

### 货架特有
- **数据模型** `app/db/models/{script,user,session}.py`（hub_scripts 存元数据 + manifest 原文 + bundle sha256 + 下载计数）。
- **仓储** `app/services/script_store.py`（import_from_zip/dir、refresh_metadata、bundle_zip、在线编辑路径安全）。
- **种子** `app/services/seed.py` + `seed_scripts.py`，从 `seed/scripts/{coklw,jmcomic,ptfans}/` 幂等入库；lifespan 首启自动导入。
- **API** `app/api/v1/{auth,scripts}.py`（19 routes）：列表/详情/bundle.zip/icon/文件读写/上传/删除/标签/登录。
- **前端**：画廊（卡片网格+搜索+标签）、详情（头部+三对接按钮+字段表+README+文件树）、管理（登录后上传/编辑/删除/标签）。「导入到管家」按钮跳 `${VITE_MANAGER_URL}/scripts?import=<encoded bundle url>` 新标签。vendor 单 chunk（避免循环依赖）。
- **部署**：见上目录。无 alembic（lifespan create_all + 种子），迁移走整库 tar。

---

## 验证记录

| 日期 | 项目 | 结果 |
|---|---|---|
| 2026-06-02 | 后端 import（19 routes） | ✅ |
| 2026-06-02 | 后端全链路 TestClient smoke（19 断言：种子/bundle/鉴权/上传覆盖/在线编辑/路径穿越/标签/删除） | ✅ 全过 |
| 2026-06-02 | **兼容性硬验证**：货架 3 个 bundle 喂管家真实校验链（zip安全→解压→manifest含apscheduler cron→slug） | ✅ 全部被管家接受 |
| 2026-06-02 | 前端 `pnpm build`（无循环警告，dist≈index 41KB + vendor 605KB + css 31KB） | ✅ |
| 2026-06-02 | Preview 闭环：画廊 3 卡片 / 详情（头部+三按钮+字段表）/ setup 登录 / 登录后写操作出现 / 0 console 错误 | ✅ |
| 2026-06-02 | 「导入到管家」href = `jb.aijiaxia.cc/scripts?import=<encoded bundle>` + target=_blank | ✅ |
| 2026-06-02 | `bash -n install/migrate` + `migrate export` 产物含 hub.sqlite3+scripts | ✅ |
| — | install/migrate VPS 实测 | ⏳ M4 |

---

## 最近迭代（倒序）

- 2026-06-02（续）push `feat/script-hub`（`db5bbf8` 货架本体 + `b7b98fa` 协作/部署素材）；组织**双会话并行** M3+M4（`进度/协作-脚本货架对接.md` 分工合同：A 货架侧+部署 / B 管家侧 upload-from-url+?import+市场页）；M4 部署素材就绪（`脚本货架/deploy/` nginx-hub.conf + 部署到生产VPS.md runbook），货架 CORS 代码就绪待部署，DNS `hub.aijiaxia.cc` 已加。
- 2026-06-02 调研「抽脚本做独立仓库站」→ 方案经用户批准（同仓库子目录 + 带后端 + 三对接 + 一键安装/迁移 + 同 VPS 子域名）→ **M1 后端**（25 源文件，smoke 19/19）+ **M2 部署/迁移脚本** 我亲自实现并验证；**M1 前端** 先派 opus agent（其 stall 但已产出完整 shadcn 全栈），我接手修 circular chunk + Preview 全验证闭环。后端用主项目 venv 本地跑（依赖是子集）。**货架 bundle 经管家真实校验确认兼容**。

---

## 已知风险 / 待观察

- ⚠️ **git 隔离待定**：货架代码当前在 `feat/ui-fullbg-mobile-runcancel` 工作树**未提交**。建议为货架开独立分支 `feat/script-hub`（用户确认后），避免混入 UI 分支。
- ⚠️ **M3 改管家有生产风险**：upload-from-url + ?import + 市场页要动 `backend/`+`frontend/`，须独立分支 + 单独 review + 先本地验证。
- ⚠️ **端口/反代冲突**：主项目生产用 host nginx 占 80/443，货架同 VPS 必须走 host nginx vhost（8100 反代），勿用 docker Caddy 抢端口（已在指南/compose 区分两路径）。
- ⚠️ **DNS 待加**：`hub.aijiaxia.cc → 154.9.238.144`。
- ⚠️ **install 前端构建**依赖 node:20-alpine 拉取 + frontend 就绪；完整 install/migrate 未在真实 VPS 跑过（留 M4）。
- ℹ️ **本地服务**：后端 uvicorn 在 `127.0.0.1:8000`（dev 库 backend/data）、前端 dev 在 `127.0.0.1:5173`（Preview 管理）。dev 库已 setup 管理员 `admin`。
