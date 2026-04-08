"""P饮料选择 handler。

P饮料可在以下场景选择:
  - 周间奖励发放（独立的 p_drink 阶段）
  - レッスン/試験内底栏（由 lesson handler 单独处理）

交互模式（经 ADB 实测确认）:
  - 第一次点击饮料: 橙色选框高亮，底部受け取る按钮变为可用。
  - 第二次点击确认按钮: 接受饮料并推进。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, List

from src.constants.yolo.labels.baseUI_Labels import BaseUILabels
from src.constants.yolo.labels.producer_Labels import ProducerLabels
from src.core.tasks.producer_challenge.gameplay.common import (
    invoke_decision_strategy,
    ocr_text,
    resolve_candidate_index,
)
from src.core.tasks.producer_challenge.gameplay.decision import (
    build_decision_state,
    hydrate_p_drink_candidates,
)
from src.core.tasks.producer_challenge.gameplay.handler_base import (
    GameplayHandler,
    HandlerResult,
)
from src.utils.logger import logger

if TYPE_CHECKING:
    from src.core.tasks.producer_challenge.context import ProduceContext
    from src.main import AppProcessor


# ────────────────────────────────────────────────────────────
# 数据类型
# ────────────────────────────────────────────────────────────

@dataclass
class PDrinkCandidate:
    index: int
    title: str
    selected: bool
    box: Any = field(repr=False, default=None)
    action_id: str = ""
    db_id: str = ""
    source: str = ""
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PDrinkStepResult:
    status: str  # "selected" | "confirmed"
    candidate: PDrinkCandidate | None = None


# ────────────────────────────────────────────────────────────
# 采集 / 决策 / 执行
# ────────────────────────────────────────────────────────────

def collect_p_drink_candidates(
    app: "AppProcessor",
    ctx: "ProduceContext",
    *,
    position: str,
) -> List[PDrinkCandidate]:
    """采集屏幕上的 P 饮料项（中央区域，非底栏）。"""
    frame_height = (
        app.latest_frame.shape[0]
        if getattr(app, "latest_frame", None) is not None
        else 2340
    )
    drinks = sorted(
        (d for d in app.latest_results.filter_by_label(BaseUILabels.P_DRINK)
         if d.cy < frame_height * 0.85),
        key=lambda item: item.cx,
    )
    pending = ctx.pending_p_drink_index if position == "p_drink_selected" else None
    candidates = [
        PDrinkCandidate(
            index=idx,
            title=ocr_text(box.frame),
            selected=pending == idx,
            box=box,
        )
        for idx, box in enumerate(drinks)
    ]
    hydrate_p_drink_candidates(candidates)
    return candidates


def decide_p_drink(
    app: "AppProcessor",
    ctx: "ProduceContext",
    candidates: List[PDrinkCandidate],
    *,
    position: str,
) -> int:
    decision_state = build_decision_state(
        app,
        ctx,
        phase="p_drink",
        position=position,
        candidates=candidates,
        reason="p_drink_decision",
    )
    decision = invoke_decision_strategy(
        ctx.p_drink_strategy,
        app,
        ctx,
        candidates,
        decision_state=decision_state,
    )
    if decision is not None:
        return resolve_candidate_index(decision, candidates)

    if (
        ctx.pending_p_drink_index is not None
        and 0 <= ctx.pending_p_drink_index < len(candidates)
    ):
        return ctx.pending_p_drink_index

    return 0


def _click_any_bottom_button(app: "AppProcessor") -> bool:
    """点击P饮料面板底部的按钮（不区分 Confirm/Disable 标签）。

    YOLO 可能将活跃的橙色「受け取らない」按钮误分类为 Disable Button，
    因此需要同时检查 Confirm 和 Disable 标签。
    """
    results = app.latest_results
    # 收集所有可能的按钮
    candidates = []
    for label in (ProducerLabels.CONFIRM_BUTTON, ProducerLabels.DISABLE_BUTTON, BaseUILabels.BUTTON):
        for box in results.filter_by_label(label):
            candidates.append(box)
    if candidates:
        # 点击最靠下的按钮
        target = max(candidates, key=lambda b: b.cy)
        app.device.click_element(target)
        return True
    return False


def _verify_p_drink_advanced(app: "AppProcessor", timeout: float = 1.5) -> bool:
    """验证 P 饮料确认后画面是否推进。

    检查是否仍停留在 P_DRINK 页面（仍能看到中央区域的 P Drink 标签）。
    """
    import time
    deadline = time.monotonic() + timeout
    time.sleep(0.6)
    frame_height = (
        app.latest_frame.shape[0]
        if getattr(app, "latest_frame", None) is not None
        else 2340
    )
    while time.monotonic() < deadline:
        results = app.latest_results
        # 检查中央 P Drink 是否消失（底栏饮料不算）
        central_drinks = [
            d for d in results.filter_by_label(ProducerLabels.P_DRINK)
            if d.cy < frame_height * 0.85
        ]
        if not central_drinks:
            return True
        # 也检查是否弹出了modal（报酬スキップ确认）
        if results.exists_label(ProducerLabels.MODAL_HEADER):
            return True
        time.sleep(0.3)
    return False


def _try_skip_p_drink(app: "AppProcessor", *, checkbox_already_checked: bool = False) -> bool:
    """P饮料所持上限时，点击「受け取らない」按钮跳过领取。

    流程：勾选「受け取らない」复选框 → 点击按钮 → 处理子弹窗。
    如果 checkbox_already_checked=True，则跳过复选框点击步骤，直接点按钮。
    """
    import time

    if not checkbox_already_checked:
        # 查找「受け取らない」复选框
        checkbox_boxes = list(app.latest_results.filter_by_label(BaseUILabels.CHECKBOX))
        if not checkbox_boxes:
            logger.debug("p_drink: 未找到复选框，无法跳过")
            return False

        logger.info("p_drink: P饮料所持上限，点击「受け取らない」跳过领取")
        app.device.click_element(checkbox_boxes[0])
        time.sleep(1.2)

    # 点击底部按钮（可能是 Confirm 或被误分类为 Disable 的橙色按钮）
    _click_any_bottom_button(app)
    time.sleep(1.5)

    # 处理「報酬スキップ」确认子弹窗
    results = app.latest_results
    modal_headers = list(results.filter_by_label(ProducerLabels.MODAL_HEADER))
    if modal_headers:
        logger.info("p_drink: 检测到報酬スキップ确认弹窗，点击确认")
        _click_any_bottom_button(app)
        time.sleep(1.0)
    return True


def execute_p_drink_step(
    app: "AppProcessor",
    ctx: "ProduceContext",
    *,
    position: str,
) -> PDrinkStepResult | None:
    """执行一步 P 饮料交互。

    - p_drink_selected: 点击确认按钮（第 2 步），支持所持上限跳过
    - p_drink_idle: 选择一个饮料（第 1 步），检测所持上限自动跳过
    """
    if position == "p_drink_selected":
        _click_any_bottom_button(app)

        # 验证画面是否推进
        if _verify_p_drink_advanced(app):
            ctx.record_operation(
                "confirm_p_drink",
                target=ctx.pending_p_drink_label or "p_drink",
                details={"index": ctx.pending_p_drink_index},
            )
            ctx.clear_p_drink_pending()
            return PDrinkStepResult(status="confirmed")

        # 画面未推进 → 可能是P饮料所持上限，尝试跳过
        logger.warning("p_drink: 确认按钮点击后画面未推进，尝试跳过领取")
        if _try_skip_p_drink(app):
            ctx.clear_p_drink_pending()
            return PDrinkStepResult(status="skipped")

        return None

    # idle 状态：检测是否为所持上限场景（Disable按钮 + Checkbox可见）
    has_disable = app.latest_results.exists_label(ProducerLabels.DISABLE_BUTTON)
    has_checkbox = app.latest_results.exists_label(BaseUILabels.CHECKBOX)
    if has_disable and has_checkbox:
        # 追踪连续跳过尝试次数，避免checkbox来回切换
        skip_attempts = ctx.handler_state.get("p_drink_skip_attempts", 0)
        # 偶数次点击checkbox（第0、2、4…次），奇数次跳过checkbox（第1、3…次已勾选）
        checkbox_already_checked = (skip_attempts % 2) == 1
        logger.info(
            "p_drink: idle 检测到 Disable + Checkbox → 所持上限，"
            f"尝试跳过(第{skip_attempts + 1}次, checkbox_checked={checkbox_already_checked})"
        )
        ctx.handler_state["p_drink_skip_attempts"] = skip_attempts + 1
        if _try_skip_p_drink(app, checkbox_already_checked=checkbox_already_checked):
            ctx.handler_state["p_drink_skip_attempts"] = 0
            ctx.clear_p_drink_pending()
            return PDrinkStepResult(status="skipped")

    candidates = collect_p_drink_candidates(app, ctx, position=position)
    if not candidates:
        return None

    target_index = decide_p_drink(app, ctx, candidates, position=position)
    target = candidates[target_index]
    app.device.click_element(target.box)
    ctx.pending_p_drink_index = target.index
    ctx.pending_p_drink_label = target.title or target.action_id or f"p_drink_{target.index + 1}"
    ctx.record_operation(
        "select_p_drink",
        target=ctx.pending_p_drink_label,
        details={
            "index": target.index,
            "action_id": target.action_id,
            "db_id": target.db_id,
        },
    )
    logger.debug(f"p_drink: selected {target.index} {target.title!r}")
    return PDrinkStepResult(status="selected", candidate=target)


# ────────────────────────────────────────────────────────────
# Handler
# ────────────────────────────────────────────────────────────

class PDrinkHandler(GameplayHandler):
    """P饮料选择画面处理。"""

    phase_tag = "p_drink"
    priority = 50

    def can_handle(self, app, ctx, phase, position):
        return phase == "p_drink"

    def handle(self, app, ctx, phase, position):
        result = execute_p_drink_step(app, ctx, position=position)
        if result is None:
            return HandlerResult.no_action("no p_drink elements")
        sleep_time = 1.0 if result.status in ("confirmed", "skipped") else 0.8
        return HandlerResult.ok(f"p_drink {result.status}", sleep_after=sleep_time)
