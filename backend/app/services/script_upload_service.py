"""脚本上传 + 在线编辑业务逻辑(MVP-5)。

详见 ``进度/设计/Web脚本编辑器.md`` § 2.4 安全模型 + § 2.2/2.3 流程。

公开函数
--------
- :func:`validate_slug`              slug 正则与保留字校验
- :func:`validate_zip_safety`        遍历 zip namelist 拒 zip slip / 超大单文件
- :func:`extract_zip_to_tmp`         安全解压
- :func:`validate_script_dir`        必含 manifest.yaml + schema 校验
- :func:`dry_run_script`             subprocess 跑 ``sandbox_runner.py`` 一次
- :func:`commit_to_scripts`          原子 rename tmp → scripts/<slug>/
- :func:`list_files_in_script`       列文件 + editable 标签
- :func:`read_file_text`             路径安全 + UTF-8 解码
- :func:`write_file_text`            写 tmp + 原子 replace + 备份旧版到 .backups/
- :func:`delete_script_files`        rmtree scripts/<slug>/

设计要点
--------
- 完全无 HTTP 依赖,路由层只做 IO 转换 + 鉴权
- 异常用 ``app.core.exceptions.*`` 既有体系
- 大小阈值 / 保留字 / 二进制后缀 都是模块级常量,便于调整
"""
from __future__ import annotations

import json
import mimetypes
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING
from zipfile import BadZipFile, ZipFile, ZipInfo

from loguru import logger

from app.core.exceptions import (
    ConflictError,
    PayloadTooLarge,
    PermissionError,
    ScriptNotFound,
    ValidationError,
)
from app.plugins.manifest import SLUG_RE, parse_manifest_text
from app.schemas.script_upload import DryRunResult, FileListItem

if TYPE_CHECKING:
    pass


# ============================================================
# 常量(可调阈值集中在此)
# ============================================================
#: 单 zip 总大小硬上限(1 MiB)
MAX_ZIP_TOTAL_BYTES: int = 1 * 1024 * 1024

#: 单文件硬上限(256 KiB)
MAX_FILE_BYTES: int = 256 * 1024

#: dry-run 子进程超时(秒)— 设计稿 § 2.3 约定 30 秒
DRY_RUN_TIMEOUT_SEC: int = 30

#: stdout/stderr 截尾上限(避免响应体膨胀)
DRY_RUN_EXCERPT_LIMIT: int = 4 * 1024

#: 不可编辑文件后缀(二进制 / 编译产物)
BINARY_SUFFIXES: frozenset[str] = frozenset({
    ".pyc", ".pyo", ".pyd",
    ".so", ".dll", ".dylib",
    ".exe", ".bin",
    ".zip", ".gz", ".tar", ".bz2", ".xz", ".7z",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp",
    ".ico", ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".pdf", ".mp3", ".mp4", ".webm", ".ogg",
    ".db", ".sqlite", ".sqlite3",
})

#: 保留字 slug(不允许用户指定)
RESERVED_SLUGS: frozenset[str] = frozenset({
    ".", "..",
    "new", "upload", "create", "edit", "delete",
    "scan", "test", "admin",
    "backups",  # 与 .backups 子目录混淆
    # 注意:`_test_*` 前缀是 verify 脚本专用,故意不放在保留字里
})

#: 备份目录名(在每个脚本目录内)
BACKUPS_SUBDIR: str = ".backups"


# ============================================================
# slug 校验
# ============================================================
def validate_slug(slug: str) -> None:
    """校验 slug 合规 + 不在保留字列表。

    设计稿 § 2.2 + 现有 ``manifest.SLUG_RE`` 兼容 — 取交集后:

        ``^[a-z][a-z0-9-]{0,40}$``

    - 以小写字母开头
    - 允许 ``a-z 0-9 -``(**不允许下划线**,与 manifest.SLUG_RE 对齐避免分裂)
    - 长度 1-41

    :raises ValidationError: 不合法
    :raises PermissionError: 命中保留字
    """
    if not slug or not isinstance(slug, str):
        raise ValidationError(
            "slug 不能为空",
            details={"field": "slug", "value": slug},
        )

    if slug.lower() in RESERVED_SLUGS:
        raise PermissionError(
            f"slug {slug!r} 是保留字,不允许使用",
            details={"slug": slug, "reserved": sorted(RESERVED_SLUGS)},
        )

    # 与 manifest.SLUG_RE 对齐,只多加 "字母开头(非数字)" + "长度上限 41" 两条
    import re  # 局部 import,避免污染模块命名空间
    pattern = re.compile(r"^[a-z][a-z0-9-]{0,40}$")
    if not pattern.match(slug):
        raise ValidationError(
            f"slug {slug!r} 不合法;必须匹配 ^[a-z][a-z0-9-]{{0,40}}$ "
            "(以小写字母开头,允许 a-z 0-9 -,总长 1-41,与 manifest.slug 一致)",
            details={"field": "slug", "value": slug},
        )


