"""全局设置 service — settings 表 CRUD + 启动期 ensure_defaults + 内存缓存。

实现见 `进度/设计/后端架构.md` § 1.8 + § 2.6 + § 9.3。

公开
----
- ``get(db, key, default=...) -> Any``
- ``set(db, *, key, value, user_id=None) -> Setting``      白名单校验 + 类型轻校验
- ``list_all(db) -> list[Setting]``                        全部记录(含 is_secret)
- ``get_all_dict(db) -> dict[str, Any]``                   {key: value} 便于业务消费
- ``ensure_defaults(db) -> int``                           启动期插入预置 KV;返回新增数
- ``invalidate_cache(key=None) -> None``                   单 key 或全部失效
- ``DEFAULT_SETTINGS`` / ``ALLOWED_KEYS`` / ``SECRET_KEYS``  常量字典

预置 key 见 § 1.8 表:retention_days/timezone/default_timeout_sec/...
"""
from __future__ import annotations

import copy
import json
import threading
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.db.models.setting import Setting


# ============================================================
# 白名单 + 默认值 + 类型规则
# ============================================================
# 设计稿 § 1.8 预置 key 表
DEFAULT_SETTINGS: dict[str, dict[str, Any]] = {
    "retention_days": {
        "default": 30,
        "type": "int",
        "description": "runs 表保留天数,过期由清理任务删除",
        "is_secret": False,
        "validator": lambda v: isinstance(v, int) and 1 <= v <= 3650,
    },
    "runs_autoclean_enabled": {
        "default": False,
        "type": "bool",
        "description": "是否启用执行记录定时自动清理(每日按 retention_days 删旧 run)",
        "is_secret": False,
        "validator": lambda v: isinstance(v, bool),
    },
    "timezone": {
        "default": "Asia/Shanghai",
        "type": "str",
        "description": "系统时区,用于 cron 解析与 UI 展示",
        "is_secret": False,
        "validator": lambda v: isinstance(v, str) and 1 <= len(v) <= 64,
    },
    "default_timeout_sec": {
        "default": 300,
        "type": "int",
        "description": "实例未指定 timeout 时的兜底",
        "is_secret": False,
        "validator": lambda v: isinstance(v, int) and 1 <= v <= 86400,
    },
    "default_max_log_bytes": {
        "default": 262144,
        "type": "int",
        "description": "单次 run stdout/stderr 各自上限(字节)",
        "is_secret": False,
        "validator": lambda v: isinstance(v, int) and 1024 <= v <= 16 * 1024 * 1024,
    },
    "concurrent_runs_max": {
        "default": 4,
        "type": "int",
        "description": "同时运行的脚本上限",
        "is_secret": False,
        "validator": lambda v: isinstance(v, int) and 1 <= v <= 64,
    },
    "notify_on_first_failure_only": {
        "default": False,
        "type": "bool",
        "description": "true 时连续失败只通知第一次",
        "is_secret": False,
        "validator": lambda v: isinstance(v, bool),
    },
    "script_scan_on_startup": {
        "default": True,
        "type": "bool",
        "description": "启动时是否自动扫描 scripts/",
        "is_secret": False,
        "validator": lambda v: isinstance(v, bool),
    },
    "script_scan_interval_sec": {
        "default": 300,
        "type": "int",
        "description": "自动扫描间隔(0 = 关闭)",
        "is_secret": False,
        "validator": lambda v: isinstance(v, int) and 0 <= v <= 86400,
    },
    "session_ttl_hours": {
        "default": 24,
        "type": "int",
        "description": "登录会话有效期(小时)",
        "is_secret": False,
        "validator": lambda v: isinstance(v, int) and 1 <= v <= 24 * 30,
    },
    "lockout_threshold": {
        "default": 5,
        "type": "int",
        "description": "登录失败多少次后锁定",
        "is_secret": False,
        "validator": lambda v: isinstance(v, int) and 1 <= v <= 1000,
    },
    "lockout_minutes": {
        "default": 15,
        "type": "int",
        "description": "锁定时长(分钟)",
        "is_secret": False,
        "validator": lambda v: isinstance(v, int) and 1 <= v <= 1440,
    },
    # ============================================================
    # 应用外观品牌(站点标题 / Logo / 背景图)— 整个 dict 一项设置
    # 图片走 base64 data URL 内联存(value 是 dict,经 json.dumps 后存 value_json)
    # 单个 value_json 上限 ~3 MB(2 张图 + 文本元数据,SQLite TEXT 足够)
    # ============================================================
    "appearance": {
        "default": {
            "site_title": "签到管家",
            "site_subtitle": "",
            "sidebar_logo_text": "签",
            "logo_image_data_url": "",
            "background_image_data_url": "",
            "background_blur": 0,
            "background_opacity": 0.3,
            "background_blend_mode": "normal",
        },
        "type": "dict",
        "description": "应用外观品牌:站点标题 / 侧栏 logo 文本 / Logo 图(base64) / 背景图(base64) + 模糊/透明度/混合模式",
        "is_secret": False,
        "validator": lambda v: _validate_appearance(v),
    },
}


