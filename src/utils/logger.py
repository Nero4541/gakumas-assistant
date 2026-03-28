import sys
import time
from pathlib import Path

from loguru import logger

from src.utils.runtime_paths import resolve_log_path

logger.remove()

LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level:<8}</level> | "
    "<cyan>{thread.name}</cyan> | "
    "<cyan>{name}:{function}:{line}</cyan> <red>-</red> "
    "<level>{message}</level>"
)

# 控制台
logger.add(
    sys.stdout,
    level="DEBUG",
    format=LOG_FORMAT,
    enqueue=True,
    backtrace=True,
)

# Ensure the packaged/runtime log directory exists regardless of the caller cwd.
log_dir = resolve_log_path()
Path(log_dir).mkdir(parents=True, exist_ok=True)

# 文件
logger.add(
    str(log_dir / f"{time.strftime('%Y-%m-%d')}.log"),
    rotation="00:00",
    retention="7 days",
    level="DEBUG",
    format=LOG_FORMAT,
    enqueue=True,
    backtrace=True,
)
