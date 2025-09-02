from time import sleep

from src.constants.text.button_text import ButtonText
from src.constants.text.modal_text import ModalText
from src.constants.yolo.labels.baseUI_Labels import BaseUILabels
from src.entity.Game.Components.Button import ButtonList
from src.utils.logger import logger
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app import AppProcessor

def action__has_gift_items(app: "AppProcessor") -> bool:
    """
    判断当前界面是否存在可领取的礼物项目。
    :return: True 表示有礼物，False 表示没有
    """
    return app.latest_results.exists_label(BaseUILabels.ITEM)

def action__collect_all_gifts(app: "AppProcessor"):
    """
    尝试点击“一括受取”按钮并处理弹窗确认。
    如果弹窗未出现则抛出超时异常。
    """
    ButtonList(app.latest_results).get_button_by_text(ButtonText.COLLECT_ALL)
    app.device.click_element(app.latest_results.filter_by_label(BaseUILabels.BUTTON).get_y_max_element().first())
    sleep(1)
    modal = app.game_utils.wait_for_modal(ModalText.TITLE.RECEIPT_COMPLETED, 15, True)
    if not modal:
        logger.warning("Gift collection failed")
        return False
    app.device.click_element(modal.cancel_button)
    return True