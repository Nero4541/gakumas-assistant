"""Step 12: 处理培育结果画面并返回主页。

培育结束后游戏会依次展示（实际顺序基于连调实测）：
  1. フォト選択画面 — 选择照片，点击「次へ」
  2. メモリー生成画面 — 圆形「生成」按钮（YOLO 无法检测）
  3. 生成动画 / Loading
  4. プロデュース評価 — 评价得分，TAP 推进
  5. メモリーカード展示 — TAP 推进（可能多页）
  6. スキルカード展示 — TAP 推进（可能多页）
  7. メモリー生成完了 — TAP 推进
  8. 結果汇总页 — 有 Confirm / Universal 按钮
  9. 成就 / 奖励进度页 — 有 Confirm 按钮（可能多页）
  10. 完了する / プロデュース履歴 — 必须点击「完了する」（左侧按钮）
  11. 受取完了弹窗 — 点击按钮关闭
  12. イベントPt 页 — 点击按钮推进
  13. Loading → 回到主页

注意：
  - 很多中间画面没有 YOLO 标签，只能靠 OCR 识别
  - 「生成」按钮是圆形设计，YOLO 不会检测到
  - 最终页有两个 Universal button 并排，必须用 OCR 区分
"""

from time import sleep, time
from typing import TYPE_CHECKING

from src.constants.game.text.button_text import ButtonText
from src.constants.game.text.produce_text import ProduceText
from src.constants.yolo.labels.baseUI_Labels import BaseUILabels
from src.constants.yolo.labels.producer_Labels import ProducerLabels
from src.constants.yolo.model_type import YoloModelType
from src.core.tasks.producer_challenge.gameplay.common import (
    click_relative_point,
    ocr_text,
)
from src.core.tasks.producer_challenge.steps.base import ProduceStep
from src.core.tasks.producer_challenge.ui import (
    collect_button_like_texts,
    collect_frame_text,
    click_modal_action_with_retry,
    find_button,
)
from src.utils.logger import logger

if TYPE_CHECKING:
    from src.core.tasks.producer_challenge.context import ProduceContext
    from src.main import AppProcessor


# ── OCR 关键词 ──────────────────────────────────────────
# 需要 TAP 推进的画面关键词
_TAP_SCREEN_KEYWORDS = (
    ProduceText.MEMORY_GENERATION_COMPLETE,  # メモリー生成完了
    "TAP",
    "プロデュース評価",                       # 培育评价得分
)

# 结果链相关关键词（用于判断是否仍在结果流程中）
_RESULT_CHAIN_KEYWORDS = (
    ProduceText.MEMORY_GENERATION_COMPLETE,
    ProduceText.MEMORY_SELECT,
    ProduceText.PRODUCE_RESULT,
    ProduceText.ACHIEVEMENT_PROGRESS,
    ProduceText.EVENT_REWARD_PROGRESS,
    ProduceText.EVENT_POINT,
    ProduceText.FAILED,
    ProduceText.FINAL_PRODUCE_EVALUATION,
    ProduceText.REWARD_ITEMS,
    "MEMORY",
    "プロデュース",
    "受取完了",
    "報酬",
    "完了する",
    "イベント",
    "最終試験",
)

# 「完了する」页面的 OCR 标识
_COMPLETE_PAGE_KEYWORDS = ("完了する",)
# 「プロデュース履歴」页面的 OCR 标识
_HISTORY_PAGE_KEYWORD = "プロデュース履歴"

# 主页检测关键词 — 同时出现 2 个以上则判定为主页（含 OCR 变体）
_HOME_SCREEN_KEYWORDS = (
    # プレゼント（礼物）及其 OCR 变体
    "プレゼント", "プレセント", "プレゼンド", "プレセンド",
    # ミッション（任务）及其 OCR 变体
    "ミッション", "ミッショラ", "ミグション",
    # アチーブ（成就）及其 OCR 变体
    "アチーブ", "アチープ",
)
# 上述关键词分 3 组，每组命中算 1 分，需至少 2 组命中
_HOME_SCREEN_GROUPS = (
    ("プレゼント", "プレセント", "プレゼンド", "プレセンド"),
    ("ミッション", "ミッショラ", "ミグション"),
    ("アチーブ", "アチープ"),
)
_HOME_SCREEN_MIN_MATCH = 2


