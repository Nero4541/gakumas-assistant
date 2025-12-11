import os


class DataPath:
    DMMPlayerDLL_Log = os.path.expandvars(r"%APPDATA%\dmmgameplayer5\logs\dll.log")
    DATABASE = os.path.join(os.getcwd(), 'data/db.sqlite3')
    class GakumasuDiffData:
        BASE = os.path.join(os.getcwd(), "assets/gakumasu-diff")
        ITEM = os.path.join(BASE, "Item.yaml")
        # 技能卡
        PRODUCE_CARD = os.path.join(BASE, "ProduceCard.yaml")
        # 效果
        EXAM_EFFECT = os.path.join(BASE, "ProduceExamEffect.yaml")
        # 触发器
        EXAM_TRIGGER = os.path.join(BASE, "ProduceExamTrigger.yaml")
        # 成长效果
        GROW_EFFECT = os.path.join(BASE, "ProduceCardGrowEffect.yaml")

    class GakumasTranslationData:
        BASE = os.path.join(os.getcwd(), "assets/GakumasTranslationData/local-files/masterTrans")
        ITEM = os.path.join(BASE, "Item.json")