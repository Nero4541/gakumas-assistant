"""Step 4b: 采集偶像卡页面信息并点击「次へ」。

在偶像卡选择完毕后、点击「次へ」之前，采集：
  - おすすめ効果 (推荐效果) — 点击推荐效果栏中的图标，OCR 弹出的 tooltip
  - 育成情報 — 打开育成情報面板，读取审查基准和育成课题
"""

import re
from time import sleep
from typing import TYPE_CHECKING, Any, Dict, List, Tuple

from src.constants.game.text.button_text import ButtonText
from src.constants.game.text.produce_text import ProduceText
from src.constants.yolo.labels.baseUI_Labels import BaseUILabels
from src.core.inference.ocr_engine import OCRService
from src.core.tasks.producer_challenge.gameplay.common import click_relative_point
from src.core.tasks.producer_challenge.steps.base import ProduceStep
from src.core.tasks.producer_challenge.ui import (
    find_button,
    inertial_swipe,
    wait_frame_stable,
)
from src.utils.debug_tools import DebugTools
from src.utils.logger import logger
from src.utils.opencv_tools import compute_ssim_score
from src.utils.string_tools import MatchConfig

if TYPE_CHECKING:
    from src.core.tasks.producer_challenge.context import ProduceContext
    from src.main import AppProcessor

_ocr = OCRService()
_debugger = DebugTools()

# ── おすすめ効果 ─────────────────────────────────────────
# Tooltip 弹出区域（全帧坐标），用于 SSIM 比较
_TOOLTIP_COMPARE_Y1 = 950
_TOOLTIP_COMPARE_Y2 = 1200
_TOOLTIP_COMPARE_X1 = 200
_TOOLTIP_COMPARE_X2 = 900
# OCR 裁切稍窄，排除底部百分比文本
_TOOLTIP_OCR_Y1 = 940
_TOOLTIP_OCR_Y2 = 1150
_TOOLTIP_OCR_X1 = 150
_TOOLTIP_OCR_X2 = 950
# 点击 y 坐标（おすすめ効果 图标行）
_ICON_CLICK_Y = 1400
# 扫描 x 范围及步长
_ICON_SCAN_X_START = 300
_ICON_SCAN_X_END = 950
_ICON_SCAN_STEP = 60
# SSIM 低于此值判定为有 tooltip 弹出
_TOOLTIP_SSIM_THRESHOLD = 0.85

# ── 育成情報 ─────────────────────────────────────────────
_PARAM_CANONICAL = {
    **{variant: "vocal" for variant in ProduceText.VOCAL_OCR_VARIANTS},
    **{variant: "dance" for variant in ProduceText.DANCE_OCR_VARIANTS},
    **{variant: "visual" for variant in ProduceText.VISUAL_OCR_VARIANTS},
}
_TASK_PARAM_PATTERN = "|".join(
    re.escape(variant)
    for variant in (
        *ProduceText.VOCAL_OCR_VARIANTS,
        *ProduceText.DANCE_OCR_VARIANTS,
        *ProduceText.VISUAL_OCR_VARIANTS,
    )
)
_TASK_CONDITION_RE = re.compile(
    rf"({_TASK_PARAM_PATTERN})"
    rf"\s*(\d+)\s*({ProduceText.COMPARISON_GE}|{ProduceText.COMPARISON_LE})",
)
_TASK_TYPE_VARIANTS = {
    **{
        variant: ProduceText.TASK_TYPE_PERFORMANCE
        for variant in ProduceText.TASK_TYPE_PERFORMANCE_OCR_VARIANTS
    },
    ProduceText.TASK_TYPE_WEAKNESS: ProduceText.TASK_TYPE_WEAKNESS,
}
_SCROLL_COMPARE_Y_TOP = 1350
_SCROLL_COMPARE_Y_BOTTOM = 2000
_TASK_AREA_Y_TOP = 1350
_TASK_AREA_Y_BOTTOM = 2100


