from typing import TYPE_CHECKING, List

from src.core.tasks.producer_challenge.steps.base import ProduceStep
from src.utils.logger import logger

if TYPE_CHECKING:
    from src.core.tasks.producer_challenge.context import ProduceContext
    from src.main import AppProcessor


class ProducePipeline:
    """
    培育流程流水线。

    按顺序执行一组 ProduceStep，在它们之间传递共享的 ProduceContext。
    任意一步的 validate 或 execute 失败都会中止流水线并抛出异常。
    """

    def __init__(self, steps: List[ProduceStep] | None = None):
        self.steps: List[ProduceStep] = steps or []

    def add_step(self, step: ProduceStep) -> "ProducePipeline":
        self.steps.append(step)
        return self

    def run(self, app: "AppProcessor", ctx: "ProduceContext"):
        total = len(self.steps)
        for idx, step in enumerate(self.steps, 1):
            tag = f"[{idx}/{total}] {step.step_name}"

            # 恢复中断模式下跳过编成相关步骤
            if getattr(ctx, "resumed_from_interrupt", False) and getattr(step, "skip_on_resume", False):
                logger.info(f"{tag} — 恢复中断模式，跳过")
                continue

            if not step.validate(app, ctx):
                raise RuntimeError(f"{tag} — 前置条件检查失败")

            logger.info(f"{tag} — 开始执行")
            if not step.execute(app, ctx):
                raise RuntimeError(f"{tag} — 执行失败")
            logger.success(f"{tag} — 完成")

        logger.success("ProducePipeline 全部步骤执行完毕")
