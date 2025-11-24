from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

class UserCancelTask(Exception):
    def __init__(self, task: "Task"):
        self.task = task

    def __str__(self):
        return f"User cancel task {self.task.id}"

class TaskTimeout(Exception):
    def __init__(self, task: "Task"):
        self.task = task

    def __str__(self):
        return f"Task '{self.task.id}' execution timed out."