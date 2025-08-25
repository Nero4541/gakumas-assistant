from src.constants.location import Location
from src.constants.text.modal_text import ModalText
from src.constants.yolo.labels.baseUI_Labels import BaseUILabels
from src.utils.game_tools import get_modal
from src.utils.logger import logger
from src.constants import *
from typing import TYPE_CHECKING

from src.utils.string_tools import string_match, MatchConfig

if TYPE_CHECKING:
    from src.main import AppProcessor

last_card_name = ""
last_modal= False

def register_middlewares(processor: "AppProcessor"):
    @processor.register_middleware()
    @logger.catch
    def _init_location(app: "AppProcessor"):
        if app.game_status_manager.current_location is None and app.latest_results:
            app.game_utils.update_current_location()
        return True


    @processor.register_middleware()
    @logger.catch
    def _handle_unexpected_modal(app: "AppProcessor"):
        global last_modal
        if app.latest_results.exists_label(BaseUILabels.MODAL_HEADER):
            if last_modal:
                return True
            modal = get_modal(app.latest_results, app.latest_frame, True)
            if modal is None:
                return True
            if string_match(modal.modal_title, [ModalText.TITLE.DATA_UPDATE, ModalText.TITLE.DATE_UPDATE], MatchConfig(fuzz_threshold=90)):
                logger.warning("Restart game...")
                app.app.click_element(modal.cancel_button)
                app.game_utils.wait_loading()
                app.game_utils.wait_for_label(BaseUILabels.START_MENU_LOGO)
                app.exec_task("start_game")
            last_modal = True
        else:
            last_modal = False
        return True

    # @processor.register_middleware()
    # @logger.catch
    # def _add_skill(app: "AppProcessor"):
    #     global last_card_name
    #     if app.game_status_manager.current_location == GamePageTypes.SUB_MENU.PRODUCER_ILLUSTRATED:
    #         if app.game_utils.update_current_location() != GamePageTypes.SUB_MENU.PRODUCER_ILLUSTRATED:
    #             return
    #         roi , skill_card, card_info = extract_skill_card_and_info(app.latest_frame)
    #         if skill_card is None or card_info is None:
    #             return
    #         ocr_service = OCRService()
    #         ocr_result = ocr_service.ocr(card_info)
    #         if ocr_result is None:
    #             return
    #         ocr_result.auto_merge_lines(width_gap=100)
    #         card_title = ocr_result.get_y_min().text
    #         if card_title != last_card_name:
    #             last_card_name = card_title
    #             return
    #         card_info = ocr_result.exclude([ocr_result.get_y_min()])
    #         card_info = OCR_ResultList([item for item in card_info if len(item.text) > 2])
    #         skill_card_types = [base_labels.skill_card, base_labels.skill_card__mental, base_labels.skill_card__active, base_labels.skill_card__trap]
    #
    #         if not app.clip_manager.skill_card_clip.add_to_memory(
    #                 skill_card,
    #                 SkillCardInfo(
    #                     card_title,
    #                     app.latest_results.filter_by_labels(
    #                     skill_card_types).get_y_min_element().first().label.replace("Skill Card: ", ""),
    #                     [item.text for item in card_info]
    #                 ), 0.97
    #         ):
    #             logger.debug(app.clip_manager.skill_card_clip.retrieve(skill_card))