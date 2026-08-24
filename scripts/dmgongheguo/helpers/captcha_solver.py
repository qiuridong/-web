"""动漫共和国算术验证码的本地、高置信识别器。

设计目标不是强行识别每一张图，而是只提交高置信结果；其余图片由调用方
点击刷新。当前发布版仅自动提交清晰的乘法题。加、减、除法会被明确拒绝并
刷新，避免把 ``÷`` 的随机扭曲字形错当成 ``×``。

运行时依赖由 ``main.py`` 安装到实例 data_dir 下的独立 Python 3.12 venv：
ddddocr、onnxruntime、opencv-python、numpy、Pillow。这个文件也可直接作为
JSON-lines 服务启动，模型只加载一次。
"""

# Chinese UI copy intentionally uses full-width punctuation.
# ruff: noqa: RUF001, RUF002, RUF003

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import math
import re
import sys
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import cv2
import ddddocr
import numpy as np
from PIL import Image, UnidentifiedImageError

SCREEN_SIZE = (720, 1280)
CAPTCHA_ROI = (230, 535, 690, 685)
FORMULA_IN_CAPTCHA = (60, 20, 430, 120)
PROFILE_IDENTITY_ROI = (150, 140, 540, 200)
PROFILE_SIGNATURE_SIZE = (192, 48)

# token 总数 = 左操作数位数 + 运算符 + 右操作数位数 + '=' + '?'
GRAMMARS: tuple[tuple[str, int, int], ...] = (
    ("1x1", 1, 1),
    ("1x2", 1, 2),
    ("2x1", 2, 1),
    ("2x2", 2, 2),
)

DIGITS = "0123456789"
OCR_OPERATORS = "+-xX*×÷/"


class SolverError(RuntimeError):
    """输入图像或 OCR 运行时不满足固定合同。"""


