---
name: Web 脚本管理 · 上传 + 单文件在线编辑(MVP-5)
description: 用户真实需求 — Web 页面上传现成脚本目录到服务器自动入库 + 可选在线小修单文件,不是全套 IDE
status: 设计完成(2026-05-17,等 audit High 部署后开工)
created: 2026-05-17
revised: 2026-05-17 PM(根据用户澄清重写)
---

# Web 脚本管理 · 详细设计

> **设计意图澄清(2026-05-17)**
>
> 用户原话:
> > "我说的添加脚本是,现成的脚本放在本地目录,可以自行添加,而不是编辑器,但是想了一下有编辑器可以线上修改脚本的某个文件也行"
>
> 真实需求 = **上传(主) + 单文件小修(次)**,不是全套 Monaco IDE。
>
> 本期不实现的:在线从零写代码 / 多文件协同编辑 / LSP / Git URL 拉取(这些留 MVP-6+ 看是否真需要)。

---

## 1. 用户故事

### 故事 ① 上传现成脚本(主流程,90% 使用场景)

> 我在 GitHub 找到一个 V2EX 签到脚本,clone 到本地后写好 `manifest.yaml`,本地 dry-run 过了。
>
> 浏览器打开 `jb.aijiaxia.cc/scripts` → 右上角点"➕ 添加脚本" → 弹出上传 Dialog → **拖一个文件夹进去**(或选 zip / 选多个文件)→ 后端校验通过 → 自动扫描入库 → 列表立刻出现新卡片。
>
> **全程零 SSH**。

### 故事 ② 在线小修(次流程,10% 场景)

> 已经上线的 coklw 突然报错说 "expected JSON",我看日志怀疑是某行解析 bug。
>
> 浏览器 `/scripts/coklw` → 概览 Tab → 文件列表 → 点 `main.py` → 弹出"在线编辑"Dialog → CodeMirror 显示源码 → 改两行 → 点"💾 保存(自动 dry-run 校验)" → 后端跑 30 秒 sandbox dry-run → 通过 → 落盘 → 下次 cron 立刻用新版本。

---

## 2. 后端 API 设计(`backend/app/api/v1/script_upload.py`)

### 2.1 端点清单(精简版,5 个)

```
POST   /api/v1/scripts/upload                🔒 上传脚本目录(zip 或 multipart 多文件)
GET    /api/v1/scripts/<slug>/files          🔒 列出脚本目录下所有文件 + 大小 + mtime
GET    /api/v1/scripts/<slug>/files/<path>   🔒 读单个文件内容(纯文本,binary 拒绝)
PUT    /api/v1/scripts/<slug>/files/<path>   🔒 改单个文件内容 + 触发 dry-run 校验
DELETE /api/v1/scripts/<slug>                🔒 删整个脚本(✨ 已有,但本期补"是否删磁盘"选项)
```

### 2.2 上传接口详解

#### `POST /scripts/upload`

**支持两种 content-type**:

##### A. `application/zip`(推荐,一次性原子上传)

```http
POST /api/v1/scripts/upload?slug=v2ex&force=false
Content-Type: application/zip
Content-Length: 12345

<zip binary>
```

后端:
1. 校验 `slug` 合规(`^[a-z][a-z0-9_-]{1,40}$`,不在保留字)
2. 解压到 `tempfile.TemporaryDirectory()`
3. 校验目录结构:**必须**有 `manifest.yaml`;**推荐**有 `main.py`(没有警告但允许)
4. 校验 `manifest.yaml` 语法 + schema(复用现有 `manifest_parser`)
5. 检查所有解压文件路径在 tmp 范围内(防 zip slip 攻击)
6. 检查总大小 ≤ 1 MiB(单 zip),单文件 ≤ 256 KiB
7. **可选 dry-run**(query 参数 `?dry_run=true`,默认 false):跑一次 sandbox 测试,通过才允许保存
8. 落盘:**原子操作** —— 先写到 `scripts/.tmp-<slug>-<uuid>/`,通过校验后 `os.rename()` 到 `scripts/<slug>/`
9. 触发 `script_service.scan_all`,新脚本立刻入库
10. 返回:

