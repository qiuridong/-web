"""脚本插件系统 — manifest 解析、字段类型、扫描。

详见 `进度/设计/后端架构.md` § 3。

子模块:
- manifest.py   manifest.yaml 解析与 schema 校验
- fields.py     字段类型注册、config 校验、表单 schema 输出
- scanner.py    扫描 scripts/ 目录差异,同步 scripts 表
- loader.py     加载脚本元信息(manifest + readme + icon)
"""
