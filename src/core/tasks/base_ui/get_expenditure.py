from time import sleep
from typing import TYPE_CHECKING

from src.constants.game.text.modal_text import ModalText
from src.constants.yolo.labels.baseUI_Labels import BaseUILabels
from src.utils.logger import logger
from src.utils.string_tools import MatchConfig, string_match

if TYPE_CHECKING:
    from src.main import AppProcessor


def action__claim_expenditure(app: "AppProcessor", max_attempts: int = 3) -> bool:
    """
    打开活动费弹窗；若误点进其他弹窗，则关闭后重试。
    """
    from src.core.tasks.base_ui.goto_pages import goto__get_expenditure

    for attempt in range(max_attempts):
        goto__get_expenditure(app)
        sleep(2)
        modal = app.game_utils.wait_for_modal(None, no_body=True, timeout=5, interval=0.5)
        if not modal:
            if app.latest_results.exists_label(BaseUILabels.TAB_HOME):
                logger.warning("There are no claimable expenses")
                return True
            continue

        if string_match(modal.modal_title, ModalText.TITLE.EXPENDITURE, MatchConfig(fuzz_threshold=90)):
            app.device.click_element(modal.cancel_button or modal.confirm_button)
            app.game_utils.wait_label_exist(BaseUILabels.MODAL_HEADER, timeout=5, interval=0.5)
            sleep(1)
            return True

        logger.warning(
            f"Unexpected modal '{modal.modal_title}' when opening expenditure. "
            f"Retrying... ({attempt + 1}/{max_attempts})"
        )
        close_button = modal.cancel_button or modal.confirm_button
        if close_button:
            app.device.click_element(close_button)
            app.game_utils.wait_label_exist(BaseUILabels.MODAL_HEADER, timeout=5, interval=0.5)
        sleep(1)

    raise TimeoutError("Timeout waiting for expenditure modal to appear.")