```json
{
  "slug": "v2ex",
  "saved_path": "scripts/v2ex/",
  "files_written": ["manifest.yaml", "main.py", "requirements.txt", "README.md"],
  "total_bytes": 12345,
  "dry_run_passed": true,
  "script_record": { /* ScriptResponse */ }
}
```

##### B. `multipart/form-data`(适合前端拖拽多个文件)

```http
POST /api/v1/scripts/upload?slug=v2ex
Content-Type: multipart/form-data; boundary=...

--boundary
Content-Disposition: form-data; name="files"; filename="manifest.yaml"
...
--boundary
Content-Disposition: form-data; name="files"; filename="main.py"
...
```

后端流程同 A,只是不需要解压,直接逐文件落到 tmp 目录。

#### 错误码

| 状态码 | 场景 |
|---|---|
| 409 | slug 已存在 + `force=false` |
| 413 | 上传总大小超 1 MiB |
| 422 | manifest.yaml 缺失 / 语法错误 / schema 不合规 / 单文件超 256KiB |
| 403 | zip slip 攻击检测(路径含 `../`) |
| 422 | dry-run 失败(若 `?dry_run=true`) |

### 2.3 文件读写接口详解

#### `GET /scripts/<slug>/files`

```json
{
  "files": [
    { "path": "manifest.yaml", "size": 1234, "mtime": "2026-05-17T10:30:00Z", "editable": true },
    { "path": "main.py", "size": 5678, "mtime": "2026-05-17T10:30:00Z", "editable": true },
    { "path": "requirements.txt", "size": 23, "mtime": "2026-05-17T10:30:00Z", "editable": true },
    { "path": "icon.svg", "size": 2048, "mtime": "2026-05-17T10:30:00Z", "editable": true },
    { "path": "README.md", "size": 1024, "mtime": "2026-05-17T10:30:00Z", "editable": true },
    { "path": "__pycache__/main.cpython-312.pyc", "size": 5432, "mtime": "...", "editable": false }
  ]
}
```

`editable: false` 的文件:`.pyc` / `.so` / `.exe` / 大于 256 KiB / 任意 binary(MIME 嗅探)。

#### `GET /scripts/<slug>/files/<path>`

```http
GET /api/v1/scripts/coklw/files/main.py

200 OK
Content-Type: text/plain; charset=utf-8

# coklw 签到主入口
import json
...
```

路径安全:`scripts/<slug>/<path>` 必须 `.resolve()` 在 `scripts/<slug>/` 内,不能逃逸。

#### `PUT /scripts/<slug>/files/<path>`

```http
PUT /api/v1/scripts/coklw/files/main.py?skip_dry_run=false
Content-Type: text/plain; charset=utf-8

<新的 main.py 内容>
```

后端:
1. 路径安全检查(同上)
2. 大小 ≤ 256 KiB
3. **自动 dry-run**(除非 `?skip_dry_run=true`,但需要 admin 额外确认):
   - 把 `scripts/<slug>/` 完整复制到 tmp + 用新内容覆盖被改的那个文件
   - 用 sandbox_runner 跑一次,30 秒超时
   - 失败返回 422 + dry-run 报告
4. 校验通过 → **原子写回**(写 tmp 文件 + `os.replace()` 同目录),旧文件备份到 `scripts/<slug>/.backups/<filename>.<timestamp>.bak`
5. 触发 `script_service.scan_all`(manifest 改了就要重读)
6. 返回:

```json
{
  "saved": true,
  "backup_path": "scripts/coklw/.backups/main.py.2026-05-17T143211.bak",
  "dry_run": {
    "exit_code": 0,
    "stdout_excerpt": "签到成功...",
    "duration_ms": 800,
    "passed": true
  }
}
```