# ============================================================
# Zip 安全校验(zip slip 防御)
# ============================================================
def validate_zip_safety(zip_path: Path) -> list[ZipInfo]:
    """遍历 zip 的 namelist,拒绝 zip slip / 超大文件。

    防御点(设计稿 § 2.4):
    - 含 ``..`` 路径段 → 403 PermissionError
    - 绝对路径(``/`` 开头 / Windows ``C:\\`` 开头)→ 403
    - 软链接 / 设备文件(external_attr 高位)→ 403
    - 单文件 > 256 KiB → 413 PayloadTooLarge
    - 总未压缩大小 > 1 MiB → 413 PayloadTooLarge
    - 文件总数 > 200(防 zip bomb 简化版)→ 413

    :raises PermissionError: 路径攻击
    :raises PayloadTooLarge: 大小超限
    :raises ValidationError: zip 自身坏
    :returns: 安全的 ZipInfo 列表(供 :func:`extract_zip_to_tmp` 复用)
    """
    try:
        with ZipFile(zip_path, "r") as zf:
            infos = zf.infolist()
    except BadZipFile as exc:
        raise ValidationError(
            f"zip 文件解析失败: {exc}",
            details={"path": str(zip_path)},
        ) from exc

    if len(infos) > 200:
        raise PayloadTooLarge(
            f"zip 包含 {len(infos)} 个条目,超过 200 上限",
            details={"count": len(infos), "limit": 200},
        )

    total_uncompressed = 0
    safe_infos: list[ZipInfo] = []
    for info in infos:
        name = info.filename

        # 跳过显式目录条目(以 / 结尾,size 0)
        if name.endswith("/"):
            continue

        # 路径穿越:含 ..  /  绝对路径 / 反斜杠绝对路径
        # 用 PurePosixPath 解析,统一处理 / 和 \
        normalized = name.replace("\\", "/")
        if normalized.startswith("/") or ":" in normalized.split("/")[0]:
            raise PermissionError(
                f"zip 含绝对路径条目,疑似 zip slip 攻击: {name!r}",
                details={"entry": name},
            )

        parts = normalized.split("/")
        if any(p == ".." for p in parts):
            raise PermissionError(
                f"zip 含 .. 路径段,疑似 zip slip 攻击: {name!r}",
                details={"entry": name},
            )

        # 软链(类 Unix:external_attr 高 16 位)
        # symlink mode = 0o120000;Windows 通常 0,跳过
        mode = (info.external_attr >> 16) & 0xFFFF
        if mode and (mode & 0o170000) == 0o120000:
            raise PermissionError(
                f"zip 含软链条目,不安全: {name!r}",
                details={"entry": name, "mode": oct(mode)},
            )

        # 单文件 size
        if info.file_size > MAX_FILE_BYTES:
            raise PayloadTooLarge(
                f"zip 单文件 {name!r} 大小 {info.file_size} > 上限 {MAX_FILE_BYTES}",
                details={
                    "entry": name,
                    "size": info.file_size,
                    "limit": MAX_FILE_BYTES,
                },
            )

        total_uncompressed += info.file_size
        if total_uncompressed > MAX_ZIP_TOTAL_BYTES:
            raise PayloadTooLarge(
                f"zip 解压后总大小 > 上限 {MAX_ZIP_TOTAL_BYTES}",
                details={
                    "current": total_uncompressed,
                    "limit": MAX_ZIP_TOTAL_BYTES,
                },
            )

        safe_infos.append(info)

    return safe_infos


