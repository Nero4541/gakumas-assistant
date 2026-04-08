"""培育阶段运行时，按主数据驱动课程、事件和阶段考试流程。"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np

from .data import MasterDataRepository, ScenarioSpec
from .exam_runtime import ExamRuntime, default_audition_row_selector
from .idol_config import build_initial_exam_deck, build_weighted_card_pool, resolve_produce_card_row, sample_card_from_weighted_pool
from .loadout import IdolLoadout
from .produce_item_interpreter import ActiveProduceItem, ProduceItemInterpreter, RuntimeExamStatusEnchantSpec


ACTION_STEP_TYPES = {
    'lesson_vocal_normal': 'ProduceStepType_LessonVocalNormal',
    'lesson_dance_normal': 'ProduceStepType_LessonDanceNormal',
    'lesson_visual_normal': 'ProduceStepType_LessonVisualNormal',
    'self_lesson_vocal_normal': 'ProduceStepType_SelfLessonVocalNormal',
    'self_lesson_vocal_sp': 'ProduceStepType_SelfLessonVocalSp',
    'self_lesson_dance_normal': 'ProduceStepType_SelfLessonDanceNormal',
    'self_lesson_dance_sp': 'ProduceStepType_SelfLessonDanceSp',
    'self_lesson_visual_normal': 'ProduceStepType_SelfLessonVisualNormal',
    'self_lesson_visual_sp': 'ProduceStepType_SelfLessonVisualSp',
}

ACTION_EFFECT_TYPES = {
    'lesson_vocal_sp': ['ProduceEffectType_VocalAddition', 'ProduceEffectType_LessonVocalSpChangeRatePermilAddition'],
    'lesson_dance_sp': ['ProduceEffectType_DanceAddition', 'ProduceEffectType_LessonDanceSpChangeRatePermilAddition'],
    'lesson_visual_sp': ['ProduceEffectType_VisualAddition', 'ProduceEffectType_LessonVisualSpChangeRatePermilAddition'],
    'lesson_vocal_hard': ['ProduceEffectType_VocalAddition'],
    'lesson_dance_hard': ['ProduceEffectType_DanceAddition'],
    'lesson_visual_hard': ['ProduceEffectType_VisualAddition'],
    'self_lesson_vocal_normal': ['ProduceEffectType_VocalAddition'],
    'self_lesson_vocal_sp': ['ProduceEffectType_VocalAddition'],
    'self_lesson_dance_normal': ['ProduceEffectType_DanceAddition'],
    'self_lesson_dance_sp': ['ProduceEffectType_DanceAddition'],
    'self_lesson_visual_normal': ['ProduceEffectType_VisualAddition'],
    'self_lesson_visual_sp': ['ProduceEffectType_VisualAddition'],
    'activity': ['ProduceEffectType_EventActivityProducePointUp'],
    'business': ['ProduceEffectType_EventBusinessVoteCountUp'],
    'present': ['ProduceEffectType_ProduceReward', 'ProduceEffectType_ProduceRewardSet', 'ProduceEffectType_ProduceCardUpgrade'],
    'refresh': ['ProduceEffectType_StaminaRecoverMultiple'],
}

EVENT_ACTION_TYPES = {'activity', 'business', 'present'}
LESSON_ACTION_TYPES = {
    'lesson_vocal_normal',
    'lesson_dance_normal',
    'lesson_visual_normal',
    'lesson_vocal_sp',
    'lesson_dance_sp',
    'lesson_visual_sp',
    'lesson_vocal_hard',
    'lesson_dance_hard',
    'lesson_visual_hard',
    'self_lesson_vocal_normal',
    'self_lesson_vocal_sp',
    'self_lesson_dance_normal',
    'self_lesson_dance_sp',
    'self_lesson_visual_normal',
    'self_lesson_visual_sp',
}
SP_ACTION_TYPES = {
    'lesson_vocal_sp',
    'lesson_dance_sp',
    'lesson_visual_sp',
    'self_lesson_vocal_sp',
    'self_lesson_dance_sp',
    'self_lesson_visual_sp',
}
HARD_ACTION_TYPES = {
    'lesson_vocal_hard',
    'lesson_dance_hard',
    'lesson_visual_hard',
}


def _is_lesson_action(action_type: str) -> bool:
    """判断动作是否属于课程或自主训练。"""

    return action_type.startswith('lesson_') or action_type.startswith('self_lesson_')


def _lesson_stat_type(action_type: str) -> str:
    """从动作类型中解析对应的属性分支。"""

    parts = action_type.split('_')
    return parts[1] if action_type.startswith('lesson_') else parts[2]


@dataclass
class ProduceActionCandidate:
    """当前周可选的一个培育动作。"""

    label: str
    action_type: str
    effect_types: list[str]
    produce_effect_ids: list[str]
    success_effect_ids: list[str] = field(default_factory=list)
    fail_effect_ids: list[str] = field(default_factory=list)
    stamina_delta: float = 0.0
    produce_point_delta: float = 0.0
    produce_card_id: str = ''
    success_probability: float = 1.0
    stat_deltas: tuple[float, float, float] = (0.0, 0.0, 0.0)
    available: bool = True
    source_row_id: str = ''


class ProduceRuntime:
    """面向训练规划的数据驱动培育运行时。

    这里仍然比正式客户端轻量，但主要转移逻辑已经依赖 ProduceEffect 和事件主数据，
    不再靠少量硬编码卡名来近似。
    """

    def __init__(
        self,
        repository: MasterDataRepository,
        scenario: ScenarioSpec,
        seed: int | None = None,
        idol_loadout: IdolLoadout | None = None,
    ):
        """初始化培育运行时，并预读取事件、课程和卡组相关主数据。"""

        self.repository = repository
        self.scenario = scenario
        self.idol_loadout = idol_loadout
        self.np_random = np.random.default_rng(seed)
        self.produce_row = repository.produces.first(scenario.produce_id) or {}
        self.produce_setting = repository.produce_settings.first(str(self.produce_row.get('produceSettingId') or '')) or {}
        self.produce_effects = repository.load_table('ProduceEffect')
        self.event_suggestions = repository.load_table('ProduceStepEventSuggestion')
        self.event_details = repository.load_table('ProduceStepEventDetail')
        self.card_searches = repository.load_table('ProduceCardSearch')
        self.lesson_levels = repository.load_table('ProduceStepLessonLevel')
        self.produce_item_interpreter = ProduceItemInterpreter(repository)
        self.checkpoints = self._build_checkpoint_positions()
        self.action_samples = self._build_action_samples()

        self.state: dict[str, Any] = {}
        self.deck: list[dict[str, Any]] = []
        self.drinks: list[dict[str, Any]] = []
        self.exam_status_enchant_ids: list[str] = []
        self.exam_status_enchant_specs: list[RuntimeExamStatusEnchantSpec] = []
        self.active_produce_items: list[ActiveProduceItem] = []
        self.support_skills: list[str] = []
        self._candidates: list[ProduceActionCandidate] = []

    def _build_checkpoint_positions(self) -> list[tuple[int, str]]:
        """按路线考试数量计算阶段性考试触发点。"""

        if len(self.scenario.audition_sequence) == 2:
            ratios = [0.5, 1.0]
        else:
            ratios = [0.33, 0.66, 1.0]
        return [
            (max(1, int(round(self.scenario.steps * ratio))), stage)
            for ratio, stage in zip(ratios, self.scenario.audition_sequence)
        ]

    def _base_state(self) -> dict[str, Any]:
        """构造包含属性、成长率和流程加成字段的初始状态。"""

        focus = np.array(self.scenario.score_weights, dtype=np.float32)
        base_stats = 180.0 + focus * 40.0 if self.scenario.route_type == 'nia' else 120.0 + focus * 25.0
        base_stamina = 32.0
        vocal_growth = 0.20
        dance_growth = 0.18
        visual_growth = 0.18
        if self.idol_loadout is not None:
            profile = self.idol_loadout.stat_profile
            base_stats = np.array([profile.vocal, profile.dance, profile.visual], dtype=np.float32)
            base_stamina = float(profile.stamina or base_stamina)
            vocal_growth = float(profile.vocal_growth_rate)
            dance_growth = float(profile.dance_growth_rate)
            visual_growth = float(profile.visual_growth_rate)
        parameter_limit = self._parameter_growth_limit()
        if parameter_limit > 0:
            base_stats = np.clip(base_stats, 0.0, parameter_limit)
        customize_slots = int(self.produce_setting.get('customizeProduceCardCount') or 0)
        return {
            'step': 0,
            'max_steps': int(self.scenario.steps),
            'stamina': float(base_stamina),
            'max_stamina': float(base_stamina),
            'produce_points': float(self.produce_setting.get('initialProducePoint') or 0),
            'fan_votes': 0.0,
            'gold_bonus': 0.0,
            'vocal': float(base_stats[0]),
            'dance': float(base_stats[1]),
            'visual': float(base_stats[2]),
            'vocal_growth': float(vocal_growth),
            'dance_growth': float(dance_growth),
            'visual_growth': float(visual_growth),
            'refresh_used': 0,
            'audition_index': 0,
            'last_exam_score': 0.0,
            'deck_quality': 0.0,
            'drink_quality': 0.0,
            'activity_produce_point_bonus': 0.0,
            'business_vote_bonus': 0.0,
            'lesson_present_point_bonus': 0.0,
            'support_event_point_bonus': 0.0,
            'support_event_stat_bonus': 0.0,
            'support_event_stamina_bonus': 0.0,
            'audition_vote_bonus': 0.0,
            'audition_parameter_bonus': 0.0,
            'audition_difficulty_bonus': 0.0,
            'audition_turn_modifier': 0.0,
            'before_audition_refresh_penalty': 0.0,
            'generic_sp_rate_bonus': 0.0,
            'vocal_sp_rate_bonus': 0.0,
            'dance_sp_rate_bonus': 0.0,
            'visual_sp_rate_bonus': 0.0,
            'reward_card_count_bonus': 0.0,
            'customize_slots': float(customize_slots),
            'exclude_count_bonus': 0.0,
            'reroll_count_bonus': 0.0,
            'shop_discount': 0.0,
            'card_upgrade_probability_bonus': 0.0,
            'producer_level': float(self.idol_loadout.producer_level if self.idol_loadout else 0),
            'idol_rank': float(self.idol_loadout.idol_rank if self.idol_loadout else 0),
            'dearness_level': float(self.idol_loadout.dearness_level if self.idol_loadout else 0),
            'exam_score_bonus_multiplier': float(self.idol_loadout.exam_score_bonus_multiplier if self.idol_loadout else 1.0),
            'parameter_growth_limit': float(parameter_limit),
        }

    def _parameter_growth_limit(self) -> float:
        """返回当前模式主数据里的三维成长上限。"""

        return max(float(getattr(self.scenario, 'parameter_growth_limit', 0.0) or 0.0), 0.0)

    def _clamp_parameter_value(self, value: float) -> float:
        """按当前模式上限裁剪单项三维属性。"""

        limit = self._parameter_growth_limit()
        if limit > 0:
            return float(np.clip(value, 0.0, limit))
        return max(float(value), 0.0)

    def _gain_parameter(self, key: str, delta: float) -> None:
        """统一处理培育阶段的三维属性增长，确保不会超过模式上限。"""

        self.state[key] = self._clamp_parameter_value(float(self.state.get(key) or 0.0) + float(delta))

    def reset(self) -> None:
        """重置培育状态、初始牌组、饮料与开场效果。"""

        self.state = self._base_state()
        self.deck = list(build_initial_exam_deck(self.repository, self.scenario, rng=self.np_random, loadout=self.idol_loadout))
        self.drinks = list(
            self.repository.build_drink_inventory(
                self.scenario,
                rng=self.np_random,
                plan_type=self.idol_loadout.stat_profile.plan_type if self.idol_loadout is not None else None,
            )
        )
        self.exam_status_enchant_ids = []
        self.exam_status_enchant_specs = []
        self.active_produce_items = []
        self.support_skills = []
        self._apply_loadout_start_effects()
        self._dispatch_produce_item_phase('ProducePhaseType_ProduceStart')
        self._trim_drinks()
        self._refresh_quality_scores()

    def _apply_loadout_start_effects(self) -> None:
        """把偶像卡自带 P 道具、附魔和开场技能灌入状态。"""

        if self.idol_loadout is None:
            return
        if self.idol_loadout.produce_item_id:
            self._register_produce_item(self.idol_loadout.produce_item_id, source='loadout')
        for skill in self.idol_loadout.produce_skills:
            if skill.trigger_id and 'produce_start' not in skill.trigger_id:
                continue
            self._apply_effect_rows(list(skill.effect_ids), source_action_type='idol_skill')

    def _append_exam_status_enchant(
        self,
        enchant_id: str,
        *,
        effect_turn: int | None = None,
        effect_count: int | None = None,
        source: str = 'produce',
        source_identity: str = '',
    ) -> None:
        """记录一个待带入考试运行时的附魔规格。"""

        if not enchant_id:
            return
        self.exam_status_enchant_ids.append(enchant_id)
        self.exam_status_enchant_specs.append(
            RuntimeExamStatusEnchantSpec(
                enchant_id=enchant_id,
                effect_turn=effect_turn,
                effect_count=effect_count,
                source=source,
                source_identity=source_identity,
            )
        )

    def _register_produce_item(self, item_id: str, *, source: str = 'reward') -> None:
        """把一个 P 道具加入运行时库存，并处理无 trigger 的静态效果。"""

        active_item = self.produce_item_interpreter.activate_item(item_id, source=source)
        if active_item is None:
            return
        self.active_produce_items.append(active_item)
        if active_item.trigger is not None:
            return
        for effect in active_item.spec.effects:
            self._apply_resolved_produce_item_effect(active_item, effect, source_action_type='idol_item')

    def _apply_resolved_produce_item_effect(
        self,
        active_item: ActiveProduceItem,
        effect,
        *,
        source_action_type: str,
    ) -> None:
        """应用一条已解析的 item effect。"""

        if effect.effect_type == 'ProduceItemEffectType_ExamStatusEnchant':
            self._append_exam_status_enchant(
                effect.enchant_id,
                effect_turn=effect.effect_turn,
                effect_count=effect.effect_count,
                source='produce_item',
                source_identity=active_item.item_id,
            )
            return
        if effect.effect_type == 'ProduceItemEffectType_ProduceEffect':
            produce_effect = self.repository.produce_effects.first(effect.produce_effect_id)
            if produce_effect is None:
                return
            self._apply_produce_effect(
                produce_effect,
                source_action_type=source_action_type,
                source='produce_item',
                source_identity=active_item.item_id,
            )

    def _dispatch_produce_item_phase(self, phase_type: str, **context: Any) -> None:
        """按 phase 触发当前持有的 P 道具效果。"""

        if not self.active_produce_items:
            return
        snapshot = list(self.active_produce_items)
        for active_item in snapshot:
            if not self.produce_item_interpreter.should_fire(
                active_item,
                phase_type=phase_type,
                scenario=self.scenario,
                state=self.state,
                deck=self.deck,
                context=context,
            ):
                continue
            self.produce_item_interpreter.mark_fired(active_item)
            for effect in active_item.spec.effects:
                self._apply_resolved_produce_item_effect(active_item, effect, source_action_type='idol_item')

    def _stage_trigger_phases(self, stage_type: str) -> tuple[str, ...]:
        """把 checkpoint stage type 映射到 item trigger phase。"""

        phases = ['ProducePhaseType_StartAudition']
        if stage_type == 'ProduceStepType_AuditionMid1':
            phases.append('ProducePhaseType_StartAuditionMid1')
        elif stage_type == 'ProduceStepType_AuditionMid2':
            phases.append('ProducePhaseType_StartAuditionMid2')
        elif stage_type == 'ProduceStepType_AuditionFinal':
            phases.append('ProducePhaseType_StartAuditionFinal')
        return tuple(phases)

    def _business_reward_kind(self, source_row_id: str) -> str:
        """从营业事件 row id 中提取产出类型标签。"""

        if 'produce_card' in source_row_id:
            return 'produce_card'
        if 'produce_drink' in source_row_id:
            return 'produce_drink'
        if 'produce_point' in source_row_id:
            return 'produce_point'
        return ''

    def _pre_audition_item_phases(self) -> tuple[str, ...]:
        """返回考试前自动经历的咨询/特训 phase 顺序。"""

        return (
            'ProducePhaseType_StartShop',
            'ProducePhaseType_EndShop',
            'ProducePhaseType_StartCustomize',
        )

    def legal_actions(self) -> list[ProduceActionCandidate]:
        """采样当前周的所有动作候选，并标记可用性。"""

        candidates: list[ProduceActionCandidate] = []
        for action_type in self.scenario.action_types:
            candidate = self._sample_action(action_type)
            candidate.available = self._action_available(candidate)
            candidates.append(candidate)
        self._candidates = candidates
        return candidates

    def step(self, action_index: int) -> tuple[float, bool, dict[str, Any]]:
        """执行一个培育动作，并在到达检查点时触发考试。"""

        candidate = self._candidates[action_index]
        if not candidate.available:
            return -0.25, False, {'invalid_action': True}

        reward = -0.01
        phase_context = {
            'action_type': candidate.action_type,
            'source_row_id': candidate.source_row_id,
            'business_reward_kind': self._business_reward_kind(candidate.source_row_id),
        }
        if _is_lesson_action(candidate.action_type):
            self._dispatch_produce_item_phase('ProducePhaseType_StartLesson', **phase_context)
        elif candidate.action_type == 'present':
            self._dispatch_produce_item_phase('ProducePhaseType_StartPresent', **phase_context)
        elif candidate.action_type == 'refresh':
            self._dispatch_produce_item_phase('ProducePhaseType_StartRefresh', **phase_context)

        self.state['stamina'] = float(np.clip(self.state['stamina'] + candidate.stamina_delta, 0.0, self.state['max_stamina']))
        self.state['produce_points'] += candidate.produce_point_delta * self._produce_point_rate(candidate.action_type)
        self._gain_parameter('vocal', candidate.stat_deltas[0])
        self._gain_parameter('dance', candidate.stat_deltas[1])
        self._gain_parameter('visual', candidate.stat_deltas[2])
        if candidate.produce_card_id:
            card_row = resolve_produce_card_row(self.repository, candidate.produce_card_id, loadout=self.idol_loadout)
            if card_row is not None:
                self.deck.append(dict(card_row))

        self._apply_effect_rows(candidate.produce_effect_ids, source_action_type=candidate.action_type)
        succeeded = self.np_random.random() <= candidate.success_probability
        self._apply_effect_rows(candidate.success_effect_ids if succeeded else candidate.fail_effect_ids, source_action_type=candidate.action_type)
        if candidate.action_type == 'refresh':
            self.state['refresh_used'] += 1
        if _is_lesson_action(candidate.action_type):
            self._dispatch_produce_item_phase('ProducePhaseType_EndLesson', **phase_context)
            self._dispatch_produce_item_phase('ProducePhaseType_EndLessonBeforePresent', **phase_context)
        elif candidate.action_type == 'activity':
            self._dispatch_produce_item_phase('ProducePhaseType_EndStepEventActivity', **phase_context)
        elif candidate.action_type == 'business':
            self._dispatch_produce_item_phase('ProducePhaseType_EndStepEventBusiness', **phase_context)
        elif candidate.action_type == 'present':
            self._dispatch_produce_item_phase('ProducePhaseType_EndStepEventSchool', **phase_context)
            self._dispatch_produce_item_phase('ProducePhaseType_EndPresent', **phase_context)

        self.state['step'] += 1
        self._trim_drinks()
        self._refresh_quality_scores()

        info = {
            'action': candidate.label,
            'action_type': candidate.action_type,
            'success': succeeded,
            'vocal': self.state['vocal'],
            'dance': self.state['dance'],
            'visual': self.state['visual'],
            'stamina': self.state['stamina'],
            'produce_points': self.state['produce_points'],
            'fan_votes': self.state['fan_votes'],
        }

        # 考试会复用当前已经组好的牌组、饮料和继承下来的附魔。
        while self.state['audition_index'] < len(self.checkpoints):
            checkpoint_step, stage_type = self.checkpoints[self.state['audition_index']]
            if self.state['step'] < checkpoint_step:
                break
            exam_reward, exam_info = self._run_audition(stage_type)
            reward += exam_reward
            info[f'audition_{self.state["audition_index"]}'] = exam_info
            self.state['audition_index'] += 1

        terminated = self.state['step'] >= self.state['max_steps']
        if terminated and self.state['audition_index'] < len(self.checkpoints):
            while self.state['audition_index'] < len(self.checkpoints):
                _, stage_type = self.checkpoints[self.state['audition_index']]
                exam_reward, exam_info = self._run_audition(stage_type)
                reward += exam_reward
                info[f'audition_{self.state["audition_index"]}'] = exam_info
                self.state['audition_index'] += 1
        return reward, terminated, info

    def _action_available(self, candidate: ProduceActionCandidate) -> bool:
        """根据体力和休息次数判断动作当前是否可用。"""

        if candidate.action_type == 'refresh':
            return self.state['refresh_used'] < max(self.scenario.max_refresh_count, 1)
        if candidate.action_type != 'refresh' and self.state['stamina'] <= 0.0:
            return False
        if candidate.action_type != 'refresh' and self.state['stamina'] + candidate.stamina_delta < 0.0:
            return False
        return True

    def _build_action_samples(self) -> dict[str, list[dict[str, Any]]]:
        """预先按动作类型整理事件候选样本。"""

        samples: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in self.event_suggestions.rows:
            step_type = str(row.get('stepType') or 'ProduceStepType_Unknown')
            for action_type, mapped_step_type in ACTION_STEP_TYPES.items():
                if step_type == mapped_step_type:
                    samples[action_type].append(row)
        for row in self.event_details.rows:
            event_type = str(row.get('eventType') or 'ProduceEventType_Unknown')
            if event_type == 'ProduceEventType_Activity':
                samples['activity'].append(row)
            elif event_type == 'ProduceEventType_Business':
                samples['business'].append(row)
            elif event_type in {'ProduceEventType_SupportCard', 'ProduceEventType_School', 'ProduceEventType_Character'}:
                samples['present'].append(row)
        return samples

    def _sample_action(self, action_type: str) -> ProduceActionCandidate:
        """为指定动作类型采样一条本周可执行动作。"""

        if action_type == 'refresh':
            recovery_permille = float(self.produce_setting.get('refreshStaminaRecoveryPermil') or 700)
            return ProduceActionCandidate(
                label='休息',
                action_type=action_type,
                effect_types=ACTION_EFFECT_TYPES[action_type],
                produce_effect_ids=self._effect_ids_for_types(ACTION_EFFECT_TYPES[action_type]),
                stamina_delta=self.state['max_stamina'] * (recovery_permille / 1000.0),
            )
        rows = self.action_samples.get(action_type, [])
        if rows:
            row = rows[int(self.np_random.integers(0, len(rows)))]
            produce_effect_ids = [str(value) for value in row.get('produceEffectIds', []) if value]
            success_effect_ids = [str(value) for value in row.get('successProduceEffectIds', []) if value]
            fail_effect_ids = [str(value) for value in row.get('failProduceEffectIds', []) if value]
            stamina_delta = -float(row.get('stamina') or 0)
            produce_point_delta = float(row.get('producePoint') or 0)
            produce_card_id = str(row.get('produceCardId') or '')
            effect_types = self._effect_types_for_ids(produce_effect_ids + success_effect_ids + fail_effect_ids)
            if not effect_types:
                effect_types = list(ACTION_EFFECT_TYPES.get(action_type, []))
            success_probability = float(row.get('successProbabilityPermyriad') or 10000) / 10000.0
            if action_type in SP_ACTION_TYPES:
                success_probability += self._sp_rate_bonus(action_type)
            success_probability = float(np.clip(success_probability, 0.05, 1.0))
            return ProduceActionCandidate(
                label=self._action_label(action_type),
                action_type=action_type,
                effect_types=effect_types,
                produce_effect_ids=produce_effect_ids,
                success_effect_ids=success_effect_ids,
                fail_effect_ids=fail_effect_ids,
                stamina_delta=stamina_delta,
                produce_point_delta=produce_point_delta,
                produce_card_id=produce_card_id,
                success_probability=success_probability,
                source_row_id=str(row.get('id') or ''),
            )
        if action_type in HARD_ACTION_TYPES:
            lesson_profiles = self.repository.lesson_profile_stats
            normal_profile = max(float(lesson_profiles.get('normal') or 170.0), 1.0)
            hard_profile = max(float(lesson_profiles.get('hard') or normal_profile), normal_profile)
            hard_scale = hard_profile / normal_profile
            stage_scale = 1.0 + 0.08 * float(self.state['audition_index'])
            parameter_gain = 60.0 * hard_scale * stage_scale
            stamina_cost = 5.0 + 1.5 * hard_scale
            produce_point_delta = 2.0 + 1.2 * hard_scale
            success_probability = float(np.clip(0.9 - 0.04 * hard_scale + 0.01 * self.state['audition_index'], 0.7, 0.88))
            stat_type = _lesson_stat_type(action_type)
            stat_deltas = {
                'vocal': (parameter_gain, 0.0, 0.0),
                'dance': (0.0, parameter_gain, 0.0),
                'visual': (0.0, 0.0, parameter_gain),
            }[stat_type]
            return ProduceActionCandidate(
                label=self._action_label(action_type),
                action_type=action_type,
                effect_types=list(ACTION_EFFECT_TYPES.get(action_type, [])),
                produce_effect_ids=[],
                stamina_delta=-stamina_cost,
                produce_point_delta=produce_point_delta,
                success_probability=success_probability,
                stat_deltas=stat_deltas,
                source_row_id=f'synthetic-hard-{action_type}',
            )
        synthetic_types = list(ACTION_EFFECT_TYPES.get(action_type, []))
        if action_type.startswith('self_lesson_'):
            stage_index = min(max(int(self.state['audition_index']) + 1, 1), 3)
            scenario_code = self.scenario.produce_id.replace('-', '_')
            lesson_tier = 'sp' if action_type.endswith('_sp') else 'normal'
            lesson_row = self.repository.load_table('ProduceStepSelfLesson').first(f'self_lesson-{scenario_code}-{stage_index:02d}-{lesson_tier}') or {}
            parameter_gain = float(lesson_row.get('parameter') or (120 if lesson_tier == 'sp' else 100))
            stamina_cost = float(lesson_row.get('stamina') or (8 if lesson_tier == 'sp' else 6))
            stat_type = _lesson_stat_type(action_type)
            stat_deltas = {
                'vocal': (parameter_gain, 0.0, 0.0),
                'dance': (0.0, parameter_gain, 0.0),
                'visual': (0.0, 0.0, parameter_gain),
            }[stat_type]
            return ProduceActionCandidate(
                label=self._action_label(action_type),
                action_type=action_type,
                effect_types=synthetic_types,
                produce_effect_ids=[],
                stamina_delta=-stamina_cost,
                produce_point_delta=0.0,
                success_probability=1.0,
                stat_deltas=stat_deltas,
            )
        if not synthetic_types and _is_lesson_action(action_type):
            stat_type = _lesson_stat_type(action_type)
            mapping = {
                'vocal': 'ProduceEffectType_VocalAddition',
                'dance': 'ProduceEffectType_DanceAddition',
                'visual': 'ProduceEffectType_VisualAddition',
            }
            synthetic_types = [mapping[stat_type]]
        success_probability = 1.0
        stamina_delta = 0.0
        produce_point_delta = 0.0
        if action_type in SP_ACTION_TYPES:
            success_probability = float(np.clip(0.82 + self._sp_rate_bonus(action_type), 0.05, 1.0))
            stamina_delta = -8.0
            produce_point_delta = 4.0
        elif action_type in LESSON_ACTION_TYPES:
            success_probability = 0.92
            stamina_delta = -5.0
            produce_point_delta = 2.0
        elif action_type == 'activity':
            success_probability = 0.95
            stamina_delta = 1.0
            produce_point_delta = 6.0
        elif action_type == 'business':
            success_probability = 0.96
            stamina_delta = -2.0
            produce_point_delta = 6.0
        elif action_type == 'present':
            success_probability = 0.98
            produce_point_delta = 2.0
        return ProduceActionCandidate(
            label=self._action_label(action_type),
            action_type=action_type,
            effect_types=synthetic_types,
            produce_effect_ids=self._effect_ids_for_types(synthetic_types),
            stamina_delta=stamina_delta,
            produce_point_delta=produce_point_delta,
            success_probability=success_probability,
        )

    def _effect_ids_for_types(self, effect_types: list[str]) -> list[str]:
        """按效果类型随机抽取对应的 ProduceEffect 行。"""

        effect_ids: list[str] = []
        for effect_type in effect_types:
            candidates = [row for row in self.produce_effects.rows if str(row.get('produceEffectType')) == effect_type]
            if not candidates:
                continue
            effect_ids.append(str(candidates[int(self.np_random.integers(0, len(candidates)))].get('id')))
        return effect_ids

    def _effect_types_for_ids(self, effect_ids: list[str]) -> list[str]:
        """把效果 id 列表反解为效果类型集合。"""

        effect_types: set[str] = set()
        for effect_id in effect_ids:
            effect_row = self.produce_effects.first(str(effect_id))
            if effect_row and effect_row.get('produceEffectType'):
                effect_types.add(str(effect_row['produceEffectType']))
        return sorted(effect_types)

    def _apply_effect_rows(self, effect_ids: list[str], source_action_type: str) -> None:
        """按 id 顺序应用一组 ProduceEffect。"""

        for effect_id in effect_ids:
            effect_row = self.produce_effects.first(str(effect_id))
            if effect_row is not None:
                self._apply_produce_effect(effect_row, source_action_type=source_action_type)

    def _apply_produce_effect(
        self,
        effect: dict[str, Any],
        source_action_type: str,
        *,
        source: str = 'produce',
        source_identity: str = '',
    ) -> None:
        """把单条 ProduceEffect 映射到当前培育状态。"""

        effect_type = str(effect.get('produceEffectType') or '')
        value = self._sample_effect_value(effect)
        event_action = source_action_type in EVENT_ACTION_TYPES

        # 直接增益会立刻写回当前培育状态；下面这类倍率增益则修改后续课程/事件，
        # 这样策略才能在新卡进入卡池时继续泛化。
        if effect_type == 'ProduceEffectType_VocalAddition':
            gain = value * (1.0 + self.state['vocal_growth'])
            if event_action:
                gain *= 1.0 + self.state['support_event_stat_bonus']
            self._gain_parameter('vocal', gain)
            return
        if effect_type == 'ProduceEffectType_DanceAddition':
            gain = value * (1.0 + self.state['dance_growth'])
            if event_action:
                gain *= 1.0 + self.state['support_event_stat_bonus']
            self._gain_parameter('dance', gain)
            return
        if effect_type == 'ProduceEffectType_VisualAddition':
            gain = value * (1.0 + self.state['visual_growth'])
            if event_action:
                gain *= 1.0 + self.state['support_event_stat_bonus']
            self._gain_parameter('visual', gain)
            return
        if effect_type == 'ProduceEffectType_VocalGrowthRateAddition':
            self.state['vocal_growth'] += value / 1000.0
            return
        if effect_type == 'ProduceEffectType_DanceGrowthRateAddition':
            self.state['dance_growth'] += value / 1000.0
            return
        if effect_type == 'ProduceEffectType_VisualGrowthRateAddition':
            self.state['visual_growth'] += value / 1000.0
            return
        if effect_type == 'ProduceEffectType_MaxStaminaAddition':
            self.state['max_stamina'] += value
            self.state['stamina'] = min(self.state['stamina'] + value, self.state['max_stamina'])
            return
        if effect_type == 'ProduceEffectType_MaxStaminaReduceFix':
            self.state['max_stamina'] = max(self.state['max_stamina'] - value, 1.0)
            self.state['stamina'] = min(self.state['stamina'], self.state['max_stamina'])
            return
        if effect_type in {'ProduceEffectType_StaminaRecoverFix', 'ProduceEffectType_EventSchoolStaminaUp'}:
            self.state['stamina'] = min(
                self.state['max_stamina'],
                self.state['stamina'] + value * self._stamina_recovery_rate(source_action_type),
            )
            return
        if effect_type == 'ProduceEffectType_StaminaRecoverMultiple':
            self.state['stamina'] = min(
                self.state['max_stamina'],
                self.state['stamina'] + self.state['max_stamina'] * (value / 1000.0) * self._stamina_recovery_rate(source_action_type),
            )
            return
        if effect_type in {'ProduceEffectType_StaminaReduceFix', 'ProduceEffectType_EventSchoolStaminaDown'}:
            self.state['stamina'] = max(self.state['stamina'] - value, 0.0)
            return
        if effect_type in {'ProduceEffectType_ProducePointAddition', 'ProduceEffectType_ProducePointAdditionDisableTrigger'}:
            self.state['produce_points'] += value * self._produce_point_rate(source_action_type)
            return
        if effect_type == 'ProduceEffectType_ProducePointReduceFix':
            self.state['produce_points'] = max(self.state['produce_points'] - value, 0.0)
            return
        if effect_type == 'ProduceEffectType_VoteCountAddition':
            self.state['fan_votes'] += value * self._vote_rate(source_action_type)
            return
        if effect_type == 'ProduceEffectType_EventActivityProducePointUp':
            self.state['activity_produce_point_bonus'] += value / 1000.0
            return
        if effect_type == 'ProduceEffectType_EventBusinessVoteCountUp':
            self.state['business_vote_bonus'] += value / 1000.0
            return
        if effect_type == 'ProduceEffectType_LessonPresentProducePointUp':
            self.state['lesson_present_point_bonus'] += value / 1000.0
            return
        if effect_type == 'ProduceEffectType_SupportCardEventProducePointAdditionValueUp':
            self.state['support_event_point_bonus'] += value / 1000.0
            return
        if effect_type == 'ProduceEffectType_SupportCardEventParameterAdditionValueUp':
            self.state['support_event_stat_bonus'] += value / 1000.0
            return
        if effect_type == 'ProduceEffectType_SupportCardEventStaminaRecoverUp':
            self.state['support_event_stamina_bonus'] += value / 1000.0
            return
        if effect_type == 'ProduceEffectType_AuditionVoteCountUp':
            self.state['audition_vote_bonus'] += value / 1000.0
            return
        if effect_type == 'ProduceEffectType_AuditionParameterBonusMultiple':
            self.state['audition_parameter_bonus'] += value / 1000.0
            return
        if effect_type == 'ProduceEffectType_AuditionNpcEnhance':
            self.state['audition_difficulty_bonus'] += value / 1000.0
            return
        if effect_type == '128':
            # 有一条主数据直接把原始枚举值序列化进来，需要按 id 识别为 NPC 弱化。
            self.state['audition_difficulty_bonus'] -= value / 1000.0
            return
        if effect_type == 'ProduceEffectType_ExamTurnDown':
            self.state['audition_turn_modifier'] -= value
            return
        if effect_type == 'ProduceEffectType_BeforeAuditionRefreshStaminaDown':
            self.state['before_audition_refresh_penalty'] += value / 1000.0
            return
        if effect_type == 'ProduceEffectType_BeforeAuditionRefreshStaminaUp':
            self.state['before_audition_refresh_penalty'] -= value / 1000.0
            return
        if effect_type == 'ProduceEffectType_LessonSpChangeRatePermilAddition':
            self.state['generic_sp_rate_bonus'] += value / 1000.0
            return
        if effect_type == 'ProduceEffectType_LessonVocalSpChangeRatePermilAddition':
            self.state['vocal_sp_rate_bonus'] += value / 1000.0
            return
        if effect_type == 'ProduceEffectType_LessonDanceSpChangeRatePermilAddition':
            self.state['dance_sp_rate_bonus'] += value / 1000.0
            return
        if effect_type == 'ProduceEffectType_LessonVisualSpChangeRatePermilAddition':
            self.state['visual_sp_rate_bonus'] += value / 1000.0
            return
        if effect_type == 'ProduceEffectType_LessonPresentProduceCardRewardCountUp':
            self.state['reward_card_count_bonus'] += value / 1000.0
            return
        if effect_type == 'ProduceEffectType_IdolCardProduceCardCustomizeEnable':
            self.state['customize_slots'] += max(value / 1000.0, 1.0)
            return
        if effect_type == 'ProduceEffectType_ProduceCardExcludeCountUp':
            self.state['exclude_count_bonus'] += max(value / 1000.0, 1.0)
            return
        if effect_type in {'ProduceEffectType_ProduceCardSelectRerollCountUp', 'ProduceEffectType_ShopRerollCountUp'}:
            self.state['reroll_count_bonus'] += max(value / 1000.0, 1.0)
            return
        if effect_type in {
            'ProduceEffectType_ShopPriceDiscountMultiple',
            'ProduceEffectType_ShopPriceUpMultiple',
            'ProduceEffectType_ShopProduceCardDeletePriceDiscountMultiple',
            'ProduceEffectType_ShopProduceCardPriceDiscountMultiple',
            'ProduceEffectType_ShopProduceCardUpgradePriceDiscountMultiple',
            'ProduceEffectType_ShopProduceDrinkPriceDiscountMultiple',
        }:
            direction = -1.0 if 'Discount' in effect_type else 1.0
            self.state['shop_discount'] += direction * (value / 1000.0)
            return
        if effect_type == 'ProduceEffectType_SupportCardProduceCardUpgradeProbabilityUp':
            self.state['card_upgrade_probability_bonus'] += value / 1000.0
            return
        if effect_type == 'ProduceEffectType_HighScoreGoldAddition':
            self.state['gold_bonus'] += value
            return
        if effect_type == 'ProduceEffectType_ProduceCardUpgrade':
            self._upgrade_matching_cards(
                str(effect.get('produceCardSearchId') or ''),
                int(max(effect.get('pickCountMin') or 1, 1)),
            )
            return
        if effect_type == 'ProduceEffectType_ProduceCardDelete':
            self._delete_matching_cards(
                str(effect.get('produceCardSearchId') or ''),
                int(max(effect.get('pickCountMin') or 1, 1)),
            )
            return
        if effect_type == 'ProduceEffectType_ProduceCardDuplicate':
            self._duplicate_matching_cards(
                str(effect.get('produceCardSearchId') or ''),
                int(max(effect.get('pickCountMin') or 1, 1)),
            )
            return
        if effect_type in {'ProduceEffectType_ProduceCardChange', 'ProduceEffectType_ProduceCardChangeUpgrade'}:
            self._replace_matching_cards(
                str(effect.get('produceCardSearchId') or ''),
                upgraded=effect_type.endswith('Upgrade'),
            )
            return
        if effect_type in {'ProduceEffectType_ProduceReward', 'ProduceEffectType_ProduceRewardSet'}:
            self._grant_rewards(effect, source_action_type=source_action_type)
            return
        if effect_type in {'ProduceEffectType_ExamStatusEnchant', 'ProduceEffectType_ExamPermanentLessonStatusEnchant', 'ProduceEffectType_ExamPermanentAuditionStatusEnchant'}:
            enchant_id = str(effect.get('produceExamStatusEnchantId') or '')
            if enchant_id:
                self._append_exam_status_enchant(
                    enchant_id,
                    source='produce_item' if source == 'produce_item' else 'produce',
                    source_identity=source_identity,
                )
            return
    def _produce_point_rate(self, source_action_type: str) -> float:
        """计算当前动作来源对应的制作点倍率。"""

        rate = 1.0
        if source_action_type == 'activity':
            rate += self.state['activity_produce_point_bonus']
        if source_action_type in EVENT_ACTION_TYPES:
            rate += self.state['support_event_point_bonus']
        if source_action_type == 'present' or _is_lesson_action(source_action_type):
            rate += self.state['lesson_present_point_bonus']
        return max(rate, 0.0)

    def _vote_rate(self, source_action_type: str) -> float:
        """计算营业类动作的粉丝票数倍率。"""

        rate = 1.0
        if source_action_type == 'business':
            rate += self.state['business_vote_bonus']
        return max(rate, 0.0)

    def _stamina_recovery_rate(self, source_action_type: str) -> float:
        """计算体力回复类效果的倍率。"""

        rate = 1.0
        if source_action_type in EVENT_ACTION_TYPES:
            rate += self.state['support_event_stamina_bonus']
        return max(rate, 0.0)

    def _sp_rate_bonus(self, action_type: str) -> float:
        """返回对应 SP 课程的额外成功率加成。"""

        bonus = self.state['generic_sp_rate_bonus']
        if action_type in {'lesson_vocal_sp', 'self_lesson_vocal_sp'}:
            bonus += self.state['vocal_sp_rate_bonus']
        elif action_type in {'lesson_dance_sp', 'self_lesson_dance_sp'}:
            bonus += self.state['dance_sp_rate_bonus']
        elif action_type in {'lesson_visual_sp', 'self_lesson_visual_sp'}:
            bonus += self.state['visual_sp_rate_bonus']
        return bonus

    def _grant_rewards(self, effect: dict[str, Any], source_action_type: str) -> None:
        """处理课程或事件奖励掉落的卡牌和饮料。"""

        rewards = effect.get('produceRewards', []) or []
        if rewards:
            for reward in rewards:
                self._grant_resource(str(reward.get('resourceType') or ''), str(reward.get('resourceId') or ''), int(reward.get('resourceLevel') or 0))
            self._trim_drinks()
            return
        resource_type = str(effect.get('produceResourceType') or '')
        count = int(max(effect.get('pickCountMax') or effect.get('pickCountMin') or 1, 1))
        if resource_type == 'ProduceResourceType_ProduceCard' and (source_action_type == 'present' or _is_lesson_action(source_action_type)):
            count += int(round(self.state['reward_card_count_bonus']))
        for _ in range(max(count, 0)):
            if resource_type == 'ProduceResourceType_ProduceDrink':
                candidates = self.repository.build_drink_inventory(
                    self.scenario,
                    max_items=self.scenario.drink_limit,
                    rng=self.np_random,
                    plan_type=self.idol_loadout.stat_profile.plan_type if self.idol_loadout is not None else None,
                )
                if candidates:
                    drink_row = dict(candidates[int(self.np_random.integers(0, len(candidates)))])
                    self.drinks.append(drink_row)
                    self._dispatch_produce_item_phase('ProducePhaseType_GetProduceDrink')
            elif resource_type == 'ProduceResourceType_ProduceCard':
                candidates = build_weighted_card_pool(self.repository, self.scenario, loadout=self.idol_loadout)
                if candidates:
                    sampled = sample_card_from_weighted_pool(candidates, self.np_random)
                    if sampled is None:
                        continue
                    randomized = self.repository.sample_random_card_variant(str(sampled.get('id') or ''), self.np_random)
                    card_row = dict(randomized or sampled)
                    if self.np_random.random() < self.state['card_upgrade_probability_bonus']:
                        upgraded_row = self._lookup_card_row(str(card_row.get('id')), int(card_row.get('upgradeCount') or 0) + 1)
                        if upgraded_row is not None:
                            card_row = dict(upgraded_row)
                    self.deck.append(card_row)
                    self._dispatch_produce_item_phase('ProducePhaseType_GetProduceCard', card=card_row)
        self._trim_drinks()

    def _grant_resource(self, resource_type: str, resource_id: str, resource_level: int) -> None:
        """把单个资源奖励写回卡组、饮料或支援技能列表。"""

        if resource_type == 'ProduceResourceType_ProduceCard':
            card_row = resolve_produce_card_row(
                self.repository,
                resource_id,
                loadout=self.idol_loadout,
                upgrade_count=resource_level,
            )
            if card_row is not None:
                resolved_card = dict(card_row)
                self.deck.append(resolved_card)
                self._dispatch_produce_item_phase('ProducePhaseType_GetProduceCard', card=resolved_card)
        elif resource_type == 'ProduceResourceType_ProduceDrink':
            drink_row = self.repository.produce_drinks.first(resource_id)
            if drink_row is not None:
                self.drinks.append(dict(drink_row))
                self._dispatch_produce_item_phase('ProducePhaseType_GetProduceDrink')
        elif resource_type == 'ProduceResourceType_ProduceItem':
            self._register_produce_item(resource_id, source='reward')
            self._dispatch_produce_item_phase('ProducePhaseType_GetProduceItem')
        elif resource_type == 'ProduceResourceType_ProduceSkill':
            self.support_skills.append(resource_id)

    def _matching_deck_indices(self, search_id: str) -> list[int]:
        """查找当前牌组里符合搜索条件的卡牌下标。"""

        search = self.card_searches.first(search_id)
        if not search:
            return list(range(len(self.deck)))
        indices: list[int] = []
        for index, card in enumerate(self.deck):
            if self._deck_card_matches(card, search):
                indices.append(index)
        return indices

    def _deck_card_matches(self, card: dict[str, Any], search: dict[str, Any]) -> bool:
        """判断牌组中的卡是否命中 ProduceCardSearch 条件。"""

        return self.produce_item_interpreter.card_matches_search(card, str(search.get('id') or ''))

    def _upgrade_matching_cards(self, search_id: str, count: int) -> None:
        """升级若干张符合条件的卡。"""

        indices = self._matching_deck_indices(search_id)
        self.np_random.shuffle(indices)
        for index in indices[:count]:
            card = self.deck[index]
            upgraded = self._lookup_card_row(str(card.get('id')), int(card.get('upgradeCount') or 0) + 1)
            if upgraded is not None:
                upgraded_row = dict(upgraded)
                self.deck[index] = upgraded_row
                self._dispatch_produce_item_phase('ProducePhaseType_UpgradeProduceCard', card=upgraded_row)

    def _delete_matching_cards(self, search_id: str, count: int) -> None:
        """删除若干张符合条件的卡。"""

        indices = self._matching_deck_indices(search_id)
        self.np_random.shuffle(indices)
        for index in sorted(indices[:count], reverse=True):
            deleted_card = dict(self.deck[index])
            self.deck.pop(index)
            self._dispatch_produce_item_phase('ProducePhaseType_DeleteProduceCard', card=deleted_card)

    def _duplicate_matching_cards(self, search_id: str, count: int) -> None:
        """复制若干张符合条件的卡。"""

        indices = self._matching_deck_indices(search_id)
        self.np_random.shuffle(indices)
        for index in indices[:count]:
            duplicated = dict(self.deck[index])
            self.deck.append(duplicated)
            self._dispatch_produce_item_phase('ProducePhaseType_GetProduceCard', card=duplicated)

    def _replace_matching_cards(self, search_id: str, upgraded: bool) -> None:
        """把命中的卡替换为当前流派候选池中的新卡。"""

        indices = self._matching_deck_indices(search_id)
        if not indices:
            return
        index = int(self.np_random.choice(indices))
        candidates = build_weighted_card_pool(self.repository, self.scenario, loadout=self.idol_loadout)
        if not candidates:
            return
        sampled = sample_card_from_weighted_pool(candidates, self.np_random)
        if sampled is None:
            return
        randomized = self.repository.sample_random_card_variant(str(sampled.get('id') or ''), self.np_random)
        replacement = dict(randomized or sampled)
        if upgraded:
            upgraded_row = self._lookup_card_row(str(replacement.get('id')), int(replacement.get('upgradeCount') or 0) + 1)
            if upgraded_row is not None:
                replacement = dict(upgraded_row)
        self.deck[index] = replacement
        self._dispatch_produce_item_phase('ProducePhaseType_ChangeProduceCard', card=replacement)

    def _lookup_card_row(self, card_id: str, upgrade_count: int) -> dict[str, Any] | None:
        """按卡 id 和强化次数查找主数据行。"""

        return self.repository.card_row_by_upgrade(card_id, upgrade_count, fallback_to_canonical=True)

    def _sample_effect_value(self, effect: dict[str, Any]) -> float:
        """从主数据字段中采样一条效果数值。"""

        minimum = float(effect.get('effectValueMin') or 0)
        maximum = float(effect.get('effectValueMax') or minimum)
        if maximum < minimum:
            minimum, maximum = maximum, minimum
        if minimum == maximum:
            return minimum
        return float(self.np_random.uniform(minimum, maximum))

    def _action_label(self, action_type: str) -> str:
        """把内部动作类型转换成展示文案。"""

        labels = {
            'lesson_vocal_normal': '声乐课',
            'lesson_dance_normal': '舞蹈课',
            'lesson_visual_normal': '形象课',
            'lesson_vocal_sp': 'SP声乐课',
            'lesson_dance_sp': 'SP舞蹈课',
            'lesson_visual_sp': 'SP形象课',
            'lesson_vocal_hard': '追击声乐课',
            'lesson_dance_hard': '追击舞蹈课',
            'lesson_visual_hard': '追击形象课',
            'self_lesson_vocal_normal': '自主声乐课',
            'self_lesson_vocal_sp': '自主SP声乐课',
            'self_lesson_dance_normal': '自主舞蹈课',
            'self_lesson_dance_sp': '自主SP舞蹈课',
            'self_lesson_visual_normal': '自主形象课',
            'self_lesson_visual_sp': '自主SP形象课',
            'activity': '活动',
            'business': '营业',
            'present': '差入/事件',
            'refresh': '休息',
        }
        return labels.get(action_type, action_type)

    def _trim_drinks(self) -> None:
        """按场景上限裁剪饮料栏。"""

        if len(self.drinks) <= self.scenario.drink_limit:
            return
        self.drinks.sort(
            key=lambda row: (len(self.repository.drink_exam_effect_types(row)), str(row.get('rarity') or '')),
            reverse=True,
        )
        self.drinks = self.drinks[: self.scenario.drink_limit]

    def _refresh_quality_scores(self) -> None:
        """重新估算当前卡组和饮料质量，用于奖励与观测。"""

        card_scores = [self.repository.card_play_priors.get(str(card.get('id')), 0.0) for card in self.deck]
        drink_scores = [len(self.repository.drink_exam_effect_types(drink)) for drink in self.drinks]
        enchant_bonus = 0.2 * len(self.exam_status_enchant_ids)
        self.state['deck_quality'] = (float(np.mean(card_scores)) / 100.0 if card_scores else 0.0) + enchant_bonus
        self.state['drink_quality'] = float(np.mean(drink_scores)) if drink_scores else 0.0

    def _audition_start_stamina(self) -> float:
        """按主数据的试验前回复量规则，计算考试开场体力。"""

        max_stamina = max(float(self.state.get('max_stamina') or 0.0), 1.0)
        current_stamina = float(np.clip(self.state.get('stamina') or 0.0, 0.0, max_stamina))
        recovery_permille = float(self.produce_setting.get('beforeAuditionRefreshStaminaRecoveryPermil') or 0.0)
        recovery_multiple = max(0.0, 1.0 - float(self.state.get('before_audition_refresh_penalty') or 0.0))
        recovered = current_stamina + max_stamina * (recovery_permille / 1000.0) * recovery_multiple
        return float(min(recovered, max_stamina))

    def _choose_exam_action(self, runtime: ExamRuntime):
        """用启发式从考试运行时里挑选一个动作。"""

        actions = runtime.legal_actions()
        if not actions:
            return None
        remaining_turns = max(runtime.max_turns - runtime.turn + 1, 1)
        best_action = actions[-1]
        best_score = float('-inf')
        playable_card_count = sum(1 for action in actions if action.kind == 'card')

        for action in actions:
            # 这个兜底控制器只使用效果类型和资源成本等结构先验，不依赖卡名。
            score = 0.0
            if action.kind == 'card':
                card = next((item for item in runtime.hand if item.uid == int(action.payload['uid'])), None)
                if card is None:
                    continue
                effect_types = self.repository.card_exam_effect_types(card.base_card)
                for effect_id in card.transient_effect_ids:
                    effect_row = self.repository.exam_effect_map.get(str(effect_id))
                    if effect_row and effect_row.get('effectType'):
                        effect_types.append(str(effect_row['effectType']))
                prior = self.repository.card_play_priors.get(str(card.card_id), 0.0) / 100.0
                effect_prior = sum(self.repository.exam_effect_priors.get((effect_type, remaining_turns), 0.0) for effect_type in effect_types) / max(len(effect_types), 1)
                score += prior + effect_prior / 100.0
                score -= float(card.base_card.get('stamina') or 0) * 0.03
                score -= float(card.base_card.get('forceStamina') or 0) * 0.05
                score += card.play_count_bonus * 0.1
            elif action.kind == 'drink':
                drink = runtime.drinks[int(action.payload['index'])]
                effect_types = self.repository.drink_exam_effect_types(drink)
                effect_prior = sum(self.repository.exam_effect_priors.get((effect_type, remaining_turns), 0.0) for effect_type in effect_types) / max(len(effect_types), 1)
                score += effect_prior / 100.0
                if runtime.stamina < runtime.max_stamina * 0.45:
                    score += 0.15
            elif action.kind == 'end_turn':
                score -= 0.1
                if playable_card_count == 0:
                    score += 0.25
            if score > best_score:
                best_score = score
                best_action = action
        return best_action

    def _run_audition(self, stage_type: str) -> tuple[float, dict[str, Any]]:
        """把当前培育构筑带入考试运行时，返回考试奖励与摘要。"""

        for phase_type in self._pre_audition_item_phases():
            self._dispatch_produce_item_phase(phase_type, stage_type=stage_type)
        self._dispatch_produce_item_phase('ProducePhaseType_EndBeforeAuditionRefresh')
        for phase_type in self._stage_trigger_phases(stage_type):
            self._dispatch_produce_item_phase(phase_type)
        exam_loadout = self.idol_loadout
        if exam_loadout is not None:
            exam_loadout = replace(
                exam_loadout,
                produce_item_id='',
                exam_status_enchant_ids=(),
                exam_status_enchant_specs=(),
            )
        runtime = ExamRuntime(
            self.repository,
            self.scenario,
            stage_type=stage_type,
            seed=int(self.np_random.integers(0, 2**31 - 1)),
            deck=list(self.deck),
            drinks=list(self.drinks),
            initial_status_enchant_ids=list(self.exam_status_enchant_ids),
            initial_status_enchants=list(self.exam_status_enchant_specs),
            loadout=exam_loadout,
            starting_stamina=self._audition_start_stamina(),
            exam_score_bonus_multiplier=(self.idol_loadout.exam_score_bonus_multiplier if self.idol_loadout else 1.0) * (1.0 + self.state['audition_parameter_bonus']),
            fan_votes=float(self.state.get('fan_votes') or 0.0),
            audition_row_id=default_audition_row_selector(
                self.repository,
                self.scenario,
                stage_type=stage_type,
                loadout=exam_loadout,
                fan_votes=float(self.state.get('fan_votes') or 0.0),
            ),
        )
        runtime.reset()
        runtime.max_turns = max(1, runtime.max_turns + int(round(self.state['audition_turn_modifier'])))
        for _ in range(256):
            action = self._choose_exam_action(runtime)
            if action is None:
                break
            runtime.step(action)
            if runtime.terminated:
                break
        self._dispatch_produce_item_phase('ProducePhaseType_EndAudition')
        effective_score = runtime.score + self.state['deck_quality'] * 120.0 + self.state['drink_quality'] * 80.0
        profile = dict(runtime.profile)
        target_score = float(profile.get('base_score') or 0.0) * max(0.25, 1.0 + self.state['audition_difficulty_bonus'])
        cleared = effective_score >= target_score
        margin = (effective_score - target_score) / max(target_score, 1.0)
        reward = (0.8 + min(margin, 0.5)) if cleared else (-0.8 + max(margin, -0.5))
        if cleared:
            vote_gain = runtime.estimate_fan_vote_gain(effective_score) * (1.0 + self.state['audition_vote_bonus'])
            self.state['fan_votes'] += max(vote_gain, 0.0)
            self.state['deck_quality'] += 0.4
            self.state['drink_quality'] += 0.2
        self.state['last_exam_score'] = effective_score
        return reward, {
            'stage_type': stage_type,
            'audition_row_id': str((runtime.selected_battle_row or {}).get('id') or ''),
            'audition_row_number': int((runtime.selected_battle_row or {}).get('number') or 0),
            'exam_score': runtime.score,
            'parameter_bonus': 0.0,
            'parameter_bonus_multiplier': runtime.score_bonus_multiplier,
            'effective_score': effective_score,
            'target_score': target_score,
            'cleared': cleared,
            'fan_votes': self.state['fan_votes'],
            'fan_vote_gain': max(vote_gain, 0.0) if cleared else 0.0,
            'fan_vote_requirement': float(profile.get('fan_vote_requirement') or 0.0),
            'fan_vote_baseline': float(profile.get('fan_vote_baseline') or 0.0),
            'turns': runtime.turn,
        }