### 2.4 安全模型(关键)

| 风险 | 缓解 |
|---|---|
| zip slip(zip 含 `../foo` 解压到上级) | 解压前遍历 `zipfile.ZipFile.namelist()`,任何含 `..` / 绝对路径 / 软链都拒绝 |
| 路径穿越(API path 含 `../`) | `Path(scripts_dir / slug / path).resolve().is_relative_to(scripts_dir / slug)` |
| 上传超大文件打满磁盘 | Content-Length / 流式累计上限,zip ≤ 1 MiB,单文件 ≤ 256 KiB |
| 上传可执行恶意脚本 | 必须 dry-run(默认开)+ sandbox 隔离 + 仅 admin 能上传 |
| 在线改 main.py 改坏现有脚本 | 强制 dry-run + 自动备份到 `.backups/` |
| 编辑 `.gitignore` / `requirements.txt` 也可能引入新问题 | requirements.txt 改动 → 自动重建 venv 并 dry-run(慢但安全) |
| 二进制文件(.pyc / icon.svg)用文本接口写 | `Content-Type: text/plain` 强制 + UTF-8 解码失败拒绝 |

### 2.5 不实现的功能(明确边界)

- ❌ **在线从零写 main.py**(用户原话:不是编辑器)
- ❌ **多文件协同编辑**(改一个文件就保存一个)
- ❌ **代码补全 / LSP**
- ❌ **Git URL 拉取**(单独的方案 ③,本期不做)
- ❌ **版本历史 / diff 查看**(只留最近 1 次 .bak,MVP-6 再说)

---

## 3. 前端 UI 设计

### 3.1 入口

`ScriptList.tsx`(`/scripts`)右上角:

```
[🔄 重新扫描]  [➕ 添加脚本]
```

`ScriptDetail.tsx`(`/scripts/<slug>`)概览 Tab 增加一个**文件列表区**(在 manifest / readme 下面):

```
📂 文件
├─ manifest.yaml          1.2 KB    [👁 查看] [✏️ 编辑]
├─ main.py                5.4 KB    [👁 查看] [✏️ 编辑]
├─ requirements.txt       23 B      [👁 查看] [✏️ 编辑]
├─ icon.svg               2.0 KB    [👁 查看]
└─ README.md              1.0 KB    [👁 查看] [✏️ 编辑]
```

### 3.2 上传 Dialog(主流程)

```
┌─ ➕ 添加脚本 ──────────────────────────────────┐
│                                                  │
│  ┌────────────────────────────────────────────┐ │
│  │                                            │ │
│  │      📁 拖一个文件夹到这里                  │ │
│  │       或 .zip 文件                          │ │
│  │                                            │ │
│  │      [📂 选择文件夹]  [📦 选 zip]           │ │
│  │                                            │ │
│  └────────────────────────────────────────────┘ │
│                                                  │
│  Slug(URL 标识,英文小写): [v2ex            ]   │
│  (留空 → 用 manifest.yaml 里的 slug)             │
│                                                  │
│  ☑ 上传前自动 dry-run(推荐)                    │
│  ☐ slug 已存在则覆盖(force)                    │
│                                                  │
│  [取消]                              [▶ 开始上传]│
└──────────────────────────────────────────────────┘
```

**拖拽实现**:用 `react-dropzone` 处理,支持文件夹(`{ webkitdirectory: 'true' }`)。

**上传进度**:Progress Bar,大文件用 XHR `upload.onprogress` 推百分比。

**上传完成 → 结果展示**:

```
┌─ ✅ 上传成功 ──────────────────────────────────┐
│                                                  │
│  📁 scripts/v2ex/  已落盘                        │
│                                                  │
│  写入文件 (4):                                   │
│    ✅ manifest.yaml       1.2 KB                 │
│    ✅ main.py             5.4 KB                 │
│    ✅ requirements.txt    23 B                   │
│    ✅ README.md           1.0 KB                 │
│                                                  │
│  Dry-run: ✅ 通过(800ms,exit=0,协议合规)      │
│                                                  │
│  [跳转到脚本详情]              [关闭并刷新列表] │
└──────────────────────────────────────────────────┘
```

