import inspect
import os
import sys
import threading
import traceback
from functools import partial, lru_cache
from pathlib import Path
from queue import Queue
from typing import Callable, Optional, TYPE_CHECKING, List
from threading import Thread
from time import time, sleep

from pyautogui import FailSafeException

from src.constants.task_status import TaskStatus
from src.constants.websocket_actions import WebsocketActions
from src.core.device.Windows.app import Windows_App
from src.core.exceptions.TaskException import UserCancelTask, TaskTimeout
from src.core.services.config_service import ConfigService
from src.core.web.websocket import WebSocketManager
from src.entity.Task import Task
from src.entity.WebSocketData import WebSocketData
from src.utils.debug_tools import DebugTools
from src.utils.logger import logger
from src.utils.string_tools import string_match, MatchConfig, MatchResult

if TYPE_CHECKING:
    from src.main import AppProcessor

config_service = ConfigService()

EXECUTE_MIDDLEWARE_WHITELIST = [
    Path("src/core/tasks").as_posix(),
    Path("src/core/services/game_utils.py").as_posix(),
]

websocket_manager = WebSocketManager()
debug_tools = DebugTools()

class TaskService:
    _app: "AppProcessor" = None
    # 任务队列
    _task_queue = Queue()
    # 任务列表
    _task_list: List[Task] = []
    # 任务初始化方法列表
    _task_pre_function: list[Callable] = []
    # 任务中间件方法列表
    _task_middleware_function: list[Callable] = []
    # 任务执行器线程
    _worker_thread: Thread = None
    # 当前运行的任务
    _current_running_task: Optional[Task] = None
    # 挂起的任务目标
    _suspend_target_task: Optional[Task] = None
    # 插入的任务
    _insert_task: Optional[Task] = None
    # 队列状态
    _queue_status: bool = False
    # 停止任务信号
    _stop_signal: bool = False
    # 挂起任务信号
    _suspend_task_signal: bool = False

    def __init__(self, app):
        self._app = app

    @staticmethod
    @lru_cache(maxsize=128)
    def _is_middleware_code(filename: str) -> bool:
        # 转换为 posix 风格统一处理
        posix_path = Path(filename).as_posix()
        return string_match(
            posix_path,
            EXECUTE_MIDDLEWARE_WHITELIST,
            MatchConfig(use_fuzz=False, use_regex=False)
        ).status

    def register_task(
            self,
            task_id: str,
            task_name: str,
            timeout: int | None = None,
            disabled_middleware: bool = False,
            manual_only: bool = False,
            hide: bool = False,
            allow_manual_suspend: bool = False,
            allow_manual_resume: bool = False
    ):
        """
        注册任务
        :param task_id: 任务ID
        :param task_name: 任务名
        :param timeout: 超时时间
        :param disabled_middleware: 禁用中间件
        :param manual_only: 仅手动模式
        :param hide: 隐藏任务
        :param allow_manual_suspend: 允许手动挂起
        :param allow_manual_resume: 允许手动恢复
        :return:
        """
        def __register(func):
            if self._find_task(task_id):
                raise RuntimeError(f"Duplicate task name: '{task_id}'")
            enable =  task_id not in config_service().base.disabled_tasks.value
            self._task_list.append(Task(
                id=task_id,
                task_name=task_name,
                enable=enable,
                disabled_middleware=disabled_middleware,
                manual_only=manual_only,
                hide=hide,
                allow_manual_suspend=allow_manual_suspend,
                allow_manual_resume=allow_manual_resume,
                function=func,
                timeout=timeout
            ))
        logger.debug(f"register task: {task_name}({task_id})")
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
                tb_str = ''.join(traceback.format_exception(type(e), e, e.__traceback__)).rstrip()
                raise RuntimeError(f"Task pre function {func.__name__} failed: \n{tb_str}")
        return True

    def start_queue(self, task_id: str = None):
        """
        执行任务
        :param task_id: 任务ID(可选)
        :return:
        """
        if self._queue_status:
            return False  # 已在运行中
        self._queue_status = True
        # 重置状态机
        self._stop_signal = False
        self._suspend_task_signal = False
        self._suspend_target_task = None
        debug_tools.clear_all()
        # 清理队列
        with self._task_queue.mutex:
            self._task_queue.queue.clear()
        # 装载任务
        if task_id:
            if task := self._find_task(task_id):
                task.update_status(TaskStatus.PENDING)
                self._task_queue.put(task)
            else:
                logger.warning(f"Task '{task_id}' not found.")
                return False
        else:
            for task in self._get_enable_tasks():
                if not task.manual_only:
                    task.update_status(TaskStatus.PENDING)
                    self._task_queue.put(task)
        # 启动工作线程
        if self._worker_thread is None or not self._worker_thread.is_alive():
            self._worker_thread = Thread(target=self._processor_task_queue, daemon=True)
            self._worker_thread.start()
        else:
            logger.error("Worker thread is already alive.")
            return False
        return True

    def suspend_running_task(self, update_status: bool = True) -> Task:
        """
        挂起当前正在运行的任务
        :return: 被挂起的 Task
        """
        if self._suspend_task_signal:
            raise RuntimeError("Task already suspended")

        target = self._current_running_task
        if not target or target.status != TaskStatus.RUNNING:
            # 回退查找
            target = next((t for t in self._task_list if t.status == TaskStatus.RUNNING), None)

        if not target:
            raise RuntimeError("No running task to suspend")
        def _send_signal():
            self._suspend_task_signal = True
            target.update_status(TaskStatus.SUSPENDED)
            self._suspend_target_task = target
            self._current_running_task = None
            if update_status:
                websocket_manager.broadcast_action_sync(WebsocketActions.TaskService.TaskQueueSuspend)
            logger.debug(f"Suspend task: {target.task_name}({target.id})")
        # 抛出线程，防止任务中调用导致出现问题
        threading.Thread(target=_send_signal, daemon=True).start()
        return target

    def resume_suspended_task(self):
        """
        恢复被挂起的任务
        """
        if not self._suspend_task_signal:
            raise RuntimeError("Current not task suspended")

        target = self._suspend_target_task
        self._suspend_task_signal = False
        target.update_status(TaskStatus.RUNNING)
        self._suspend_target_task = None
        self._current_running_task = target
        websocket_manager.broadcast_action_sync(WebsocketActions.TaskService.TaskQueueStart)
        logger.debug(f"Resume task: {target.task_name}({target.id})")

    def insert_task_to_run_queue(self, task_id: str):
        """
        插队执行：挂起当前 -> 执行新任务 -> 恢复旧任务
        """
        if self._suspend_task_signal:
            logger.error("System is already suspended, cannot insert.")
            return False

        insert_task = self._find_task(task_id)
        if not insert_task:
            logger.error(f"Task '{task_id}' does not exist.")
            return False

        logger.debug(f"Insert task: {insert_task.task_name}({insert_task.id})")

        try:
            self.suspend_running_task()
        except RuntimeError as e:
            logger.error(f"Try suspend current running task error: {e}")
            return False

        def _insert_runner():
            """插入运行器"""
            logger.debug("Start insert task thread")
            try:
                self._task_thread(insert_task)
            finally:
                logger.debug("Resume suspended task")
                self.resume_suspended_task()

        self._current_running_task = insert_task
        Thread(target=_insert_runner, daemon=True).start()
        return True

    def _get_task_names(self):
        """
        获取所有任务名
        :return:
        """
        return [task.id for task in self._task_list]

    def _processor_task_queue(self):
        """任务队列处理器，确保任务按顺序执行"""
        websocket_manager.broadcast_action_sync(WebsocketActions.TaskService.TaskQueueStart)

        # 执行 Pre-functions
        try:
            for func in self._task_pre_function:
                if func() is False:
                    raise RuntimeError(f"Pre-function {func.__name__} returned False")
        except Exception as e:
            logger.error(f"Task queue pre-check failed: {e}")
            websocket_manager.broadcast_action_sync(WebsocketActions.TaskService.TaskQueueStop)
            self._queue_status = False
            self._app.yolo_engine.pause()
            return

        try:
            while not self._task_queue.empty():
                if self._stop_signal:
                    break
                task = self._task_queue.get()
                self._current_running_task = task
                websocket_manager.broadcast_action_sync(
                    WebsocketActions.TaskService.UpdateCurrentTask,
                    WebSocketData(message={
                        "task_id": task.id,
                    }
                ))
                logger.info(f"Run task: {task.task_name}({task.id})")
                self._task_thread(task)
                if task.status == TaskStatus.FAILED:
                    logger.warning(f"Task {task.task_name}({task.id}) failed, clearing queue.")
                    with self._task_queue.mutex:
                        self._task_queue.queue.clear()
                    break
        finally:
            websocket_manager.broadcast_action_sync(WebsocketActions.TaskService.TaskQueueStop)
            self._queue_status = False
            self._app.yolo_engine.pause()
            self._current_running_task = None
            logger.debug("Task queue processor exited")

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
        """任务方法注入器"""

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

        execute_file = frame.f_code.co_filename

        # 忽略不在src里的
        if os.path.join(os.getcwd(), "src") not in execute_file:
            return partial(self._trace_calls, task=task)

        # print(f">>> [Trace] {frame.f_code.co_filename}:{frame.f_lineno} | func: {frame.f_code.co_name}")

        # 忽略队列管理器
        if execute_file == __file__ or execute_file == inspect.getfile(Task):
            return partial(self._trace_calls, task=task)

        if "logger" in execute_file:
            return partial(self._trace_calls, task=task)

        # 检查停止信号
        if self._stop_signal:
            raise UserCancelTask(task)

        if self._suspend_task_signal and self._suspend_target_task == task:
            wait_and_extend(lambda: self._suspend_task_signal, step=0.1)
            if self._stop_signal:
                raise UserCancelTask(task)

        if task.timeout not in (None, -1):
            if (time() - task.get_start_time()) > task.timeout:
                raise TaskTimeout(task)

        # Windows 焦点丢失挂起
        if isinstance(self._app.device, Windows_App):
            wait_and_extend(lambda: not self._app.device.is_app_focused())
            if self._stop_signal:
                raise UserCancelTask(task)

        if not task.disabled_middleware and self._is_middleware_code(frame.f_code.co_filename):
            wait_and_extend(lambda: not self._exec_task_middleware(), step=0.2)
            if self._stop_signal:
                raise UserCancelTask(task)

        return partial(self._trace_calls, task=task)

    def _task_thread(self, task: Task):
        """
        执行任务线程
        :param task: 任务实例
        :return:
        """
        try:
            task.update_status(TaskStatus.RUNNING)
            task.update_start_time()
            # 注入trace
            sys.settrace(partial(self._trace_calls, task=task))
            func = task.function
            # 注入App实例
            sig = inspect.signature(func)
            result = func(self._app) if len(sig.parameters) > 0 else func()
            # 处理结果状态
            if result in TaskStatus.__dict__.keys():
                task.update_status(result)
            elif result is False:
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

    def get_current_running_task(self) -> Task:
        return self._current_running_task

    def get_current_suspend_task(self) -> Task:
        return self._suspend_target_task

    def get_task_list(self):
        """获取所有任务列表"""
        return {
            task.id: {
                "description": task.task_name,
                "enable": task.enable,
                "last_run_time": task.last_run_time,
                "start_time": task.get_start_time(),
                "status": task.status,
                "manual_only": task.manual_only,
                "allow_manual_resume": task.allow_manual_resume,
                "allow_manual_suspend": task.allow_manual_suspend,
            }
            for task in self._task_list if task.hide is False
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
        if self._queue_status:
            if self._suspend_task_signal:
                return TaskStatus.SUSPENDED
            return TaskStatus.RUNNING
        return TaskStatus.PENDING

    def stop(self):
        """停止任务队列"""
        if not self._queue_status:
            return False
        self._stop_signal = True
        self._suspend_task_signal = False
        with self._task_queue.mutex:
            for task in [t for t in self._task_list if t.status == TaskStatus.PENDING]:
                task.update_status(TaskStatus.CANCELED)
            self._task_queue.queue.clear()
        return True