def extract_zip_to_tmp(zip_path: Path, target_tmp: Path) -> list[str]:
    """把 zip 解压到 target_tmp(target_tmp 必须已存在且为空)。

    **必须先调** :func:`validate_zip_safety` 校验通过再调本函数。

    :returns: 写入文件的相对路径列表(POSIX 风格)
    """
    target_tmp = Path(target_tmp)
    if not target_tmp.is_dir():
        raise ValidationError(
            f"解压目标目录不存在: {target_tmp}",
            details={"target": str(target_tmp)},
        )

    # 再次走一遍 safety(保险 — 调用方可能漏掉)
    safe_infos = validate_zip_safety(zip_path)

    # 检测 zip 是否有"顶层单一目录"包装(如 GitHub 下载的 repo zip 通常带 ``repo-master/``)
    # 若所有条目都以同一目录开头 → 自动剥掉这一层
    top_dir = _detect_single_top_dir(safe_infos)
    if top_dir:
        logger.info("zip 顶层单一目录 {!r},解压时自动剥离", top_dir)

    written: list[str] = []
    with ZipFile(zip_path, "r") as zf:
        for info in safe_infos:
            rel_in_zip = info.filename.replace("\\", "/")
            if top_dir and rel_in_zip.startswith(top_dir + "/"):
                rel_in_zip = rel_in_zip[len(top_dir) + 1:]
            if not rel_in_zip:
                continue  # 单纯的顶层目录条目

            dest = target_tmp / rel_in_zip
            # 再做一次 resolve 校验(双保险防 zip slip)
            dest_resolved = dest.resolve()
            target_resolved = target_tmp.resolve()
            try:
                dest_resolved.relative_to(target_resolved)
            except ValueError as exc:
                raise PermissionError(
                    f"解压目标路径逃出 target_tmp: {dest_resolved}",
                    details={
                        "entry": info.filename,
                        "resolved": str(dest_resolved),
                    },
                ) from exc

            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out, length=64 * 1024)

            written.append(rel_in_zip)

    return written


def _detect_single_top_dir(infos: list[ZipInfo]) -> str | None:
    """若所有条目都在同一顶层目录下,返回该目录名;否则 None。"""
    if not infos:
        return None
    first = infos[0].filename.replace("\\", "/").split("/", 1)[0]
    for info in infos:
        name = info.filename.replace("\\", "/")
        head = name.split("/", 1)[0]
        if head != first:
            return None
        # 若顶层就是文件(没有 / 子路径),也不算单一顶层目录
        if "/" not in name:
            return None
    return first


# ============================================================
# 脚本目录结构校验
# ============================================================
def validate_script_dir(tmp_dir: Path) -> dict:
    """校验解压(或 multipart 落盘)后的目录是否构成合法脚本。

    必填:``manifest.yaml`` 存在且 schema 通过
    推荐:``main.py`` 存在(没有也允许,但 dry-run 必然失败)

    :returns: 解析出的 manifest dict(供调用方拿 slug 等)
    :raises ValidationError: manifest 缺失或解析失败
    """
    tmp_dir = Path(tmp_dir)
    manifest_path = tmp_dir / "manifest.yaml"
    if not manifest_path.is_file():
        raise ValidationError(
            "上传内容缺少 manifest.yaml(脚本目录根必须有此文件)",
            details={"tmp_dir": str(tmp_dir)},
        )

    # 用既有 parse_manifest_text 走完整 schema 校验
    text = manifest_path.read_text(encoding="utf-8")
    # parse_manifest_text 自身抛 ManifestInvalidError(继承 ValidationError 422),
    # 由路由层异常处理直接转 422 — 不在这里多包一层。
    manifest = parse_manifest_text(text, source=manifest_path)

    return {
        "slug": manifest.slug,
        "name": manifest.name,
        "version": manifest.version,
        "manifest": manifest,
        "has_main_py": (tmp_dir / "main.py").is_file(),
    }


