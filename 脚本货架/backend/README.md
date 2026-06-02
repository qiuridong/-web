# 脚本货架 · 后端

「签到管家」的附属**脚本货架**后端（FastAPI + SQLite）。

集中存储 / 浏览 / 管理签到脚本，并产出与签到管家**完全兼容**的标准 zip
（manifest.yaml + main.py + …），供管家一键导入运行。

- 读公开（浏览 / 下载 zip），写需登录（上传 / 编辑 / 删除）。
- 数据极简：`data/hub.sqlite3` + `data/scripts/<slug>/`，无加密密钥，易迁移。
- 移植自主项目 `backend/`：`compute_script_bundle` / `validate_zip_safety` /
  bcrypt 鉴权 / SQLite WAL；精简掉调度、通知、沙箱、加密。

详见仓库根 `脚本货架/一键部署指南.md` 与 `进度/分支/feat-script-hub.md`。
