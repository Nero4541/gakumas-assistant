from dataclasses import dataclass
from time import time
from typing import Callable, Optional

from src.utils.logger import logger
from src.constants.task_status import TaskStatus
from src.constants.websocket_actions import WebsocketActions
from src.core.web.websocket import WebSocketManager
from src.entity.WebSocketData import WebSocketData

websocket_manager = WebSocketManager()

@dataclass
class Task:
    # 任务ID
    id: str
    # 任务名
    task_name: str
    # 启用任务
    enable: bool
    # 禁用中间件
    disabled_middleware: bool
    # 任务方法
    function: Callable
    # 超时时间
    timeout: int
    # 任务状态
    status: str = TaskStatus.PENDING
    # 开始时间
    _start_time: Optional[int] = -1
    # 结束时间
    _end_time: Optional[int] = -1
    # 上次运行时间
    last_run_time: float = 0
    # 仅手动触发
    manual_only: bool = False
    # 允许手动挂起
    allow_manual_suspend: bool = False
    # 允许手动解除挂起
    allow_manual_resume: bool = False

    def update_start_time(self):
        self._start_time = int(time())
        self.last_run_time = self._start_time
        self._end_time = None
        self.update_status(TaskStatus.RUNNING)
        return self._start_time

    def update_end_time(self):
        self._end_time = int(time())
        return self._end_time

    def update_status(self, status: str):
        """更新任务状态"""
        if status == self.status:
            return
        old_status = self.status
        self.status = status
        websocket_manager.broadcast_action_sync(
            WebsocketActions.TaskService.TaskStatusUpdate,
            WebSocketData(message={
                "id": self.id,
                "target_status": status,
            })
        )
        logger.debug(f"[TaskStatus] {self.id}: {old_status} -> {status}")

    def get_start_time(self):
        return self._start_time
