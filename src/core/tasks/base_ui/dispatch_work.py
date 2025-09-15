from time import sleep
from typing import TYPE_CHECKING

from src.constants.text.button_text import ButtonText
from src.constants.text.modal_text import ModalText
from src.constants.yolo.labels.baseUI_Labels import BaseUILabels
from src.entity.Game.Page.Types.index import GamePageTypes
from src.entity.Yolo import Yolo_Box, Yolo_Results
from src.utils.logger import logger
from src.core.inference.ocr_engine import OCRService
from src.utils.opencv_tools import check_color_in_region, check_color
from src.utils.game_tools import get_modal
from src.utils.string_tools import string_match, MatchConfig

if TYPE_CHECKING:
    from src.main import AppProcessor

MAX_WORKS = 2
FLAG__Reconfigure_work_hour = False
ocr_service = OCRService()

def handle__work_dispatch_results(app: "AppProcessor"):
    """处理任务派遣结果"""
    count = 0

    while count < MAX_WORKS + 2:
        if app.game_utils.update_current_location() == GamePageTypes.HOME_TAB.WORK:
            return
        if app.game_utils.wait_for_label(BaseUILabels.MODAL_HEADER, 3):
            modal = get_modal(app.latest_results, True)
            app.device.click_element(modal.cancel_button)
            count += 1
            sleep(3)
    else:
        raise RuntimeError("Too many attempts to claim daily dispatch task.")

def action__dispatch_all_available_work(app: "AppProcessor"):
    """派遣任务逻辑"""
    global FLAG__Reconfigure_work_hour
    height, width = app.latest_frame.shape[:2]
    item_group = app.latest_results.filter_by_label(BaseUILabels.ITEM).group_yolo_boxes_by_position(10, width // 4)
    FLAG__Reconfigure_work_hour = False
    if len(item_group) != MAX_WORKS:
        raise RuntimeError("Error in calculating the range of the box body")

    for group in item_group:
        if _is_work_already_dispatched(app, group, width):
            continue
        app.device.click_element(group)
        sleep(1)
        _dispatch_single_work(app)
        sleep(3)
        app.game_utils.wait_for_label(BaseUILabels.AVATAR, 10)

def _is_work_already_dispatched(app: "AppProcessor", group, width):
    """判断该任务是否已派遣"""
    return group.get_vertical_range_elements(app.latest_results, width / 4).exists_label(BaseUILabels.AVATAR)

def _is_avatar_guaranteed_success(avatar):
    """判断角色是否带有标志“好調：大成功確定”"""
    height, width = avatar.frame.shape[:2]
    region = (width / 4, 0, width, height / 4)
    return check_color_in_region(avatar.frame, (98,217,240), (100,255,255), region, 20)

def _assign_avatar_to_work(app: "AppProcessor", avatar=None):
    """选中角色并点击时长按钮"""
    if avatar:  # 当有头像元素时
        app.device.click_element(avatar)
        sleep(0.5)
    app.device.click_element(app.latest_results.filter_by_label(BaseUILabels.BUTTON).get_y_max_element().first())
    app.debug_tools.hide()
    sleep(1)
    while True:
        exists_modal = app.latest_results.exists_label(BaseUILabels.MODAL_HEADER)
        if not app.latest_results.exists_label(BaseUILabels.AVATAR) and not exists_modal:
            break
        if exists_modal:
            modal = get_modal(app.latest_results)
            if string_match(modal.modal_title, ModalText.TITLE.CONFIRM) and string_match(modal.modal_body_text, ModalText.BODY.DISPATCH_WORK_ERROR.OTHER_SELECTABLE_IDOLS):
                app.device.click_element(modal.cancel_button)
                sleep(0.5)
                return False
    app.game_utils.wait_for_label(BaseUILabels.BUTTON)
    _select_work_duration(app)
    sleep(1)
    app.device.click_element(app.latest_results.filter_by_label(BaseUILabels.BUTTON).get_y_max_element().first())
    sleep(1)
    modal = app.game_utils.wait_for_modal(ModalText.TITLE.WORK_START_CONFIRMATION, 10, no_body=True)
    app.device.click_element(modal.confirm_button)
    sleep(1)
    return True

def _select_work_duration(app: "AppProcessor"):
    """选择工作时长"""
    global FLAG__Reconfigure_work_hour
    print("FLAG__Reconfigure_work_hour:", FLAG__Reconfigure_work_hour)
    if FLAG__Reconfigure_work_hour or not app.config_service().task__dispatch_work.reconfigure_work_hours.value:
        return
    frame_h, frame_w = app.latest_frame.shape[:2]
    y_start = frame_h // 2
    y_end = int(app.latest_results.filter_by_label(BaseUILabels.BUTTON).get_y_max_element().first().y)
    y_end = min(frame_h, max(y_start + 1, y_end))
    frame = app.latest_frame[y_start:y_end, 0:frame_w]

    ocr_results = ocr_service.ocr(frame)
    selects = {
        "4H": ButtonText.WORK.TIME.TIME_4H,
        "8H": ButtonText.WORK.TIME.TIME_8H,
        "12H": ButtonText.WORK.TIME.TIME_12H
    }

    candidates = [
        Yolo_Box(
            x := o.x, y := y_start + o.y, w := x + o.w, h := y + o.h,
            f"button__{o.text}", app.latest_frame[y:h, x:w]
        )
        for o in ocr_results if o.text in selects.values()
    ]

    # 根据配置选择目标按钮
    target_text = selects.get(app.config_service().task__dispatch_work.working_hours.value)
    print(target_text)
    app.device.click_element(
        next(
            (c for c in candidates if string_match(c.label, f"button__{target_text}", MatchConfig(fuzz_threshold=95))),
            candidates[-1]
        )
    )
    FLAG__Reconfigure_work_hour = True

def _dispatch_single_work(app: "AppProcessor"):
    """派遣单个任务"""
    app.game_utils.wait_for_label(BaseUILabels.AVATAR)
    def _exec():
        app.debug_tools.clear_all_boxes()
        avatars = app.latest_results.filter_by_label(BaseUILabels.AVATAR)
        avatars = Yolo_Results.from_boxes([avatar for avatar in avatars if avatar.x >= 10])
        for avatar in avatars:
            # 跳过正在工作中的角色
            if  check_color(avatar.frame, (0,15,157), (179,120,185),threshold=40):
                app.debug_tools.add_box(avatar.x, avatar.y, avatar.w, avatar.h, label=f"跳过，已派遣", color=(255,255,0))
                logger.debug("Skip 'お仕事中' avatar")
                continue
            if _is_avatar_guaranteed_success(avatar):
                app.debug_tools.add_box(avatar.x, avatar.y, avatar.w, avatar.h, label="大成功确定", color=(0,255,0))
                return _assign_avatar_to_work(app, avatar)
            app.debug_tools.add_box(avatar.x, avatar.y, avatar.w, avatar.h, label="非优选")
        return False
    if not _exec():
        x, y = app.latest_results.filter_by_label(BaseUILabels.AVATAR).get_COL()
        app.debug_tools.clear_all_boxes()
        app.device.scrollY(x, y, -10)
        sleep(0.5)
        if _exec():
            app.debug_tools.clear_all_boxes()
            return
        _assign_avatar_to_work(app)
        app.debug_tools.clear_all_boxes()

