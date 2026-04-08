"""推理服务的HTTP API接口。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from .inference_service import (
    ExamState,
    InferenceRequest,
    InferenceResponse,
    InferenceService,
)

router = APIRouter(prefix='/api/inference', tags=['inference'])

# 全局推理服务实例
_inference_service: InferenceService | None = None


class LoadModelRequest(BaseModel):
    """加载模型请求。"""

    backend_type: str = Field(..., description="后端类型: ppo/dqn/alphazero")
    checkpoint_path: str = Field(..., description="模型checkpoint路径")


class PredictRequest(BaseModel):
    """推理请求。"""

    # 基础属性
    vocal: int
    dance: int
    visual: int
    stamina: int
    max_stamina: int

    # 考试状态
    score: int
    target_score: int
    turn: int
    max_turns: int

    # 资源状态
    block: int = 0
    review: int = 0
    aggressive: int = 0
    concentration: int = 0
    full_power_point: int = 0
    parameter_buff: int = 0
    lesson_buff: int = 0

    # 指针状态
    stance: str = "neutral"
    stance_level: int = 0

    # 手牌信息
    hand_cards: list[dict[str, Any]] = Field(default_factory=list)
    deck_count: int = 0
    grave_count: int = 0

    # 饮料信息
    drinks: list[dict[str, Any]] = Field(default_factory=list)

    # P道具效果
    status_enchants: list[str] = Field(default_factory=list)

    # N.I.A专属
    fan_votes: int | None = None

    # 回忆卡（支援卡）
    support_cards: list[str] | None = None

    # 其他状态
    gimmicks: list[dict[str, Any]] | None = None

    # 合法动作列表
    legal_actions: list[dict[str, Any]] = Field(default_factory=list)

    # 推理参数
    deterministic: bool = True


class PredictResponse(BaseModel):
    """推理响应。"""

    action_index: int
    action_label: str
    confidence: float
    value_estimate: float | None = None
    policy_probs: list[float] | None = None


@router.post('/load_model')
def load_model(request: LoadModelRequest) -> dict[str, Any]:
    """加载模型。

    Example:
        ```json
        {
            "backend_type": "ppo",
            "checkpoint_path": "runs/sb3_exam_nia_master_xxx/checkpoints/step_500000.zip"
        }
        ```
    """
    global _inference_service

    try:
        _inference_service = InferenceService(backend_type=request.backend_type)
        _inference_service.load_model(request.checkpoint_path)

        return {
            'status': 'success',
            'message': f'Model loaded successfully',
            'info': _inference_service.get_info(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/predict', response_model=PredictResponse)
def predict(request: PredictRequest) -> PredictResponse:
    """执行推理。

    Example:
        ```json
        {
            "vocal": 450,
            "dance": 420,
            "visual": 380,
            "stamina": 12,
            "max_stamina": 15,
            "score": 500,
            "target_score": 2000,
            "turn": 3,
            "max_turns": 9,
            "block": 5,
            "review": 10,
            "aggressive": 8,
            "hand_cards": [
                {"id": "card_001", "name": "卡牌1", "stamina": 3},
                {"id": "card_002", "name": "卡牌2", "stamina": 2}
            ],
            "drinks": [
                {"id": "drink_001", "name": "饮料1", "consumed": false}
            ],
            "legal_actions": [
                {"index": 0, "label": "卡牌1", "kind": "card", "available": true},
                {"index": 1, "label": "卡牌2", "kind": "card", "available": true},
                {"index": 48, "label": "饮料1", "kind": "drink", "available": true},
                {"index": 51, "label": "结束回合", "kind": "end_turn", "available": true}
            ],
            "deterministic": true
        }
        ```
    """
    global _inference_service

    if _inference_service is None:
        raise HTTPException(
            status_code=400,
            detail='Model not loaded. Please call /load_model first.'
        )

    try:
        # 构造状态
        state = ExamState(
            vocal=request.vocal,
            dance=request.dance,
            visual=request.visual,
            stamina=request.stamina,
            max_stamina=request.max_stamina,
            score=request.score,
            target_score=request.target_score,
            turn=request.turn,
            max_turns=request.max_turns,
            block=request.block,
            review=request.review,
            aggressive=request.aggressive,
            concentration=request.concentration,
            full_power_point=request.full_power_point,
            parameter_buff=request.parameter_buff,
            lesson_buff=request.lesson_buff,
            stance=request.stance,
            stance_level=request.stance_level,
            hand_cards=request.hand_cards,
            deck_count=request.deck_count,
            grave_count=request.grave_count,
            drinks=request.drinks,
            status_enchants=request.status_enchants,
            fan_votes=request.fan_votes,
            support_cards=request.support_cards,
            gimmicks=request.gimmicks,
        )

        # 构造推理请求
        inference_request = InferenceRequest(
            state=state,
            legal_actions=request.legal_actions,
            deterministic=request.deterministic,
        )

        # 执行推理
        response = _inference_service.predict(inference_request)

        return PredictResponse(
            action_index=response.action_index,
            action_label=response.action_label,
            confidence=response.confidence,
            value_estimate=response.value_estimate,
            policy_probs=response.policy_probs,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/info')
def get_info() -> dict[str, Any]:
    """获取推理服务信息。"""
    global _inference_service

    if _inference_service is None:
        return {
            'status': 'not_loaded',
            'message': 'No model loaded',
        }

    return {
        'status': 'ready',
        'info': _inference_service.get_info(),
    }


@router.post('/unload')
def unload_model() -> dict[str, Any]:
    """卸载当前模型。"""
    global _inference_service

    if _inference_service is None:
        return {
            'status': 'success',
            'message': 'No model to unload',
        }

    _inference_service = None

    return {
        'status': 'success',
        'message': 'Model unloaded successfully',
    }


def register_inference_routes(app: FastAPI) -> None:
    """注册推理路由到FastAPI应用。"""
    app.include_router(router)


def create_inference_app() -> FastAPI:
    """创建独立的推理服务应用。"""
    app = FastAPI(
        title="Gakumas RL Inference Service",
        description="统一的RL推理服务，支持多种后端算法",
        version="1.0.0",
    )
    register_inference_routes(app)
    return app
