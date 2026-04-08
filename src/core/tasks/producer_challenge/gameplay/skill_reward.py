"""技能卡奖励选择 handler。

技能卡奖励画面出现在:
  - 活動支給（活动支给）
  - レッスン完成后
  - 各种事件奖励

画面显示 1-3 张可选技能卡，选中后确认按钮激活。

交互模式（经 ADB 实测确认）:
  - 第一次点击卡片: 高亮选中，确认按钮变为可用。
  - 第二次点击确认按钮: 接受卡片并推进。
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
    hydrate_card_candidates,
)
from src.core.tasks.producer_challenge.gameplay.handler_base import (
    GameplayHandler,
    HandlerResult,
)
from src.utils.logger import logger

if TYPE_CHECKING:
    from src.core.tasks.producer_challenge.context import ProduceContext
    from src.main import AppProcessor

_REWARD_CARD_LABELS = (
    BaseUILabels.SKILL_CARD_ACTIVE,
    BaseUILabels.SKILL_CARD_MENTAL,
    BaseUILabels.SKILL_CARD_TRAP,
    ProducerLabels.SKILL_CARD_INFO,
)


# ────────────────────────────────────────────────────────────
# 数据类型
# ────────────────────────────────────────────────────────────

@dataclass
class SkillRewardCandidate:
    index: int
    label: str
    title: str
    selected: bool
    box: Any = field(repr=False, default=None)
    action_id: str = ""
    db_id: str = ""
    source: str = ""
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillRewardStepResult:
    status: str  # "selected" | "confirmed"
    candidate: SkillRewardCandidate | None = None


# ────────────────────────────────────────────────────────────
# 采集 / 决策 / 执行
# ────────────────────────────────────────────────────────────

def collect_skill_reward_candidates(
    app: "AppProcessor",
    ctx: "ProduceContext",
    *,
    position: str,
) -> List[SkillRewardCandidate]:
    """采集屏幕上的技能卡奖励选项，按左到右排序。"""
    boxes: list[tuple[str, Any]] = []
    for label in _REWARD_CARD_LABELS:
        for box in app.latest_results.filter_by_label(label):
            boxes.append((label, box))
    boxes.sort(key=lambda pair: pair[1].cx)

    pending = ctx.pending_skill_reward_index if position == "skill_reward_selected" else None
    candidates = [
        SkillRewardCandidate(
            index=idx,
            label=label,
            title=ocr_text(box.frame),
            selected=pending == idx,
            box=box,
        )
        for idx, (label, box) in enumerate(boxes)
    ]
    hydrate_card_candidates(app, candidates)
    return candidates


def decide_skill_reward(
    app: "AppProcessor",
    ctx: "ProduceContext",
    candidates: List[SkillRewardCandidate],
    *,
    position: str,
) -> int:
    decision_state = build_decision_state(
        app,
        ctx,
        phase="skill_reward",
        position=position,
        candidates=candidates,
        reason="skill_reward_decision",
    )
    decision = invoke_decision_strategy(
        ctx.skill_reward_strategy,
        app,
        ctx,
        candidates,
        decision_state=decision_state,
    )
    if decision is not None:
        return resolve_candidate_index(decision, candidates)

    if (
        ctx.pending_skill_reward_index is not None
        and 0 <= ctx.pending_skill_reward_index < len(candidates)
    ):
        return ctx.pending_skill_reward_index

    return 0


def _click_confirm_button(app: "AppProcessor") -> bool:
    """点击激活的确认按钮。"""
    confirm_boxes = app.latest_results.filter_by_label(ProducerLabels.CONFIRM_BUTTON)
    if confirm_boxes:
        app.device.click_element(confirm_boxes.first())
        return True
    buttons = app.latest_results.filter_by_label(BaseUILabels.BUTTON)
    if buttons:
        app.device.click_element(max(buttons, key=lambda b: b.cy))
        return True
    return False


def execute_skill_reward_step(
    app: "AppProcessor",
    ctx: "ProduceContext",
    *,
    position: str,
) -> SkillRewardStepResult | None:
    """执行一步技能卡奖励交互。

    - skill_reward_selected: 点击确认按钮（第 2 步）
    - skill_reward_idle: 选择一张卡（第 1 步）
    """
    if position == "skill_reward_selected":
        # 如果没有记录的待确认选择，先选一张卡再确认
        if ctx.pending_skill_reward_index is None:
            logger.debug("skill_reward: 无待确认卡片，先执行选卡流程")
            candidates = collect_skill_reward_candidates(app, ctx, position=position)
            if candidates:
                target_index = decide_skill_reward(app, ctx, candidates, position=position)
                target = candidates[target_index]
                app.device.click_element(target.box)
                ctx.pending_skill_reward_index = target.index
                ctx.pending_skill_reward_label = target.title or target.label or target.action_id
                logger.debug(f"skill_reward: 先选中卡片 {target.index} {target.title!r}")
                return SkillRewardStepResult(status="selected", candidate=target)

        if not _click_confirm_button(app):
            return None
        logger.debug(f"skill_reward: 确认选择 index={ctx.pending_skill_reward_index}")
        ctx.record_operation(
            "confirm_skill_reward",
            target=ctx.pending_skill_reward_label or "skill_reward",
            details={"index": ctx.pending_skill_reward_index},
        )
        ctx.clear_skill_reward_pending()
        return SkillRewardStepResult(status="confirmed")

    candidates = collect_skill_reward_candidates(app, ctx, position=position)
    if not candidates:
        return None

    target_index = decide_skill_reward(app, ctx, candidates, position=position)
    target = candidates[target_index]
    app.device.click_element(target.box)
    ctx.pending_skill_reward_index = target.index
    ctx.pending_skill_reward_label = target.title or target.label or target.action_id
    ctx.record_operation(
        "select_skill_reward",
        target=ctx.pending_skill_reward_label,
        details={
            "index": target.index,
            "label": target.label,
            "action_id": target.action_id,
            "db_id": target.db_id,
        },
    )
    logger.debug(f"skill_reward: selected {target.index} {target.title!r}")
    return SkillRewardStepResult(status="selected", candidate=target)


# ────────────────────────────────────────────────────────────
# Handler
# ────────────────────────────────────────────────────────────

class SkillRewardHandler(GameplayHandler):
    """技能卡奖励选择画面处理。"""

    phase_tag = "skill_reward"
    priority = 50

    def can_handle(self, app, ctx, phase, position):
        return phase == "skill_reward"

    def handle(self, app, ctx, phase, position):
        # 连续 idle 状态选择卡片但无法进入 selected → 可能是展示画面，点击空白推进
        if position == "skill_reward_idle":
            streak = ctx.handler_state.get("skill_reward_idle_streak", 0) + 1
            ctx.handler_state["skill_reward_idle_streak"] = streak
            ctx.handler_state["skill_reward_selected_streak"] = 0
            if streak >= 3:
                logger.info(f"skill_reward: 连续{streak}次 idle，判定为展示画面，点击空白推进")
                ctx.handler_state["skill_reward_idle_streak"] = 0
                from .common import click_relative_point
                # 点击对话框区域（卡片下方），避免点击卡片本身触发详情
                click_relative_point(app, x_ratio=0.5, y_ratio=0.88, label="skill_reward_advance")
                return HandlerResult.ok("skill_reward advance (display)", sleep_after=1.0)
        elif position == "skill_reward_selected":
            streak = ctx.handler_state.get("skill_reward_selected_streak", 0) + 1
            ctx.handler_state["skill_reward_selected_streak"] = streak
            ctx.handler_state["skill_reward_idle_streak"] = 0
            # 连续3次确认都无进展 → 强制重新选卡
            if streak >= 3:
                logger.info(f"skill_reward: 连续{streak}次 selected 无进展，强制重新选卡")
                ctx.handler_state["skill_reward_selected_streak"] = 0
                ctx.pending_skill_reward_index = None  # 重置以触发重新选卡
        else:
            ctx.handler_state["skill_reward_idle_streak"] = 0
            ctx.handler_state["skill_reward_selected_streak"] = 0

        result = execute_skill_reward_step(app, ctx, position=position)
        if result is None:
            return HandlerResult.no_action("no skill_reward elements")
        return HandlerResult.ok(f"skill_reward {result.status}", sleep_after=0.8)
