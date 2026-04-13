from __future__ import annotations

import re
from dataclasses import dataclass, field
from time import sleep
from typing import TYPE_CHECKING, Any, List

from src.constants.game.producer_gameplay import GameplayPosition
from src.constants.game.text.produce_text import ProduceText
from src.constants.yolo.labels.producer_Labels import ProducerLabels
from src.core.inference.ocr_engine import OCRService
from src.utils.logger import logger
from src.utils.string_tools import MatchConfig, normalize_ocr_jp, string_match

from .common import (
    first_matching_index,
    infer_param_kind,
    invoke_decision_strategy,
    ocr_text,
    resolve_candidate_index,
)
from .decision import (
    build_decision_state,
    detect_sp_badge,
    hydrate_schedule_candidates,
    resolve_schedule_action_identity,
)

if TYPE_CHECKING:
    from src.core.tasks.producer_challenge.context import ProduceContext
    from src.main import AppProcessor

_SCHEDULE_SCREEN_OCR = OCRService()
_PRESENT_SUPPORT_BONUS_RE = re.compile(r"\+\d+")
_CRITICAL_STAMINA_RATIO = 0.18
_LOW_STAMINA_RATIO = 0.32
_SCHEDULE_LOOKUP_NOISE_TOKENS = (
    ProduceText.PRESENT_SELECTION,
    ProduceText.PRESENT_SUPPORT,
    "審査基準",
    "パラメータ上昇",
)

# ── 授業課程選項 ──
_LESSON_PROBE_TAP_WAIT = 0.5      # 点击选项后等待 UI 动画
_LESSON_PROBE_INFER_WAIT = 0.3    # 等待 YOLO 再推理
_LESSON_STAMINA_COST_RE = re.compile(r"[-ー一](\d+)")  # 体力消耗匹配: "-4", "ー8"
_LESSON_INFO_OCR = OCRService()
# 授業效果描述中的属性关键词 → param_kind 映射
_LESSON_STAT_KEYWORDS: dict[str, str] = {
    "ボーカル": "vocal",
    "ダンス": "dance",
    "ビジュアル": "visual",
}


@dataclass
class ScheduleActionCandidate:
    index: int
    title: str
    kind: str
    recommended: bool
    selected: bool
    box: Any = field(repr=False, default=None)
    action_id: str = ""
    db_id: str = ""
    source: str = ""
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScheduleStepResult:
    status: str
    candidate: ScheduleActionCandidate


def _normalize_schedule_text(text: str | None) -> str:
    return normalize_ocr_jp(str(text or "")).strip()


def _is_unknown_schedule_action_id(action_id: str | None) -> bool:
    normalized = str(action_id or "").strip()
    return not normalized or ":" in normalized or "unknown" in normalized


# ────────────────────────────────────────────────────────────
# CLIP 周行動アイコン記憶
# ────────────────────────────────────────────────────────────

def _get_schedule_clip(app: "AppProcessor"):
    """获取周行动 CLIP 服务实例（若可用）。"""
    clip_manager = getattr(app, "clip_manager", None)
    if clip_manager is None:
        return None
    return getattr(clip_manager, "schedule_action_clip", None)


def _resolve_schedule_from_clip(
    app: "AppProcessor",
    box: Any,
) -> dict[str, Any] | None:
    """尝试使用 CLIP 记忆识别周行动图标。

    Returns:
        匹配成功时返回 dict(action_id, param_kind, rl_action_type)；
        未命中时返回 None。
    """
    schedule_clip = _get_schedule_clip(app)
    if schedule_clip is None or box is None or getattr(box, "frame", None) is None:
        return None
    try:
        matched = schedule_clip.retrieve(box.frame)
    except Exception as exc:  # noqa: BLE001
        logger.debug("schedule CLIP: 识别失败，回退 OCR: {}", exc)
        return None
    if matched is None:
        return None
    logger.debug(
        "schedule CLIP: 命中 action_id={} kind={}",
        matched.action_id,
        matched.param_kind,
    )
    return {
        "action_id": matched.action_id,
        "param_kind": matched.param_kind,
        "rl_action_type": matched.rl_action_type,
    }


def _learn_schedule_clip(
    app: "AppProcessor",
    image: Any,
    action_id: str,
    *,
    param_kind: str = "",
    rl_action_type: str = "",
) -> None:
    """将已识别的周行动图标写入 CLIP 记忆库。"""
    if image is None or getattr(image, "size", 0) <= 0:
        return
    if not action_id or _is_unknown_schedule_action_id(action_id):
        return
    schedule_clip = _get_schedule_clip(app)
    if schedule_clip is None:
        return
    try:
        from src.core.services.clip.schedule_action import ScheduleActionIdentity
        payload = ScheduleActionIdentity(
            action_id=action_id,
            param_kind=param_kind or "",
            rl_action_type=rl_action_type or "",
        )
        schedule_clip.add_to_memory(image, payload, similarity_threshold=0.96)
    except Exception as exc:  # noqa: BLE001
        logger.debug("schedule CLIP: 学习失败 {}: {}", action_id, exc)


# ────────────────────────────────────────────────────────────
# 行動情報パネル探査（PC_ACTION_INFO からエフェクト説明を読取）
# ────────────────────────────────────────────────────────────

_ACTION_INFO_OCR = OCRService()


def _probe_action_info_panel(
    app: "AppProcessor",
    candidate: "ScheduleActionCandidate",
) -> str:
    """点击周行动后，从 PC_ACTION_INFO 面板 OCR 读取效果描述文本。

    该函数在候选被选中后（SCHEDULE_SELECTED 位置）调用，
    此时 PC_ACTION_INFO 面板应已展示。不执行额外点击操作，
    只读取当前帧中的信息面板内容。

    Returns:
        效果描述文本，读取失败时返回空字符串。
    """
    results = getattr(app, "latest_results", None)
    if results is None:
        return ""
    info_boxes = results.filter_by_label(ProducerLabels.PC_ACTION_INFO)
    if not info_boxes:
        return ""
    info_box = info_boxes.first()
    frame = getattr(info_box, "frame", None)
    if frame is None or getattr(frame, "size", 0) <= 0:
        return ""

    # 信息面板全文 OCR
    try:
        ocr_results = _ACTION_INFO_OCR.ocr(frame)
        merged = ocr_results.auto_merge_lines(
            cy_range=max(4, int(frame.shape[0] * 0.015)),
            width_gap=max(10, int(frame.shape[1] * 0.02)),
        )
        lines = [
            normalize_ocr_jp(getattr(line, "text", "")).strip()
            for line in merged
            if len(normalize_ocr_jp(getattr(line, "text", "")).strip()) >= 2
        ]
        # 过滤掉标题行（通常是行动名称本身），保留效果描述
        effect_lines = [
            line for line in lines
            if not any(
                token in line
                for token in (
                    candidate.title or "",
                    ProduceText.EXAM_CRITERIA,
                    "パラメータ上昇",
                )
            )
        ]
        text = "；".join(effect_lines) if effect_lines else "；".join(lines)
    except Exception as exc:  # noqa: BLE001
        logger.debug("schedule info: 面板 OCR 失败: {}", exc)
        text = ""

    # 可视化调试标注
    debugger = getattr(app, "debug_tools", None)
    if debugger is not None and text:
        debugger.add_box(
            int(getattr(info_box, "x", 0)),
            int(getattr(info_box, "y", 0)),
            max(int(getattr(info_box, "w", 0) - getattr(info_box, "x", 0)), 1),
            max(int(getattr(info_box, "h", 0) - getattr(info_box, "y", 0)), 1),
            label=f"action_info: {text[:40]}",
            color=(50, 200, 255),
            alpha=0.15,
            duration=3.0,
            font_size=14,
        )

    if text:
        logger.debug(
            "schedule info: 候选[{}] '{}' 效果描述: {}",
            candidate.index,
            candidate.title,
            text[:80],
        )
    return text


# ────────────────────────────────────────────────────────────
# P手帳（Pノート）読取: OCR + 图标颜色分析で未来の日程を取得
# ────────────────────────────────────────────────────────────

import cv2
import numpy as np

_NOTEBOOK_OCR = OCRService()

# 特殊事件关键词（出现在宽幅横幅上，OCR 可读）
_NOTEBOOK_SPECIAL_KEYWORDS = (
    "試験", "オーディション", "追い込み", "レッスン",
    "フェス", "ライブ", "中間", "最終",
)

# ── 图标背景色 HSV 色相映射（基于实测中位值） ──
# OpenCV HSV: H=0-180
# 实测值: ボーカル H≈164, ダンス H≈98, ビジュアル H≈21,
#          お出かけ H≈76-89, 活動 H≈17, 授業 H≈111
_NOTEBOOK_ICON_HUE_MAP: list[tuple[int, int, str]] = [
    (10, 19,  "活動"),               # H≈17, 橙色
    (19, 40,  "ビジュアルレッスン"),  # H≈21, 黄色
    (40, 95,  "お出かけ"),           # H≈76-89, 绿〜青绿
    (95, 108, "ダンスレッスン"),      # H≈98, 青色
    (108, 130, "授業"),              # H≈111, 蓝紫
    (130, 180, "ボーカルレッスン"),   # H≈164, 品红/粉红
    (0, 10,   "ボーカルレッスン"),    # H≈0-9, 红色端（品红绕回）
]

