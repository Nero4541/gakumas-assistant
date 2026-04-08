from __future__ import annotations

import re
from statistics import median
from time import sleep, time
from typing import TYPE_CHECKING, Sequence

from src.constants.game.producer_gameplay import (
    CONSULT_ENHANCEMENT_POSITION_PREFIX,
    CONSULT_POSITION_PREFIX,
    GAMEPLAY_MODAL_POSITIONS,
    GameplayPhase,
    GameplayPosition,
    P_DRINK_SELECTION_POSITIONS,
    SKILL_REWARD_SELECTION_POSITIONS,
)
from src.constants.game.text.button_text import ButtonText
from src.constants.game.text.produce_text import ProduceText
from src.constants.yolo.labels.baseUI_Labels import BaseUILabels
from src.constants.yolo.labels.producer_Labels import ProducerLabels
from src.entity.Game.Components.Button import Button, ButtonList
from src.core.tasks.producer_challenge.gameplay.common import (
    invoke_decision_strategy,
    normalize_text,
    ocr_text,
    resolve_candidate_index,
)
from src.utils.debug_tools import DebugTools
from src.utils.logger import logger
from src.utils.string_tools import MatchConfig, string_match

if TYPE_CHECKING:
    from src.core.tasks.producer_challenge.context import ProduceContext
    from src.entity.Game.Components.Modal import Modal
    from src.main import AppProcessor

_PRESET_INDEX_PATTERN = re.compile(r"(\d+)\s*/\s*(\d+)")


def get_buttons(app: "AppProcessor") -> ButtonList:
    return ButtonList(app.latest_results)


def parse_preset_index(text: str | None) -> tuple[int, int] | None:
    normalized = str(text or "").replace(" ", "")
    if not normalized:
        return None
    match = _PRESET_INDEX_PATTERN.search(normalized)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


def get_current_preset_index(app: "AppProcessor") -> tuple[int, int] | None:
    for button in get_buttons(app):
        if parsed := parse_preset_index(button.text):
            return parsed
    return None


def build_preset_swipe_paths(
    boxes: Sequence,
    *,
    frame_width: int,
) -> list[tuple[int, int, int, int]]:
    if not boxes:
        return []

    left = int(min(box.x for box in boxes))
    right = int(max(box.w for box in boxes))
    span = max(1, right - left)
    margin = max(40, int(span * 0.15))
    start_x = min(frame_width - 40, right - margin)
    end_x = max(40, left + margin)
    if start_x - end_x < 160:
        start_x = max(end_x + 160, int(frame_width * 0.75))
        end_x = int(frame_width * 0.25)

    rows: list[list] = []
    current_row: list = []
    row_anchor_cy: int | None = None
    for box in sorted(boxes, key=lambda item: item.cy):
        if row_anchor_cy is None or abs(box.cy - row_anchor_cy) <= 120:
            if not current_row:
                row_anchor_cy = box.cy
            current_row.append(box)
        else:
            rows.append(current_row)
            current_row = [box]
            row_anchor_cy = box.cy
    if current_row:
        rows.append(current_row)

    return [
        (start_x, int(round(median([box.cy for box in row]))), end_x, int(round(median([box.cy for box in row]))))
        for row in rows
    ]


def get_preset_swipe_paths(
    app: "AppProcessor",
    *,
    card_labels: Sequence[str],
) -> list[tuple[int, int, int, int]]:
    boxes = list(app.latest_results.filter_by_labels(list(card_labels)))
    if not boxes:
        boxes = list(app.latest_results.filter_by_label(BaseUILabels.BLANK_SLOT))
    if not boxes:
        raise TimeoutError("未识别到可切换编组的卡片区域")

    frame_width = app.latest_frame.shape[1]
    paths = build_preset_swipe_paths(boxes, frame_width=frame_width)
    if not paths:
        raise TimeoutError("未能计算编组横滑路径")
    return paths


