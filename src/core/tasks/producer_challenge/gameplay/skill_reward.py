"""技能卡奖励选择 handler。

技能卡奖励画面出现在:
  - 活動支給（活动支给）
  - レッスン完成后
  - 各种事件奖励

画面显示 1-3 张可选技能卡，选中后确认按钮激活。
部分场景可选「再抽選」（re-draw）刷新候选卡。

交互模式（经 ADB 实测确认）:
  - 第一次点击卡片: 高亮选中，确认按钮变为可用，信息面板显示卡名/效果。
  - 第二次点击确认按钮（受け取る）: 接受卡片并推进。
  - 点击「再抽選」按钮: 消耗一次再抽選机会，刷新候选卡。

卡片识别优先级:
  1. CLIP 图像记忆（高置信度、无交互延迟）
  2. 点击卡片 → 信息面板 OCR → 主数据库匹配 → 动态学习 CLIP 记忆
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from time import sleep
from typing import TYPE_CHECKING, Any, List

from src.constants.yolo.labels.baseUI_Labels import BaseUILabels
from src.constants.yolo.labels.producer_Labels import ProducerLabels
from src.constants.game.text.produce_text import ProduceText
from src.core.tasks.producer_challenge.gameplay.common import (
    invoke_decision_strategy,
    ocr_text,
    resolve_candidate_index,
)
from src.core.tasks.producer_challenge.gameplay.decision import (
    build_decision_state,
    hydrate_card_candidates,
    _learn_card_clip_from_db_id,
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

# 再抽選剩余次数 OCR 匹配正则
_REDRAW_REMAINING_RE = re.compile(r"あと\s*(\d+)\s*回")


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
    status: str  # "selected" | "confirmed" | "redrawn"
    candidate: SkillRewardCandidate | None = None


# ────────────────────────────────────────────────────────────
# 信息面板 OCR — 从選中カード的详情面板读取卡名
# ────────────────────────────────────────────────────────────

def _extract_card_name_from_info_panel(
    app: "AppProcessor",
    card_boxes: list[Any],
) -> str:
    """从技能卡信息面板 OCR 读取卡名。

    信息面板位于卡片缩略图上方，显示当前选中/高亮卡片的名称和效果。
    卡名在面板顶部，使用较大字体居中显示。

    Args:
        app: 设备接口
        card_boxes: YOLO 检测到的卡片 box 列表（用于定位面板区域）

    Returns:
        OCR 识别出的卡名文本（可能为空）
    """
    frame = getattr(app, "latest_frame", None)
    if frame is None:
        return ""

    h, w = frame.shape[:2]

    if card_boxes:
        # 卡片上边缘作为面板底部基线
        card_top = min(getattr(b, "y", h) for b in card_boxes)
        # 信息面板卡名区域: 卡片上方约 30% 高度处到卡片顶部偏上
        panel_name_top = max(0, int(card_top - h * 0.23))
        panel_name_bottom = max(0, int(card_top - h * 0.18))
    else:
        # 无卡片检测时使用经验比例
        panel_name_top = int(h * 0.42)
        panel_name_bottom = int(h * 0.48)

    # 水平居中裁剪（卡名居中显示）
    x_start = int(w * 0.15)
    x_end = int(w * 0.75)

    region = frame[panel_name_top:panel_name_bottom, x_start:x_end]
    if region.size == 0:
        return ""

    card_name = ocr_text(region).strip()
    logger.debug(
        "skill_reward: 信息面板 OCR 卡名={!r} (区域 y={}..{}, x={}..{})",
        card_name, panel_name_top, panel_name_bottom, x_start, x_end,
    )
    return card_name


# ────────────────────────────────────────────────────────────
# 再抽選按钮检测
# ────────────────────────────────────────────────────────────

def _detect_redraw_info(
    app: "AppProcessor",
) -> tuple[Any | None, int]:
    """检测再抽選按钮及剩余次数。

    再抽選按钮为 YOLO 检测到的 Universal button，位于受け取る（Confirm）右侧。
    按钮上方/内部有「あとN回」文本标识剩余次数。

    Returns:
        (redraw_box, remaining_count) — 无按钮时 (None, 0)
    """
    confirm_boxes = app.latest_results.filter_by_label(ProducerLabels.CONFIRM_BUTTON)
    generic_buttons = app.latest_results.filter_by_label(BaseUILabels.BUTTON)

    # 确认按钮中心 x（用于区分左侧确认 vs 右侧再抽選）
    confirm_cx = 0
    if confirm_boxes:
        confirm_cx = confirm_boxes.first().cx

    # 再抽選按钮: 位于确认按钮右侧的 Universal button
    redraw_box = None
    for btn in generic_buttons:
        if confirm_cx and btn.cx > confirm_cx:
            redraw_box = btn
            break
    # 如果没有 Confirm button 作参照，尝试找最右侧的 button
    if redraw_box is None and generic_buttons and not confirm_boxes:
        sorted_btns = sorted(generic_buttons, key=lambda b: b.cx, reverse=True)
        redraw_box = sorted_btns[0] if sorted_btns else None

    if redraw_box is None:
        return None, 0

    # OCR 按钮区域读取「あとN回」
    btn_text = ocr_text(redraw_box.frame)
    remaining = 0
    m = _REDRAW_REMAINING_RE.search(btn_text)
    if m:
        remaining = int(m.group(1))
    else:
        # 按钮上方区域可能有剩余次数徽章
        frame = getattr(app, "latest_frame", None)
        if frame is not None:
            badge_top = max(0, getattr(redraw_box, "y", 0) - 60)
            badge_bottom = getattr(redraw_box, "y", 0) + 20
            badge_left = max(0, getattr(redraw_box, "x", 0) - 10)
            badge_right = min(frame.shape[1], getattr(redraw_box, "w", 0) + 30)
            badge_region = frame[badge_top:badge_bottom, badge_left:badge_right]
            if badge_region.size > 0:
                badge_text = ocr_text(badge_region)
                m2 = _REDRAW_REMAINING_RE.search(badge_text)
                if m2:
                    remaining = int(m2.group(1))

    # 确认按钮文本包含「再抽選」才认定（防误判）
    full_text = btn_text
    if remaining > 0 or ProduceText.REDRAW in full_text or "再" in full_text:
        logger.debug(
            "skill_reward: 检测到再抽選按钮 (剩余{}次, OCR={!r})",
            remaining, btn_text,
        )
        return redraw_box, remaining

    return None, 0


# ────────────────────────────────────────────────────────────
# 卡片探査 — CLIP 未命中时点击卡片读取信息面板
# ────────────────────────────────────────────────────────────

def _probe_unresolved_cards(
    app: "AppProcessor",
    candidates: list[SkillRewardCandidate],
) -> None:
    """对 CLIP 未识别的卡片执行信息面板探査。

    依次点击 CLIP 未命中的卡片，等待信息面板更新后 OCR 卡名，
    匹配主数据库并动态学习 CLIP 记忆。

    探査完成后不改变画面选中状态（最后点击的卡是最终高亮卡）。
    """
    # 找出未解析的候选项（排除再抽選等非卡片候选）
    unresolved = [
        c for c in candidates
        if not c.db_id
        and not c.metadata.get("is_redraw")
        and c.box is not None
    ]
    if not unresolved:
        return

    from src.utils.game_database_tools import GakumasDatabase_ProduceCardDataUtils
    card_db = GakumasDatabase_ProduceCardDataUtils()

    # 收集所有卡片 box（用于面板区域定位）
    card_boxes = [c.box for c in candidates if c.box and not c.metadata.get("is_redraw")]

    for candidate in unresolved:
        # 点击卡片触发信息面板显示
        app.device.click_element(candidate.box)
        sleep(0.8)

        # 等待帧刷新后 OCR，失败则重试一次
        card_name = ""
        for attempt in range(2):
            sleep(0.3)
            card_name = _extract_card_name_from_info_panel(app, card_boxes)
            if card_name:
                break
            logger.debug(
                "skill_reward: 探査卡片 #{} OCR 第{}次为空，重试",
                candidate.index, attempt + 1,
            )

        if not card_name:
            logger.debug("skill_reward: 探査卡片 #{} 信息面板 OCR 为空", candidate.index)
            continue

        # 匹配主数据库
        found, card_entry = card_db.search_by_name(card_name)
        if not found or card_entry is None:
            logger.debug(
                "skill_reward: 探査卡片 #{} 名称 {!r} 未匹配数据库",
                candidate.index, card_name,
            )
            # 即使 DB 未匹配，也更新 title（比缩略图 OCR 更可靠）
            candidate.title = card_name
            continue

        # 匹配成功 → 更新候选项元数据
        card_id = str(card_entry.id)
        upgrade_count = int(getattr(card_entry, "upgradeCount", 0) or 0)
        from src.core.tasks.producer_challenge.gameplay.decision import (
            _enrich_card_metadata,
            _apply_resolution,
            CandidateResolution,
        )
        metadata = _enrich_card_metadata(card_id, upgrade_count=upgrade_count)
        display_name = metadata.get("display_name") or card_name
        resolution = CandidateResolution(
            action_id=f"produce_card:{card_id}:{upgrade_count}",
            candidate_type="produce_card",
            db_id=card_id,
            display_name=str(display_name),
            source="info_panel_ocr",
            confidence=0.85,
            metadata=metadata,
        )
        _apply_resolution(candidate, resolution)

        # 动态学习 CLIP 记忆（使用卡片缩略图）
        card_frame = getattr(candidate.box, "frame", None)
        if card_frame is not None:
            _learn_card_clip_from_db_id(app, card_frame, card_id, upgrade_count=upgrade_count)
            logger.info(
                "skill_reward: 探査卡片 #{} {!r} → DB匹配 {} + CLIP学习完成",
                candidate.index, card_name, card_id,
            )


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
    # CLIP 识别 + OCR fallback（不含信息面板探査）
    hydrate_card_candidates(app, candidates)
    return candidates


def _append_redraw_candidate(
    app: "AppProcessor",
    candidates: list[SkillRewardCandidate],
) -> tuple[Any | None, int]:
    """检测再抽選并追加为特殊候选项。

    Returns:
        (redraw_box, remaining_count) — 无按钮时 (None, 0)
    """
    redraw_box, remaining = _detect_redraw_info(app)
    if redraw_box is None or remaining <= 0:
        return None, 0

    redraw_index = len(candidates)
    candidates.append(SkillRewardCandidate(
        index=redraw_index,
        label="redraw",
        title=f"{ProduceText.REDRAW}（あと{remaining}回）",
        selected=False,
        box=redraw_box,
        action_id="skill_reward:redraw",
        db_id="",
        source="ui_detection",
        confidence=1.0,
        metadata={
            "is_redraw": True,
            "redraw_remaining": remaining,
            "candidate_type": "skill_reward_redraw",
        },
    ))
    return redraw_box, remaining


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
    """点击激活的确认按钮（受け取る）。"""
    confirm_boxes = app.latest_results.filter_by_label(ProducerLabels.CONFIRM_BUTTON)
    if confirm_boxes:
        app.device.click_element(confirm_boxes.first())
        return True
    # 回退: 如果没有 Confirm 但有 generic button，点击最低位的（通常是受け取る）
    buttons = app.latest_results.filter_by_label(BaseUILabels.BUTTON)
    if buttons:
        # 排除再抽選按钮（最右侧）— 选最低且非最右的
        sorted_btns = sorted(buttons, key=lambda b: b.cy, reverse=True)
        app.device.click_element(sorted_btns[0])
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
    - skill_reward_idle: 选择一张卡（第 1 步），可选再抽選
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
        acquired_db_id = str(ctx.handler_state.get("pending_skill_reward_db_id") or "")
        ctx.record_operation(
            "confirm_skill_reward",
            target=ctx.pending_skill_reward_label or "skill_reward",
            details={"index": ctx.pending_skill_reward_index, "db_id": acquired_db_id},
        )
        if acquired_db_id:
            ctx.mutate_deck_acquire(
                acquired_db_id,
                kind="produce_card",
                name=ctx.pending_skill_reward_label or "",
                source="skill_reward",
            )
        ctx.clear_skill_reward_pending()
        # 确认领取后会有展示/过渡动画，设置重试容忍
        ctx.handler_state["unknown_retry_override"] = {
            "reason": "skill_reward_confirmed_transition",
            "retry_limit": 15,
            "retry_sleep": 1.0,
        }
        return SkillRewardStepResult(status="confirmed")

    # ── skill_reward_idle: 选卡 / 再抽選 ──
    candidates = collect_skill_reward_candidates(app, ctx, position=position)
    if not candidates:
        return None

    # CLIP 未命中的卡片 → 信息面板探査（点击读取卡名 + DB匹配 + CLIP学习）
    has_unresolved = any(
        not c.db_id and not c.metadata.get("is_redraw")
        for c in candidates
    )
    if has_unresolved:
        _probe_unresolved_cards(app, candidates)
        # 探査完成后等待 YOLO 引擎更新帧（探査过程中点击了卡片）
        sleep(0.3)

    # 检测再抽選按钮并追加为候选项
    _append_redraw_candidate(app, candidates)

    target_index = decide_skill_reward(app, ctx, candidates, position=position)
    target = candidates[target_index]

    # ── 再抽選: 点击再抽選按钮刷新候选卡 ──
    if target.metadata.get("is_redraw"):
        app.device.click_element(target.box)
        remaining = target.metadata.get("redraw_remaining", 0)
        ctx.record_operation(
            "skill_reward_redraw",
            target=ProduceText.REDRAW,
            details={"remaining_after": max(0, remaining - 1)},
        )
        logger.info("skill_reward: 执行再抽選 (剩余{}回→{}回)", remaining, max(0, remaining - 1))
        # 清除 pending，下次循环重新采集新卡
        ctx.clear_skill_reward_pending()
        return SkillRewardStepResult(status="redrawn", candidate=target)

    # ── 普通选卡: 点击卡片高亮选中 ──
    app.device.click_element(target.box)
    ctx.pending_skill_reward_index = target.index
    ctx.pending_skill_reward_label = target.title or target.label or target.action_id
    ctx.handler_state["pending_skill_reward_db_id"] = target.db_id or ""
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
        # 展示画面（单卡获得/强化演出 / メモリー效果）：点击空白区域推进
        if position == "skill_reward_showcase":
            from .common import click_relative_point
            click_relative_point(app, x_ratio=0.5, y_ratio=0.88, label="skill_reward_showcase_advance")
            logger.info("skill_reward: 展示画面，点击空白推进")
            # 展示消失后常伴随切页动画，给更长的 unknown 重试窗口
            ctx.handler_state["unknown_retry_override"] = {
                "reason": "skill_reward_showcase_transition",
                "retry_limit": int(ctx.handler_state.get("skill_reward_transition_unknown_retry_limit", 15)),
                "retry_sleep": float(ctx.handler_state.get("skill_reward_transition_unknown_retry_sleep", 1.0)),
            }
            return HandlerResult.ok("skill_reward showcase advance", sleep_after=1.0)
        # 连续 idle 状态选择卡片但无法进入 selected → 可能是展示画面，点击空白推进
        if position == "skill_reward_idle":
            streak = ctx.handler_state.get("skill_reward_idle_streak", 0) + 1
            ctx.handler_state["skill_reward_idle_streak"] = streak
            ctx.handler_state["skill_reward_selected_streak"] = 0
            if streak >= 4:
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

        sleep_time = 1.2 if result.status == "redrawn" else 0.8
        return HandlerResult.ok(f"skill_reward {result.status}", sleep_after=sleep_time)