失败时显示具体错误(zip 解析失败 / manifest 不合规 / dry-run exit_code 非 0 + stderr 摘要)。

### 3.3 在线编辑 Dialog(次流程)

点文件列表里的 `[✏️ 编辑]`:

```
┌─ ✏️ 编辑 main.py ─────────────────────────[✕]─┐
│                                                  │
│  ┌────────────────────────────────────────────┐ │
│  │ # coklw 签到主入口                         │ │
│  │ import json                                │ │
│  │ import sys                                 │ │
│  │ ...                                        │ │
│  │                                            │ │
│  │   (CodeMirror,Python 语法高亮,            │ │
│  │    行号,搜索 Ctrl+F)                     │ │
│  │                                            │ │
│  │                                            │ │
│  │                                            │ │
│  └────────────────────────────────────────────┘ │
│                                                  │
│  状态:5.4 KB / 256 KB                            │
│  ⏱ 上次保存:2 小时前                            │
│                                                  │
│  ☑ 保存前自动 dry-run(强烈推荐)                │
│                                                  │
│  [取消]                            [💾 保存]    │
└──────────────────────────────────────────────────┘
```

**编辑器选型**:`@uiw/react-codemirror`(轻量,~80KB gz,远小于 Monaco 2MB)。语法高亮按文件扩展名自动:
- `.py` → Python
- `.yaml` / `.yml` → YAML
- `.json` → JSON
- `.txt` / `.md` → plain / markdown
- 其它 → plain text

**保存流程**:
1. 点保存 → 显示 spinner "正在 dry-run..."(30 秒超时)
2. 通过 → 绿色 toast "保存成功,已备份旧版到 `.backups/`"
3. 失败 → 红色 Dialog 显示 dry-run stderr,**不关闭编辑器**(让用户改完再试)

### 3.4 关键 UX

- 上传 Dialog 拖入文件夹后,显示文件树预览("即将上传 4 个文件,共 7.6 KB"),让用户**确认**再点开始
- 编辑器 Ctrl+S 等同于点保存
- 文件列表的 `.backups/` 目录默认折叠(用户偶尔需要看历史备份)
- 上传按钮在用户**未登录 / 非 admin** 时显示但 disabled + 提示"需要管理员权限"

---

## 4. 工程化

### 4.1 新增文件

后端:
- `backend/app/api/v1/script_upload.py`(~250 行)
- `backend/app/services/script_upload_service.py`(~200 行)
- `backend/app/schemas/script_upload.py`(~60 行)
- `backend/_verify_mvp5_upload_edit.py`(~120 行,~12 断言)

前端:
- `frontend/src/pages/scripts/components/UploadScriptDialog.tsx`(~200 行)
- `frontend/src/pages/scripts/components/FileEditDialog.tsx`(~150 行)
- `frontend/src/pages/scripts/components/ScriptFileList.tsx`(~80 行)
- `frontend/src/api/hooks/useScriptUpload.ts`(~50 行)
- `frontend/src/api/hooks/useScriptFiles.ts`(~50 行)

### 4.2 修改文件

- `backend/app/api/v1/__init__.py`(+1 router include)
- `backend/app/api/v1/scripts.py`(DELETE 加 `?delete_files=true` 选项)
- `frontend/src/pages/scripts/ScriptList.tsx`(+"添加脚本"按钮 + UploadScriptDialog 集成)
- `frontend/src/pages/scripts/ScriptDetail.tsx`(+文件列表区 + FileEditDialog 集成)

### 4.3 新前端依赖

```jsonc
{
  "react-dropzone": "^14.3.5",       // 拖拽文件夹支持,~30KB gz
  "@uiw/react-codemirror": "^4.23.0",// 轻量编辑器,~80KB gz
  "@codemirror/lang-python": "^6.1.6",
  "@codemirror/lang-yaml": "^6.1.2",
  "js-yaml": "^4.1.0"                // 前端预校验
}
```