def select_preset_by_horizontal_swipe(
    app: "AppProcessor",
    target_index: int,
    *,
    card_labels: Sequence[str],
    description: str,
    max_swipes: int | None = None,
) -> bool:
    current_info = get_current_preset_index(app)
    if current_info is None:
        raise TimeoutError(f"{description}页面未识别到编组编号")

    current_index, total = current_info
    if target_index < 1 or target_index > total:
        raise ValueError(f"{description}预设编号超出范围: {target_index} (1-{total})")
    if current_index == target_index:
        logger.debug(f"{description}已在目标编组 {current_index}/{total}")
        return True

    left_swipe_increases = True
    stuck_attempts = 0
    swipe_limit = max_swipes or max(abs(target_index - current_index) * 2 + 4, 6)

    for attempt in range(1, swipe_limit + 1):
        paths = get_preset_swipe_paths(app, card_labels=card_labels)
        start_x, start_y, end_x, end_y = paths[(attempt - 1) % len(paths)]
        should_increase = target_index > current_index
        swipe_left = should_increase if left_swipe_increases else not should_increase
        if swipe_left:
            inertial_swipe(app, start_x, start_y, end_x, end_y, duration=0.35, settle_timeout=4.5)
        else:
            inertial_swipe(app, end_x, start_y, start_x, end_y, duration=0.35, settle_timeout=4.5)

        updated_info = get_current_preset_index(app)
        if updated_info is None:
            raise TimeoutError(f"{description}页面横滑后未识别到新的编组编号")

        updated_index, updated_total = updated_info
        total = updated_total
        if updated_index == target_index:
            logger.debug(f"{description}切换到目标编组 {updated_index}/{total}")
            return True

        if updated_index != current_index:
            if swipe_left:
                left_swipe_increases = updated_index > current_index
            else:
                left_swipe_increases = updated_index < current_index
            logger.debug(
                f"{description}横滑后编组变化: {current_index}/{total} -> {updated_index}/{total}, "
                f"left_swipe_increases={left_swipe_increases}"
            )
            current_index = updated_index
            stuck_attempts = 0
            continue

        stuck_attempts += 1
        logger.debug(
            f"{description}横滑后编组编号未变化: {current_index}/{total}, "
            f"attempt={attempt}/{swipe_limit}, path_index={(attempt - 1) % len(paths)}"
        )
        if stuck_attempts >= len(paths):
            left_swipe_increases = not left_swipe_increases
            stuck_attempts = 0

    raise TimeoutError(
        f"{description}未能切换到目标编组 {target_index}/{total}，当前仍为 {current_index}/{total}"
    )


def find_button(
    app: "AppProcessor",
    text: str,
    *,
    fuzz_threshold: float = 70,
    use_contains: bool = True,
) -> Button | None:
    return get_buttons(app).get_button_by_text(
        text,
        match_config=MatchConfig(fuzz_threshold=fuzz_threshold, use_contains=use_contains, normalize=True),
    )


def has_button(
    app: "AppProcessor",
    text: str,
    *,
    fuzz_threshold: float = 70,
    use_contains: bool = True,
) -> bool:
    return find_button(app, text, fuzz_threshold=fuzz_threshold, use_contains=use_contains) is not None


def wait_frame_stable(app: "AppProcessor", timeout: float = 4.0) -> None:
    app.game_utils.wait_frame_stable(
        threshold=0.985,
        stable_count=2,
        timeout=timeout,
    )


def inertial_swipe(
    app: "AppProcessor",
    start_x: int,
    start_y: int,
    end_x: int,
    end_y: int,
    *,
    duration: float = 0.45,
    settle_timeout: float = 4.0,
    hold_end: float = 0.15,
    ease: str | None = "out_quad",
) -> None:
    """执行带惯性抑制的滑动。

    通过 ease="out_quad" 使手指到达终点前逐渐减速（缓出曲线），
    再通过 hold_end 在终点短暂驻留后才松开手指，
    让游戏物理引擎将触点速度归零，从而消除惯性滑过。
    """
    app.device.swipe(
        start_x, start_y, end_x, end_y,
        duration=duration, offset_y=0,
        hold_end=hold_end, ease=ease,
    )
    sleep(0.1)
    wait_frame_stable(app, timeout=settle_timeout)


def is_final_confirm_page(app: "AppProcessor") -> bool:
    if has_button(app, ButtonText.AUTO_SELECT, fuzz_threshold=75):
        return False
    if has_button(app, ButtonText.NEXT, fuzz_threshold=75):
        return False
    if has_button(app, ButtonText.RESET, fuzz_threshold=75):
        return False

    has_detail_button = has_button(app, ProduceText.FORMATION_DETAILS, fuzz_threshold=68)
    has_start_button = has_button(app, ButtonText.PRODUCE_START, fuzz_threshold=65)
    has_context = any(
        app.latest_results.exists_label(label)
        for label in (
            BaseUILabels.SUPPORT_CARD,
            BaseUILabels.MEMORY_CARD,
            BaseUILabels.SPECIAL_ITEMS,
        )
    )
    return bool(has_detail_button and has_start_button and has_context)


def wait_for_final_confirm_page(app: "AppProcessor", timeout: float = 15.0) -> bool:
    end_time = time() + timeout
    while time() < end_time:
        if is_final_confirm_page(app):
            wait_frame_stable(app, timeout=3.0)
            return True
        sleep(0.4)
    return False


def is_memory_selection_page(app: "AppProcessor") -> bool:
    if has_button(app, ButtonText.PRODUCE_START, fuzz_threshold=65):
        return False
    if not has_button(app, ButtonText.NEXT, fuzz_threshold=75):
        return False
    if not has_button(app, ButtonText.AUTO_SELECT, fuzz_threshold=75):
        return False
    if not has_button(app, ButtonText.RESET, fuzz_threshold=75):
        return False
    if not has_button(app, ProduceText.FORMATION_DETAILS, fuzz_threshold=68):
        return False
    return bool(app.latest_results.exists_label(BaseUILabels.MEMORY_CARD))


