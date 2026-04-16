from __future__ import annotations

import copy
from collections import Counter
import re
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence

import cv2
import numpy as np

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
from src.utils.clip_tools import CLIPTools, CLIPRetrieveData
from src.utils.runtime_paths import resolve_data_str
from src.core.tasks.producer_challenge.gameplay.exam_wheel import get_exam_wheel_info
from src.core.tasks.producer_challenge.gameplay.exam_prep import get_exam_prep_bonuses
from src.core.tasks.producer_challenge.gameplay.exam_ranking import get_exam_ranking_value

if TYPE_CHECKING:
    from src.core.tasks.producer_challenge.context import ProduceContext
    from src.main import AppProcessor

_LOOKUP_CLEANUP_RE = re.compile(r"[\s　・･/／|｜,，.。:：()\[\]{}<>「」『』【】'\"`]+")
_SLUG_CLEANUP_RE = re.compile(r"[^a-z0-9_]+")
_NUMBER_RE = re.compile(r"\d+")
_STAMINA_RE = re.compile(r"(\d+)\s*/\s*(\d+)")
_MULTIPLIER_RE = re.compile(r"[x×]?\s*(\d+(?:\.\d+)?)")
_PERCENT_BASED_RESOURCE_PATTERNS = (
    re.compile(r"(好印象|集中|好調|元気|熱意|全力値)\s*の\s*\d+\s*[%％]"),
    re.compile(r"(好印象|集中|好調|元気|熱意|全力値)\s*的\s*\d+\s*[%％]"),
)
_SNAPSHOT_RESOURCE_KEY_BY_LABEL = {
    "好印象": "aggressive",
    "集中": "review",
    "好調": "parameter_buff",
    "元気": "block",
    "熱意": "enthusiastic",
    "全力値": "full_power_point",
}
_SNAPSHOT_CARD_CATEGORY_NAMES = {
    "ProduceCardCategory_ActiveSkill": "アクティブ",
    "ProduceCardCategory_MentalSkill": "メンタル",
    "ProduceCardCategory_Trouble": "トラブル",
}
_OFFENSIVE_EFFECT_KEYWORDS = (
    "ExamLesson",
    "ExamLessonFix",
    "ProduceExamEffectType_Score",
    "打分",
    "固定打分",
    "スコア",
)
_OFFENSIVE_DESCRIPTION_KEYWORDS = (
    "打分",
    "固定打分",
    "スコア",
    "パラメータ",
)

_VISUAL_DISABLED_LOW_SAT_THRESHOLD = 34
_VISUAL_DISABLED_HIGH_SAT_THRESHOLD = 72
_VISUAL_DISABLED_LOW_SAT_RATIO = 0.70
_VISUAL_DISABLED_COLORFUL_RATIO = 0.10
_VISUAL_DISABLED_MID_VALUE_RATIO = 0.42
_DRINK_EFFECT_SCORE_WEIGHTS = {
    "ProduceExamEffectType_Score": 38.0,
    "ProduceExamEffectType_ParameterBuff": 34.0,
    "ProduceExamEffectType_Review": 30.0,
    "ProduceExamEffectType_Aggressive": 28.0,
    "ProduceExamEffectType_Block": 26.0,
    "ProduceExamEffectType_Enthusiastic": 18.0,
    "ProduceExamEffectType_FullPowerPoint": 16.0,
    "ProduceExamEffectType_FullPower": 16.0,
}
_DRINK_DESCRIPTION_SCORE_RULES = (
    ("スキルカード使用数追加", 34.0),
    ("パラメータ上昇量増加", 28.0),
    ("好調", 18.0),
    ("集中", 16.0),
    ("好印象", 16.0),
    ("元気", 15.0),
    ("体力回復", 22.0),
    ("消費体力", 12.0),
    ("熱意", 10.0),
    ("全力値", 10.0),
)
_DRINK_RARITY_BONUS = {
    "SSR": 8.0,
    "SR": 5.0,
    "R": 2.0,
}
_PLAN_TYPE_METADATA = {
    "ProducePlanType_Plan1": {
        "label": ProduceText.PLAN_SENSE,
        "focus": "好調 / 集中 / 絶好調",
        "description": "官方主轴是好調、集中与絶好調，偏向放大单次参数/得分收益。",
    },
    "ProducePlanType_Plan2": {
        "label": ProduceText.PLAN_LOGIC,
        "focus": "好印象 / やる気 / 元気",
        "description": "官方主轴是好印象与やる気，偏向回合结算收益与续航。",
    },
    "ProducePlanType_Plan3": {
        "label": ProduceText.PLAN_ANOMALY,
        "focus": "全力 / 全力値 / 強気 / 温存 / 熱意",
        "description": "官方主轴是全力、強気、温存与熱意，偏向指针切换和爆发回合。",
    },
}
_EFFECT_TERM_HINTS = (
    ("スキルカード使用数追加", "本回合可以多打一张技能卡"),
    ("パラメータ上昇量増加", "会抬高后续参数/得分型动作的收益"),
    ("体力回復", "会直接回复体力，缓解低体力卡手"),
    ("絶好調", "会按当前好調层数进一步放大好調收益"),
    ("好印象", "会在回合结束按层数结算一次收益，并在回合开始时-1"),
    ("やる気", "每+1都会提高元気的获取量"),
    ("全力値", "累计到10会在下回合进入全力，并额外+1出牌次数"),
    ("全力", "会大幅提高参数/得分收益，并额外+1出牌次数"),
    ("強気", "会提高参数/得分收益，但也会增加体力消耗"),
    ("温存", "会降低当前收益和体力消耗，解除时返还热意/元気/出牌次数"),
    ("熱意", "每+1都会再追加1点参数/得分基础值，回合结束归零"),
    ("元気", "会优先代替体力支付，且不能带到下一场レッスン/試験"),
    ("集中", "每+1都会再追加1点参数/得分基础值，不会自然衰减"),
    ("好調", "会把参数/得分上升量提高50%，并随回合衰减"),
)


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


def _clean_description_text(text: str) -> str:
    cleaned = (
        str(text or "")
        .replace("<nobr>", "")
        .replace("</nobr>", "")
        .replace("<br>", "；")
        .replace("<br/>", "；")
        .replace("<br />", "；")
        .replace("\t", " ")
    )
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s*([,，。；：、）])", r"\1", cleaned)
    cleaned = re.sub(r"([（(])\s+", r"\1", cleaned)
    return cleaned.strip()


def _description_text(entries: Any) -> str:
    if not entries:
        return ""
    parts: list[str] = []
    for raw_entry in entries:
        entry = raw_entry or {}
        text = _clean_description_text(str(entry.get("text") or ""))
        if text:
            parts.append(text)
    return _clean_description_text("".join(parts))


def _humanize_runtime_text(text: str) -> str:
    cleaned = _clean_description_text(text)
    replacements = (
        ("干劲", "やる気"),
        ("好调", "好調"),
        ("绝好调", "絶好調"),
        ("元气", "元気"),
        ("强气", "強気"),
        ("弱气", "弱気"),
        ("热意", "熱意"),
        ("全力值", "全力値"),
        ("技能卡使用数追加", "スキルカード使用数追加"),
        ("体力回复", "回复体力"),
    )
    for before, after in replacements:
        cleaned = cleaned.replace(before, after)
    cleaned = re.sub(r"[；]{2,}", "；", cleaned)
    return cleaned.strip("； ")


def _plan_type_payload(plan_type: Any) -> dict[str, str]:
    raw_value = str(plan_type or "").strip()
    metadata = _PLAN_TYPE_METADATA.get(raw_value, {})
    return {
        "type": raw_value,
        "label": str(metadata.get("label") or ""),
        "focus": str(metadata.get("focus") or ""),
        "description": str(metadata.get("description") or ""),
    }


def _current_idol_plan_payload(ctx: "ProduceContext") -> dict[str, str]:
    idol_card = getattr(ctx, "selected_idol_card", None)
    # 回退: 从主数据库按配置的目标偶像卡 ID 查询
    if idol_card is None:
        target_id = getattr(ctx, "target_idol_card_id", "") or ""
        if target_id:
            try:
                from src.utils.game_database_tools import GakumasDatabase_IdolCardDataUtils
                idol_card = GakumasDatabase_IdolCardDataUtils().get_by_id(target_id)
                if idol_card is not None:
                    ctx.selected_idol_card = idol_card
            except Exception:
                pass
    if idol_card is None:
        return _plan_type_payload("")
    return _plan_type_payload(getattr(idol_card, "planType", ""))


def _build_parameter_priority(ctx: "ProduceContext") -> str:
    """根据偶像卡成长率计算属性优先级排序（如 'visual > dance > vocal'）。
    优先使用 ctx.selected_idol_card；若为空则从主数据库按 target_idol_card_id 查询。
    """
    idol_card = getattr(ctx, "selected_idol_card", None)

    # 回退: 从主数据库按配置的目标偶像卡 ID 查询
    if idol_card is None:
        target_id = getattr(ctx, "target_idol_card_id", "") or ""
        if target_id:
            try:
                from src.utils.game_database_tools import GakumasDatabase_IdolCardDataUtils
                idol_card = GakumasDatabase_IdolCardDataUtils().get_by_id(target_id)
                if idol_card is not None:
                    # 同时回填 ctx，后续调用不再重复查询
                    ctx.selected_idol_card = idol_card
            except Exception:
                pass

    if idol_card is None:
        return ""
    growth = {
        "vocal": int(getattr(idol_card, "produceVocalGrowthRatePermil", 0) or 0),
        "dance": int(getattr(idol_card, "produceDanceGrowthRatePermil", 0) or 0),
        "visual": int(getattr(idol_card, "produceVisualGrowthRatePermil", 0) or 0),
    }
    sorted_params = sorted(growth.items(), key=lambda x: x[1], reverse=True)
    return " > ".join(p[0] for p in sorted_params)


def _build_consult_session_summary(ctx: "ProduceContext") -> dict[str, Any]:
    """从 handler_state 和 operation_history 构建当前相談 session 的操作摘要。"""
    handler = ctx.handler_state
    used_enhancement = bool(handler.get("consult_auto_used_enhancement"))
    used_remove = bool(handler.get("consult_auto_used_remove"))
    # 统计本次相談中已完成的兑换操作
    exchanged_items: list[str] = []
    for op in reversed(ctx.operation_history):
        if op.phase != GameplayPhase.CONSULT:
            break
        if op.action == "consult_exchange":
            name = op.target or (op.details or {}).get("db_id", "")
            if name:
                exchanged_items.append(name)
    exchanged_items.reverse()
    return {
        "used_enhancement": used_enhancement,
        "used_remove": used_remove,
        "exchanged_items": exchanged_items,
        "actions_taken": len(exchanged_items) + int(used_enhancement) + int(used_remove),
    }


def _build_effect_term_hints(text: str) -> list[str]:
    remaining_text = fullwidth_to_halfwidth(str(text or ""))
    hints: list[str] = []
    for token, hint in _EFFECT_TERM_HINTS:
        if token not in remaining_text:
            continue
        hints.append(f"{token}={hint}")
        remaining_text = remaining_text.replace(token, " ")
    return hints


def _coerce_candidate_metadata(candidate: Any) -> dict[str, Any]:
    metadata = getattr(candidate, "metadata", None)
    if metadata is None:
        metadata = {}
        setattr(candidate, "metadata", metadata)
    return metadata


def mark_candidate_unavailable(candidate: Any, *, reason: str) -> None:
    """把候选标记为当前不可用，供序列化和本地 fallback 共用。"""
    reason_text = str(reason or "").strip()
    if not reason_text:
        return
    metadata = _coerce_candidate_metadata(candidate)
    metadata["available"] = False
    metadata["unavailable_reason"] = reason_text


def is_produce_card_action_id(action_id: Any) -> bool:
    normalized = str(action_id or "")
    return normalized.startswith("produce_card:") or normalized.startswith("produce_card_unknown")


def is_produce_drink_action_id(action_id: Any) -> bool:
    normalized = str(action_id or "")
    return normalized.startswith("produce_drink:") or normalized.startswith("produce_drink_unknown")


def is_end_turn_action_id(action_id: Any) -> bool:
    return str(action_id or "").strip() == "end_turn"


def score_produce_drink_metadata(
    metadata: dict[str, Any] | None,
    *,
    phase: str = "",
    stamina: int = 0,
    max_stamina: int = 0,
    remaining_turns: int = 0,
) -> float:
    """根据主库效果轴和描述，为 P 饮料给一个通用价值分。

    这里故意不用名字黑白名单，而是基于 effect_types / description / rarity 做粗评分，
    方便后续新剧本或新饮料直接复用。
    """
    payload = dict(metadata or {})
    description = str(payload.get("description") or "")
    effect_types = [str(value or "") for value in payload.get("effect_types", []) or []]
    rarity = str(payload.get("rarity") or "").upper()
    phase_key = phase.value if hasattr(phase, "value") else str(phase)

    score = _DRINK_RARITY_BONUS.get(rarity, 0.0)
    for effect_type in effect_types:
        for token, weight in _DRINK_EFFECT_SCORE_WEIGHTS.items():
            if token in effect_type:
                score += weight
                break

    normalized_description = fullwidth_to_halfwidth(description)
    for keyword, weight in _DRINK_DESCRIPTION_SCORE_RULES:
        if keyword in normalized_description:
            score += weight

    numeric_values = [int(value) for value in _NUMBER_RE.findall(normalized_description)]
    if numeric_values:
        score += min(max(numeric_values), 30) * 0.45

    stamina_ratio = (
        float(stamina) / max(int(max_stamina), 1)
        if int(max_stamina or 0) > 0
        else 1.0
    )
    if stamina_ratio <= 0.35 and any(
        token in normalized_description
        for token in ("元気", "体力回復", "消費体力", "ブロック")
    ):
        score += 18.0
    if phase_key in {GameplayPhase.LESSON, GameplayPhase.EXAM} and remaining_turns <= 2 and any(
        token in normalized_description
        for token in ("好調", "集中", "好印象", "スキルカード使用数追加", "パラメータ上昇量増加")
    ):
        score += 12.0
    return score


