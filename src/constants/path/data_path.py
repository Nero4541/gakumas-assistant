import os


class DataPath:
    DMMPlayerDLL_Log = os.path.expandvars(r"%APPDATA%\dmmgameplayer5\logs\dll.log")
    DATABASE = os.path.join(os.getcwd(), 'data/db.sqlite3')
    class GakumasuDiffData:
        BASE = os.path.join(os.getcwd(), "assets/gakumasu-diff")
        ITEM = os.path.join(BASE, "Item.yaml")
        CHARACTER = os.path.join(BASE, "Character.yaml")
        IDOL_CARD = os.path.join(BASE, "IdolCard.yaml")
        SUPPORT_CARD = os.path.join(BASE, "SupportCard.yaml")
        # 技能卡
        PRODUCE_CARD = os.path.join(BASE, "ProduceCard.yaml")
        PRODUCE_CARD_CUSTOMIZE = os.path.join(BASE, "ProduceCardCustomize.yaml")
        PRODUCE_CARD_SEARCH = os.path.join(BASE, "ProduceCardSearch.yaml")
        PRODUCE_CARD_STATUS_ENCHANT = os.path.join(BASE, "ProduceCardStatusEnchant.yaml")
        # 效果
        EFFECT_GROUP = os.path.join(BASE, "EffectGroup.yaml")
        EXAM_EFFECT = os.path.join(BASE, "ProduceExamEffect.yaml")
        # 触发器
        EXAM_TRIGGER = os.path.join(BASE, "ProduceExamTrigger.yaml")
        # 成长效果
        GROW_EFFECT = os.path.join(BASE, "ProduceCardGrowEffect.yaml")
        PRODUCE_EXAM_STATUS_ENCHANT = os.path.join(BASE, "ProduceExamStatusEnchant.yaml")
        PRODUCE_ITEM = os.path.join(BASE, "ProduceItem.yaml")
        PRODUCE_DRINK = os.path.join(BASE, "ProduceDrink.yaml")
        PRODUCE_SKILL = os.path.join(BASE, "ProduceSkill.yaml")

    class GakumasTranslationData:
        BASE = os.path.join(os.getcwd(), "assets/GakumasTranslationData/local-files/masterTrans")
        ITEM = os.path.join(BASE, "Item.json")