def _validate_appearance(v: object) -> bool:
    """appearance dict 校验。

    宽松策略:
    - 必须是 dict
    - 各字段类型基本对(string / number / 空字符串都行)
    - 图片 data URL 不强制 prefix 但限制总长度(单字段 < 3 MB,防 megaJSON 撑死 DB)
    - background_blur 0-20、background_opacity 0-1、blend_mode 在合法值
    - 允许部分字段缺失(取默认值)
    """
    if not isinstance(v, dict):
        return False
    # 字符串字段 + 长度上限
    string_limits = {
        "site_title": 128,
        "site_subtitle": 128,
        "sidebar_logo_text": 8,
        "logo_image_data_url": 3 * 1024 * 1024,
        "background_image_data_url": 3 * 1024 * 1024,
        "background_blend_mode": 32,
    }
    for key, max_len in string_limits.items():
        if key in v:
            val = v[key]
            if not isinstance(val, str):
                return False
            if len(val) > max_len:
                return False
    # 🔴 HIGH · code-review #3:logo / 背景图必须是 data:image/ 前缀,防 XSS
    # 攻击场景:管理员账号被盗,恶意设 logo='data:text/html,<script>...</script>',
    # 用户右键图片新 tab 打开会渲染 HTML → XSS。也防 javascript: URI scheme。
    for img_key in ("logo_image_data_url", "background_image_data_url"):
        if img_key in v:
            url = v[img_key]
            if url and not url.startswith("data:image/"):
                return False
    # blend_mode 合法值(CSS background-blend-mode)
    if "background_blend_mode" in v:
        bm = str(v["background_blend_mode"]).lower()
        if bm not in {
            "normal", "multiply", "screen", "overlay", "darken", "lighten",
            "color-dodge", "color-burn", "hard-light", "soft-light",
            "difference", "exclusion", "hue", "saturation", "color", "luminosity",
        }:
            return False
    # 数值字段范围
    if "background_blur" in v:
        bb = v["background_blur"]
        if not isinstance(bb, (int, float)) or isinstance(bb, bool):
            return False
        if not (0 <= float(bb) <= 40):
            return False
    if "background_opacity" in v:
        bo = v["background_opacity"]
        if not isinstance(bo, (int, float)) or isinstance(bo, bool):
            return False
        if not (0 <= float(bo) <= 1):
            return False
    return True

ALLOWED_KEYS: frozenset[str] = frozenset(DEFAULT_SETTINGS.keys())
SECRET_KEYS: frozenset[str] = frozenset(
    k for k, meta in DEFAULT_SETTINGS.items() if meta.get("is_secret")
)


# ============================================================
# 内存缓存
# ============================================================
_cache: dict[str, Any] = {}
_cache_lock = threading.Lock()


def invalidate_cache(key: str | None = None) -> None:
    """清除缓存。

    传 ``key=None`` 清空全部;否则只清单 key。
    """
    with _cache_lock:
        if key is None:
            _cache.clear()
        else:
            _cache.pop(key, None)


def _cache_get(key: str) -> Any | None:
    with _cache_lock:
        return _cache.get(key)


def _cache_set(key: str, value: Any) -> None:
    with _cache_lock:
        _cache[key] = value


# ============================================================
# 读
# ============================================================
_SENTINEL = object()


def get(db: Session, key: str, default: Any = _SENTINEL) -> Any:
    """读取单 key。

    流程:cache → DB → DEFAULT_SETTINGS → default 参数 → 抛 KeyError。
    """
    cached = _cache_get(key)
    if cached is not None:
        return cached

    row = db.get(Setting, key)
    if row is not None:
        try:
            value = json.loads(row.value_json)
        except json.JSONDecodeError as exc:  # pragma: no cover
            logger.warning("settings value_json 解析失败 key={} err={}", key, exc)
            value = None
        _cache_set(key, value)
        return value

    # 不在 DB,fallback 默认表
    # 🔴 HIGH · code-review #4:deepcopy 防 mutate 污染模块级共享 dict
    # 若调用方对返回值做 d['site_title']='x',会永久污染 DEFAULT_SETTINGS + _cache
    if key in DEFAULT_SETTINGS:
        raw = DEFAULT_SETTINGS[key]["default"]
        value = copy.deepcopy(raw) if isinstance(raw, (dict, list)) else raw
        _cache_set(key, value)
        return value

    if default is _SENTINEL:
        raise KeyError(f"settings key 未配置且无默认值: {key!r}")
    return default