def _localized_humanized_description(
    table_name: str,
    item_id: str,
    fallback_entries: Any = None,
    *,
    upgrade_count: int | None = None,
) -> str:
    repository = _get_rl_repository()
    if repository is None or not item_id:
        return _humanize_runtime_text(_description_text(fallback_entries))
    loc_map = repository.load_localization(table_name)
    # 优先使用 "{id}.{upgradeCount}" 复合键查找精确升级等级的翻译
    row = {}
    if upgrade_count is not None:
        row = loc_map.get(f"{item_id}.{int(upgrade_count)}", {})
    if not row:
        row = loc_map.get(str(item_id), {})
    entries = row.get("produceDescriptions") or fallback_entries
    return _humanize_runtime_text(_description_text(entries))


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
    # raw_title 可能是 CLIP 传入的内部 action_id（如 "schedule_action_outing"），
    # 这时应使用 spec 的第一个 alias 作为可读名称，避免 LLM 看到内部 ID。
    display = raw_title
    if raw_title.startswith("schedule_action_") and spec.aliases:
        display = spec.aliases[0]
    return CandidateResolution(
        action_id=spec.action_id,
        candidate_type="schedule_action",
        display_name=display,
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


def _match_catalog_entry_from_texts(
    texts: Sequence[str],
    *,
    expected_kind: str | None = None,
) -> dict[str, Any] | None:
    normalized_texts = [str(text or "").strip() for text in texts if str(text or "").strip()]
    if not normalized_texts:
        return None
    matches = match_card_and_item_entries(normalized_texts, threshold=72)
    if expected_kind is not None:
        matches = [entry for entry in matches if entry["kind"] == expected_kind]
    if not matches:
        return None
    matches.sort(key=lambda entry: float(entry.get("score") or 0.0), reverse=True)
    return matches[0]


def _match_catalog_entry(
    title: str,
    *,
    expected_kind: str | None = None,
) -> dict[str, Any] | None:
    return _match_catalog_entry_from_texts([title], expected_kind=expected_kind)


def _enrich_card_metadata(card_id: str, *, upgrade_count: int = 0) -> dict[str, Any]:
    row = _lookup_card_row(card_id, upgrade_count=upgrade_count)
    repository = _get_rl_repository()
    if row is None or repository is None:
        return {
            "upgrade_count": int(upgrade_count),
            "description": "",
        }
    return {
        "upgrade_count": int(row.get("upgradeCount") or upgrade_count or 0),
        "rarity": str(row.get("rarity") or ""),
        "category": str(row.get("category") or ""),
        "plan_type": str(row.get("planType") or ""),
        "plan_type_label": _plan_type_payload(row.get("planType")).get("label", ""),
        "cost_type": str(row.get("costType") or ""),
        "cost": int(row.get("stamina") or 0),
        "display_name": repository.card_name(row),
        "raw_name": repository.raw_card_name(row),
        "description": _localized_humanized_description(
            "ProduceCard",
            card_id,
            row.get("produceDescriptions"),
            upgrade_count=int(row.get("upgradeCount") or upgrade_count or 0),
        ),
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
        "plan_type": str(row.get("planType") or ""),
        "plan_type_label": _plan_type_payload(row.get("planType")).get("label", ""),
        "display_name": repository.drink_name(row),
        "raw_name": repository.raw_drink_name(row),
        "description": _localized_humanized_description(
            "ProduceDrink",
            drink_id,
            row.get("produceDescriptions"),
        ),
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
        "description": _localized_humanized_description(
            "ProduceItem",
            item_id,
            row.get("produceDescriptions"),
        ),
    }


# ── SP 徽章视觉检测（纯色彩+结构分析，适配多分辨率）──────────────
_SP_PINK_RATIO_THRESHOLD = 0.03
_SP_COMP_RATIO_THRESHOLD = 0.015


def detect_sp_badge(action_box: Any) -> bool:
    """检测 PC_ACTION 框左上角区域是否存在 SP 渐变徽章。

    SP 徽章特征：粉红/品红色多彩渐变星形图标，位于动作框左上角。
    使用两层独立色彩信号检测（纯 HSV，不依赖模板或分辨率）：

      1. **饱和粉红像素占比** — SP 徽章有独特的品红色渐变背景
         (H:150-180 + H:0-10, S≥100, V≥100)，占比 ≥3%
      2. **最大连通域占比** — SP 徽章形成单一大块粉红色区域
         (排除 JPEG 伪影产生的散碎小噪点)，最大连通域 ≥1.5%
      3. 两层均通过 → SP

    已验证：JPEG q=15-95 × 缩放 0.5x-3.0x → 48/48 全通过。
    非 SP 的两项指标均为精确 0.000。
    """
    frame = getattr(action_box, "frame", None)
    if frame is None or frame.size == 0:
        return False

    h, w = frame.shape[:2]
    roi = frame[: max(1, int(h * 0.30)), : max(1, int(w * 0.25))]
    if roi.size == 0:
        return False

    blurred = cv2.GaussianBlur(roi, (3, 3), 0)
    hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
    area = float(roi.shape[0] * roi.shape[1])

    pink = cv2.inRange(hsv, (150, 100, 100), (180, 255, 255))
    red = cv2.inRange(hsv, (0, 100, 100), (10, 255, 255))
    warm_mask = cv2.bitwise_or(pink, red)

    pink_ratio = cv2.countNonZero(warm_mask) / area
    if pink_ratio < _SP_PINK_RATIO_THRESHOLD:
        return False

    contours, _ = cv2.findContours(warm_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    largest = max((cv2.contourArea(c) for c in contours), default=0)
    comp_ratio = largest / area

    return comp_ratio >= _SP_COMP_RATIO_THRESHOLD


def resolve_schedule_action_identity(
    title: str,
    kind: str,
    *,
    index: int = 0,
    is_sp: bool = False,
) -> CandidateResolution:
    raw_title = str(title or "")
    normalized_title = _normalize_lookup_text(raw_title)
    metadata: dict[str, Any] = {
        "title": raw_title,
        "param_kind": kind or infer_param_kind(raw_title),
    }

    for spec in _SCHEDULE_ACTION_SPECS:
        # 先检查 raw_title 是否直接是内部 action_id（CLIP 路径传入）
        if raw_title == spec.action_id:
            return _resolve_schedule_spec(spec, raw_title=raw_title, metadata=metadata)
        if any(_matches_schedule_alias(raw_title, normalized_title, alias) for alias in spec.aliases):
            return _resolve_schedule_spec(spec, raw_title=raw_title, metadata=metadata)

    param_kind = metadata["param_kind"]
    if ProduceText.SELF_LESSON in raw_title:
        variant = "sp" if ("SP" in raw_title.upper() or is_sp) else "normal"
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

    if "SP" in raw_title.upper() or "ＳＰ" in raw_title or is_sp:
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


# ────────────────────────────────────────────────────────────
# おでかけ活動 DB マッチング
# ────────────────────────────────────────────────────────────
# ProduceStepEventSuggestion.yaml 中的 activity 条目に基づき、
# OCR 效果描述 + P 点成本 → 安定的 DB ID を取得。
# RL / 学習に必要な一貫性のある識別子を提供する。

_outing_activity_entries: list[dict[str, Any]] | None = None
_OUTING_WHITESPACE_RE = re.compile(r"[\s\n\r　]+")
# 通用組 ID パターン: activity-NNN-NNN-NN（角色非依存）
_OUTING_GENERIC_ID_RE = re.compile(
    r"^p_s_e_s-event-detail-activity-\d+-\d+-\d+$"
)
# DB マッチング最低閾値
_OUTING_MATCH_THRESHOLD = 0.5


def _load_outing_activity_entries() -> list[dict[str, Any]]:
    """懒加载おでかけ活動 DB 条目（单例）。

    从 ProduceStepEventSuggestion.yaml 提取所有 activity 类条目，
    标准化描述文本，优先保留通用組 ID。
    """
    global _outing_activity_entries
    if _outing_activity_entries is not None:
        return _outing_activity_entries

    from src.utils.runtime_paths import resolve_existing_resource_path

    path = resolve_existing_resource_path(
        "assets", "gakumasu-diff", "ProduceStepEventSuggestion.yaml"
    )
    import yaml
    with open(str(path), "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not data:
        _outing_activity_entries = []
        return _outing_activity_entries

    # 按 (p_cost, normalized_desc) 去重，优先保留通用組 ID
    seen: dict[tuple[int, str], dict[str, Any]] = {}
    for entry in data:
        eid = str(entry.get("id", ""))
        if "activity" not in eid:
            continue
        p_cost = int(entry.get("producePoint", 0))
        desc_parts = [
            d.get("text", "")
            for d in entry.get("produceDescriptions", [])
            if d.get("text")
        ]
        raw_desc = "".join(desc_parts)
        norm_desc = _OUTING_WHITESPACE_RE.sub("", raw_desc)

        key = (p_cost, norm_desc)
        is_generic = bool(_OUTING_GENERIC_ID_RE.match(eid))
        # 通用組 ID 优先；同 key 下第一条 generic 覆盖 character-specific
        if key not in seen or (is_generic and not seen[key].get("is_generic")):
            seen[key] = {
                "id": eid,
                "produce_point": p_cost,
                "norm_desc": norm_desc,
                "raw_desc": raw_desc,
                "effect_ids": entry.get("produceEffectIds", []),
                "is_generic": is_generic,
            }

    _outing_activity_entries = list(seen.values())
    logger.info(
        "outing DB: 加载 {} 条唯一活動条目（来自 {} 条原始记录）",
        len(_outing_activity_entries),
        sum(1 for e in data if "activity" in str(e.get("id", ""))),
    )
    return _outing_activity_entries


def resolve_outing_option_identity(
    *,
    p_cost: int | None,
    effect_text: str,
    title: str = "",
    index: int = 0,
) -> CandidateResolution:
    """解析おでかけ選項的 DB ID。

    使用 P 点成本（精确匹配） + 効果描述文本（模糊匹配）
    定位 ProduceStepEventSuggestion.yaml 中的活動条目。

    Args:
        p_cost: 选项消耗的 P 点（从选项标题 OCR 提取）
        effect_text: Action Info 区域的効果描述（OCR）
        title: 选项标题（用于 display_name / fallback）
        index: 选项索引
    """
    # 没有効果描述 → fallback 到普通对话解析
    if not effect_text:
        return resolve_dialogue_option_identity(title, index=index)

    entries = _load_outing_activity_entries()
    if not entries:
        return resolve_dialogue_option_identity(title, index=index)

    ocr_normalized = _OUTING_WHITESPACE_RE.sub("", effect_text)

    from difflib import SequenceMatcher

    best_entry: dict[str, Any] | None = None
    best_score = 0.0

    for entry in entries:
        # P 成本精确匹配（如果已知）
        if p_cost is not None and entry["produce_point"] != p_cost:
            continue
        # 文本相似度
        score = SequenceMatcher(None, ocr_normalized, entry["norm_desc"]).ratio()
        if score > best_score:
            best_score = score
            best_entry = entry

    if best_entry and best_score >= _OUTING_MATCH_THRESHOLD:
        db_id = best_entry["id"]
        logger.debug(
            "outing DB: 选项 #{} '{}' → {} (score={:.2f}, P={})",
            index, (effect_text or "")[:30], db_id, best_score, p_cost,
        )
        return CandidateResolution(
            action_id=f"outing_activity:{db_id}",
            candidate_type="outing_activity",
            db_id=db_id,
            display_name=title,
            source="db_match",
            confidence=best_score,
            metadata={
                "outing_match_score": best_score,
                "outing_db_description": best_entry["raw_desc"],
                "outing_effect_ids": best_entry["effect_ids"],
            },
        )

    logger.debug(
        "outing DB: 选项 #{} '{}' 未匹配 (best_score={:.2f}, P={})",
        index, (effect_text or "")[:30], best_score, p_cost,
    )
    return resolve_dialogue_option_identity(title, index=index)


# ── 授業課程選項解析 ──

# 授業选项的属性类型 → 标准化 action_id / rl_action_type 映射
_LESSON_OPTION_MAP: dict[str, dict[str, str]] = {
    "vocal": {
        "action_id": "lesson_option_vocal_normal",
        "rl_action_type": "lesson_vocal_normal",
        "display_name": "ボーカルレッスン",
    },
    "dance": {
        "action_id": "lesson_option_dance_normal",
        "rl_action_type": "lesson_dance_normal",
        "display_name": "ダンスレッスン",
    },
    "visual": {
        "action_id": "lesson_option_visual_normal",
        "rl_action_type": "lesson_visual_normal",
        "display_name": "ビジュアルレッスン",
    },
}


def resolve_lesson_option_identity(
    kind: str,
    *,
    stamina_cost: int | None = None,
    effect_text: str = "",
    index: int = 0,
) -> CandidateResolution:
    """解析授業課程選項的 action_id 和 rl_action_type。

    基于探査阶段确定的 param_kind（vocal/dance/visual）映射到固定的
    action_id，不依赖角色特定的数据库条目。

    Args:
        kind: 属性类型 (vocal/dance/visual/unknown)
        stamina_cost: 体力消耗（OCR 读取）
        effect_text: 信息面板效果描述
        index: 选项索引
    """
    spec = _LESSON_OPTION_MAP.get(kind)
    if spec is not None:
        metadata: dict[str, Any] = {
            "param_kind": kind,
            "rl_action_type": spec["rl_action_type"],
            "lesson_option": True,
        }
        if stamina_cost is not None:
            metadata["stamina_cost"] = stamina_cost
        if effect_text:
            metadata["effect_text"] = effect_text
        return CandidateResolution(
            action_id=spec["action_id"],
            candidate_type="lesson_option",
            display_name=spec["display_name"],
            source="probe",
            confidence=1.0,
            metadata=metadata,
        )

    # 未识别属性类型 → fallback
    return CandidateResolution(
        action_id=f"lesson_option_unknown_{index}",
        candidate_type="lesson_option",
        display_name=f"授業選項{index + 1}",
        source="unknown",
        confidence=0.3,
        metadata={
            "param_kind": "unknown",
            "lesson_option": True,
            "stamina_cost": stamina_cost,
        },
    )
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


def _learn_card_clip_from_db_id(app: "AppProcessor", image: Any, card_id: str, *, upgrade_count: int = 0) -> None:
    if image is None or getattr(image, "size", 0) <= 0 or not card_id:
        return
    clip_manager = getattr(app, "clip_manager", None)
    if clip_manager is None:
        return
    skill_card_clip = getattr(clip_manager, "skill_card_clip", None)
    if skill_card_clip is None:
        return
    try:
        from src.utils.game_database_tools import GakumasDatabase_ProduceCardDataUtils

        payload = GakumasDatabase_ProduceCardDataUtils().get_by_id(f"{card_id}.{int(upgrade_count)}")
        if payload is None:
            payload = GakumasDatabase_ProduceCardDataUtils().get_by_id(f"{card_id}.0")
        if payload is None:
            return
        skill_card_clip.add_to_memory(image, payload, similarity_threshold=0.98)
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"producer decision: 技能卡 CLIP 学习失败 {card_id}: {exc}")


def _resolve_card_from_clip(app: "AppProcessor", box: Any) -> CandidateResolution | None:
    clip_manager = getattr(app, "clip_manager", None)
    if clip_manager is None or box is None or getattr(box, "frame", None) is None:
        return None
    skill_card_clip = getattr(clip_manager, "skill_card_clip", None)
    if skill_card_clip is None:
        return None
    try:
        matched = skill_card_clip.retrieve(box.frame)
    except Exception as exc:  # noqa: BLE001
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


def _resolve_drink_from_clip(app: "AppProcessor", box: Any) -> CandidateResolution | None:
    clip_manager = getattr(app, "clip_manager", None)
    if clip_manager is None or box is None or getattr(box, "frame", None) is None:
        return None
    produce_drink_clip = getattr(clip_manager, "produce_drink_clip", None)
    if produce_drink_clip is None:
        return None
    try:
        matched = produce_drink_clip.retrieve(box.frame)
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"producer decision: P饮料 CLIP 识别失败，回退 OCR: {exc}")
        return None
    if matched is None:
        return None

    drink_id = str(getattr(matched, "id", "") or "")
    metadata = _enrich_drink_metadata(drink_id)
    display_name = (
        metadata.get("display_name")
        or getattr(getattr(matched, "localization", None), "name", None)
        or getattr(matched, "name", "")
        or drink_id
    )
    return CandidateResolution(
        action_id=f"produce_drink:{drink_id}",
        candidate_type="produce_drink",
        db_id=drink_id,
        display_name=str(display_name),
        source="clip",
        confidence=1.0,
        metadata=metadata,
    )


def _learn_drink_clip_from_db_id(app: "AppProcessor", image: Any, drink_id: str) -> None:
    if image is None or getattr(image, "size", 0) <= 0 or not drink_id:
        return
    clip_manager = getattr(app, "clip_manager", None)
    if clip_manager is None:
        return
    produce_drink_clip = getattr(clip_manager, "produce_drink_clip", None)
    if produce_drink_clip is None:
        return
    try:
        from src.utils.game_database_tools import GakumasDatabase_ProduceDrinkDataUtils

        payload = GakumasDatabase_ProduceDrinkDataUtils().get_by_id(str(drink_id))
        if payload is None:
            return
        produce_drink_clip.add_to_memory(image, payload, similarity_threshold=0.98)
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"producer decision: P饮料 CLIP 学习失败 {drink_id}: {exc}")


def _resolve_item_from_clip(app: "AppProcessor", box: Any) -> CandidateResolution | None:
    clip_manager = getattr(app, "clip_manager", None)
    if clip_manager is None or box is None or getattr(box, "frame", None) is None:
        return None
    produce_item_clip = getattr(clip_manager, "produce_item_clip", None)
    if produce_item_clip is None:
        return None
    try:
        matched = produce_item_clip.retrieve(box.frame)
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"producer decision: P物品 CLIP 识别失败，回退 OCR: {exc}")
        return None
    if matched is None:
        return None

    item_id = str(getattr(matched, "id", "") or "")
    metadata = _enrich_item_metadata(item_id)
    display_name = (
        metadata.get("display_name")
        or getattr(getattr(matched, "localization", None), "name", None)
        or getattr(matched, "name", "")
        or item_id
    )
    return CandidateResolution(
        action_id=f"produce_item:{item_id}",
        candidate_type="produce_item",
        db_id=item_id,
        display_name=str(display_name),
        source="clip",
        confidence=1.0,
        metadata=metadata,
    )


def _learn_item_clip_from_db_id(app: "AppProcessor", image: Any, item_id: str) -> None:
    if image is None or getattr(image, "size", 0) <= 0 or not item_id:
        return
    clip_manager = getattr(app, "clip_manager", None)
    if clip_manager is None:
        return
    produce_item_clip = getattr(clip_manager, "produce_item_clip", None)
    if produce_item_clip is None:
        return
    try:
        from src.utils.game_database_tools import GakumasDatabase_ProduceItemDataUtils

        payload = GakumasDatabase_ProduceItemDataUtils().get_by_id(str(item_id))
        if payload is None:
            return
        produce_item_clip.add_to_memory(image, payload, similarity_threshold=0.98)
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"producer decision: P物品 CLIP 学习失败 {item_id}: {exc}")


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
        _learn_card_clip_from_db_id(app, getattr(box, "frame", None), card_id, upgrade_count=0)
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
    app: "AppProcessor | None" = None,
    box: Any = None,
    index: int,
) -> CandidateResolution:
    clip_resolution = _resolve_drink_from_clip(app, box) if app is not None else None
    if clip_resolution is not None:
        return clip_resolution

    matched = _match_catalog_entry(title, expected_kind="produce_drink")
    if matched is not None:
        drink_id = str(matched["id"])
        metadata = _enrich_drink_metadata(drink_id)
        display_name = metadata.get("display_name") or matched.get("name") or title or drink_id
        if app is not None and box is not None:
            _learn_drink_clip_from_db_id(app, getattr(box, "frame", None), drink_id)
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
    app: "AppProcessor | None" = None,
    box: Any = None,
    index: int,
    lookup_texts: Sequence[str] | None = None,
) -> CandidateResolution:
    clip_resolution = _resolve_item_from_clip(app, box) if app is not None else None
    if clip_resolution is not None:
        return clip_resolution

    match_inputs = [title, *(lookup_texts or ())]
    matched = (
        _match_catalog_entry_from_texts(match_inputs, expected_kind="produce_item")
        if lookup_texts
        else _match_catalog_entry(title, expected_kind="produce_item")
    )
    if matched is not None:
        item_id = str(matched["id"])
        metadata = {
            **_enrich_item_metadata(item_id),
            "matched_text": str(matched.get("matched_text") or ""),
        }
        display_name = (
            metadata.get("display_name")
            or matched.get("name")
            or next((text for text in match_inputs if text), "")
            or item_id
        )
        if app is not None and box is not None:
            _learn_item_clip_from_db_id(app, getattr(box, "frame", None), item_id)
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
        display_name=title or next((text for text in (lookup_texts or ()) if text), ""),
        source="unresolved",
        confidence=0.0,
        metadata={
            "unresolved": True,
            "lookup_texts": [str(text) for text in (lookup_texts or ()) if str(text or "").strip()],
        },
    )


def _auto_collect_unresolved_entity_image(box: Any, index: int) -> None:
    """CLIP 识别失败时自动采集未识别的实体图像，用于后续人工标注和学习。"""
    import os
    from datetime import datetime

    frame = getattr(box, "frame", None)
    if frame is None or getattr(frame, "size", 0) <= 0:
        return
    try:
        collect_dir = resolve_data_str("CLIP", "unresolved_consult")
        os.makedirs(collect_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = os.path.join(collect_dir, f"entity_{ts}_{index}.png")
        import cv2
        cv2.imwrite(path, frame)
        logger.info(f"[CLIP] 未识别实体已采集至: {path}")
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"[CLIP] 自动采集失败: {exc}")


