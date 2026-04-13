"""LLM 配置模块 — 从 ConfigService 读取全局 LLM 设置。"""

from src.core.services.config_service import ConfigService


def get_llm_config() -> dict:
    """从 ConfigService 读取 LLM 相关配置，返回扁平字典。

    返回值示例::

        {
            "base_url": "http://192.168.100.10:11434/v1/",
            "model": "gpt-oss:20b",
            "api_key": "ollama",
            "timeout": 60.0,
            "max_tokens": 4096,
            "num_ctx": 8192,
            "temperature": 0.3,
        }
    """
    base = ConfigService().items.base
    return {
        "base_url":    str(base.llm_base_url),
        "model":       str(base.llm_model),
        "api_key":     str(base.llm_api_key),
        "timeout":     float(base.llm_timeout),
        "max_tokens":  int(base.llm_max_tokens),
        "num_ctx":     int(base.llm_num_ctx),
        "temperature": float(base.llm_temperature),
    }


# 非 ConfigService 管理的运行时常量
MAX_RETRIES = 2
RETRY_DELAY = 2.0
TOP_P = 0.9
MAX_ACTIVE_EFFECTS = 15
MAX_ACTIVE_ENCHANTS = 10
