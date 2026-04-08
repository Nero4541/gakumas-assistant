"""相談（咨询交换页）handler。

基于 `producer_plan.md` 中的拆分思路，把相談视为可编排的多子动作流程：
  - 交换商品（技能卡 / P饮料 / 其他道具）
  - 技能卡强化
  - 技能卡删除
  - 退出相談

当前优先补齐「候选项规范化 + 无状态决策桥 + 強化骨架」。
默认兜底策略保持保守：
  - 优先只自动进入一次强化
  - 强化页优先选择目标卡，再确认
  - 不默认执行删除
后续可通过 ``ctx.consult_strategy`` 完全覆盖。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, List

from src.constants.game.producer_gameplay import (
    CONSULT_SELECTION_POSITIONS,
    GameplayPhase,
    GameplayPosition,
)
from src.constants.yolo.labels.baseUI_Labels import BaseUILabels
from src.constants.yolo.labels.producer_Labels import ProducerLabels
from src.constants.game.text.button_text import ButtonText
from src.constants.game.text.general_text import GeneralText
from src.constants.game.text.produce_text import ProduceText
from src.core.tasks.producer_challenge.gameplay.common import (
    invoke_decision_strategy,
    ocr_text,
    resolve_candidate_index,
)
from src.core.tasks.producer_challenge.gameplay.decision import (
    build_decision_state,
    hydrate_consult_candidates,
)
from src.core.tasks.producer_challenge.gameplay.handler_base import (
    GameplayHandler,
    HandlerResult,
)
from src.utils.logger import logger

if TYPE_CHECKING:
    from src.core.tasks.producer_challenge.context import ProduceContext
    from src.main import AppProcessor

_CONSULT_CARD_LABELS = (
    ProducerLabels.SKILL_CARD_ACTIVE,
    ProducerLabels.SKILL_CARD_MENTAL,
    ProducerLabels.SKILL_CARD_TRAP,
    ProducerLabels.SKILL_CARD_INFO,
)


def _consult_mode_action_prefix(mode: str) -> str:
    """将相談子模式映射到统一动作前缀。

    说明：
    - `enhancement` 与 `remove` 共享同一套“进入子流程 -> 选卡 -> 预览 -> 确认 -> 返回”骨架。
    - 区别只体现在动作名前缀与按钮文案，不额外复制一套状态机。
    """
    return "remove" if mode == "remove" else "enhancement"


def _consult_target_kind_for_mode(mode: str) -> str:
    return "remove_target" if mode == "remove" else "enhancement_target"


def _consult_confirm_kind_for_mode(mode: str) -> str:
    return "confirm_remove" if mode == "remove" else "confirm_enhancement"


def _consult_select_operation_for_mode(mode: str) -> str:
    prefix = _consult_mode_action_prefix(mode)
    return f"consult_select_{prefix}_target"


def _consult_confirm_operation_for_mode(mode: str) -> str:
    prefix = _consult_mode_action_prefix(mode)
    return f"consult_confirm_{prefix}"


@dataclass
class ConsultActionCandidate:
    """相談页面上的一个可执行候选项。"""

    index: int
    kind: str
    title: str
    box: Any = field(repr=False, default=None)
    selected: bool = False
    action_id: str = ""
    db_id: str = ""
    source: str = ""
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


def _sorted_boxes(boxes) -> list:
    return sorted(boxes, key=lambda item: (item.cy, item.cx))


def _consult_subflow_mode(ctx: "ProduceContext") -> str:
    mode = str(ctx.handler_state.get("consult_pending_mode", "") or "")
    if mode in {"enhancement", "remove"}:
        return mode
    last_subaction = str(ctx.handler_state.get("consult_last_subaction", "") or "")
    if "remove" in last_subaction:
        return "remove"
    return "enhancement"


def detect_consult_actions(
    app: "AppProcessor",
    ctx: "ProduceContext",
    *,
    position: str,
) -> List[ConsultActionCandidate]:
    """根据相談子页面位置收集候选项。"""
    candidates: list[ConsultActionCandidate] = []

    if position == GameplayPosition.CONSULT_EXCHANGE:
        for box in _sorted_boxes(app.latest_results.filter_by_label(ProducerLabels.CARD_ITEM_EXCHANGE)):
            candidates.append(
                ConsultActionCandidate(
                    index=len(candidates),
                    kind="exchange",
                    title=ocr_text(box.frame),
                    box=box,
                )
            )
        for label, kind, fallback_title in (
            (ProducerLabels.PC_SKILL_CARD_ENHANCEMENT, "enhance", GeneralText.ENHANCE),
            (ProducerLabels.PC_SKILL_CARD_REMOVE, "delete", ProduceText.SKILL_CARD_REMOVE),
        ):
            for box in _sorted_boxes(app.latest_results.filter_by_label(label)):
                candidates.append(
                    ConsultActionCandidate(
                        index=len(candidates),
                        kind=kind,
                        title=ocr_text(box.frame) or fallback_title,
                        box=box,
                    )
                )
        # 收集退出按钮（Close Button）
        for box in app.latest_results.filter_by_label(ProducerLabels.CLOSE_BUTTON):
            candidates.append(
                ConsultActionCandidate(
                    index=len(candidates),
                    kind="exit",
                    title=ButtonText.EXIT,
                    box=box,
                )
            )
    elif position in CONSULT_SELECTION_POSITIONS:
        subflow_mode = _consult_subflow_mode(ctx)
        pending_target = str(ctx.handler_state.get("consult_enhancement_target_label", "") or "")
        target_kind = _consult_target_kind_for_mode(subflow_mode)
        for label in _CONSULT_CARD_LABELS:
            for box in _sorted_boxes(app.latest_results.filter_by_label(label)):
                title = ocr_text(box.frame)
                candidates.append(
                    ConsultActionCandidate(
                        index=len(candidates),
                        kind=target_kind,
                        title=title,
                        selected=bool(pending_target and pending_target == title),
                        box=box,
                    )
                )

        confirm_boxes = list(app.latest_results.filter_by_label(ProducerLabels.CONFIRM_BUTTON))
        if not confirm_boxes:
            confirm_boxes = list(app.latest_results.filter_by_label(BaseUILabels.BUTTON))
        if confirm_boxes:
            confirm_box = max(confirm_boxes, key=lambda item: item.cy)
            candidates.append(
                ConsultActionCandidate(
                    index=len(candidates),
                    kind=_consult_confirm_kind_for_mode(subflow_mode),
                    title=ocr_text(confirm_box.frame) or (
                        ProduceText.SKILL_CARD_REMOVE if subflow_mode == "remove" else ProduceText.ENHANCE_CONFIRM
                    ),
                    box=confirm_box,
                )
            )

        cancel_boxes = list(app.latest_results.filter_by_label(ProducerLabels.CANCEL_BUTTON))
        if cancel_boxes:
            cancel_box = max(cancel_boxes, key=lambda item: item.cy)
            candidates.append(
                ConsultActionCandidate(
                    index=len(candidates),
                    kind="exit",
                    title=ocr_text(cancel_box.frame) or ButtonText.EXIT,
                    box=cancel_box,
                )
            )

    hydrate_consult_candidates(app, candidates)
    return candidates


def decide_consult_action(
    app: "AppProcessor",
    ctx: "ProduceContext",
    candidates: List[ConsultActionCandidate],
    *,
    position: str,
) -> int:
    decision_state = build_decision_state(
        app,
        ctx,
        phase=GameplayPhase.CONSULT,
        position=position,
        candidates=candidates,
        reason="consult_decision",
    )
    decision = invoke_decision_strategy(
        ctx.consult_strategy,
        app,
        ctx,
        candidates,
        decision_state=decision_state,
    )
    if decision is not None:
        return resolve_candidate_index(decision, candidates)

    if position == GameplayPosition.CONSULT_EXCHANGE:
        # 卡顿检测：如果连续多次停留在 consult_exchange，直接退出
        exchange_stuck = ctx.handler_state.get("consult_exchange_stuck", 0) + 1
        ctx.handler_state["consult_exchange_stuck"] = exchange_stuck
        CONSULT_STUCK_THRESHOLD = 5

        if exchange_stuck <= CONSULT_STUCK_THRESHOLD:
            if not ctx.handler_state.get("consult_auto_used_enhancement"):
                for idx, candidate in enumerate(candidates):
                    if candidate.kind == "enhance":
                        return idx
        else:
            # 连续卡顿超过阈值，强制标记已使用过强化，后续直接退出
            logger.warning(
                "consult: exchange页面卡顿 {} 次，跳过强化直接退出",
                exchange_stuck,
            )
            ctx.handler_state["consult_auto_used_enhancement"] = True

        # 强化完成后，优先退出相談页面
        for idx, candidate in enumerate(candidates):
            if candidate.kind == "exit":
                return idx
        for idx, candidate in enumerate(candidates):
            if candidate.kind == "exchange":
                return idx
        for idx, candidate in enumerate(candidates):
            if candidate.kind == "enhance":
                return idx
        return 0

    subflow_mode = _consult_subflow_mode(ctx)
    pending_target = ctx.handler_state.get("consult_enhancement_target")
    target_kind = _consult_target_kind_for_mode(subflow_mode)
    confirm_kind = _consult_confirm_kind_for_mode(subflow_mode)
    if pending_target:
        for idx, candidate in enumerate(candidates):
            if candidate.kind == confirm_kind:
                return idx
    for idx, candidate in enumerate(candidates):
        if candidate.kind == target_kind:
            return idx
    for idx, candidate in enumerate(candidates):
        if candidate.kind == confirm_kind:
            return idx
    for idx, candidate in enumerate(candidates):
        if candidate.kind == "exit":
            return idx
    return 0


def execute_consult_step(
    app: "AppProcessor",
    ctx: "ProduceContext",
    *,
    position: str,
) -> ConsultActionCandidate | None:
    # 非 exchange 页面时重置卡顿计数
    if position != GameplayPosition.CONSULT_EXCHANGE:
        ctx.handler_state.pop("consult_exchange_stuck", None)

    candidates = detect_consult_actions(app, ctx, position=position)
    if not candidates:
        return None

    target_index = decide_consult_action(app, ctx, candidates, position=position)
    target = candidates[target_index]
    app.device.click_element(target.box)

    if target.kind in {"enhancement_target", "remove_target"}:
        pending_mode = "remove" if target.kind == "remove_target" else "enhancement"
        operation_name = _consult_select_operation_for_mode(pending_mode)
        ctx.handler_state["consult_enhancement_target"] = target.db_id or target.action_id or str(target.index)
        ctx.handler_state["consult_enhancement_target_label"] = target.title or target.action_id
        ctx.handler_state["consult_pending_mode"] = pending_mode
        ctx.handler_state["consult_last_subaction"] = operation_name.removeprefix("consult_")
        ctx.record_operation(
            operation_name,
            target=target.title or target.action_id,
            details={
                "index": target.index,
                "action_id": target.action_id,
                "db_id": target.db_id,
            },
        )
        return target

    if target.kind == "confirm_enhancement":
        ctx.handler_state["consult_auto_used_enhancement"] = True
        ctx.handler_state["consult_last_subaction"] = "confirm_enhancement"
        ctx.record_operation(
            _consult_confirm_operation_for_mode("enhancement"),
            target=ctx.handler_state.get("consult_enhancement_target_label", "") or target.title or target.action_id,
            details={
                "index": target.index,
                "action_id": target.action_id,
                "db_id": target.db_id,
            },
        )
        return target

    if target.kind == "confirm_remove":
        ctx.handler_state["consult_last_subaction"] = "confirm_remove"
        ctx.record_operation(
            _consult_confirm_operation_for_mode("remove"),
            target=ctx.handler_state.get("consult_enhancement_target_label", "") or target.title or target.action_id,
            details={
                "index": target.index,
                "action_id": target.action_id,
                "db_id": target.db_id,
            },
        )
        ctx.clear_consult_pending()
        return target

    if target.kind == "exit":
        ctx.clear_consult_pending()
        ctx.record_operation(
            "consult_exit",
            target=target.title or target.action_id or "consult_exit",
            details={
                "index": target.index,
                "action_id": target.action_id,
            },
        )
        return target

    if target.kind == "enhance":
        ctx.handler_state["consult_pending_mode"] = "enhancement"
        ctx.handler_state["consult_last_subaction"] = "open_enhancement"
    elif target.kind == "delete":
        ctx.handler_state["consult_pending_mode"] = "remove"
        ctx.handler_state["consult_last_subaction"] = "open_remove"
    else:
        ctx.handler_state["consult_last_subaction"] = "exchange"

    ctx.record_operation(
        f"consult_{target.kind}",
        target=target.title or target.action_id or f"consult_{target.index + 1}",
        details={
            "index": target.index,
            "kind": target.kind,
            "action_id": target.action_id,
            "db_id": target.db_id,
        },
    )
    return target


class ConsultHandler(GameplayHandler):
    """相談（咨询交换页）处理。"""

    phase_tag = GameplayPhase.CONSULT
    priority = 50

    def can_handle(self, app, ctx, phase, position):
        return phase == GameplayPhase.CONSULT

    def handle(self, app, ctx, phase, position):
        target = execute_consult_step(app, ctx, position=position)
        if target is None:
            return HandlerResult.no_action("consult: no actionable candidates")

        logger.debug(
            "consult: position={}, kind={}, title={!r}, action_id={}",
            position,
            target.kind,
            target.title,
            target.action_id,
        )
        return HandlerResult.ok(f"consult {target.kind}", sleep_after=0.8)
