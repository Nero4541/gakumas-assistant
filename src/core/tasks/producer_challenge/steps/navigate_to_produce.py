"""Step 1: 从主页导航到培育（プロデュース）剧本选择页面。"""

from time import sleep
from typing import TYPE_CHECKING

from src.constants.yolo.labels.baseUI_Labels import BaseUILabels
from src.core.tasks.producer_challenge.steps.base import ProduceStep
from src.core.tasks.producer_challenge.ui import click_modal_action_with_retry
from src.entity.Game.Page.Types.index import GamePageTypes
from src.utils.logger import logger

if TYPE_CHECKING:
    from src.core.tasks.producer_challenge.context import ProduceContext
    from src.main import AppProcessor

_SCENARIO_LABELS = (
    BaseUILabels.PRODUCER_REGULAR,
    BaseUILabels.PRODUCER_PRO,
    BaseUILabels.PRODUCER_MASTER,
    BaseUILabels.PRODUCER_NIA,
)


def _is_on_scenario_page(app: "AppProcessor") -> bool:
    """当前画面能检测到任意难度标签 → 说明在剧本选择页。"""
    return any(
        app.latest_results.exists_label(lbl) for lbl in _SCENARIO_LABELS
    )


class NavigateToProduceStep(ProduceStep):
    step_name = "navigate_to_produce"

    def execute(self, app: "AppProcessor", ctx: "ProduceContext") -> bool:
        if _is_on_scenario_page(app):
            logger.debug("已经在培育剧本选择页面")
            return True

        self._dismiss_residual_modal(app)

        # 确保在主页
        app.game_utils.go_home()
        app.game_utils.wait_loading()

        # 点击培育按钮
        if not app.game_utils.wait_for_label(BaseUILabels.HOME_PRODUCE_BTN, timeout=10):
            raise TimeoutError("等待 Home: Produce Button 超时")
        app.game_utils.click_on_label(BaseUILabels.HOME_PRODUCE_BTN)

        # 等待加载完成
        app.game_utils.wait_loading()

        # 等待剧本页面出现
        for _ in range(15):
            if _is_on_scenario_page(app):
                logger.debug("成功进入剧本选择页")
                return True
            sleep(1)

        raise TimeoutError("导航到培育剧本选择页超时")

    @staticmethod
    def _dismiss_residual_modal(app: "AppProcessor") -> None:
        """清理任务起跑前残留的弹窗。

        真机断点恢复时，可能停在启动弹窗、提示弹窗或确认弹窗上。
        这些弹窗会让 `go_home()` 的返回路径失效，因此先尽量关闭。
        """
        for attempt in range(3):
            modal = app.game_utils.try_get_modal(no_body=True, require_header=False)
            if modal is None:
                return
            logger.info(f"navigate_to_produce: 清理残留弹窗 {attempt + 1}: {modal.modal_title!r}")
            if click_modal_action_with_retry(
                app,
                modal,
                prefer_confirm=False,
                retries=2,
                timeout=3.0,
                action_name="navigate_to_produce residual modal",
            ):
                sleep(0.5)
                continue
            break
