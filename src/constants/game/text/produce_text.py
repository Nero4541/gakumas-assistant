class ProduceText:
    """プロデュース（培育）相关的游戏内文本常量"""

    # 确认页 / 育成情报
    AFFINITY = "親愛度"  # 亲密度
    TRAINING_INFO = "育成情報"  # 育成信息
    FORMATION_DETAILS = "編成詳細"  # 编成详细

    # 参数名称
    VOCAL = "ボーカル"
    DANCE = "ダンス"
    VISUAL = "ビジュアル"
    STAMINA = "体力"
    VOCAL_OCR_VARIANTS = (VOCAL, "ポーカル", "ホーカル", "ボ一カル")
    DANCE_OCR_VARIANTS = (DANCE, "タンス")
    VISUAL_OCR_VARIANTS = (VISUAL, "ヒジュアル")
    STAMINA_OCR_VARIANTS = (STAMINA, "体カ")

    # 编成详细 - 子页签
    TAB_CARD_ITEM = "カード/アイテム"  # 卡片/道具
    TAB_ABILITY = "アビリティ"  # 能力
    TAB_EVENT = "イベント"  # 事件

    # 编成详细 - 能力分区标题
    LESSON_SUPPORT = "レッスンサポート"  # 课程支援
    SUPPORT_ABILITY = "サポートアビリティ"  # 支援能力
    MEMORY_ABILITY = "メモリーアビリティ"  # 回忆能力

    # 编成详细 - 卡片来源标题
    OWNED_AT_START = "プロデュース開始時から所持"  # 开始时持有
    OWNED_AT_START_SHORT = "開始時から所持"  # 开始时持有（简称）
    EARNED_DURING_PRODUCE = "プロデュース中獲得"  # 育成中获得

    # 编成详细 - 噪声文本（OCR 过滤用）
    GUIDE = "獲得ガイド"  # 获得指南
    SKILL_CARD_SWITCH = "スキルカードスイッチ設定"  # 技能卡切换设置

    # 育成课题 - 任务类型
    TASK_TYPE_PERFORMANCE = "実力発揮"  # 实力发挥
    TASK_TYPE_WEAKNESS = "弱点克服"  # 弱点克服
    TASK_TYPE_PERFORMANCE_OCR_VARIANTS = (
        TASK_TYPE_PERFORMANCE,
        "実カ発準",
        "実カ発揮",
    )

    # 育成课题 - 比较运算符
    COMPARISON_GE = "以上"  # ≥
    COMPARISON_LE = "以下"  # ≤

    # 阶段关键词（判定文本是否为阶段描述）
    PHASE_KEYWORDS = ("獲得", "開始時", "終了時", "終了後", "試験", "審査", "オーディション")

    # 审查 / 试验关键词
    MID_EXAM = "中間試験"  # 中间考试
    MID_REVIEW = "中間審査"  # 中间审查
    FIRST_AUDITION = "1次オーディション"  # 第一次试镜

    # ── 培育ゲームプレイ中テキスト ──
    VOICE_PLAYBACK_CONFIRM = "ボイス再生確認"  # 语音播放确认
    COMMU_FAST_FORWARD = "コミュ早送り設定"  # 对话快进设置
    PRODUCE_SKIP_SETTINGS = "プロデュース演出スキップ設定"  # 培育演出跳过设置
    P_DRINK_SELECT = "受け取るPドリンクを選んでください"  # P饮料选择提示
    P_DRINK = "Pドリンク"  # P 饮料
    DETAIL = "詳細"  # 详情
    LEGEND = "レジェンド"  # Legend 难度
    RENTAL = "レンタル"  # 租借
    MEMORY_FORMATION = "メモリー編成"  # 记忆编成
    OWNED_MEMORY = "所持メモリー"  # 所持记忆
    AVAILABLE_SKILL_CARD = "獲得可能スキルカード"  # 记忆详情中的可获得技能卡分页标题
    PRODUCE_RESULT = "プロデュース結果"  # 培育结果
    PRODUCE_COMPLETE = "プロデュース完了"  # 培育完成
    FINAL_PRODUCE_EVALUATION = "最終プロデュース評価"  # 最终培育评价
    REWARD_ITEMS = "獲得アイテム"  # 获得道具
    FINAL_EXAM = "最終試験"  # 最终考试
    FINAL_REVIEW = "最終審査"  # 最终审查
    EXAM_RESULT_RETRY_CONFIRM = "再挑戦確認"  # 再挑战确认
    END_TURN_CONFIRM = "ターン終了"  # 结束当前回合确认
    MEMORY_EFFECT = "メモリー効果"  # 记忆效果
    MEMORY_REGEN_CONFIRM = "メモリー再生成確認"  # 记忆再生成确认
    MEMORY_CONFIRM = "メモリー確定確認"  # 记忆确定确认
    MEMORY_GENERATION_COMPLETE = "メモリー生成完了"  # 记忆生成完成
    MEMORY_SELECT = "獲得するメモリーを選択してください"  # 选择要获得的记忆
    PRODUCE_HISTORY = "プロデュース履歴"  # 培育历史
    ACHIEVEMENT_PROGRESS = "アチーブメント進捗"  # 成就进度
    EVENT_REWARD_PROGRESS = "イベント報酬進捗"  # 事件奖励进度
    EVENT_POINT = "イベントPt"  # 事件点数
    UNREAD_COMMU_FAST_FORWARD_CONFIRM = "未読のコミュです"  # 未读对话快进确认
    FAILED = "不合格"  # 不合格
    CONSULT = "相談"  # 相談行动
    ACTIVITY = "活動"  # 活动类事件
    PRESENT_SUPPORT = "活動支給"  # 活动支给
    FAN_PRESENT = "差し入れ"  # 差し入れ
    BUSINESS = "営業"  # 营业
    BUSINESS_CORPORATE = "企業イベント"  # 企业活动营业
    BUSINESS_MUNICIPAL = "自治体イベント"  # 自治体活动营业
    BUSINESS_RESORT = "リゾート施設"  # 度假设施营业
    BUSINESS_COMMERCIAL = "商業施設"  # 商业设施营业
    OUTING = "おでかけ"  # 外出
    GO_OUT = "外出"  # 外出（替代写法）
    CLASS = "授業"  # 授业
    REST = "休"  # 休息
    SELF_LESSON = "自主"  # 自主训练
    HARD_LESSON = "追い込み"  # 追い込み训练
    LESSON = "レッスン"  # 课程 / レッスン
    AUDITION = "オーディション"  # 选秀 / 试镜
    SECOND_AUDITION = "2次オーディション"  # 第二次选秀
    FINALE = "FINALE"  # 最终舞台
    SPECIAL_GUIDANCE = "特別指導"  # 特别指导
    CUSTOMIZE = "カスタマイズ"  # 卡牌自定义
    SKILL_CARD_REMOVE = "削除"  # 技能卡删除
    ENHANCE_CONFIRM = "強化する"  # 强化确认

    # ── AP 相关テキスト ──
    AP_SHORTAGE = "AP不足"  # AP 不足弹窗标题
    AP_RECOVERY = "AP回復"  # AP 回复弹窗标题
    AP_DRINK = "APドリンク"  # AP 回复道具名
    AP_DRINK_USE = "使う"  # 使用 AP 道具按钮
    AP_RECOVER_BUTTON = "回復する"  # AP 回复确认按钮
    AP_CANCEL = "キャンセル"  # 取消按钮

    # ── ライブ演出テキスト ──
    TAP_TO_START = "TAP TO START"  # ライブ演出開始
    TAP_TO_START_OCR_VARIANTS = ("TAP TO START", "TAPTO START", "TAP TOSTART", "TAPTOSTART")
