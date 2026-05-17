"""字段类型系统 — 11 种类型 + 实例 config 校验 + secret 字段处理。

详见 `进度/设计/后端架构.md` § 3.2 / § 5.2。

公开接口:
- ``validate_config(config, fields) -> dict`` 严格校验并返回清洗后的 config(类型已转,
  缺失 default 已填)
- ``mask_secrets(config, fields) -> tuple[dict, dict[str, bool]]``
  GET 响应脱敏:secret 字段值置为 ``None``,同时返回 ``_secret_set`` 指示哪些字段已配置
- ``merge_secrets(old_config, new_partial, fields) -> dict``
  PATCH 时:新值缺失的 secret 字段保留旧值(§ 5.2 关键语义)

校验失败抛 :class:`app.core.exceptions.ConfigSchemaError`,``details`` 形如
``{"errors": {field_key: error_message, ...}}``。

注意:secret 字段在这里**不做加密**,加密由 service 层负责
(``app.core.crypto.get_cipher().encrypt_dict()``)。
"""
from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

from apscheduler.triggers.cron import CronTrigger

from app.core.exceptions import ConfigSchemaError
from app.plugins.manifest import ManifestField


# ============================================================
# 公开 API
# ============================================================
def validate_config(
    config: dict[str, Any],
    fields: list[ManifestField],
) -> dict[str, Any]:
    """按 fields_schema 校验 + 清洗 config。

    流程:
    1. 检查 config 中是否有未声明的 key(严格,失败)
    2. 逐字段:
       - 缺失 → 若 required 报错;否则填 default
       - 存在 → 按 type 校验 + 类型转换
    3. 返回清洗后的新 dict(不修改入参)

    :param config: 用户提交的 raw 配置
    :param fields: manifest 解析后的字段定义列表
    :returns: 清洗后的 config(类型已转换、default 已填充)
    :raises ConfigSchemaError: 任意字段校验失败
    """
    if not isinstance(config, dict):
        raise ConfigSchemaError(
            message="config 必须是 dict",
            details={"errors": {"_root": f"期望 dict,实际 {type(config).__name__}"}},
        )

    errors: dict[str, str] = {}
    cleaned: dict[str, Any] = {}
    declared_keys = {f.key for f in fields}

    # 1. 未声明的 key — 直接报错(严格模式,防止 typo / 旧字段残留)
    for k in config:
        if k not in declared_keys:
            errors[k] = "未在 manifest.fields 中声明的字段"

    # 2. 逐字段校验
    for f in fields:
        key = f.key
        if key in config:
            try:
                cleaned[key] = _validate_field_value(config[key], f)
            except _FieldError as exc:
                errors[key] = str(exc)
        else:
            # 字段未提交
            if f.required:
                errors[key] = "必填字段缺失"
            elif f.default is not None:
                cleaned[key] = f.default
            # 否则:可选 + 无默认 → 不写入 cleaned

    if errors:
        raise ConfigSchemaError(
            message=f"实例 config 校验失败 ({len(errors)} 个错误)",
            details={"errors": errors},
        )

    return cleaned


def mask_secrets(
    config: dict[str, Any],
    fields: list[ManifestField],
) -> tuple[dict[str, Any], dict[str, bool]]:
    """GET 响应脱敏。

    - secret 字段在返回 dict 中置为 ``None``
    - 同时返回 ``_secret_set`` 字典,标识每个 secret 字段是否已配置过非空值

    :returns: (脱敏后的 config 副本, secret 字段配置状态字典)
    """
    masked = dict(config)
    secret_set: dict[str, bool] = {}
    for f in fields:
        if f.type == "secret":
            v = config.get(f.key)
            secret_set[f.key] = bool(v)  # 非空字符串才算"已设置"
            masked[f.key] = None
    return masked, secret_set


def merge_secrets(
    old_config: dict[str, Any],
    new_partial: dict[str, Any],
    fields: list[ManifestField],
) -> dict[str, Any]:
    """PATCH 合并:secret 字段缺失时保留旧值,其他字段以新值覆盖(若提供)。

    用于 PATCH /instances/{id} 场景:用户只想改 cron / name,不重输密码。

    流程:
    1. 以 ``old_config`` 为基底
    2. 用 ``new_partial`` 中**显式提供**的字段覆盖
       - 例外:secret 字段若 ``new_partial[key]`` 为 None / 缺失,保留 old 值
       - secret 字段若 ``new_partial[key]`` 为空字符串,亦保留 old 值
    3. 返回合并结果(未做 schema 校验,后续应再过 ``validate_config``)
    """
    secret_keys = {f.key for f in fields if f.type == "secret"}
    merged = dict(old_config)
    for k, v in new_partial.items():
        if k in secret_keys:
            # secret 字段:None / 空字符串 → 保留旧值(用户没改密码)
            if v is None or (isinstance(v, str) and v == ""):
                continue
        merged[k] = v
    return merged


# ============================================================
# 内部:单字段校验
# ============================================================
class _FieldError(ValueError):
    """单字段校验错误(内部用,会被收集到 errors 字典)。"""


_FIELD_VALIDATORS: dict[str, Any] = {}  # 末尾注册