# ============================================================
# Dry-run(子进程跑一次 sandbox_runner.py)
# ============================================================
def dry_run_script(
    script_dir: Path,
    *,
    timeout_sec: int = DRY_RUN_TIMEOUT_SEC,
    config: dict | None = None,
) -> DryRunResult:
    """用 ``sandbox_runner.py`` 子进程跑一次脚本(stdin 喂空 config + fake context)。

    本函数与 executor 实际的运行路径(``subprocess.Popen sandbox_runner.py``)
    完全一致 — 保证 "dry-run 通过 = 生产路径能跑"。

    :param script_dir: 包含 ``main.py`` + ``manifest.yaml`` 的脚本根目录
    :param timeout_sec: 子进程墙钟超时(秒)
    :param config: 注入给脚本的 config dict;默认空 dict(让脚本走默认值路径)
    :returns: :class:`DryRunResult`
    """
    script_dir = Path(script_dir).resolve()

    # sandbox_runner.py 在 backend/ 根目录(与 app/ 平级)
    backend_root = Path(__file__).resolve().parents[2]
    sandbox_runner = backend_root / "sandbox_runner.py"
    if not sandbox_runner.is_file():
        raise ValidationError(
            f"sandbox_runner.py 不存在 path={sandbox_runner}",
            details={"sandbox_runner": str(sandbox_runner)},
        )

    # 构造 fake context — 字段与 executor 真实路径一致
    fake_context = {
        "run_id": 0,
        "instance_id": 0,
        "instance_name": "_dry_run_",
        "script_slug": script_dir.name,
        "script_dir": str(script_dir),
        "data_dir": str(script_dir / "_dry_run_data"),
        "timeout_sec": timeout_sec,
        "trigger_type": "manual",
        "attempt": 1,
    }
    payload = json.dumps(
        {"config": config or {}, "context": fake_context},
        ensure_ascii=False,
    )

    # 用 sys.executable 当前 python(就是 venv 的 python,因为 backend 跑在 venv 里)
    cmd = [sys.executable, "-u", str(sandbox_runner)]

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    # 不透传 backend 的 PYTHONPATH:sandbox_runner._isolate_sys_path 会再处理一次

    started = time.monotonic()
    timed_out = False
    try:
        proc = subprocess.run(  # noqa: S603 — 已用 list 形式,无 shell
            cmd,
            input=payload.encode("utf-8") + b"\n",
            capture_output=True,
            timeout=timeout_sec,
            check=False,
            env=env,
            cwd=str(script_dir),
        )
        exit_code = proc.returncode
        stdout = proc.stdout.decode("utf-8", errors="replace")
        stderr = proc.stderr.decode("utf-8", errors="replace")
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = -1
        stdout = (exc.stdout or b"").decode("utf-8", errors="replace")
        stderr = (exc.stderr or b"").decode("utf-8", errors="replace")
        logger.warning(
            "dry-run 超时被杀 script_dir={} timeout={}", script_dir, timeout_sec
        )
    duration_ms = int((time.monotonic() - started) * 1000)

    return DryRunResult(
        passed=(exit_code == 0 and not timed_out),
        exit_code=exit_code,
        duration_ms=duration_ms,
        stdout_excerpt=stdout[-DRY_RUN_EXCERPT_LIMIT:],
        stderr_excerpt=stderr[-DRY_RUN_EXCERPT_LIMIT:],
        timed_out=timed_out,
    )


# ============================================================
# 原子落盘:tmp_dir → scripts/<slug>/
# ============================================================
def commit_to_scripts(
    tmp_dir: Path,
    scripts_root: Path,
    slug: str,
    *,
    force: bool = False,
) -> list[str]:
    """把 tmp_dir 内容原子搬到 ``scripts_root/<slug>/``。

    步骤:
    1. 若目标已存在:
       - force=False → ConflictError(409)
       - force=True  → 先把旧目录 rename 到 ``<slug>.old-<uuid>`` 备份
    2. ``os.replace(tmp_dir, scripts_root/<slug>)``
    3. 若步骤 2 成功且备份存在 → 删旧备份(rmtree)

    :returns: 入库脚本根目录下的相对路径列表
    :raises ConflictError: slug 存在且 force=False
    """
    scripts_root = Path(scripts_root).resolve()
    tmp_dir = Path(tmp_dir).resolve()
    target = scripts_root / slug

    backup_target: Path | None = None
    if target.exists():
        if not force:
            raise ConflictError(
                f"脚本 slug={slug!r} 已存在,使用 ?force=true 覆盖",
                details={"slug": slug, "existing": str(target)},
            )
        # 先备份旧目录
        backup_target = scripts_root / f"{slug}.old-{uuid.uuid4().hex[:8]}"
        os.replace(target, backup_target)
        logger.info(
            "force=true 旧版备份 slug={} backup={}", slug, backup_target
        )

    try:
        os.replace(tmp_dir, target)
    except OSError as exc:
        # 回滚:把备份还回去
        if backup_target is not None and backup_target.exists():
            try:
                os.replace(backup_target, target)
            except OSError:
                logger.exception("回滚失败 backup={} target={}", backup_target, target)
        raise ValidationError(
            f"原子落盘失败 tmp_dir={tmp_dir} target={target}: {exc}",
            details={"tmp_dir": str(tmp_dir), "target": str(target)},
        ) from exc

    # 成功 — 清旧备份
    if backup_target is not None and backup_target.exists():
        try:
            shutil.rmtree(backup_target)
        except OSError as exc:
            logger.warning("清旧备份失败(可手动 rm){} err={}", backup_target, exc)

    # 列出落盘的相对路径(用于响应 files_written)
    written: list[str] = []
    for p in sorted(target.rglob("*")):
        if p.is_file():
            try:
                rel = p.relative_to(target).as_posix()
                written.append(rel)
            except ValueError:
                continue
    return written