def wait_for_memory_selection_page(app: "AppProcessor", timeout: float = 12.0) -> bool:
    end_time = time() + timeout
    while time() < end_time:
        if is_memory_selection_page(app):
            wait_frame_stable(app, timeout=3.0)
            return True
        sleep(0.4)
    return False


def click_modal_action_with_retry(
    app: "AppProcessor",
    modal: "Modal | None" = None,
    *,
    prefer_confirm: bool = True,
    retries: int = 3,
    timeout: float = 5.0,
    action_name: str = "modal action",
) -> bool:
    current_modal = modal
    for attempt in range(1, retries + 1):
        if current_modal is None:
            current_modal = app.game_utils.try_get_modal(no_body=True)
        if current_modal is None:
            return True

        button = current_modal.confirm_button if prefer_confirm else current_modal.cancel_button
        if button is None:
            button = current_modal.cancel_button or current_modal.confirm_button
        if button is None:
            logger.warning(f"{action_name}: modal {current_modal.modal_title!r} has no actionable button")
            return False

        if app.game_utils.click_modal_button_and_wait_transition(
            button,
            previous_modal_title=current_modal.modal_title,
            timeout=timeout,
            interval=0.2,
        ):
            wait_frame_stable(app, timeout=min(timeout, 3.0))
            return True

        logger.warning(
            f"{action_name}: modal {current_modal.modal_title!r} did not transition "
            f"after attempt {attempt}/{retries}"
        )
        sleep(0.5)
        current_modal = app.game_utils.try_get_modal(no_body=True)

    return False


def click_top_right_action(app: "AppProcessor", *, timeout: float = 6.0) -> bool:
    buttons = get_buttons(app)
    candidates = [button for button in buttons if button.cx >= 720 and button.cy <= 280]
    candidates.sort(key=lambda button: (button.cy, -button.cx))
    if not candidates:
        return False
    return app.game_utils.click_element_and_wait_trigger(candidates[0], timeout=timeout)


def _button_like_boxes(results) -> list:
    if results is None:
        return []
    boxes = []
    for label in (
        BaseUILabels.BUTTON,
        ProducerLabels.CONFIRM_BUTTON,
        ProducerLabels.CANCEL_BUTTON,
        BaseUILabels.PLOT_FAST_FORWARD_BUTTON,
        BaseUILabels.SKIP_BUTTON,
    ):
        boxes.extend(list(results.filter_by_label(label)))
    deduped: list = []
    seen: set[tuple[int, int, int, int, str]] = set()
    for box in boxes:
        key = (int(box.x), int(box.y), int(box.w), int(box.h), str(box.label))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(box)
    return deduped


def collect_button_like_texts(results) -> list[str]:
    texts: list[str] = []
    debugger = DebugTools()
    for box in _button_like_boxes(results):
        text = ocr_text(getattr(box, "frame", None))
        if text:
            texts.append(text)
            debugger.add_box(
                int(box.x),
                int(box.y),
                int(box.w),
                int(box.h),
                label=f"button:{text[:20]}",
                color=(0, 200, 255),
                alpha=0.12,
                duration=2.5,
                font_size=18,
            )
    return texts


def collect_frame_text(results) -> str:
    if results is None:
        return ""
    return ocr_text(getattr(results, "frame", None))


def _contains_text(text: str, *tokens: str) -> bool:
    normalized = normalize_text(text)
    if not normalized:
        return False
    return any(normalize_text(token) in normalized for token in tokens if token)


def _button_text_matches(button_texts: list[str], *tokens: str) -> bool:
    return any(_contains_text(text, *tokens) for text in button_texts)


def _looks_like_result_chain(results) -> bool:
    """结果链 / 记忆生成链的 OCR 兜底识别。

    这些页面在 producer 模型下经常只有少量按钮或根本没有可分辨标签，
    单靠 YOLO 不足以稳定分流，因此在低频的 unknown 分支中叠加 OCR 文本。
    """
    button_texts = collect_button_like_texts(results)
    frame_text = collect_frame_text(results)

    if _button_text_matches(button_texts, ButtonText.REGENERATE, ButtonText.COMPLETE):
        return True
    if _button_text_matches(button_texts, ButtonText.GENERATE) and _contains_text(frame_text, ProduceText.MEMORY_SELECT):
        return True
    if _contains_text(
        frame_text,
        ProduceText.FAILED,
        ProduceText.FINAL_PRODUCE_EVALUATION,
        ProduceText.MEMORY_GENERATION_COMPLETE,
        ProduceText.MEMORY_SELECT,
        ProduceText.ACHIEVEMENT_PROGRESS,
        ProduceText.EVENT_REWARD_PROGRESS,
        ProduceText.EVENT_POINT,
        ProduceText.PRODUCE_RESULT,
        ProduceText.REWARD_ITEMS,
    ):
        return True
    return False