总新增前端 bundle 大小 ~200KB(全部按需 lazy load,不影响主页面)。

### 4.4 后端无新依赖

`zipfile` / `tempfile` / `pathlib` / `shutil` / `os` 都是 stdlib。

---

## 5. 实施路线(估时 ~1.5 小时,可并行 ~50 分钟)

| 阶段 | 内容 | 时间 |
|---|---|---|
| 1 | 后端 upload 端点 + zip 解析 + 路径安全 + 原子落盘 | 30 分钟 |
| 2 | 后端 files CRUD 端点 + 自动 dry-run 集成 | 20 分钟 |
| 3 | 验证脚本 `_verify_mvp5_upload_edit.py` 写完跑过 | 15 分钟 |
| 4 | 前端 UploadScriptDialog(react-dropzone + Progress + 结果展示) | 25 分钟 |
| 5 | 前端 FileEditDialog + ScriptFileList(CodeMirror 集成) | 25 分钟 |
| 6 | 集成 + 本机 Claude Preview 真闭环(上传 + 改 + 删) | 15 分钟 |
| 7 | 部署生产 + 真浏览器走一遍 | 10 分钟 |

并行优化:阶段 1+2 派 backend opus agent,同时 PM 自己写阶段 4+5 → 阶段 3+6+7 串行收尾 → **总时 ~50 分钟**。

---

## 6. 验证清单(自验断言)

`backend/_verify_mvp5_upload_edit.py`:

- ✅ 未鉴权 upload → 401
- ✅ 非 admin upload → 403
- ✅ upload 缺 manifest.yaml → 422
- ✅ upload zip slip 攻击(`../`) → 403
- ✅ upload 超 1 MiB → 413
- ✅ upload 合规 zip → 200 + 落盘 + 入库
- ✅ upload force=false + slug 存在 → 409
- ✅ upload force=true + slug 存在 → 200 + 覆盖
- ✅ upload dry-run 失败 → 422 + 不落盘
- ✅ GET files → 列出 manifest/main.py 等
- ✅ GET binary file → 拒绝
- ✅ PUT files 路径穿越 → 403
- ✅ PUT files 超 256KiB → 413
- ✅ PUT files 改坏代码 → 422 + 不写盘
- ✅ PUT files 合规改 → 200 + 备份旧版到 `.backups/`

---

## 7. 与 audit 报告其它建议的协同

audit High #7 提到 "/openapi.json 生产无鉴权"(已派 agent 修),本期 MVP-5 实现时:
- 新的 upload 端点必须强制 `require_admin`
- 在 OpenAPI schema 注明 security: cookie auth

---

## 附录:曾考虑的"Monaco 全套 IDE"方案(已废弃)

最初(2026-05-17 上午)设计为 Monaco Editor 全套体验:在线写 manifest + main.py + AST 危险词扫描 + 实时校验 + 全套 dry-run + Save。

**为什么废弃**(用户 2026-05-17 PM 澄清):
1. 用户不是要"在线写代码",而是要"上传现成脚本"
2. Monaco 2MB,过重
3. AST 扫描在单用户场景里属于过度防御
4. 全套 IDE 体验 ≠ 用户的实际工作流

**保留的设计要素**(本期复用):
- Sandbox dry-run 复用 `backend/sandbox_runner.py`(同生产路径)
- 路径穿越防御
- 文件大小硬上限
- 仅 admin 权限校验
- 审计日志

**MVP-6+ 才考虑**(如果届时真有需要):
- 多文件协同编辑
- Git URL 拉取(方案 ③)
- LSP 支持
- 在线 diff / 版本历史

---

📅 设计完成:2026-05-17 PM(根据用户澄清重写)
🚀 开工触发:audit High agent 完成 + PM 验证部署 + 用户抓包好第二个脚本
