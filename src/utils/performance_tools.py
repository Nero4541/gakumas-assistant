import time
import functools
from src.utils.logger import logger

def timeit(func):
    """测试函数执行时间"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        end = time.perf_counter()
        use_time = (end - start)*1000
        if use_time > 300:
            logger.warning(f"[{func.__name__}] 执行耗时: {use_time:.3f} ms")
        return result
    return wrapper
