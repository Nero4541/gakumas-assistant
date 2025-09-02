import os
import sys
import traceback
from dataclasses import dataclass
from functools import partial
from queue import Queue
from typing import Callable, Optional, TYPE_CHECKING, List
from threading import Thread, Lock
from time import time, sleep

from pyautogui import FailSafeException

from src.constants.task_status import TaskStatus
from src.core.exceptions.TaskException import UserCancelTask, TaskTimeout
from src.core.services.config_service import ConfigService
from src.entity.WebSocketData import WebSocketData
from src.utils.logger import logger
from src.utils.string_tools import string_match, MatchConfig

if TYPE_CHECKING:
    from src.main import AppProcessor

config_service = ConfigService()

EXECUTE_MIDDLEWARE_WHITELIST = [
    "src/core/tasks",
    "src/core/services/game_utils.py"
]

@dataclass
class Task:
    # 任务名
    name: str
    # 任务简介
    description: str
    # 启用任务
    enable: bool
    # 禁用中间件
    disabled_middleware: bool
    # 仅手动触发
    manual_only: bool
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

    def update_start_time(self):
        self._start_time = int(time())
        self.last_run_time = self._start_time
        self._end_time = None
        self.status = TaskStatus.RUNNING
        return self._start_time

    def update_end_time(self):
        self._end_time = int(time())
        return self._end_time

    def update_status(self, status: str):
        """更新任务状态"""
        old_status = self.status
        self.status = status
        logger.debug(f"[TaskStatus] {self.name}: {old_status} -> {status}")

    def get_start_time(self):
        return self._start_time


