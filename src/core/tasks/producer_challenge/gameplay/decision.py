from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence

from src.constants.game.producer_gameplay import GameplayPhase, GameplayPosition
from src.constants.yolo.labels.producer_Labels import ProducerLabels
from src.constants.game.text.button_text import ButtonText
from src.constants.game.text.general_text import GeneralText
from src.constants.game.text.produce_text import ProduceText
from src.core.tasks.producer_challenge.catalog import match_card_and_item_entries
from src.core.tasks.producer_challenge.gameplay.common import infer_param_kind, ocr_text
from src.utils.logger import logger
from src.utils.debug_tools import DebugTools
from src.utils.string_tools import fullwidth_to_halfwidth, normalize_ocr_jp

if TYPE_CHECKING:
    from src.core.tasks.producer_challenge.context import ProduceContext
    from src.main import AppProcessor

_LOOKUP_CLEANUP_RE = re.compile(r"[\s　・･/／|｜,，.。:：()\[\]{}<>「」『』【】'\"`]+")
_SLUG_CLEANUP_RE = re.compile(r"[^a-z0-9_]+")
_NUMBER_RE = re.compile(r"\d+")
_STAMINA_RE = re.compile(r"(\d+)\s*/\s*(\d+)")
@dataclass(frozen=True)
class CandidateResolution:
    action_id: str
    candidate_type: str
    db_id: str = ""
    display_name: str = ""
    source: str = ""
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ScheduleActionSpec:
    action_id: str
    aliases: tuple[str, ...]
    rl_action_type: str = ""
    todo: str = ""
    confidence: float = 0.95


_SCHEDULE_ACTION_SPECS: tuple[ScheduleActionSpec, ...] = (
    ScheduleActionSpec(
        action_id="schedule_action_special_guidance",
        aliases=(ProduceText.SPECIAL_GUIDANCE,),
        todo="TODO: 缺少特別指導真实采集图与稳定界面判据，当前仅补 action_id，未实现专用 handler。",
        confidence=0.75,
    ),
    ScheduleActionSpec(
        action_id="schedule_action_customize",
        aliases=(ProduceText.CUSTOMIZE,),
        todo="TODO: 缺少カスタマイズ真实采集图与稳定界面判据，当前仅补 action_id，未实现专用 handler。",
        confidence=0.75,
    ),
    ScheduleActionSpec(
        action_id="schedule_action_audition_finale",
        aliases=(ProduceText.FINALE,),
    ),
    ScheduleActionSpec(
        action_id="schedule_action_audition_second",
        aliases=(ProduceText.SECOND_AUDITION,),
    ),
    ScheduleActionSpec(
        action_id="schedule_action_audition_first",
        aliases=(ProduceText.FIRST_AUDITION,),
    ),
    ScheduleActionSpec(
        action_id="schedule_action_audition",
        aliases=(ProduceText.AUDITION,),
    ),
    ScheduleActionSpec(
        action_id="schedule_action_consult",
        aliases=(ProduceText.CONSULT,),
    ),
    ScheduleActionSpec(
        action_id="schedule_action_present_support",
        aliases=(ProduceText.PRESENT_SUPPORT,),
        rl_action_type="present",
    ),
    ScheduleActionSpec(
        action_id="schedule_action_fan_present",
        aliases=(ProduceText.FAN_PRESENT,),
        rl_action_type="present",
    ),
    ScheduleActionSpec(
        action_id="schedule_action_business_corporate",
        aliases=(ProduceText.BUSINESS_CORPORATE,),
        rl_action_type="business",
    ),
    ScheduleActionSpec(
        action_id="schedule_action_business_municipal",
        aliases=(ProduceText.BUSINESS_MUNICIPAL,),
        rl_action_type="business",
    ),
    ScheduleActionSpec(
        action_id="schedule_action_business_resort",
        aliases=(ProduceText.BUSINESS_RESORT,),
        rl_action_type="business",
    ),
    ScheduleActionSpec(
        action_id="schedule_action_business_commercial",
        aliases=(ProduceText.BUSINESS_COMMERCIAL,),
        rl_action_type="business",
    ),
    ScheduleActionSpec(
        action_id="schedule_action_business",
        aliases=(ProduceText.BUSINESS,),
        rl_action_type="business",
    ),
    ScheduleActionSpec(
        action_id="schedule_action_outing",
        aliases=(ProduceText.OUTING, ProduceText.GO_OUT),
        rl_action_type="activity",
    ),
    ScheduleActionSpec(
        action_id="schedule_action_class",
        aliases=(ProduceText.CLASS,),
        rl_action_type="activity",
    ),
    ScheduleActionSpec(
        action_id="schedule_action_activity",
        aliases=(ProduceText.ACTIVITY,),
        rl_action_type="activity",
    ),
    ScheduleActionSpec(
        action_id="schedule_action_refresh",
        aliases=(ProduceText.REST, "refresh"),
        rl_action_type="refresh",
    ),
)


