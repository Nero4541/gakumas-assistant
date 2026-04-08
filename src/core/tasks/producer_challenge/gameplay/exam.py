"""試験 / オーディション handler。

試験与レッスン共用手牌交互机制: 每回合从手牌中出片，
目标是分数/排名。主要区别:
  - 試験显示排名 vs 对手，而非参数成长
  - 中间試験 (中間試験) / 最终試験 (最終試験)
  - NIA 剧本有オーディション（审核）

当前 YOLO 模型无法可靠区分試験与レッスン —
两者都显示技能卡 + 训练分数/剩余回合。本 handler 在检测到
「exam」阶段时激活（需要后续补充检测逻辑），并回退到 lesson 出牌逻辑。

TODO: 补充試験专用检测信号:
  - OCR 识别「中間試験」/「最終試験」/「オーディション」标题
  - 排名显示 / 对手分数指示器
  - 不同的 HUD 布局
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.constants.yolo.labels.producer_Labels import ProducerLabels
from src.core.tasks.producer_challenge.gameplay.handler_base import (
    GameplayHandler,
    HandlerResult,
)
from src.core.tasks.producer_challenge.gameplay.lesson import (
    execute_lesson_step,
)
from src.utils.logger import logger

if TYPE_CHECKING:
    from src.core.tasks.producer_challenge.context import ProduceContext
    from src.main import AppProcessor


def _try_click_skip(app: "AppProcessor") -> bool:
    """尝试点击試験画面的「スキップ」按钮（所有卡片不可用时跳过回合）。"""
    skip_boxes = app.latest_results.filter_by_label(ProducerLabels.PC_SKIP)
    if skip_boxes:
        logger.info("exam: 点击スキップ按钮跳过回合")
        app.device.click_element(skip_boxes.first())
        return True
    return False


class ExamHandler(GameplayHandler):
    """試験 / オーディション画面处理。

    当前委托给 lesson 出牌逻辑，因为 UI 机制相同。
    当試験专用检测可用时，可改用 ctx.exam_strategy。

    未来增强:
      - 使用 exam_strategy 回调进行試験专用卡牌选择
      - 在 context 中跟踪試験类型 (中间/最终/审核)
      - 不同的分数/排名显示
    """

    phase_tag = "exam"
    priority = 55  # 略高于 lesson，确保可检测时优先处理

    def can_handle(self, app, ctx, phase, position):
        return phase == "exam"

    def handle(self, app, ctx, phase, position):
        result = execute_lesson_step(app, ctx, position=position, phase="exam")
        if result is None:
            # 无手牌时尝试点击跳过
            if _try_click_skip(app):
                return HandlerResult.ok("exam: skip (no cards)", sleep_after=1.0)
            return HandlerResult.no_action("exam: no playable cards")
        if result.status == "used":
            ctx.lesson_turns_played += 1
            return HandlerResult.ok(f"exam {result.status}", sleep_after=0.5)
        if result.status == "all_unplayable":
            # 所有卡片不可用 → 尝试点击スキップ按钮
            if _try_click_skip(app):
                return HandlerResult.ok("exam: skip (all_unplayable)", sleep_after=1.0)
            return HandlerResult.ok("exam: all_unplayable", sleep_after=0.5)
        return HandlerResult.ok(f"exam {result.status}", sleep_after=0.5)
