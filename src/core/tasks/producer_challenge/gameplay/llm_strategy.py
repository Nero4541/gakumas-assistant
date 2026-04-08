"""LLM 决策策略 — 通过 OpenAI 兼容 API 为各阶段提供智能决策。

使用方式：
    strategy = LLMStrategy(
        base_url="http://192.168.100.10:11434/v1/",
        model="gpt-oss:20b",
    )
    ctx.schedule_strategy = strategy
    ctx.lesson_strategy = strategy
    ctx.dialogue_strategy = strategy
    # ... 注入到所有策略字段

策略回调签名：strategy(app, ctx, candidates, decision_state) → int | dict | None
"""

from __future__ import annotations

import json
import re
import time
from typing import TYPE_CHECKING, Any, Sequence

from openai import OpenAI

from src.utils.logger import logger

if TYPE_CHECKING:
    from src.core.tasks.producer_challenge.context import ProduceContext
    from src.main import AppProcessor

# ── 系统提示词 ──────────────────────────────────────────

_SYSTEM_PROMPT = """\
你是「学園アイドルマスター」的培育决策助手。
根据当前游戏局面信息，从合法候选动作中选择最优动作。

## 决策目标
- 培育阶段（schedule）：合理安排每周行程，平衡属性提升、体力管理和事件触发
- 出牌阶段（lesson/exam）：选择最优手牌，考虑当前资源、目标分数和回合数
- 对话阶段（dialogue）：选择能提升亲密度或获得最佳效果的选项
- 技能卡奖励（skill_reward）：选择与当前编成和策略最匹配的卡片
- P饮料选择（p_drink）：选择当前最需要的饮料
- 相谈（consult）：根据当前需求选择强化、交换或跳过

## 规则
- 只输出一个动作编号（纯数字），不要输出任何解释
- 合法动作编号在候选列表中给出
- 如果局面信息不足以做出判断，选择第一个候选动作（编号 0）
"""

# ── 各阶段提示词模板 ──────────────────────────────────

_PHASE_PROMPTS = {
    "schedule": "## 周行程选择\n选择本周要执行的行动。",
    "lesson": "## レッスン出牌\n选择要打出的手牌。考虑卡牌效果、当前资源和剩余回合数。",
    "exam": "## 試験/オーディション出牌\n选择要打出的手牌。这是考试阶段，需要尽可能提高分数。",
    "dialogue": "## 对话选项\n选择对话回复。不同选项可能影响属性提升和亲密度。",
    "skill_reward": "## 技能卡奖励\n选择要获得的技能卡。考虑与当前编成的匹配度。",
    "p_drink": "## P饮料选择\n选择要使用的P饮料。",
    "consult": "## 相谈决策\n选择相谈中要执行的操作。",
}


