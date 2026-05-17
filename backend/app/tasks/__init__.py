"""周期性后台任务 — 由 SchedulerService 在 startup 时注册为内置 job。

详见 `进度/设计/后端架构.md` § 9.2 步骤 7a。

子模块:
- cleanup_runs.py    按 retention_days 删除旧 run 行
- scan_scripts.py    周期扫描 scripts/ 目录(若 settings 启用)
- resume_paused.py   恢复 paused_until 到期的 instance
- housekeeping.py    session 过期清理、孤立 data_dir 清理等
"""