def _normalize_lookup_text(text: str | None) -> str:
    if not text:
        return ""
    normalized = normalize_ocr_jp(fullwidth_to_halfwidth(str(text)))
    normalized = _LOOKUP_CLEANUP_RE.sub("", normalized)
    return normalized.lower().strip()


def _slugify_text(text: str | None, *, fallback: str) -> str:
    normalized = _normalize_lookup_text(text)
    slug = _SLUG_CLEANUP_RE.sub("_", normalized.lower()).strip("_")
    return slug or fallback


def _build_unknown_action_id(prefix: str, text: str | None, *, index: int) -> str:
    return f"{prefix}:{_slugify_text(text, fallback=f'idx_{index}')}"


def _matches_schedule_alias(raw_title: str, normalized_title: str, alias: str) -> bool:
    if not alias:
        return False
    return alias in raw_title or _normalize_lookup_text(alias) in normalized_title


def _resolve_schedule_spec(
    spec: ScheduleActionSpec,
    *,
    raw_title: str,
    metadata: dict[str, Any],
) -> CandidateResolution:
    spec_metadata = dict(metadata)
    spec_metadata["schedule_family"] = spec.action_id.removeprefix("schedule_action_")
    spec_metadata["supported"] = not bool(spec.todo)
    if spec.rl_action_type:
        spec_metadata["rl_action_type"] = spec.rl_action_type
    if spec.todo:
        spec_metadata["todo"] = spec.todo
    return CandidateResolution(
        action_id=spec.action_id,
        candidate_type="schedule_action",
        display_name=raw_title,
        source="todo" if spec.todo else "heuristic",
        confidence=spec.confidence,
        metadata=spec_metadata,
    )


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _ensure_rl_package_on_path() -> None:
    rl_root = _repo_root() / "train" / "gakumas_rl"
    if rl_root.exists():
        rl_root_str = str(rl_root)
        if rl_root_str not in sys.path:
            sys.path.insert(0, rl_root_str)


@lru_cache(maxsize=1)
def _get_rl_repository():
    try:
        _ensure_rl_package_on_path()
        from gakumas_rl.service import get_repository

        return get_repository()
    except Exception as exc:  # noqa: BLE001 - 这里需要容忍缺失依赖，回退到 OCR/本地 catalog
        logger.debug(f"producer decision: 无法加载 gakumas_rl 主数据仓库，回退文本匹配: {exc}")
        return None


def _lookup_card_row(card_id: str, *, upgrade_count: int | None = None) -> dict[str, Any] | None:
    repository = _get_rl_repository()
    if repository is None or not card_id:
        return None
    if upgrade_count is not None:
        return repository.card_row_by_upgrade(card_id, upgrade_count)
    return repository.canonical_card_row(card_id)


def _lookup_named_row(table_name: str, item_id: str) -> dict[str, Any] | None:
    repository = _get_rl_repository()
    if repository is None or not item_id:
        return None
    table = getattr(repository, table_name, None)
    if table is None:
        table = repository.load_table(
            "ProduceDrink" if table_name == "produce_drinks" else "ProduceItem"
        )
    return table.first(item_id)


