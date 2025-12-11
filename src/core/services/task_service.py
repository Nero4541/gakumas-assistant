import inspect
import os
import sys
import threading
import traceback
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from queue import Queue
from typing import Callable, Optional, TYPE_CHECKING, List
from threading import Thread, Lock
from time import time, sleep

from pyautogui import FailSafeException

from src.constants.task_status import TaskStatus
from src.core.device.Windows.app import Windows_App
from src.core.exceptions.TaskException import UserCancelTask, TaskTimeout
from src.core.services.config_service import ConfigService
from src.entity.WebSocketData import WebSocketData
from src.utils.logger import logger
from src.utils.string_tools import string_match, MatchConfig

if TYPE_CHECKING:
    from src.main import AppProcessor

config_service = ConfigService()

EXECUTE_MIDDLEWARE_WHITELIST = [
    Path("src/core/tasks").as_posix(),
    Path("src/core/services/game_utils.py").as_posix(),
]

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
        logger.debug(f"[TaskStatus] {self.id}: {old_status} -> {status}")

    def get_start_time(self):
        return self._start_time


class TaskQueue:
    _app: "AppProcessor" = None
    _task_queue = Queue()
    _task_list: List[Task] = []
    _task_pre_function: list[Callable] = []
    _task_middleware_function: list[Callable] = []
    _insert_task: Optional[Task]
    _run_lock: Lock
    _worker_thread: Thread = None
    _suspend_current_task: bool
    _stop_event: bool

    def __init__(self, app):
        # app实例
        self._app = app
        # 运行锁
        self._run_lock = Lock()
        # 插入任务
        self._insert_task: Optional[Task] = None
        # flag：挂起当前任务
        self._suspend_current_task = False
        # flag：停止任务队列
        self._stop_event = False

    def register_task(
            self,
            task_id: str,
            task_name: str,
            timeout: int | None = None,
            disabled_middleware: bool = False,
            manual_only: bool = False,
    ):
        """
        注册任务
        :param task_id: 任务ID
        :param task_name: 任务名
        :param timeout: 超时时间
        :param disabled_middleware: 禁用中间件
        :param manual_only: 仅手动模式
        :return:
        """
        def __register(func):
            if self._find_task(task_id):
                raise RuntimeError(f"Duplicate task name: '{task_id}'")
            enable = True
            if task_id in config_service().base.disabled_tasks.value:
                enable = False
            self._task_list.append(Task(
                id=task_id,
                task_name=task_name,
                enable=enable,
                disabled_middleware=disabled_middleware,
                manual_only=manual_only,
                function=func,
                timeout=timeout
            ))
        logger.debug(f"register task: {task_id}")
        def decorator(func: Callable):
            __register(func)
        return decorator

    def register_pre_queue_start(self):
        """注册任务队列执行前预执行"""
        def decorator(func: Callable):
            if func not in self._task_pre_function:
                logger.debug(f"register task pre function: {func.__name__}")
                self._task_pre_function.append(func)
        return decorator

    def register_task_middleware(self):
        """
        注册任务中间件
        :return:
        """
        def decorator(func: Callable):
            if func not in self._task_middleware_function:
                logger.debug(f"register middleware: {func.__name__}")
                self._task_middleware_function.append(func)
        return decorator


    def __run_task_queue_pre_functions(self):
        """执行任务队列运行前初始化方法"""
        for func in self._task_pre_function:
            try:
                logger.debug(f"run task pre function: {func.__name__}")
                result = func()
                if result is False:
                    raise RuntimeError(f"Task pre function {func.__name__} error")
            except Exception as e:
                raise RuntimeError(f"Task pre function {func.__name__} failed: {e}")
        return True

    def exec_task(self, task_id: str = None):
        """执行任务"""
        if self._run_lock.locked():
            return False  # 已在运行中

        self._run_lock.acquire()
        self._stop_event = False
        logger.debug("start exec task queue")
        self._app.debug_tools.clear_all_boxes()
        if self._task_queue.not_empty:
            with self._task_queue.mutex:
                self._task_queue.queue.clear()
        if task_id:
            if task_id not in self._get_task_names():
                logger.warning(f"Task '{task_id}' does not exist.")
                return False
            task = self._find_task(task_id)
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

    def insert_task_to_run_queue(self, task_id):
        """
        插入任务到当前队列并挂起任务
        :param task_id: 任务id
        :return:
        """
        if self._suspend_current_task:
            logger.warning(f"Task '{task_id}' is suspended.")
            return False
        if task_id not in self._get_task_names():
            logger.warning(f"Task '{task_id}' does not exist.")
            return False
        self._insert_task = self._find_task(task_id)
        logger.debug(f"Insert task: {self._insert_task.task_name}(id: {self._insert_task.id})")
        self._suspend_current_task = True
        suspend_task = next(task for task in self._task_list if task.status == TaskStatus.RUNNING)
        suspend_task.update_status(TaskStatus.SUSPENDED)
        def _insert_task_thread():
            logger.debug("Start insert task thread")
            self._task_thread(self._insert_task)
            logger.debug("Resume suspended tasks thread")
            self._suspend_current_task = False
            self._insert_task = None
            suspend_task.update_status(TaskStatus.RUNNING)
        thread = Thread(target=_insert_task_thread, daemon=True, args=())
        thread.start()
        return True

    def _get_task_names(self):
        """
        获取所有任务名
        :return:
        """
        return [task.id for task in self._task_list]

    def _processor_task_queue(self):
        """任务队列处理器，确保任务按顺序执行"""
        try:
            self.__run_task_queue_pre_functions()
        except Exception as e:
            logger.error(e)
            self._app.yolo_engine.pause()
            return False

        while self._app.latest_results is None:
            sleep(0.1)
        try:
            while not self._task_queue.empty():
                task = self._task_queue.get()
                logger.info(f"Run task: {task.id}")
                self._task_thread(task)

                if task.status == TaskStatus.FAILED:
                    logger.warning(f"Task '{task.id}' failed, terminating remaining tasks.")
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

    def _exec_task_middleware(self):
        """
        执行中间件
        :return:
        """
        flag: bool = True
        for func in self._task_middleware_function:
            if func(self._app) is False:
                logger.debug(f"{func.__name__} return false")
                flag = False
        return flag

    def _trace_calls(self, frame, event, arg, task: Task):

        def wait_and_extend(condition, step=0.1):
            """
            通用等待逻辑：
            - 当 condition() 为 True 时阻塞
            - 期间累计延迟时间
            - 自动延长 task.timeout
            """
            if task.timeout in (None, -1):
                # 不处理无限或无超时
                while condition():
                    sleep(step)
                return

            added = 0.0
            while condition():
                sleep(step)
                added += step

            if added > 0:
                task.timeout += added

        if not self.is_called_by(frame, task.function.__code__):
            return partial(self._trace_calls, task=task)

        if self._stop_event:
            raise UserCancelTask(task)

        if os.path.join(os.getcwd(), "src") not in frame.f_code.co_filename:
            return partial(self._trace_calls, task=task)

        if self._suspend_current_task and self._insert_task.id != task.id:
            wait_and_extend(lambda: self._suspend_current_task)

        if task.timeout not in (None, -1):
            if (time() - task.get_start_time()) > task.timeout:
                raise TaskTimeout(task)

        if isinstance(self._app.device, Windows_App):
            wait_and_extend(lambda: not self._app.device.is_app_focused())

        # logger.debug(f"{Path(frame.f_code.co_filename).as_posix()}, {string_match(frame.f_code.co_filename, EXECUTE_MIDDLEWARE_WHITELIST, MatchConfig(use_fuzz=False, use_regex=False))}")
        if (
            # 不禁用中间件并在中间件白名单中
            not task.disabled_middleware and
            string_match(Path(frame.f_code.co_filename).as_posix(), EXECUTE_MIDDLEWARE_WHITELIST, MatchConfig(use_fuzz=False, use_regex=False))
        ):
            wait_and_extend(lambda: not self._exec_task_middleware(), step=0.2)

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
            func = task.function
            sig = inspect.signature(func)
            # 判断是否需要参数
            if len(sig.parameters) == 0:
                task_result = func()
            else:
                task_result = func(self._app)
            if task_result in TaskStatus.__dict__.keys():
                task.update_status(task_result)
            elif task_result is False:
                task.update_status(TaskStatus.CANCELED)
            else:
                task.update_status(TaskStatus.SUCCESS)
        except (UserCancelTask, FailSafeException):
            task.update_status(TaskStatus.CANCELED)
            logger.warning(f"Task '{task.task_name}({task.id})' cancelled")
        except Exception as e:
            task.update_status(TaskStatus.FAILED)
            tb_str = ''.join(traceback.format_exception(type(e), e, e.__traceback__)).rstrip()
            logger.error(f"Task '{task.task_name}({task.id})' failed:\n{tb_str}")
        finally:
            task.update_end_time()
            sys.settrace(None)
            logger.info(f"Task '{task.task_name}({task.id})' status: {task.status}")

    def _find_task(self, task_id: str):
        """查找任务"""
        return next((task for task in self._task_list if task.id == task_id), None)

    def _get_enable_tasks(self):
        """获取启用的任务"""
        return [task for task in self._task_list if task.enable]

    def get_task_list(self):
        """获取所有任务列表"""
        return {
            task.id: {
                "description": task.task_name,
                "enable": task.enable,
                "last_run_time": task.last_run_time,
                "start_time": task.get_start_time(),
                "status": task.status,
            }
            for task in self._task_list
        }

    def disable_task(self, task_id: str):
        """禁用任务"""
        if task := self._find_task(task_id):
            task.enable = False
            return True
        return False

    def enable_task(self, task_id: str):
        """启用任务"""
        if task := self._find_task(task_id):
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