# ──────────────────────────────────────────────────────────
# Gameplay 阶段检测辅助
# ──────────────────────────────────────────────────────────

def classify_gameplay_phase(results, *, ctx: "ProduceContext | None" = None) -> str:
    """根据 PRODUCER YOLO 结果判定当前 gameplay phase。"""
    if results is None:
        return GameplayPhase.UNKNOWN

    # ── 横画面检测（ライブ演出）──
    # ライブ演出中はゲーム画面が横向き（width > height）になる。
    # YOLO は縦画面用にトレーニングされているため、横画面ではラベルが検出されない。
    frame = getattr(results, "frame", None)
    if frame is not None and frame.shape[1] > frame.shape[0] * 1.3:
        return GameplayPhase.LIVE_PERFORMANCE

    has_action = results.exists_label(ProducerLabels.PC_ACTION)
    has_action_info = results.exists_label(ProducerLabels.PC_ACTION_INFO)
    has_recommend = results.exists_label(ProducerLabels.PC_RECOMMEND_ACTION)
    has_skill_card = any(
        results.exists_label(label)
        for label in (
            ProducerLabels.SKILL_CARD_ACTIVE,
            ProducerLabels.SKILL_CARD_MENTAL,
            ProducerLabels.SKILL_CARD_TRAP,
        )
    )
    has_skill_card_info = results.exists_label(ProducerLabels.SKILL_CARD_INFO)
    has_training_score = results.exists_label(ProducerLabels.PC_TRAINING_SCORE)
    has_training_remaining = results.exists_label(ProducerLabels.PC_TRAINING_REMAINING)
    has_options = results.exists_label(ProducerLabels.UNIVERSAL_OPTIONS)
    has_p_drink = results.exists_label(ProducerLabels.P_DRINK)
    has_modal_header = results.exists_label(ProducerLabels.MODAL_HEADER)
    has_skip_button = results.exists_label(ProducerLabels.SKIP_BUTTON)
    has_fast_forward = results.exists_label(ProducerLabels.PLOT_FAST_FORWARD_BUTTON)
    has_progress = results.exists_label(ProducerLabels.PC_PROGRESS)
    has_button = results.exists_label(BaseUILabels.BUTTON)
    has_confirm = results.exists_label(ProducerLabels.CONFIRM_BUTTON)
    has_disable = results.exists_label(ProducerLabels.DISABLE_BUTTON)
    has_cancel = results.exists_label(ProducerLabels.CANCEL_BUTTON)
    has_card_exchange = results.exists_label(ProducerLabels.CARD_ITEM_EXCHANGE)
    has_enhancement = results.exists_label(ProducerLabels.PC_SKILL_CARD_ENHANCEMENT)
    has_remove = results.exists_label(ProducerLabels.PC_SKILL_CARD_REMOVE)
    has_bonus_indicator = results.exists_label(ProducerLabels.PC_BONUS_INDICATOR)
    has_pc_skip = results.exists_label(ProducerLabels.PC_SKIP) or results.exists_label(BaseUILabels.SKIP_BUTTON)
    has_special_item = results.exists_label(ProducerLabels.SPECIAL_ITEM)
    last_consult_position = str(getattr(ctx, "last_stable_position", "") or "")

    # 弹窗判定：排除 P_DRINK 面板（其标题也被检测为 Modal Header）
    if has_modal_header and not has_p_drink:
        return GameplayPhase.MODAL
    # 相談交换页：出现兑换卡、強化、削除任一元素
    if (has_card_exchange or has_enhancement or has_remove) and not has_training_score:
        return GameplayPhase.CONSULT
    # 相談子流程（強化/削除预览页）与 skill_reward 外观相似，需要借助上一个稳定位置反解。
    if (
        ctx is not None
        and last_consult_position.startswith(CONSULT_POSITION_PREFIX)
        and has_skill_card
        and not has_action
        and not has_training_score
        and (has_button or has_confirm or has_disable or has_cancel)
    ):
        return GameplayPhase.CONSULT
    # Pアイテム選択：Special Item 出现且无技能卡、无行动
    if has_special_item and not has_skill_card and not has_action:
        return GameplayPhase.ITEM_SELECT
    if has_skill_card and (has_bonus_indicator or has_pc_skip) and not has_action and not has_training_score:
        return GameplayPhase.EXAM
    if has_skill_card and (has_training_score or has_training_remaining):
        return GameplayPhase.LESSON
    # 手牌为空的 LESSON/EXAM：HUD 存在但没有技能卡（0枚状态，回合自动前进）
    if not has_skill_card and (has_training_score or has_training_remaining) and not has_action:
        return GameplayPhase.LESSON
    if not has_skill_card and has_bonus_indicator and not has_action and not has_training_score:
        return GameplayPhase.EXAM
    # 结果链检测：至少需要一个可交互元素（按钮/确认/跳过）才认定为结果画面，
    # 避免过渡帧的 OCR 噪声导致误判
    has_any_interactive = has_button or has_confirm or has_disable or has_cancel or has_skip_button or has_pc_skip
    if has_any_interactive and _looks_like_result_chain(results):
        return GameplayPhase.RESULT
    if (has_skill_card or has_skill_card_info) and not has_action and not has_training_score:
        # 有按钮 → 技能奖励选择; 无按钮但有卡片 → 技能奖励展示（单卡/预览）
        return GameplayPhase.SKILL_REWARD

    # P_DRINK 弹窗（cy < 85% 区分行程栏底部的P饮料图标）
    if has_p_drink and not has_action and not has_skill_card:
        frame_height = results.frame.shape[0] if getattr(results, "frame", None) is not None else 2340
        p_drink_boxes = results.filter_by_label(ProducerLabels.P_DRINK)
        if any(box.cy < frame_height * 0.85 for box in p_drink_boxes):
            return GameplayPhase.P_DRINK

    # ──── Progress 一级判定 ────
    # Producer Challenge: Progress 是行程页面的唯一确定标识。
    # 有 Progress → 行程画面上下文（含行程触发的对话事件、おでかけ选项等），
    # 由 SCHEDULE handler 统一处理，避免误触发纯剧情对话的快进逻辑。
    if has_progress and not has_skill_card and not has_training_score and not has_training_remaining:
        return GameplayPhase.SCHEDULE

    # ──── 纯对话（非行程上下文，Progress 不可见） ────
    if has_options and not has_action and not has_action_info:
        return GameplayPhase.DIALOGUE
    if has_options and has_action_info:
        return GameplayPhase.DIALOGUE
    if has_fast_forward and not has_action and not has_action_info and not has_skill_card:
        return GameplayPhase.DIALOGUE
    # Skip Button 单独出现（おでかけ剧情等）也属于对话，不能误判为结果画面
    if has_skip_button and not has_action and not has_skill_card:
        return GameplayPhase.DIALOGUE

    return GameplayPhase.UNKNOWN


