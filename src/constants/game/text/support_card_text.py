class SupportCardText:
    """支援卡相关的游戏内文本常量"""

    # 品级 / Rarity
    RARITY_R = "R"
    RARITY_SR = "SR"
    RARITY_SSR = "SSR"

    # 属性类型 / Type
    TYPE_VOCAL = "ボーカル"
    TYPE_DANCE = "ダンス"
    TYPE_VISUAL = "ビジュアル"
    TYPE_ASSIST = "アシスト"

    # 计划类型 / Plan Type
    PLAN_COMMON = "フリー"
    PLAN_SENSE = "センス"
    PLAN_LOGIC = "ロジック"
    PLAN_SENSE_LIMITED = "センス限定"
    PLAN_LOGIC_LIMITED = "ロジック限定"

    # 强化相关
    LV_ENHANCE = "Lv強化"
    LIMIT_BREAK = "上限解放"
    LIMIT_BREAK_CONFIRM = "解放する"
    ENHANCE_CONFIRM = "強化する"
    ENHANCE_CLOSE = "閉じる"
    ENHANCE_CANCEL = "キャンセル"
    ENHANCE_MAX_LEVEL_TEXT = "最大までLv強化されています"
    SUPPORT_CONVERT = "サポート変換"
    CONVERT_CONFIRM = "変換する"
    CONVERT_SELECT_ALL = "全選択"
    CONVERT_DECISION = "決定"

    # 支援卡页面
    SUPPORT_CARD_TAB = "サポートカード"
    VIEW_DETAIL = "詳細を見る"
    MAX_LEVEL_BUTTON = ">>"

    class RARITY_DB_KEY:
        """数据库中的品级枚举值"""
        R = "SupportCardRarity_R"
        SR = "SupportCardRarity_SR"
        SSR = "SupportCardRarity_SSR"

    class TYPE_DB_KEY:
        """数据库中的属性类型枚举值"""
        VOCAL = "SupportCardType_Vocal"
        DANCE = "SupportCardType_Dance"
        VISUAL = "SupportCardType_Visual"
        STAMINA = "SupportCardType_Stamina"
        ASSIST = "SupportCardType_Assist"

    class PLAN_DB_KEY:
        """数据库中的计划类型枚举值"""
        COMMON = "ProducePlanType_Common"
        SENSE = "ProducePlanType_SensePlan"
        LOGIC = "ProducePlanType_LogicPlan"