class LLMStrategy:
    """通过 OpenAI 兼容 API 做游戏决策的统一策略。

    所有阶段（schedule/lesson/exam/dialogue/skill_reward/p_drink/consult）
    共用同一个实例，根据 decision_state["phase"] 自动切换提示词。
    """

    def __init__(
        self,
        base_url: str = "http://192.168.100.10:11434/v1/",
        model: str = "gpt-oss:20b",
        api_key: str = "ollama",
        timeout: float = 180.0,
        temperature: float = 0.3,
        max_tokens: int = 256,
        think: str = "low",
    ):
        self.base_url = base_url.rstrip("/")
        # 确保 base_url 以 /v1 结尾
        if not self.base_url.endswith("/v1"):
            self.base_url += "/v1" if not self.base_url.endswith("/") else "v1"
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.think = think
        self._client: OpenAI | None = None
        self._call_count = 0
        self._total_latency = 0.0

    def _get_client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                timeout=self.timeout,
            )
        return self._client

    # ── 策略回调入口（供 invoke_decision_strategy 调用）──

    def __call__(
        self,
        app: "AppProcessor",
        ctx: "ProduceContext",
        candidates: Sequence[Any],
        decision_state: dict[str, Any] | None = None,
    ) -> int | None:
        """策略回调入口。返回候选动作索引或 None（交给后续 fallback）。"""
        if not candidates or decision_state is None:
            return None

        phase = decision_state.get("phase", "unknown")
        prompt = self._build_prompt(decision_state)
        if not prompt:
            return None

        try:
            t0 = time.monotonic()
            action_index = self._call_and_parse(prompt, decision_state)
            elapsed = time.monotonic() - t0
            self._call_count += 1
            self._total_latency += elapsed

            if action_index is not None:
                # 验证索引合法性
                legal = decision_state.get("legal_actions", [])
                if legal and action_index not in legal:
                    logger.warning(
                        f"[LLM] 返回索引 {action_index} 不在合法动作 {legal} 中，忽略"
                    )
                    return None
                candidate_name = self._get_candidate_name(
                    decision_state, action_index
                )
                logger.info(
                    f"[LLM] {phase} 决策: 选择 #{action_index}"
                    f" ({candidate_name}) [{elapsed:.1f}s]"
                )
                return action_index

            logger.debug(f"[LLM] {phase} 决策: 无法解析结果，交给 fallback")
            return None

        except Exception as exc:
            logger.warning(f"[LLM] {phase} 决策出错: {exc}")
            return None

    # ── Prompt 构建 ──────────────────────────────────────

    def _build_prompt(self, state: dict[str, Any]) -> str:
        """根据 decision_state 构建用户提示词。"""
        phase = state.get("phase", "unknown")
        parts: list[str] = []

        # 阶段标题
        phase_header = _PHASE_PROMPTS.get(phase, f"## {phase} 决策")
        parts.append(phase_header)
        parts.append("")

        # 游戏状态摘要
        parts.append(self._format_game_state(state))
        parts.append("")

        # 候选动作列表
        parts.append(self._format_candidates(state))
        parts.append("")

        # 指令
        parts.append("请选择最优动作，只输出动作编号（一个数字）：")

        return "\n".join(parts)

    @staticmethod
    def _format_game_state(state: dict[str, Any]) -> str:
        """格式化游戏状态摘要。"""
        lines: list[str] = []
        lines.append("### 当前状态")

        phase = state.get("phase", "")
        position = state.get("position", "")
        week = state.get("week", 0)
        scenario = state.get("scenario", "")
        difficulty = state.get("difficulty", "")
        lines.append(f"阶段: {phase} | 位置: {position}")
        lines.append(f"剧本: {scenario} | 难度: {difficulty} | 第{week}周")

        # 经济状态
        economy = state.get("economy", {})
        if economy:
            stamina = economy.get("stamina", 0)
            max_stamina = economy.get("max_stamina", 0)
            p_point = economy.get("p_point", 0)
            lines.append(f"体力: {stamina}/{max_stamina} | Pポイント: {p_point}")

        # 参数状态
        params = state.get("parameters", {})
        target = params.get("target_score", 0)
        if target:
            lines.append(f"目標スコア: {target}")

        # 手牌信息（lesson/exam 阶段）
        card_zones = state.get("card_zones", {})
        hand = card_zones.get("hand", [])
        if hand:
            lines.append(f"\n### 手牌 ({len(hand)}张)")
            for card in hand:
                name = card.get("name", card.get("label", "?"))
                db_id = card.get("db_id", "")
                card_type = card.get("type", "")
                lines.append(f"- {name} (DB: {db_id}, 类型: {card_type})")

        # 道具信息
        inventory = state.get("inventory", {})
        drinks = inventory.get("p_drinks", [])
        if drinks:
            lines.append(f"\n### P饮料 ({len(drinks)}个)")
            for d in drinks:
                lines.append(f"- {d.get('name', '?')} (DB: {d.get('db_id', '')})")

        return "\n".join(lines)

    @staticmethod
    def _format_candidates(state: dict[str, Any]) -> str:
        """格式化候选动作列表。"""
        candidates = state.get("candidates", [])
        if not candidates:
            return "### 候选动作\n（无候选）"

        lines = [f"### 候选动作 ({len(candidates)}个)"]
        for c in candidates:
            idx = c.get("index", 0)
            name = c.get("name", c.get("label", "?"))
            db_id = c.get("db_id", "")
            recommended = c.get("recommended", False)
            available = c.get("available", True)

            parts = [f"{idx}: {name}"]
            if db_id:
                parts.append(f"(DB:{db_id})")
            if recommended:
                parts.append("[推荐]")
            if not available:
                parts.append("[不可用]")

            # 附加元数据
            metadata = c.get("metadata", {})
            kind = metadata.get("kind") or c.get("type", "")
            if kind:
                parts.append(f"[{kind}]")

            lines.append(" ".join(parts))

        return "\n".join(lines)

    @staticmethod
    def _get_candidate_name(state: dict[str, Any], index: int) -> str:
        """获取指定索引的候选名称。"""
        for c in state.get("candidates", []):
            if c.get("index") == index:
                return c.get("name", c.get("label", f"#{index}"))
        return f"#{index}"

    # ── LLM 调用 ────────────────────────────────────────

    def _call_and_parse(
        self,
        prompt: str,
        state: dict[str, Any],
    ) -> int | None:
        """调用 LLM 并解析返回的动作编号。"""
        client = self._get_client()
        legal = state.get("legal_actions", [])

        # 构建请求参数
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        # Ollama think 参数
        if self.think and self.think != "false":
            think_value = self.think if self.think in ("low", "medium", "high") else True
            kwargs["extra_body"] = {"think": think_value}

        try:
            response = client.chat.completions.create(**kwargs)
        except Exception as exc:
            # 若 think 参数不支持，回退不带 think 的请求
            if "think" in str(exc).lower() or "unsupported" in str(exc).lower():
                logger.debug("[LLM] think 参数不支持，回退重试")
                kwargs.pop("extra_body", None)
                response = client.chat.completions.create(**kwargs)
            else:
                raise

        # 提取最终文本
        final_text = self._extract_final_text(response)
        if not final_text:
            logger.debug("[LLM] 返回空文本")
            return None

        # 去除推理标签
        cleaned = re.sub(
            r"<think>.*?</think>", "", final_text, flags=re.IGNORECASE | re.DOTALL
        )
        cleaned = cleaned.strip()
        logger.debug(f"[LLM] 原始回复: {final_text[:200]}")
        logger.debug(f"[LLM] 清理后: {cleaned[:100]}")

        # 解析动作编号
        return self._parse_action_index(cleaned, legal)

    @staticmethod
    def _extract_final_text(response: Any) -> str:
        """从 OpenAI 响应中提取最终文本（兼容 thinking/reasoning 模式）。"""
        if not response or not response.choices:
            return ""
        choice = response.choices[0]
        message = choice.message

        # 标准 content
        content = getattr(message, "content", None) or ""
        if isinstance(content, str) and content.strip():
            return content.strip()

        # 某些模型把结果放在 content 列表中
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text") or item.get("content") or ""
                    if text:
                        parts.append(str(text))
            if parts:
                return "".join(parts).strip()

        # gpt-oss 等模型可能把结果放在 reasoning 字段中
        reasoning = getattr(message, "reasoning", None) or ""
        if isinstance(reasoning, str) and reasoning.strip():
            return reasoning.strip()

        return ""

    @staticmethod
    def _parse_action_index(text: str, legal_actions: list[int]) -> int | None:
        """从文本中解析动作编号。"""
        if not text:
            return None

        # 尝试第一行精确匹配
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if lines:
            exact = re.fullmatch(r"\D*(\d+)\D*", lines[0])
            if exact:
                idx = int(exact.group(1))
                if not legal_actions or idx in legal_actions:
                    return idx

        # 回退：找到文本中所有数字，从后往前匹配
        numbers = re.findall(r"\d+", text)
        for num_str in reversed(numbers):
            idx = int(num_str)
            if not legal_actions or idx in legal_actions:
                return idx

        return None

    # ── 工具方法 ────────────────────────────────────────

    @property
    def stats(self) -> str:
        """返回统计摘要。"""
        avg = (self._total_latency / self._call_count) if self._call_count else 0
        return f"calls={self._call_count}, avg_latency={avg:.1f}s"