def detect_gameplay_phase(app: "AppProcessor", ctx: "ProduceContext | None" = None) -> str:
    return classify_gameplay_phase(app.latest_results, ctx=ctx)


def classify_pipeline_position(
    results,
    *,
    modal_title: str | None = None,
    final_confirm: bool = False,
    ctx: "ProduceContext | None" = None,
) -> str:
    if final_confirm:
        return GameplayPosition.FINAL_CONFIRM

    phase = classify_gameplay_phase(results, ctx=ctx)
    if phase == GameplayPhase.MODAL:
        modal_title = modal_title or ""
        if string_match(modal_title, ProduceText.VOICE_PLAYBACK_CONFIRM, MatchConfig(fuzz_threshold=65, normalize=True)):
            return GameplayPosition.STARTUP_MODAL_VOICE
        if string_match(modal_title, ProduceText.COMMU_FAST_FORWARD, MatchConfig(fuzz_threshold=65, normalize=True)):
            return GameplayPosition.STARTUP_MODAL_FAST_FORWARD
        if string_match(modal_title, ProduceText.PRODUCE_SKIP_SETTINGS, MatchConfig(fuzz_threshold=65, normalize=True)):
            return GameplayPosition.STARTUP_MODAL_SKIP_SETTINGS
        if _contains_text(modal_title, ProduceText.END_TURN_CONFIRM):
            return GameplayPosition.EXAM_END_TURN_CONFIRM_MODAL
        if _contains_text(modal_title, ProduceText.EXAM_RESULT_RETRY_CONFIRM):
            return GameplayPosition.EXAM_RETRY_CONFIRM_MODAL
        if _contains_text(modal_title, ProduceText.MEMORY_CONFIRM):
            return GameplayPosition.MEMORY_CONFIRM_MODAL
        if _contains_text(modal_title, ProduceText.MEMORY_REGEN_CONFIRM):
            return GameplayPosition.MEMORY_REGEN_CONFIRM_MODAL
        if _contains_text(modal_title, ProduceText.UNREAD_COMMU_FAST_FORWARD_CONFIRM):
            return GameplayPosition.FAST_FORWARD_CONFIRM_MODAL
        if ProduceText.P_DRINK in modal_title and ProduceText.DETAIL in modal_title:
            return GameplayPosition.P_DRINK_DETAIL
        if ProduceText.DETAIL in modal_title:
            return GameplayPosition.DETAIL_MODAL
        last_position = str(getattr(ctx, "last_stable_position", "") or "")
        if last_position.startswith(CONSULT_ENHANCEMENT_POSITION_PREFIX):
            return GameplayPosition.CONSULT_ENHANCEMENT_CONFIRM_MODAL
        return GameplayPosition.GAMEPLAY_MODAL

    if results is None:
        return GameplayPosition.UNKNOWN

    if phase == GameplayPhase.SCHEDULE:
        has_pc_action = results.exists_label(ProducerLabels.PC_ACTION)
        has_ff = results.exists_label(BaseUILabels.PLOT_FAST_FORWARD_BUTTON)
        has_opts = results.exists_label(ProducerLabels.UNIVERSAL_OPTIONS)

        # 行程事件对话选项（おでかけ等）— 有选项且无行程行动按钮
        if has_opts and not has_pc_action:
            return GameplayPosition.SCHEDULE_EVENT_OPTIONS
        if results.exists_label(ProducerLabels.PC_ACTION_INFO):
            return GameplayPosition.SCHEDULE_SELECTED
        if results.exists_label(ProducerLabels.PC_RECOMMEND_ACTION):
            return GameplayPosition.SCHEDULE_RECOMMEND
        # 行程事件対話テキスト（快進ボタンあり、選択肢なし、行動なし）
        if has_ff and not has_opts and not has_pc_action:
            return GameplayPosition.SCHEDULE_EVENT_DIALOGUE
        return GameplayPosition.SCHEDULE_IDLE

    if phase == GameplayPhase.LESSON:
        if results.exists_label(ProducerLabels.SKILL_CARD_INFO):
            return GameplayPosition.LESSON_SELECTED
        return GameplayPosition.LESSON_IDLE

    if phase == GameplayPhase.DIALOGUE:
        if results.exists_label(ProducerLabels.UNIVERSAL_OPTIONS):
            return GameplayPosition.DIALOGUE_OPTIONS
        return GameplayPosition.DIALOGUE_CONTINUE

    if phase == GameplayPhase.P_DRINK:
        if results.exists_label(ProducerLabels.CONFIRM_BUTTON):
            return GameplayPosition.P_DRINK_SELECTED
        if results.exists_label(ProducerLabels.DISABLE_BUTTON):
            return GameplayPosition.P_DRINK_IDLE
        return GameplayPosition.P_DRINK_IDLE

    if phase == GameplayPhase.SKILL_REWARD:
        if results.exists_label(ProducerLabels.CONFIRM_BUTTON):
            return GameplayPosition.SKILL_REWARD_SELECTED
        if results.exists_label(ProducerLabels.DISABLE_BUTTON):
            return GameplayPosition.SKILL_REWARD_IDLE
        if results.exists_label(BaseUILabels.BUTTON):
            return GameplayPosition.SKILL_REWARD_SELECTED
        return GameplayPosition.SKILL_REWARD_IDLE

    if phase == GameplayPhase.CONSULT:
        has_enhance = results.exists_label(ProducerLabels.PC_SKILL_CARD_ENHANCEMENT)
        has_remove = results.exists_label(ProducerLabels.PC_SKILL_CARD_REMOVE)
        has_exchange = results.exists_label(ProducerLabels.CARD_ITEM_EXCHANGE)
        has_consult_cards = any(
            results.exists_label(label)
            for label in (
                ProducerLabels.SKILL_CARD_ACTIVE,
                ProducerLabels.SKILL_CARD_MENTAL,
                ProducerLabels.SKILL_CARD_TRAP,
            )
        )
        if has_enhance or has_remove or has_exchange:
            return GameplayPosition.CONSULT_EXCHANGE
        if has_consult_cards:
            if results.exists_label(ProducerLabels.CONFIRM_BUTTON) or results.exists_label(BaseUILabels.BUTTON):
                return GameplayPosition.CONSULT_ENHANCEMENT_READY
            return GameplayPosition.CONSULT_ENHANCEMENT_PREVIEW
        return GameplayPosition.CONSULT_IDLE

    if phase == GameplayPhase.ITEM_SELECT:
        # Disable Button → 未选择; Confirm Button → 已选择
        if results.exists_label(ProducerLabels.CONFIRM_BUTTON) or results.exists_label(BaseUILabels.BUTTON):
            return GameplayPosition.ITEM_SELECT_SELECTED
        return GameplayPosition.ITEM_SELECT_IDLE

    if phase == GameplayPhase.EXAM:
        if results.exists_label(ProducerLabels.SKILL_CARD_INFO):
            return GameplayPosition.EXAM_SELECTED
        return GameplayPosition.EXAM_IDLE

    if phase == GameplayPhase.RESULT:
        frame_text = collect_frame_text(results)
        button_texts = collect_button_like_texts(results)
        if _contains_text(frame_text, ProduceText.FAILED):
            return GameplayPosition.RESULT_EXAM_FAILURE
        if _contains_text(frame_text, ProduceText.FINAL_PRODUCE_EVALUATION):
            return GameplayPosition.RESULT_FINAL_EVALUATION
        if _contains_text(frame_text, ProduceText.MEMORY_SELECT) or _button_text_matches(
            button_texts,
            ButtonText.REGENERATE,
            "メモリー一覧",
        ):
            return GameplayPosition.RESULT_MEMORY_PAGE
        if _contains_text(frame_text, ProduceText.ACHIEVEMENT_PROGRESS):
            return GameplayPosition.RESULT_ACHIEVEMENT_PROGRESS
        if _contains_text(frame_text, ProduceText.EVENT_REWARD_PROGRESS, ProduceText.EVENT_POINT):
            return GameplayPosition.RESULT_EVENT_REWARD_PROGRESS
        if _button_text_matches(button_texts, ButtonText.NEXT) and _button_text_matches(button_texts, ProduceText.PRODUCE_HISTORY):
            return GameplayPosition.RESULT_REWARD_SUMMARY
        if _contains_text(frame_text, ProduceText.PRODUCE_RESULT):
            return GameplayPosition.RESULT_REWARD_SUMMARY
        if _button_text_matches(button_texts, ButtonText.GENERATE):
            return GameplayPosition.RESULT_MEMORY_GENERATION
        if _button_text_matches(button_texts, ButtonText.COMPLETE):
            return GameplayPosition.RESULT_FINAL_EVALUATION
        return GameplayPosition.RESULT

    if not results:
        return GameplayPosition.TRANSITION_EMPTY

    has_hud = any(
        results.exists_label(label)
        for label in (
            ProducerLabels.PC_PROGRESS,
            ProducerLabels.PC_TRAINING_SCORE,
            ProducerLabels.PC_TRAINING_REMAINING,
            ProducerLabels.PC_STAMINA,
            ProducerLabels.PC_P_POINT,
            ProducerLabels.PC_TARGET,
        )
    )
    if has_hud:
        return GameplayPosition.TRANSITION_HUD
    # 无 HUD 标签但画面非空（例如过场动画、外部界面）→ 统一归为 TRANSITION_EMPTY
    return GameplayPosition.TRANSITION_EMPTY