def _match_catalog_entry(
    title: str,
    *,
    expected_kind: str | None = None,
) -> dict[str, Any] | None:
    if not title:
        return None
    matches = match_card_and_item_entries([title], threshold=72)
    if expected_kind is not None:
        matches = [entry for entry in matches if entry["kind"] == expected_kind]
    if not matches:
        return None
    matches.sort(key=lambda entry: float(entry.get("score") or 0.0), reverse=True)
    return matches[0]


def _enrich_card_metadata(card_id: str, *, upgrade_count: int = 0) -> dict[str, Any]:
    row = _lookup_card_row(card_id, upgrade_count=upgrade_count)
    repository = _get_rl_repository()
    if row is None or repository is None:
        return {"upgrade_count": int(upgrade_count)}
    return {
        "upgrade_count": int(row.get("upgradeCount") or upgrade_count or 0),
        "rarity": str(row.get("rarity") or ""),
        "category": str(row.get("category") or ""),
        "cost_type": str(row.get("costType") or ""),
        "display_name": repository.card_name(row),
        "raw_name": repository.raw_card_name(row),
        "effect_types": repository.card_axis_effect_types(row),
        "trigger_phases": repository.card_trigger_phases(row),
    }


def _enrich_drink_metadata(drink_id: str) -> dict[str, Any]:
    row = _lookup_named_row("produce_drinks", drink_id)
    repository = _get_rl_repository()
    if row is None or repository is None:
        return {}
    return {
        "rarity": str(row.get("rarity") or ""),
        "display_name": repository.drink_name(row),
        "raw_name": repository.raw_drink_name(row),
        "effect_types": repository.drink_axis_effect_types(row),
    }


def _enrich_item_metadata(item_id: str) -> dict[str, Any]:
    row = _lookup_named_row("produce_items", item_id)
    repository = _get_rl_repository()
    if row is None or repository is None:
        return {}
    return {
        "rarity": str(row.get("rarity") or ""),
        "display_name": repository.item_name(row),
        "raw_name": repository.raw_item_name(row),
    }


def resolve_schedule_action_identity(
    title: str,
    kind: str,
    *,
    index: int = 0,
) -> CandidateResolution:
    raw_title = str(title or "")
    normalized_title = _normalize_lookup_text(raw_title)
    metadata: dict[str, Any] = {
        "title": raw_title,
        "param_kind": kind or infer_param_kind(raw_title),
    }

    for spec in _SCHEDULE_ACTION_SPECS:
        if any(_matches_schedule_alias(raw_title, normalized_title, alias) for alias in spec.aliases):
            return _resolve_schedule_spec(spec, raw_title=raw_title, metadata=metadata)

    param_kind = metadata["param_kind"]
    if ProduceText.SELF_LESSON in raw_title:
        variant = "sp" if "SP" in raw_title.upper() else "normal"
        metadata["rl_action_type"] = (
            f"self_lesson_{param_kind}_{variant}" if param_kind != "unknown" else ""
        )
        return CandidateResolution(
            action_id=(
                f"schedule_action_self_lesson_{param_kind}_{variant}"
                if param_kind != "unknown"
                else _build_unknown_action_id("schedule_action_self_lesson_unknown", raw_title, index=index)
            ),
            candidate_type="schedule_action",
            display_name=raw_title,
            source="heuristic",
            confidence=0.95,
            metadata=metadata,
        )

    if ProduceText.HARD_LESSON in raw_title:
        metadata["rl_action_type"] = (
            f"lesson_{param_kind}_hard" if param_kind != "unknown" else ""
        )
        return CandidateResolution(
            action_id=(
                f"schedule_action_lesson_{param_kind}_hard"
                if param_kind != "unknown"
                else _build_unknown_action_id("schedule_action_lesson_hard_unknown", raw_title, index=index)
            ),
            candidate_type="schedule_action",
            display_name=raw_title,
            source="heuristic",
            confidence=0.95,
            metadata=metadata,
        )

    if "SP" in raw_title.upper() or "ＳＰ" in raw_title:
        metadata["rl_action_type"] = (
            f"lesson_{param_kind}_sp" if param_kind != "unknown" else ""
        )
        return CandidateResolution(
            action_id=(
                f"schedule_action_lesson_{param_kind}_sp"
                if param_kind != "unknown"
                else _build_unknown_action_id("schedule_action_lesson_sp_unknown", raw_title, index=index)
            ),
            candidate_type="schedule_action",
            display_name=raw_title,
            source="heuristic",
            confidence=0.95,
            metadata=metadata,
        )

    if ProduceText.LESSON in raw_title or param_kind != "unknown":
        metadata["rl_action_type"] = (
            f"lesson_{param_kind}_normal" if param_kind != "unknown" else ""
        )
        return CandidateResolution(
            action_id=(
                f"schedule_action_lesson_{param_kind}_normal"
                if param_kind != "unknown"
                else _build_unknown_action_id("schedule_action_lesson_unknown", raw_title, index=index)
            ),
            candidate_type="schedule_action",
            display_name=raw_title,
            source="heuristic",
            confidence=0.95,
            metadata=metadata,
        )

    return CandidateResolution(
        action_id=_build_unknown_action_id("schedule_action", raw_title, index=index),
        candidate_type="schedule_action",
        display_name=raw_title,
        source="heuristic",
        confidence=0.5,
        metadata=metadata,
    )


