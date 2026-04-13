"""LLM 决策策略 — 通过 OpenAI 兼容 API 为各阶段提供智能决策。
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

# ── Jinja2 模板：按阶段选择系统提示词 ────────────────
from src.core.tasks.producer_challenge.gameplay.llm.prompt_renderer import render as _render_template

# 阶段 → 系统提示词模板映射
_SYSTEM_TEMPLATE_MAP: dict[str, str] = {
    "lesson": "system_lesson.j2",
    "exam": "system_exam.j2",
    "schedule": "system_schedule.j2",
    "dialogue": "system_dialogue.j2",
    "skill_reward": "system_skill_reward.j2",
    "p_drink": "system_p_drink.j2",
    "consult": "system_consult.j2",
    "item_select": "system_item_select.j2",
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
        timeout: float = 60.0,
        temperature: float = 0.3,
        max_tokens: int | None = None,
        think: str = "low",
        num_ctx: int = 8192,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.temperature = temperature
        # max_tokens 为 None 时不传给 API，让模型自行控制（避免 thinking 占满 token 预算导致 content 为空）
        self.max_tokens = max_tokens
        self.think = think
        self.num_ctx = num_ctx
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

    def _build_system_prompt(self, phase: str, snapshot: dict[str, Any] | None = None) -> str:
        """根据阶段选择对应的系统提示词模板。
        部分系统模板（如 schedule）需要传入 snapshot 中的上下文数据。
        """
        template_name = _SYSTEM_TEMPLATE_MAP.get(phase, "system_default.j2")
        kwargs = dict(snapshot) if snapshot else {}
        try:
            return _render_template(template_name, **kwargs)
        except Exception as exc:
            logger.warning("[LLM] 渲染系统模板 {} 失败: {}", template_name, exc)
            return _render_template("system_default.j2")

    def _build_prompt(self, state: dict[str, Any]) -> str:
        """使用 Jinja2 模板渲染用户提示词（游戏状态 + 候选动作）。"""
        snapshot = state.get("llm_snapshot", {})
        llm_actions = state.get("llm_actions") or []

        # 渲染局面快照
        try:
            rendered_snapshot = _render_template("state_snapshot.j2", **snapshot)
        except Exception as exc:
            logger.warning("[LLM] 渲染 state_snapshot.j2 失败: {}", exc)
            rendered_snapshot = f"## 当前局面\n（模板渲染失败: {exc}）"

        # 渲染完整用户提示词（快照 + 动作列表 + 决策指令）
        try:
            return _render_template(
                "action_select.j2",
                snapshot=rendered_snapshot,
                actions=llm_actions,
            )
        except Exception as exc:
            logger.warning("[LLM] 渲染 action_select.j2 失败: {}", exc)
            # 最小回退：拼接快照和简单动作列表
            parts = [rendered_snapshot, "\n## 合法动作"]
            for a in llm_actions:
                idx = a.get("index", 0)
                label = a.get("label", "?")
                desc = a.get("description", "")
                line = f"{idx}: {label}"
                if desc:
                    line += f" - {desc}"
                parts.append(line)
            parts.append("\n请选择当前最优动作，只输出动作编号：")
            return "\n".join(parts)

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
        phase = state.get("phase", "unknown")

        # 根据阶段渲染系统提示词（部分模板需要 snapshot 数据）
        snapshot = state.get("llm_snapshot", {})
        system_prompt = self._build_system_prompt(phase, snapshot)

        # 构建请求参数
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": self.temperature,
        }
        # max_tokens 为 None 时不传，让模型自行管理 thinking / content 的 token 分配
        if self.max_tokens is not None:
            kwargs["max_tokens"] = self.max_tokens

        # Ollama think 参数
        if self.think and self.think != "false":
            think_value = self.think if self.think in ("low", "medium", "high") else True
            kwargs["extra_body"] = {"think": think_value, "options": {"num_ctx": self.num_ctx}}
        elif self.num_ctx:
            kwargs["extra_body"] = {"options": {"num_ctx": self.num_ctx}}

        # 调试：打印系统提示词和用户提示词
        logger.debug("[LLM] ====== SYSTEM PROMPT [{}] ======\n{}", phase, system_prompt)
        logger.debug("[LLM] ====== USER PROMPT ======\n{}", prompt)

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

        # 调试：打印原始 response 关键字段（content vs reasoning 分离验证）
        if response and response.choices:
            _msg_dict = self._coerce_dict(
                response.choices[0].message if hasattr(response.choices[0], "message") else response.choices[0]
            )
            _raw_content = self._coerce_text(_msg_dict.get("content"))
            _raw_reasoning = self._coerce_text(
                _msg_dict.get("reasoning_content") or _msg_dict.get("reasoning")
            )
            logger.info("[LLM] content({} 字符): {}", len(_raw_content), repr(_raw_content[:300]))
            if _raw_reasoning:
                logger.info("[LLM] reasoning({} 字符): {}", len(_raw_reasoning), repr(_raw_reasoning[:300]))

        # 提取最终文本（只取 content，不取 reasoning）
        final_text = self._extract_final_text(response)
        if not final_text:
            logger.debug("[LLM] 返回空文本，交给 fallback")
            return None

        # 去除推理标签（content 里可能还有 <think> 标签）
        cleaned = re.sub(
            r"<think>.*?</think>", "", final_text, flags=re.IGNORECASE | re.DOTALL
        )
        cleaned = cleaned.strip()
        logger.info("[LLM] 清理后最终输出: [{}]", cleaned[:200])

        # 解析动作编号
        return self._parse_action_index(cleaned, legal)

    @staticmethod
    def _coerce_dict(value: Any) -> dict[str, Any]:
        """将 pydantic 对象或 dict 统一转为 dict。"""
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if hasattr(value, "model_dump"):
            dumped = value.model_dump(mode="json")
            return dumped if isinstance(dumped, dict) else {}
        if hasattr(value, "to_dict"):
            dumped = value.to_dict()
            return dumped if isinstance(dumped, dict) else {}
        return getattr(value, "__dict__", {})

    @staticmethod
    def _coerce_text(value: Any) -> str:
        """从各种格式中提取纯文本（content 字段可能是 str / list / dict）。"""
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            parts: list[str] = []
            for item in value:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    item_type = str(item.get("type") or "")
                    if item_type and item_type not in {"text", "output_text"}:
                        continue
                    text = item.get("text") or item.get("content") or ""
                    if text:
                        parts.append(str(text))
            return "".join(parts)
        if isinstance(value, dict):
            return str(value.get("text") or value.get("content") or "")
        return str(value)

    @classmethod
    def _extract_final_text(cls, response: Any) -> str:
        """从 OpenAI 响应中提取最终输出文本。

        关键：思考内容(reasoning/reasoning_content)和最终输出(content)必须分离，
        只返回 content 部分。思考内容里的数字不应被用于决策。
        参考 train/gakumas_rl/gakumas_rl/llm_player.py 的实现。
        """
        if not response or not response.choices:
            return ""
        choice = response.choices[0] if isinstance(response.choices, list) else response.choices
        message_raw = getattr(choice, "message", choice)
        message = cls._coerce_dict(message_raw)

        # 最终输出：只从 content 字段取
        raw_text = cls._coerce_text(message.get("content"))
        if raw_text.strip():
            return raw_text.strip()

        # content 为空时不应回退到 reasoning — 那是思考过程不是最终回答
        # 记录 reasoning 长度以便调试
        reasoning = cls._coerce_text(
            message.get("reasoning_content") or message.get("reasoning")
        )
        if reasoning.strip():
            logger.warning(
                "[LLM] content 为空但有 reasoning ({} 字符) — 模型可能只思考未输出最终回答",
                len(reasoning),
            )
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

        # 回退：找到文本中所有数字，从前往后匹配（优先取第一个合法数字）
        numbers = re.findall(r"\d+", text)
        for num_str in numbers:
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

    logger.debug(
        f"[LLM] 策略已注入所有决策字段 | model={strategy.model} "
        f"base_url={strategy.base_url}"
    )
    return strategy