# ============================================================
# 文件列表(GET /scripts/{slug}/files)
# ============================================================
def list_files_in_script(scripts_root: Path, slug: str) -> list[FileListItem]:
    """列出 ``scripts/<slug>/`` 下所有文件 + editable 判定。

    editable=False 的条件(任一即可):
    - 后缀在 :data:`BINARY_SUFFIXES`
    - 大小 > :data:`MAX_FILE_BYTES`
    - 路径含 ``.backups/`` 段(保留只读视图,不允许直接编辑备份)
    - MIME 嗅探判定 binary(对未知后缀的兜底)

    :raises ScriptNotFound: 目录不存在
    """
    scripts_root = Path(scripts_root).resolve()
    target = scripts_root / slug

    if not target.is_dir():
        raise ScriptNotFound(
            f"脚本目录不存在: {slug}",
            details={"slug": slug, "path": str(target)},
        )

    items: list[FileListItem] = []
    for p in sorted(target.rglob("*")):
        if not p.is_file():
            continue
        try:
            rel = p.relative_to(target).as_posix()
        except ValueError:
            continue

        size = p.stat().st_size
        mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
        editable = _is_editable(p, rel, size)

        items.append(
            FileListItem(path=rel, size=size, mtime=mtime, editable=editable)
        )

    return items


def _is_editable(path: Path, rel_path: str, size: int) -> bool:
    """判断单个文件是否可在线编辑。"""
    # .backups 目录内的备份永远不可编辑(view-only)
    parts = rel_path.split("/")
    if BACKUPS_SUBDIR in parts:
        return False

    # 超大
    if size > MAX_FILE_BYTES:
        return False

    # 后缀黑名单
    if path.suffix.lower() in BINARY_SUFFIXES:
        return False

    # MIME 嗅探(对没有后缀的兜底)
    guess, _ = mimetypes.guess_type(str(path))
    if guess and not (
        guess.startswith("text/")
        or guess in {"application/json", "application/xml", "application/yaml"}
    ):
        return False

    return True


# ============================================================
# 路径安全(读 / 写共用)
# ============================================================
def _safe_resolve(scripts_root: Path, slug: str, rel_path: str) -> Path:
    """解析 ``scripts/<slug>/<rel_path>`` 并校验在 ``scripts/<slug>/`` 内。

    :raises PermissionError: 路径逃逸
    :raises ScriptNotFound: slug 目录不存在
    :raises ValidationError: rel_path 为空 / 包含奇怪字符
    """
    scripts_root = Path(scripts_root).resolve()
    base = (scripts_root / slug).resolve()

    if not base.is_dir():
        raise ScriptNotFound(
            f"脚本目录不存在: {slug}",
            details={"slug": slug, "path": str(base)},
        )

    if not rel_path or rel_path in {".", ".."}:
        raise ValidationError(
            f"文件路径无效: {rel_path!r}",
            details={"rel_path": rel_path},
        )

    # 早期拒绝路径穿越特征(在 resolve 前快速拒)
    normalized = rel_path.replace("\\", "/")
    if normalized.startswith("/") or normalized.startswith("\\"):
        raise PermissionError(
            f"文件路径不允许绝对路径: {rel_path!r}",
            details={"rel_path": rel_path},
        )
    parts = normalized.split("/")
    if any(p == ".." for p in parts):
        raise PermissionError(
            f"文件路径含 ..,疑似路径穿越: {rel_path!r}",
            details={"rel_path": rel_path},
        )

    target = (base / normalized).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise PermissionError(
            f"文件路径逃出脚本目录: {rel_path!r}",
            details={"rel_path": rel_path, "resolved": str(target)},
        ) from exc

    return target


