from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, List, Set

from src.constants.yolo.labels.producer_Labels import ProducerLabels
from src.core.tasks.producer_challenge.gameplay.common import click_relative_point
from src.utils.logger import logger

from .common import invoke_decision_strategy, ocr_text, resolve_candidate_index
from .decision import build_decision_state, hydrate_card_candidates

if TYPE_CHECKING:
    from src.core.tasks.producer_challenge.context import ProduceContext
    from src.main import AppProcessor


_CARD_LABEL_PRIORITY = (
    ProducerLabels.SKILL_CARD_ACTIVE,
    ProducerLabels.SKILL_CARD_MENTAL,
    ProducerLabels.SKILL_CARD_TRAP,
)

# 空白区域坐标（用于取消卡片选中）
_DESELECT_TAP_Y = 800


@dataclass
class LessonCardCandidate:
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
class LessonStepResult:
    status: str
    candidate: LessonCardCandidate


def collect_lesson_card_candidates(
    app: "AppProcessor",
    ctx: "ProduceContext",
    *,
    position: str,
) -> List[LessonCardCandidate]:
    """收集当前手牌中的技能卡候选列表。

    按 Active > Mental > Trap 优先级排列，同类别按 x 坐标左→右排列。
    """
    cards: list[LessonCardCandidate] = []
    pending_index = ctx.pending_lesson_card_index if position == "lesson_selected" else None

    current_index = 0
    for label in _CARD_LABEL_PRIORITY:
        boxes = sorted(app.latest_results.filter_by_label(label), key=lambda item: item.cx)
        for box in boxes:
            cards.append(
                LessonCardCandidate(
                    index=current_index,
                    label=label,
                    title=ocr_text(box.frame),
                    selected=pending_index == current_index,
                    box=box,
                )
            )
            current_index += 1
    hydrate_card_candidates(app, cards)
    return cards


def decide_lesson_card(
    app: "AppProcessor",
    ctx: "ProduceContext",
    candidates: List[LessonCardCandidate],
    *,
    phase: str,
    position: str,
    skip_indices: Set[int] | None = None,
) -> int:
    """决定要打出哪张卡片，支持跳过不可用的卡片索引。"""
    strategy = ctx.exam_strategy if phase == "exam" and ctx.exam_strategy is not None else ctx.lesson_strategy
    decision_state = build_decision_state(
        app,
        ctx,
        phase=phase,
        position=position,
        candidates=candidates,
        reason=f"{phase}_decision",
    )
    decision = invoke_decision_strategy(
        strategy,
        app,
        ctx,
        candidates,
        decision_state=decision_state,
    )
    if decision is not None:
        idx = resolve_candidate_index(decision, candidates)
        if skip_indices is None or idx not in skip_indices:
            return idx

    # 决策策略返回的卡片不可用，或无决策 → 按优先级顺序尝试
    if ctx.pending_lesson_card_index is not None and 0 <= ctx.pending_lesson_card_index < len(candidates):
        if skip_indices is None or ctx.pending_lesson_card_index not in skip_indices:
            return ctx.pending_lesson_card_index

    # 回退：选第一个不在跳过列表中的卡片
    for c in candidates:
        if skip_indices is None or c.index not in skip_indices:
            return c.index

    # 全部被跳过，返回第一张（兜底）
    return 0


def _verify_card_played(app: "AppProcessor", timeout: float = 1.5) -> bool:
    """验证卡片是否成功打出。

    检查 Skill Card Info 面板是否消失，消失说明卡片已打出。
    """
    deadline = time.monotonic() + timeout
    time.sleep(0.6)
    while time.monotonic() < deadline:
        results = app.latest_results
        if not results.exists_label(ProducerLabels.SKILL_CARD_INFO):
            return True
        time.sleep(0.3)
    return False