def get_pipeline_position(app: "AppProcessor", ctx: "ProduceContext | None" = None) -> str:
    modal_title: str | None = None
    results = app.latest_results
    if results and results.exists_label(ProducerLabels.MODAL_HEADER):
        modal = app.game_utils.try_get_modal(no_body=True)
        if modal is not None:
            modal_title = modal.modal_title
    return classify_pipeline_position(
        results,
        modal_title=modal_title,
        final_confirm=is_final_confirm_page(app),
        ctx=ctx,
    )


def click_recommend_action(app: "AppProcessor", ctx: "ProduceContext | None" = None) -> str | None:
    if ctx is None:
        return None
    from src.core.tasks.producer_challenge.gameplay.schedule import execute_schedule_step

    result = execute_schedule_step(app, ctx, position=get_pipeline_position(app))
    return result.status if result else None


def handle_skill_card_selection(app: "AppProcessor", ctx: "ProduceContext | None" = None) -> str | None:
    if ctx is None:
        return None
    from src.core.tasks.producer_challenge.gameplay.lesson import execute_lesson_step

    result = execute_lesson_step(app, ctx, position=get_pipeline_position(app))
    return result.status if result else None


def _click_preferred_confirmation(app: "AppProcessor") -> bool:
    confirm_boxes = app.latest_results.filter_by_label(ProducerLabels.CONFIRM_BUTTON)
    if confirm_boxes:
        app.device.click_element(confirm_boxes.first())
        return True

    buttons = app.latest_results.filter_by_label(BaseUILabels.BUTTON)
    if buttons:
        app.device.click_element(max(buttons, key=lambda button: button.cy))
        return True
    return False


