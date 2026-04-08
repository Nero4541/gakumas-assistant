"""Pアイテム選択 handler。

「受け取るPアイテムを選んでください。」画面を処理する。
画面に 1~3 個の Special Item が表示され、選択後に
「受け取る」ボタンが有効化される。

交互模式:
  1. Special Item アイコンをタップ → 選択ハイライト → ボタン有効化
  2. 受け取るボタンをタップ → アイテム取得、次の画面へ
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.constants.game.producer_gameplay import GameplayPhase, GameplayPosition
from src.constants.yolo.labels.baseUI_Labels import BaseUILabels
from src.constants.yolo.labels.producer_Labels import ProducerLabels
from src.core.tasks.producer_challenge.gameplay.handler_base import (
    GameplayHandler,
    HandlerResult,
)
from src.utils.logger import logger

if TYPE_CHECKING:
    from src.core.tasks.producer_challenge.context import ProduceContext
    from src.main import AppProcessor


def _click_first_item(app: "AppProcessor") -> bool:
    """点击第一个（最左侧的）Special Item。"""
    items = list(app.latest_results.filter_by_label(ProducerLabels.SPECIAL_ITEM))
    if not items:
        return False
    items.sort(key=lambda b: b.cx)
    app.device.click_element(items[0])
    logger.debug(f"item_select: 点击第 1 个 Special Item (共 {len(items)} 个)")
    return True


def _click_receive_button(app: "AppProcessor") -> bool:
    """点击激活的「受け取る」按钮。"""
    # 优先找 Confirm Button
    confirm = app.latest_results.filter_by_label(ProducerLabels.CONFIRM_BUTTON)
    if confirm:
        app.device.click_element(confirm.first())
        return True
    # 其次找 Universal button
    buttons = list(app.latest_results.filter_by_label(BaseUILabels.BUTTON))
    if buttons:
        # 取最靠下的按钮（受け取る通常在底部）
        btn = max(buttons, key=lambda b: b.cy)
        app.device.click_element(btn)
        return True
    return False


class ItemSelectHandler(GameplayHandler):
    """Pアイテム選択画面処理。

    idle 状態: Special Item は検出されるがボタンが無効（Disable）→ アイテムを選択
    selected 状態: ボタンが有効 → 受け取るをタップ
    """

    phase_tag = GameplayPhase.ITEM_SELECT
    priority = 50  # 与 LESSON / SCHEDULE 等同级

    def can_handle(self, app, ctx, phase, position):
        return phase == GameplayPhase.ITEM_SELECT

    def handle(self, app, ctx, phase, position):
        if position == GameplayPosition.ITEM_SELECT_SELECTED:
            # 已选择物品，点击受け取る
            if _click_receive_button(app):
                ctx.handler_state["item_select_idle_streak"] = 0
                return HandlerResult.ok("item_select: 确认受取", sleep_after=1.0)
            return HandlerResult.no_action("item_select: 无法找到确认按钮")

        # idle — 选择一个物品
        streak = ctx.handler_state.get("item_select_idle_streak", 0) + 1
        ctx.handler_state["item_select_idle_streak"] = streak

        if _click_first_item(app):
            return HandlerResult.ok("item_select: 选择物品", sleep_after=0.8)

        # 无 Special Item 检测到 → 可能是过渡帧
        if streak >= 5:
            logger.warning("item_select: 连续无法选择物品，尝试点击屏幕推进")
            from .common import click_relative_point
            click_relative_point(app, x_ratio=0.5, y_ratio=0.7, label="item_select_advance")
            ctx.handler_state["item_select_idle_streak"] = 0
            return HandlerResult.ok("item_select: 强制推进", sleep_after=1.0)

        return HandlerResult.no_action("item_select: 等待 Special Item 出现")
