from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from src.utils.logger import logger

if TYPE_CHECKING:
    from src.core.tasks.producer_challenge.context import ProduceContext
    from src.main import AppProcessor


class ProduceStep(ABC):
    """培育流程中的一个步骤基类。"""

    step_name: str = "unnamed_step"
    skip_on_resume: bool = False  # 恢复中断模式下是否跳过此步骤

    @abstractmethod
    def execute(self, app: "AppProcessor", ctx: "ProduceContext") -> bool:
        """
        执行步骤逻辑。

        :return: True 表示成功；False 或抛异常表示失败。
        """
        ...

    def validate(self, app: "AppProcessor", ctx: "ProduceContext") -> bool:
        """
        前置条件检查（可选覆盖）。

        默认总是通过。子类可覆盖以校验上一步是否正确完成。
        """
        return True

    def __repr__(self):
        return f"<{self.__class__.__name__} step_name={self.step_name!r}>"