def resolve_dialogue_option_identity(title: str, *, index: int) -> CandidateResolution:
    return CandidateResolution(
        action_id=f"dialogue_option:{_slugify_text(title, fallback=f'idx_{index}')}",
        candidate_type="dialogue_option",
        display_name=title,
        source="ocr",
        confidence=0.75 if title else 0.0,
        metadata={},
    )


def _resolve_card_from_clip(app: "AppProcessor", box: Any) -> CandidateResolution | None:
    clip_manager = getattr(app, "clip_manager", None)
    if clip_manager is None or box is None or getattr(box, "frame", None) is None:
        return None
    skill_card_clip = getattr(clip_manager, "skill_card_clip", None)
    if skill_card_clip is None:
        return None
    try:
        matched = skill_card_clip.retrieve(box.frame)
    except Exception as exc:  # noqa: BLE001 - 识别失败要显式退回 OCR
        logger.debug(f"producer decision: 技能卡 CLIP 识别失败，回退 OCR: {exc}")
        return None
    if matched is None:
        return None

    card_id = str(getattr(matched, "id", "") or "")
    upgrade_count = int(getattr(matched, "upgradeCount", 0) or 0)
    metadata = _enrich_card_metadata(card_id, upgrade_count=upgrade_count)
    display_name = (
        metadata.get("display_name")
        or getattr(getattr(matched, "localization", None), "name", None)
        or getattr(matched, "name", "")
        or card_id
    )
    return CandidateResolution(
        action_id=f"produce_card:{card_id}:{upgrade_count}",
        candidate_type="produce_card",
        db_id=card_id,
        display_name=str(display_name),
        source="clip",
        confidence=1.0,
        metadata=metadata,
    )


def resolve_produce_card_identity(
    app: "AppProcessor",
    *,
    title: str,
    box: Any,
    index: int,
) -> CandidateResolution:
    clip_resolution = _resolve_card_from_clip(app, box)
    if clip_resolution is not None:
        return clip_resolution

    matched = _match_catalog_entry(title, expected_kind="produce_card")
    if matched is not None:
        card_id = str(matched["id"])
        metadata = _enrich_card_metadata(card_id, upgrade_count=0)
        display_name = metadata.get("display_name") or matched.get("name") or title or card_id
        return CandidateResolution(
            action_id=f"produce_card:{card_id}:0",
            candidate_type="produce_card",
            db_id=card_id,
            display_name=str(display_name),
            source="ocr",
            confidence=float(matched.get("score") or 0.0) / 100.0,
            metadata=metadata,
        )

    return CandidateResolution(
        action_id=_build_unknown_action_id("produce_card_unknown", title, index=index),
        candidate_type="produce_card",
        display_name=title,
        source="unresolved",
        confidence=0.0,
        metadata={"unresolved": True},
    )