class HandleResultsStep(ProduceStep):
    step_name = "handle_results"

    def execute(self, app: "AppProcessor", ctx: "ProduceContext") -> bool:
        ctx.gameplay_phase = "results"
        logger.info("开始处理培育结果画面")

        # 阶段一：在 PRODUCER 模型下跳过结果页面
        self._skip_result_screens(app, timeout=120)

        # 阶段二：切回 BASE_UI 模型
        logger.info("切换回 BASE_UI 模型")
        app.yolo_engine.load_model(YoloModelType.BASE_UI)
        sleep(2)

        # 阶段三：等待回到主页（处理残余弹窗）
        if not self._wait_for_home(app, timeout=40):
            logger.warning("未自动回到主页，尝试手动导航")
            try:
                app.game_utils.go_home(max_try=5)
            except RuntimeError:
                logger.error("返回主页失败")
                return False

        logger.success("培育完成，已返回主页")
        return True

    # ── 阶段一：结果链推进 ─────────────────────────────────

    @staticmethod
    def _skip_result_screens(app: "AppProcessor", timeout: int = 120):
        """在结果链中持续推进，直到进入 Loading 或检测到主页标签。

        策略：OCR 优先识别画面类型 → YOLO 按钮点击 → TAP 兜底
        """
        start = time()
        consecutive_no_progress = 0
        same_text_count = 0           # 连续相同 OCR 文本计数（检测画面卡住）
        last_text_hash = ""           # 上一次 OCR 文本摘要
        MAX_NO_PROGRESS = 15          # 连续无法推进则退出
        MAX_SAME_TEXT = 8             # 同一画面持续 N 次则尝试强制推进

        while time() - start < timeout:
            sleep(1.0)
            results = app.latest_results
            frame = app.latest_frame
            if results is None or frame is None:
                consecutive_no_progress += 1
                if consecutive_no_progress >= MAX_NO_PROGRESS:
                    break
                continue

            # ── 快速主页检测（PRODUCER 模型偶尔也能看到 Tab 标签）──
            if results.exists_label(BaseUILabels.TAB_HOME):
                logger.debug("结果链: 检测到主页标签，退出")
                break

            # ── OCR 识别当前画面 ──
            frame_text = ocr_text(frame)
            labels = [r.label for r in results]
            # 缩短文本用于日志（最多80字符）
            short_text = frame_text.replace("\n", " ")[:80]
            logger.debug(f"结果链: OCR=[{short_text}] YOLO={labels}")

            # ── OCR 主页检测（PRODUCER 模型下 YOLO 无法识别主页标签）──
            if HandleResultsStep._is_home_screen(frame_text):
                logger.debug("结果链: OCR 检测到主页关键词，退出")
                break

            # ── 同一画面检测（防止死循环）──
            text_hash = frame_text.replace(" ", "").replace("\n", "")[:100]
            if text_hash == last_text_hash and text_hash:
                same_text_count += 1
            else:
                same_text_count = 0
                last_text_hash = text_hash

            # 画面长时间无变化 → 强制尝试关闭/退出
            if same_text_count >= MAX_SAME_TEXT:
                logger.warning(f"结果链: 画面卡住 {same_text_count} 次，尝试强制推进")
                # 先尝试 Close Button
                close_boxes = results.filter_by_label(ProducerLabels.CLOSE_BUTTON)
                if close_boxes:
                    app.device.click_element(close_boxes.first())
                else:
                    # 点击底部关闭按钮常见位置
                    click_relative_point(app, x_ratio=0.5, y_ratio=0.94, label="stuck-close")
                sleep(2.0)
                same_text_count = 0
                consecutive_no_progress += 1
                if consecutive_no_progress >= MAX_NO_PROGRESS:
                    break
                continue

            # ── 1. 「生成」按钮页 — 圆形按钮 YOLO 无法检测 ──
            if HandleResultsStep._is_generate_screen(frame_text, labels):
                logger.debug("结果链: 检测到「生成」按钮页，点击生成")
                gen_btn = find_button(app, ButtonText.GENERATE, fuzz_threshold=50)
                if gen_btn:
                    app.device.click_element(gen_btn)
                else:
                    # 圆形按钮在画面偏下方 y≈0.77
                    click_relative_point(app, x_ratio=0.5, y_ratio=0.77, label="生成-button")
                sleep(3.0)
                consecutive_no_progress = 0
                continue

            # ── 2. 「プロデュース履歴」详情页 — 误触后关闭（优先于完了检测）──
            if HandleResultsStep._is_history_page(frame_text, labels):
                logger.debug("结果链: 检测到プロデュース履歴详情页，关闭")
                close_boxes = results.filter_by_label(ProducerLabels.CLOSE_BUTTON)
                if close_boxes:
                    app.device.click_element(close_boxes.first())
                else:
                    # Close Button 在底部 y≈0.94（PRODUCER 模型可能检测不到）
                    click_relative_point(app, x_ratio=0.5, y_ratio=0.94, label="history-close")
                sleep(1.5)
                consecutive_no_progress = 0
                continue

            # ── 3. 「完了する」页 — 必须点左侧按钮 ──
            if HandleResultsStep._is_complete_page(frame_text):
                logger.debug("结果链: 检测到「完了する」页面")
                complete_btn = find_button(app, ButtonText.COMPLETE, fuzz_threshold=50)
                if complete_btn:
                    app.device.click_element(complete_btn)
                    logger.debug("结果链: 点击「完了する」按钮")
                else:
                    # 兜底：两个并排按钮时取左侧（cx 较小的）
                    btns = results.filter_by_label(ProducerLabels.BUTTON)
                    confirms = results.filter_by_label(ProducerLabels.CONFIRM_BUTTON)
                    all_btns = list(btns) + list(confirms)
                    if len(all_btns) >= 2:
                        leftmost = min(all_btns, key=lambda b: b.cx)
                        app.device.click_element(leftmost)
                        logger.debug("结果链: 点击左侧按钮（兜底）")
                    elif all_btns:
                        app.device.click_element(all_btns[0])
                    else:
                        # 「完了する」按钮通常在左下角
                        click_relative_point(app, x_ratio=0.27, y_ratio=0.92, label="完了-fallback")
                sleep(2.0)
                consecutive_no_progress = 0
                continue

            # ── 4. TAP 推进画面（评价/展示/生成完了）──
            if HandleResultsStep._is_tap_screen(frame_text):
                logger.debug("结果链: TAP 推进画面")
                click_relative_point(app, x_ratio=0.5, y_ratio=0.5, label="result-tap")
                sleep(1.5)
                consecutive_no_progress = 0
                continue

            # ── 5. Skip 按钮 ──
            skip_boxes = results.filter_by_label(ProducerLabels.SKIP_BUTTON)
            if skip_boxes:
                app.device.click_element(skip_boxes.first())
                logger.debug("结果链: 点击 Skip")
                sleep(1.5)
                consecutive_no_progress = 0
                continue

            # ── 6. 快进按钮（剧情过场）──
            ff = results.filter_by_label(ProducerLabels.PLOT_FAST_FORWARD_BUTTON)
            if ff:
                app.device.click_element(ff.first())
                sleep(0.5)
                consecutive_no_progress = 0
                continue

            # ── 7. YOLO 检测到的按钮 ──
            clicked_btn = HandleResultsStep._click_best_button(app, results, frame_text)
            if clicked_btn:
                logger.debug(f"结果链: 点击按钮 [{clicked_btn}]")
                sleep(1.5)
                consecutive_no_progress = 0
                continue

            # ── 8. 结果链内容但无按钮 — TAP 推进 ──
            if HandleResultsStep._text_matches_result_chain(frame_text):
                click_relative_point(app, x_ratio=0.5, y_ratio=0.5, label="result-chain-tap")
                logger.debug("结果链: 文本匹配结果链，TAP推进")
                sleep(1.5)
                # 不重置 consecutive_no_progress — 纯文本匹配可能是卡住
                consecutive_no_progress += 1
                if consecutive_no_progress >= MAX_NO_PROGRESS:
                    logger.debug("结果链: 结果链文本匹配但无法推进，退出")
                    break
                continue

            # ── 9. Loading 画面 ──
            if "NOW LOADING" in frame_text.upper() or "LOADING" in frame_text.upper():
                logger.debug("结果链: Loading 中，等待")
                sleep(2.0)
                consecutive_no_progress = 0
                continue

            # ── 10. 完全无内容 — 可能是过渡动画 ──
            consecutive_no_progress += 1
            if consecutive_no_progress >= MAX_NO_PROGRESS:
                logger.debug("结果链: 连续无法推进，退出")
                break
            click_relative_point(app, x_ratio=0.5, y_ratio=0.5, label="result-empty")
            sleep(1.0)

        elapsed = round(time() - start, 1)
        logger.debug(f"结果链处理完毕，耗时 {elapsed}s")

    # ── 画面类型判断辅助 ─────────────────────────────────

    @staticmethod
    def _is_generate_screen(frame_text: str, labels: list[str]) -> bool:
        """判断是否是メモリー生成页（圆形「生成」按钮）。
        特征：OCR 只有「生成」或「MEMORY」+「生成」，且无 YOLO 按钮标签。
        """
        text = frame_text.replace(" ", "").replace("\n", "")
        has_generate = "生成" in text
        has_memory = "MEMORY" in text.upper() or "メモリー" in text
        # 排除「メモリー生成完了」（那是 TAP 推进页）
        if "生成完了" in text:
            return False
        # 排除「再生成」按钮页（有其他按钮）
        has_any_button = any(
            "button" in lbl.lower() or "Button" in lbl
            for lbl in labels
        )
        return has_generate and (has_memory or len(text) < 10) and not has_any_button

    @staticmethod
    def _is_complete_page(frame_text: str) -> bool:
        """判断是否是最终「完了する」页面。
        特征：同时有「完了する」和「プロデュース履歴」或「メモリー変換」文本。
        """
        text = frame_text.replace(" ", "")
        has_complete = "完了する" in text
        has_history = _HISTORY_PAGE_KEYWORD in text
        has_memory_convert = "メモリー変換" in text
        return has_complete and (has_history or has_memory_convert)

    @staticmethod
    def _is_history_page(frame_text: str, labels: list[str]) -> bool:
        """判断是否是「プロデュース履歴」详情页（误触后进入的页面）。
        特征：有「プロデュース履歴」+ 详情内容（定期公演/編成/PLV等），
        但没有「完了する」按钮。
        注意：PRODUCER 模型可能检测不到 Close Button，所以不依赖 YOLO 标签。
        """
        text = frame_text.replace(" ", "")
        has_history = _HISTORY_PAGE_KEYWORD in text
        has_complete = "完了する" in text
        # 详情页特有的关键词（区分完了する页面）
        _detail_keywords = ("定期公演", "編成", "PLV", "編成詳細", "サポートカード")
        has_detail = any(kw in text for kw in _detail_keywords)
        return has_history and has_detail and not has_complete

    @staticmethod
    def _is_home_screen(frame_text: str) -> bool:
        """判断是否已经回到主页。
        主页 OCR 同时包含「プレゼント」「ミッション」「アチーブ」等导航文本。
        按组匹配（每组含 OCR 变体），至少 2 组命中。
        """
        text = frame_text.replace(" ", "").replace("\n", "")
        matched_groups = 0
        for group in _HOME_SCREEN_GROUPS:
            if any(variant in text for variant in group):
                matched_groups += 1
        return matched_groups >= _HOME_SCREEN_MIN_MATCH

    @staticmethod
    def _is_tap_screen(frame_text: str) -> bool:
        """判断是否是需要 TAP 推进的展示画面。
        排除主页（主页 OCR 中「TAPアイドルへの道...」会误匹配）。
        """
        text = frame_text.replace(" ", "").replace("\n", "")
        # 主页排除
        if HandleResultsStep._is_home_screen(frame_text):
            return False
        for keyword in _TAP_SCREEN_KEYWORDS:
            if keyword in text:
                return True
        return False

    @staticmethod
    def _text_matches_result_chain(frame_text: str) -> bool:
        """判断 OCR 文本是否属于结果链的一部分。
        排除主页（主页 OCR 也包含「イベント」「ミッション」等词）。
        """
        text = frame_text.replace(" ", "")
        if not text:
            return False
        # 主页排除
        if HandleResultsStep._is_home_screen(frame_text):
            return False
        for keyword in _RESULT_CHAIN_KEYWORDS:
            if keyword in text:
                return True
        return False

    # ── 按钮点击辅助 ─────────────────────────────────────

    @staticmethod
    def _click_best_button(app: "AppProcessor", results, frame_text: str = "") -> str | None:
        """智能选择并点击最佳按钮。

        优先级：
        1. 如果画面有「完了する」，优先点左侧按钮
        2. OCR 匹配「閉じる」/「次へ」/「確認」 → 精确点击
        3. Universal Confirm button → 直接点击
        4. Universal button → 底部优先
        返回点击的按钮描述，无按钮返回 None。
        """
        # 特殊处理：如果 OCR 包含「完了する」，优先点击左侧按钮
        clean_text = frame_text.replace(" ", "")
        if "完了する" in clean_text:
            complete_btn = find_button(app, ButtonText.COMPLETE, fuzz_threshold=50)
            if complete_btn:
                app.device.click_element(complete_btn)
                return "完了する(OCR)"
            # 兜底：取最左侧按钮
            btns = list(results.filter_by_label(ProducerLabels.BUTTON)) + \
                   list(results.filter_by_label(ProducerLabels.CONFIRM_BUTTON))
            if len(btns) >= 2:
                leftmost = min(btns, key=lambda b: b.cx)
                app.device.click_element(leftmost)
                return "完了する(左侧兜底)"

        # 尝试 OCR 匹配关键按钮文本
        for text_key, label in (
            (ButtonText.CLOSE, "閉じる"),
            (ButtonText.NEXT, "次へ"),
            (ButtonText.CONFIRM, "確認"),
        ):
            btn = find_button(app, text_key, fuzz_threshold=50)
            if btn:
                app.device.click_element(btn)
                return label

        # Confirm 按钮（底部优先）
        confirms = results.filter_by_label(ProducerLabels.CONFIRM_BUTTON)
        if confirms:
            target = max(list(confirms), key=lambda b: b.cy)
            app.device.click_element(target)
            return f"Confirm@{round(target.cy)}"

        # Universal 按钮（底部优先）
        buttons = results.filter_by_label(ProducerLabels.BUTTON)
        if buttons:
            target = max(list(buttons), key=lambda b: b.cy)
            app.device.click_element(target)
            return f"Button@{round(target.cy)}"

        return None

    # ── 阶段三：等待主页 ─────────────────────────────────

    @staticmethod
    def _wait_for_home(app: "AppProcessor", timeout: int = 40) -> bool:
        """等待回到主页（BASE_UI 模型下检测 Tab: Home 标签）。

        同时处理残余弹窗（受取完了、イベントPt 等）。
        """
        start = time()
        while time() - start < timeout:
            results = app.latest_results
            if results is None:
                sleep(1)
                continue

            # 检测主页底部 tab bar
            if results.exists_label(BaseUILabels.TAB_HOME):
                return True

            # 处理残余弹窗（BASE_UI 模型下 try_get_modal 可靠）
            modal = app.game_utils.try_get_modal(no_body=True)
            if modal:
                click_modal_action_with_retry(
                    app, modal,
                    prefer_confirm=True,
                    retries=2,
                    timeout=3.0,
                    action_name="post-result modal",
                )
                sleep(1)
                continue

            # 通用按钮兜底（可能还有残余结果页未关闭）
            buttons = results.filter_by_label(BaseUILabels.BUTTON)
            if buttons:
                target = max(list(buttons), key=lambda b: b.cy)
                app.device.click_element(target)
                sleep(1.5)
                continue

            sleep(1)
        return False
