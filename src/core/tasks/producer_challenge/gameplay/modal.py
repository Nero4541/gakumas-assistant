"""弹窗 handler。

在 gameplay 中出现弹窗的场景:
  - 技能卡使用确认 (lesson内)
  - 強化确认
  - 支援事件「戻す」（撤回效果）
  - P饮料详情页
  - 各类信息提示框

默认行为: 点击确认/OK 关闭。handler 优先级较高，
因为弹窗覆盖在其他阶段之上，必须优先处理。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from src.constants.yolo.labels.producer_Labels import ProducerLabels
from src.core.tasks.producer_challenge.gameplay.handler_base import (
    GameplayHandler,
    HandlerResult,
)
from src.utils.logger import logger

if TYPE_CHECKING:
    from src.core.tasks.producer_challenge.context import ProduceContext
    from src.main import AppProcessor


def _click_modal_confirm_direct(app: "AppProcessor") -> bool:
    """直接通过 YOLO 检测结果点击弹窗的确认/取消按钮。

    PRODUCER 模型将按钮标记为 Universal Confirm button / Universal Cancel button，
    而非 ModalParser 期望的 Universal button，因此在 try_get_modal 失败时使用此方法。
    当有多个确认按钮时，优先点击最靠下的（子弹窗在最上层）。
    若只有取消按钮（如「日付変更」弹窗），也会点击取消以关闭弹窗。
    """
    results = app.latest_results
    # 优先点击确认按钮（最靠下的）
    confirm_boxes = list(results.filter_by_label(ProducerLabels.CONFIRM_BUTTON))
    if confirm_boxes:
        target = max(confirm_boxes, key=lambda b: b.cy)
        app.device.click_element(target)
        return True
    # 其次点击通用按钮（取最靠下的）
    buttons = list(results.filter_by_label(ProducerLabels.BUTTON))
    if buttons:
        app.device.click_element(max(buttons, key=lambda b: b.cy))
        return True
    # 最后尝试取消按钮（某些系统弹窗只有取消）
    cancel_boxes = list(results.filter_by_label(ProducerLabels.CANCEL_BUTTON))
    if cancel_boxes:
        target = max(cancel_boxes, key=lambda b: b.cy)
        app.device.click_element(target)
        logger.debug("modal: 仅检测到取消按钮，点击取消")
        return True
    return False


class ModalHandler(GameplayHandler):
    """处理 producer gameplay 中的弹窗。"""

    phase_tag = "modal"
    priority = 90  # 弹窗覆盖其他阶段，优先处理

    def can_handle(self, app, ctx, phase, position):
        return phase == "modal"

    def handle(self, app, ctx, phase, position):
        from src.core.tasks.producer_challenge.ui import click_modal_action_with_retry

        # 累计连续 modal 计数，用于检测卡住情况
        stuck_key = "modal_stuck_count"
        stuck_count = ctx.handler_state.get(stuck_key, 0) + 1
        ctx.handler_state[stuck_key] = stuck_count

        results = app.latest_results

        # 如果连续3次以上弹窗未消失，尝试更激进的关闭策略
        if stuck_count >= 3:
            logger.warning(f"modal: 连续 {stuck_count} 次未消失，尝试备用关闭策略")
            # 尝试 Close Button
            close_boxes = list(results.filter_by_label(ProducerLabels.CLOSE_BUTTON))
            if close_boxes:
                app.device.click_element(close_boxes[0])
                logger.debug("modal: 尝试 Close Button")
                ctx.record_operation("handle_modal", target="close_button_fallback",
                                     details={"stuck_count": stuck_count})
                time.sleep(0.8)
                return HandlerResult.ok("modal: close button fallback", sleep_after=0.5)
            # 尝试取消按钮（某些弹窗只有取消）
            cancel_boxes = list(results.filter_by_label(ProducerLabels.CANCEL_BUTTON))
            if cancel_boxes:
                target = max(cancel_boxes, key=lambda b: b.cy)
                app.device.click_element(target)
                logger.debug("modal: 尝试取消按钮（stuck fallback）")
                ctx.record_operation("handle_modal", target="cancel_fallback",
                                     details={"stuck_count": stuck_count})
                time.sleep(0.8)
                return HandlerResult.ok("modal: cancel fallback", sleep_after=0.5)

        modal = app.game_utils.try_get_modal(no_body=True)
        if modal is None:
            # PRODUCER 模型的按钮标签与 ModalParser 期望的不一致，
            # 直接通过 YOLO 检测结果点击确认按钮
            if _click_modal_confirm_direct(app):
                logger.debug("modal: ModalParser 无法解析，直接点击确认按钮")
                ctx.record_operation("handle_modal", target="direct_confirm", details={"position": position})
                time.sleep(0.5)
                return HandlerResult.ok("modal: direct confirm", sleep_after=0.5)
            return HandlerResult.ok("modal already dismissed")

        title = modal.modal_title or ""
        logger.debug(f"modal: {title!r} (position={position})")

        ctx.record_operation(
            "handle_modal",
            target=title,
            details={"position": position},
        )

        success = click_modal_action_with_retry(
            app,
            modal,
            prefer_confirm=True,
            retries=2,
            timeout=4.0,
            action_name="gameplay modal",
        )
        if not success:
            return HandlerResult.no_action(f"modal {title!r}: failed to dismiss")
        return HandlerResult.ok(f"modal {title!r}: dismissed", sleep_after=0.5)
