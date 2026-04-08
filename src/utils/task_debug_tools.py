from collections import deque
from datetime import datetime
from typing import Any

_TASK_DEBUG_TRACE_MAXLEN = 200


def _make_json_safe(value: Any):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _make_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_make_json_safe(item) for item in value]
    return str(value)


def reset_task_debug_trace(app, task_id: str | None = None, maxlen: int = _TASK_DEBUG_TRACE_MAXLEN):
    trace = deque(maxlen=maxlen)
    setattr(app, "_task_debug_trace", trace)
    setattr(app, "_task_debug_task_id", task_id)
    return trace


def record_task_step(app, step: str, **data):
    trace = getattr(app, "_task_debug_trace", None)
    if trace is None or not isinstance(trace, deque):
        trace = reset_task_debug_trace(app)

    entry = {
        "timestamp": datetime.now().isoformat(timespec="milliseconds"),
        "step": step,
    }
    if data:
        entry["data"] = _make_json_safe(data)
    trace.append(entry)
    return entry


def get_task_debug_trace(app) -> list[dict]:
    trace = getattr(app, "_task_debug_trace", None)
    if trace is None:
        return []
    return list(trace)