def resolve_produce_drink_identity(
    title: str,
    *,
    index: int,
) -> CandidateResolution:
    matched = _match_catalog_entry(title, expected_kind="produce_drink")
    if matched is not None:
        drink_id = str(matched["id"])
        metadata = _enrich_drink_metadata(drink_id)
        display_name = metadata.get("display_name") or matched.get("name") or title or drink_id
        return CandidateResolution(
            action_id=f"produce_drink:{drink_id}",
            candidate_type="produce_drink",
            db_id=drink_id,
            display_name=str(display_name),
            source="ocr",
            confidence=float(matched.get("score") or 0.0) / 100.0,
            metadata=metadata,
        )

    return CandidateResolution(
        action_id=_build_unknown_action_id("produce_drink_unknown", title, index=index),
        candidate_type="produce_drink",
        display_name=title,
        source="unresolved",
        confidence=0.0,
        metadata={"unresolved": True},
    )


def resolve_produce_item_identity(
    title: str,
    *,
    index: int,
) -> CandidateResolution:
    matched = _match_catalog_entry(title, expected_kind="produce_item")
    if matched is not None:
        item_id = str(matched["id"])
        metadata = _enrich_item_metadata(item_id)
        display_name = metadata.get("display_name") or matched.get("name") or title or item_id
        return CandidateResolution(
            action_id=f"produce_item:{item_id}",
            candidate_type="produce_item",
            db_id=item_id,
            display_name=str(display_name),
            source="ocr",
            confidence=float(matched.get("score") or 0.0) / 100.0,
            metadata=metadata,
        )

    return CandidateResolution(
        action_id=_build_unknown_action_id("produce_item_unknown", title, index=index),
        candidate_type="produce_item",
        display_name=title,
        source="unresolved",
        confidence=0.0,
        metadata={"unresolved": True},
    )


def resolve_produce_entity_identity(
    title: str,
    *,
    index: int,
) -> CandidateResolution:
    matched = _match_catalog_entry(title)
    if matched is None:
        return CandidateResolution(
            action_id=_build_unknown_action_id("produce_entity_unknown", title, index=index),
            candidate_type="produce_entity",
            display_name=title,
            source="unresolved",
            confidence=0.0,
            metadata={"unresolved": True},
        )
    kind = str(matched.get("kind") or "")
    if kind == "produce_card":
        return resolve_produce_card_identity(None, title=title, box=None, index=index)  # type: ignore[arg-type]
    if kind == "produce_drink":
        return resolve_produce_drink_identity(title, index=index)
    if kind == "produce_item":
        return resolve_produce_item_identity(title, index=index)
    return CandidateResolution(
        action_id=_build_unknown_action_id("produce_entity_unknown", title, index=index),
        candidate_type="produce_entity",
        display_name=title,
        source="unresolved",
        confidence=0.0,
        metadata={"unresolved": True},
    )


def _apply_resolution(candidate: Any, resolution: CandidateResolution) -> None:
    candidate.action_id = resolution.action_id
    candidate.db_id = resolution.db_id
    candidate.source = resolution.source
    candidate.confidence = resolution.confidence
    existing_metadata = getattr(candidate, "metadata", None)
    if existing_metadata is None:
        existing_metadata = {}
        candidate.metadata = existing_metadata
    existing_metadata.update(
        {
            "candidate_type": resolution.candidate_type,
            "source": resolution.source,
            **resolution.metadata,
        }
    )
    if resolution.display_name and not getattr(candidate, "title", ""):
        if hasattr(candidate, "title"):
            candidate.title = resolution.display_name


