import sys
import time
from loguru import logger

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

# 文件
logger.add(
    f"logs/{time.strftime('%Y-%m-%d')}.log",
    rotation="00:00",
    retention="7 days",
    level="DEBUG",
    format=LOG_FORMAT,
    enqueue=True,
    backtrace=True,
)