def list_all(db: Session) -> list[Setting]:
    """全部记录(按 key 升序)。返回 ORM 行;脱敏由调用方决定。"""
    stmt = select(Setting).order_by(Setting.key.asc())
    return list(db.scalars(stmt).all())


def get_all_dict(db: Session) -> dict[str, Any]:
    """返回 ``{key: value}`` 字典(自动 fallback 到默认)。

    凡是 ``ALLOWED_KEYS`` 内的项都会在返回值里出现一次。
    """
    out: dict[str, Any] = {}
    rows = list_all(db)
    by_key = {r.key: r for r in rows}
    for key in ALLOWED_KEYS:
        row = by_key.get(key)
        if row is not None:
            try:
                out[key] = json.loads(row.value_json)
            except json.JSONDecodeError:  # pragma: no cover
                out[key] = DEFAULT_SETTINGS[key]["default"]
        else:
            out[key] = DEFAULT_SETTINGS[key]["default"]
    return out


# ============================================================
# 写
# ============================================================
def set_value(
    db: Session,
    *,
    key: str,
    value: Any,
    user_id: int | None = None,
) -> Setting:
    """写入/更新单 key。

    校验:
    1. key 必须在 ALLOWED_KEYS
    2. 通过 ``DEFAULT_SETTINGS[key]['validator']`` 类型/范围校验
    3. value 必须是 JSON serializable

    成功后清缓存。
    """
    if key not in ALLOWED_KEYS:
        raise ValidationError(
            f"未知 setting key: {key!r}",
            details={"key": key, "allowed": sorted(ALLOWED_KEYS)},
        )

    meta = DEFAULT_SETTINGS[key]
    validator = meta.get("validator")
    if callable(validator) and not validator(value):
        raise ValidationError(
            f"setting 值不符合类型/范围: key={key!r} value={value!r}",
            details={
                "key": key,
                "expected_type": meta.get("type"),
                "got_value": value,
            },
        )

    try:
        value_json = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            f"setting 值不可序列化为 JSON: {exc}",
            details={"key": key, "value": str(value)[:200]},
        ) from exc

    row = db.get(Setting, key)
    if row is None:
        row = Setting(
            key=key,
            value_json=value_json,
            description=meta.get("description"),
            is_secret=bool(meta.get("is_secret", False)),
            updated_by=user_id,
        )
        db.add(row)
    else:
        row.value_json = value_json
        if not row.description and meta.get("description"):
            row.description = meta["description"]
        row.is_secret = bool(meta.get("is_secret", False))
        row.updated_by = user_id

    db.flush()
    invalidate_cache(key)
    logger.info(
        "设置已更新 key={} updated_by={}",
        key,
        user_id,
    )
    return row


# 保留 set 作为别名(规格里要求,但实现避开了名字冲突)
set = set_value  # noqa: A001 — 显式别名,使用方调 settings_service.set(...) 仍工作


# ============================================================
# 启动期 ensure_defaults
# ============================================================
def ensure_defaults(db: Session) -> int:
    """启动期插入预置 KV;返回新增的行数。

    对已存在的 key 不动其值,只在缺失时插入默认值。
    """
    import builtins  # noqa: PLC0415 — 局部 import,避免模块顶层污染
    existing_keys: builtins.set[str] = builtins.set(
        db.scalars(select(Setting.key)).all()
    )
    inserted = 0
    for key, meta in DEFAULT_SETTINGS.items():
        if key in existing_keys:
            continue
        try:
            value_json = json.dumps(
                meta["default"], ensure_ascii=False, separators=(",", ":")
            )
        except (TypeError, ValueError):
            continue
        row = Setting(
            key=key,
            value_json=value_json,
            description=meta.get("description"),
            is_secret=bool(meta.get("is_secret", False)),
        )
        db.add(row)
        inserted += 1
    if inserted:
        db.flush()
        logger.info("ensure_defaults 插入预置设置 {} 项", inserted)
    return inserted
