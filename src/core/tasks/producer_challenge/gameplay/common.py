from __future__ import annotations

from inspect import signature
from typing import Any, Iterable, Sequence

from src.core.inference.ocr_engine import OCRService
from src.constants.game.text.produce_text import ProduceText

_ocr_service = OCRService()

_VOCAL_TOKENS = (ProduceText.VOCAL, "vocal", "vo")
_DANCE_TOKENS = (ProduceText.DANCE, "dance", "da")
_VISUAL_TOKENS = (ProduceText.VISUAL, "visual", "vi")


def ocr_text(image) -> str:
    if image is None or getattr(image, "size", 0) <= 0:
        return ""
    return "".join(item.text for item in _ocr_service.ocr(image))


def normalize_text(text: str | None) -> str:
    return "".join(str(text or "").lower().split())


def infer_param_kind(text: str | None) -> str:
    normalized = normalize_text(text)
    if any(token in normalized for token in _VOCAL_TOKENS):
        return "vocal"
    if any(token in normalized for token in _DANCE_TOKENS):
        return "dance"
    if any(token in normalized for token in _VISUAL_TOKENS):
        return "visual"
    return "unknown"


def get_frame_size(app) -> tuple[int, int]:
    frame = getattr(app, "latest_frame", None)
    if frame is None:
        return 1080, 2340
    height, width = frame.shape[:2]
    return int(width), int(height)


def click_relative_point(
    app,
    *,
    x_ratio: float,
    y_ratio: float,
    label: str = "",
) -> tuple[int, int]:
    width, height = get_frame_size(app)
    x = max(0, min(width - 1, int(round(width * x_ratio))))
    y = max(0, min(height - 1, int(round(height * y_ratio))))
    app.device.click(x, y, label)
    return x, y


def invoke_decision_strategy(
    strategy,
    app,
    ctx,
    candidates: Sequence[Any],
    *,
    decision_state: Any = None,
) -> Any:
    if strategy is None:
        return None
    try:
        parameters = list(signature(strategy).parameters.values())
        parameter_count = len(parameters)
    except (TypeError, ValueError):
        parameters = []
        parameter_count = 0

    if parameter_count >= 4:
        return strategy(app, ctx, candidates, decision_state)
    if parameter_count >= 3:
        last_param_name = parameters[2].name.lower()
        if decision_state is not None and last_param_name in {
            "state",
            "snapshot",
            "payload",
            "decision_state",
            "game_state",
            "input",
        }:
            return strategy(app, ctx, decision_state)
        return strategy(app, ctx, candidates)
    if parameter_count == 2:
        return strategy(app, ctx)
    if parameter_count == 1:
        param_name = parameters[0].name.lower() if parameters else ""
        if decision_state is not None and param_name in {
            "state",
            "snapshot",
            "payload",
            "decision_state",
            "game_state",
            "input",
        }:
            return strategy(decision_state)
        return strategy(candidates)
    if parameter_count == 0:
        return strategy()
    return strategy(app, ctx)


def resolve_candidate_index(
    decision: Any,
    candidates: Sequence[Any],
    *,
    default_index: int = 0,
) -> int:
    if not candidates:
        raise ValueError("候选列表为空")

    if isinstance(decision, int):
        if 0 <= decision < len(candidates):
            return decision

    if hasattr(decision, "index"):
        candidate_index = getattr(decision, "index")
        if isinstance(candidate_index, int) and 0 <= candidate_index < len(candidates):
            return candidate_index

    if isinstance(decision, dict):
        for key in ("action_index", "index", "candidate_index"):
            candidate_index = decision.get(key)
            if isinstance(candidate_index, int) and 0 <= candidate_index < len(candidates):
                return candidate_index
        for key in ("candidate_id", "action_id", "db_id", "id", "action_type", "label", "title", "name", "kind"):
            candidate_index = _match_candidate_key(str(decision.get(key) or ""), candidates)
            if candidate_index is not None:
                return candidate_index

    for attr_name in ("action_index", "candidate_index", "choice_index"):
        if hasattr(decision, attr_name):
            candidate_index = getattr(decision, attr_name)
            if isinstance(candidate_index, int) and 0 <= candidate_index < len(candidates):
                return candidate_index
    for attr_name in ("candidate_id", "action_id", "db_id", "id", "action_type", "label", "title", "name", "kind"):
        if hasattr(decision, attr_name):
            candidate_index = _match_candidate_key(str(getattr(decision, attr_name) or ""), candidates)
            if candidate_index is not None:
                return candidate_index

    normalized_decision = normalize_text(decision) if isinstance(decision, str) else ""
    if normalized_decision:
        matched_index = _match_candidate_key(normalized_decision, candidates, already_normalized=True)
        if matched_index is not None:
            return matched_index

    return max(0, min(default_index, len(candidates) - 1))


def _match_candidate_key(
    value: str,
    candidates: Sequence[Any],
    *,
    already_normalized: bool = False,
) -> int | None:
    normalized_value = value if already_normalized else normalize_text(value)
    if not normalized_value:
        return None
    for idx, candidate in enumerate(candidates):
        for attr_name in ("action_id", "db_id", "action_type", "title", "kind", "label", "name"):
            candidate_value = normalize_text(getattr(candidate, attr_name, ""))
            if candidate_value and (
                normalized_value == candidate_value
                or normalized_value in candidate_value
                or candidate_value in normalized_value
            ):
                return idx
    return None


def first_matching_index(candidates: Iterable[Any], *, kind: str) -> int | None:
    for idx, candidate in enumerate(candidates):
        if getattr(candidate, "kind", "") == kind:
            return idx
    return None