def create_llm_strategy(
    base_url: str = "http://192.168.100.10:11434/v1/",
    model: str = "gpt-oss:20b",
    **kwargs: Any,
) -> LLMStrategy:
    """创建 LLM 策略实例的便捷工厂函数。"""
    return LLMStrategy(base_url=base_url, model=model, **kwargs)


def inject_llm_strategy(
    ctx: "ProduceContext",
    strategy: LLMStrategy | None = None,
    *,
    base_url: str = "http://192.168.100.10:11434/v1/",
    model: str = "gpt-oss:20b",
    **kwargs: Any,
) -> LLMStrategy:
    """创建 LLM 策略并注入到 ProduceContext 的所有决策字段。

    Returns:
        注入的 LLMStrategy 实例。
    """
    if strategy is None:
        strategy = create_llm_strategy(base_url=base_url, model=model, **kwargs)

    ctx.schedule_strategy = strategy
    ctx.lesson_strategy = strategy
    ctx.exam_strategy = strategy
    ctx.dialogue_strategy = strategy
    ctx.skill_reward_strategy = strategy
    ctx.p_drink_strategy = strategy
    ctx.consult_strategy = strategy
    ctx.modal_strategy = strategy

    logger.info(
        f"[LLM] 策略已注入所有决策字段 | model={strategy.model} "
        f"base_url={strategy.base_url}"
    )
    return strategy
