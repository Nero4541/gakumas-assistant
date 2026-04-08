from src.core.tasks.producer_challenge.context import ProduceContext
from src.core.tasks.producer_challenge.pipeline import ProducePipeline
from src.core.tasks.producer_challenge.steps import (
    NavigateToProduceStep,
    SelectScenarioStep,
    SelectDifficultyStep,
    SelectIdolCardStep,
    SelectSupportCardsStep,
    SelectMemoriesStep,
    CollectMemoryAttributesStep,
    CollectFormationDetailsStep,
    ConfirmAndStartStep,
    HandleStartupModalsStep,
    ProduceGameplayLoopStep,
    HandleResultsStep,
)


def build_produce_pipeline() -> ProducePipeline:
    """构建完整的培育流程流水线（从导航到培育结束返回主页）。

    步骤顺序：
      1. NavigateToProduceStep — 从主页导航到剧本选择页
      2. SelectScenarioStep — 选择剧本（初 / NIA）
      3. SelectDifficultyStep — 选择难度（Regular/Pro/Master/Legend, NIA Pro/Master）
      4. SelectIdolCardStep — 选择偶像卡
      5. SelectSupportCardsStep — 支援卡编成
      6. SelectMemoriesStep — 记忆编成（含レンタル复选框同步）
      7. CollectMemoryAttributesStep — 采集记忆卡属性（編成詳細 → メモリー Tab）
      8. CollectFormationDetailsStep — 采集完整编成详情
      9. ConfirmAndStartStep — 处理加成道具 → 点击プロデュース開始
     10. HandleStartupModalsStep — 处理启动弹窗（语音/快进/跳过设置）→ 切换 PRODUCER 模型
     11. ProduceGameplayLoopStep — 培育主循环（行程选择/对话/レッスン/試験/P饮料）
     12. HandleResultsStep — 结果画面处理 → 切回 BASE_UI 模型 → 返回主页
    """
    return ProducePipeline([
        NavigateToProduceStep(),
        SelectScenarioStep(),
        SelectDifficultyStep(),
        SelectIdolCardStep(),
        SelectSupportCardsStep(),
        SelectMemoriesStep(),
        CollectMemoryAttributesStep(),
        CollectFormationDetailsStep(),
        ConfirmAndStartStep(),
        HandleStartupModalsStep(),
        ProduceGameplayLoopStep(),
        HandleResultsStep(),
    ])


__all__ = [
    "ProduceContext",
    "ProducePipeline",
    "build_produce_pipeline",
]