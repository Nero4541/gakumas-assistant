"""考试轮盘队列识别。

考试中左上角有一个圆形轮盘，展示回合队列信息：
  - 各色扇区代表参数类型：粉红=Vocal，蓝=Dance，黄=Visual
  - 白色三角指针指向当前回合
  - 扇区数量 = 剩余回合数（已结束的回合扇区会消失）
  - 轮盘右侧显示当前参数名和加成倍率

提取结果：
  - queue: 逆时针顺序的参数队列（从当前回合开始）
  - remaining_turns: 剩余回合数（= 扇区数量）
  - current_param: 当前回合参数类型
  - current_bonus_pct: 当前回合加成百分比（右侧文字）
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Optional

import cv2
import numpy as np

from src.constants.game.text.produce_text import ProduceText
from src.core.tasks.producer_challenge.gameplay.common import ocr_text
from src.utils.logger import logger
from src.utils.string_tools import fullwidth_to_halfwidth

if TYPE_CHECKING:
    from src.core.tasks.producer_challenge.context import ProduceContext

# ── 颜色分类阈值（HSV 空间，高饱和+高亮度过滤分割线） ──
_SEG_S_THRESH = 150  # 饱和度下限（排除暗色分割线）
_SEG_V_THRESH = 150  # 明度下限
_POINTER_S_MAX = 60  # 指针白色：饱和度上限
_POINTER_V_MIN = 200  # 指针白色：明度下限
_POINTER_MIN_AREA = 50  # 指针三角最小面积(px²)
_POINTER_MAX_VERTICES = 5  # 指针轮廓最大顶点数（三角≈3~4）

# 参数名 → 内部 key
_PARAM_KEY = {"Vo": "vocal", "Da": "dance", "Vi": "visual"}
_PARAM_JP = {"Vo": ProduceText.VOCAL, "Da": ProduceText.DANCE, "Vi": ProduceText.VISUAL}


def _classify_pixel(h: int, s: int, v: int) -> Optional[str]:
    """将 HSV 像素分类为参数类型（仅高饱和+高亮度有效）。"""
    if s < _SEG_S_THRESH or v < _SEG_V_THRESH:
        return None  # 分割线 / 暗区
    if h >= 150 or h <= 12:
        return "Vo"  # Vocal（粉红）
    if 85 <= h <= 130:
        return "Da"  # Dance（蓝）
    if 12 < h <= 42:
        return "Vi"  # Visual（黄）
    return None


def _find_wheel_circle(frame: np.ndarray) -> Optional[tuple[int, int, int, int]]:
    """在画面左上角用 HoughCircles 定位轮盘，并自动扫描色环半径。

    通过以下步骤确保定位正确：
    1. HoughCircles 找候选圆心
    2. 对每个圆心扫描半径，找高饱和度色环（色段所在位置）
    3. 色环覆盖率最高的候选即为轮盘

    返回 (cx, cy, inner_r, ring_r)：
      - inner_r: HoughCircles 检测的几何圆半径
      - ring_r: 实际色段环的采样半径
    失败返回 None。
    """
    h, w = frame.shape[:2]
    # 搜索左上角区域（轮盘通常在 x<25%, y<25%）
    roi_x2 = int(w * 0.25)
    roi_y2 = int(h * 0.25)
    roi = frame[0:roi_y2, 0:roi_x2]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (9, 9), 2)
    hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

    # 内圆半径范围
    min_r = max(20, int(w * 0.035))
    max_r = int(w * 0.10)

    def _find_ring_radius(cx: int, cy: int) -> tuple[int, float]:
        """扫描各半径，找到高饱和度色环所在位置。返回 (best_r, coverage)。"""
        best_r, best_cov = 0, 0.0
        # 扫描半径 30~150，找色段密集区
        scan_min = max(20, int(w * 0.025))
        scan_max = min(int(w * 0.14), min(cx, cy, roi_x2 - cx, roi_y2 - cy) - 5)
        for test_r in range(scan_min, scan_max, 3):
            colored = 0
            total = 0
            for deg in range(0, 360, 8):
                rad = np.deg2rad(deg)
                sx = int(cx + test_r * np.cos(rad))
                sy = int(cy + test_r * np.sin(rad))
                if 0 <= sx < hsv_roi.shape[1] and 0 <= sy < hsv_roi.shape[0]:
                    total += 1
                    s_val = int(hsv_roi[sy, sx, 1])
                    v_val = int(hsv_roi[sy, sx, 2])
                    if s_val > 150 and v_val > 150:
                        colored += 1
            cov = colored / max(total, 1)
            if cov > best_cov:
                best_cov = cov
                best_r = test_r
        return best_r, best_cov

    # 收集所有候选圆
    all_circles = []
    for p2 in (40, 30, 20):
        circles = cv2.HoughCircles(
            blurred, cv2.HOUGH_GRADIENT, dp=1.2, minDist=30,
            param1=100, param2=p2, minRadius=min_r, maxRadius=max_r,
        )
        if circles is not None:
            for c in circles[0]:
                all_circles.append((int(c[0]), int(c[1]), int(c[2])))

    if not all_circles:
        return None

    # 去重（同一圆心附近多次检测）
    unique: list[tuple[int, int, int]] = []
    for c in all_circles:
        if not any(abs(c[0] - u[0]) < 15 and abs(c[1] - u[1]) < 15 for u in unique):
            unique.append(c)

    # 对每个独立圆心扫描色环
    best_result = None
    best_score = 0.0
    for cx, cy, r in unique:
        ring_r, ring_cov = _find_ring_radius(cx, cy)
        if ring_cov > best_score and ring_cov > 0.5:
            best_score = ring_cov
            best_result = (cx, cy, r, ring_r)

    if best_result:
        cx, cy, r, ring_r = best_result
        logger.debug(
            f"[轮盘] 内圆检测: center=({cx},{cy}) inner_r={r} "
            f"ring_r={ring_r} 色环覆盖={best_score:.0%}"
        )
        return best_result

    return None


def _detect_segments(
    hsv: np.ndarray, cx: int, cy: int, ring_r: int,
) -> list[tuple[int, int, str]]:
    """检测轮盘色段。

    在色环半径附近按角度采样，多半径投票分类颜色，
    合并连续同色段并处理 360° wrap-around。

    Args:
        ring_r: 色环采样半径（由 _find_wheel_circle 自动扫描得出）

    返回 [(start_deg, end_deg, color_code), ...] 按角度排序。
    """
    h, w = hsv.shape[:2]
    # 采样半径：围绕色环中心半径 ±8 步长3
    sample_radii = [ring_r + dr for dr in range(-8, 9, 3)]

    # 每 2° 采样
    angle_colors: dict[int, Optional[str]] = {}
    for deg in range(0, 360, 2):
        rad = np.radians(deg)
        votes: dict[str, int] = {}
        for r_s in sample_radii:
            px = int(cx + r_s * np.cos(rad))
            py = int(cy + r_s * np.sin(rad))
            if 0 <= py < h and 0 <= px < w:
                c = _classify_pixel(*hsv[py, px])
                if c:
                    votes[c] = votes.get(c, 0) + 1
        angle_colors[deg] = max(votes, key=votes.get) if votes else None

    # 合并连续同色区间
    raw_segs: list[tuple[int, int, Optional[str]]] = []
    cur_color: Optional[str] = None
    start = 0
    for deg in range(0, 360, 2):
        c = angle_colors[deg]
        if c != cur_color:
            if cur_color is not None:
                raw_segs.append((start, deg - 2, cur_color))
            start = deg
            cur_color = c
    if cur_color is not None:
        raw_segs.append((start, 358, cur_color))

    # 只保留有颜色的段
    colored = [(s, e, c) for s, e, c in raw_segs if c is not None]
    if not colored:
        return []

    # 处理首尾 wrap-around（首段和末段同色 → 合并）
    if len(colored) >= 2 and colored[0][2] == colored[-1][2]:
        merged_start = colored[-1][0]
        merged_end = colored[0][1] + 360  # 跨越 360° 边界
        colored = [(merged_start, merged_end, colored[0][2])] + colored[1:-1]

    # 按段中心角排序
    def _center(s: int, e: int) -> float:
        return ((s + e) / 2) % 360

    colored.sort(key=lambda x: _center(x[0], x[1]))
    return colored


def _find_pointer_angle(
    frame: np.ndarray, hsv: np.ndarray,
    cx: int, cy: int, ring_r: int,
) -> Optional[float]:
    """检测白色三角指针，返回其相对轮盘中心的角度。

    在色环外围搜索白色区域，找到面积最大且顶点≤5的三角形轮廓。
    """
    h, w = frame.shape[:2]

    # 构建环形 mask（色环半径 ±15 范围搜索指针）
    r_inner = ring_r - 5
    r_outer = ring_r + max(30, int(ring_r * 0.5))
    mask = np.zeros((h, w), dtype=np.uint8)
    for deg in range(0, 360, 1):
        rad = np.radians(deg)
        for r_s in range(r_inner, r_outer):
            px = int(cx + r_s * np.cos(rad))
            py = int(cy + r_s * np.sin(rad))
            if 0 <= py < h and 0 <= px < w:
                sv, vv = hsv[py, px][1], hsv[py, px][2]
                if sv < _POINTER_S_MAX and vv > _POINTER_V_MIN:
                    mask[py, px] = 255

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    # 找面积最大的三角形轮廓
    best_cnt = None
    best_area = 0
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < _POINTER_MIN_AREA:
            continue
        approx = cv2.approxPolyDP(cnt, 0.04 * cv2.arcLength(cnt, True), True)
        if len(approx) <= _POINTER_MAX_VERTICES and area > best_area:
            best_area = area
            best_cnt = cnt

    if best_cnt is None:
        return None

    M = cv2.moments(best_cnt)
    if M["m00"] == 0:
        return None
    ptr_x = int(M["m10"] / M["m00"])
    ptr_y = int(M["m01"] / M["m00"])
    angle = float(np.degrees(np.arctan2(ptr_y - cy, ptr_x - cx))) % 360
    logger.debug(f"[轮盘] 指针检测: pos=({ptr_x},{ptr_y}) 角度={angle:.1f}° 面积={best_area:.0f}")
    return angle


def _ocr_wheel_area(
    frame: np.ndarray, cx: int, cy: int, inner_r: int,
) -> tuple[Optional[str], Optional[int], Optional[int]]:
    """OCR 轮盘区域，提取当前参数名、加成百分比、回合数字。

    整体 OCR 轮盘 + 上方标签 + 右侧文字，通过正则分离各信息：
      - 参数名（ボーカル/ダンス/ビジュアル）
      - 加成百分比（紧跟参数名后的 N 位数字 + %）
      - 回合数字（参数名前的单位数，即中心数字）

    返回 (param_code, bonus_pct, ocr_turns)。
    """
    h, w = frame.shape[:2]
    # 整体区域：轮盘 + 上方标签 + 右侧文字
    margin_top = int(inner_r * 1.8)  # 上方 "残りターン" 标签
    x2 = min(w, cx + inner_r + int(w * 0.3))
    y1 = max(0, cy - inner_r - margin_top)
    y2 = min(h, cy + inner_r + 15)

    crop = frame[y1:y2, 0:x2]
    if crop.size == 0:
        return None, None, None

    scale = max(2, 200 // (y2 - y1))
    big = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    text = fullwidth_to_halfwidth(ocr_text(big))
    logger.debug(f"[轮盘] 整体OCR: '{text}'")

    # 匹配参数名
    param_code = None
    param_name_found = ""
    for code, jp_name in _PARAM_JP.items():
        if jp_name in text:
            param_code = code
            param_name_found = jp_name
            break

    # 从「参数名 + 百分比%」中提取倍率，回合数从「残りターン」单独提取
    # 注意: 考试进行中 "ダンス527%" 整体是倍率，不含回合数
    # 考试准备时 "ビジュアル9701%" 前1位可能是回合数但不可靠，优先以色段数为准
    ocr_turns = None
    bonus_pct = None
    if param_name_found:
        # 先尝试整体匹配: 参数名后所有数字+% 作为倍率
        m_full = re.search(re.escape(param_name_found) + r"\s*(\d{2,4})%", text)
        if m_full:
            bonus_pct = int(m_full.group(1))
            if not (50 <= bonus_pct <= 9999):
                bonus_pct = None

    # 也尝试从 "残りターン" 后提取回合数
    if ocr_turns is None:
        for variant in ProduceText.REMAINING_TURNS_OCR_VARIANTS:
            m3 = re.search(re.escape(variant) + r"\s*(\d{1,2})", text)
            if m3:
                ocr_turns = int(m3.group(1))
                break

    logger.debug(
        f"[轮盘] OCR解析: 参数={param_code} 倍率={bonus_pct} "
        f"OCR回合={ocr_turns}"
    )
    return param_code, bonus_pct, ocr_turns


def extract_exam_wheel_info(frame: np.ndarray) -> Optional[dict]:
    """从考试页面单帧提取轮盘队列信息。

    交叉验证逻辑：
      - 色段数量 vs OCR 回合数字 → 不一致时记录警告但以色段为准
      - 指针色段 vs OCR 参数名 → 不一致时以 OCR 为准（文字更可靠）

    返回:
      {
          "remaining_turns": 9,              # 剩余回合数（色段数量）
          "current_param": "visual",         # 当前回合参数
          "current_bonus_pct": 701,          # 当前回合加成百分比
          "queue": ["visual", "dance", ...], # 逆时针队列（从当前回合开始）
          "confidence": "high",              # 置信度（high/medium/low）
      }
    提取失败返回 None。
    """
    if frame is None or not hasattr(frame, "shape"):
        return None

    # 1. 定位轮盘内圆 + 色环半径
    circle = _find_wheel_circle(frame)
    if circle is None:
        logger.warning("[轮盘] 未检测到轮盘内圆")
        return None
    cx, cy, inner_r, ring_r = circle

    # 2. 检测色段（在色环半径处采样）
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    segments = _detect_segments(hsv, cx, cy, ring_r)
    if len(segments) < 2:
        logger.warning(f"[轮盘] 色段不足: {len(segments)}")
        return None

    seg_count = len(segments)

    # 3. 检测指针角度（使用色环半径范围搜索）
    pointer_angle = _find_pointer_angle(frame, hsv, cx, cy, ring_r)
    if pointer_angle is None:
        logger.warning("[轮盘] 未检测到指针")
        return None

    # 4. 找指针所在的段（当前回合）
    def _center(s: int, e: int) -> float:
        return ((s + e) / 2) % 360

    def _angle_dist(a1: float, a2: float) -> float:
        d = abs(a1 - a2) % 360
        return min(d, 360 - d)

    best_idx = min(
        range(len(segments)),
        key=lambda i: _angle_dist(pointer_angle, _center(segments[i][0], segments[i][1])),
    )

    # 5. 逆时针顺序（角度递减方向）
    queue_codes: list[str] = []
    n = len(segments)
    for offset in range(n):
        idx = (best_idx - offset) % n
        queue_codes.append(segments[idx][2])

    queue_keys = [_PARAM_KEY[c] for c in queue_codes]

    # 6. OCR 整体区域（参数名 + 加成倍率 + 回合数字）
    ocr_param, bonus_pct, ocr_turns = _ocr_wheel_area(frame, cx, cy, inner_r)

    # ── 交叉验证 ──
    confidence = "high"

    # 验证1: 色段数 vs OCR 回合数
    if ocr_turns is not None and ocr_turns != seg_count:
        logger.warning(
            f"[轮盘] 色段数={seg_count} 与 OCR回合={ocr_turns} 不一致，"
            f"以色段数为准"
        )
        confidence = "medium"

    # 验证2: 指针段颜色 vs OCR 参数名
    current_code = queue_codes[0]
    current_key = _PARAM_KEY[current_code]
    if ocr_param and ocr_param != current_code:
        logger.warning(
            f"[轮盘] 指针段={current_code} 与 OCR参数={ocr_param} 不一致，"
            f"以 OCR 为准"
        )
        current_key = _PARAM_KEY[ocr_param]
        queue_keys[0] = current_key
        confidence = "medium"

    # 缺少 OCR 信息时降低置信度
    if ocr_param is None or bonus_pct is None:
        confidence = "low"

    result = {
        "remaining_turns": seg_count,
        "current_param": current_key,
        "current_bonus_pct": bonus_pct,
        "queue": queue_keys,
        "confidence": confidence,
    }
    logger.info(
        f"[轮盘] 剩余{seg_count}回合 "
        f"当前={current_key}"
        + (f" {bonus_pct}%" if bonus_pct else "")
        + f" 队列={queue_keys}"
        + (f" (OCR回合={ocr_turns})" if ocr_turns is not None else "")
        + f" 置信={confidence}"
    )
    return result


def extract_exam_wheel_validated(
    capture_fn,
    max_frames: int = 3,
    min_agreement: int = 2,
) -> Optional[dict]:
    """多帧采集 + 共识校验。

    连续采集 max_frames 帧，对每帧独立提取，要求至少 min_agreement 帧
    在关键字段（remaining_turns + queue）上一致才返回结果。

    Args:
        capture_fn: 无参函数，返回 np.ndarray（ADB 截图等）
        max_frames: 最大采集帧数
        min_agreement: 最小一致帧数

    Returns:
        置信度最高的一致结果，或 None。
    """
    results: list[dict] = []
    for i in range(max_frames):
        frame = capture_fn()
        if frame is None:
            continue
        info = extract_exam_wheel_info(frame)
        if info is not None:
            results.append(info)

    if not results:
        logger.warning("[轮盘] 多帧采集全部失败")
        return None

    if len(results) == 1:
        logger.debug("[轮盘] 仅1帧有效，直接返回")
        return results[0]

    # 以 (remaining_turns, tuple(queue)) 为签名分组
    from collections import Counter

    def _signature(r: dict) -> tuple:
        return (r["remaining_turns"], tuple(r["queue"]))

    sig_counter = Counter(_signature(r) for r in results)
    best_sig, best_count = sig_counter.most_common(1)[0]

    if best_count < min_agreement:
        logger.warning(
            f"[轮盘] 多帧不一致: "
            f"{dict(sig_counter)} (需要{min_agreement}帧一致)"
        )
        # 仍返回出现最多的，但降低置信度
        for r in results:
            if _signature(r) == best_sig:
                r["confidence"] = "low"
                return r

    # 从一致帧中选置信度最高的
    confidence_rank = {"high": 3, "medium": 2, "low": 1}
    best_result = max(
        (r for r in results if _signature(r) == best_sig),
        key=lambda r: confidence_rank.get(r.get("confidence", "low"), 0),
    )
    logger.info(
        f"[轮盘] 多帧共识: {best_count}/{len(results)}帧一致 "
        f"置信={best_result['confidence']}"
    )
    return best_result


def store_exam_wheel_info(ctx: "ProduceContext", info: dict) -> None:
    """将轮盘信息存入上下文。"""
    ctx.handler_state["exam_wheel_info"] = info


def get_exam_wheel_info(ctx: "ProduceContext") -> Optional[dict]:
    """从上下文读取轮盘信息。"""
    return ctx.handler_state.get("exam_wheel_info")