def resolve_produce_entity_identity(
    title: str,
    *,
    app: "AppProcessor | None" = None,
    box: Any = None,
    index: int,
    icon_box: Any = None,
    entity_type_hint: str = "",
) -> CandidateResolution:
    # 1. OCR 文本匹配
    matched = _match_catalog_entry(title) if title.strip() else None
    if matched is not None:
        kind = str(matched.get("kind") or "")
        if kind == "produce_card":
            if app is None:
                return CandidateResolution(
                    action_id=_build_unknown_action_id("produce_card_unknown", title, index=index),
                    candidate_type="produce_card",
                    display_name=title,
                    source="unresolved",
                    confidence=0.0,
                    metadata={"unresolved": True},
                )
            return resolve_produce_card_identity(app, title=title, box=box, index=index)
        if kind == "produce_drink":
            return resolve_produce_drink_identity(title, app=app, box=box, index=index)
        if kind == "produce_item":
            return resolve_produce_item_identity(title, app=app, box=box, index=index)

    # 2. 尝试 CLIP 视觉识别（仅标准阈值，宁可不识别也不能误识别）
    if app is not None:
        # 选择最佳 CLIP 输入图像：优先使用内层图标框（更干净），否则用整个 box
        clip_box = icon_box if icon_box is not None else box

        if clip_box is not None:
            # 根据类型提示优先尝试对应的 CLIP 服务（标准阈值）
            if entity_type_hint == "produce_drink":
                result = _resolve_drink_from_clip(app, clip_box)
                if result is not None:
                    return result
            elif entity_type_hint == "produce_card":
                result = _resolve_card_from_clip(app, clip_box)
                if result is not None:
                    return result

            # 无提示或提示的 CLIP 未命中 → 按优先级尝试所有 CLIP 服务（标准阈值）
            for resolver in (_resolve_drink_from_clip, _resolve_card_from_clip, _resolve_item_from_clip):
                result = resolver(app, clip_box)
                if result is not None:
                    return result

        # 3. 所有识别均失败 → 自动采集未识别图像供后续人工标注
        collect_box = clip_box if clip_box is not None else box
        if collect_box is not None:
            _auto_collect_unresolved_entity_image(collect_box, index)

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
    # 重新解析成功时（有 db_id），清除之前的未识别标记
    if resolution.db_id:
        existing_metadata.pop("unresolved", None)
    # 有 DB 规范名称时，始终覆盖 OCR 原始文本（避免脏 OCR 如 |初星水 留在 title 中）
    # 周行动: CLIP 路径下 title 可能是内部 action_id，必须用可读名覆盖
    if resolution.display_name and hasattr(candidate, "title"):
        current_title = getattr(candidate, "title", "")
        is_internal_id = current_title.startswith("schedule_action_")
        if resolution.db_id or not current_title or is_internal_id:
            candidate.title = resolution.display_name


def hydrate_schedule_candidates(candidates: Sequence[Any]) -> None:
    for candidate in candidates:
        metadata = getattr(candidate, "metadata", None) or {}
        resolution = resolve_schedule_action_identity(
            getattr(candidate, "title", ""),
            getattr(candidate, "kind", ""),
            index=getattr(candidate, "index", 0),
            is_sp=bool(metadata.get("is_sp")),
        )
        _apply_resolution(candidate, resolution)


def hydrate_dialogue_candidates(candidates: Sequence[Any]) -> None:
    for candidate in candidates:
        resolution = resolve_dialogue_option_identity(
            getattr(candidate, "title", ""),
            index=getattr(candidate, "index", 0),
        )
        _apply_resolution(candidate, resolution)


def hydrate_outing_candidates(candidates: Sequence[Any]) -> None:
    """おでかけ選項の DB ID 解析（探査後に呼び出す）。

    outing probe 完了後、metadata に p_cost / outing_effect が設定された
    候選項を DB マッチングで再解析し、安定的な db_id を付与する。
    """
    for candidate in candidates:
        metadata = getattr(candidate, "metadata", {}) or {}
        effect_text = str(metadata.get("outing_effect") or "")
        if not effect_text:
            continue
        p_cost = metadata.get("p_cost")
        resolution = resolve_outing_option_identity(
            p_cost=p_cost,
            effect_text=effect_text,
            title=getattr(candidate, "title", ""),
            index=getattr(candidate, "index", 0),
        )
        # outing 解析成功時のみ上書き（fallback 的 dialogue_option は既に適用済み）
        if resolution.db_id:
            _apply_resolution(candidate, resolution)


def hydrate_lesson_candidates(candidates: Sequence[Any]) -> None:
    """授業課程選項の解析。

    探査完了後、metadata に lesson_stat / lesson_effect が設定された
    候選項から action_id / rl_action_type を付与する。
    """
    for candidate in candidates:
        metadata = getattr(candidate, "metadata", {}) or {}
        kind = getattr(candidate, "kind", "") or metadata.get("lesson_stat", "unknown")
        resolution = resolve_lesson_option_identity(
            kind,
            stamina_cost=metadata.get("stamina_cost"),
            effect_text=str(metadata.get("lesson_effect") or ""),
            index=getattr(candidate, "index", 0),
        )
        _apply_resolution(candidate, resolution)
        # 授業選項: 用标准属性名覆盖叙事性 OCR 文本
        # （LLM 需要看到「ボーカルレッスン」而非「名前を繰り返す」等叙事描述）
        if resolution.display_name and hasattr(candidate, "title"):
            candidate.title = resolution.display_name


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


