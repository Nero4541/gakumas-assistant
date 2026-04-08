"""Step 4: 选择偶像卡（P アイドル）。

偶像卡以水平卡片轮播展示（位于屏幕下半部约 y=1600~1800）。
支持两种模式：
  - CLIP 匹配目标偶像卡 ID（如果配置了 target_idol_card_id）
  - 默认使用当前选中的卡（不配置 ID 时）

选择完毕后点击「次へ」进入支援卡编成。
"""

from time import sleep
from typing import TYPE_CHECKING, Optional

import numpy as np

from src.constants.game.text.button_text import ButtonText
from src.constants.yolo.labels.baseUI_Labels import BaseUILabels
from src.core.services.idol_card_ui import (
    advance_to_next_idol_card,
    extract_selected_idol_card_image,
    trim_idol_card_component,
)
from src.core.tasks.producer_challenge.steps.base import ProduceStep
from src.core.tasks.producer_challenge.ui import wait_frame_stable
from src.utils.game_database_tools import GakumasDatabase_IdolCardDataUtils
from src.utils.logger import logger
from src.utils.string_tools import MatchConfig

if TYPE_CHECKING:
    from src.core.tasks.producer_challenge.context import ProduceContext
    from src.main import AppProcessor

MAX_ADVANCE_ATTEMPTS = 10

idol_card_db = GakumasDatabase_IdolCardDataUtils()


class SelectIdolCardStep(ProduceStep):
    step_name = "select_idol_card"

    def validate(self, app: "AppProcessor", ctx: "ProduceContext") -> bool:
        if app.latest_results.exists_label(BaseUILabels.PRODUCT_CARD_SELECTED):
            return True
        idol_labels = (
            BaseUILabels.PRODUCE_CARD_VOCAL,
            BaseUILabels.PRODUCE_CARD_DANCE,
            BaseUILabels.PRODUCE_CARD_VISUAL,
        )
        return any(app.latest_results.exists_label(lbl) for lbl in idol_labels)

    def execute(self, app: "AppProcessor", ctx: "ProduceContext") -> bool:
        # 如果用户指定了目标偶像卡 ID，通过 CLIP 推进匹配
        if ctx.target_idol_card_id:
            self._select_by_clip(app, ctx)
        else:
            logger.info("未配置目标偶像卡 ID，使用默认选中卡")
            self._remember_current_selection(app, ctx)

        # 偶像卡确定后，需要显式推进到支援卡编成页。
        return self._advance_to_support_selection(app)

    def _select_by_clip(self, app: "AppProcessor", ctx: "ProduceContext"):
        """
        通过 CLIP 模型在卡片轮播中匹配目标偶像卡。

        流程：截取当前选中卡图像 → CLIP 检索 → 比对目标 ID
        → 不匹配则优先点击相邻候选卡推进，必要时再回退到低位横滑兜底。
        """
        target_id = ctx.target_idol_card_id
        logger.info(f"目标偶像卡 ID: {target_id}")

        # 验证目标 ID 在主数据库中存在
        target_card = idol_card_db.get_by_id(target_id)
        if target_card is None:
            logger.warning(f"目标偶像卡 ID '{target_id}' 在主数据库中未找到，使用默认选中卡")
            return

        if app.clip_manager is None or not hasattr(app.clip_manager, "idol_card_clip"):
            logger.warning("CLIP 服务未初始化，使用默认选中卡")
            return

        for attempt in range(MAX_ADVANCE_ATTEMPTS):
            card_image = self._extract_selected_card_image(app)
            if card_image is None:
                logger.debug(f"无法提取选中卡片图像 (attempt {attempt + 1}/{MAX_ADVANCE_ATTEMPTS})")
                if not self._advance_carousel(app, None):
                    break
                continue

            matched_card = app.clip_manager.idol_card_clip.retrieve(card_image)
            if matched_card is not None and matched_card.id == target_id:
                logger.success(f"CLIP 匹配成功: {matched_card.name} ({matched_card.id})")
                ctx.selected_idol_card = matched_card
                return

            if matched_card is not None:
                logger.debug(f"当前卡: {matched_card.name} ({matched_card.id})，非目标卡")
            else:
                logger.debug(f"CLIP 未识别当前卡 (attempt {attempt + 1})")

            if not self._advance_carousel(app, card_image):
                logger.debug("无法切换到下一张偶像卡，停止继续查找")
                break

        logger.warning(f"推进 {MAX_ADVANCE_ATTEMPTS} 次仍未找到目标偶像卡，使用当前选中卡")
        self._remember_current_selection(app, ctx)

    def _extract_selected_card_image(self, app: "AppProcessor") -> Optional[np.ndarray]:
        """优先使用 PRODUCT_CARD_SELECTED 裁切，并去掉选中态箭头/边框装饰。"""
        card_image = extract_selected_idol_card_image(getattr(app, "latest_results", None))
        if card_image is not None:
            return card_image

        frame = app.latest_frame
        if frame is None or frame.size == 0:
            return None

        height, width = frame.shape[:2]
        fallback = frame[
            int(height * 0.73):int(height * 0.93),
            int(width * 0.18):int(width * 0.46),
        ]
        return trim_idol_card_component(fallback)

    def _advance_carousel(
            self,
            app: "AppProcessor",
            previous_image: Optional[np.ndarray],
    ) -> bool:
        return advance_to_next_idol_card(app, previous_image, retries=2, timeout=2.5)

    def _remember_current_selection(self, app: "AppProcessor", ctx: "ProduceContext"):
        if ctx.selected_idol_card is not None:
            return
        if app.clip_manager is None or not hasattr(app.clip_manager, "idol_card_clip"):
            return

        card_image = self._extract_selected_card_image(app)
        if card_image is None:
            return

        matched_card = app.clip_manager.idol_card_clip.retrieve(card_image)
        if matched_card is not None:
            ctx.selected_idol_card = matched_card
            logger.info(f"记录当前偶像卡: {matched_card.name} ({matched_card.id})")

    def _advance_to_support_selection(self, app: "AppProcessor") -> bool:
        """点击「次へ」并等待进入支援卡编成页。"""
        app.game_utils.click_button(
            ButtonText.NEXT,
            match_config=MatchConfig(fuzz_threshold=80),
        )
        app.game_utils.wait_loading()
        return self._wait_for_support_selection_page(app)

    @staticmethod
    def _wait_for_support_selection_page(app: "AppProcessor") -> bool:
        """等待支援卡编成页稳定出现。

        真机上进入支援卡编成页后，画面里仍可能残留一些 Produce Card /
        Skill Card 类缩略图，因此不能再把“偶像卡标签全部消失”当成硬条件。

        实际可依赖的稳定信号是：
        - 支援卡槽位已被 YOLO 识别为 `Support Card`
        - 或页面存在空槽 `Blank Slot`
        """
        for _ in range(15):
            has_support_slot = (
                app.latest_results.exists_label(BaseUILabels.SUPPORT_CARD)
                or app.latest_results.exists_label(BaseUILabels.BLANK_SLOT)
            )
            if has_support_slot:
                wait_frame_stable(app, timeout=2.5)
                logger.debug("成功进入支援卡编成页")
                return True
            sleep(1)
        raise TimeoutError("等待支援卡编成页超时")