def _json_safe(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def _decode_png(payload: bytes) -> np.ndarray:
    try:
        with Image.open(io.BytesIO(payload)) as source:
            source.load()
            return np.asarray(source.convert("RGB"))
    except (OSError, ValueError, UnidentifiedImageError) as exc:
        raise SolverError(f"invalid PNG: {type(exc).__name__}") from exc


def _captcha_crop(frame: np.ndarray) -> np.ndarray:
    height, width = frame.shape[:2]
    if (width, height) == SCREEN_SIZE:
        x1, y1, x2, y2 = CAPTCHA_ROI
        return frame[y1:y2, x1:x2].copy()
    if (width, height) == (
        CAPTCHA_ROI[2] - CAPTCHA_ROI[0],
        CAPTCHA_ROI[3] - CAPTCHA_ROI[1],
    ):
        return frame.copy()
    raise SolverError(
        f"unsupported image size {width}x{height}; expected 720x1280 or 460x150"
    )


def _formula_area(captcha: np.ndarray) -> np.ndarray:
    x1, y1, x2, y2 = FORMULA_IN_CAPTCHA
    return captcha[y1:y2, x1:x2].copy()


def _fingerprint(formula: np.ndarray) -> str:
    # 像素哈希而不是 PNG 字节哈希，避免编码器元数据造成假变化。
    return hashlib.sha256(formula.tobytes()).hexdigest()


def _pink_ratio(image: np.ndarray) -> float:
    r = image[:, :, 0]
    g = image[:, :, 1]
    b = image[:, :, 2]
    return float(((r > 210) & (g < 125) & (b < 145)).mean())


def _white_ratio(image: np.ndarray) -> float:
    return float((image.min(axis=2) > 235).mean())


def _fixed_similarity(a: np.ndarray, b: np.ndarray) -> float:
    if a.shape != b.shape:
        return 0.0
    ag = cv2.cvtColor(a, cv2.COLOR_RGB2GRAY).astype(np.float32)
    bg = cv2.cvtColor(b, cv2.COLOR_RGB2GRAY).astype(np.float32)
    # 平均绝对误差会被大面积深色背景“稀释”，曾把登录表单误判成“我的”页。
    # 同尺寸归一化相关系数会去掉整体亮度基线，只比较真实结构/文字/图标。
    score = float(cv2.matchTemplate(ag, bg, cv2.TM_CCOEFF_NORMED)[0, 0])
    return max(0.0, min(1.0, score))


def _load_rgb(path: Path) -> np.ndarray:
    try:
        with Image.open(path) as source:
            source.load()
            return np.asarray(source.convert("RGB"))
    except (OSError, ValueError, UnidentifiedImageError) as exc:
        raise SolverError(f"invalid template {path.name}: {type(exc).__name__}") from exc


def inspect_ui(frame: np.ndarray, assets_dir: Path) -> dict[str, Any]:
    """按固定 720x1280 几何对当前界面做 fail-closed 分类。"""

    height, width = frame.shape[:2]
    if (width, height) != SCREEN_SIZE:
        raise SolverError(f"UI inspection requires 720x1280, got {width}x{height}")

    captcha_panel = frame[565:763, 51:668]
    captcha_confirm = frame[666:736, 398:650]
    captcha_score = min(
        _white_ratio(captcha_panel),
        _pink_ratio(captcha_confirm) * 1.7,
    )
    if _white_ratio(captcha_panel) >= 0.64 and _pink_ratio(captcha_confirm) >= 0.48:
        formula = _formula_area(_captcha_crop(frame))
        return {
            "surface": "captcha",
            "confidence": min(1.0, captcha_score),
            "formula_fingerprint": _fingerprint(formula),
        }

    announcement_panel = frame[265:1062, 43:677]
    announcement_bottom = frame[970:1045, 390:655]
    if (
        _white_ratio(announcement_panel) >= 0.58
        and _pink_ratio(announcement_bottom) >= 0.002
    ):
        return {
            "surface": "announcement",
            "confidence": min(1.0, _white_ratio(announcement_panel)),
        }

    login_button = frame[625:701, 55:665]
    phone_template_path = assets_dir / "ui" / "login-phone-mode.png"
    email_template_path = assets_dir / "ui" / "login-email-mode.png"
    # 只比较底部“切换为…登录”区域，避开账号和密码字段。登录请求处理中
    # 按钮会由粉色变灰，因此表单识别不能依赖按钮颜色。
    mode_roi = frame[700:780, 45:675]
    scores: dict[str, float] = {}
    if phone_template_path.is_file():
        scores["phone"] = _fixed_similarity(mode_roi, _load_rgb(phone_template_path))
    if email_template_path.is_file():
        scores["email"] = _fixed_similarity(mode_roi, _load_rgb(email_template_path))
    mode = max(scores, key=scores.get) if scores else "unknown"
    mode_score = scores.get(mode, 0.0)
    login_button_active = _pink_ratio(login_button) >= 0.62
    if mode_score >= 0.94 or login_button_active:
        if mode_score < 0.94:
            mode = "unknown"
        return {
            "surface": "login_form",
            "confidence": max(mode_score, min(1.0, _pink_ratio(login_button))),
            "login_mode": mode,
            "mode_scores": scores,
            "login_button_active": login_button_active,
        }

    ui_dir = assets_dir / "ui"
    task_nav_path = ui_dir / "task-nav.png"
    task_layout_path = ui_dir / "task-layout.png"
    task_ready_path = ui_dir / "task-ready-top.png"
    task_signed_path = ui_dir / "task-signed-top.png"
    task_paths = (
        task_nav_path,
        task_layout_path,
        task_ready_path,
        task_signed_path,
    )
    if all(path.is_file() for path in task_paths):
        task_nav_score = _fixed_similarity(
            frame[1140:1280, 0:720], _load_rgb(task_nav_path)
        )
        task_layout_score = _fixed_similarity(
            frame[365:875, 25:695], _load_rgb(task_layout_path)
        )
        ready_score = _fixed_similarity(
            frame[145:345, 250:470], _load_rgb(task_ready_path)
        )
        signed_score = _fixed_similarity(
            frame[145:345, 250:470], _load_rgb(task_signed_path)
        )
        success_panel = frame[590:862, 85:635]
        if (
            task_nav_score >= 0.90
            and signed_score >= 0.90
            and _white_ratio(success_panel) >= 0.65
        ):
            return {
                "surface": "task_success_dialog",
                "confidence": min(task_nav_score, signed_score),
            }
        if task_nav_score >= 0.90 and task_layout_score >= 0.94:
            if ready_score >= 0.88 and ready_score > signed_score:
                surface = "task_ready"
                state_score = ready_score
            elif signed_score >= 0.88 and signed_score > ready_score:
                surface = "task_signed"
                state_score = signed_score
            else:
                surface = "unknown"
                state_score = 0.0
            return {
                "surface": surface,
                "confidence": min(task_nav_score, task_layout_score, state_score),
                "scores": {
                    "nav": task_nav_score,
                    "layout": task_layout_score,
                    "ready": ready_score,
                    "signed": signed_score,
                },
            }

    required = {
        "header": ui_dir / "my-logged-out-header.png",
        "grid": ui_dir / "my-grid.png",
        "nav": ui_dir / "my-nav.png",
    }
    if all(path.is_file() for path in required.values()):
        header = frame[130:285, 25:700]
        grid = frame[555:830, 25:700]
        nav = frame[1140:1280, 0:720]
        header_score = _fixed_similarity(header, _load_rgb(required["header"]))
        grid_score = _fixed_similarity(grid, _load_rgb(required["grid"]))
        nav_score = _fixed_similarity(nav, _load_rgb(required["nav"]))
        if grid_score >= 0.88 and nav_score >= 0.88:
            if header_score >= 0.90:
                surface = "my_logged_out"
                confidence = min(header_score, grid_score, nav_score)
            elif header_score <= 0.84:
                surface = "my_logged_in"
                confidence = min(grid_score, nav_score, 1.0 - header_score)
            else:
                surface = "unknown"
                confidence = 0.0
            return {
                "surface": surface,
                "confidence": confidence,
                "scores": {
                    "header": header_score,
                    "grid": grid_score,
                    "nav": nav_score,
                },
            }

    home_nav_path = ui_dir / "home-nav.png"
    if home_nav_path.is_file():
        home_nav_score = _fixed_similarity(
            frame[1140:1280, 0:720], _load_rgb(home_nav_path)
        )
        if home_nav_score >= 0.90:
            return {
                "surface": "home",
                "confidence": home_nav_score,
                "scores": {"nav": home_nav_score},
            }

    return {"surface": "unknown", "confidence": 0.0}


def inspect_profile_identity(frame: np.ndarray) -> dict[str, Any]:
    """提取“我的”页昵称字形签名，不返回昵称文字或原始截图。"""

    height, width = frame.shape[:2]
    if (width, height) != SCREEN_SIZE:
        raise SolverError(
            f"profile inspection requires 720x1280, got {width}x{height}"
        )
    x1, y1, x2, y2 = PROFILE_IDENTITY_ROI
    roi = frame[y1:y2, x1:x2]
    mask = (
        (roi[:, :, 0] > 190)
        & (roi[:, :, 1] > 190)
        & (roi[:, :, 2] > 190)
    ).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    kept = np.zeros_like(mask)
    for component in range(1, count):
        _, _, _, component_height, area = (
            int(value) for value in stats[component]
        )
        if area >= 3 and component_height >= 3:
            kept[labels == component] = 1
    ys, xs = np.where(kept)
    if len(xs) < 25:
        raise SolverError("profile identity region has insufficient foreground")
    cropped = kept[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    normalized = cv2.resize(
        cropped,
        PROFILE_SIGNATURE_SIZE,
        interpolation=cv2.INTER_NEAREST,
    )
    signature = hashlib.sha256(np.packbits(normalized).tobytes()).hexdigest()
    return {
        "profile_signature": signature,
        "ink_pixels": int(kept.sum()),
        "bounding_box": [
            int(xs.min()),
            int(ys.min()),
            int(xs.max()),
            int(ys.max()),
        ],
        "policy": "nickname_glyph_sha256_v1",
    }


def _pad_square(image: np.ndarray, padding: int = 20) -> Image.Image:
    if image.ndim == 2:
        image = np.repeat(image[:, :, None], 3, axis=2)
    height, width = image.shape[:2]
    size = max(height, width) + padding
    canvas = np.full((size, size, 3), 255, dtype=np.uint8)
    y = (size - height) // 2
    x = (size - width) // 2
    canvas[y : y + height, x : x + width] = image
    return Image.fromarray(canvas).resize((160, 160))


def _select_component(window: np.ndarray, threshold: int) -> np.ndarray | None:
    ink = 255 - window.min(axis=2)
    mask = (ink > 255 - threshold).astype(np.uint8)
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)
    height, width = mask.shape
    candidates: list[tuple[float, int, tuple[int, int, int, int]]] = []
    for component in range(1, count):
        x, y, w, h, area = (int(v) for v in stats[component])
        if area < 6 or h < 6:
            continue
        cx, cy = centroids[component]
        strength = float(ink[labels == component].mean()) / 255.0
        centrality = math.exp(
            -((cx - width / 2) / (width * 0.38)) ** 2
            -((cy - height * 0.57) / (height * 0.38)) ** 2
        )
        shape = (min(h, 45) / 25) ** 1.2 * (min(w, 35) / 15) ** 0.3
        score = area * strength**1.5 * centrality * shape
        candidates.append((score, component, (x, y, w, h)))
    if not candidates:
        return None
    _, component, (x, y, w, h) = max(candidates)
    selected = (labels == component).astype(np.uint8) * 255
    y1, y2 = max(0, y - 3), min(height, y + h + 3)
    x1, x2 = max(0, x - 3), min(width, x + w + 3)
    # ddddocr 需要黑字白底。
    return 255 - selected[y1:y2, x1:x2]


def _ocr_text(engine: ddddocr.DdddOcr, image: np.ndarray, ranges: str) -> str:
    engine.set_ranges(ranges)
    result = engine.classification(_pad_square(image), probability=False)
    return str(result or "").strip()


def _digit_vote(
    engine: ddddocr.DdddOcr,
    formula: np.ndarray,
    *,
    center: float,
    spacing: float,
) -> dict[str, Any]:
    half_width = max(12, int(spacing * 0.47))
    x = round(center)
    window = formula[
        18:100,
        max(0, x - half_width) : min(formula.shape[1], x + half_width + 1),
    ]
    component_votes: Counter[str] = Counter()
    window_votes: Counter[str] = Counter()
    raw_texts: list[str] = []
    for threshold in (130, 160, 190, 220, 235):
        selected = _select_component(window, threshold)
        if selected is not None:
            text = _ocr_text(engine, selected, DIGITS)
            if len(text) == 1 and text in DIGITS:
                component_votes[text] += 1
        binary = np.where(window.min(axis=2) < threshold, 0, 255).astype(np.uint8)
        text = _ocr_text(engine, binary, DIGITS)
        raw_texts.append(text)
        if len(text) == 1 and text in DIGITS:
            window_votes[text] += 1

    weighted = {
        digit: component_votes[digit] * 2 + window_votes[digit]
        for digit in DIGITS
    }
    digit = max(DIGITS, key=lambda item: weighted[item])
    component_count = component_votes[digit]
    window_count = window_votes[digit]
    accepted = component_count >= 2 or (component_count >= 1 and window_count >= 2)
    if component_count >= 2:
        confidence = min(1.0, 0.82 + 0.05 * (component_count - 2) + 0.03 * window_count)
    elif component_count >= 1 and window_count >= 2:
        confidence = min(0.92, 0.78 + 0.04 * (window_count - 2))
    elif component_count >= 1 and window_count >= 1:
        # 单组件票 + 单整窗票本身不足以放行，但可被两次整行一致结果交叉确认。
        confidence = 0.72
    else:
        confidence = min(0.69, weighted[digit] / 7.0)
    return {
        "accepted": accepted,
        "char": digit,
        "confidence": confidence,
        "component_votes": dict(component_votes),
        "window_votes": dict(window_votes),
        "raw_texts": raw_texts,
    }


def _operator_feature(window: np.ndarray) -> np.ndarray:
    ink = (255 - window.min(axis=2)).astype(np.float32) / 255.0
    ink = np.clip((ink - 0.10) / 0.90, 0.0, 1.0) ** 2
    ink = cv2.resize(ink, (32, 48), interpolation=cv2.INTER_AREA)
    gx = cv2.Sobel(ink, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(ink, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = np.sqrt(gx * gx + gy * gy)
    feature = np.concatenate(
        (ink.ravel(), magnitude.ravel(), ink.sum(axis=0), ink.sum(axis=1))
    ).astype(np.float32)
    feature -= float(feature.mean())
    feature /= float(np.linalg.norm(feature)) + 1e-9
    return feature


def _load_operator_features(assets_dir: Path) -> dict[str, list[np.ndarray]]:
    result: dict[str, list[np.ndarray]] = {"multiply": [], "other": []}
    root = assets_dir / "operators"
    for group in result:
        directory = root / group
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.png")):
            result[group].append(_operator_feature(_load_rgb(path)))
    if not result["multiply"] or not result["other"]:
        raise SolverError("operator template bank is incomplete")
    return result


def _operator_vote(
    engine: ddddocr.DdddOcr,
    formula: np.ndarray,
    *,
    center: float,
    spacing: float,
    templates: dict[str, list[np.ndarray]],
) -> dict[str, Any]:
    half_width = max(12, int(spacing * 0.47))
    x = round(center)
    window = formula[
        18:100,
        max(0, x - half_width) : min(formula.shape[1], x + half_width + 1),
    ]
    feature = _operator_feature(window)
    multiply_score = max(float(feature @ item) for item in templates["multiply"])
    other_score = max(float(feature @ item) for item in templates["other"])
    margin = multiply_score - other_score

    votes = 0
    texts: list[str] = []
    for threshold in (130, 160, 190, 220, 235):
        selected = _select_component(window, threshold)
        if selected is None:
            texts.append("")
            continue
        text = _ocr_text(engine, selected, OCR_OPERATORS)
        texts.append(text)
        if text in {"x", "X", "×", "*"}:
            votes += 1

    # 两条独立高置信通道：模板相对其它运算符拉开足够距离，或 OCR 五个
    # 阈值至少四票一致且模板也偏向乘法。后者覆盖清晰实心 ×，前者覆盖
    # 随机描边/扭曲 ×。像 ``÷`` 的沙漏形通常只能拿到三票，因此不会提交。
    accepted = margin >= 0.15 or (
        votes >= 4 and margin >= 0.04 and multiply_score >= 0.45
    )
    confidence = min(
        1.0,
        max(0.0, margin) / 0.25 * 0.65 + votes / 5.0 * 0.35,
    )
    return {
        "accepted": accepted,
        "operator": "*" if accepted else None,
        "confidence": confidence,
        "margin": margin,
        "multiply_score": multiply_score,
        "other_score": other_score,
        "ocr_votes": votes,
        "ocr_texts": texts,
    }


def _normalize_ocr_expression(text: str) -> str:
    value = text.replace("×", "x").replace("X", "x").replace("*", "x")
    value = value.replace("÷", "/")
    return re.sub(r"[^0-9x+\-/]", "", value)


def _whole_formula_votes(
    engine: ddddocr.DdddOcr,
    formula: np.ndarray,
) -> list[str]:
    values: list[str] = []
    engine.set_ranges(DIGITS + OCR_OPERATORS + "=?")
    for threshold in (None, 160, 190, 220):
        if threshold is None:
            image = formula[15:100]
        else:
            area = formula[15:100]
            binary = np.where(area.min(axis=2) < threshold, 0, 255).astype(np.uint8)
            image = np.repeat(binary[:, :, None], 3, axis=2)
        result = engine.classification(
            Image.fromarray(image).resize((740, 200)), probability=False
        )
        values.append(_normalize_ocr_expression(str(result or "")))
    return values


def _candidate_support(left: str, right: str, whole_votes: Iterable[str]) -> int:
    pattern = re.compile(re.escape(left) + r"x" + re.escape(right))
    return sum(1 for value in whole_votes if pattern.search(value))


def _candidate_operand_support(left: str, right: str, whole_votes: Iterable[str]) -> int:
    """统计整行 OCR 对同一操作数布局的支持，不要求其认对运算符。"""

    pattern = re.compile(re.escape(left) + r"[x+\-/]" + re.escape(right))
    return sum(1 for value in whole_votes if pattern.search(value))


def solve_captcha(
    frame: np.ndarray,
    *,
    assets_dir: Path,
    engine: ddddocr.DdddOcr,
    min_confidence: float,
) -> dict[str, Any]:
    captcha = _captcha_crop(frame)
    formula = _formula_area(captcha)
    fingerprint = _fingerprint(formula)
    templates = _load_operator_features(assets_dir)
    whole_votes = _whole_formula_votes(engine, formula)
    candidates: list[dict[str, Any]] = []

    for grammar_name, left_digits, right_digits in GRAMMARS:
        token_count = left_digits + 1 + right_digits + 2
        centers = np.linspace(60.0, 275.0, token_count)
        spacing = float(centers[1] - centers[0])
        operator_index = left_digits
        digit_indexes = list(range(left_digits)) + list(
            range(operator_index + 1, operator_index + 1 + right_digits)
        )
        digit_results = [
            _digit_vote(
                engine,
                formula,
                center=float(centers[index]),
                spacing=spacing,
            )
            for index in digit_indexes
        ]
        operator = _operator_vote(
            engine,
            formula,
            center=float(centers[operator_index]),
            spacing=spacing,
            templates=templates,
        )
        left = "".join(item["char"] for item in digit_results[:left_digits])
        right = "".join(item["char"] for item in digit_results[left_digits:])
        support = _candidate_support(left, right, whole_votes)
        operand_support = _candidate_operand_support(left, right, whole_votes)
        digits_ok = all(bool(item["accepted"]) for item in digit_results)
        weak_digits_ok = all(
            int(item["component_votes"].get(item["char"], 0)) >= 1
            and int(item["window_votes"].get(item["char"], 0)) >= 1
            for item in digit_results
        )
        whole_backed = support >= 2 and weak_digits_ok
        template_backed = (
            digits_ok
            and operand_support >= 1
            and float(operator["margin"]) >= 0.30
            and float(operator["multiply_score"]) >= 0.72
        )
        accepted = bool(operator["accepted"]) and (
            (digits_ok and support >= 1) or whole_backed or template_backed
        )
        digit_confidence = min(
            (float(item["confidence"]) for item in digit_results), default=0.0
        )
        if whole_backed:
            digit_confidence = max(digit_confidence, 0.80)
        evidence_confidence = (
            min(1.0, 0.78 + support * 0.08)
            if support
            else (0.80 if template_backed else 0.0)
        )
        operator_confidence = float(operator["confidence"])
        if bool(operator["accepted"]) and support >= 3:
            # 三种以上整行渲染均读出同一 ``左×右`` 时，整行通道已经独立
            # 补足了局部运算符模板的弱分；仍要求局部分类器先判为乘法，因而
            # ``÷`` 被整行 OCR 误读成 x 的样本不会借此越过保护线。
            operator_confidence = max(operator_confidence, 0.80)
        confidence = min(
            digit_confidence,
            operator_confidence,
            evidence_confidence,
        )
        candidates.append(
            {
                "grammar": grammar_name,
                "left": left,
                "right": right,
                "expression": f"{left}*{right}",
                "accepted": accepted and confidence >= min_confidence,
                "confidence": confidence,
                "whole_support": support,
                "operand_support": operand_support,
                "whole_backed": whole_backed,
                "template_backed": template_backed,
                "digits": digit_results,
                "operator": operator,
            }
        )

    accepted_candidates = [item for item in candidates if item["accepted"]]
    accepted_candidates.sort(key=lambda item: float(item["confidence"]), reverse=True)
    unique_expressions = {str(item["expression"]) for item in accepted_candidates}
    if not accepted_candidates:
        reason = "no_high_confidence_multiplication"
        result: dict[str, Any] = {
            "accepted": False,
            "reason": reason,
            "confidence": max(
                (float(item["confidence"]) for item in candidates), default=0.0
            ),
        }
    elif len(unique_expressions) != 1:
        result = {
            "accepted": False,
            "reason": "ambiguous_grammar",
            "confidence": float(accepted_candidates[0]["confidence"]),
        }
    else:
        winner = accepted_candidates[0]
        left = int(str(winner["left"]))
        right = int(str(winner["right"]))
        result = {
            "accepted": True,
            "reason": "high_confidence_multiplication",
            "confidence": float(winner["confidence"]),
            "expression": f"{left}*{right}",
            "answer": str(left * right),
            "grammar": winner["grammar"],
        }
    result.update(
        {
            "formula_fingerprint": fingerprint,
            "whole_ocr": whole_votes,
            "candidates": candidates,
            "solver_policy": "multiply_only_refresh_others_v1",
        }
    )
    return _json_safe(result)


def _handle_request(
    request: dict[str, Any],
    *,
    assets_dir: Path,
    engine: ddddocr.DdddOcr,
) -> dict[str, Any]:
    encoded = request.get("image_b64")
    if not isinstance(encoded, str) or not encoded:
        raise SolverError("image_b64 is required")
    try:
        payload = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise SolverError("image_b64 is invalid") from exc
    frame = _decode_png(payload)
    mode = request.get("mode")
    if mode == "ui":
        return inspect_ui(frame, assets_dir)
    if mode == "captcha":
        minimum = float(request.get("min_confidence", 0.72))
        if not 0.0 <= minimum <= 1.0:
            raise SolverError("min_confidence must be between 0 and 1")
        return solve_captcha(
            frame,
            assets_dir=assets_dir,
            engine=engine,
            min_confidence=minimum,
        )
    if mode == "fingerprint":
        formula = _formula_area(_captcha_crop(frame))
        return {"formula_fingerprint": _fingerprint(formula)}
    if mode == "profile":
        return inspect_profile_identity(frame)
    raise SolverError(f"unsupported mode: {mode!r}")


def serve(assets_dir: Path) -> int:
    engine = ddddocr.DdddOcr(show_ad=False)
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        request_id: Any = None
        try:
            request = json.loads(raw)
            if not isinstance(request, dict):
                raise SolverError("request must be a JSON object")
            request_id = request.get("id")
            result = _handle_request(request, assets_dir=assets_dir, engine=engine)
            response = {"id": request_id, "ok": True, "result": result}
        except Exception as exc:  # 服务边界：始终返回一行结构化错误
            response = {
                "id": request_id,
                "ok": False,
                "error": type(exc).__name__,
                "message": str(exc)[:300],
            }
        print(json.dumps(_json_safe(response), ensure_ascii=False), flush=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", action="store_true")
    parser.add_argument("--assets", required=True, type=Path)
    parser.add_argument("--self-check", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.self_check:
        engine = ddddocr.DdddOcr(show_ad=False)
        _load_operator_features(args.assets)
        print(
            json.dumps(
                {
                    "ok": True,
                    "engine": type(engine).__name__,
                    "policy": "multiply_only_refresh_others_v1",
                },
                ensure_ascii=False,
            )
        )
        return 0
    if args.server:
        return serve(args.assets)
    raise SystemExit("--server or --self-check is required")


if __name__ == "__main__":
    raise SystemExit(main())