def hydrate_schedule_candidates(candidates: Sequence[Any]) -> None:
    for candidate in candidates:
        resolution = resolve_schedule_action_identity(
            getattr(candidate, "title", ""),
            getattr(candidate, "kind", ""),
            index=getattr(candidate, "index", 0),
        )
        _apply_resolution(candidate, resolution)


def hydrate_dialogue_candidates(candidates: Sequence[Any]) -> None:
    for candidate in candidates:
        resolution = resolve_dialogue_option_identity(
            getattr(candidate, "title", ""),
            index=getattr(candidate, "index", 0),
        )
        _apply_resolution(candidate, resolution)


def hydrate_card_candidates(
    app: "AppProcessor",
    candidates: Sequence[Any],
) -> None:
    for candidate in candidates:
        resolution = resolve_produce_card_identity(
            app,
            title=getattr(candidate, "title", ""),
            box=getattr(candidate, "box", None),
            index=getattr(candidate, "index", 0),
        )
        _apply_resolution(candidate, resolution)


def hydrate_p_drink_candidates(candidates: Sequence[Any]) -> None:
    for candidate in candidates:
        resolution = resolve_produce_drink_identity(
            getattr(candidate, "title", ""),
            index=getattr(candidate, "index", 0),
        )
        _apply_resolution(candidate, resolution)


def hydrate_consult_candidates(
    app: "AppProcessor",
    candidates: Sequence[Any],
) -> None:
    for candidate in candidates:
        kind = getattr(candidate, "kind", "")
        title = getattr(candidate, "title", "")
        index = getattr(candidate, "index", 0)
        if kind in {"enhancement_target", "remove_target"}:
            resolution = resolve_produce_card_identity(app, title=title, box=getattr(candidate, "box", None), index=index)
            consult_action = (
                "consult_select_remove_target"
                if kind == "remove_target"
                else "consult_select_enhancement_target"
            )
            resolution = CandidateResolution(
                action_id=f"{consult_action}:{resolution.db_id or index}",
                candidate_type="consult_action",
                db_id=resolution.db_id,
                display_name=resolution.display_name or title,
                source=resolution.source,
                confidence=resolution.confidence,
                metadata={
                    **resolution.metadata,
                    "consult_action": consult_action,
                },
            )
        elif kind == "enhance":
            resolution = CandidateResolution(
                action_id="consult_open_enhancement",
                candidate_type="consult_action",
                display_name=title or GeneralText.ENHANCE,
                source="yolo",
                confidence=1.0,
                metadata={"consult_action": "consult_open_enhancement"},
            )
        elif kind == "delete":
            resolution = CandidateResolution(
                action_id="consult_open_remove",
                candidate_type="consult_action",
                display_name=title or ProduceText.SKILL_CARD_REMOVE,
                source="yolo",
                confidence=1.0,
                metadata={"consult_action": "consult_open_remove"},
            )
        elif kind == "confirm_enhancement":
            resolution = CandidateResolution(
                action_id="consult_confirm_enhancement",
                candidate_type="consult_action",
                display_name=title or ProduceText.ENHANCE_CONFIRM,
                source="yolo",
                confidence=1.0,
                metadata={"consult_action": "consult_confirm_enhancement"},
            )
        elif kind == "confirm_remove":
            resolution = CandidateResolution(
                action_id="consult_confirm_remove",
                candidate_type="consult_action",
                display_name=title or ProduceText.SKILL_CARD_REMOVE,
                source="yolo",
                confidence=1.0,
                metadata={"consult_action": "consult_confirm_remove"},
            )
        elif kind == "exit":
            resolution = CandidateResolution(
                action_id="consult_exit",
                candidate_type="consult_action",
                display_name=title or ButtonText.EXIT,
                source="ocr",
                confidence=0.9,
                metadata={"consult_action": "consult_exit"},
            )
        else:
            entry_resolution = resolve_produce_entity_identity(title, index=index)
            consult_action = GameplayPosition.CONSULT_EXCHANGE
            if entry_resolution.candidate_type == "produce_drink":
                consult_action = "consult_exchange_drink"
            elif entry_resolution.candidate_type == "produce_card":
                consult_action = "consult_exchange_card"
            resolution = CandidateResolution(
                action_id=f"{consult_action}:{entry_resolution.db_id or index}",
                candidate_type="consult_action",
                db_id=entry_resolution.db_id,
                display_name=entry_resolution.display_name or title,
                source=entry_resolution.source or "ocr",
                confidence=entry_resolution.confidence,
                metadata={
                    **entry_resolution.metadata,
                    "consult_action": consult_action,
                },
            )
        _apply_resolution(candidate, resolution)


