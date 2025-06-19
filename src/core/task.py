import app
import sys
from dataclasses import dataclass
from functools import partial
from queue import Queue
from typing import Callable, Optional
from threading import Thread, Lock
from time import time, sleep

from src.utils.logger import logger


class TaskStatus:
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    RETRY = "RETRY"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


@dataclass
class Task:
    name: str
    description: str
    enable: bool
    function: Callable
    timeout: int
    status: str = TaskStatus.PENDING
    _start_time: Optional[int] = -1
    _end_time: Optional[int] = -1
    last_run_time: float = 0

    def __init__(self, name: str, description: str, enable: bool, function: Callable, timeout: int = 30):
        """
        :param name: 任务名
        :param description: 任务介绍
        :param enable: 是否启用
        :param function: 方法
        :param timeout: 任务超时事件
        """
        self.name = name
        self.description = description
        self.enable = enable
        self.function = function
        self.timeout = timeout

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
        if self.status in [TaskStatus.RUNNING, TaskStatus.PENDING]:
            self.status = status

    def get_start_time(self):
        return self._start_time


class TaskQueue:
    _app: "app.AppProcessor" = None
    _task_queue = Queue()
    _task_list = []
    _run_lock: Lock
    _worker_thread: Thread = None

    def __init__(self, app):
        self._app = app
        self._run_lock = Lock()

    def reg_task(self, task_name: str, task_description: str, task_func: Callable, timeout: int | None = None):
        """
        注册任务
        """
        if self._find_task(task_name):
            raise RuntimeError(f"Duplicate task name: '{task_name}'")
        self._task_list.append(Task(task_name, task_description, True, task_func, timeout))

    def exec_task(self, task_name: str = None):
        """执行任务"""
        if self._run_lock.locked():
            return False  # 已在运行中

        # 在锁内封装整个启动流程
        self._run_lock.acquire()

        logger.debug("start exec task queue")
        if self._task_queue.not_empty:
            with self._task_queue.mutex:
                self._task_queue.queue.clear()
        if task_name:
            if task_name not in self._get_task_names():
                logger.warning(f"Task '{task_name}' does not exist.")
                return False
            self._task_queue.put(self._find_task(task_name))
        else:
            for task in self._get_enable_tasks():
                self._task_queue.put(task)
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

            logger.debug("[Exit]Task queue is empty or stopped")
        finally:
            if self._run_lock.locked():
                self._run_lock.release()

    def _trace_calls(self, frame, event, arg, task: Task):
        if frame.f_code.co_name != task.function.__name__:
            return partial(self._trace_calls, task=task)
        if task.timeout and task.timeout != -1 and (int(time()) - task.get_start_time()) > task.timeout:
            task.status = TaskStatus.FAILED
            raise TimeoutError(f"Task '{task.name}' execution timed out.")
        while not self._app.exec_middleware():
            sleep(0.1)
        return partial(self._trace_calls, task=task)

    def _task_thread(self, task: Task):
        """执行任务"""
        logger.debug(f"Executing task: {task.name}")

        try:
            task.status = TaskStatus.RUNNING
            task.update_start_time()
            sys.settrace(partial(self._trace_calls, task=task))
            if task.function(self._app) is False:
                task.status = TaskStatus.CANCELED
            else:
                task.status = TaskStatus.SUCCESS
        except Exception as e:
            task.status = TaskStatus.FAILED
            logger.error(f"Task '{task.name}' failed: {e}")
        finally:
            task.update_end_time()
            sys.settrace(None)
            logger.debug(f"Task Status: {task.status}")

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
        return self._run_lock.locked() and not self._task_queue.empty()

    def stop(self):
        """停止任务队列"""
        if not self.queue_status():
            return False
        with self._task_queue.mutex:
            self._task_queue.queue.clear()
        if self._run_lock.locked():
            self._run_lock.release()
        return True