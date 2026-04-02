"""
任务失败时的现场转储工具。

在任务超时或异常失败时，自动保存：
- 最后一帧截图 (PNG)
- YOLO 标注帧 (PNG)
- YOLO 检测结果 (JSON)
- 任务信息 & 异常堆栈 (JSON)

转储目录: logs/dumps/<task_id>_<timestamp>/
"""
import json
import os
import traceback
from datetime import datetime
from typing import TYPE_CHECKING, Optional

import cv2
import numpy as np

from src.utils.logger import logger
from src.utils.runtime_paths import resolve_log_path

if TYPE_CHECKING:
    from src.entity.Task import Task
    from src.entity.Yolo import Yolo_Results
    from src.main import AppProcessor

# 最多保留的 dump 目录数量，超出时删除最旧的
MAX_DUMPS = 50


def _cleanup_old_dumps(dumps_root: str):
    """保留最新的 MAX_DUMPS 个 dump 目录，删除多余的。"""
    try:
        entries = []
        for name in os.listdir(dumps_root):
            full = os.path.join(dumps_root, name)
            if os.path.isdir(full):
                entries.append((os.path.getmtime(full), full))
        if len(entries) <= MAX_DUMPS:
            return
        entries.sort()
        for _, path in entries[: len(entries) - MAX_DUMPS]:
            import shutil
            shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass


def _serialize_yolo_results(results: "Yolo_Results") -> list:
    """将 Yolo_Results 中的检测框序列化为可 JSON 化的列表。"""
    items = []
    raw = results.results  # ONNXYoloResult
    for i, box in enumerate(results.boxes):
        entry = {
            "label": box.label,
            "x": int(box.x),
            "y": int(box.y),
            "w": int(box.w),
            "h": int(box.h),
            "cx": int(box.cx),
            "cy": int(box.cy),
        }
        # 置信度来自原始推理结果
        if raw is not None and hasattr(raw, "scores") and i < len(raw.scores):
            entry["confidence"] = round(float(raw.scores[i]), 4)
        items.append(entry)
    return items


def dump_task_failure(
    app: "AppProcessor",
    task: "Task",
    exception: Optional[BaseException] = None,
):
    """
    保存任务失败的诊断现场。

    Parameters
    ----------
    app : AppProcessor
        应用主处理器，用于获取最新帧和 YOLO 结果。
    task : Task
        失败的任务对象。
    exception : BaseException, optional
        导致失败的异常。
    """
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dump_dir = str(resolve_log_path("dumps", f"{task.id}_{ts}"))
        os.makedirs(dump_dir, exist_ok=True)

        # ── 1. 最后一帧截图 ──
        frame: Optional[np.ndarray] = getattr(app, "latest_frame", None)
        if frame is not None:
            cv2.imwrite(os.path.join(dump_dir, "last_frame.png"), frame)

        # ── 2. YOLO 检测结果 & 标注帧 ──
        results: Optional["Yolo_Results"] = getattr(app, "latest_results", None)
        yolo_data = []
        if results is not None:
            yolo_data = _serialize_yolo_results(results)
            # 标注帧
            raw = results.results
            if raw is not None and hasattr(raw, "plot"):
                try:
                    annotated = raw.plot()
                    cv2.imwrite(os.path.join(dump_dir, "annotated_frame.png"), annotated)
                except Exception:
                    pass

        # ── 3. 任务 & 状态元数据 ──
        meta = {
            "timestamp": ts,
            "task": {
                "id": task.id,
                "name": task.task_name,
                "status": task.status,
                "timeout": task.timeout,
                "runtime_timeout": task.get_timeout(),
                "start_time": task.get_start_time(),
            },
            "game": {
                "current_location": getattr(
                    getattr(app, "game_status_manager", None),
                    "current_location",
                    None,
                ),
            },
            "yolo_detections": yolo_data,
        }

        # ── 4. 异常堆栈 ──
        if exception is not None:
            meta["exception"] = {
                "type": type(exception).__name__,
                "message": str(exception),
                "traceback": traceback.format_exception(
                    type(exception), exception, exception.__traceback__
                ),
            }

        with open(os.path.join(dump_dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        logger.info(f"Task failure dump saved to {dump_dir}")

        # 清理旧 dump
        dumps_root = str(resolve_log_path("dumps"))
        _cleanup_old_dumps(dumps_root)

    except Exception as e:
        logger.warning(f"Failed to save task dump: {e}")