def _serialize_box(box: Any) -> list[int] | None:
    if box is None:
        return None
    x = int(getattr(box, "x", 0))
    y = int(getattr(box, "y", 0))
    w = int(getattr(box, "w", 0))
    h = int(getattr(box, "h", 0))
    if w <= 0 or h <= 0:
        return None
    return [x, y, w, h]


def _annotate_candidates(app: "AppProcessor", *, phase: str, candidates: Sequence[Any]) -> None:
    debugger = getattr(app, "debug_tools", None) or DebugTools()
    phase_color = {
        GameplayPhase.SCHEDULE: (255, 215, 0),
        GameplayPhase.DIALOGUE: (0, 180, 255),
        GameplayPhase.LESSON: (0, 220, 120),
        GameplayPhase.EXAM: (255, 120, 0),
        GameplayPhase.SKILL_REWARD: (160, 120, 255),
        GameplayPhase.P_DRINK: (255, 0, 160),
        GameplayPhase.CONSULT: (255, 80, 80),
    }.get(phase, (200, 200, 200))
    for candidate in candidates:
        box = getattr(candidate, "box", None)
        coords = _serialize_box(box)
        if coords is None:
            continue
        label_core = getattr(candidate, "db_id", "") or getattr(candidate, "action_id", "") or getattr(candidate, "title", "") or getattr(candidate, "kind", "")
        debugger.add_box(
            coords[0],
            coords[1],
            coords[2],
            coords[3],
            label=f"{phase}:{getattr(candidate, 'index', 0)} {str(label_core)[:24]}",
            color=phase_color,
            alpha=0.15,
            duration=3.0,
            font_size=18,
        )


def serialize_candidate(candidate: Any, *, phase: str) -> dict[str, Any]:
    title = getattr(candidate, "title", "") or getattr(candidate, "label", "") or getattr(candidate, "kind", "")
    metadata = dict(getattr(candidate, "metadata", {}) or {})
    payload = {
        "index": int(getattr(candidate, "index", 0)),
        "id": getattr(candidate, "action_id", "") or f"{phase}:{getattr(candidate, 'index', 0)}",
        "db_id": getattr(candidate, "db_id", "") or "",
        "name": title,
        "type": metadata.get("consult_action") or metadata.get("candidate_type") or phase,
        "label": getattr(candidate, "label", "") or getattr(candidate, "kind", "") or title,
        "selected": bool(getattr(candidate, "selected", False)),
        "recommended": bool(getattr(candidate, "recommended", False)),
        "available": bool(metadata.get("available", True)),
        "bbox": _serialize_box(getattr(candidate, "box", None)),
        "source": getattr(candidate, "source", "") or metadata.get("source", ""),
        "confidence": float(getattr(candidate, "confidence", 0.0) or 0.0),
        "metadata": metadata,
    }
    if payload["db_id"]:
        payload["entity_kind"] = (
            "produce_card"
            if payload["id"].startswith("produce_card:")
            else "produce_drink"
            if payload["id"].startswith("produce_drink:")
            else "produce_item"
            if payload["id"].startswith("produce_item:")
            else ""
        )
    return payload


def _extract_first_int(text: str) -> int:
    match = _NUMBER_RE.search(text or "")
    return int(match.group()) if match else 0