# ============================================================
# 单文件读
# ============================================================
def read_file_text(scripts_root: Path, slug: str, rel_path: str) -> tuple[str, int, datetime]:
    """读取单文件文本内容。

    :returns: (content, size, mtime_utc)
    :raises PermissionError: 路径穿越
    :raises ScriptNotFound: slug 或文件不存在
    :raises ValidationError: 文件是二进制(UTF-8 解码失败)/ 超大
    """
    target = _safe_resolve(scripts_root, slug, rel_path)

    if not target.is_file():
        raise ScriptNotFound(
            f"文件不存在: {rel_path}",
            details={"slug": slug, "rel_path": rel_path},
        )

    size = target.stat().st_size
    if size > MAX_FILE_BYTES:
        raise PayloadTooLarge(
            f"文件 {rel_path!r} 大小 {size} > 上限 {MAX_FILE_BYTES}",
            details={"size": size, "limit": MAX_FILE_BYTES},
        )

    # 二进制后缀直接拒(避免一上来就把 .pyc 当字符串读)
    if target.suffix.lower() in BINARY_SUFFIXES:
        raise ValidationError(
            f"文件 {rel_path!r} 是二进制(后缀 {target.suffix}),不支持文本读取",
            details={"rel_path": rel_path, "suffix": target.suffix},
        )

    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError(
            f"文件 {rel_path!r} UTF-8 解码失败,可能是二进制",
            details={"rel_path": rel_path, "error": str(exc)},
        ) from exc
    except OSError as exc:
        raise ValidationError(
            f"文件读取失败 {rel_path!r}: {exc}",
            details={"rel_path": rel_path},
        ) from exc

    mtime = datetime.fromtimestamp(target.stat().st_mtime, tz=timezone.utc)
    return content, size, mtime