def handle_p_drink_select(app: "AppProcessor", ctx: "ProduceContext | None" = None) -> str | None:
    position = get_pipeline_position(app)
    if position not in P_DRINK_SELECTION_POSITIONS:
        return None

    if position == GameplayPosition.P_DRINK_SELECTED:
        if not _click_preferred_confirmation(app):
            return None
        if ctx is not None:
            ctx.record_operation(
                "confirm_p_drink",
                target=ctx.pending_p_drink_label or "p_drink",
                details={"index": ctx.pending_p_drink_index},
            )
            ctx.clear_p_drink_pending()
        sleep(1.0)
        return "confirmed"

    drinks = sorted(app.latest_results.filter_by_label(ProducerLabels.P_DRINK), key=lambda item: item.cx)
    if not drinks:
        return None

    target_index = 0
    if ctx is not None:
        decision = invoke_decision_strategy(ctx.p_drink_strategy, app, ctx, drinks)
        target_index = resolve_candidate_index(decision, drinks, default_index=ctx.pending_p_drink_index or 0)

    target = drinks[target_index]
    app.device.click_element(target)
    if ctx is not None:
        ctx.pending_p_drink_index = target_index
        ctx.pending_p_drink_label = ocr_text(target.frame) or f"p_drink_{target_index + 1}"
        ctx.record_operation(
            "select_p_drink",
            target=ctx.pending_p_drink_label,
            details={"index": target_index},
        )
    sleep(0.8)
    return "selected"