def _extract_hud_state(app: "AppProcessor") -> dict[str, Any]:
    results = getattr(app, "latest_results", None)
    if results is None:
        return {
            "stamina": 0,
            "max_stamina": 0,
            "p_point": 0,
            "target_score": 0,
        }

    def _ocr_first(label: str) -> str:
        boxes = results.filter_by_label(label)
        if not boxes:
            return ""
        return ocr_text(boxes.first().frame)

    stamina_text = _ocr_first(ProducerLabels.PC_STAMINA)
    stamina_match = _STAMINA_RE.search(stamina_text)
    if stamina_match:
        stamina_value = int(stamina_match.group(1))
        max_stamina_value = int(stamina_match.group(2))
    else:
        stamina_value = _extract_first_int(stamina_text)
        max_stamina_value = 0

    return {
        "stamina": stamina_value,
        "max_stamina": max_stamina_value,
        "p_point": _extract_first_int(_ocr_first(ProducerLabels.PC_P_POINT)),
        "target_score": _extract_first_int(_ocr_first(ProducerLabels.PC_TARGET)),
    }


def build_decision_state(
    app: "AppProcessor",
    ctx: "ProduceContext",
    *,
    phase: str,
    position: str,
    candidates: Sequence[Any],
    reason: str = "decision",
) -> dict[str, Any]:
    hud_state = _extract_hud_state(app)
    _annotate_candidates(app, phase=phase, candidates=candidates)
    candidate_payloads = [serialize_candidate(candidate, phase=phase) for candidate in candidates]
    resolved_entities = [payload for payload in candidate_payloads if payload.get("db_id")]
    unresolved_entities = [payload for payload in candidate_payloads if not payload.get("db_id")]

    ctx.hud_stamina = hud_state["stamina"]
    if hud_state["max_stamina"] > 0:
        ctx.hud_max_stamina = hud_state["max_stamina"]
    ctx.hud_p_point = hud_state["p_point"]
    ctx.hud_target_score = hud_state["target_score"]
    ctx.consult_remaining_p_points = hud_state["p_point"]
    ctx.economy_state = {
        "stamina": ctx.hud_stamina,
        "max_stamina": ctx.hud_max_stamina,
        "p_point": ctx.hud_p_point,
    }
    ctx.parameter_state = {
        "target_score": ctx.hud_target_score,
    }
    ctx.last_sync_reason = reason
    ctx.state_revision += 1

    if phase in {GameplayPhase.LESSON, GameplayPhase.EXAM}:
        ctx.recognized_hand_cards = resolved_entities
        ctx.card_zone_state = {
            "hand": resolved_entities,
        }
        ctx.observability_state = {
            **ctx.observability_state,
            "draw_pile_order_known": False,
        }
    elif phase == GameplayPhase.P_DRINK:
        ctx.recognized_p_drinks = resolved_entities
        ctx.inventory_state = {
            **ctx.inventory_state,
            "p_drinks": resolved_entities,
        }
    elif phase == GameplayPhase.CONSULT:
        ctx.recognized_produce_items = resolved_entities
        ctx.inventory_state = {
            **ctx.inventory_state,
            "consult_candidates": resolved_entities,
        }

    ctx.unresolved_clip_entities = unresolved_entities

    snapshot = {
        "revision": ctx.state_revision,
        "phase": phase,
        "position": position,
        "week": ctx.current_week,
        "scenario": ctx.scenario,
        "difficulty": ctx.difficulty,
        "produce_id": ctx.produce_id,
        "produce_group_id": ctx.produce_group_id,
        "economy": dict(ctx.economy_state),
        "parameters": dict(ctx.parameter_state),
        "inventory": dict(ctx.inventory_state),
        "card_zones": dict(ctx.card_zone_state),
        "observability": dict(ctx.observability_state),
        "candidates": candidate_payloads,
        "legal_actions": [payload["index"] for payload in candidate_payloads],
        "resolved_entities": resolved_entities,
        "unresolved_entities": unresolved_entities,
    }
    ctx.handler_state["last_decision_state"] = snapshot
    return snapshot
