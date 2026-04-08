"""对话 / コミュ handler。

对话画面包括:
  - 2-3 个可选选项 (Universal Options)
  - 快进按钮 (Fast Forward)
  - 可点击推进的剧情文本

交互模式（经 ADB 实测确认）:
  - 选项需要双击: 第一次点击高亮选中，第二次点击确认。
  - 快进: 单击切换自动推进。
  - 纯剧情文本: 点击任意位置继续。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, List

from src.constants.yolo.labels.baseUI_Labels import BaseUILabels
from src.constants.yolo.labels.producer_Labels import ProducerLabels
from src.core.tasks.producer_challenge.gameplay.common import (
    click_relative_point,
    invoke_decision_strategy,
    ocr_text,
    resolve_candidate_index,
)
from src.core.tasks.producer_challenge.gameplay.decision import (
    build_decision_state,
    hydrate_dialogue_candidates,
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
class DialogueOptionCandidate:
    """对话场景中的一个可选选项。"""
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
class DialogueStepResult:
    status: str  # "selected" | "confirmed" | "fast_forward" | "advanced"
    candidate: DialogueOptionCandidate | None = None


# ────────────────────────────────────────────────────────────
# 采集 / 决策 / 执行
# ────────────────────────────────────────────────────────────

def collect_dialogue_option_candidates(
    app: "AppProcessor",
    ctx: "ProduceContext",
    *,
    position: str,
) -> List[DialogueOptionCandidate]:
    """采集屏幕上的对话选项，按从上到下排序。"""
    options = sorted(
        app.latest_results.filter_by_label(ProducerLabels.UNIVERSAL_OPTIONS),
        key=lambda o: o.cy,
    )
    pending = ctx.pending_dialogue_option_index if position == "dialogue_options" else None
    candidates = [
        DialogueOptionCandidate(
            index=idx,
            title=ocr_text(box.frame),
            selected=pending == idx,
            box=box,
        )
        for idx, box in enumerate(options)
    ]
    hydrate_dialogue_candidates(candidates)
    return candidates


def decide_dialogue_option(
    app: "AppProcessor",
    ctx: "ProduceContext",
    candidates: List[DialogueOptionCandidate],
    *,
    position: str,
) -> int:
    """选择哪个对话选项（策略回调或默认选第一个）。"""
    decision_state = build_decision_state(
        app,
        ctx,
        phase="dialogue",
        position=position,
        candidates=candidates,
        reason="dialogue_decision",
    )
    decision = invoke_decision_strategy(
        ctx.dialogue_strategy,
        app,
        ctx,
        candidates,
        decision_state=decision_state,
    )
    if decision is not None:
        return resolve_candidate_index(decision, candidates)

    if (
        ctx.pending_dialogue_option_index is not None
        and 0 <= ctx.pending_dialogue_option_index < len(candidates)
    ):
        return ctx.pending_dialogue_option_index

    return 0


def _get_dialogue_stuck_count(ctx: "ProduceContext") -> int:
    """获取对话卡住计数器（同一选项连续确认但画面未变化）。"""
    return ctx.handler_state.get("dialogue_stuck_count", 0)


def _update_dialogue_stuck(ctx: "ProduceContext", option_index: int) -> int:
    """更新对话卡住状态，返回当前卡住次数。

    如果连续确认同一选项，计数递增；否则重置。
    """
    last = ctx.handler_state.get("dialogue_stuck_last_option", -1)
    if option_index == last:
        count = ctx.handler_state.get("dialogue_stuck_count", 0) + 1
    else:
        count = 0
    ctx.handler_state["dialogue_stuck_count"] = count
    ctx.handler_state["dialogue_stuck_last_option"] = option_index
    return count


def _reset_dialogue_stuck(ctx: "ProduceContext") -> None:
    """重置对话卡住计数。"""
    ctx.handler_state.pop("dialogue_stuck_count", None)
    ctx.handler_state.pop("dialogue_stuck_last_option", None)
    ctx.handler_state.pop("dialogue_skip_indices", None)


def execute_dialogue_step(
    app: "AppProcessor",
    ctx: "ProduceContext",
    *,
    position: str,
) -> DialogueStepResult | None:
    """执行一步对话交互。

    - dialogue_options + 有待确认: 确认已选中选项（第 2 次点击）
    - dialogue_options + 无待确认: 选中一个选项（第 1 次点击）
    - dialogue_continue: 快进或点击推进

    卡住检测:
      当某个选项被连续确认 STUCK_THRESHOLD 次后（例如 Pポイント不足
      导致选项无法执行），自动跳过该选项尝试下一个。
    """
    STUCK_THRESHOLD = 3  # 同一选项连续确认N次视为卡住

    candidates = collect_dialogue_option_candidates(app, ctx, position=position)

    if candidates:
        # ── 第二次点击: 确认已选中选项 ──
        if ctx.pending_dialogue_option_index is not None:
            target_index = ctx.pending_dialogue_option_index
            if 0 <= target_index < len(candidates):
                target = candidates[target_index]
                # 检测卡住: 连续确认同一选项
                stuck_count = _update_dialogue_stuck(ctx, target_index)
                if stuck_count >= STUCK_THRESHOLD:
                    # 该选项可能无法执行（如P点不足），加入跳过列表
                    skip_set: set = ctx.handler_state.setdefault("dialogue_skip_indices", set())
                    skip_set.add(target_index)
                    logger.warning(
                        f"dialogue: 选项 {target_index} {target.title!r} "
                        f"连续确认 {stuck_count} 次未生效，跳过此选项"
                    )
                    ctx.clear_dialogue_pending()
                    # 不 return — 直接 fall through 到下面选择新选项
                else:
                    app.device.click_element(target.box)
                    ctx.record_operation(
                        "confirm_dialogue_option",
                        target=target.title or f"option_{target.index + 1}",
                        details={"index": target.index},
                    )
                    ctx.dialogue_choices_made += 1
                    ctx.clear_dialogue_pending()
                    return DialogueStepResult(status="confirmed", candidate=target)
            else:
                # 待确认索引超出范围 — 重置并重新选择
                ctx.clear_dialogue_pending()

        # ── 第一次点击: 选中 ──
        skip_set = ctx.handler_state.get("dialogue_skip_indices", set())
        available = [c for c in candidates if c.index not in skip_set]
        if not available:
            # 所有选项都被跳过 — 清除跳过列表，从最后一个选项开始
            logger.warning("dialogue: 所有选项均被跳过，重置跳过列表并选择最后一个选项")
            _reset_dialogue_stuck(ctx)
            available = candidates

        target_index = decide_dialogue_option(app, ctx, available, position=position)
        target = available[target_index]
        app.device.click_element(target.box)
        ctx.pending_dialogue_option_index = target.index
        ctx.record_operation(
            "select_dialogue_option",
            target=target.title or f"option_{target.index + 1}",
            details={
                "index": target.index,
                "action_id": target.action_id,
                "db_id": target.db_id,
            },
        )
        logger.debug(f"dialogue: selected option {target.index} {target.title!r}")
        return DialogueStepResult(status="selected", candidate=target)

    # ── 没有选项可见 — 快进或点击推进 ──
    # 选项消失表示对话已推进，重置卡住状态
    _reset_dialogue_stuck(ctx)

    # 纯剧情对话（非行程上下文）— 可以使用快进
    ff_buttons = app.latest_results.filter_by_label(BaseUILabels.PLOT_FAST_FORWARD_BUTTON)
    if ff_buttons:
        app.device.click_element(ff_buttons.first())
        logger.debug("dialogue: fast forward")
        return DialogueStepResult(status="fast_forward")
    # Skip 按钮（おでかけ剧情等未读コミュ）— 直接跳过
    skip_buttons = app.latest_results.filter_by_label(BaseUILabels.SKIP_BUTTON)
    if skip_buttons:
        app.device.click_element(skip_buttons.first())
        logger.debug("dialogue: skip button")
        return DialogueStepResult(status="skipped")
    click_relative_point(app, x_ratio=0.5, y_ratio=0.82, label="dialogue-advance")
    return DialogueStepResult(status="advanced")


# ────────────────────────────────────────────────────────────
# Handler
# ────────────────────────────────────────────────────────────

class DialogueHandler(GameplayHandler):
    """对话 / コミュ画面处理。"""

    phase_tag = "dialogue"
    priority = 50

    def can_handle(self, app, ctx, phase, position):
        return phase == "dialogue"

    def handle(self, app, ctx, phase, position):
        result = execute_dialogue_step(app, ctx, position=position)
        if result is None:
            return HandlerResult.no_action("no dialogue elements")
        return HandlerResult.ok(f"dialogue {result.status}", sleep_after=0.6)