# 图标检测参数
_ICON_SAT_THRESHOLD = 80    # 饱和度阈值（区分彩色 vs 白色背景）
_ICON_VAL_THRESHOLD = 100   # 亮度下限
_ICON_MIN_AREA = 2500       # 最小面积（约 50x50）
_ICON_MAX_WIDTH = 150       # 最大宽度（排除宽幅横幅/底栏等）
_ICON_MIN_WIDTH = 60        # 最小宽度（排除最終試験 banner 内的小色块）
_ICON_MIN_HEIGHT = 50       # 最小高度（排除细线/进度条）
_ICON_MAX_ASPECT = 2.0      # 最大高宽比（排除竖长条形误检，正常图标约 1:1）
_ICON_ROW_GAP = 100         # 行间 Y 距离阈值


def _classify_icon_hue(h: float) -> str:
    """根据 HSV 色相值分类图标对应的行动类型。"""
    for h_min, h_max, label in _NOTEBOOK_ICON_HUE_MAP:
        if h_min <= h < h_max:
            return label
    return "不明"


def _detect_notebook_icons(frame: "np.ndarray") -> list[dict[str, Any]]:
    """检测 P手帳 画面中的彩色行动图标。

    通过高饱和度掩码定位图标区域，裁剪每个图标的图像，
    并用 HSV 色相做初步分类（后续可被 CLIP 识别覆盖）。

    Returns:
        图标信息列表，每个 dict 包含:
        - abs_x, abs_y, w, h: 在原始 frame 中的绝对坐标
        - hue: 中位色相值
        - action_type: 色相分类结果（可被 CLIP 覆盖）
        - icon_image: 裁剪出的图标 BGR 图像
    """
    height, width = frame.shape[:2]
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # 面板区域（排除顶部 HUD 和底部关闭按钮）
    panel_x1, panel_y1 = int(width * 0.04), int(height * 0.16)
    panel_x2, panel_y2 = int(width * 0.72), int(height * 0.90)
    panel_hsv = hsv[panel_y1:panel_y2, panel_x1:panel_x2]

    # 高饱和度掩码：分离彩色图标 vs 白色背景
    sat_mask = (
        (panel_hsv[:, :, 1] > _ICON_SAT_THRESHOLD)
        & (panel_hsv[:, :, 2] > _ICON_VAL_THRESHOLD)
    ).astype(np.uint8) * 255
    kernel = np.ones((5, 5), np.uint8)
    sat_mask = cv2.morphologyEx(sat_mask, cv2.MORPH_OPEN, kernel)
    sat_mask = cv2.morphologyEx(sat_mask, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(sat_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    icons: list[dict[str, Any]] = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < _ICON_MIN_AREA:
            continue
        x, y, bw, bh = cv2.boundingRect(cnt)
        # 过滤非图标形状（排除 banner 内小色块、宽幅横幅、竖长条等）
        if bw > _ICON_MAX_WIDTH or bw < _ICON_MIN_WIDTH or bh < _ICON_MIN_HEIGHT:
            continue
        if bh / bw > _ICON_MAX_ASPECT:
            continue

        # 取区域内饱和像素的中位色相
        roi_mask = sat_mask[y:y + bh, x:x + bw]
        roi_hue = panel_hsv[y:y + bh, x:x + bw, 0]
        sat_pixels = roi_mask > 0
        if np.count_nonzero(sat_pixels) < 50:
            continue
        median_h = float(np.median(roi_hue[sat_pixels]))

        # 裁剪图标图像（从原始 frame 的绝对坐标）
        ax, ay = x + panel_x1, y + panel_y1
        icon_image = frame[ay:ay + bh, ax:ax + bw].copy()

        action_type = _classify_icon_hue(median_h)
        icons.append({
            "abs_x": ax,
            "abs_y": ay,
            "w": bw, "h": bh,
            "hue": median_h,
            "action_type": action_type,
            "icon_image": icon_image,
        })

    icons.sort(key=lambda i: (i["abs_y"], i["abs_x"]))
    return icons


# ── P手帳 图标 CLIP 识别 + 色相回退 ──
# 未识别的图标按色相缓存（每个色相类型仅缓存一张），
# 当后续 CLIP 学习到新类型时可重新识别。
_notebook_icon_clip_cache: dict[str, "np.ndarray"] = {}


def _identify_notebook_icons_with_clip(
    app: "AppProcessor",
    icons: list[dict[str, Any]],
) -> None:
    """尝试用 CLIP 识别每个图标，未命中则保留色相分类并缓存图像。

    就地修改 icons 列表中每个 dict 的 action_type 和 source 字段。
    """
    schedule_clip = _get_schedule_clip(app)

    for ic in icons:
        icon_img = ic.get("icon_image")
        if icon_img is None or icon_img.size == 0:
            ic["source"] = "hue"
            continue

        # 优先尝试 CLIP 检索
        if schedule_clip is not None:
            try:
                matched = schedule_clip.retrieve(icon_img, similarity_threshold=0.90)
                if matched is not None:
                    ic["action_type"] = matched.action_id
                    ic["source"] = "clip"
                    ic.setdefault("metadata", {})["clip_action_id"] = matched.action_id
                    ic.setdefault("metadata", {})["param_kind"] = matched.param_kind
                    ic.setdefault("metadata", {})["rl_action_type"] = matched.rl_action_type
                    logger.debug(
                        "P手帳 CLIP: 命中 {} (H={:.0f})",
                        matched.action_id, ic["hue"],
                    )
                    continue
            except Exception:  # noqa: BLE001
                pass

        # CLIP 未命中 → 使用色相分类（已在 _detect_notebook_icons 中设置）
        ic["source"] = "hue"
        hue_label = ic["action_type"]

        # 每个色相类型缓存一张图标，供后续 CLIP 学习后重新识别
        if hue_label not in _notebook_icon_clip_cache:
            _notebook_icon_clip_cache[hue_label] = icon_img.copy()
            logger.debug(
                "P手帳: 缓存未识别图标 '{}' (H={:.0f}) 供后续 CLIP 学习",
                hue_label, ic["hue"],
            )


def _retry_cached_notebook_icons(app: "AppProcessor") -> dict[str, str]:
    """对缓存中的未识别图标重新尝试 CLIP 识别。

    当 schedule 主流程学习了新的 CLIP 类型后调用。

    Returns:
        成功重新识别的映射: {原色相标签: CLIP action_id}
    """
    schedule_clip = _get_schedule_clip(app)
    if schedule_clip is None or not _notebook_icon_clip_cache:
        return {}

    resolved: dict[str, str] = {}
    to_remove: list[str] = []

    for hue_label, icon_img in _notebook_icon_clip_cache.items():
        try:
            matched = schedule_clip.retrieve(icon_img, similarity_threshold=0.90)
            if matched is not None:
                resolved[hue_label] = matched.action_id
                to_remove.append(hue_label)
                logger.debug(
                    "P手帳 CLIP重试: '{}' → '{}'",
                    hue_label, matched.action_id,
                )
        except Exception:  # noqa: BLE001
            pass

    for key in to_remove:
        del _notebook_icon_clip_cache[key]

    return resolved


def _group_icons_into_rows(
    icons: list[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    """将图标按 Y 坐标分组为行（每行对应一个周）。"""
    if not icons:
        return []
    rows: list[list[dict[str, Any]]] = []
    current_row: list[dict[str, Any]] = [icons[0]]
    for ic in icons[1:]:
        if ic["abs_y"] - current_row[-1]["abs_y"] > _ICON_ROW_GAP:
            rows.append(current_row)
            current_row = [ic]
        else:
            current_row.append(ic)
    rows.append(current_row)
    return rows


def _detect_p_notebook_button(app: "AppProcessor"):
    """检测 P手帳 按钮（YOLO 标签 PC_P_MANUAL）。"""
    results = getattr(app, "latest_results", None)
    if results is None:
        return None
    manual_boxes = results.filter_by_label(ProducerLabels.PC_P_MANUAL)
    if not manual_boxes:
        return None
    btn = manual_boxes.first()
    logger.debug(
        "P手帳: 检测到按钮 cx={}, cy={}",
        getattr(btn, "cx", 0),
        getattr(btn, "cy", 0),
    )
    return btn


def _open_p_notebook(app: "AppProcessor") -> bool:
    """点击 P手帳 按钮打开日程一览。"""
    btn = _detect_p_notebook_button(app)
    if btn is None:
        logger.debug("P手帳: 未检测到按钮，跳过")
        return False
    app.device.click_element(btn)
    logger.debug("P手帳: 已点击打开按钮")
    sleep(1.2)
    # 等待弹出动画结束，画面稳定后再操作
    app.game_utils.wait_frame_stable(stable_count=2, timeout=3.0)
    return True


def _close_p_notebook(app: "AppProcessor") -> None:
    """关闭 P手帳 面板。

    P手帳 底部有一个 × 圆形关闭按钮，位于画面底部中央 (约 x=50%, y=94.4%)。
    实测按钮中心 = (540, 2208)，半径约 60px。
    """
    from src.core.tasks.producer_challenge.gameplay.common import click_relative_point
    sleep(0.3)
    click_relative_point(app, x_ratio=0.50, y_ratio=0.944, label="p-notebook-close-x")
    logger.debug("P手帳: 点击 × 关闭按钮")
    sleep(0.8)


def _read_notebook_schedule_page(app: "AppProcessor") -> list[dict[str, Any]]:
    """读取 P手帳 当前可见页面，结合 OCR + 颜色检测。

    策略:
    1. OCR 左侧区域读取周数标签（N週）
    2. OCR 中央区域读取特殊事件文字（最終試験、追い込みレッスン 等）
    3. 颜色检测找到图标并分类行动类型
    4. 按 Y 坐标匹配周数标签和图标行

    Returns:
        每周一个 dict 的列表: {week, raw_text, actions, special_event, ...}
    """
    frame = getattr(app, "latest_frame", None)
    if frame is None or getattr(frame, "size", 0) <= 0:
        return []

    height, width = frame.shape[:2]

    # ── 步骤1: OCR 左侧区域，提取周数标签 ──
    ocr_left = int(width * 0.04)
    ocr_right = int(width * 0.25)
    ocr_top = int(height * 0.18)
    ocr_bottom = int(height * 0.90)
    left_crop = frame[ocr_top:ocr_bottom, ocr_left:ocr_right]

    week_labels: list[dict[str, Any]] = []  # {week: int, cy: int}
    try:
        ocr_left_results = _NOTEBOOK_OCR.ocr(left_crop)
        merged_left = ocr_left_results.auto_merge_lines(
            cy_range=max(4, int(left_crop.shape[0] * 0.015)),
            width_gap=max(10, int(left_crop.shape[1] * 0.05)),
        )
        for line in merged_left:
            text = normalize_ocr_jp(getattr(line, "text", "")).strip()
            # "N週" 形式 or 纯数字（P手帳左列只有周数）
            m = re.search(r"(\d+)\s*[週周]", text)
            if not m:
                # OCR 可能只读到数字（"16"、"15" 等），无"週"字
                cleaned = re.sub(r"[^\d]", "", text)
                if cleaned and 1 <= int(cleaned) <= 20:
                    m_num = int(cleaned)
                else:
                    m_num = None
            else:
                m_num = None
            week_num = int(m.group(1)) if m else m_num
            if week_num is not None:
                cy_abs = int(getattr(line, "cy", 0)) + ocr_top
                week_labels.append({"week": week_num, "cy": cy_abs})
    except Exception:  # noqa: BLE001
        pass

    # 调试: 显示 OCR 读到的原始周数标签
    if week_labels:
        _week_nums = [w["week"] for w in week_labels]
        logger.debug("P手帳 OCR: 读取到周数标签 {} (共{}个)", _week_nums, len(_week_nums))
    else:
        logger.debug("P手帳 OCR: 未读取到任何周数标签")

    # ── 步骤2: OCR 中央区域，提取特殊事件文字 ──
    # 使用较宽区域（0.12-0.78）以提高渐变色 banner（最終試験等）的 OCR 准确率
    center_left = int(width * 0.12)
    center_right = int(width * 0.78)
    center_crop = frame[ocr_top:ocr_bottom, center_left:center_right]

    special_events: list[dict[str, Any]] = []  # {text: str, cy: int}
    try:
        ocr_center_results = _NOTEBOOK_OCR.ocr(center_crop)
        merged_center = ocr_center_results.auto_merge_lines(
            cy_range=max(4, int(center_crop.shape[0] * 0.015)),
            width_gap=max(10, int(center_crop.shape[1] * 0.05)),
        )
        for line in merged_center:
            text = normalize_ocr_jp(getattr(line, "text", "")).strip()
            if len(text) < 2:
                continue
            # 只保留包含特殊事件关键词的行
            if any(kw in text for kw in _NOTEBOOK_SPECIAL_KEYWORDS):
                cy_abs = int(getattr(line, "cy", 0)) + ocr_top
                special_events.append({"text": text, "cy": cy_abs})
    except Exception:  # noqa: BLE001
        pass

    # ── 步骤3: 颜色检测图标 + CLIP 识别 ──
    icons = _detect_notebook_icons(frame)
    # 尝试用 CLIP 识别每个图标（有 CLIP 服务时），未命中保留色相分类
    _identify_notebook_icons_with_clip(app, icons)
    icon_rows = _group_icons_into_rows(icons)

    logger.debug(
        "P手帳: 检测到 {} 个图标, 分为 {} 行 (周标签 {} 个, 特殊事件 {} 个)",
        len(icons), len(icon_rows), len(week_labels), len(special_events),
    )

    # ── 步骤4: 匹配周数标签 → 图标行 / 特殊事件 ──
    # 将周数标签按 cy 排序
    week_labels.sort(key=lambda w: w["cy"])

    entries: list[dict[str, Any]] = []
    used_icon_rows: set[int] = set()
    used_special: set[int] = set()

    # 第一遍: 先匹配特殊事件，标记哪些周是事件周（不消耗图标行）
    special_weeks: dict[int, str] = {}  # wl_index → special_text
    for wi, wl in enumerate(week_labels):
        wl_cy = wl["cy"]
        for si, se in enumerate(special_events):
            if si in used_special:
                continue
            if abs(se["cy"] - wl_cy) < 200:
                special_weeks[wi] = se["text"]
                used_special.add(si)
                break

    # 第二遍: 非事件周匹配图标行（事件周不消耗图标行，避免抢占）
    for wi, wl in enumerate(week_labels):
        week_num = wl["week"]
        wl_cy = wl["cy"]

        if wi in special_weeks:
            # 特殊事件周: 无可选行动
            special_text = special_weeks[wi]
            entries.append({
                "week": week_num,
                "raw_text": f"{week_num}週: {special_text}",
                "actions": [],
                "special_event": special_text,
                "completed": False,
                "is_action": True,
                "is_week_label": True,
            })
            continue

        # 匹配最近的未使用图标行
        actions: list[str] = []
        best_row_idx = -1
        best_row_dist = 999999
        for ri, row in enumerate(icon_rows):
            if ri in used_icon_rows:
                continue
            row_cy = int(np.mean([ic["abs_y"] for ic in row]))
            dist = abs(row_cy - wl_cy)
            if dist < best_row_dist and dist < 200:
                best_row_dist = dist
                best_row_idx = ri
        if best_row_idx >= 0:
            used_icon_rows.add(best_row_idx)
            for ic in icon_rows[best_row_idx]:
                actions.append(ic["action_type"])

        # 构建 raw_text
        if actions:
            raw_text = f"{week_num}週: {' / '.join(actions)}"
        else:
            raw_text = f"{week_num}週"

        entries.append({
            "week": week_num,
            "raw_text": raw_text,
            "actions": actions,
            "special_event": None,
            "completed": False,
            "is_action": True,
            "is_week_label": True,
        })

    # 添加未匹配到周标签的特殊事件（可能在列表最顶部没有周标签）
    for si, se in enumerate(special_events):
        if si not in used_special:
            entries.append({
                "week": 0,
                "raw_text": se["text"],
                "actions": [],
                "special_event": se["text"],
                "completed": False,
                "is_action": True,
                "is_week_label": False,
            })

    # ── 步骤5: 为未匹配的图标行推断周数 ──
    # OCR 可能漏读部分周数标签，导致有图标行无对应周标签。
    # 利用已匹配条目的 (week, cy) 关系，按 Y 坐标线性插值推断周数。
    orphan_rows = [
        ri for ri in range(len(icon_rows)) if ri not in used_icon_rows
    ]
    if orphan_rows and len(entries) >= 2:
        # 收集已匹配的 (cy, week) 锚点
        anchors: list[tuple[int, int]] = []  # (cy, week)
        for e in entries:
            if e.get("is_week_label") and e.get("week", 0) > 0:
                # 找到该 entry 对应图标行的 cy（如果有）
                # 优先用该 entry 被匹配到的周标签 cy
                for wl in week_labels:
                    if wl["week"] == e["week"]:
                        anchors.append((wl["cy"], e["week"]))
                        break

        if len(anchors) >= 2:
            # 按 cy 排序（从上到下），周数应该是递减的（上方=大周数）
            anchors.sort(key=lambda a: a[0])

            for ri in orphan_rows:
                row = icon_rows[ri]
                row_cy = int(np.mean([ic["abs_y"] for ic in row]))

                # 找到 row_cy 在 anchors 中的插值位置
                inferred_week = None
                if row_cy <= anchors[0][0]:
                    # 在所有锚点之上，外推
                    if len(anchors) >= 2:
                        cy_diff = anchors[1][0] - anchors[0][0]
                        w_diff = anchors[0][1] - anchors[1][1]
                        if cy_diff > 0 and w_diff != 0:
                            steps = (anchors[0][0] - row_cy) / cy_diff
                            inferred_week = anchors[0][1] + round(steps * w_diff)
                elif row_cy >= anchors[-1][0]:
                    # 在所有锚点之下，外推
                    if len(anchors) >= 2:
                        cy_diff = anchors[-1][0] - anchors[-2][0]
                        w_diff = anchors[-2][1] - anchors[-1][1]
                        if cy_diff > 0 and w_diff != 0:
                            steps = (row_cy - anchors[-1][0]) / cy_diff
                            inferred_week = anchors[-1][1] - round(steps * w_diff)
                else:
                    # 在两个锚点之间，线性插值
                    for ai in range(len(anchors) - 1):
                        a_above, a_below = anchors[ai], anchors[ai + 1]
                        if a_above[0] <= row_cy <= a_below[0]:
                            span_cy = a_below[0] - a_above[0]
                            span_w = a_above[1] - a_below[1]
                            if span_cy > 0 and span_w > 0:
                                ratio = (row_cy - a_above[0]) / span_cy
                                inferred_week = a_above[1] - round(ratio * span_w)
                            break

                if inferred_week is not None and 1 <= inferred_week <= 20:
                    # 检查该周数是否已存在
                    existing_weeks = {e.get("week", 0) for e in entries}
                    if inferred_week not in existing_weeks:
                        actions = [ic["action_type"] for ic in row]
                        raw_text = f"{inferred_week}週: {' / '.join(actions)}"
                        entries.append({
                            "week": inferred_week,
                            "raw_text": raw_text,
                            "actions": actions,
                            "special_event": None,
                            "completed": False,
                            "is_action": True,
                            "is_week_label": True,
                        })
                        logger.debug(
                            "P手帳: 推断未匹配图标行 → {}週 (cy={}, actions={})",
                            inferred_week, row_cy, actions,
                        )

    if orphan_rows:
        logger.debug(
            "P手帳: {} 个图标行未匹配到周标签 (已推断恢复)",
            len(orphan_rows),
        )

    # 按周数降序排列（近到远）
    entries.sort(key=lambda e: e.get("week", 0), reverse=True)

    # 调试可视化
    debugger = getattr(app, "debug_tools", None)
    if debugger is not None and icons:
        for ic in icons:
            debugger.add_rect(
                ic["abs_x"], ic["abs_y"],
                ic["abs_x"] + ic["w"], ic["abs_y"] + ic["h"],
                color=(0, 255, 0),
                label=ic["action_type"][:6],
                duration=3.0,
            )

    return entries


def _notebook_scroll_and_check(
    app: "AppProcessor",
    start_y_ratio: float,
    end_y_ratio: float,
) -> bool:
    """P手帳 内执行一次滑动并检测是否发生了实际滚动。

    滑动后用 wait_frame_stable 检测画面是否快速静止：
    - 如果在短时间内就稳定 → 没有发生实际滚动 → 到达边界
    - 如果超时未稳定 → 滚动动画正在进行 → 还能继续滚

    推理帧率约1fps，stable_count=2 需要约2帧（~2秒），
    短超时3秒内能采到2-3帧，刚好能判断。

    Returns:
        True 表示发生了实际滚动；False 表示已到边界（内容没变）。
    """
    from src.core.tasks.producer_challenge.gameplay.common import get_frame_size

    width, height = get_frame_size(app)
    center_x = width // 2

    # 执行滑动
    app.device.swipe(
        center_x, int(height * start_y_ratio),
        center_x, int(height * end_y_ratio),
        duration=0.4,
    )
    # 如果到边界了，画面不会变化，wait_frame_stable 很快返回 True
    # 如果还在滚，滚动动画期间帧间差异大，3秒内不会稳定，返回 False
    is_stable = app.game_utils.wait_frame_stable(
        threshold=0.985, stable_count=2, timeout=3.0,
    )
    if is_stable:
        # 画面快速稳定 → 内容没变 → 到达边界
        return False
    # 超时未稳定 → 正在滚动，等动画结束
    app.game_utils.wait_frame_stable(threshold=0.985, stable_count=2, timeout=3.0)
    return True


def _scroll_notebook_up(app: "AppProcessor") -> bool:
    """P手帳 内向下拖动，内容向上卷，显示更高周数（未来）。

    Returns:
        True 表示发生了实际滚动；False 表示已到顶（无法再滚）。
    """
    return _notebook_scroll_and_check(app, 0.35, 0.65)


def _scroll_notebook_down(app: "AppProcessor") -> bool:
    """P手帳 内向上拖动，内容向下卷，显示更低周数（过去）。

    Returns:
        True 表示发生了实际滚动；False 表示已到底（无法再滚）。
    """
    return _notebook_scroll_and_check(app, 0.65, 0.35)


def _scroll_notebook_to_bottom(app: "AppProcessor") -> None:
    """快速滑动到 P手帳 底部（最早的周）。"""
    for i in range(10):
        scrolled = _scroll_notebook_down(app)
        if not scrolled:
            logger.debug("P手帳: 已到达底部 (第{}次滑动)", i + 1)
            break


def read_p_notebook(
    app: "AppProcessor",
    ctx: "ProduceContext",
    *,
    max_scroll_pages: int = 5,
) -> list[dict[str, Any]]:
    """完整流程: 打开 P手帳 → 滑到底部 → 逐页向上读取 → 关闭。

    图标识别优先级: CLIP 记忆 > HSV 色相分类（回退）。
    CLIP 未命中的图标会缓存到内存，后续 CLIP 学习新类型后可重新识别。
    结果按周数降序排列（最近的周在前）。

    Args:
        max_scroll_pages: 最大滚动页数（0 = 仅读取当前可见页）。

    Returns:
        每周一个 dict，包含 week/raw_text/actions/special_event 等字段。
    """
    cache_key = f"p_notebook_week_{ctx.current_week}"
    cached = ctx.handler_state.get(cache_key)
    if cached is not None:
        logger.debug("P手帳: 第{}周已缓存，跳过读取", ctx.current_week)
        return cached

    if not _open_p_notebook(app):
        ctx.handler_state[cache_key] = []
        return []

    # 按周号去重合并多页结果
    all_entries: dict[int, dict[str, Any]] = {}

    try:
        # 先滑到底部（最早的周）
        _scroll_notebook_to_bottom(app)

        # 读取底部第一页
        page_entries = _read_notebook_schedule_page(app)
        for e in page_entries:
            key = e.get("week", 0)
            if key not in all_entries:
                all_entries[key] = e
        logger.debug("P手帳: 底部首页读取 {} 周", len(page_entries))

        # 向上滚动逐页读取后续日程
        for page_idx in range(max_scroll_pages):
            scrolled = _scroll_notebook_up(app)
            if not scrolled:
                logger.debug("P手帳: 已到顶，停止滚动")
                break
            new_entries = _read_notebook_schedule_page(app)
            added = 0
            for e in new_entries:
                key = e.get("week", 0)
                if key not in all_entries:
                    all_entries[key] = e
                    added += 1
            logger.debug("P手帳: 向上滚动第{}页，新增 {} 周", page_idx + 1, added)
    finally:
        # 无论读取成功与否，必须关闭 P手帳，否则会卡在此画面
        _close_p_notebook(app)

    # 按周数降序排列
    entries = sorted(all_entries.values(), key=lambda e: e.get("week", 0), reverse=True)
    logger.debug("P手帳: 最终 {} 个日程条目", len(entries))

    # 可视化调试摘要
    debugger = getattr(app, "debug_tools", None)
    if debugger is not None and entries:
        from src.core.tasks.producer_challenge.gameplay.common import get_frame_size
        w_frame, _h = get_frame_size(app)
        parts = [e["raw_text"][:16] for e in entries[:5]]
        debugger.add_text(
            int(w_frame * 0.02), 20,
            f"P手帳: {' | '.join(parts)}",
            color=(100, 255, 200), font_size=12, duration=5.0,
        )

    # 缓存
    ctx.handler_state[cache_key] = entries
    ctx.handler_state["p_notebook_schedule"] = entries
    ctx.handler_state["p_notebook_week"] = ctx.current_week

    ctx.record_operation(
        "read_p_notebook",
        target=f"week_{ctx.current_week}",
        details={
            "entry_count": len(entries),
            "scroll_pages": max_scroll_pages,
        },
    )
    return entries


def _schedule_title_resolution_score(text: str | None, *, index: int) -> float:
    normalized = _normalize_schedule_text(text)
    if not normalized:
        return -100.0

    inferred_kind = infer_param_kind(normalized)
    resolution = resolve_schedule_action_identity(normalized, inferred_kind, index=index)
    action_id = str(getattr(resolution, "action_id", "") or "")
    metadata = dict(getattr(resolution, "metadata", {}) or {})

    score = min(len(normalized), 18) * 0.15
    if inferred_kind != "unknown":
        score += 6.0
    if not _is_unknown_schedule_action_id(action_id):
        score += 16.0
    if metadata.get("supported") is True:
        score += 2.0
    if metadata.get("rl_action_type"):
        score += 2.0
    if any(
        token and token in normalized
        for token in (
            ProduceText.OUTING,
            ProduceText.GO_OUT,
            ProduceText.CLASS,
            ProduceText.REST,
            ProduceText.BUSINESS,
            ProduceText.ACTIVITY,
            ProduceText.CONSULT,
            ProduceText.AUDITION,
            ProduceText.LESSON,
            ProduceText.SELF_LESSON,
            ProduceText.HARD_LESSON,
        )
    ):
        score += 4.0
    return score


def _choose_schedule_candidate_title(
    direct_title: str,
    lookup_texts: list[str],
    *,
    index: int,
) -> tuple[str, str]:
    normalized_direct = _normalize_schedule_text(direct_title)
    normalized_lookup = [
        text
        for text in (_normalize_schedule_text(value) for value in lookup_texts)
        if text
    ]
    if not normalized_direct and not normalized_lookup:
        return "", "direct"
    if not normalized_lookup:
        return normalized_direct, "direct"

    direct_score = _schedule_title_resolution_score(normalized_direct, index=index)
    best_lookup = max(
        normalized_lookup,
        key=lambda text: _schedule_title_resolution_score(text, index=index),
    )
    best_lookup_score = _schedule_title_resolution_score(best_lookup, index=index)

    if not normalized_direct:
        return best_lookup, "lookup"
    if best_lookup_score >= direct_score + 1.5:
        return best_lookup, "lookup"
    return normalized_direct, "direct"


def _collect_schedule_lookup_texts(app: "AppProcessor", action_boxes: list) -> list[list[str]]:
    frame = getattr(app, "latest_frame", None)
    if frame is None or getattr(frame, "size", 0) <= 0 or not action_boxes:
        return [[] for _ in action_boxes]

    height, _width = frame.shape[:2]
    merged_lines = _SCHEDULE_SCREEN_OCR.ocr(frame).auto_merge_lines(
        cy_range=max(6, int(height * 0.003)),
        width_gap=max(20, int(frame.shape[1] * 0.02)),
    )
    content_lines: list[tuple[object, str]] = []
    for line in merged_lines:
        text = _normalize_schedule_text(getattr(line, "text", ""))
        if not text or len(text) < 2:
            continue
        if not (height * 0.18 <= line.cy <= height * 0.82):
            continue
        if any(token in text for token in _SCHEDULE_LOOKUP_NOISE_TOKENS):
            continue
        content_lines.append((line, text))

    if not content_lines:
        return [[] for _ in action_boxes]

    lookup_texts: list[list[str]] = []
    for idx, box in enumerate(action_boxes):
        box_width = max(1, int(getattr(box, "w", 0) - getattr(box, "x", 0)))
        box_height = max(1, int(getattr(box, "h", 0) - getattr(box, "y", 0)))
        top_boundary = max(0, int(getattr(box, "y", 0) - box_height * 0.35))
        bottom_boundary = min(height, int(getattr(box, "h", 0) + box_height * 0.45))
        if idx > 0:
            top_boundary = max(top_boundary, int((action_boxes[idx - 1].cy + box.cy) / 2))
        if idx < len(action_boxes) - 1:
            bottom_boundary = min(bottom_boundary, int((box.cy + action_boxes[idx + 1].cy) / 2))

        candidate_rows: list[tuple[float, str]] = []
        for line, text in content_lines:
            if not (top_boundary <= line.cy <= bottom_boundary):
                continue
            if not (
                int(getattr(box, "x", 0) - box_width * 0.25)
                <= line.cx
                <= int(getattr(box, "w", 0) + box_width * 0.25)
            ):
                continue
            vertical_gap = abs(float(line.cy) - float(box.cy))
            horizontal_gap = abs(float(line.cx) - float(box.cx))
            score = (
                vertical_gap * 2.0
                + horizontal_gap * 0.35
                - _schedule_title_resolution_score(text, index=idx)
            )
            candidate_rows.append((score, text))

        candidate_rows.sort(key=lambda item: item[0])
        deduped: list[str] = []
        for _score, text in candidate_rows:
            if text not in deduped:
                deduped.append(text)
        lookup_texts.append(deduped)

    return lookup_texts


def _schedule_payload_family(payload: dict[str, Any]) -> str:
    metadata = dict(payload.get("metadata", {}) or {})
    family = str(metadata.get("schedule_family") or "").strip()
    if family:
        return family
    action_id = str(payload.get("id") or payload.get("action_id") or "")
    title = str(payload.get("label") or payload.get("title") or "")
    if "refresh" in action_id or "休" in title:
        return "refresh"
    if "outing" in action_id or "おでかけ" in title or "外出" in title:
        return "outing"
    return ""


def _select_low_stamina_recovery_action(
    decision_state: dict[str, Any],
) -> tuple[int, str] | None:
    economy = dict(decision_state.get("economy", {}) or {})
    stamina = int(economy.get("stamina") or 0)
    max_stamina = int(economy.get("max_stamina") or 0)
    p_point = int(economy.get("p_point") or 0)
    if max_stamina <= 0:
        return None

    stamina_ratio = float(stamina) / max(max_stamina, 1)
    critical = stamina <= 2 or stamina_ratio <= _CRITICAL_STAMINA_RATIO
    low = stamina <= 4 or stamina_ratio <= _LOW_STAMINA_RATIO
    if not (critical or low):
        return None

    legal_actions = {
        int(index)
        for index in decision_state.get("legal_actions", [])
    }
    refresh_payloads: list[dict[str, Any]] = []
    outing_payloads: list[dict[str, Any]] = []
    for payload in decision_state.get("candidates", []):
        index = int(payload.get("index", -1))
        if index not in legal_actions:
            continue
        family = _schedule_payload_family(payload)
        if family == "refresh":
            refresh_payloads.append(payload)
        elif family == "outing":
            outing_payloads.append(payload)

    if critical:
        if refresh_payloads:
            return (
                int(refresh_payloads[0]["index"]),
                "当前体力过低，按手册应优先休む回体，避免下一周直接暴毙。",
            )
        if outing_payloads and p_point > 0:
            return (
                int(outing_payloads[0]["index"]),
                "当前体力过低，且 Pポイント 足够，优先おでかけ回体更稳。",
            )
    if low:
        if outing_payloads and p_point > 0:
            return (
                int(outing_payloads[0]["index"]),
                "当前体力偏低，且有 Pポイント，可优先おでかけ回体并顺带争取额外收益。",
            )
        if refresh_payloads:
            return (
                int(refresh_payloads[0]["index"]),
                "当前体力偏低，先休む补体力比继续高消耗行动更稳。",
            )
    return None


def _annotate_low_stamina_recovery_preference(
    decision_state: dict[str, Any],
    *,
    preferred_index: int,
    reason: str,
) -> None:
    payloads = list(decision_state.get("candidates", []) or [])
    label = f"候选 {preferred_index}"
    for payload in payloads:
        if int(payload.get("index", -1)) == preferred_index:
            payload["recommended"] = True
            label = str(payload.get("label") or payload.get("title") or label)
            break

    for payload in decision_state.get("llm_actions", []) or []:
        if int(payload.get("index", -1)) == preferred_index:
            payload["recommended"] = True

    stage_context = dict(decision_state.get("stage_context", {}) or {})
    stage_context["system_recommendation"] = f"系统当前推荐优先考虑：{label}。{reason}"
    decision_state["stage_context"] = stage_context
    llm_snapshot = decision_state.get("llm_snapshot")
    if isinstance(llm_snapshot, dict):
        llm_snapshot["stage_context"] = stage_context


def _collect_schedule_action_boxes(app: "AppProcessor") -> list:
    """收集时间表动作候选框。

    优先使用 PC_ACTION 标签，若无则回退到 Universal Options。
    有些时间表画面（例如特殊事件周）使用 Options 而非 Action 标签。
    """
    actions = list(app.latest_results.filter_by_label(ProducerLabels.PC_ACTION))
    if not actions:
        actions = list(app.latest_results.filter_by_label(ProducerLabels.UNIVERSAL_OPTIONS))
    # 按垂直位置排序（选项通常纵向排列，cx 几乎相同）
    return sorted(actions, key=lambda item: item.cy)


def _detect_recommended_kind(app: "AppProcessor") -> str:
    recommend_boxes = app.latest_results.filter_by_label(ProducerLabels.PC_RECOMMEND_ACTION)
    if not recommend_boxes:
        return "unknown"
    return infer_param_kind(ocr_text(recommend_boxes.first().frame))


def _looks_like_present_support_line(text: str) -> bool:
    normalized = normalize_ocr_jp(str(text or ""))
    return bool(
        string_match(
            normalized,
            ProduceText.PRESENT_SUPPORT,
            MatchConfig(fuzz_threshold=60, normalize=True),
        )
    ) or ProduceText.PRESENT_SELECTION in normalized or "選択時" in normalized


def _collect_present_support_candidates(
    app: "AppProcessor",
    ctx: "ProduceContext",
) -> List[ScheduleActionCandidate]:
    frame = getattr(app, "latest_frame", None)
    if frame is None or getattr(frame, "size", 0) <= 0:
        return []

    height = frame.shape[0]
    ocr_results = list(_SCHEDULE_SCREEN_OCR.ocr(frame))
    if not ocr_results:
        return []

    content_lines = [
        item
        for item in ocr_results
        if height * 0.28 <= item.cy <= height * 0.78
    ]
    header_lines = [item for item in content_lines if _looks_like_present_support_line(item.text)]
    bonus_lines = [
        item
        for item in content_lines
        if _PRESENT_SUPPORT_BONUS_RE.search(normalize_ocr_jp(item.text))
    ]
    bonus_lines.sort(key=lambda item: item.cy)

    candidates: list[ScheduleActionCandidate] = []
    for idx, bonus_line in enumerate(bonus_lines):
        prefix = None
        for line in reversed(header_lines):
            if line.cy <= bonus_line.cy and abs(bonus_line.cy - line.cy) <= height * 0.08:
                prefix = line
                break

        title_parts = []
        if prefix is not None:
            title_parts.append(normalize_ocr_jp(prefix.text))
        title_parts.append(normalize_ocr_jp(bonus_line.text))
        title = "".join(part for part in title_parts if part).strip()
        if not title:
            title = normalize_ocr_jp(bonus_line.text).strip()

        candidates.append(
            ScheduleActionCandidate(
                index=idx,
                title=title,
                kind=infer_param_kind(title),
                recommended=False,
                selected=False,
                box=bonus_line,
                action_id=f"schedule_present_support_option_{idx}",
                source="ocr_present_support",
                confidence=1.0,
                metadata={
                    "candidate_type": "present_support",
                    "effect_text": title,
                },
            )
        )

    if candidates:
        logger.debug(
            "schedule present support: 检测到 {} 个候选项: {}",
            len(candidates),
            [candidate.title for candidate in candidates],
        )
    return candidates


# ────────────────────────────────────────────────────────────
# 授業課程選項 — 采集 / 探査 / 決策
# ────────────────────────────────────────────────────────────

from src.utils.debug_tools import DebugTools
_lesson_debugger = DebugTools()


def _detect_lesson_stat_from_info(text: str) -> str:
    """从授業信息面板 OCR 文本中提取属性类型（vocal/dance/visual）。

    效果描述例: "ボーカル上昇+55 スキルカード選択して獲得"
    """
    for keyword, param_kind in _LESSON_STAT_KEYWORDS.items():
        if keyword in text:
            return param_kind
    return "unknown"


def _extract_lesson_stamina_cost(text: str) -> int | None:
    """从授業选项上方的 OCR 文本中提取体力消耗值。

    例: "-4" → 4, "ー8" → 8
    """
    match = _LESSON_STAMINA_COST_RE.search(text or "")
    return int(match.group(1)) if match else None


def _read_lesson_info_panel(app: "AppProcessor") -> str:
    """读取当前授業选项信息面板（PC_ACTION_INFO）的 OCR 文本。"""
    results = getattr(app, "latest_results", None)
    if results is None:
        return ""
    info_boxes = results.filter_by_label(ProducerLabels.PC_ACTION_INFO)
    if not info_boxes:
        return ""
    info_box = info_boxes.first()
    frame = getattr(info_box, "frame", None)
    if frame is None or getattr(frame, "size", 0) <= 0:
        return ""
    try:
        ocr_results = _LESSON_INFO_OCR.ocr(frame)
        merged = ocr_results.auto_merge_lines(
            cy_range=max(4, int(frame.shape[0] * 0.015)),
            width_gap=max(10, int(frame.shape[1] * 0.02)),
        )
        lines = [
            normalize_ocr_jp(getattr(line, "text", "")).strip()
            for line in merged
            if len(normalize_ocr_jp(getattr(line, "text", "")).strip()) >= 2
        ]
        text = "；".join(lines)
    except Exception as exc:  # noqa: BLE001
        logger.debug("lesson info: 面板 OCR 失败: {}", exc)
        text = ""

    # Debug 可視化
    if text:
        _lesson_debugger.add_box(
            int(getattr(info_box, "x", 0)),
            int(getattr(info_box, "y", 0)),
            max(int(getattr(info_box, "w", 0) - getattr(info_box, "x", 0)), 1),
            max(int(getattr(info_box, "h", 0) - getattr(info_box, "y", 0)), 1),
            label=f"LessonInfo: {text[:40]}",
            color=(100, 255, 100),
            alpha=0.15,
            duration=3.0,
            font_size=14,
        )
    return text


def _ocr_lesson_stamina_costs(
    app: "AppProcessor",
    action_boxes: list,
) -> list[int | None]:
    """OCR 读取每个授業选项上方的体力消耗标签。

    体力消耗数字显示在 PC_ACTION 框的正上方区域。
    """
    frame = getattr(app, "latest_frame", None)
    costs: list[int | None] = []
    if frame is None or getattr(frame, "size", 0) <= 0:
        return [None] * len(action_boxes)

    for box in action_boxes:
        # 选项上方区域：宽度同选项，高度约 40px
        bx = int(getattr(box, "x", 0))
        by = int(getattr(box, "y", 0))
        bw = int(getattr(box, "w", 0)) - bx if hasattr(box, "w") else 0
        cost_h = max(40, int(by * 0.03))  # 上方标签高度
        cost_y = max(0, by - cost_h)
        cost_w = max(bw, 80)
        if cost_h <= 5 or cost_w <= 5:
            costs.append(None)
            continue
        try:
            crop = frame[cost_y:by, bx:bx + cost_w]
            if crop.size <= 0:
                costs.append(None)
                continue
            text = ocr_text(crop)
            cost = _extract_lesson_stamina_cost(text)
            costs.append(cost)
            if cost is not None:
                _lesson_debugger.add_box(
                    bx, cost_y, cost_w, cost_h,
                    label=f"体力-{cost}",
                    color=(255, 80, 80),
                    thickness=2,
                    duration=3.0,
                )
        except Exception:  # noqa: BLE001
            costs.append(None)
    return costs


def _probe_lesson_options(
    app: "AppProcessor",
    candidates: list[ScheduleActionCandidate],
) -> None:
    """逐个点击授業选项，从信息面板读取效果描述 + 属性类型。

    流程:
      1. 第一个选项通常已预选 → 先读取其信息面板
      2. 逐个点击其余选项 → 等待 UI 刷新 → 读取信息面板
      3. 将属性类型 + 效果描述写入 candidate.metadata

    与おでかけ探査相同模式：点击只切换高亮，不确认。
    """
    if not candidates:
        return

    logger.info("lesson: 授業探査開始 — {} 個選項", len(candidates))

    # 第一个选项通常已预选 → 直接读取信息面板
    first_info = _read_lesson_info_panel(app)
    if first_info:
        stat_kind = _detect_lesson_stat_from_info(first_info)
        candidates[0].metadata["lesson_effect"] = first_info
        candidates[0].metadata["lesson_stat"] = stat_kind
        if stat_kind != "unknown":
            candidates[0].kind = stat_kind
        logger.debug(
            "lesson: 選項 #0 効果(預選): stat={}, text={}",
            stat_kind, first_info[:60],
        )

    # 逐个点击其余选项
    for idx, candidate in enumerate(candidates):
        if candidate.metadata.get("lesson_effect"):
            continue  # 已取得（预选项）

        try:
            app.device.click_element(candidate.box)
            sleep(_LESSON_PROBE_TAP_WAIT)
            sleep(_LESSON_PROBE_INFER_WAIT)

            info_text = _read_lesson_info_panel(app)
            if info_text:
                stat_kind = _detect_lesson_stat_from_info(info_text)
                candidate.metadata["lesson_effect"] = info_text
                candidate.metadata["lesson_stat"] = stat_kind
                if stat_kind != "unknown":
                    candidate.kind = stat_kind
                logger.debug(
                    "lesson: 選項 #{} 効果: stat={}, text={}",
                    idx, stat_kind, info_text[:60],
                )
            else:
                logger.debug("lesson: 選項 #{} 信息面板未検出", idx)

            # Debug 可視化
            _lesson_debugger.add_box(
                int(getattr(candidate.box, "x", 0)),
                int(getattr(candidate.box, "y", 0)),
                max(int(getattr(candidate.box, "w", 0) - getattr(candidate.box, "x", 0)), 1),
                max(int(getattr(candidate.box, "h", 0) - getattr(candidate.box, "y", 0)), 1),
                color=(0, 200, 100),
                thickness=2,
                duration=3,
                label=f"Lesson#{idx} {candidate.kind}",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("lesson: 選項 #{} 探査異常: {}", idx, exc)

    probed = [c for c in candidates if c.metadata.get("lesson_effect")]
    logger.info(
        "lesson: 授業探査完了 — {}/{} 個取得効果描述",
        len(probed), len(candidates),
    )


def _collect_lesson_option_candidates(
    app: "AppProcessor",
    ctx: "ProduceContext",
    *,
    position: str,
) -> List[ScheduleActionCandidate]:
    """采集授業課程選項候选。

    授業画面有 3 个 PC_ACTION 选项（ボーカル/ダンス/ビジュアル），
    每个选项上方显示体力消耗，点击后信息面板显示效果描述。
    """
    action_boxes = _collect_schedule_action_boxes(app)
    if not action_boxes:
        return []

    selected_index = (
        ctx.pending_schedule_index
        if position == GameplayPosition.SCHEDULE_LESSON_SELECTED
        else None
    )

    # OCR 读取选项上方的体力消耗
    stamina_costs = _ocr_lesson_stamina_costs(app, action_boxes)

    candidates: list[ScheduleActionCandidate] = []
    for idx, box in enumerate(action_boxes):
        # OCR 选项内容文本（叙事性描述，非数据库名）
        title = ocr_text(box.frame) if getattr(box, "frame", None) is not None else ""
        cost = stamina_costs[idx] if idx < len(stamina_costs) else None
        candidates.append(
            ScheduleActionCandidate(
                index=idx,
                title=title,
                kind="unknown",  # 探査后由信息面板 OCR 确定
                recommended=False,
                selected=selected_index == idx,
                box=box,
                metadata={
                    "stamina_cost": cost,
                    "lesson_option": True,
                },
            )
        )

    # 探査: 逐个点击读取信息面板，确定属性类型
    if position != GameplayPosition.SCHEDULE_LESSON_SELECTED:
        _probe_lesson_options(app, candidates)

    # 视觉 SP 徽章检测
    for cand in candidates:
        if cand.box and detect_sp_badge(cand.box):
            cand.metadata["is_sp"] = True
            logger.info("SP badge detected visually on lesson candidate #{}", cand.index)

    # hydrate: 根据属性类型赋予 action_id 和 rl_action_type
    from .decision import hydrate_lesson_candidates
    hydrate_lesson_candidates(candidates)

    logger.info(
        "lesson: 采集完成 — {} 個候选: {}",
        len(candidates),
        [(c.index, c.kind, c.metadata.get("stamina_cost")) for c in candidates],
    )
    return candidates


def collect_schedule_action_candidates(
    app: "AppProcessor",
    ctx: "ProduceContext",
    *,
    position: str,
) -> List[ScheduleActionCandidate]:
    if position == GameplayPosition.SCHEDULE_PRESENT_SUPPORT:
        return _collect_present_support_candidates(app, ctx)

    # 授業課程選項: 独立的采集流程（探査 + 属性识别）
    if position in (
        GameplayPosition.SCHEDULE_LESSON_OPTIONS,
        GameplayPosition.SCHEDULE_LESSON_SELECTED,
    ):
        return _collect_lesson_option_candidates(app, ctx, position=position)

    action_boxes = _collect_schedule_action_boxes(app)
    recommended_kind = _detect_recommended_kind(app)
    selected_index = ctx.pending_schedule_index if position == "schedule_selected" else None
    lookup_text_groups = _collect_schedule_lookup_texts(app, action_boxes)

    candidates: list[ScheduleActionCandidate] = []
    for idx, box in enumerate(action_boxes):
        # ── 第一步: 尝试 CLIP 记忆命中 ──
        clip_result = _resolve_schedule_from_clip(app, box)
        if clip_result is not None:
            # CLIP 直接命中 → 使用记忆中的 action_id / param_kind
            action_id = clip_result["action_id"]
            param_kind = clip_result["param_kind"] or "unknown"
            rl_action_type = clip_result["rl_action_type"] or ""
            candidates.append(
                ScheduleActionCandidate(
                    index=idx,
                    title=action_id,  # hydrate 阶段会用 display_name 覆盖
                    kind=param_kind,
                    recommended=param_kind == recommended_kind and param_kind != "unknown",
                    selected=selected_index == idx,
                    box=box,
                    action_id=action_id,
                    source="clip",
                    confidence=1.0,
                    metadata={
                        "clip_match": True,
                        "rl_action_type": rl_action_type,
                    },
                )
            )
            continue

        # ── 第二步: CLIP 未命中 → 常规 OCR + 启发式 ──
        direct_title = ocr_text(box.frame)
        lookup_texts = list(lookup_text_groups[idx]) if idx < len(lookup_text_groups) else []
        title, title_source = _choose_schedule_candidate_title(
            direct_title,
            lookup_texts,
            index=idx,
        )
        kind = infer_param_kind(title)
        candidates.append(
            ScheduleActionCandidate(
                index=idx,
                title=title,
                kind=kind,
                recommended=kind == recommended_kind and kind != "unknown",
                selected=selected_index == idx,
                box=box,
                metadata={
                    "ocr_title": _normalize_schedule_text(direct_title),
                    "lookup_texts": lookup_texts,
                    "title_source": title_source,
                },
            )
        )

    # 视觉 SP 徽章检测（在 hydrate 前标记，以便正确解析 action_id）
    for cand in candidates:
        if cand.box and detect_sp_badge(cand.box):
            cand.metadata["is_sp"] = True
            logger.info("SP badge detected visually on candidate #{}", cand.index)

    # hydrate 阶段为候选补充 action_id / rl_action_type 等
    hydrate_schedule_candidates(candidates)

    # ── 第三步: hydrate 后对成功识别的非 CLIP 候选学习 CLIP 记忆 ──
    learned_new = False
    for cand in candidates:
        if cand.metadata.get("clip_match"):
            continue  # 已由 CLIP 命中，无需再学习
        if _is_unknown_schedule_action_id(cand.action_id):
            continue  # 未识别 → 不学习
        image = getattr(cand.box, "frame", None) if cand.box else None
        _learn_schedule_clip(
            app,
            image,
            cand.action_id,
            param_kind=cand.kind or "",
            rl_action_type=cand.metadata.get("rl_action_type", ""),
        )
        learned_new = True

    # 学习了新类型后，尝试重新识别 P手帳 缓存的未识别图标
    if learned_new and _notebook_icon_clip_cache:
        _retry_cached_notebook_icons(app)

    # ── 第四步: SCHEDULE_SELECTED 位置下读取信息面板效果描述 ──
    if position == "schedule_selected":
        selected_cand = next(
            (c for c in candidates if c.selected), None
        )
        if selected_cand is not None:
            effect_text = _probe_action_info_panel(app, selected_cand)
            if effect_text:
                selected_cand.metadata["effect_text"] = effect_text

    return candidates


def decide_schedule_action(
    app: "AppProcessor",
    ctx: "ProduceContext",
    candidates: List[ScheduleActionCandidate],
    *,
    position: str,
) -> int:
    decision_state = build_decision_state(
        app,
        ctx,
        phase="schedule",
        position=position,
        candidates=candidates,
        reason="schedule_decision",
    )
    recovery_plan = None
    if position != GameplayPosition.SCHEDULE_SELECTED:
        recovery_plan = _select_low_stamina_recovery_action(decision_state)
        if recovery_plan is not None:
            _annotate_low_stamina_recovery_preference(
                decision_state,
                preferred_index=recovery_plan[0],
                reason=recovery_plan[1],
            )
    decision = invoke_decision_strategy(
        ctx.schedule_strategy,
        app,
        ctx,
        candidates,
        decision_state=decision_state,
    )
    if decision is not None:
        resolved_index = resolve_candidate_index(decision, candidates)
        if recovery_plan is not None and resolved_index != recovery_plan[0]:
            logger.info(
                "schedule: 体力偏低，覆盖原决策 {} -> {} ({})",
                resolved_index,
                recovery_plan[0],
                recovery_plan[1],
            )
            return recovery_plan[0]
        return resolved_index

    if recovery_plan is not None:
        return recovery_plan[0]

    if ctx.pending_schedule_index is not None and 0 <= ctx.pending_schedule_index < len(candidates):
        return ctx.pending_schedule_index

    recommended_index = first_matching_index(candidates, kind=_detect_recommended_kind(app))
    if recommended_index is not None:
        return recommended_index

    for idx, candidate in enumerate(candidates):
        if candidate.recommended:
            return idx

    return 0


def execute_schedule_step(
    app: "AppProcessor",
    ctx: "ProduceContext",
    *,
    position: str,
) -> ScheduleStepResult | None:
    candidates = collect_schedule_action_candidates(app, ctx, position=position)
    if not candidates:
        return None

    target_index = decide_schedule_action(app, ctx, candidates, position=position)
    target = candidates[target_index]

    logger.debug(
        "schedule step: position={}, target_index={}, title={!r}, kind={}, recommended={}",
        position,
        target_index,
        target.title,
        target.kind,
        target.recommended,
    )

    app.device.click_element(target.box)
    if position == GameplayPosition.SCHEDULE_PRESENT_SUPPORT:
        ctx.record_operation(
            "select_schedule_present_support",
            target=target.title or target.kind or target.action_id or f"option_{target.index + 1}",
            details={
                "index": target.index,
                "kind": target.kind,
                "action_id": target.action_id,
                "db_id": target.db_id,
                "source": target.source,
            },
        )
        return ScheduleStepResult(status="present_selected", candidate=target)

    # ── 授業選項確認（信息面板已顯示） ──
    if position == GameplayPosition.SCHEDULE_LESSON_SELECTED:
        ctx.record_operation(
            "confirm_lesson_option",
            target=target.title or target.kind or f"lesson_{target.index + 1}",
            details={
                "index": target.index,
                "kind": target.kind,
                "action_id": target.action_id,
                "stamina_cost": target.metadata.get("stamina_cost"),
            },
        )
        return ScheduleStepResult(status="confirmed", candidate=target)

    # ── 授業選項選択（探査完了 → 决策 → 点击） ──
    if position == GameplayPosition.SCHEDULE_LESSON_OPTIONS:
        ctx.pending_schedule_index = target.index
        ctx.pending_schedule_label = (
            target.title or target.kind or target.action_id or f"lesson_{target.index + 1}"
        )
        ctx.record_operation(
            "select_lesson_option",
            target=ctx.pending_schedule_label,
            details={
                "index": target.index,
                "kind": target.kind,
                "action_id": target.action_id,
                "stamina_cost": target.metadata.get("stamina_cost"),
                "lesson_effect": target.metadata.get("lesson_effect", "")[:80],
            },
        )
        return ScheduleStepResult(status="selected", candidate=target)

    if position == "schedule_selected":
        ctx.record_operation(
            "confirm_schedule_action",
            target=target.title or target.kind or target.action_id or f"action_{target.index + 1}",
            details={
                "index": target.index,
                "kind": target.kind,
                "recommended": target.recommended,
                "action_id": target.action_id,
                "db_id": target.db_id,
            },
        )
        return ScheduleStepResult(status="confirmed", candidate=target)

    ctx.pending_schedule_index = target.index
    ctx.pending_schedule_label = target.title or target.kind or target.action_id or f"action_{target.index + 1}"
    ctx.record_operation(
        "select_schedule_action",
        target=ctx.pending_schedule_label,
        details={
            "index": target.index,
            "kind": target.kind,
            "recommended": target.recommended,
            "action_id": target.action_id,
            "db_id": target.db_id,
        },
    )
    return ScheduleStepResult(status="selected", candidate=target)


# ────────────────────────────────────────────────────────────
# Handler
# ────────────────────────────────────────────────────────────

class ScheduleHandler:
    """日程行动选择的 gameplay handler 包装。

    处理两类场景：
    1. 常规行程选择 — 委托给 execute_schedule_step()
    2. 行程事件对话（おでかけ等） — 选项交给 dialogue 逻辑，
       文本推进仅点击推进、绝不快进
    """

    phase_tag = "schedule"
    priority = 50

    # 行程事件相关位置集合
    _EVENT_POSITIONS = frozenset({
        "schedule_event_options",
        "schedule_event_dialogue",
    })

    def can_handle(self, app, ctx, phase, position):
        return phase == "schedule"

    def handle(self, app, ctx, phase, position):
        from src.core.tasks.producer_challenge.gameplay.handler_base import HandlerResult

        # ── 行程事件对话选项（おでかけ等の選択肢） ──
        if position == "schedule_event_options":
            from src.core.tasks.producer_challenge.gameplay.dialogue import (
                execute_dialogue_step,
            )
            result = execute_dialogue_step(app, ctx, position=position)
            if result is None:
                return HandlerResult.no_action("no dialogue options in schedule event")
            return HandlerResult.ok(f"schedule event {result.status}", sleep_after=0.6)

        # ── 行程事件对话文本推进（不快进） ──
        if position == "schedule_event_dialogue":
            from src.core.tasks.producer_challenge.gameplay.common import click_relative_point
            click_relative_point(app, x_ratio=0.5, y_ratio=0.82, label="schedule-event-advance")
            logger.debug("schedule: 行程事件对话推进（不快进）")
            return HandlerResult.ok("schedule event dialogue advance", sleep_after=0.6)

        if position == GameplayPosition.SCHEDULE_PRESENT_SUPPORT:
            result = execute_schedule_step(app, ctx, position=position)
            if result is None:
                return HandlerResult.no_action("no present support candidates found")
            ctx.handler_state["unknown_retry_override"] = {
                "reason": "present_support_selection",
                "retry_limit": int(
                    ctx.handler_state.get("present_support_unknown_retry_limit", 8) or 8
                ),
                "retry_sleep": float(
                    ctx.handler_state.get("present_support_unknown_retry_sleep", 0.8) or 0.8
                ),
            }
            return HandlerResult.ok("schedule present support selected", sleep_after=0.8)

        if position == GameplayPosition.SCHEDULE_PRESENT_SUPPORT_SHOWCASE:
            from src.core.tasks.producer_challenge.gameplay.common import click_relative_point

            # 这是活動支給奖励链中的资源箱 / 奖励展示页，点击上方安全区域继续，
            # 避免误触底栏的 P 饮料 / 手牌库按钮。
            click_relative_point(
                app,
                x_ratio=0.5,
                y_ratio=0.35,
                label="schedule-present-support-showcase",
            )
            ctx.record_operation(
                "advance_schedule_present_support_showcase",
                target=ProduceText.PRESENT_SUPPORT,
                position=position,
            )
            ctx.handler_state["unknown_retry_override"] = {
                "reason": "present_support_showcase",
                "retry_limit": int(
                    ctx.handler_state.get("present_support_showcase_unknown_retry_limit", 6) or 6
                ),
                "retry_sleep": float(
                    ctx.handler_state.get("present_support_showcase_unknown_retry_sleep", 0.6) or 0.6
                ),
            }
            return HandlerResult.ok("schedule present support showcase advance", sleep_after=0.8)

        # ── 授業課程選項 ──
        if position == GameplayPosition.SCHEDULE_LESSON_OPTIONS:
            result = execute_schedule_step(app, ctx, position=position)
            if result is None:
                return HandlerResult.no_action("no lesson option candidates found")
            ctx.handler_state["unknown_retry_override"] = {
                "reason": "lesson_option_selection",
                "retry_limit": 6,
                "retry_sleep": 0.6,
            }
            return HandlerResult.ok(
                f"lesson option selected: {result.candidate.kind}",
                sleep_after=0.8,
            )

        # ── 授業選項已選中（信息面板表示中）→ 点击确认 ──
        if position == GameplayPosition.SCHEDULE_LESSON_SELECTED:
            result = execute_schedule_step(app, ctx, position=position)
            if result is None:
                return HandlerResult.no_action("no lesson selected candidate")
            ctx.handler_state["unknown_retry_override"] = {
                "reason": "confirm_lesson_option",
                "retry_limit": 12,
                "retry_sleep": 0.7,
            }
            ctx.record_schedule_choice(
                result.candidate.title
                or result.candidate.kind
                or f"lesson_{result.candidate.index + 1}"
            )
            return HandlerResult.ok(
                f"lesson option confirmed: {result.candidate.kind}",
                sleep_after=0.8,
            )

        # ── 常规行程选择 ──

        # 首次进入 SCHEDULE_IDLE 时尝试读取 P手帳，获取后续日程供 LLM 参考
        if position == GameplayPosition.SCHEDULE_IDLE:
            cache_key = f"p_notebook_week_{ctx.current_week}"
            if ctx.handler_state.get(cache_key) is None:
                try:
                    notebook_entries = read_p_notebook(app, ctx, max_scroll_pages=2)
                    if notebook_entries:
                        logger.info(
                            "schedule: P手帳读取成功，第{}周，{}个日程条目",
                            ctx.current_week,
                            len(notebook_entries),
                        )
                        # P手帳关闭后需要等待画面恢复到 SCHEDULE_IDLE
                        sleep(0.5)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("schedule: P手帳读取异常，跳过: {}", exc)
                    ctx.handler_state[cache_key] = []

        result = execute_schedule_step(app, ctx, position=position)
        if result is None:
            # 无候选行动（如活動支給の宝箱领取画面）——
            # 连续无候选时点击画面上方安全区域以推进（避免误触底栏按钮）
            no_action_key = "schedule_no_action_count"
            count = ctx.handler_state.get(no_action_key, 0) + 1
            ctx.handler_state[no_action_key] = count
            if count >= 2:
                from src.core.tasks.producer_challenge.gameplay.common import click_relative_point
                # 使用屏幕上方偏左位置（y=0.35），避免误触底栏的手牌库/P饮料按钮
                click_relative_point(app, x_ratio=0.5, y_ratio=0.35, label="schedule-idle-fallback-tap")
                logger.debug("schedule: 无候选行动，第{}次回退点击画面上方安全区域", count)
                return HandlerResult.ok("schedule idle fallback tap", sleep_after=0.8)
            return HandlerResult.no_action("no schedule actions found")

        # 找到候选项时重置无候选计数器
        ctx.handler_state.pop("schedule_no_action_count", None)

        if result.status == "confirmed":
            action_name = (
                result.candidate.title
                or result.candidate.kind
                or f"action_{result.candidate.index + 1}"
            )
            # 周行动确认后，下一页经常会经历较长的剧情/演出切换。
            # 在真机上这段时间可能连续出现空帧，因此给主循环一次性更长的
            # unknown 被动复检窗口，避免还没等到真正页面就被误判成卡死。
            ctx.handler_state["unknown_retry_override"] = {
                "reason": "confirm_schedule_action",
                "retry_limit": int(
                    ctx.handler_state.get("schedule_confirm_unknown_retry_limit", 12) or 12
                ),
                "retry_sleep": float(
                    ctx.handler_state.get("schedule_confirm_unknown_retry_sleep", 0.7) or 0.7
                ),
            }
            ctx.record_schedule_choice(action_name)

        return HandlerResult.ok(f"schedule {result.status}", sleep_after=0.8)

    def __repr__(self):
        return f"<ScheduleHandler phase={self.phase_tag!r} priority={self.priority}>"