# ============================================================
# 单文件写(原子 + 备份)
# ============================================================
def write_file_text(
    scripts_root: Path,
    slug: str,
    rel_path: str,
    content: str,
    *,
    skip_dry_run: bool = False,
) -> tuple[str | None, DryRunResult | None]:
    """写文件 + 自动 dry-run + 备份旧版到 .backups/。

    流程:
    1. 路径安全 + 大小校验
    2. 写到同目录 tmp 文件(避免覆盖到一半失败)
    3. 若 ``skip_dry_run=False``:
       a. 把当前 scripts/<slug>/ 完整 copy 到 tmp_copy/
       b. 在 tmp_copy 里用新内容覆盖被改的那个文件
       c. dry_run_script(tmp_copy)
       d. 失败 → 不写盘,返回 (None, dry_run_result)
    4. dry-run 通过:
       a. 若旧文件存在 → 备份到 ``<slug>/.backups/<filename>.<ISO>.bak``
       b. ``os.replace(tmp_new, target)`` 原子替换
    5. 返回 (backup_path 或 None, dry_run_result 或 None)

    :returns: (backup_path_or_None, dry_run_result_or_None)
    """
    target = _safe_resolve(scripts_root, slug, rel_path)

    # 大小校验
    content_bytes = content.encode("utf-8")
    if len(content_bytes) > MAX_FILE_BYTES:
        raise PayloadTooLarge(
            f"文件内容 {len(content_bytes)} bytes > 上限 {MAX_FILE_BYTES}",
            details={
                "size": len(content_bytes),
                "limit": MAX_FILE_BYTES,
                "rel_path": rel_path,
            },
        )

    # .backups 目录内的备份不可编辑
    if BACKUPS_SUBDIR in rel_path.replace("\\", "/").split("/"):
        raise PermissionError(
            f".backups/ 内备份只读,不允许编辑: {rel_path!r}",
            details={"rel_path": rel_path},
        )

    # 二进制后缀拒
    if target.suffix.lower() in BINARY_SUFFIXES:
        raise ValidationError(
            f"文件 {rel_path!r} 是二进制(后缀 {target.suffix}),不支持文本写入",
            details={"rel_path": rel_path, "suffix": target.suffix},
        )

    # ===== dry-run =====
    dry_run_result: DryRunResult | None = None
    if not skip_dry_run:
        scripts_root_resolved = Path(scripts_root).resolve()
        slug_dir = scripts_root_resolved / slug
        with tempfile.TemporaryDirectory(prefix=f"dryrun-{slug}-") as tmp:
            tmp_path = Path(tmp)
            copy_dir = tmp_path / slug
            # 完整 copy(排除 .backups 节省时间)
            shutil.copytree(
                slug_dir,
                copy_dir,
                ignore=shutil.ignore_patterns(BACKUPS_SUBDIR, "_dry_run_data"),
            )
            # 在 copy 中用新内容覆盖
            copy_target = copy_dir / rel_path.replace("\\", "/")
            copy_target.parent.mkdir(parents=True, exist_ok=True)
            copy_target.write_bytes(content_bytes)

            dry_run_result = dry_run_script(copy_dir)

        if not dry_run_result.passed:
            logger.warning(
                "PUT files dry-run 失败 slug={} rel_path={} exit_code={}",
                slug,
                rel_path,
                dry_run_result.exit_code,
            )
            return None, dry_run_result

    # ===== 真正落盘:tmp + os.replace =====
    target.parent.mkdir(parents=True, exist_ok=True)

    # 1) 备份旧文件(若存在)
    backup_rel: str | None = None
    if target.is_file():
        backups_dir = (Path(scripts_root).resolve() / slug / BACKUPS_SUBDIR)
        backups_dir.mkdir(parents=True, exist_ok=True)
        # 文件名:foo.py → foo.py.2026-05-18T103030Z.bak(去掉 ":" 让 Windows 文件系统接受)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
        filename = target.name
        backup_path = backups_dir / f"{filename}.{ts}.bak"
        try:
            shutil.copy2(target, backup_path)
            backup_rel = backup_path.relative_to(
                Path(scripts_root).resolve() / slug
            ).as_posix()
        except OSError as exc:
            logger.warning("备份旧版失败 path={} err={}", target, exc)

    # 2) 写 tmp + os.replace
    tmp_target = target.parent / f".{target.name}.tmp-{uuid.uuid4().hex[:8]}"
    try:
        tmp_target.write_bytes(content_bytes)
        os.replace(tmp_target, target)
    except OSError as exc:
        # 清理 tmp
        try:
            if tmp_target.exists():
                tmp_target.unlink()
        except OSError:
            pass
        raise ValidationError(
            f"文件写入失败 {rel_path!r}: {exc}",
            details={"rel_path": rel_path},
        ) from exc

    logger.info(
        "PUT files 成功 slug={} rel_path={} size={} backup={}",
        slug,
        rel_path,
        len(content_bytes),
        backup_rel,
    )
    return backup_rel, dry_run_result


# ============================================================
# 删脚本(磁盘整目录)
# ============================================================
def delete_script_files(scripts_root: Path, slug: str) -> int:
    """rm -rf ``scripts/<slug>/`` 整目录。

    与 ``script_service.delete_script`` 互补:
    - ``delete_script(db, slug)`` 删 DB 行(级联 instance / run)
    - 本函数删磁盘

    设计稿 § 2.1:DELETE /scripts/{slug}?delete_files=true 同时调两者。

    :returns: 被删除文件总数(供日志/响应)
    :raises ScriptNotFound: 目录不存在
    """
    scripts_root = Path(scripts_root).resolve()
    target = scripts_root / slug

    if not target.is_dir():
        raise ScriptNotFound(
            f"脚本目录不存在: {slug}",
            details={"slug": slug, "path": str(target)},
        )

    # 安全校验:target 必须确实在 scripts_root 下(防 slug 含 .. 等)
    try:
        target.resolve().relative_to(scripts_root)
    except ValueError as exc:
        raise PermissionError(
            f"目标路径逃出 scripts_root: {target}",
            details={"slug": slug, "target": str(target)},
        ) from exc

    # 统计文件数
    file_count = sum(1 for _ in target.rglob("*") if _.is_file())

    try:
        shutil.rmtree(target)
    except OSError as exc:
        raise ValidationError(
            f"删除目录失败 {target}: {exc}",
            details={"path": str(target)},
        ) from exc

    logger.info("已删脚本目录 slug={} files_removed={}", slug, file_count)
    return file_count