class CollectIdolPageInfoStep(ProduceStep):
    step_name = "collect_idol_page_info"

    def validate(self, app: "AppProcessor", ctx: "ProduceContext") -> bool:
        if app.latest_results.exists_label(BaseUILabels.PRODUCT_CARD_SELECTED):
            return True
        idol_labels = (
            BaseUILabels.PRODUCE_CARD_VOCAL,
            BaseUILabels.PRODUCE_CARD_DANCE,
            BaseUILabels.PRODUCE_CARD_VISUAL,
        )
        return any(app.latest_results.exists_label(lbl) for lbl in idol_labels)

    def execute(self, app: "AppProcessor", ctx: "ProduceContext") -> bool:
        try:
            self._collect_recommended_effects(app, ctx)
        except Exception as exc:
            logger.warning(f"おすすめ効果采集失败: {exc}")

        try:
            self._collect_training_info(app, ctx)
        except Exception as exc:
            logger.warning(f"育成情報采集失败: {exc}")

        # 点击「次へ」进入支援卡编成
        app.game_utils.click_button(
            ButtonText.NEXT,
            match_config=MatchConfig(fuzz_threshold=80),
        )
        app.game_utils.wait_loading()

        for _ in range(15):
            if app.latest_results.exists_label(BaseUILabels.SUPPORT_CARD):
                logger.debug("成功进入支援卡编成页")
                return True
            if app.latest_results.exists_label(BaseUILabels.BLANK_SLOT):
                logger.debug("进入支援卡编成页（存在空白槽位）")
                return True
            sleep(1)

        raise TimeoutError("等待支援卡编成页超时")

    # ── おすすめ効果 ─────────────────────────────────────

    def _collect_recommended_effects(
        self, app: "AppProcessor", ctx: "ProduceContext"
    ) -> None:
        """点击おすすめ効果区域的图标，通过 SSIM 检测 tooltip 出现并 OCR。"""
        # 先消除任何残留 tooltip 并获取基线截图
        click_relative_point(app, x_ratio=0.05, y_ratio=0.17, label="clear-tooltip")
        sleep(0.4)
        wait_frame_stable(app, timeout=2.0)
        baseline = app.device.capture()
        baseline_crop = baseline[
            _TOOLTIP_COMPARE_Y1:_TOOLTIP_COMPARE_Y2,
            _TOOLTIP_COMPARE_X1:_TOOLTIP_COMPARE_X2,
        ]

        # Debug: 显示 SSIM 比较区域和图标扫描行
        _debugger.add_box(
            _TOOLTIP_COMPARE_X1, _TOOLTIP_COMPARE_Y1,
            _TOOLTIP_COMPARE_X2, _TOOLTIP_COMPARE_Y2,
            label="tooltip SSIM", color=(255, 200, 0), alpha=0.2, duration=8.0,
        )
        _debugger.add_box(
            _TOOLTIP_OCR_X1, _TOOLTIP_OCR_Y1,
            _TOOLTIP_OCR_X2, _TOOLTIP_OCR_Y2,
            label="tooltip OCR", color=(0, 200, 255), alpha=0.2, duration=8.0,
        )
        _debugger.add_line(
            _ICON_SCAN_X_START, _ICON_CLICK_Y,
            _ICON_SCAN_X_END, _ICON_CLICK_Y,
            color=(255, 0, 255), thickness=2, duration=8.0,
        )

        effects: List[str] = []

        for x_pos in range(
            _ICON_SCAN_X_START, _ICON_SCAN_X_END + 1, _ICON_SCAN_STEP
        ):
            # 消除上一个 tooltip
            click_relative_point(app, x_ratio=0.05, y_ratio=0.17, label="clear-tooltip")
            sleep(0.25)

            app.device.click(x_pos, _ICON_CLICK_Y)
            sleep(0.55)

            frame = app.device.capture()
            current_crop = frame[
                _TOOLTIP_COMPARE_Y1:_TOOLTIP_COMPARE_Y2,
                _TOOLTIP_COMPARE_X1:_TOOLTIP_COMPARE_X2,
            ]
            ssim = compute_ssim_score(baseline_crop, current_crop)
            if ssim >= _TOOLTIP_SSIM_THRESHOLD:
                continue

            tooltip_ocr_crop = frame[
                _TOOLTIP_OCR_Y1:_TOOLTIP_OCR_Y2,
                _TOOLTIP_OCR_X1:_TOOLTIP_OCR_X2,
            ]
            results = _ocr.ocr(tooltip_ocr_crop)
            texts = sorted(results.results, key=lambda r: (r.cy, r.cx))
            combined = " ".join(
                r.text.strip()
                for r in texts
                if r.text.strip() and r.confidence >= 0.25
            )
            if not combined:
                continue

            if not _is_duplicate(combined, effects):
                effects.append(combined)
                logger.debug(
                    f"おすすめ効果 x={x_pos} ssim={ssim:.3f}: {combined}"
                )

        # 消除最后的 tooltip
        click_relative_point(app, x_ratio=0.05, y_ratio=0.17, label="clear-tooltip")
        sleep(0.3)
        wait_frame_stable(app, timeout=2.0)

        ctx.recommended_effects = effects
        logger.info(f"おすすめ効果采集完成: {len(effects)} 条")
        for i, eff in enumerate(effects, 1):
            logger.debug(f"  効果{i}: {eff}")

    # ── 育成情報 ─────────────────────────────────────────

    def _collect_training_info(
        self, app: "AppProcessor", ctx: "ProduceContext"
    ) -> None:
        """打开育成情報面板，采集审查基准和育成课题。"""
        btn = find_button(app, ProduceText.TRAINING_INFO, fuzz_threshold=65)
        if btn is None:
            logger.warning("未找到育成情報按钮")
            return

        app.device.click(btn.cx, btn.cy)
        sleep(1.0)
        wait_frame_stable(app, timeout=3.0)

        if not app.latest_results.exists_label(BaseUILabels.MODAL_HEADER):
            logger.warning("育成情報面板未打开")
            return

        try:
            exam = self._read_exam_criteria(app)
            ctx.exam_criteria = exam
            logger.info(f"审查基准: {exam}")

            tasks = self._read_training_tasks_with_scroll(app)
            ctx.training_tasks = tasks
            logger.info(f"育成课题: {len(tasks)} 条")
            for t in tasks:
                logger.debug(f"  课题: {t}")
        finally:
            self._close_training_info(app)

    def _read_exam_criteria(self, app: "AppProcessor") -> Dict[str, Any]:
        """读取「最終試験の審査基準」: 目标分数 + 参数优先级。"""
        frame = app.device.capture()
        crop = frame[700:1300, 50:1050]
        results = _ocr.ocr(crop)

        exam: Dict[str, Any] = {"target_score": None, "priority": []}

        for r in results.results:
            text = r.text.strip()
            if text.isdigit() and 50 <= int(text) <= 9999:
                exam["target_score"] = int(text)
                break

        params: List[Tuple[int, str]] = []
        for r in results.results:
            canonical = _PARAM_CANONICAL.get(r.text.strip())
            if canonical:
                params.append((r.cx, canonical))
        params.sort(key=lambda p: p[0])
        exam["priority"] = [name for _, name in params]

        return exam

    def _read_training_tasks_with_scroll(
        self, app: "AppProcessor"
    ) -> List[Dict[str, Any]]:
        """读取育成课题列表，自动滚动直到内容不再变化。"""
        all_tasks: List[Dict[str, Any]] = []
        seen_conditions: set = set()

        for scroll_round in range(6):
            frame = app.device.capture()
            new_tasks = self._parse_tasks_from_frame(frame, seen_conditions)
            all_tasks.extend(new_tasks)

            if scroll_round > 0 and not new_tasks:
                break

            before_crop = frame[
                _SCROLL_COMPARE_Y_TOP:_SCROLL_COMPARE_Y_BOTTOM, 50:1050
            ]
            # Debug: 显示滚动比较区域和任务解析区域
            _debugger.add_box(
                50, _SCROLL_COMPARE_Y_TOP, 1050, _SCROLL_COMPARE_Y_BOTTOM,
                label=f"scroll SSIM:{scroll_round}", color=(100, 200, 255),
                alpha=0.15, duration=3.0,
            )
            _debugger.add_box(
                50, _TASK_AREA_Y_TOP, 1050, _TASK_AREA_Y_BOTTOM,
                label="task OCR", color=(200, 100, 255),
                alpha=0.1, duration=3.0,
            )
            # 缩短滑动距离（1800→1200 改为 1700→1350），配合 hold_end 消除惯性
            inertial_swipe(
                app, 540, 1700, 540, 1350, duration=0.35, settle_timeout=2.5
            )

            after_frame = app.device.capture()
            after_crop = after_frame[
                _SCROLL_COMPARE_Y_TOP:_SCROLL_COMPARE_Y_BOTTOM, 50:1050
            ]
            ssim = compute_ssim_score(before_crop, after_crop)
            if ssim > 0.98:
                extra = self._parse_tasks_from_frame(after_frame, seen_conditions)
                all_tasks.extend(extra)
                break

        return all_tasks

    @staticmethod
    def _parse_tasks_from_frame(
        frame, seen_conditions: set
    ) -> List[Dict[str, Any]]:
        """从当前帧解析育成课题。"""
        crop = frame[_TASK_AREA_Y_TOP:_TASK_AREA_Y_BOTTOM, 50:1050]
        results = _ocr.ocr(crop)
        sorted_results = sorted(results.results, key=lambda r: (r.cy, r.cx))

        tasks: List[Dict[str, Any]] = []
        current: Dict[str, Any] = {}

        for r in sorted_results:
            text = r.text.strip()
            if not text:
                continue

            match = _TASK_CONDITION_RE.search(text)
            if match:
                if current.get("condition"):
                    _finalize_task(current, tasks, seen_conditions)
                param_jp = match.group(1)
                param = _PARAM_CANONICAL.get(param_jp, param_jp)
                current = {
                    "condition": text,
                    "param": param,
                    "threshold": int(match.group(2)),
                    "comparison": match.group(3),
                    "type": "",
                    "reward": "",
                }
                continue

            task_type = _TASK_TYPE_VARIANTS.get(text)
            if task_type and current.get("condition"):
                current["type"] = task_type
                continue

            if current.get("condition") and (
                "ポイント" in text
                or "Pポイント" in text
                or "ドリンク" in text
                or "ボーナス" in text
            ):
                current["reward"] = text
                _finalize_task(current, tasks, seen_conditions)
                current = {}

        if current.get("condition"):
            _finalize_task(current, tasks, seen_conditions)

        return tasks

    def _close_training_info(self, app: "AppProcessor") -> None:
        """关闭育成情報面板。"""
        btn = find_button(app, ButtonText.CLOSE, fuzz_threshold=70)
        if btn:
            app.device.click(btn.cx, btn.cy)
            sleep(0.5)
            wait_frame_stable(app, timeout=2.0)
            return
        click_relative_point(app, x_ratio=0.05, y_ratio=0.17, label="close-training-info-fallback")
        sleep(0.5)
        wait_frame_stable(app, timeout=2.0)


def _finalize_task(
    task: Dict[str, Any],
    tasks: List[Dict[str, Any]],
    seen: set,
) -> None:
    cond = task.get("condition", "")
    if cond and cond not in seen:
        seen.add(cond)
        tasks.append(dict(task))


def _is_duplicate(text: str, existing: List[str], threshold: float = 0.7) -> bool:
    """简单去重：如果新文本和已有条目的字符重叠率超过 threshold 则视为重复。"""
    if not existing:
        return False
    text_chars = set(text)
    for prev in existing:
        prev_chars = set(prev)
        if not text_chars or not prev_chars:
            continue
        overlap = len(text_chars & prev_chars) / max(len(text_chars), len(prev_chars))
        if overlap > threshold:
            return True
    return False
