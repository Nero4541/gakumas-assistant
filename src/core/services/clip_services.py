from src.core.services.clip.item import ItemCLIP
# from src.core.services.clip.skill_card import SkillCardCLIP
from src.core.ONNX import CLIPModelFromONNX

class CLIPServiceManager:
    _model_session: CLIPModelFromONNX
    # skill_card_clip: SkillCardCLIP
    item_clip: ItemCLIP
    def __init__(self):
        self._model_session = CLIPModelFromONNX()
        # self.skill_card_clip = SkillCardCLIP(self._model_session)
        self.item_clip = ItemCLIP(self._model_session)