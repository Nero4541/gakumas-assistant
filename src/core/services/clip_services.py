from src.core.services.clip.item import ItemCLIP
from src.core.services.clip.skill_card import SkillCardCLIP
from src.core.services.clip.support_card import SupportCardCLIP
from src.core.inference.ONNX import CLIPModelFromONNX


class CLIPServiceManager:
    """统一管理各类 CLIP 识别服务，共享同一个 ONNX 模型会话以节省内存。"""

    _model_session: CLIPModelFromONNX
    skill_card_clip: SkillCardCLIP
    item_clip: ItemCLIP
    support_card_clip: SupportCardCLIP

    def __init__(self):
        """初始化共享 ONNX 模型会话，并创建各类 CLIP 子服务实例。"""
        self._model_session = CLIPModelFromONNX()
        self.skill_card_clip = SkillCardCLIP(self._model_session)
        self.item_clip = ItemCLIP(self._model_session)
        self.support_card_clip = SupportCardCLIP(self._model_session)