def _deselect_card(app: "AppProcessor") -> None:
    """点击空白区域取消卡片选中。"""
    # 使用屏幕中部偏上区域（角色立绘区，不会触发任何UI元素）
    screen_width = 1080  # 标准竖屏宽度
    app.device.click(screen_width // 2, _DESELECT_TAP_Y, el_label="deselect_card")
    time.sleep(0.5)


def execute_lesson_step(
    app: "AppProcessor",
    ctx: "ProduceContext",
    *,
    position: str,
    phase: str = "lesson",
) -> LessonStepResult | None:
    """执行一次 lesson 出牌步骤。

    - lesson_idle:    选中一张卡片（第一次点击），等待进入 selected 状态
    - lesson_selected: 尝试打出卡片（第二次点击），并验证是否成功
      如果卡片不可用（条件未满足），自动取消选中并尝试下一张
    """
    candidates = collect_lesson_card_candidates(app, ctx, position=position)
    if not candidates:
        return None

    # 统一处理 lesson/exam 的 idle/selected 状态
    is_idle = position.endswith("_idle")

    if is_idle:
        # ── 第一次点击：选中卡片 ──
        target_index = decide_lesson_card(app, ctx, candidates, phase=phase, position=position)
        target = candidates[target_index]

        logger.debug(f"lesson: 选中卡片 [{target_index}] {target.label} {target.title!r}")
        app.device.click_element(target.box)

        ctx.pending_lesson_card_index = target.index
        ctx.pending_lesson_card_label = target.title or target.label or target.action_id
        ctx.record_operation(
            "select_lesson_card",
            target=ctx.pending_lesson_card_label,
            details={
                "index": target.index,
                "label": target.label,
                "action_id": target.action_id,
                "db_id": target.db_id,
            },
        )
        return LessonStepResult(status="selected", candidate=target)

    # ── lesson_selected: 第二次点击 → 尝试打出 ──
    tried_indices: Set[int] = set()
    max_retries = len(candidates)

    for attempt in range(max_retries):
        target_index = decide_lesson_card(
            app, ctx, candidates, phase=phase, position=position,
            skip_indices=tried_indices if tried_indices else None,
        )
        target = candidates[target_index]

        logger.debug(
            f"lesson: 尝试打出卡片 [{target_index}] {target.label} {target.title!r}"
            f" (尝试 {attempt + 1}/{max_retries})"
        )
        app.device.click_element(target.box)

        # 验证卡片是否成功打出
        if _verify_card_played(app):
            logger.info(f"lesson: 卡片打出成功 [{target_index}] {target.title!r}")
            ctx.pending_lesson_card_index = None
            ctx.pending_lesson_card_label = ""
            ctx.record_operation(
                "use_lesson_card",
                target=target.title or target.label,
                details={
                    "index": target.index,
                    "label": target.label,
                    "action_id": target.action_id,
                    "db_id": target.db_id,
                },
            )
            return LessonStepResult(status="used", candidate=target)

        # 卡片未打出 → 可能是不可用（条件不满足），取消选中后尝试下一张
        logger.warning(
            f"lesson: 卡片 [{target_index}] {target.title!r} 无法打出，"
            f"取消选中并尝试下一张"
        )
        tried_indices.add(target_index)
        _deselect_card(app)

        # 重新检测画面获取最新候选列表
        time.sleep(0.3)
        candidates = collect_lesson_card_candidates(app, ctx, position="lesson_idle")
        if not candidates:
            logger.warning("lesson: 取消选中后无法检测到手牌")
            return None

    # 所有卡片都尝试过但都无法打出
    logger.warning("lesson: 所有手牌均无法打出")
    ctx.pending_lesson_card_index = None
    ctx.pending_lesson_card_label = ""
    return LessonStepResult(status="all_unplayable", candidate=candidates[0])


# ────────────────────────────────────────────────────────────
# Handler
# ────────────────────────────────────────────────────────────

class LessonHandler:
    """レッスン出牌的 gameplay handler 包装。

    委托给 execute_lesson_step()，并跟踪已打出的回合数。
    通过鸭子类型作为 GameplayHandler 被 dispatcher 导入。
    """

    phase_tag = "lesson"
    priority = 50

    def can_handle(self, app, ctx, phase, position):
        return phase == "lesson"

    def handle(self, app, ctx, phase, position):
        from src.core.tasks.producer_challenge.gameplay.handler_base import HandlerResult

        result = execute_lesson_step(app, ctx, position=position, phase=phase)
        if result is None:
            # 手牌为空 → 回合自动推进，点击画面加速或等待
            logger.info("lesson: 手牌为空（0枚），尝试点击画面推进或跳过")
            skip_boxes = app.latest_results.filter_by_label(ProducerLabels.PC_SKIP)
            if skip_boxes:
                app.device.click_element(skip_boxes.first())
                return HandlerResult.ok("lesson: skip (empty_hand)", sleep_after=1.0)
            # 无跳过按钮时，点击画面中央推进动画
            click_relative_point(app, x_ratio=0.5, y_ratio=0.5, label="lesson-empty-hand-advance")
            return HandlerResult.ok("lesson: 空手牌等待推进", sleep_after=1.0)
        if result.status == "used":
            ctx.lesson_turns_played += 1
            ctx.handler_state["lesson_idle_streak"] = 0
            return HandlerResult.ok(
                f"lesson: 打出 {result.candidate.title!r}",
                sleep_after=1.0,
            )
        if result.status == "all_unplayable":
            # 所有卡片不可用 → 尝试点击跳过按钮
            ctx.handler_state["lesson_idle_streak"] = 0
            skip_boxes = app.latest_results.filter_by_label(ProducerLabels.PC_SKIP)
            if skip_boxes:
                logger.info("lesson: 所有手牌不可用，点击スキップ跳过回合")
                app.device.click_element(skip_boxes.first())
                return HandlerResult.ok("lesson: skip (all_unplayable)", sleep_after=1.0)
            logger.warning("lesson: 所有手牌不可用，无跳过按钮，等待")
            return HandlerResult.ok("lesson: all_unplayable", sleep_after=1.0)

        # status == "selected" — 跟踪连续 idle→selected 未进入 lesson_selected 的次数
        if position.endswith("_idle"):
            streak = ctx.handler_state.get("lesson_idle_streak", 0) + 1
            ctx.handler_state["lesson_idle_streak"] = streak
            if streak >= 4:
                # 连续多次在 idle 状态选择卡片但无法进入 selected → 尝试跳过
                logger.warning(f"lesson: 连续{streak}次无法选中卡片，尝试跳过")
                ctx.handler_state["lesson_idle_streak"] = 0
                skip_boxes = app.latest_results.filter_by_label(ProducerLabels.PC_SKIP)
                if skip_boxes:
                    app.device.click_element(skip_boxes.first())
                    return HandlerResult.ok("lesson: skip (idle_stuck)", sleep_after=1.0)
        else:
            ctx.handler_state["lesson_idle_streak"] = 0

        return HandlerResult.ok(f"lesson: 选中 {result.candidate.title!r}", sleep_after=0.8)

    def __repr__(self):
        return f"<LessonHandler phase={self.phase_tag!r} priority={self.priority}>"