class TaskQueue:
    _app: "AppProcessor" = None
    _task_queue = Queue()
    _task_list: List[Task] = []
    _run_lock: Lock
    _worker_thread: Thread = None
    _stop_event: bool

    def __init__(self, app):
        self._app = app
        self._run_lock = Lock()
        self._stop_event = False

    def reg_task(
            self,
            task_name: str,
            task_description: str,
            task_func: Callable,
            disabled_middleware: bool = False,
            manual_only: bool = False,
            timeout: int | None = None
    ):
        """
        注册任务
        """
        if self._find_task(task_name):
            raise RuntimeError(f"Duplicate task name: '{task_name}'")
        enable = True
        if task_name in config_service().base.disabled_tasks.value:
            enable = False
        self._task_list.append(Task(
            name=task_name,
            description=task_description,
            enable=enable,
            disabled_middleware=disabled_middleware,
            manual_only=manual_only,
            function=task_func,
            timeout=timeout
        ))

    def exec_task(self, task_name: str = None):
        """执行任务"""
        if self._run_lock.locked():
            return False  # 已在运行中

        self._run_lock.acquire()
        self._stop_event = False
        logger.debug("start exec task queue")
        if self._task_queue.not_empty:
            with self._task_queue.mutex:
                self._task_queue.queue.clear()
        if task_name:
            if task_name not in self._get_task_names():
                logger.warning(f"Task '{task_name}' does not exist.")
                return False
            task = self._find_task(task_name)
            task.status = TaskStatus.PENDING
            self._task_queue.put(task)
        else:
            for task in self._get_enable_tasks():
                if task.manual_only:
                    continue
                task.status = TaskStatus.PENDING
                self._task_queue.put(task)
        self._app.ws_manager.broadcast_sync(WebSocketData(message={
            "action": "task_queue:start"
        }))
        if self._worker_thread is None or not self._worker_thread.is_alive():
            self._worker_thread = Thread(target=self._processor_task_queue, daemon=True)
            self._worker_thread.start()
        else:
            logger.error("Task Running Thread is alive")
            return False
        return True

    def _get_task_names(self):
        """
        获取所有任务名
        :return:
        """
        return [task.name for task in self._task_list]

    def _processor_task_queue(self):
        """任务队列处理器，确保任务按顺序执行"""
        self._app.yolo_engine.resume()
        while self._app.latest_results is None:
            sleep(0.1)
        try:
            while not self._task_queue.empty():
                task = self._task_queue.get()
                logger.info(f"Run task: {task.name}")
                self._task_thread(task)

                if task.status == TaskStatus.FAILED:
                    logger.warning(f"Task '{task.name}' failed, terminating remaining tasks.")
                    with self._task_queue.mutex:
                        self._task_queue.queue.clear()
                    break
            self._app.ws_manager.broadcast_sync(WebSocketData(message={
                "action": "task_queue:end"
            }))
            logger.debug("[Exit]Task queue is empty or stopped")
        finally:
            if self._run_lock.locked():
                self._run_lock.release()
            self._app.yolo_engine.pause()

    @staticmethod
    def _get_call_stack(frame):
        stack = []
        while frame:
            code = frame.f_code
            stack.append(f"{code.co_name} ({os.path.basename(code.co_filename)}:{code.co_firstlineno})")
            frame = frame.f_back
        return " -> ".join(stack)

    @staticmethod
    def is_called_by(frame, target_code):
        """检查当前frame是否由target_code对应的函数直接或间接调用"""
        f = frame
        while f is not None:
            if f.f_code is target_code:
                return True
            f = f.f_back
        return False

    def _trace_calls(self, frame, event, arg, task: Task):
        if not self.is_called_by(frame, task.function.__code__):
            return partial(self._trace_calls, task=task)
        # 任务停止
        if self._stop_event:
            raise UserCancelTask(task)
        # 拦截由库文件触发的
        if os.path.join(os.getcwd(), "src") not in frame.f_code.co_filename:
            return partial(self._trace_calls, task=task)
        # 超时抛出
        if task.timeout and task.timeout != -1 and (int(time()) - task.get_start_time()) > task.timeout:
            raise TaskTimeout(task)
        # 不在焦点不执行
        while not self._app.device.is_app_focused():
            sleep(0.2)
        # 判断是否执行中间件
        if task.disabled_middleware or not string_match(frame.f_code.co_filename, EXECUTE_MIDDLEWARE_WHITELIST, MatchConfig(use_fuzz=False, use_regex=False)):
            return partial(self._trace_calls, task=task)
        while not self._app.exec_middleware():
            sleep(0.2)
        # if "src" in frame.f_code.co_filename:
        #     print(f"执行文件: {frame.f_code.co_filename}, 当前行: {frame.f_lineno}")
        return partial(self._trace_calls, task=task)

    def _task_thread(self, task: Task):
        """
        执行任务
        :param task: 任务实例
        :return:
        """
        try:
            task.status = TaskStatus.RUNNING
            task.update_start_time()
            # 启动任务跟踪
            sys.settrace(partial(self._trace_calls, task=task))
            task_result = task.function(self._app)
            if task_result in TaskStatus.__dict__.keys():
                task.update_status(task_result)
            elif task_result is False:
                task.update_status(TaskStatus.CANCELED)
            else:
                task.update_status(TaskStatus.SUCCESS)
        except (UserCancelTask, FailSafeException):
            task.update_status(TaskStatus.CANCELED)
            logger.warning(f"Task '{task.description}({task.name})' cancelled")
        except Exception as e:
            task.update_status(TaskStatus.FAILED)
            tb_str = ''.join(traceback.format_exception(type(e), e, e.__traceback__)).rstrip()
            logger.error(f"Task '{task.description}({task.name})' failed:\n{tb_str}")
        finally:
            task.update_end_time()
            sys.settrace(None)
            logger.info(f"Task '{task.description}({task.name})' status: {task.status}")

    def _find_task(self, task_name: str):
        """查找任务"""
        return next((task for task in self._task_list if task.name == task_name), None)

    def _get_enable_tasks(self):
        """获取启用的任务"""
        return [task for task in self._task_list if task.enable]

    def get_task_list(self):
        """获取所有任务列表"""
        return {
            task.name: {
                "description": task.description,
                "enable": task.enable,
                "last_run_time": task.last_run_time,
                "start_time": task.get_start_time(),
                "status": task.status,
            }
            for task in self._task_list
        }

    def disable_task(self, task_name: str):
        """禁用任务"""
        if task := self._find_task(task_name):
            task.enable = False
            return True
        return False

    def enable_task(self, task_name: str):
        """启用任务"""
        if task := self._find_task(task_name):
            task.enable = True
            return True
        return False

    def queue_status(self):
        return self._run_lock.locked() or not self._task_queue.empty()

    def stop(self):
        """停止任务队列"""
        if not self.queue_status():
            return False
        self._stop_event = True
        with self._task_queue.mutex:
            for task in [t for t in self._task_list if t.status == TaskStatus.PENDING]:
                task.status = TaskStatus.CANCELED
            self._task_queue.queue.clear()
        if self._run_lock.locked():
            self._run_lock.release()
        return True