def _validate_field_value(value: Any, field: ManifestField) -> Any:
    """按 field.type 派发校验函数,返回类型转换后的值。"""
    validator = _FIELD_VALIDATORS.get(field.type)
    if validator is None:  # pragma: no cover — manifest 解析阶段已限制
        raise _FieldError(f"未知字段类型: {field.type}")
    return validator(value, field)


# ---------- 各 type 的校验器 ----------
def _v_string(value: Any, f: ManifestField) -> str:
    if not isinstance(value, str):
        raise _FieldError(f"期望字符串,实际 {type(value).__name__}")
    if f.min_length is not None and len(value) < f.min_length:
        raise _FieldError(f"长度 < min_length ({f.min_length})")
    if f.max_length is not None and len(value) > f.max_length:
        raise _FieldError(f"长度 > max_length ({f.max_length})")
    if f.pattern is not None and not re.match(f.pattern, value):
        raise _FieldError(f"不匹配 pattern: {f.pattern}")
    return value


def _v_secret(value: Any, f: ManifestField) -> str:
    # secret 与 string 校验逻辑相同,只是存储/返回语义不同
    return _v_string(value, f)


def _v_integer(value: Any, f: ManifestField) -> int:
    # bool 是 int 的子类,需要显式排除
    if isinstance(value, bool) or not isinstance(value, int):
        # 容忍字符串数字
        if isinstance(value, str):
            try:
                value = int(value)
            except ValueError as exc:
                raise _FieldError(f"无法解析为整数: {exc}") from exc
        else:
            raise _FieldError(f"期望整数,实际 {type(value).__name__}")
    if f.min is not None and value < f.min:
        raise _FieldError(f"< min ({f.min})")
    if f.max is not None and value > f.max:
        raise _FieldError(f"> max ({f.max})")
    if f.step is not None and f.step > 1:
        # 以 min(若有) 为锚点检查 step;无 min 则以 0 为锚
        anchor = f.min if f.min is not None else 0
        if (value - anchor) % f.step != 0:
            raise _FieldError(f"不在 step ({f.step}) 网格上")
    return value


def _v_boolean(value: Any, _f: ManifestField) -> bool:
    if isinstance(value, bool):
        return value
    # 容忍 "true"/"false" / 0/1
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        low = value.strip().lower()
        if low in {"true", "1", "yes", "on"}:
            return True
        if low in {"false", "0", "no", "off", ""}:
            return False
    raise _FieldError(f"无法解析为布尔: {value!r}")


def _v_select(value: Any, f: ManifestField) -> str:
    if not isinstance(value, str):
        raise _FieldError(f"select 期望字符串,实际 {type(value).__name__}")
    valid = {opt.value for opt in (f.options or [])}
    if value not in valid:
        raise _FieldError(f"值 {value!r} 不在 options 中: {sorted(valid)}")
    return value


def _v_multiselect(value: Any, f: ManifestField) -> list[str]:
    if not isinstance(value, list):
        raise _FieldError(f"multiselect 期望数组,实际 {type(value).__name__}")
    valid = {opt.value for opt in (f.options or [])}
    bad = [v for v in value if v not in valid]
    if bad:
        raise _FieldError(f"包含未声明选项: {bad}")
    if f.min_items is not None and len(value) < f.min_items:
        raise _FieldError(f"元素数 < min_items ({f.min_items})")
    if f.max_items is not None and len(value) > f.max_items:
        raise _FieldError(f"元素数 > max_items ({f.max_items})")
    # 去重保序
    seen: list[str] = []
    for v in value:
        if v not in seen:
            seen.append(v)
    return seen


def _v_multiline(value: Any, f: ManifestField) -> str:
    return _v_string(value, f)


def _v_cron(value: Any, _f: ManifestField) -> str:
    if not isinstance(value, str):
        raise _FieldError(f"cron 期望字符串,实际 {type(value).__name__}")
    try:
        CronTrigger.from_crontab(value)
    except (ValueError, KeyError) as exc:
        raise _FieldError(f"非法 cron 表达式: {exc}") from exc
    return value


def _v_url(value: Any, f: ManifestField) -> str:
    if not isinstance(value, str):
        raise _FieldError(f"url 期望字符串,实际 {type(value).__name__}")
    try:
        parsed = urlparse(value)
    except ValueError as exc:
        raise _FieldError(f"URL 解析失败: {exc}") from exc
    if not parsed.scheme or not parsed.netloc:
        raise _FieldError("URL 缺少 scheme 或 host")
    allowed = [s.lower() for s in (f.schemes if f.schemes is not None else ["http", "https"])]
    if parsed.scheme.lower() not in allowed:
        raise _FieldError(f"scheme {parsed.scheme!r} 不在白名单 {allowed}")
    return value


def _v_json(value: Any, _f: ManifestField) -> Any:
    """json 字段:可接受已经是 dict/list 的值;字符串会尝试 json.loads。

    schema 校验暂不实现(留待 v2 + jsonschema 库)。
    """
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise _FieldError(f"JSON 解析失败: {exc}") from exc
    raise _FieldError(f"json 期望 dict/list/json-string,实际 {type(value).__name__}")


_FIELD_VALIDATORS.update(
    {
        "string": _v_string,
        "secret": _v_secret,
        "integer": _v_integer,
        "boolean": _v_boolean,
        "select": _v_select,
        "multiselect": _v_multiselect,
        "multiline": _v_multiline,
        "cron": _v_cron,
        "url": _v_url,
        "json": _v_json,
    }
)
