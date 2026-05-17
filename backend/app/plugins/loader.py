"""脚本辅助资源加载器(README / icon / requirements)。

用于详情页 ``GET /scripts/{slug}`` 响应:
- README.md 内容(可选,Markdown,前端渲染)
- icon 路径(可选,前端通过静态路由展示)
- requirements.txt 是否存在(影响 docker 构建提示)

不读取 main.py / 不导入脚本(那是 sandbox runner 的职责)。
"""
from __future__ import annotations

from pathlib import Path

from app.plugins.manifest import Manifest

_README_NAMES: tuple[str, ...] = ("README.md", "readme.md", "Readme.md")
_REQUIREMENTS_NAMES: tuple[str, ...] = ("requirements.txt",)


def load_readme(script_dir: Path) -> str | None:
    """读取 README.md(若存在)。

    候选文件名按优先级:``README.md`` > ``readme.md`` > ``Readme.md``。
    """
    script_dir = Path(script_dir)
    for name in _README_NAMES:
        candidate = script_dir / name
        if candidate.is_file():
            try:
                return candidate.read_text(encoding="utf-8")
            except OSError:
                return None
    return None


def has_requirements(script_dir: Path) -> bool:
    """``requirements.txt`` 是否存在。"""
    script_dir = Path(script_dir)
    return any((script_dir / n).is_file() for n in _REQUIREMENTS_NAMES)


def load_icon_path(script_dir: Path, manifest: Manifest) -> Path | None:
    """返回 icon 文件的绝对路径(若存在)。

    manifest.icon 是相对于 script_dir 的路径(默认 ``icon.svg``)。
    """
    script_dir = Path(script_dir)
    icon_rel = manifest.icon or "icon.svg"
    candidate = script_dir / icon_rel
    if candidate.is_file():
        return candidate.resolve()
    return None
