class ProduceDescriptionType:
    """介绍富文本类型"""
    Exam = "ProduceDescriptionType_Exam"
    ProduceExamEffectType = "ProduceDescriptionType_ProduceExamEffectType"
    PlainText = "ProduceDescriptionType_PlainText"
    ProduceCard = "ProduceDescriptionType_ProduceCard"
    ProduceCardGrowEffectType = "ProduceDescriptionType_ProduceCardGrowEffectType"
    ProduceCardCategory = "ProduceDescriptionType_ProduceCardCategory"
    ProduceDescription = "ProduceDescriptionType_ProduceDescription"
    ProduceDescriptionName = "ProduceDescriptionType_ProduceDescriptionName"
    Unknown = "ProduceDescriptionType_Unknown"

class ProduceExamEffectType:
    """考试效果类型"""
    # Stamina 和 Card Effects (体力和卡片效果)
    StaminaDamage = "ProduceExamEffectType_ExamStaminaDamage"  # 减少或伤害玩家的体力
    StaminaRecover = "ProduceExamEffectType_ExamStaminaRecover"  # 恢复体力
    StaminaReduce = "ProduceExamEffectType_ExamStaminaReduce"  # 减少体力
    StaminaConsumptionAdd = "ProduceExamEffectType_ExamStaminaConsumptionAdd"  # 增加体力消耗
    StaminaConsumptionDown = "ProduceExamEffectType_ExamStaminaConsumptionDown"  # 减少体力消耗
    StaminaRecoverFix = "ProduceExamEffectType_ExamStaminaRecoverFix"  # 固定值的体力恢复

    # 卡片和技能的使用与影响
    CardDraw = "ProduceExamEffectType_ExamCardDraw"  # 增加或减少抽卡的数量
    CardMove = "ProduceExamEffectType_ExamCardMove"  # 卡片的移动效果
    CardSearchEffectPlayCountBuff = "ProduceExamEffectType_ExamCardSearchEffectPlayCountBuff"  # 增强某些卡片搜索的效果
    CardCreateId = "ProduceExamEffectType_ExamCardCreateId"  # 生成卡片的标识
    CardUpgrade = "ProduceExamEffectType_ExamCardUpgrade"  # 提升卡片的级别或能力
    CardDuplicate = "ProduceExamEffectType_ExamCardDuplicate"  # 重复或复制卡片
    ForcePlayCardSearch = "ProduceExamEffectType_ExamForcePlayCardSearch"  # 强制执行卡片搜索

    # Buff 和 Debuff（增益与减益效果）
    ParameterBuff = "ProduceExamEffectType_ExamParameterBuff"  # 为某个参数增加增益效果
    ParameterBuffMultiplePerTurn = "ProduceExamEffectType_ExamParameterBuffMultiplePerTurn"  # 每回合增加多重增益效果
    ParameterBuffReduce = "ProduceExamEffectType_ExamParameterBuffReduce"  # 减少某个参数的增益效果
    GimmickParameterDebuff = "ProduceExamEffectType_ExamGimmickParameterDebuff"  # 通过特定机制使某个参数的减益效果增强
    AggressiveReduce = "ProduceExamEffectType_ExamAggressiveReduce"  # 减少攻击性或进攻效果
    StanceLock = "ProduceExamEffectType_StanceLock"  # 锁定玩家或角色的某种姿势或状态

    # 阻挡、限制和防护
    Block = "ProduceExamEffectType_ExamBlock"  # 阻挡某些动作或效果
    BlockAddDown = "ProduceExamEffectType_ExamBlockAddDown"  # 减少阻挡的效果
    BlockFix = "ProduceExamEffectType_ExamBlockFix"  # 固定的阻挡效果
    BlockValueMultiple = "ProduceExamEffectType_ExamBlockValueMultiple"  # 多倍增加阻挡的数值
    BlockPerUseCardCount = "ProduceExamEffectType_ExamBlockPerUseCardCount"  # 每次使用卡片时增加阻挡次数
    BlockRestriction = "ProduceExamEffectType_ExamBlockRestriction"  # 限制某些类型的阻挡或防护

    # 与课程、回顾、复习相关的效果
    LessonDependExamReview = "ProduceExamEffectType_ExamLessonDependExamReview"  # 依赖考试回顾来决定某些效果
    LessonBuffAdditive = "ProduceExamEffectType_ExamLessonBuffAdditive"  # 增加课程增益效果
    LessonBuffMultiple = "ProduceExamEffectType_ExamLessonBuffMultiple"  # 课程增益效果的多重效果
    Review = "ProduceExamEffectType_ExamReview"  # 触发复习相关的效果
    LessonDependBlock = "ProduceExamEffectType_ExamLessonDependBlock"  # 根据阻挡效果来触发课程相关的效果
    ReviewDependExamCardPlayAggressive = "ProduceExamEffectType_ExamReviewDependExamCardPlayAggressive"  # 回顾阶段依赖于某些激进的卡片玩法
    ReviewAdditive = "ProduceExamEffectType_ExamReviewAdditive"  # 回顾阶段的附加效果

    # 增强与惩罚机制
    EnthusiasticAdditive = "ProduceExamEffectType_ExamEnthusiasticAdditive"  # 增强玩家或角色的热情效果
    EnthusiasticMultiple = "ProduceExamEffectType_ExamEnthusiasticMultiple"  # 热情效果的多重增强
    GimmickSlump = "ProduceExamEffectType_ExamGimmickSlump"  # 模拟某种情绪低谷或效果减弱
    Panic = "ProduceExamEffectType_ExamPanic"  # 可能模拟玩家或角色的慌乱状态，降低表现

    # 时间和回合限制
    EffectTimer = "ProduceExamEffectType_ExamEffectTimer"  # 与时间相关的效果，比如限时触发的效果
    ExtraTurn = "ProduceExamEffectType_ExamExtraTurn"  # 额外的回合或时间
    LessonFix = "ProduceExamEffectType_ExamLessonFix"  # 修复课程相关的效果

    # 特殊的战术效果
    GimmickPlayCardLimit = "ProduceExamEffectType_ExamGimmickPlayCardLimit"  # 限制卡片的使用次数或限制某些卡片的激活
    StatusEnchant = "ProduceExamEffectType_ExamStatusEnchant"  # 为玩家或角色附加状态效果

