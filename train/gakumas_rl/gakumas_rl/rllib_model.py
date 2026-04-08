"""RLlib 旧 API stack 适配的动作掩码模型。"""

from __future__ import annotations

from typing import Any

import numpy as np
import torch
from torch import nn

from ray.rllib.models import ModelCatalog
from ray.rllib.models.modelv2 import restore_original_dimensions
from ray.rllib.models.torch.torch_modelv2 import TorchModelV2

from .model import MaskedPolicyValueNet


class RLlibMaskedActionsModel(TorchModelV2, nn.Module):
    """让 RLlib 旧 API stack 复用仓库内的动作掩码策略网络。"""

    def __init__(
        self,
        obs_space,
        action_space,
        num_outputs: int,
        model_config: dict[str, Any],
        name: str,
        **kwargs,
    ):
        TorchModelV2.__init__(self, obs_space, action_space, num_outputs, model_config, name)
        nn.Module.__init__(self)

        original_space = getattr(obs_space, 'original_space', obs_space)
        global_dim = int(np.prod(original_space['global'].shape))
        action_feature_dim = int(original_space['action_features'].shape[-1])
        hidden_dim = int(kwargs.get('hidden_dim', model_config.get('custom_model_config', {}).get('hidden_dim', 256)))
        self.net = MaskedPolicyValueNet(global_dim, action_feature_dim, hidden_dim=hidden_dim)
        self._value_out: torch.Tensor | None = None

    def forward(self, input_dict, state, seq_lens):
        """从 Dict 观测恢复原始结构，并输出带 mask 的 logits。"""

        obs = restore_original_dimensions(input_dict['obs'], self.obs_space, tensorlib='torch')
        global_obs = obs['global'].float()
        action_features = obs['action_features'].float()
        action_mask = obs['action_mask'].float()
        logits, value = self.net(global_obs, action_features, action_mask)
        self._value_out = value
        return logits, state

    def value_function(self) -> torch.Tensor:
        """返回上一轮 forward 缓存的 state value。"""

        if self._value_out is None:
            raise ValueError('value_function() called before forward().')
        return self._value_out.reshape(-1)


def register_rllib_model() -> str:
    """注册自定义 RLlib 模型，并返回固定名称。"""

    model_name = 'gakumas_masked_actions_model'
    registry = getattr(register_rllib_model, '_registered', set())
    if model_name not in registry:
        ModelCatalog.register_custom_model(model_name, RLlibMaskedActionsModel)
        registry.add(model_name)
        register_rllib_model._registered = registry
    return model_name