def hydrate_p_drink_candidates(app: "AppProcessor", candidates: Sequence[Any]) -> None:
    for candidate in candidates:
        resolution = resolve_produce_drink_identity(
            getattr(candidate, "title", ""),
            app=app,
            box=getattr(candidate, "box", None),
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
            entry_resolution = resolve_produce_entity_identity(
                title,
                app=app,
                box=getattr(candidate, "box", None),
                index=index,
                icon_box=getattr(candidate, "icon_box", None),
                entity_type_hint=getattr(candidate, "entity_type_hint", ""),
            )
            consult_action = GameplayPosition.CONSULT_EXCHANGE
            if entry_resolution.candidate_type == "produce_drink":
                consult_action = "consult_exchange_drink"
            elif entry_resolution.candidate_type == "produce_card":
                consult_action = "consult_exchange_card"
            elif entry_resolution.candidate_type == "produce_item":
                consult_action = "consult_exchange_item"
            # 将价格信息附加到元数据
            price = (getattr(candidate, "metadata", {}) or {}).get("price", "")
            resolution = CandidateResolution(
                action_id=f"{consult_action}:{entry_resolution.db_id or index}",
                candidate_type="consult_action",
                db_id=entry_resolution.db_id,
                display_name=entry_resolution.display_name or title,
                source=entry_resolution.source or "clip",
                confidence=entry_resolution.confidence,
                metadata={
                    **entry_resolution.metadata,
                    "consult_action": consult_action,
                    **({"price": price} if price else {}),
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


def _looks_like_visually_disabled_card(box: Any) -> bool:
    """通过卡面低饱和灰蒙版特征识别“当前无法打出”的禁用态卡牌。"""
    frame = getattr(box, "frame", None)
    if frame is None or getattr(frame, "size", 0) <= 0:
        return False
    if len(frame.shape) < 3:
        return False
    height, width = frame.shape[:2]
    if height < 24 or width < 24:
        return False

    crop = frame[
        int(height * 0.14):int(height * 0.88),
        int(width * 0.08):int(width * 0.92),
    ]
    if crop.size <= 0:
        return False

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    saturation = hsv[:, :, 1].astype(np.float32)
    value = hsv[:, :, 2].astype(np.float32)
    low_sat_ratio = float(np.mean(saturation <= _VISUAL_DISABLED_LOW_SAT_THRESHOLD))
    colorful_ratio = float(np.mean(saturation >= _VISUAL_DISABLED_HIGH_SAT_THRESHOLD))
    mid_value_ratio = float(np.mean((value >= 70) & (value <= 215)))
    return (
        low_sat_ratio >= _VISUAL_DISABLED_LOW_SAT_RATIO
        and colorful_ratio <= _VISUAL_DISABLED_COLORFUL_RATIO
        and mid_value_ratio >= _VISUAL_DISABLED_MID_VALUE_RATIO
    )


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
        metadata = _coerce_candidate_metadata(candidate)
        if (
            phase in {GameplayPhase.LESSON, GameplayPhase.EXAM}
            and is_produce_card_action_id(getattr(candidate, "action_id", ""))
            and _looks_like_visually_disabled_card(box)
        ):
            mark_candidate_unavailable(
                candidate,
                reason="卡面呈现灰色禁用蒙版，当前条件下无法打出",
            )
            metadata = _coerce_candidate_metadata(candidate)
        label_core = getattr(candidate, "db_id", "") or getattr(candidate, "action_id", "") or getattr(candidate, "title", "") or getattr(candidate, "kind", "")
        unavailable_reason = str(metadata.get("unavailable_reason") or "").strip()
        debugger.add_box(
            coords[0],
            coords[1],
            coords[2],
            coords[3],
            label=(
                f"{phase}:{getattr(candidate, 'index', 0)} {str(label_core)[:24]}"
                f"{' [不可用]' if unavailable_reason else ''}"
            ),
            color=(255, 80, 80) if unavailable_reason else phase_color,
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
            if is_produce_card_action_id(payload["id"])
            else "produce_drink"
            if is_produce_drink_action_id(payload["id"])
            else "produce_item"
            if payload["id"].startswith("produce_item:")
            else ""
        )
    return payload


def _extract_first_int(text: str) -> int:
    match = _NUMBER_RE.search(text or "")
    return int(match.group()) if match else 0


# ── 课程画面进度圆圈解析 ──
# PC_TRAINING_SCORE 在课程中检测到的是中央进度圆圈，
# OCR 文本示例: "CLEARまで10", "PERFECTまで175CLEAR"


def _match_any_variant(text_upper: str, variants: tuple[str, ...]) -> bool:
    """检查 text_upper 是否包含 variants 中的任意一个（大小写不敏感）。"""
    return any(v.upper() in text_upper for v in variants)


def _parse_progress_circle(score_text: str) -> dict | None:
    """尝试将 PC_TRAINING_SCORE 的 OCR 文本解析为进度圆圈信息。

    课程画面的进度圆圈显示 "CLEARまで XX" 或 "PERFECTまで XX CLEAR"，
    其中的数字是 **距离目标的剩余分数**，而非当前累计分数。
    使用 ProduceText 中定义的 OCR 抗噪变体进行模糊匹配。

    Returns:
        dict with keys: clear_achieved, remaining_to_clear, remaining_to_perfect
        如果文本不是进度圆圈格式则返回 None。
    """
    if not score_text:
        return None
    normalized = (score_text or "").replace(" ", "").replace("　", "").upper()
    # 使用抗噪变体检测关键词
    has_made = _match_any_variant(normalized, ProduceText.PROGRESS_MADE_OCR_VARIANTS)
    has_perfect = _match_any_variant(normalized, ProduceText.PROGRESS_PERFECT_OCR_VARIANTS)
    has_clear = _match_any_variant(normalized, ProduceText.PROGRESS_CLEAR_OCR_VARIANTS)
    # 检测是否包含进度圆圈标志性关键词
    if not has_made and not has_clear and not has_perfect:
        return None
    # 从 "まで"（或其变体）之后的文本提取数字，
    # 避免抓到关键词里的噪点数字（如 "PERFEC7" 中的 7）
    made_end = 0
    for v in ProduceText.PROGRESS_MADE_OCR_VARIANTS:
        idx = normalized.find(v.upper())
        if idx >= 0:
            made_end = max(made_end, idx + len(v))
    number = _extract_first_int(normalized[made_end:]) if made_end > 0 else _extract_first_int(score_text)
    # "PERFECTまで175CLEAR" → 已 CLEAR, 距 PERFECT 还需 175
    # "CLEARまで10" → 未 CLEAR, 距 CLEAR 还需 10
    if has_perfect:
        return {
            "clear_achieved": True,
            "remaining_to_clear": 0,
            "remaining_to_perfect": number,
        }
    else:
        return {
            "clear_achieved": False,
            "remaining_to_clear": number,
            "remaining_to_perfect": 0,
        }


def _build_noisy_stamina_candidates(digits: str) -> list[int]:
    """从可能粘连/夹噪的数字串里枚举候选当前体力。"""
    if not digits:
        return []
    candidates: list[int] = [int(digits)]
    if len(digits) >= 2:
        candidates.extend(int(digits[index:]) for index in range(1, len(digits)))
        candidates.extend(int(digits[:index]) for index in range(1, len(digits)))
        candidates.extend(
            int(digits[start:end])
            for start in range(len(digits))
            for end in range(start + 1, len(digits) + 1)
            if end - start <= 2
        )
        candidates.extend(
            int(digits[:index] + digits[index + 1 :])
            for index in range(len(digits))
            if digits[:index] + digits[index + 1 :]
        )
    deduped: list[int] = []
    seen: set[int] = set()
    for value in candidates:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _parse_stamina_text(
    text: str,
    *,
    previous_stamina: int = 0,
    previous_max_stamina: int = 0,
) -> tuple[int, int]:
    normalized = fullwidth_to_halfwidth(str(text or ""))
    match = _STAMINA_RE.search(normalized)
    if match:
        return int(match.group(1)), int(match.group(2))

    digit_groups = re.findall(r"\d+", normalized)
    if not digit_groups:
        return 0, 0
    digits = "".join(digit_groups)
    has_slash = "/" in normalized

    if previous_max_stamina > 0:
        max_text = str(previous_max_stamina)
        if digits == max_text and 0 < previous_stamina < previous_max_stamina:
            return previous_stamina, previous_max_stamina
        if digits.endswith(max_text) and len(digits) > len(max_text):
            current_text = digits[:-len(max_text)]
            candidate_values = _build_noisy_stamina_candidates(current_text)
            valid_candidates = [
                value
                for value in candidate_values
                if 0 <= value <= previous_max_stamina
            ]
            if valid_candidates:
                current_value = min(
                    valid_candidates,
                    key=lambda value: (abs(value - previous_stamina), -value),
                )
                return current_value, previous_max_stamina
        inferred_current = int(digits)
        if 0 <= inferred_current <= previous_max_stamina:
            return inferred_current, previous_max_stamina
        if not has_slash:
            # 同一战斗里 max 体力通常稳定；斜杠丢失时宁可保留上一帧，也不要让脏 OCR 污染缓存。
            return previous_stamina, previous_max_stamina

    if len(digits) >= 3:
        current_value = int(digits[:-2])
        max_value = int(digits[-2:])
        if 0 < max_value <= 99 and 0 <= current_value <= max_value:
            return current_value, max_value
    if len(digits) >= 2:
        current_value = int(digits[:-1])
        max_value = int(digits[-1:])
        if 0 < max_value <= 9 and 0 <= current_value <= max_value:
            return current_value, max_value
    return int(digits), 0


def _build_noisy_hud_value_candidates(digits: str) -> list[tuple[int, int]]:
    """从单值 HUD 的 OCR 文本里枚举去噪候选，priority 越小越可信。"""
    if not digits:
        return []
    candidates: list[tuple[int, int]] = []
    seen: set[int] = set()

    def _add(value: int, priority: int) -> None:
        if value in seen:
            return
        seen.add(value)
        candidates.append((value, priority))

    _add(int(digits), 0)
    if len(digits) >= 2 and len(digits) % 2 == 0:
        half = len(digits) // 2
        if digits[:half] == digits[half:]:
            _add(int(digits[:half]), 1)
    for index in range(1, len(digits)):
        _add(int(digits[index:]), 2)
    for index in range(len(digits) - 1, 0, -1):
        _add(int(digits[:index]), 3)
    max_window = min(len(digits) - 1, 3)
    for window in range(max_window, 0, -1):
        for start in range(0, len(digits) - window + 1):
            _add(int(digits[start : start + window]), 4)
    return candidates


def _extract_noisy_hud_value(
    *texts: str,
    previous_value: int = 0,
    upper_bound: int = 0,
) -> tuple[int, bool]:
    """综合多份裁切 OCR，提取 battle HUD 中的单个数值。"""
    candidate_items: list[tuple[int, int, int, int]] = []
    has_digits = False
    for source_index, text in enumerate(texts):
        normalized = fullwidth_to_halfwidth(str(text or ""))
        digit_groups = re.findall(r"\d+", normalized)
        if not digit_groups:
            continue
        has_digits = True
        digits = "".join(digit_groups)
        for value, priority in _build_noisy_hud_value_candidates(digits):
            if upper_bound > 0 and value > upper_bound:
                continue
            candidate_items.append((value, source_index, priority, len(str(value))))
    if not candidate_items:
        return 0, has_digits
    if previous_value > 0:
        candidate_items.sort(
            key=lambda item: (
                abs(item[0] - previous_value),
                item[1],
                item[2],
                -item[3],
                item[0],
            )
        )
    else:
        candidate_items.sort(
            key=lambda item: (
                item[1],
                item[2],
                -item[3],
                item[0],
            )
        )
    return candidate_items[0][0], True


def _get_parameter_seed_value(ctx: "ProduceContext" | None, key: str) -> int:
    """优先使用已同步参数，其次回退到偶像卡主库基础值。"""
    if ctx is None:
        return 0
    current_value = ctx.parameter_state.get(key)
    if isinstance(current_value, int) and current_value > 0:
        return current_value
    selected_idol_card = getattr(ctx, "selected_idol_card", None)
    if selected_idol_card is None:
        return 0
    field_name = {
        "vocal": "produceVocal",
        "dance": "produceDance",
        "visual": "produceVisual",
    }.get(key, "")
    if not field_name:
        return 0
    return int(getattr(selected_idol_card, field_name, 0) or 0)


def _extract_planning_parameter_value(
    *texts: str,
    previous_value: int = 0,
    upper_bound: int = 0,
) -> tuple[int | None, bool]:
    """提取周规划 HUD 参数值，并利用数据库上限抑制粘连脏 OCR。"""
    max_digits = len(str(upper_bound)) if upper_bound > 0 else 0
    if previous_value <= 0 and max_digits > 0:
        for text in texts:
            normalized = fullwidth_to_halfwidth(str(text or ""))
            digit_groups = re.findall(r"\d+", normalized)
            if not digit_groups:
                continue
            digits = "".join(digit_groups)
            if len(digits) <= max_digits:
                continue
            for prefix_len in range(max_digits, 0, -1):
                candidate = int(digits[:prefix_len])
                if 0 < candidate <= upper_bound:
                    return candidate, True

    value, has_digits = _extract_noisy_hud_value(
        *texts,
        previous_value=previous_value,
        upper_bound=upper_bound,
    )
    if not has_digits:
        return None, False
    return (value if value > 0 else None), True


def _extract_first_int_from_texts(*texts: str) -> int:
    for text in texts:
        value = _extract_first_int(text)
        if value > 0:
            return value
    return 0


def _build_parameter_stats_payload(ctx: "ProduceContext") -> dict[str, Any]:
    parameter_limit = int(getattr(ctx, "parameter_growth_limit", 0) or 0)
    return {
        "vocal": ctx.parameter_state.get("vocal", "") or "",
        "dance": ctx.parameter_state.get("dance", "") or "",
        "visual": ctx.parameter_state.get("visual", "") or "",
        "vocal_max": parameter_limit or "",
        "dance_max": parameter_limit or "",
        "visual_max": parameter_limit or "",
    }


def _extract_hud_state(app: "AppProcessor") -> dict[str, Any]:
    ctx = getattr(app, "_produce_decision_ctx", None)
    results = getattr(app, "latest_results", None)
    if results is None:
        return {
            "stamina": 0,
            "max_stamina": 0,
            "stamina_observed": False,
            "genki": 0,
            "genki_observed": False,
            "p_point": 0,
            "p_point_observed": False,
            "target_score": 0,
            "target_score_observed": False,
            "score": 0,
            "score_observed": False,
            "remaining_turns": 0,
            "remaining_turns_observed": False,
            "turn_color": "",
            "score_bonus": "",
            "exam_ranking": "",
            "vocal": None,
            "vocal_observed": False,
            "dance": None,
            "dance_observed": False,
            "visual": None,
            "visual_observed": False,
            "has_progress_hud": False,
            "recommend_action_text": "",
            "recommend_action_kind": "",
        }

    def _ocr_first(label: str) -> str:
        boxes = results.filter_by_label(label)
        if not boxes:
            return ""
        return ocr_text(boxes.first().frame)

    def _ocr_region(x1_ratio: float, y1_ratio: float, x2_ratio: float, y2_ratio: float) -> str:
        frame = getattr(app, "latest_frame", None)
        if frame is None or frame.size == 0:
            return ""
        h, w = frame.shape[:2]
        x1 = int(w * x1_ratio)
        y1 = int(h * y1_ratio)
        x2 = int(w * x2_ratio)
        y2 = int(h * y2_ratio)
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return ""
        return ocr_text(crop)

    debugger = getattr(app, "debug_tools", None) or DebugTools()

    def _ocr_box_region(
        box,
        *,
        x1_ratio: float,
        y1_ratio: float,
        x2_ratio: float,
        y2_ratio: float,
        debug_label: str = "",
    ) -> str:
        frame = getattr(box, "frame", None)
        if frame is None or frame.size == 0:
            return ""
        h, w = frame.shape[:2]
        x1 = int(w * x1_ratio)
        y1 = int(h * y1_ratio)
        x2 = int(w * x2_ratio)
        y2 = int(h * y2_ratio)
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return ""
        if debug_label:
            box_x = int(getattr(box, "x", 0))
            box_y = int(getattr(box, "y", 0))
            debugger.add_box(
                box_x + x1,
                box_y + y1,
                box_x + x2,
                box_y + y2,
                label=debug_label,
                color=(80, 220, 120),
                alpha=0.15,
                duration=2.5,
                font_size=16,
            )
        return ocr_text(crop)

    def _ocr_box_text_right_of_color_anchor(
        box,
        *,
        lower_color: tuple[int, int, int],
        upper_color: tuple[int, int, int],
        search_y1_ratio: float,
        search_y2_ratio: float,
        min_area_ratio: float,
        min_aspect: float,
        max_aspect: float,
        x_padding: int,
        y_padding: int,
        min_x1_ratio: float,
        debug_label: str = "",
    ) -> str:
        frame = getattr(box, "frame", None)
        if frame is None or frame.size == 0:
            return ""
        h, w = frame.shape[:2]
        search_y1 = int(h * search_y1_ratio)
        search_y2 = int(h * search_y2_ratio)
        search_crop = frame[search_y1:search_y2, :]
        if search_crop.size == 0:
            return ""
        hsv = cv2.cvtColor(search_crop, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(
            hsv,
            np.array(lower_color, dtype=np.uint8),
            np.array(upper_color, dtype=np.uint8),
        )
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.dilate(mask, kernel, iterations=1)
        num_labels, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        min_area = float(mask.shape[0] * mask.shape[1]) * min_area_ratio
        anchor_box: tuple[int, int, int, int] | None = None
        anchor_area = 0
        for label_idx in range(1, num_labels):
            x = int(stats[label_idx, cv2.CC_STAT_LEFT])
            y = int(stats[label_idx, cv2.CC_STAT_TOP])
            component_w = int(stats[label_idx, cv2.CC_STAT_WIDTH])
            component_h = int(stats[label_idx, cv2.CC_STAT_HEIGHT])
            area = int(stats[label_idx, cv2.CC_STAT_AREA])
            if area < min_area or component_w <= 0 or component_h <= 0:
                continue
            aspect = component_w / max(1, component_h)
            if aspect < min_aspect or aspect > max_aspect:
                continue
            if area >= anchor_area:
                anchor_box = (x, y, component_w, component_h)
                anchor_area = area
        if anchor_box is None:
            return ""
        anchor_x, anchor_y, anchor_w, anchor_h = anchor_box
        x1 = min(
            w - 1,
            max(int(w * min_x1_ratio), anchor_x + anchor_w + x_padding),
        )
        y1 = max(0, search_y1 + anchor_y - y_padding)
        y2 = min(h, search_y1 + anchor_y + anchor_h + y_padding)
        crop = frame[y1:y2, x1:w]
        if crop.size == 0:
            return ""
        if debug_label:
            box_x = int(getattr(box, "x", 0))
            box_y = int(getattr(box, "y", 0))
            debugger.add_box(
                box_x + anchor_x,
                box_y + search_y1 + anchor_y,
                box_x + anchor_x + anchor_w,
                box_y + search_y1 + anchor_y + anchor_h,
                label=f"{debug_label}_anchor",
                color=(255, 200, 0),
                alpha=0.12,
                duration=2.5,
                font_size=16,
            )
            debugger.add_box(
                box_x + x1,
                box_y + y1,
                box_x + w,
                box_y + y2,
                label=debug_label,
                color=(80, 220, 120),
                alpha=0.15,
                duration=2.5,
                font_size=16,
            )
        return ocr_text(crop)

    battle_like_hud = any(
        results.exists_label(label)
        for label in (
            ProducerLabels.PC_BONUS_INDICATOR,
            ProducerLabels.PC_TRAINING_SCORE,
            ProducerLabels.SKILL_CARD_ACTIVE,
            ProducerLabels.SKILL_CARD_MENTAL,
            ProducerLabels.SKILL_CARD_TRAP,
        )
    )

    stamina_text = _ocr_first(ProducerLabels.PC_STAMINA)
    previous_stamina = int(getattr(app, "_last_produce_hud_stamina", 0) or 0)
    previous_max_stamina = int(getattr(app, "_last_produce_hud_max_stamina", 0) or 0)
    previous_genki = int(getattr(app, "_last_produce_hud_genki", 0) or 0)
    stamina_value = 0
    max_stamina_value = 0
    genki_value = 0
    stamina_observed = False
    genki_observed = False
    stamina_boxes = results.filter_by_label(ProducerLabels.PC_STAMINA)
    if battle_like_hud and stamina_boxes:
        stamina_box = stamina_boxes.first()
        genki_text_color = _ocr_box_text_right_of_color_anchor(
            stamina_box,
            lower_color=(40, 80, 80),
            upper_color=(110, 255, 255),
            search_y1_ratio=0.00,
            search_y2_ratio=0.55,
            min_area_ratio=0.03,
            min_aspect=2.0,
            max_aspect=20.0,
            x_padding=4,
            y_padding=6,
            min_x1_ratio=0.50,
            debug_label="pc_genki_color",
        )
        genki_text = _ocr_box_region(
            stamina_box,
            x1_ratio=0.54,
            y1_ratio=0.02,
            x2_ratio=0.98,
            y2_ratio=0.48,
            debug_label="pc_genki_hud",
        )
        genki_text_alt = _ocr_box_region(
            stamina_box,
            x1_ratio=0.42,
            y1_ratio=0.08,
            x2_ratio=0.98,
            y2_ratio=0.56,
            debug_label="pc_genki_hud_alt",
        )
        stamina_text_color = _ocr_box_text_right_of_color_anchor(
            stamina_box,
            lower_color=(30, 80, 80),
            upper_color=(85, 255, 255),
            search_y1_ratio=0.45,
            search_y2_ratio=1.00,
            min_area_ratio=0.02,
            min_aspect=0.5,
            max_aspect=2.0,
            x_padding=4,
            y_padding=6,
            min_x1_ratio=0.38,
            debug_label="pc_stamina_color",
        )
        stamina_lower_text = _ocr_box_region(
            stamina_box,
            x1_ratio=0.42,
            y1_ratio=0.40,
            x2_ratio=0.98,
            y2_ratio=0.98,
            debug_label="pc_stamina_hud",
        )
        stamina_lower_text_alt = _ocr_box_region(
            stamina_box,
            x1_ratio=0.48,
            y1_ratio=0.46,
            x2_ratio=0.98,
            y2_ratio=0.98,
            debug_label="pc_stamina_hud_alt",
        )
        stamina_lower_text_legacy = _ocr_box_region(
            stamina_box,
            x1_ratio=0.54,
            y1_ratio=0.48,
            x2_ratio=0.98,
            y2_ratio=0.98,
            debug_label="pc_stamina_hud_legacy",
        )
        genki_value, genki_has_digits = _extract_noisy_hud_value(
            genki_text_color,
            genki_text,
            genki_text_alt,
            previous_value=previous_genki,
            upper_bound=999,
        )
        stamina_value, stamina_has_digits = _extract_noisy_hud_value(
            stamina_text_color,
            stamina_lower_text,
            stamina_lower_text_alt,
            stamina_lower_text_legacy,
            previous_value=previous_stamina,
            upper_bound=previous_max_stamina or 99,
        )
        if not stamina_has_digits and previous_stamina > 0:
            stamina_value = previous_stamina
        if not genki_has_digits and previous_genki > 0:
            genki_value = previous_genki
        stamina_observed = any(
            str(text or "").strip()
            for text in (
                stamina_lower_text,
                stamina_lower_text_alt,
                stamina_lower_text_legacy,
                stamina_text_color,
                stamina_text,
            )
        )
        genki_observed = any(
            str(text or "").strip()
            for text in (
                genki_text_color,
                genki_text,
                genki_text_alt,
            )
        )
        max_stamina_value = previous_max_stamina
    else:
        stamina_value, max_stamina_value = _parse_stamina_text(
            stamina_text,
            previous_stamina=previous_stamina,
            previous_max_stamina=previous_max_stamina,
        )
        stamina_observed = bool(str(stamina_text or "").strip())
        genki_value = previous_genki
        genki_observed = False
    if stamina_observed:
        setattr(app, "_last_produce_hud_stamina", stamina_value)
        if max_stamina_value > 0:
            setattr(app, "_last_produce_hud_max_stamina", max_stamina_value)
    if genki_observed:
        setattr(app, "_last_produce_hud_genki", genki_value)

    bonus_text = _ocr_first(ProducerLabels.PC_BONUS_INDICATOR)
    recommend_text = _ocr_first(ProducerLabels.PC_RECOMMEND_ACTION)
    target_text = _ocr_first(ProducerLabels.PC_TARGET)
    score_text = _ocr_first(ProducerLabels.PC_TRAINING_SCORE)
    remaining_turns_text = _ocr_first(ProducerLabels.PC_TRAINING_REMAINING)
    turn_color = ""
    for token, display in (
        ("Vo", ProduceText.VOCAL),
        ("Da", ProduceText.DANCE),
        ("Vi", ProduceText.VISUAL),
        (ProduceText.VOCAL, ProduceText.VOCAL),
        (ProduceText.DANCE, ProduceText.DANCE),
        (ProduceText.VISUAL, ProduceText.VISUAL),
    ):
        if token and token in bonus_text:
            turn_color = display
            break

    score_bonus = ""
    if bonus_text:
        multiplier_match = _MULTIPLIER_RE.search(bonus_text.replace("x", "×"))
        if multiplier_match:
            score_bonus = multiplier_match.group(1)

    # 排名从上下文读取（由 exam.py 每回合提取并存入）
    exam_ranking_str = get_exam_ranking_value(ctx) if ctx else ""
    p_point_text = _ocr_first(ProducerLabels.PC_P_POINT)
    parameter_upper_bound = int(getattr(ctx, "parameter_growth_limit", 0) or 0)
    vocal_value, vocal_observed = _extract_planning_parameter_value(
        _ocr_first(ProducerLabels.PARAM_VOCAL),
        previous_value=_get_parameter_seed_value(ctx, "vocal"),
        upper_bound=parameter_upper_bound,
    )
    dance_value, dance_observed = _extract_planning_parameter_value(
        _ocr_first(ProducerLabels.PARAM_DANCE),
        previous_value=_get_parameter_seed_value(ctx, "dance"),
        upper_bound=parameter_upper_bound,
    )
    visual_value, visual_observed = _extract_planning_parameter_value(
        _ocr_first(ProducerLabels.PARAM_VISUAL),
        previous_value=_get_parameter_seed_value(ctx, "visual"),
        upper_bound=parameter_upper_bound,
    )

    # ── 解析进度圆圈（课程画面） ──
    # score_text 可能是 "PERFECTまで175CLEAR" 或 "CLEARまで10"
    progress_info = _parse_progress_circle(score_text)
    if progress_info is not None:
        # 进度圆圈模式: 数字是"距离目标的剩余分数"，不是当前累计分数
        score_value = 0
        score_observed = False
    else:
        # 普通模式: 数字就是当前分数（日程/考核画面）
        score_value = _extract_first_int(score_text)
        score_observed = bool(str(score_text or "").strip())

    return {
        "stamina": stamina_value,
        "max_stamina": max_stamina_value,
        "stamina_observed": stamina_observed,
        "genki": genki_value,
        "genki_observed": genki_observed,
        "p_point": _extract_first_int(p_point_text),
        "p_point_observed": bool(str(p_point_text or "").strip()),
        "target_score": _extract_first_int(target_text),
        "target_score_observed": bool(str(target_text or "").strip()),
        "score": score_value,
        "score_observed": score_observed,
        "remaining_turns": _extract_first_int(remaining_turns_text),
        "remaining_turns_observed": bool(str(remaining_turns_text or "").strip()),
        "turn_color": turn_color,
        "score_bonus": score_bonus,
        "exam_ranking": exam_ranking_str,
        "vocal": vocal_value,
        "vocal_observed": vocal_observed,
        "dance": dance_value,
        "dance_observed": dance_observed,
        "visual": visual_value,
        "visual_observed": visual_observed,
        "has_progress_hud": results.exists_label(ProducerLabels.PC_PROGRESS),
        "recommend_action_text": recommend_text,
        "recommend_action_kind": infer_param_kind(recommend_text) if recommend_text else "",
        # 课程进度圆圈解析结果
        "progress_circle": progress_info,
    }


def sync_visible_planning_context(
    app: "AppProcessor",
    ctx: "ProduceContext",
    *,
    phase: str,
    position: str,
    reason: str = "visible_hud_sync",
) -> dict[str, Any]:
    """把当前帧能稳定读到的周规划 HUD 尽快同步到上下文。"""
    setattr(app, "_produce_decision_ctx", ctx)
    setattr(app, "_produce_decision_ctx", ctx)
    hud_state = _extract_hud_state(app)
    updated_fields: list[str] = []

    if bool(hud_state.get("p_point_observed", False)):
        ctx.hud_p_point = int(hud_state.get("p_point") or 0)
        ctx.consult_remaining_p_points = ctx.hud_p_point
        ctx.economy_state = {
            **ctx.economy_state,
            "p_point": ctx.hud_p_point,
        }
        updated_fields.append("p_point")

    next_parameter_state = dict(ctx.parameter_state)
    for key in ("vocal", "dance", "visual"):
        if not bool(hud_state.get(f"{key}_observed", False)):
            continue
        next_parameter_state[key] = hud_state.get(key)
        updated_fields.append(key)
    parameter_limit = int(getattr(ctx, "parameter_growth_limit", 0) or 0)
    if parameter_limit > 0:
        for key in ("vocal", "dance", "visual"):
            next_parameter_state[f"{key}_max"] = parameter_limit
    if updated_fields:
        ctx.parameter_state = next_parameter_state
        ctx.last_sync_reason = reason
        logger.debug(
            "hud: 快速同步周规划上下文 phase={} position={} updated={} p_point={} params={}",
            phase,
            position,
            updated_fields,
            ctx.hud_p_point,
            {
                "vocal": ctx.parameter_state.get("vocal", ""),
                "dance": ctx.parameter_state.get("dance", ""),
                "visual": ctx.parameter_state.get("visual", ""),
            },
        )
    return hud_state


def _build_hand_snapshot(resolved_entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for entity in resolved_entities:
        metadata = dict(entity.get("metadata", {}) or {})
        entries.append({
            "name": entity.get("name") or metadata.get("display_name") or entity.get("label") or "",
            "db_id": entity.get("db_id") or "",
            "category": metadata.get("category") or "",
            "rarity": metadata.get("rarity") or "",
            "upgrade_count": int(metadata.get("upgrade_count") or 0),
            "cost": metadata.get("cost") or 0,
            "description": metadata.get("description") or "",
            "effect_types": list(metadata.get("effect_types", []) or []),
        })
    return entries


def _build_initial_deck_snapshot(ctx: "ProduceContext") -> list[dict[str, Any]]:
    card_details = dict((ctx.formation_details or {}).get("cards_and_items", {}) or {})
    entries = list(card_details.get("matched_entries", []) or [])
    deck_entries: list[dict[str, Any]] = []
    for entry in entries:
        if entry.get("kind") != "produce_card":
            continue
        card_id = str(entry.get("id") or "")
        metadata = _enrich_card_metadata(card_id, upgrade_count=0)
        deck_entries.append({
            "id": card_id,
            "name": metadata.get("display_name") or entry.get("name") or card_id,
            "description": metadata.get("description") or "",
            "category": metadata.get("category") or "",
            "cost": metadata.get("cost") or 0,
            "effect_types": list(metadata.get("effect_types", []) or []),
        })
    return deck_entries


def _build_current_deck_snapshot(ctx: "ProduceContext") -> list[dict[str, Any]]:
    """从初始牌组快照出发，叠加 deck_mutations 返回当前实际牌组。"""
    deck = _build_initial_deck_snapshot(ctx)

    # 按 card_id 索引增量強化记录
    enhance_map: dict[str, int] = {}
    acquired: list[dict[str, Any]] = []
    removed_ids: set[str] = set()

    for m in ctx.deck_mutations:
        mt = m.get("type")
        card_id = str(m.get("card_id") or "")
        kind = str(m.get("kind", "produce_card"))
        if not card_id:
            continue
        if mt == "enhance":
            enhance_map[card_id] = enhance_map.get(card_id, 0) + int(m.get("upgrade_count", 1))
        elif mt == "acquire" and kind == "produce_card":
            acquired.append(m)
        elif mt == "remove" and kind == "produce_card":
            removed_ids.add(card_id)

    # 应用強化: 更新 upgrade_count 并重新获取元数据
    if enhance_map:
        for entry in deck:
            cid = str(entry.get("id") or "")
            if cid in enhance_map:
                uc = min(enhance_map[cid], 3)
                metadata = _enrich_card_metadata(cid, upgrade_count=uc)
                entry["name"] = metadata.get("display_name") or entry.get("name", cid)
                entry["description"] = metadata.get("description") or ""
                entry["category"] = metadata.get("category") or entry.get("category", "")
                entry["cost"] = metadata.get("cost") or entry.get("cost", 0)
                entry["effect_types"] = list(metadata.get("effect_types", []) or [])
                entry["upgrade_count"] = uc

    # 应用削除
    if removed_ids:
        deck = [e for e in deck if str(e.get("id") or "") not in removed_ids]

    # 应用获取
    for m in acquired:
        card_id = str(m.get("card_id") or "")
        if card_id in removed_ids:
            continue
        metadata = _enrich_card_metadata(card_id, upgrade_count=0)
        deck.append({
            "id": card_id,
            "name": metadata.get("display_name") or m.get("name") or card_id,
            "description": metadata.get("description") or "",
            "category": metadata.get("category") or "",
            "cost": metadata.get("cost") or 0,
            "effect_types": list(metadata.get("effect_types", []) or []),
        })

    return deck


def _build_produce_item_snapshot(ctx: "ProduceContext") -> list[dict[str, Any]]:
    card_details = dict((ctx.formation_details or {}).get("cards_and_items", {}) or {})
    item_ids = list(card_details.get("produce_item_ids", []) or [])
    items: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item_id in item_ids:
        sid = str(item_id)
        seen_ids.add(sid)
        metadata = _enrich_item_metadata(sid)
        items.append({
            "id": sid,
            "name": metadata.get("display_name") or sid,
            "description": metadata.get("description") or "",
            "rarity": metadata.get("rarity") or "",
        })
    # 叠加 deck_mutations 中新获取的 produce_item
    for m in ctx.deck_mutations:
        if m.get("type") == "acquire" and m.get("kind") == "produce_item":
            mid = str(m.get("card_id") or "")
            if mid and mid not in seen_ids:
                seen_ids.add(mid)
                metadata = _enrich_item_metadata(mid)
                items.append({
                    "id": mid,
                    "name": metadata.get("display_name") or m.get("name") or mid,
                    "description": metadata.get("description") or "",
                    "rarity": metadata.get("rarity") or "",
                })
    return items


def _build_formation_ability_snapshot(ctx: "ProduceContext") -> list[dict[str, Any]]:
    """Extract matched support/P-idol abilities from formation details for LLM."""
    abilities_data = dict((ctx.formation_details or {}).get("abilities", {}) or {})
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for section_key in ("p_idol_abilities", "lesson_support", "support_abilities"):
        section = abilities_data.get(section_key, {})
        if not isinstance(section, dict):
            continue
        matched = section.get("matched_entries") or []
        for entry in matched:
            eid = str(entry.get("id") or "")
            name = str(entry.get("name") or eid)
            if not eid or eid in seen:
                continue
            seen.add(eid)
            entries.append({"name": name, "section": section_key})
    return entries


def _build_formation_event_snapshot(ctx: "ProduceContext") -> list[dict[str, Any]]:
    """Extract support card events from formation details for LLM."""
    events_data = dict((ctx.formation_details or {}).get("events", {}) or {})
    support_cards = events_data.get("support_cards") or []
    result: list[dict[str, Any]] = []
    for sc in support_cards:
        card_name = sc.get("name") or sc.get("name_ja") or sc.get("id", "")
        events = sc.get("events") or []
        event_lines: list[str] = []
        for ev in events:
            title = ev.get("title") or ev.get("title_ja") or f"Event#{ev.get('number', '?')}"
            descs = ev.get("descriptions") or []
            desc_text = ", ".join(descs) if descs else ""
            if desc_text:
                event_lines.append(f"{title}: {desc_text}")
            else:
                event_lines.append(title)
        result.append({"card_name": card_name, "events": event_lines})
    return result


def _build_drink_snapshot(drink_entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    drinks: list[dict[str, Any]] = []
    for entity in drink_entities:
        metadata = dict(entity.get("metadata", {}) or {})
        drinks.append({
            "id": entity.get("db_id") or "",
            "name": entity.get("name") or metadata.get("display_name") or "",
            "description": metadata.get("description") or "",
            "rarity": metadata.get("rarity") or "",
            "effect_types": list(metadata.get("effect_types", []) or []),
        })
    return drinks


def _compute_remaining_weeks(ctx: "ProduceContext") -> int | None:
    """从 P手帳 数据推算剩余可操作周数。

    P手帳 entries 按游戏周数降序排列，每个 entry 有 ``completed`` 标志。
    剩余周数 = 未完成且非特殊事件的 entry 数量。
    如果没有 P手帳 数据则返回 None。
    """
    notebook = list(ctx.handler_state.get("p_notebook_schedule") or [])
    if not notebook:
        return None
    remaining = 0
    for e in notebook:
        if e.get("completed"):
            continue
        if e.get("special_event") and not e.get("actions"):
            continue
        remaining += 1
    return remaining


def _snapshot_card_category_name(value: Any) -> str:
    category = str(value or "")
    if category in _SNAPSHOT_CARD_CATEGORY_NAMES:
        return _SNAPSHOT_CARD_CATEGORY_NAMES[category]
    return category or "未知"


def _is_offensive_snapshot_card(card: dict[str, Any]) -> bool:
    effect_types = [
        str(value or "")
        for value in card.get("effect_types", []) or []
    ]
    if any(
        keyword in effect_type
        for effect_type in effect_types
        for keyword in _OFFENSIVE_EFFECT_KEYWORDS
    ):
        return True

    description = str(card.get("description") or "")
    return any(keyword in description for keyword in _OFFENSIVE_DESCRIPTION_KEYWORDS)


def _count_offensive_snapshot_cards(cards: list[dict[str, Any]]) -> int:
    return sum(1 for card in cards if _is_offensive_snapshot_card(card))


def _build_snapshot_deck_summary(cards: list[dict[str, Any]]) -> str:
    if not cards:
        return "(空)"

    category_counts: Counter[str] = Counter()
    total_cost = 0.0
    cost_count = 0
    for card in cards:
        category_counts[_snapshot_card_category_name(card.get("category"))] += 1
        if card.get("cost") not in (None, ""):
            total_cost += float(card.get("cost") or 0)
            cost_count += 1

    category_text = ", ".join(
        f"{category}×{count}"
        for category, count in category_counts.most_common()
    )
    if cost_count <= 0:
        return f"分类: {category_text}"
    avg_cost = total_cost / max(cost_count, 1)
    return f"分类: {category_text} | 平均消耗:{avg_cost:.1f}"


def _build_snapshot_reshuffle_hint(
    *,
    deck_cards: list[dict[str, Any]],
    grave_cards: list[dict[str, Any]],
    offensive_counts: dict[str, int],
) -> str:
    if len(deck_cards) <= 2 and grave_cards:
        return f"牌库仅剩{len(deck_cards)}张；下次抽牌大概率会把弃牌堆洗回。"
    if offensive_counts.get("deck", 0) <= 0 and offensive_counts.get("grave", 0) > 0:
        return "当前牌库几乎没有火力牌，后续主要依赖洗回弃牌堆后的再抽。"
    return ""


def _observe_bottom_inventory_drinks(
    app: "AppProcessor",
) -> tuple[list[dict[str, Any]], bool]:
    """观察课内底栏 P 饮料库存，并整理成可复用的实体列表。"""
    results = getattr(app, "latest_results", None)
    frame = getattr(app, "latest_frame", None)
    if results is None or frame is None or getattr(frame, "size", 0) <= 0:
        return [], False

    frame_height = int(frame.shape[0])
    boxes = sorted(
        (
            box
            for box in results.filter_by_label(ProducerLabels.P_DRINK)
            if getattr(box, "cy", 0) >= frame_height * 0.88
        ),
        key=lambda item: item.cx,
    )
    debugger = getattr(app, "debug_tools", None) or DebugTools()
    observed: list[dict[str, Any]] = []
    for index, box in enumerate(boxes):
        resolution = resolve_produce_drink_identity(
            "",
            app=app,
            box=box,
            index=index,
        )
        metadata = dict(resolution.metadata or {})
        display_name = (
            resolution.display_name
            or metadata.get("display_name")
            or resolution.db_id
            or f"Pドリンク#{index + 1}"
        )
        observed.append({
            "action_id": resolution.action_id,
            "db_id": resolution.db_id,
            "name": display_name,
            "source": resolution.source,
            "confidence": resolution.confidence,
            "metadata": metadata,
        })
        coords = _serialize_box(box)
        if coords is None:
            continue
        label_core = resolution.db_id or display_name
        debugger.add_box(
            coords[0],
            coords[1],
            coords[2],
            coords[3],
            label=f"inventory_drink:{index} {str(label_core)[:24]}",
            color=(255, 0, 160),
            alpha=0.18,
            duration=3.0,
            font_size=18,
        )
    return observed, True


def _build_stage_context(
    *,
    phase: str,
    position: str,
    hud_state: dict[str, Any],
    candidate_payloads: list[dict[str, Any]],
) -> dict[str, Any]:
    phase_key = phase.value if hasattr(phase, "value") else str(phase)
    position_key = position.value if hasattr(position, "value") else str(position)
    has_progress_hud = bool(hud_state.get("has_progress_hud"))
    has_battle_drink_actions = any(
        is_produce_drink_action_id(payload.get("id"))
        for payload in candidate_payloads
    )
    has_end_turn_action = any(
        is_end_turn_action_id(payload.get("id"))
        for payload in candidate_payloads
    )

    stage_id = phase_key or "unknown"
    label = "未知阶段"
    description = "当前画面阶段语义尚未稳定识别。"
    available_action_summary = "优先从合法动作列表中选择当前最稳妥的动作。"
    interaction_hint = ""

    if phase_key == GameplayPhase.SCHEDULE:
        stage_id = "schedule_action_select"
        label = "周行动选择"
        description = "当前处于培育周行程页，需要在本周可执行行动中做选择。"
        available_action_summary = "可从候选周行动中选择一项；若已选中行动，则下一次点击会确认进入该行动。"
        interaction_hint = "周行动通常是先选中，再在下一帧确认。"
        if position_key == GameplayPosition.SCHEDULE_PRESENT_SUPPORT:
            stage_id = "schedule_present_support_options"
            label = "活动支给选项"
            description = "当前已进入「活動支給 / 差し入れ」收益选择页，需要在多个加成候选中选一个。"
            available_action_summary = "可从当前活动支给候选项中选择一个收益分支，这类页面通常单击即可确认。"
            interaction_hint = "活动支给候选通常单击就会直接进入后续奖励链。"
        elif position_key == GameplayPosition.SCHEDULE_SELECTED:
            stage_id = "schedule_action_confirm"
            label = "周行动确认"
            description = "当前已有一个周行动被选中，等待确认进入。"
        elif position_key == GameplayPosition.SCHEDULE_RECOMMEND:
            stage_id = "schedule_action_recommend"
    elif phase_key == GameplayPhase.DIALOGUE:
        if has_progress_hud:
            if position_key in {
                GameplayPosition.DIALOGUE_OPTIONS,
                GameplayPosition.SCHEDULE_EVENT_OPTIONS,
            }:
                stage_id = "schedule_event_options"
                label = "周事件选项"
                description = "当前处于培育流程内的周事件分支选择，不是普通コミュ。"
                available_action_summary = "可从当前周事件选项中选择一个分支。"
                interaction_hint = "事件选项通常是先点一次选中，再点一次确认。"
            else:
                stage_id = "schedule_event_dialogue"
                label = "周事件对话推进"
                description = "当前处于培育流程内的周事件文本推进阶段。"
                available_action_summary = "当前无分支时推进文本；若出现选项则转为选择事件分支。"
                interaction_hint = "无选项时以点击推进为主。"
        elif position_key == GameplayPosition.DIALOGUE_OPTIONS:
            stage_id = "dialogue_options"
            label = "普通对话选项"
            description = "当前是普通コミュ对话分支选择。"
            available_action_summary = "可从当前对话选项中选择一个分支。"
            interaction_hint = "对话选项通常是先点一次选中，再点一次确认。"
        else:
            stage_id = "dialogue_continue"
            label = "普通对话推进"
            description = "当前是无分支的剧情推进阶段。"
            available_action_summary = "当前无选项时推进文本；若可快进则也可切换快进。"
            interaction_hint = "普通对话可推进文本，必要时可以快进。"
    elif phase_key == GameplayPhase.LESSON:
        stage_id = "lesson_card_play"
        label = "课程出牌"
        description = "当前处于レッスン回合，需要决定本回合如何出牌。"
        available_action_summary = "可从当前手牌中选择一张技能卡使用；若已有选中卡，则下一次点击会确认出牌。"
        interaction_hint = "出牌通常是先选中卡牌，再确认使用。"
        if has_battle_drink_actions:
            available_action_summary = (
                "可从当前手牌中选择技能卡，也可以直接使用底栏 P 饮料；"
                "饮料通常点击一次就会打开使用确认。"
            )
            interaction_hint = "技能卡按双击使用；P 饮料通常点击图标后进入确认/详情。"
        if has_end_turn_action:
            available_action_summary = f"{available_action_summary} 也可以选择 SKIP，直接结束本回合。"
            interaction_hint = f"{interaction_hint} 选择 SKIP 前若有残留选中态，先取消选中再结束回合。"
        if position_key == GameplayPosition.LESSON_SELECTED:
            stage_id = "lesson_card_confirm"
            label = "课程出牌确认"
            description = "当前已有技能卡被选中，等待确认出牌。"
    elif phase_key == GameplayPhase.EXAM:
        stage_id = "exam_card_play"
        label = "考试出牌"
        description = "当前处于考试/试演回合，需要决定本回合如何出牌。"
        available_action_summary = "可从当前手牌中选择一张技能卡使用；若已有选中卡，则下一次点击会确认出牌。"
        interaction_hint = "出牌通常是先选中卡牌，再确认使用。"
        if position_key == GameplayPosition.EXAM_RETRY_CONFIRM_MODAL:
            stage_id = "exam_retry_confirm"
            label = "考试失败后的再挑战确认"
            description = "当前考试未通过，需要在「再挑戦」与「プロデュース終了」之间做最终选择。"
            available_action_summary = "可选择消耗一次再挑战机会重打本场考试，或直接结束本次培育并接受失败结果。"
            interaction_hint = "左侧通常是再挑戦，右侧通常是プロデュース終了，这个弹窗点击一次就会立即生效。"
            retry_payload = next(
                (payload for payload in candidate_payloads if str(payload.get("id") or "") == "exam_retry"),
                None,
            )
            remaining_retry_count = None
            if retry_payload is not None:
                remaining_retry_count = retry_payload.get("metadata", {}).get("remaining_retry_count")
            if remaining_retry_count is not None:
                description = f"{description} 当前剩余再挑战次数约为 {remaining_retry_count} 次。"
        elif has_battle_drink_actions:
            available_action_summary = (
                "可从当前手牌中选择技能卡，也可以直接使用底栏 P 饮料；"
                "饮料通常点击一次就会打开使用确认。"
            )
            interaction_hint = "技能卡按双击使用；P 饮料通常点击图标后进入确认/详情。"
        if stage_id != "exam_retry_confirm" and has_end_turn_action:
            available_action_summary = f"{available_action_summary} 也可以选择结束本回合，放弃剩余出牌。"
            interaction_hint = f"{interaction_hint} 结束回合前若有残留选中态，先取消选中再点击按钮。"
        if position_key == GameplayPosition.EXAM_SELECTED:
            stage_id = "exam_card_confirm"
            label = "考试出牌确认"
            description = "当前已有技能卡被选中，等待确认出牌。"
    elif phase_key == GameplayPhase.SKILL_REWARD:
        stage_id = "skill_reward_select"
        label = "技能卡奖励选择"
        description = "当前处于技能卡奖励阶段，需要从候选奖励中选择一张。"
        available_action_summary = "可从候选奖励卡中选择一张；若已有选中卡，则下一次点击会确认领取。"
        interaction_hint = "奖励卡通常是先选中，再确认领取。"
        if position_key == GameplayPosition.SKILL_REWARD_SELECTED:
            stage_id = "skill_reward_confirm"
            label = "技能卡奖励确认"
            description = "当前已有奖励卡被选中，等待确认领取。"
    elif phase_key == GameplayPhase.P_DRINK:
        stage_id = "p_drink_select"
        label = "P饮料选择"
        description = "当前处于 P 饮料选择阶段，需要决定是否使用/领取某个饮料。"
        available_action_summary = "可从当前 P 饮料候选中选择一个；若已有选中饮料，则下一次点击会确认。"
        interaction_hint = "P 饮料通常是先选中，再确认。"
        if position_key == "p_drink_limit":
            stage_id = "p_drink_limit"
            label = "P饮料上限处理"
            description = "当前 P 饮料槽已满，需要决定是放弃新饮料，还是丢弃一瓶旧饮料来保留新饮料。"
            available_action_summary = "可选择放弃新饮料，或丢弃一瓶现有饮料以腾出槽位。"
            interaction_hint = "所持上限页的每个动作都会直接改变保留方案。"
        if position_key == GameplayPosition.P_DRINK_SELECTED:
            stage_id = "p_drink_confirm"
            label = "P饮料确认"
            description = "当前已有 P 饮料被选中，等待确认。"
    elif phase_key == GameplayPhase.CONSULT:
        if position_key == GameplayPosition.CONSULT_EXCHANGE:
            stage_id = "consult_exchange"
            label = "咨询兑换"
            description = "当前处于相談兑换页，可执行多个操作后再退出。"
            available_action_summary = "可兑换物品（多次）、打开強化（限1次）、打开削除（限1次）、或退出。"
            interaction_hint = "兑换类候选点选后立即进入下一步；每次操作后会再次询问。"
        else:
            stage_id = "consult_card_select"
            label = "咨询卡牌处理"
            description = "当前处于相談后的卡牌预览/确认页，需要决定强化或删除对象。"
            available_action_summary = "可从当前可见卡牌中选择要强化/删除的目标。"
            interaction_hint = "卡牌目标通常是先选中，再确认。"
    elif phase_key == GameplayPhase.ITEM_SELECT:
        stage_id = "item_select"
        label = "P物品选择"
        description = "当前处于 P 物品选择阶段，需要从候选物品中选择一个。"
        available_action_summary = "可从当前 P 物品候选中选择一个；若已有选中物品，则下一次点击会确认。"
        interaction_hint = "P 物品通常是先选中，再确认。"
        if position_key == GameplayPosition.ITEM_SELECT_SELECTED:
            stage_id = "item_confirm"
            label = "P物品确认"
            description = "当前已有 P 物品被选中，等待确认。"

    candidate_names = [
        payload.get("name") or payload.get("label") or f"动作{payload.get('index', 0)}"
        for payload in candidate_payloads
    ]
    recommended_names = [
        payload.get("name") or payload.get("label") or f"动作{payload.get('index', 0)}"
        for payload in candidate_payloads
        if payload.get("recommended")
    ]

    system_recommendation = ""
    if recommended_names:
        system_recommendation = f"系统当前推荐优先考虑：{' / '.join(recommended_names[:3])}"
        if len(recommended_names) > 3:
            system_recommendation += f" 等{len(recommended_names)}项"
    else:
        recommend_kind = str(hud_state.get("recommend_action_kind") or "").strip()
        recommend_text = str(hud_state.get("recommend_action_text") or "").strip()
        if recommend_kind and recommend_kind != "unknown":
            system_recommendation = f"系统当前推荐优先考虑 {recommend_kind} 系行动"
        elif recommend_text:
            system_recommendation = f"系统当前推荐提示：{recommend_text}"

    return {
        "id": stage_id,
        "label": label,
        "description": description,
        "available_action_summary": available_action_summary,
        "interaction_hint": interaction_hint,
        "candidate_count": len(candidate_payloads),
        "candidate_names": candidate_names,
        "system_recommendation": system_recommendation,
        "is_schedule_context": has_progress_hud,
    }


def _describe_candidate_operation(
    payload: dict[str, Any],
    *,
    phase: str,
    position: str,
    stage_context: dict[str, Any],
) -> str:
    phase_key = phase.value if hasattr(phase, "value") else str(phase)
    position_key = position.value if hasattr(position, "value") else str(position)
    label = str(payload.get("name") or payload.get("label") or f"动作{payload.get('index', 0)}")
    stage_id = str(stage_context.get("id") or "")

    if phase_key == GameplayPhase.SCHEDULE:
        _meta = dict(payload.get("metadata") or {})
        # 使用可读名称（display_name / 识别后的 title），不直接展示 action_id
        readable = str(
            _meta.get("display_name")
            or payload.get("name")
            or payload.get("label")
            or f"动作{payload.get('index', 0)}"
        )
        if stage_id == "schedule_present_support_options":
            return f"点击后会直接选择这项活動支給收益：「{readable}」。"
        if position_key == GameplayPosition.SCHEDULE_SELECTED:
            return f"点击后会确认进入「{readable}」这个周行动。"
        return f"点击后会选中「{readable}」这个周行动，下一帧再次点击会确认进入。"
    if stage_id == "schedule_event_options":
        # おでかけ: 追加 P 点消耗信息
        _meta = dict(payload.get("metadata") or {})
        p_cost = _meta.get("p_cost")
        cost_hint = f"（消耗{p_cost}Pポイント）" if p_cost is not None else ""
        return f"点击后会选中「{label}」这个周事件分支{cost_hint}，下一帧再次点击会确认该分支。"
    if phase_key == GameplayPhase.DIALOGUE and position_key == GameplayPosition.DIALOGUE_OPTIONS:
        return f"点击后会选中「{label}」这个对话分支，下一帧再次点击会确认该分支。"
    if phase_key == GameplayPhase.LESSON:
        if is_end_turn_action_id(payload.get("id")):
            if position_key == GameplayPosition.LESSON_SELECTED:
                return "点击后会先取消当前选中的技能卡，再执行 SKIP 结束本回合。"
            return "点击后会执行 SKIP，放弃本回合剩余出牌并直接进入下一回合。"
        if is_produce_drink_action_id(payload.get("id")):
            return f"点击后会尝试在课程中使用这瓶 P 饮料「{label}」，随后可能进入详情或确认页。"
        if position_key == GameplayPosition.LESSON_SELECTED:
            return f"点击后会确认使用这张技能卡：「{label}」。"
        return f"点击后会选中技能卡「{label}」，下一帧再次点击会确认使用。"
    if phase_key == GameplayPhase.EXAM:
        if position_key == GameplayPosition.EXAM_RETRY_CONFIRM_MODAL:
            action_id = str(payload.get("id") or "")
            if action_id == "exam_retry":
                return "点击后会消耗一次再挑战机会，重新开始当前这场考试，不会直接结束本次培育。"
            if action_id == "produce_end":
                return "点击后会确认结束本次培育，本场考试将按失败处理并退出本次挑战。"
            return f"点击后会在考试失败后的确认弹窗里执行「{label}」。"
        if is_end_turn_action_id(payload.get("id")):
            if position_key == GameplayPosition.EXAM_SELECTED:
                return "点击后会先取消当前选中的技能卡，再结束本回合。"
            return "点击后会结束本回合，放弃当前剩余出牌并推进到下一回合。"
        if is_produce_drink_action_id(payload.get("id")):
            return f"点击后会尝试在考试中使用这瓶 P 饮料「{label}」，随后可能进入详情或确认页。"
        if position_key == GameplayPosition.EXAM_SELECTED:
            return f"点击后会确认在考试中使用这张技能卡：「{label}」。"
        return f"点击后会选中考试用技能卡「{label}」，下一帧再次点击会确认使用。"
    if phase_key == GameplayPhase.SKILL_REWARD:
        _meta = dict(payload.get("metadata") or {})
        if _meta.get("is_redraw"):
            remaining = _meta.get("redraw_remaining", 0)
            return f"点击后会消耗一次再抽選机会（剩余{remaining}回），刷新全部候选技能卡。使用后不可撤销。"
        if position_key == GameplayPosition.SKILL_REWARD_SELECTED:
            return f"点击后会确认领取奖励卡「{label}」。"
        return f"点击后会选中奖励卡「{label}」，下一帧再次点击会确认领取。"
    if phase_key == GameplayPhase.P_DRINK:
        if position_key == "p_drink_limit":
            kind = str(payload.get("kind") or "")
            if kind == "skip_new_drink":
                return f"点击后会放弃新饮料「{label}」，保留当前饮料槽配置。"
            if kind == "discard_existing_drink":
                return f"点击后会丢弃当前库存中的一瓶旧饮料，并保留新饮料「{label}」。"
        if position_key == GameplayPosition.P_DRINK_SELECTED:
            return f"点击后会确认当前选择的 P 饮料「{label}」。"
        return f"点击后会选中 P 饮料「{label}」，下一帧再次点击会确认。"
    if phase_key == GameplayPhase.CONSULT:
        # consult_action 由 hydrate_consult_candidates 写入，标识候选项类型
        consult_action = str(
            payload.get("type")
            or (payload.get("metadata") or {}).get("consult_action")
            or payload.get("label")
            or ""
        )
        # 交换类操作使用 display_name（数据库规范名），因为 label 现在是 DB ID
        _meta = dict(payload.get("metadata") or {})
        display_name = str(
            _meta.get("display_name") or _meta.get("raw_name") or label
        )
        if position_key == GameplayPosition.CONSULT_EXCHANGE:
            if consult_action == "consult_open_enhancement":
                return "点击后会进入技能卡強化页面，可以选择一张技能卡进行強化。"
            if consult_action == "consult_open_remove":
                return "点击后会进入技能卡削除页面，可以选择一张技能卡进行削除。"
            if consult_action == "consult_exit":
                return "点击后会退出相談，结束本次相談环节。"
            # 兑换类物品（饮料 / 技能卡 / P 物品）— 附带价格信息
            price = str(_meta.get("price") or "")
            price_part = f"消耗 {price}P" if price else "消耗对应 P ポイント"
            return f"点击后会尝试兑换「{display_name}」，{price_part}。"
        if consult_action == "consult_confirm_enhancement":
            return f"点击后会确认強化选中的技能卡「{display_name}」。"
        if consult_action == "consult_confirm_remove":
            return f"点击后会确认削除选中的技能卡「{display_name}」。"
        if consult_action in {"consult_select_enhancement_target", "consult_select_remove_target"}:
            return f"点击后会选中「{display_name}」作为相談处理目标，下一帧再确认。"
        return f"点击后会选中「{display_name}」作为相談处理目标，下一帧再确认。"
    if phase_key == GameplayPhase.ITEM_SELECT:
        _item_meta = dict(payload.get("metadata") or {})
        display_name = str(
            _item_meta.get("display_name")
            or _item_meta.get("raw_name")
            or label
        )
        if position_key == GameplayPosition.ITEM_SELECT_SELECTED:
            return f"点击后会确认领取/选择 P 物品「{display_name}」。"
        return f"点击后会选中 P 物品「{display_name}」，下一帧再次点击会确认。"
    return stage_context.get("available_action_summary", "")


def _build_llm_actions(
    candidate_payloads: list[dict[str, Any]],
    *,
    phase: str,
    position: str,
    stage_context: dict[str, Any],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for payload in candidate_payloads:
        phase_key = phase.value if hasattr(phase, "value") else str(phase)
        metadata = dict(payload.get("metadata", {}) or {})
        consult_action = str(payload.get("type") or "")

        # ── 相談: 判断候选是否为实体类（兑换 / 強化选卡 / 削除选卡） ──
        # 这些候选代表具体的游戏实体（卡/饮料/物品），必须有 db_id
        is_consult_entity = (
            phase_key == GameplayPhase.CONSULT
            and (
                consult_action.startswith("consult_exchange")
                or consult_action in {
                    "consult_select_enhancement_target",
                    "consult_select_remove_target",
                }
            )
        )
        # ── 战斗 (lesson/exam): 技能卡必须有 db_id，未识别卡不参与自动决策 ──
        is_battle_card = (
            phase_key in {GameplayPhase.LESSON, GameplayPhase.EXAM}
            and is_produce_card_action_id(payload.get("id"))
        )
        # ── 技能卡奖励: 有 db_id 的卡使用数据库描述，无 db_id 的跳过 ──
        is_skill_reward_card = (
            phase_key == GameplayPhase.SKILL_REWARD
            and is_produce_card_action_id(payload.get("id"))
        )
        # ── 技能卡奖励再抽選: 特殊非实体候选 ──
        is_skill_reward_redraw = (
            phase_key == GameplayPhase.SKILL_REWARD
            and bool(metadata.get("is_redraw"))
        )
        # ── P物品选択: 实体类，有 db_id 则走数据库描述 ──
        is_item_select_entity = (
            phase_key == GameplayPhase.ITEM_SELECT
            and str(payload.get("id") or "").startswith("produce_item:")
        )
        # ── P饮料选择: 有 db_id 的饮料走数据库描述 ──
        is_p_drink_entity = (
            phase_key == GameplayPhase.P_DRINK
            and is_produce_drink_action_id(payload.get("id"))
        )
        # ── おでかけ活動: outing probe 匹配到 DB ID 的選項 ──
        is_outing_entity = (
            str(metadata.get("candidate_type") or "") == "outing_activity"
            and bool(payload.get("db_id"))
        )
        db_id = str(payload.get("db_id") or "")
        # 全链路 DB ID 传递: 无 db_id 的实体候选无法对接 RL / 数据库查询，直接跳过
        if (is_consult_entity or is_battle_card or is_skill_reward_card) and not db_id:
            continue
        # 技能卡奖励: 未识别卡（无 db_id 且非再抽選）也跳过
        if phase_key == GameplayPhase.SKILL_REWARD and not is_skill_reward_card and not is_skill_reward_redraw and not db_id:
            continue
        # 相談兑换: P 点不足的候选直接过滤，避免 LLM 花时间分析买不起的选项
        if is_consult_entity and consult_action.startswith("consult_exchange"):
            price_str = str(metadata.get("price") or "")
            price_val = int(re.search(r"\d+", price_str).group()) if re.search(r"\d+", price_str) else 0
            current_p = int(stage_context.get("p_point") or 0)
            if price_val > 0 and current_p < price_val:
                continue

        is_entity = is_consult_entity or is_battle_card or is_skill_reward_card or (is_item_select_entity and bool(db_id)) or is_outing_entity or (is_p_drink_entity and bool(db_id))

        # ── 描述构建 ──
        if is_skill_reward_redraw:
            # 再抽選: 构建带剩余次数的描述
            remaining = int(metadata.get("redraw_remaining") or 0)
            description = f"再抽選（あと{remaining}回）— 消耗一次再抽選机会，刷新全部候选技能卡"
        elif is_outing_entity:
            # おでかけ活動: DB 描述 + P 成本
            display_name = str(
                metadata.get("display_name")
                or payload.get("name")
                or ""
            )
            p_cost = metadata.get("p_cost")
            # DB マッチ成功時は DB 記述を使用、失敗時は OCR 効果描述を使用
            outing_db_desc = str(metadata.get("outing_db_description") or "")
            outing_effect = str(metadata.get("outing_effect") or "")
            parts: list[str] = [display_name] if display_name else []
            if p_cost is not None:
                parts.append(f"消耗: {p_cost}P")
            else:
                parts.append("免费")
            desc_text = outing_db_desc or outing_effect
            if desc_text:
                parts.append(f"効果: {desc_text}")
            description = " | ".join(parts)
        elif is_entity:
            # 实体类: 所有描述/属性均从数据库查询结果获取，不使用 OCR 原文
            display_name = str(
                metadata.get("display_name")
                or metadata.get("raw_name")
                or payload.get("name")
                or ""
            )
            db_description = str(metadata.get("description") or "")
            # 属性明细（全部来自 _enrich_card_metadata / _enrich_drink_metadata）
            detail_parts: list[str] = []
            upgrade_count = metadata.get("upgrade_count")
            if upgrade_count is not None:
                detail_parts.append(f"等级: {int(upgrade_count)}")
            price = str(metadata.get("price") or "")
            if price:
                detail_parts.append(f"价格: {price}P")
            rarity = str(metadata.get("rarity") or "")
            if rarity:
                rarity_short = rarity.rsplit("_", 1)[-1] if "_" in rarity else rarity
                detail_parts.append(f"稀有度: {rarity_short}")
            plan_label = str(metadata.get("plan_type_label") or "")
            if plan_label:
                detail_parts.append(f"适性: {plan_label}")
            category = str(metadata.get("category") or "")
            if category:
                cat_name = _SNAPSHOT_CARD_CATEGORY_NAMES.get(category, "")
                if cat_name:
                    detail_parts.append(f"分类: {cat_name}")
            cost = int(metadata.get("cost") or 0)
            if cost:
                detail_parts.append(f"消耗体力: {cost}")
            # 组装: "属性1 | 属性2；效果描述"（display_name 已在 label 中，不重复）
            description = " | ".join(detail_parts) if detail_parts else ""
            if db_description:
                description = f"{description}；{db_description}" if description else db_description

            # ── 强化目标: 追加强化后收益对比，帮助 LLM 判断是否值得 ──
            if consult_action == "consult_select_enhancement_target" and upgrade_count is not None:
                next_uc = int(upgrade_count) + 1
                if next_uc <= 3:
                    next_meta = _enrich_card_metadata(db_id, upgrade_count=next_uc)
                    next_desc = str(next_meta.get("description") or "")
                    next_name = str(next_meta.get("display_name") or "")
                    if next_desc and next_desc != db_description:
                        description = f"{description}；【強化後→{next_name}】{next_desc}"
                    elif next_name:
                        description = f"{description}；【強化後→{next_name}】效果不变"
                else:
                    description = f"{description}；已满级，无法再強化"
        else:
            # 非实体类（强化/削除/退出按钮等 + 周行动）: 保持原有逻辑
            description = (
                metadata.get("description")
                or metadata.get("display_name")
                or payload.get("name")
                or ""
            )

        # ── 周行动: 附加效果描述（来自信息面板探查或数据库） ──
        if phase_key == GameplayPhase.SCHEDULE:
            effect_text = str(metadata.get("effect_text") or "").strip()
            # 授業選項: 探査効果描述存放在 lesson_effect 字段
            lesson_effect = str(metadata.get("lesson_effect") or "").strip()
            if lesson_effect and not effect_text:
                effect_text = lesson_effect
            display_name = str(
                metadata.get("display_name")
                or payload.get("name")
                or ""
            ).strip()
            rl_type = str(metadata.get("rl_action_type") or "").strip()
            sched_parts: list[str] = []
            if display_name and display_name != description:
                sched_parts.append(display_name)
            if rl_type:
                sched_parts.append(f"类型: {rl_type}")
            # 授業選項: 附加体力消耗
            stamina_cost = metadata.get("stamina_cost")
            if stamina_cost is not None and metadata.get("lesson_option"):
                sched_parts.append(f"消耗体力: {stamina_cost}")
            if sched_parts:
                prefix = " | ".join(sched_parts)
                description = f"{prefix}；{description}" if description else prefix
            if effect_text and effect_text not in description:
                description = f"{description}；効果: {effect_text}" if description else f"効果: {effect_text}"

        unavailable_reason = str(metadata.get("unavailable_reason") or "").strip()
        if unavailable_reason and unavailable_reason not in description:
            description = (
                f"{description}；注意：{unavailable_reason}"
                if description
                else unavailable_reason
            )
        effect_hint_source = "；".join(
            value
            for value in (
                description,
                " / ".join(str(item or "") for item in metadata.get("effect_types", []) or []),
            )
            if str(value or "").strip()
        )
        effect_hints = (
            _build_effect_term_hints(effect_hint_source)
            if phase_key in {
                GameplayPhase.LESSON,
                GameplayPhase.EXAM,
                GameplayPhase.P_DRINK,
                GameplayPhase.SKILL_REWARD,
                GameplayPhase.CONSULT,
            }
            else []
        )
        if effect_hints:
            effect_hint_text = "；".join(effect_hints[:4])
            description = (
                f"{description}；术语提示：{effect_hint_text}"
                if description
                else f"术语提示：{effect_hint_text}"
            )

        # ── 标签: 实体类用 db_id（RL 对接），おでかけ用可读名（LLM 不需要内部 ID） ──
        if is_outing_entity:
            # おでかけ: LLM 看到可读名称，db_id 仅供 RL 外部消费
            label = str(
                metadata.get("display_name")
                or payload.get("name")
                or payload.get("label")
                or db_id
            )
        elif is_entity:
            # 战斗卡/实体类: label 用可读名称（LLM 需要看懂卡名），db_id 已在 payload 中保留供 RL 使用
            label = str(
                metadata.get("display_name")
                or metadata.get("raw_name")
                or payload.get("name")
                or payload.get("label")
                or db_id
            )
        elif phase_key == GameplayPhase.CONSULT:
            label = str(payload.get("id") or payload.get("name") or payload.get("label") or "")
        else:
            label = str(payload.get("name") or payload.get("label") or "")

        actions.append({
            "index": int(payload.get("index", 0)),
            "kind": consult_action if phase_key == GameplayPhase.CONSULT else payload.get("type", ""),
            "label": label,
            "description": description,
            "recommended": bool(payload.get("recommended", False)),
            "selected": bool(payload.get("selected", False)),
            "available": bool(payload.get("available", True)),
            "operation_meaning": _describe_candidate_operation(
                payload,
                phase=phase,
                position=position,
                stage_context=stage_context,
            ),
        })
    return actions


def _blocked_battle_card_keys(
    ctx: "ProduceContext",
    *,
    phase: str,
    llm_snapshot: dict[str, Any],
) -> set[str]:
    blocked_state = dict(ctx.handler_state.get("battle_blocked_cards", {}) or {})
    current_marker = (
        str(phase or ""),
        int(ctx.current_week or 0),
        int(llm_snapshot.get("remaining") or -1),
    )
    if blocked_state.get("turn_marker") != current_marker:
        ctx.handler_state.pop("battle_blocked_cards", None)
        return set()
    return {
        str(key)
        for key in blocked_state.get("keys", [])
        if str(key or "").strip()
    }


def _zero_resource_dependency_reason(
    description: str,
    *,
    resources: dict[str, Any],
) -> str:
    normalized = fullwidth_to_halfwidth(str(description or ""))
    if not normalized:
        return ""
    for pattern in _PERCENT_BASED_RESOURCE_PATTERNS:
        match = pattern.search(normalized)
        if not match:
            continue
        resource_label = str(match.group(1) or "")
        resource_key = _SNAPSHOT_RESOURCE_KEY_BY_LABEL.get(resource_label, "")
        if not resource_key:
            continue
        if int(resources.get(resource_key) or 0) <= 0:
            return (
                f"当前{resource_label}=0，这张牌的主要效果依赖该资源，"
                "当前回合先不要使用"
            )
    return ""


def _insufficient_cost_reason(
    metadata: dict[str, Any],
    *,
    llm_snapshot: dict[str, Any],
) -> str:
    cost = int(metadata.get("cost") or 0)
    if cost <= 0:
        return ""
    current_stamina = int(llm_snapshot.get("stamina") or 0)
    current_genki = int(
        ((llm_snapshot.get("resources") or {}).get("block"))
        or llm_snapshot.get("genki")
        or 0
    )
    description = str(metadata.get("description") or "")
    direct_stamina_only = any(
        token in description
        for token in (
            "元気は体力のかわりに消費できません",
            "元気のかわりに消費できません",
            "体力を直接消費",
            "体力直接消費",
        )
    )
    available_cost_budget = current_stamina if direct_stamina_only else current_stamina + current_genki
    if available_cost_budget >= cost:
        return ""
    if direct_stamina_only or current_genki <= 0:
        return f"当前体力只有{current_stamina}，但这张牌需要消耗{cost}体力，当前无法使用"
    return (
        f"当前体力只有{current_stamina}，元气只有{current_genki}，可用于支付的总量只有"
        f"{available_cost_budget}，但这张牌需要消耗{cost}体力，当前无法使用"
    )


def _annotate_battle_candidate_availability(
    ctx: "ProduceContext",
    *,
    phase: str,
    candidate_payloads: list[dict[str, Any]],
    llm_snapshot: dict[str, Any],
) -> None:
    phase_key = phase.value if hasattr(phase, "value") else str(phase)
    if phase_key not in {GameplayPhase.LESSON, GameplayPhase.EXAM}:
        return
    blocked_keys = _blocked_battle_card_keys(ctx, phase=phase_key, llm_snapshot=llm_snapshot)
    resources = dict(llm_snapshot.get("resources", {}) or {})
    for payload in candidate_payloads:
        action_id = str(payload.get("id") or "")
        if not is_produce_card_action_id(action_id):
            continue
        metadata = dict(payload.get("metadata", {}) or {})
        description = str(
            metadata.get("description")
            or payload.get("name")
            or payload.get("label")
            or ""
        )
        candidate_keys = {
            str(value)
            for value in (
                action_id,
                payload.get("db_id"),
                payload.get("name"),
                payload.get("label"),
            )
            if str(value or "").strip()
        }
        unavailable_reason = ""
        if blocked_keys and candidate_keys & blocked_keys:
            unavailable_reason = "上一轮已确认当前条件下效果不会发动，本回合先不要再用这张牌"
        elif not bool(payload.get("available", True)):
            unavailable_reason = str(metadata.get("unavailable_reason") or "").strip()
        elif int(llm_snapshot.get("play_limit_remaining") or 1) <= 0:
            unavailable_reason = "本回合已没有剩余出牌次数，当前不能再打出技能卡"
        else:
            unavailable_reason = _insufficient_cost_reason(
                metadata,
                llm_snapshot=llm_snapshot,
            )
        if not unavailable_reason:
            unavailable_reason = _zero_resource_dependency_reason(
                description,
                resources=resources,
            )
        if not unavailable_reason:
            continue
        payload["available"] = False
        payload["unavailable_reason"] = unavailable_reason
        metadata["available"] = False
        metadata["unavailable_reason"] = unavailable_reason
        payload["metadata"] = metadata


_SIM_RESOURCE_KEYS = (
    "parameter_buff",
    "review",
    "aggressive",
    "block",
    "enthusiastic",
    "full_power_point",
    "lesson_buff",
)
_SIM_DECAY_KEYS = ("parameter_buff", "aggressive")
_SIM_DESTINATION_HOLD_KEYWORDS = ("保留",)
_SIM_DESTINATION_LOST_KEYWORDS = ("除外", "削除", "消去")


def register_realtime_resource_snapshot(ctx: "ProduceContext", **values: Any) -> None:
    """注册实时资源观测值，供虚拟状态估算结果覆写。"""
    realtime = ctx.handler_state.setdefault("realtime_battle_state", {})
    resources = realtime.setdefault("resources", {})
    for key, value in values.items():
        if value is not None:
            resources[key] = value


def register_realtime_zone_snapshot(ctx: "ProduceContext", **zones: Any) -> None:
    """注册实时牌区观测值，供虚拟状态估算结果覆写。"""
    realtime = ctx.handler_state.setdefault("realtime_battle_state", {})
    zone_payload = realtime.setdefault("zones", {})
    for key, value in zones.items():
        if value is not None:
            zone_payload[key] = value


def _default_virtual_battle_state() -> dict[str, Any]:
    return {
        "version": 1,
        "initialized": False,
        "instance_seq": 0,
        "last_operation_count": 0,
        "last_remaining_turns": None,
        "turn_index": 1,
        "play_limit_total_current": 1,
        "play_limit_remaining": 1,
        "resources": {key: 0 for key in _SIM_RESOURCE_KEYS},
        "resource_source": {key: "simulated" for key in _SIM_RESOURCE_KEYS},
        "zones": {
            "deck": [],
            "hand": [],
            "grave": [],
            "hold": [],
            "lost": [],
        },
        "zone_source": {
            "deck": "simulated",
            "hand": "simulated",
            "grave": "simulated",
            "hold": "simulated",
            "lost": "simulated",
        },
    }


def _get_virtual_battle_state(ctx: "ProduceContext") -> dict[str, Any]:
    state = ctx.handler_state.get("virtual_battle_state")
    if not isinstance(state, dict) or state.get("version") != 1:
        state = _default_virtual_battle_state()
        ctx.handler_state["virtual_battle_state"] = state
    return state


def _new_virtual_card_instance(state: dict[str, Any], entry: dict[str, Any], *, source: str) -> dict[str, Any]:
    state["instance_seq"] += 1
    return {
        "instance_key": f"{entry.get('id') or entry.get('name') or 'card'}#{state['instance_seq']}",
        "id": str(entry.get("id") or ""),
        "name": str(entry.get("name") or ""),
        "description": str(entry.get("description") or ""),
        "category": str(entry.get("category") or ""),
        "upgrade_count": int(entry.get("upgrade_count") or 0),
        "source": source,
    }


def _bootstrap_virtual_deck(state: dict[str, Any], known_deck: list[dict[str, Any]]) -> None:
    if state["initialized"]:
        return
    state["zones"]["deck"] = [
        _new_virtual_card_instance(state, entry, source="formation")
        for entry in known_deck
    ]
    state["initialized"] = True


def _normalize_card_identity(card: dict[str, Any]) -> str:
    return str(card.get("id") or card.get("name") or "").strip()


def _find_virtual_card(
    state: dict[str, Any],
    observed: dict[str, Any],
) -> tuple[str, dict[str, Any]] | None:
    observed_id = _normalize_card_identity(observed)
    observed_name = str(observed.get("name") or "").strip()
    for zone_name in ("hand", "deck", "grave", "hold", "lost"):
        for card in state["zones"][zone_name]:
            if observed_id and observed_id == _normalize_card_identity(card):
                return zone_name, card
            if observed_name and observed_name == str(card.get("name") or "").strip():
                return zone_name, card
    return None


def _remove_virtual_card_from_all_zones(state: dict[str, Any], instance_key: str) -> None:
    for zone_name in ("deck", "hand", "grave", "hold", "lost"):
        state["zones"][zone_name] = [
            card for card in state["zones"][zone_name]
            if card.get("instance_key") != instance_key
        ]


def _sync_virtual_hand(
    state: dict[str, Any],
    observed_hand: list[dict[str, Any]],
) -> None:
    if not observed_hand:
        state["zones"]["hand"] = []
        return

    current_hand: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for observed in observed_hand:
        found = _find_virtual_card(state, observed)
        if found is None:
            card = _new_virtual_card_instance(
                state,
                {
                    "id": observed.get("db_id") or "",
                    "name": observed.get("name") or "",
                    "description": observed.get("description") or "",
                    "category": observed.get("category") or "",
                    "upgrade_count": observed.get("upgrade_count") or 0,
                },
                source="observed",
            )
        else:
            _, card = found
            _remove_virtual_card_from_all_zones(state, card["instance_key"])
        if card["instance_key"] in seen_keys:
            continue
        seen_keys.add(card["instance_key"])
        current_hand.append(card)

    previous_hand = list(state["zones"]["hand"])
    state["zones"]["hand"] = current_hand
    for card in previous_hand:
        if card.get("instance_key") not in seen_keys:
            state["zones"]["grave"].append(card)


def _extract_simulated_delta(text: str, keyword: str, *, allow_turn_suffix: bool = True) -> int:
    raw = str(text or "")
    if not raw or keyword not in raw:
        return 0
    patterns = [
        rf"{re.escape(keyword)}\s*[+＋]\s*(\d+)",
        rf"{re.escape(keyword)}\s*(\d+){'(?:ターン|回合)' if allow_turn_suffix else ''}",
        rf"[+＋]\s*(\d+)\s*{re.escape(keyword)}",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw)
        if match:
            return int(match.group(1))
    return 0


def _infer_virtual_destination(card: dict[str, Any]) -> str:
    description = str(card.get("description") or "")
    if any(keyword in description for keyword in _SIM_DESTINATION_HOLD_KEYWORDS):
        return "hold"
    if any(keyword in description for keyword in _SIM_DESTINATION_LOST_KEYWORDS):
        return "lost"
    return "grave"


def _apply_virtual_card_effects(state: dict[str, Any], card: dict[str, Any]) -> None:
    description = str(card.get("description") or "")
    state["resources"]["parameter_buff"] += _extract_simulated_delta(description, "好調")
    state["resources"]["review"] += _extract_simulated_delta(description, "集中", allow_turn_suffix=False)
    state["resources"]["aggressive"] += _extract_simulated_delta(description, "好印象")
    state["resources"]["block"] += _extract_simulated_delta(description, "元気", allow_turn_suffix=False)
    state["resources"]["enthusiastic"] += _extract_simulated_delta(description, "熱意", allow_turn_suffix=False)
    state["resources"]["full_power_point"] += _extract_simulated_delta(description, "全力値", allow_turn_suffix=False)
    state["resources"]["lesson_buff"] += _extract_simulated_delta(description, "パラメータ上昇量増加", allow_turn_suffix=False)

    bonus_plays = (
        _extract_simulated_delta(description, "スキルカード使用数追加", allow_turn_suffix=False)
        or _extract_simulated_delta(description, "使用数追加", allow_turn_suffix=False)
    )
    if bonus_plays > 0:
        state["play_limit_total_current"] += bonus_plays
        state["play_limit_remaining"] += bonus_plays


def _find_card_in_hand_by_operation(state: dict[str, Any], operation: Any) -> dict[str, Any] | None:
    details = dict(getattr(operation, "details", {}) or {})
    target = str(getattr(operation, "target", "") or "")
    db_id = str(details.get("db_id") or "")
    for card in state["zones"]["hand"]:
        if db_id and card.get("id") == db_id:
            return card
        if target and target == str(card.get("name") or ""):
            return card
    return None


def _apply_virtual_operations(ctx: "ProduceContext", state: dict[str, Any]) -> None:
    operations = list(ctx.operation_history)
    start_index = int(state.get("last_operation_count", 0) or 0)
    for operation in operations[start_index:]:
        action = str(getattr(operation, "action", "") or "")
        if action == "use_lesson_card":
            card = _find_card_in_hand_by_operation(state, operation)
            if card is None:
                continue
            _remove_virtual_card_from_all_zones(state, card["instance_key"])
            destination = _infer_virtual_destination(card)
            state["zones"][destination].append(card)
            state["play_limit_remaining"] = max(int(state["play_limit_remaining"]) - 1, 0)
            _apply_virtual_card_effects(state, card)
    state["last_operation_count"] = len(operations)


def _advance_virtual_turn(state: dict[str, Any], turns: int = 1) -> None:
    for _ in range(max(int(turns), 0)):
        for key in _SIM_DECAY_KEYS:
            state["resources"][key] = max(int(state["resources"].get(key, 0) or 0) - 1, 0)
        state["turn_index"] = int(state.get("turn_index", 1) or 1) + 1
        state["play_limit_total_current"] = 1
        state["play_limit_remaining"] = 1


def _sync_virtual_turn_boundary(state: dict[str, Any], hud_state: dict[str, Any]) -> None:
    current_remaining = int(hud_state.get("remaining_turns") or 0)
    last_remaining = state.get("last_remaining_turns")
    if last_remaining is None:
        state["last_remaining_turns"] = current_remaining
        return
    if current_remaining <= 0:
        return
    if current_remaining < int(last_remaining):
        _advance_virtual_turn(state, int(last_remaining) - current_remaining)
    state["last_remaining_turns"] = current_remaining


def _merge_realtime_virtual_overrides(ctx: "ProduceContext", state: dict[str, Any]) -> None:
    realtime = ctx.handler_state.get("realtime_battle_state", {})
    for key, value in dict(realtime.get("resources", {}) or {}).items():
        if key in state["resources"] and value is not None:
            state["resources"][key] = value
            state["resource_source"][key] = "realtime"
    for zone_name, payload in dict(realtime.get("zones", {}) or {}).items():
        if zone_name in state["zones"] and payload is not None:
            state["zones"][zone_name] = list(payload)
            state["zone_source"][zone_name] = "realtime"


def _sync_virtual_battle_state(
    ctx: "ProduceContext",
    *,
    hud_state: dict[str, Any],
    known_deck: list[dict[str, Any]],
    observed_hand: list[dict[str, Any]],
) -> dict[str, Any]:
    state = _get_virtual_battle_state(ctx)
    _bootstrap_virtual_deck(state, known_deck)
    _apply_virtual_operations(ctx, state)
    _sync_virtual_turn_boundary(state, hud_state)
    _sync_virtual_hand(state, observed_hand)
    _merge_realtime_virtual_overrides(ctx, state)
    return state


def _build_llm_snapshot(
    ctx: "ProduceContext",
    *,
    phase: str,
    position: str,
    hud_state: dict[str, Any],
    resolved_entities: list[dict[str, Any]],
    stage_context: dict[str, Any],
) -> dict[str, Any]:
    phase_key = phase.value if hasattr(phase, "value") else str(phase)
    known_deck = _build_current_deck_snapshot(ctx)
    hand_entries = _build_hand_snapshot(resolved_entities) if phase_key in {GameplayPhase.LESSON, GameplayPhase.EXAM} else []
    virtual_state = _sync_virtual_battle_state(
        ctx,
        hud_state=hud_state,
        known_deck=known_deck,
        observed_hand=hand_entries,
    ) if phase_key in {GameplayPhase.LESSON, GameplayPhase.EXAM} else None
    idol_plan = _current_idol_plan_payload(ctx)
    if virtual_state is not None:
        hand_entries = list(virtual_state["zones"]["hand"])
    known_drinks = _build_drink_snapshot(ctx.recognized_p_drinks)
    deck_cards = list(virtual_state["zones"]["deck"]) if virtual_state is not None else known_deck
    grave_cards = list(virtual_state["zones"]["grave"]) if virtual_state is not None else []
    hold_cards = list(virtual_state["zones"]["hold"]) if virtual_state is not None else []
    lost_cards = list(virtual_state["zones"]["lost"]) if virtual_state is not None else []
    offensive_counts = {
        "hand": _count_offensive_snapshot_cards(hand_entries),
        "deck": _count_offensive_snapshot_cards(deck_cards),
        "grave": _count_offensive_snapshot_cards(grave_cards),
        "hold": _count_offensive_snapshot_cards(hold_cards),
    }
    deck_summary = _build_snapshot_deck_summary(deck_cards)
    reshuffle_hint = _build_snapshot_reshuffle_hint(
        deck_cards=deck_cards,
        grave_cards=grave_cards,
        offensive_counts=offensive_counts,
    )
    # 优先使用本帧观测到的 target_score，未观测时回退到 ctx 缓存的上次值
    effective_target = hud_state.get("target_score") or getattr(ctx, "hud_target_score", 0) or 0

    # ── 课程进度圆圈信息 ──
    progress_circle = hud_state.get("progress_circle")  # _parse_progress_circle 的结果
    if progress_circle is not None:
        # 进度圆圈模式: score=0, 使用 remaining_to_clear / remaining_to_perfect
        clear_achieved = progress_circle["clear_achieved"]
        remaining_to_clear = progress_circle["remaining_to_clear"]
        remaining_to_perfect = progress_circle["remaining_to_perfect"]
    else:
        clear_achieved = None
        remaining_to_clear = 0
        remaining_to_perfect = 0

    snapshot = {
        "phase": phase_key,
        "position": position,
        "stage_context": stage_context,
        "scenario": ctx.scenario,
        "difficulty": ctx.difficulty,
        "week": ctx.current_week,
        "remaining_weeks": _compute_remaining_weeks(ctx),
        "idol_plan_type": idol_plan["type"],
        "idol_plan_label": idol_plan["label"],
        "idol_plan_focus": idol_plan["focus"],
        "idol_plan_description": idol_plan["description"],
        "parameter_priority": _build_parameter_priority(ctx),
        "turn": virtual_state["turn_index"] if virtual_state is not None else (ctx.lesson_turns_played + 1 if hud_state.get("remaining_turns") else None),
        "remaining": hud_state.get("remaining_turns", 0),
        "max_turns": None,
        "battle_kind": "exam" if phase_key == GameplayPhase.EXAM else "lesson",
        "battle_kind_label": "試験" if phase_key == GameplayPhase.EXAM else "レッスン",
        "score": hud_state.get("score", 0),
        "target": effective_target,
        "ratio": (
            f"{(hud_state.get('score', 0) / max(effective_target, 1)):.0%}"
            if effective_target
            else "未知"
        ),
        # 课程进度圆圈
        "clear_achieved": clear_achieved,
        "remaining_to_clear": remaining_to_clear,
        "remaining_to_perfect": remaining_to_perfect,
        "p_point": hud_state.get("p_point", 0),
        "stamina": hud_state.get("stamina", 0),
        "max_stamina": hud_state.get("max_stamina", 0),
        "genki": hud_state.get("genki", 0),
        "play_limit_remaining": virtual_state["play_limit_remaining"] if virtual_state is not None else None,
        "play_limit_total": virtual_state["play_limit_total_current"] if virtual_state is not None else None,
        "turn_color_label": hud_state.get("turn_color", ""),
        "turn_color_display_label": hud_state.get("turn_color", ""),
        "score_bonus_multiplier": hud_state.get("score_bonus", ""),
        "exam_ranking": hud_state.get("exam_ranking", ""),
        "parameter_stats": _build_parameter_stats_payload(ctx),
        "hand": hand_entries,
        "deck_count": len(deck_cards),
        "deck_summary": deck_summary,
        "deck_cards": deck_cards,
        "grave_cards": grave_cards,
        "hold_cards": hold_cards,
        "lost_cards": lost_cards,
        "zone_counts": {
            "deck": len(deck_cards),
            "grave": len(grave_cards),
            "hold": len(hold_cards),
            "lost": len(lost_cards),
        },
        "offensive_counts": offensive_counts,
        "reshuffle_hint": reshuffle_hint,
        "resources": {
            "parameter_buff": virtual_state["resources"]["parameter_buff"] if virtual_state is not None else "",
            "review": virtual_state["resources"]["review"] if virtual_state is not None else "",
            "aggressive": virtual_state["resources"]["aggressive"] if virtual_state is not None else "",
            "block": virtual_state["resources"]["block"] if virtual_state is not None else "",
            "lesson_buff": virtual_state["resources"]["lesson_buff"] if virtual_state is not None else "",
            "enthusiastic": virtual_state["resources"]["enthusiastic"] if virtual_state is not None else "",
            "full_power_point": virtual_state["resources"]["full_power_point"] if virtual_state is not None else "",
        },
        "stance_desc": "",
        "negatives": "",
        "active_effects": [],
        "active_enchants": [],
        "drinks": known_drinks,
        "available_drink_count": len(known_drinks),
        "used_drink_count": 0,
        "drink_total_count": len(known_drinks),
        "p_items": _build_produce_item_snapshot(ctx),
        "formation_abilities": _build_formation_ability_snapshot(ctx),
        "formation_events": _build_formation_event_snapshot(ctx),
        "gimmicks": "",
        "total_counters": {
            "play_count": 0,
            "stamina_spent": "",
            "block_consumed": "",
        },
        "observability": {
            "deck_order_known": False,
            "resource_panel_parsed": virtual_state is not None,
            "exam_ranking_observed": bool(hud_state.get("exam_ranking")),
            "turn_color_observed": bool(hud_state.get("turn_color")),
            "drink_inventory_observed": bool(ctx.observability_state.get("drink_inventory_observed", False)),
            "empty_hand_observed": bool(ctx.observability_state.get("empty_hand_observed", False)),
        },
    }
    # 考试轮盘队列 + 加成倍率（供 LLM 规划后续回合）
    if phase_key == GameplayPhase.EXAM:
        wheel_info = get_exam_wheel_info(ctx)
        if wheel_info:
            snapshot["exam_wheel"] = {
                "queue": wheel_info.get("queue", []),
                "remaining_turns": wheel_info.get("remaining_turns"),
                "current_param": wheel_info.get("current_param", ""),
                "bonus_pct": wheel_info.get("current_bonus_pct"),
                "confidence": wheel_info.get("confidence", "low"),
            }
        prep_bonuses = get_exam_prep_bonuses(ctx)
        if prep_bonuses:
            snapshot["exam_prep_bonuses"] = {
                "vocal": prep_bonuses.get("vocal_bonus_pct", 0),
                "dance": prep_bonuses.get("dance_bonus_pct", 0),
                "visual": prep_bonuses.get("visual_bonus_pct", 0),
            }
    # 相談 session 操作摘要（告知 LLM 本次相談已做了什么、还能做什么）
    if phase_key == GameplayPhase.CONSULT:
        snapshot["consult_session"] = _build_consult_session_summary(ctx)
    return snapshot


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
    observed_inventory_drinks: list[dict[str, Any]] = []
    drink_inventory_observed = False
    if phase in {GameplayPhase.LESSON, GameplayPhase.EXAM}:
        observed_inventory_drinks, drink_inventory_observed = _observe_bottom_inventory_drinks(app)
    resolved_entities = [payload for payload in candidate_payloads if payload.get("db_id")]
    unresolved_entities = [payload for payload in candidate_payloads if not payload.get("db_id")]
    resolved_card_entities = [
        payload
        for payload in resolved_entities
        if is_produce_card_action_id(payload.get("id"))
    ]
    resolved_drink_entities = [
        payload
        for payload in resolved_entities
        if is_produce_drink_action_id(payload.get("id"))
    ]

    ctx.hud_stamina = hud_state["stamina"]
    if hud_state["max_stamina"] > 0:
        ctx.hud_max_stamina = hud_state["max_stamina"]
    if bool(hud_state.get("p_point_observed", True)):
        ctx.hud_p_point = hud_state["p_point"]
        ctx.consult_remaining_p_points = hud_state["p_point"]
    # 仅在本帧实际观测到目标分数时才更新；课程打牌画面 PC_TARGET 不可检测，
    # 保留上一次（日程页面等）观测到的值
    if hud_state.get("target_score_observed") and hud_state["target_score"] > 0:
        ctx.hud_target_score = hud_state["target_score"]
    ctx.economy_state = {
        "stamina": ctx.hud_stamina,
        "max_stamina": ctx.hud_max_stamina,
        "p_point": ctx.hud_p_point,
    }
    next_parameter_state = {
        "target_score": ctx.hud_target_score,
        "score": hud_state["score"],
        "remaining_turns": hud_state["remaining_turns"],
        "turn_color": hud_state["turn_color"],
        "score_bonus": hud_state["score_bonus"],
        "exam_ranking": hud_state["exam_ranking"],
    }
    for key in ("vocal", "dance", "visual"):
        value = hud_state.get(key)
        if value is not None:
            next_parameter_state[key] = value
        elif key in ctx.parameter_state:
            next_parameter_state[key] = ctx.parameter_state[key]
    parameter_limit = int(getattr(ctx, "parameter_growth_limit", 0) or 0)
    if parameter_limit > 0:
        for key in ("vocal", "dance", "visual"):
            next_parameter_state[f"{key}_max"] = parameter_limit
    ctx.parameter_state = next_parameter_state
    ctx.last_sync_reason = reason
    ctx.state_revision += 1

    if phase in {GameplayPhase.LESSON, GameplayPhase.EXAM} and bool(hud_state.get("genki_observed", False)):
        register_realtime_resource_snapshot(
            ctx,
            block=int(hud_state.get("genki") or 0),
        )

    if phase in {GameplayPhase.LESSON, GameplayPhase.EXAM}:
        ctx.recognized_hand_cards = resolved_card_entities
        ctx.card_zone_state = {
            "hand": resolved_card_entities,
        }
        if drink_inventory_observed:
            ctx.recognized_p_drinks = list(observed_inventory_drinks)
        ctx.inventory_state = {
            **ctx.inventory_state,
            "p_drinks": list(ctx.recognized_p_drinks),
        }
        ctx.observability_state = {
            **ctx.observability_state,
            "draw_pile_order_known": False,
            "drink_inventory_observed": drink_inventory_observed,
        }
    elif phase == GameplayPhase.P_DRINK:
        ctx.recognized_p_drinks = resolved_entities
        ctx.inventory_state = {
            **ctx.inventory_state,
            "p_drinks": resolved_entities,
        }
        ctx.observability_state = {
            **ctx.observability_state,
            "drink_inventory_observed": True,
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
        "remaining_weeks": _compute_remaining_weeks(ctx),
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
    }
    stage_context = _build_stage_context(
        phase=phase,
        position=position,
        hud_state=hud_state,
        candidate_payloads=candidate_payloads,
    )
    # P手帳 日程データを stage_context に注入（LLM の未来計画参照用）
    if phase == GameplayPhase.SCHEDULE:
        notebook_entries = list(ctx.handler_state.get("p_notebook_schedule") or [])
        if notebook_entries:
            stage_context["future_schedule"] = notebook_entries
            stage_context["schedule_history"] = list(ctx.schedule_history or [])
    snapshot["stage_context"] = stage_context
    snapshot["llm_snapshot"] = _build_llm_snapshot(
        ctx,
        phase=phase,
        position=position,
        hud_state=hud_state,
        resolved_entities=(
            resolved_card_entities
            if phase in {GameplayPhase.LESSON, GameplayPhase.EXAM}
            else resolved_entities
        ),
        stage_context=stage_context,
    )
    battle_resources = dict(snapshot["llm_snapshot"].get("resources", {}) or {})
    current_stamina = int(snapshot["llm_snapshot"].get("stamina") or ctx.hud_stamina)
    current_max_stamina = int(snapshot["llm_snapshot"].get("max_stamina") or ctx.hud_max_stamina)
    current_genki = int(
        battle_resources.get("block")
        or snapshot["llm_snapshot"].get("genki")
        or 0
    )
    ctx.economy_state = {
        **ctx.economy_state,
        "battle_stamina": current_stamina,
        "battle_max_stamina": current_max_stamina,
        "battle_genki": current_genki,
    }
    ctx.parameter_state = {
        **ctx.parameter_state,
        "battle_resources": battle_resources,
        "battle_block": battle_resources.get("block", ""),
        "battle_review": battle_resources.get("review", ""),
        "battle_aggressive": battle_resources.get("aggressive", ""),
        "battle_parameter_buff": battle_resources.get("parameter_buff", ""),
    }
    snapshot["economy"] = dict(ctx.economy_state)
    snapshot["parameters"] = dict(ctx.parameter_state)
    _annotate_battle_candidate_availability(
        ctx,
        phase=phase,
        candidate_payloads=candidate_payloads,
        llm_snapshot=snapshot["llm_snapshot"],
    )
    for candidate, payload in zip(candidates, candidate_payloads, strict=False):
        metadata = _coerce_candidate_metadata(candidate)
        if "available" in payload:
            metadata["available"] = bool(payload.get("available", True))
        if payload.get("unavailable_reason"):
            metadata["unavailable_reason"] = str(payload.get("unavailable_reason") or "")
    snapshot["llm_actions"] = _build_llm_actions(
        candidate_payloads,
        phase=phase,
        position=position,
        stage_context=stage_context,
    )
    snapshot["legal_actions"] = [
        payload["index"]
        for payload in candidate_payloads
        if bool(payload.get("available", True))
    ]
    snapshot["resolved_entities"] = resolved_entities
    snapshot["unresolved_entities"] = unresolved_entities
    ctx.handler_state["last_decision_state"] = snapshot
    return snapshot


def build_followup_decision_state(
    ctx: "ProduceContext",
    *,
    phase: str,
    position: str,
    candidates: Sequence[Any],
    reason: str = "followup_decision",
) -> dict[str, Any]:
    """基于上一份稳定快照，为覆盖层/确认页重组一份可供 LLM 使用的决策状态。"""
    phase_key = phase.value if hasattr(phase, "value") else str(phase)
    position_key = position.value if hasattr(position, "value") else str(position)
    previous_state = copy.deepcopy(ctx.handler_state.get("last_decision_state", {}) or {})
    previous_snapshot = dict(previous_state.get("llm_snapshot", {}) or {})
    candidate_payloads = [serialize_candidate(candidate, phase=phase_key) for candidate in candidates]
    stage_context = _build_stage_context(
        phase=phase_key,
        position=position_key,
        hud_state={
            "has_progress_hud": bool(previous_snapshot.get("stage_context", {}).get("is_schedule_context", False)),
            "recommend_action_kind": "",
            "recommend_action_text": "",
        },
        candidate_payloads=candidate_payloads,
    )

    llm_snapshot = {
        **previous_snapshot,
        "phase": phase_key,
        "position": position_key,
        "stage_context": stage_context,
        "scenario": previous_snapshot.get("scenario", ctx.scenario),
        "difficulty": previous_snapshot.get("difficulty", ctx.difficulty),
        "week": previous_snapshot.get("week", ctx.current_week),
        "remaining_weeks": previous_snapshot.get("remaining_weeks") or _compute_remaining_weeks(ctx),
    }
    idol_plan = _current_idol_plan_payload(ctx)
    llm_snapshot.setdefault("idol_plan_type", idol_plan["type"])
    llm_snapshot.setdefault("idol_plan_label", idol_plan["label"])
    llm_snapshot.setdefault("idol_plan_focus", idol_plan["focus"])
    llm_snapshot.setdefault("idol_plan_description", idol_plan["description"])
    llm_snapshot.setdefault("parameter_priority", _build_parameter_priority(ctx))
    # 相談 session 摘要传递
    if phase_key == GameplayPhase.CONSULT:
        llm_snapshot.setdefault("consult_session", _build_consult_session_summary(ctx))
    if phase_key in {GameplayPhase.LESSON, GameplayPhase.EXAM}:
        llm_snapshot.setdefault(
            "battle_kind",
            "exam" if phase_key == GameplayPhase.EXAM else "lesson",
        )
        llm_snapshot.setdefault(
            "battle_kind_label",
            "試験" if phase_key == GameplayPhase.EXAM else "レッスン",
        )
        llm_snapshot.setdefault("turn", None)
        llm_snapshot.setdefault("remaining", None)
        llm_snapshot.setdefault("max_turns", None)
        llm_snapshot.setdefault("score", 0)
        llm_snapshot.setdefault("target", 0)
        llm_snapshot.setdefault("ratio", "0%")
        llm_snapshot.setdefault("stamina", 0)
        llm_snapshot.setdefault("max_stamina", 0)
        llm_snapshot.setdefault("genki", 0)
        llm_snapshot.setdefault("play_limit_remaining", None)
        llm_snapshot.setdefault("play_limit_total", None)
        llm_snapshot.setdefault("turn_color_label", "")
        llm_snapshot.setdefault("turn_color_display_label", "")
        llm_snapshot.setdefault("score_bonus_multiplier", "")
        llm_snapshot.setdefault("exam_ranking", "")
        llm_snapshot.setdefault("deck_count", 0)
        llm_snapshot.setdefault("deck_summary", "未知")
        llm_snapshot.setdefault("reshuffle_hint", "")
        llm_snapshot.setdefault("stance_desc", "")
        llm_snapshot.setdefault("negatives", "")
        llm_snapshot.setdefault("gimmicks", "")
        llm_snapshot.setdefault("available_drink_count", 0)
        llm_snapshot.setdefault("used_drink_count", 0)
        llm_snapshot.setdefault("drink_total_count", 0)
        llm_snapshot.setdefault("hand", [])
        llm_snapshot.setdefault("deck_cards", [])
        llm_snapshot.setdefault("grave_cards", [])
        llm_snapshot.setdefault("hold_cards", [])
        llm_snapshot.setdefault("lost_cards", [])
        llm_snapshot.setdefault("active_effects", [])
        llm_snapshot.setdefault("active_enchants", [])
        llm_snapshot.setdefault("drinks", [])
        llm_snapshot.setdefault("p_items", [])
        llm_snapshot.setdefault("formation_abilities", _build_formation_ability_snapshot(ctx))
        llm_snapshot.setdefault("formation_events", _build_formation_event_snapshot(ctx))
        parameter_stats = {
            "vocal": "",
            "dance": "",
            "visual": "",
            "vocal_max": int(getattr(ctx, "parameter_growth_limit", 0) or 0) or "",
            "dance_max": int(getattr(ctx, "parameter_growth_limit", 0) or 0) or "",
            "visual_max": int(getattr(ctx, "parameter_growth_limit", 0) or 0) or "",
            **dict(llm_snapshot.get("parameter_stats", {}) or {}),
        }
        llm_snapshot["parameter_stats"] = parameter_stats
        zone_counts = {
            "deck": 0,
            "grave": 0,
            "hold": 0,
            "lost": 0,
            **dict(llm_snapshot.get("zone_counts", {}) or {}),
        }
        llm_snapshot["zone_counts"] = zone_counts
        offensive_counts = {
            "hand": 0,
            "deck": 0,
            "grave": 0,
            "hold": 0,
            **dict(llm_snapshot.get("offensive_counts", {}) or {}),
        }
        llm_snapshot["offensive_counts"] = offensive_counts
        resources = {
            "parameter_buff": "",
            "review": "",
            "aggressive": "",
            "block": "",
            "lesson_buff": "",
            "enthusiastic": "",
            "full_power_point": "",
            **dict(llm_snapshot.get("resources", {}) or {}),
        }
        llm_snapshot["resources"] = resources
        total_counters = {
            "play_count": 0,
            "stamina_spent": "",
            "block_consumed": "",
            **dict(llm_snapshot.get("total_counters", {}) or {}),
        }
        llm_snapshot["total_counters"] = total_counters
        observability = {
            "deck_order_known": False,
            "resource_panel_parsed": False,
            "exam_ranking_observed": False,
            "turn_color_observed": False,
            "drink_inventory_observed": False,
            "empty_hand_observed": False,
            **dict(llm_snapshot.get("observability", {}) or {}),
        }
        llm_snapshot["observability"] = observability

    snapshot = {
        **previous_state,
        "phase": phase_key,
        "position": position_key,
        "candidates": candidate_payloads,
        "stage_context": stage_context,
        "llm_snapshot": llm_snapshot,
    }
    snapshot["llm_actions"] = _build_llm_actions(
        candidate_payloads,
        phase=phase_key,
        position=position_key,
        stage_context=stage_context,
    )
    snapshot["legal_actions"] = [
        payload["index"]
        for payload in candidate_payloads
        if bool(payload.get("available", True))
    ]
    ctx.last_sync_reason = reason
    ctx.handler_state["last_decision_state"] = snapshot
    return snapshot