class ProduceCardGrowEffectType:
    """卡片成长效果类型"""
    # —— 费用类（Cost Related） ——
    CostAdd = "ProduceCardGrowEffectType_CostAdd"  # 增加卡牌费用
    CostReduce = "ProduceCardGrowEffectType_CostReduce"  # 减少卡牌费用
    CostAggressiveAdd = "ProduceCardGrowEffectType_CostAggressiveAdd"  # 增加激进（进攻）类费用需求
    CostAggressiveReduce = "ProduceCardGrowEffectType_CostAggressiveReduce"  # 减少激进（进攻）类费用需求
    CostParameterBuffAdd = "ProduceCardGrowEffectType_CostParameterBuffAdd"  # 增加使用时所需参数加成
    CostParameterBuffReduce = "ProduceCardGrowEffectType_CostParameterBuffReduce"  # 减少使用时所需参数加成
    CostReviewAdd = "ProduceCardGrowEffectType_CostReviewAdd"  # 增加回顾（Review）相关费用
    CostReviewReduce = "ProduceCardGrowEffectType_CostReviewReduce"  # 减少回顾（Review）相关费用
    CostLessonBuffAdd = "ProduceCardGrowEffectType_CostLessonBuffAdd"  # 增加课程（Lesson）类费用要求
    CostLessonBuffReduce = "ProduceCardGrowEffectType_CostLessonBuffReduce"  # 减少课程（Lesson）类费用要求
    CostPenetrateAdd = "ProduceCardGrowEffectType_CostPenetrateAdd"  # 增加贯穿（Penetrate）型费用
    CostPenetrateReduce = "ProduceCardGrowEffectType_CostPenetrateReduce"  # 减少贯穿（Penetrate）型费用
    CostFullPowerPointAdd = "ProduceCardGrowEffectType_CostFullPowerPointAdd"  # 增加满能量点(FPP)需求
    CostFullPowerPointReduce = "ProduceCardGrowEffectType_CostFullPowerPointReduce"  # 减少满能量点(FPP)需求

    # —— 基础参数 Buff 类（Parameter Buff Related） ——
    ParameterBuffTurnAdd = "ProduceCardGrowEffectType_ParameterBuffTurnAdd"  # 增加参数 Buff 的持续回合数
    ParameterBuffMultiplePerTurnAdd = "ProduceCardGrowEffectType_ParameterBuffMultiplePerTurnAdd"  # 每回合增加更多的参数 Buff

    # —— Lesson / Review 系（课程、回顾） ——
    LessonAdd = "ProduceCardGrowEffectType_LessonAdd"  # 增加课程效果
    LessonReduce = "ProduceCardGrowEffectType_LessonReduce"  # 减少课程效果
    LessonCountAdd = "ProduceCardGrowEffectType_LessonCountAdd"  # 增加课程触发次数
    LessonCountReduce = "ProduceCardGrowEffectType_LessonCountReduce"  # 减少课程触发次数
    LessonBuffAdd = "ProduceCardGrowEffectType_LessonBuffAdd"  # 增加课程增益量
    LessonDependBlockAdd = "ProduceCardGrowEffectType_LessonDependBlockAdd"  # 与 Block 相关联的课程效果提升
    LessonDependExamReviewAdd = "ProduceCardGrowEffectType_LessonDependExamReviewAdd"  # 与回顾联动的课程增强
    LessonDependExamCardPlayAggressiveAdd = "ProduceCardGrowEffectType_LessonDependExamCardPlayAggressiveAdd"  # 与激进打法联动的课程增强
    ReviewAdd = "ProduceCardGrowEffectType_ReviewAdd"  # 增加回顾收益

    # —— Block / Stamina 系（防御、体力） ——
    BlockAdd = "ProduceCardGrowEffectType_BlockAdd"  # 增加阻挡数值
    BlockReduce = "ProduceCardGrowEffectType_BlockReduce"  # 减少阻挡数值
    StaminaConsumptionDownTurnAdd = "ProduceCardGrowEffectType_StaminaConsumptionDownTurnAdd"  # 降低体力消耗的回合数提升

    # —— Card 行为与触发方式（Behavior / Trigger Related） ——
    PlayTriggerChange = "ProduceCardGrowEffectType_PlayTriggerChange"  # 修改卡片的触发条件
    EffectChange = "ProduceCardGrowEffectType_EffectChange"  # 替换卡片原本的效果
    EffectAdd = "ProduceCardGrowEffectType_EffectAdd"  # 在现有效果上追加新效果
    PlayEffectTriggerChange = "ProduceCardGrowEffectType_PlayEffectTriggerChange"  # 修改效果触发时机
    PlayMovePositionTypeChange = "ProduceCardGrowEffectType_PlayMovePositionTypeChange"  # 改变使用后卡片移动位置（如弃牌/留场）

    # —— 状态、附魔、卡片特性（Status / Enchant Related） ——
    CardStatusEnchantChange = "ProduceCardGrowEffectType_CardStatusEnchantChange"  # 修改附魔或状态效果
    InitialAdd = "ProduceCardGrowEffectType_InitialAdd"  # 增加该卡片初始携带数量

    # —— 能量点（FullPowerPoint） 系列 ——
    FullPowerPointAdd = "ProduceCardGrowEffectType_FullPowerPointAdd"  # 增加满能量点
    FullPowerPointReduce = "ProduceCardGrowEffectType_FullPowerPointReduce"  # 减少满能量点

class ProduceCardType:
    """卡牌类型"""
    Active = "ProduceCardCategory_ActiveSkill"
    Mental = "ProduceCardCategory_MentalSkill"
    Trouble = "ProduceCardCategory_Trouble" # 目前仅有一张 眠気
    Unknown = "ProduceCardCategory_Unknown"

class ProduceCardMovePositionType:
    """卡牌移动类型"""
    # 不做操作
    Unknown = "ProduceCardMovePositionType_Unknown"
    # 丢弃
    Grave = "ProduceCardMovePositionType_Grave"

class ProduceCardRarity:
    """卡牌稀有度等级"""
    N = "ProduceCardRarity_N"
    R = "ProduceCardRarity_R"
    SR = "ProduceCardRarity_Sr"
    SSR = "ProduceCardRarity_Ssr"