def handle_skill_reward_selection(app: "AppProcessor", ctx: "ProduceContext | None" = None) -> str | None:
    position = get_pipeline_position(app)
    if position not in SKILL_REWARD_SELECTION_POSITIONS:
        return None

    if position == GameplayPosition.SKILL_REWARD_SELECTED:
        if not _click_preferred_confirmation(app):
            return None
        if ctx is not None:
            ctx.record_operation(
                "confirm_skill_reward",
                target=ctx.pending_skill_reward_label or "skill_reward",
                details={"index": ctx.pending_skill_reward_index},
            )
            ctx.clear_skill_reward_pending()
        sleep(1.0)
        return "confirmed"

    candidates = []
    for label in (
        ProducerLabels.SKILL_CARD_ACTIVE,
        ProducerLabels.SKILL_CARD_MENTAL,
        ProducerLabels.SKILL_CARD_TRAP,
        ProducerLabels.SKILL_CARD_INFO,
    ):
        candidates.extend(app.latest_results.filter_by_label(label))
    candidates = sorted(candidates, key=lambda item: item.cx)
    if not candidates:
        return None

    target_index = 0
    if ctx is not None:
        decision = invoke_decision_strategy(ctx.skill_reward_strategy, app, ctx, candidates)
        target_index = resolve_candidate_index(decision, candidates, default_index=ctx.pending_skill_reward_index or 0)

    target = candidates[target_index]
    app.device.click_element(target)
    if ctx is not None:
        ctx.pending_skill_reward_index = target_index
        ctx.pending_skill_reward_label = ocr_text(target.frame) or f"skill_reward_{target_index + 1}"
        ctx.record_operation(
            "select_skill_reward",
            target=ctx.pending_skill_reward_label,
            details={"index": target_index},
        )
    sleep(0.8)
    return "selected"


def go_back_in_gameplay(app: "AppProcessor") -> bool:
    position = get_pipeline_position(app)
    if position in GAMEPLAY_MODAL_POSITIONS:
        modal = app.game_utils.try_get_modal(no_body=True)
        if modal is not None:
            prefer_confirm = position not in {
                GameplayPosition.P_DRINK_DETAIL,
                GameplayPosition.DETAIL_MODAL,
            }
            return click_modal_action_with_retry(
                app,
                modal,
                prefer_confirm=prefer_confirm,
                retries=2,
                timeout=4.0,
                action_name=f"go_back_in_gameplay[{position}]",
            )

    if close_buttons := app.latest_results.filter_by_label(BaseUILabels.CLOSE_BUTTON):
        return app.game_utils.click_element_and_wait_trigger(close_buttons.first(), timeout=3.0)
    if back_buttons := app.latest_results.filter_by_label(BaseUILabels.BACK_BTN):
        return app.game_utils.click_element_and_wait_trigger(back_buttons.first(), timeout=3.0)

    close_button = find_button(app, ButtonText.CLOSE, fuzz_threshold=60)
    if close_button is not None:
        return app.game_utils.click_element_and_wait_trigger(close_button, timeout=3.0)

    cancel_button = (
        find_button(app, ButtonText.CLOSE, fuzz_threshold=60)
        or find_button(app, ButtonText.CANCEL, fuzz_threshold=60)
    )
    if cancel_button is not None:
        return app.game_utils.click_element_and_wait_trigger(cancel_button, timeout=3.0)

    return False


def go_home_from_gameplay(app: "AppProcessor", *, max_try: int = 4) -> bool:
    for _ in range(max_try):
        if app.latest_results.exists_label(BaseUILabels.TAB_HOME):
            return True

        if home_buttons := app.latest_results.filter_by_label(BaseUILabels.GO_HOME_BTN):
            if app.game_utils.click_element_and_wait_trigger(home_buttons.first(), timeout=3.0):
                sleep(1.0)
                continue

        text_button = (
            find_button(app, ButtonText.SAVE_AND_SUSPEND, fuzz_threshold=60)
            or find_button(app, ButtonText.HOME, fuzz_threshold=60)
            or find_button(app, ButtonText.RETIRE, fuzz_threshold=60)
        )
        if text_button is not None:
            if app.game_utils.click_element_and_wait_trigger(text_button, timeout=3.0):
                sleep(1.0)
                continue

        if go_back_in_gameplay(app):
            sleep(0.8)
            continue

        if click_top_right_action(app, timeout=2.0):
            sleep(1.0)
            continue

        break
    return app.latest_results.exists_label(BaseUILabels.TAB_HOME)
