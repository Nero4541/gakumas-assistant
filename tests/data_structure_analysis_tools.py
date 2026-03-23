# import dataclasses
# import os
# import re
# from dataclasses import dataclass
# from typing import List, TextIO, Dict, Optional
# from loguru import logger
# from functools import lru_cache
# from src.utils.performance_tools import timeit
#
# import yaml
# import json
#
# base_path__assets = os.path.join(os.getcwd(), "..", "assets")
# base_path__game_database = os.path.join(base_path__assets, "gakumasu-diff")
# base_path__game_localization = os.path.join(base_path__assets, "GakumasTranslationData", "local-files", "masterTrans")
#
#
# @logger.catch
# def from_dict(cls, data):
#     """支持 list / 嵌套 dataclass 的自动转换"""
#     if not hasattr(cls, "__dataclass_fields__"):
#         return data
#
#     kwargs = {}
#     for f_name, f_type in cls.__annotations__.items():
#         value = data.get(f_name, dataclasses.MISSING)
#
#         if value is dataclasses.MISSING:
#             continue
#
#         # List[T]
#         if getattr(f_type, "__origin__", None) is list:
#             inner = f_type.__args__[0]
#             if value is None:
#                 kwargs[f_name] = []
#             else:
#                 kwargs[f_name] = [from_dict(inner, v) for v in value]
#
#         elif hasattr(f_type, "__dataclass_fields__"):
#             kwargs[f_name] = from_dict(f_type, value)
#
#         else:
#             kwargs[f_name] = value
#
#     return cls(**kwargs)
#
# def preprocess_yaml_data(f: TextIO) -> str:
#     _content = f.read()
#     _content = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", _content)
#     _content = _content.replace('\t', '    ')
#     return _content
#
# def load_localization(data_file_path, data_entity):
#     with open(os.path.join(base_path__game_localization, f"{os.path.splitext(os.path.basename(data_file_path))[0]}.json"), "r", encoding="utf-8") as f:
#         entries = json.load(f)
#         for entry in entries.get("data", []):
#             if pd := entry.get("produceDescriptions"):
#
#                 # 跳过 "", None, 非 dict 型的数据，只保留真正的描述对象
#                 entry["produceDescriptions"] = [
#                     d for d in pd if isinstance(d, dict)
#                 ]
#         objects = [from_dict(data_entity, entry) for entry in entries.get("data", [])]
#         return objects
#
# produce_card_data_file = os.path.join(base_path__game_database, "ProduceCard.yaml")
# skill_card_localization = os.path.join(base_path__game_localization, "ProduceCard.json")
# exam_effect_data_file = os.path.join(base_path__game_database, "ProduceExamEffect.yaml")
# exam_trigger_data_file = os.path.join(base_path__game_database, "ProduceExamTrigger.yaml")
# grow_effect_data_file = os.path.join(base_path__game_database, "ProduceCardGrowEffect.yaml")
#
# @timeit
# @lru_cache(maxsize=None)
# def load_exam_trigger() -> List[ProduceExamTrigger]:
#     """
#     加载触发器数据
#     :return:
#     """
#     with open(exam_trigger_data_file, "r", encoding="utf-8") as f:
#         content = preprocess_yaml_data(f)
#         entries = yaml.load(content, Loader=yaml.CSafeLoader)
#         objects = [from_dict(ProduceExamTrigger, entry) for entry in entries]
#         i18n_map = {e.id: e for e in load_localization(exam_trigger_data_file, GeneralProduceDescriptionsLocalization)}
#         for trigger in objects:
#             trigger.localization = i18n_map.get(trigger.id)
#     return objects
#
# @timeit
# @lru_cache(maxsize=None)
# def load_exam_effect_data() -> List[ProduceExamEffect]:
#     """
#     加载考试效果数据
#     :return:
#     """
#     with open(exam_effect_data_file, "r", encoding="utf-8") as f:
#         content = preprocess_yaml_data(f)
#         entries = yaml.load(content, Loader=yaml.CSafeLoader)
#         objects = [from_dict(ProduceExamEffect, entry) for entry in entries]
#         i18n_map = {e.id: e for e in load_localization(exam_effect_data_file, GeneralProduceDescriptionsLocalization)}
#         for exam_effect in objects:
#             exam_effect.localization = i18n_map.get(exam_effect.id)
#     return objects
#
# @timeit
# @lru_cache(maxsize=None)
# def load_grow_effect_data() -> List[ProduceCardGrowEffect]:
#     """
#     加载成长效果数据
#     :return:
#     """
#     with open(grow_effect_data_file, "r", encoding="utf-8") as f:
#         content = preprocess_yaml_data(f)
#         entries = yaml.load(content, Loader=yaml.CSafeLoader)
#         objects = [from_dict(ProduceCardGrowEffect, entry) for entry in entries]
#         exam_trigger_map = {e.id: e for e in load_exam_trigger()}
#         for grow_effect in objects:
#             grow_effect.playProduceExamTriggerCls = exam_trigger_map.get(grow_effect.playProduceExamTriggerId)
#             grow_effect.playEffectProduceExamTriggerCls = exam_trigger_map.get(grow_effect.playEffectProduceExamTriggerId)
#             for index, t in enumerate(grow_effect.targetPlayEffectProduceExamTriggerIds):
#                 grow_effect.targetPlayEffectProduceExamTriggerClss[index] = exam_trigger_map.get(t)
#     return objects
#
# @timeit
# @lru_cache(maxsize=None)
# def load_produce_card_data() -> List[ProduceCard]:
#     """
#     加载技能卡数据
#     :return:
#     """
#     with open(produce_card_data_file, "r", encoding="utf-8") as f:
#         content = preprocess_yaml_data(f)
#         entries = yaml.load(content, Loader=yaml.CSafeLoader)
#         objects: List[ProduceCard] = [from_dict(ProduceCard, entry) for entry in entries]
#         exam_effect_map = {e.id: e for e in load_exam_effect_data()}
#         exam_trigger_map = {e.id: e for e in load_exam_trigger()}
#         i18n_map = {f"{e.id}.{e.upgradeCount}": e for e in load_localization(produce_card_data_file, ProduceCardLocalization)}
#         for card in objects:
#             for play_eff in card.playEffects:
#                 if play_eff.produceExamTriggerId:
#                     play_eff.produceExamTriggerCls = exam_trigger_map.get(play_eff.produceExamTriggerId)
#                 if play_eff.produceExamEffectId:
#                     play_eff.produceExamEffectCls = exam_effect_map.get(play_eff.produceExamEffectId)
#             card.localization = i18n_map.get(f"{card.id}.{card.upgradeCount}")
#             card.playProduceExamTriggerCls = exam_trigger_map.get(card.playProduceExamTriggerId)
#     return objects
# from src.constants.path.data_path import DataPath
# from src.utils.game_database_tools import GakumasDatabase_ProduceCardDataUtils
# cards = GakumasDatabase_ProduceCardDataUtils(DataPath.GakumasuDiffData.PRODUCE_CARD)
# print(cards.get_all_item())
from src.entity.Game.Database.General import GeneralProduceDescriptionsLocalization
from src.entity.Game.Database.ProduceExamEffect import ProduceExamEffect
# exam_effects = load_exam_effect_data()
# print(exam_effects)
# print()
# grow_effects = load_grow_effect_data()
# print(grow_effects)
#
# print()
# print("effectTypes:", set([i.effectType for i in grow_effects]))
# print("costTypes:", set([i.costType for i in grow_effects]))
# print("playMovePositionTypes:", set([i.playMovePositionType for i in grow_effects]))
# print(set([i.costType for i in grow_effects]))
# print(set([i.costType for i in grow_effects]))
# print(set([i.costType for i in grow_effects]))
# print(set([i.costType for i in grow_effects]))
# print()
# produce_card = load_produce_card_data()
# print("rarity types:", set([i.rarity for i in produce_card]))
# print("plan types:", set([i.planType for i in produce_card]))
# print("play move position types:", set([i.playMovePositionType for i in produce_card]))
# print("move effect trigger types:", set([i.moveEffectTriggerType for i in produce_card]))
#
# print(produce_card[1])
# print(json.dumps(dataclasses.asdict(produce_card[1])))
# for card in produce_card:
#     print(card.id)
#     print(card.name, card.localization.name)
#     print(card.playProduceExamTriggerCls)
    # for effect_item in card.playEffects:
    #     print(effect_item.produceExamEffectId)
    #     print(effect_item.produceExamEffectCls)
    # print("-"*20)
# print(produce_card[1].playEffects[0].produceExamEffectCls)

#
# with open(skill_card_localization,encoding="utf-8") as f:
#     skill_card_localization_data = json.load(f)
# with open(skill_card_data,encoding="utf-8") as f:
#     content = preprocess_yaml_data(f)
#     skill_cards = yaml.load(content, Loader=yaml.CLoader)
#
#     print(f"rarity_list: {set([skill_card['rarity'] for skill_card in skill_cards])}")
#     print(f"planType_list: {set([skill_card['planType'] for skill_card in skill_cards])}")
#     print(f"category_list: {set([skill_card['category'] for skill_card in skill_cards])}")
#     print(f"costType_list: {set([skill_card['costType'] for skill_card in skill_cards])}")
#     print(f"playMovePositionType_list: {set([skill_card['playMovePositionType'] for skill_card in skill_cards])}")
#     print(f"moveEffectTriggerType_list: {set([skill_card['moveEffectTriggerType'] for skill_card in skill_cards])}")
#     print(f"ProduceDescriptionType_list: {set(desc['produceDescriptionType'] for skill_card in skill_cards for desc in skill_card['produceDescriptions'])}")
#
#
#     localization_data = skill_card_localization_data.get("data")
#
#     for card_data in skill_cards:
#         card_id = card_data.get("id")
#         card_level = card_data.get("upgradeCount")
#         card_name = card_data.get("name")
#         card_type = card_data.get("category")
#         cost_type = card_data.get("costType")
#         if card_type not in SkillCardType.__dict__.values():
#             card_type = SkillCardType.Unknown
#         stamina = card_data.get("forceStamina") or card_data.get("stamina")
#         isForceStamina = card_data.get("forceStamina", 0) != 0
#
#         localization = next((i18n_item for i18n_item in localization_data if i18n_item.get("id") == card_id and i18n_item.get("upgradeCount") == card_level))
#
#         skill_card = SkillCard(
#             id=card_id,
#             update_level=card_level,
#             name=card_name,
#             type=card_type,
#             use_stamina=stamina,
#             force_stamina=isForceStamina,
#             description=List[ProduceDescriptionItem](
#                 texts=[item.get("text") for item in card_data.get("produceDescriptions")],
#                 types=[item.get("produceDescriptionType") for item in card_data.get("produceDescriptions")]
#             ),
#             localization=SkillCardLocalization(
#                 name=localization.get("name"),
#                 description=List[ProduceDescriptionItem](
#                     texts=[item.get("text") for item in localization.get("produceDescriptions")],
#                     types=[item.get("produceDescriptionType") for item in localization.get("produceDescriptions")]
#                 )
#             )
#         )
#
#         print(skill_card)
#
#
#         # string_building = ""
#         # for desc in card_data.get("produceDescriptions"):
#         #     text = desc.get("text", "")
#         #     if text == "" or text is None:
#         #         text = "\n"
#         #
#         #     string_building += text
#         # print(f"id: {card_id}, name: {card_name}, use stamina: {stamina}, forceStamina: {isForceStamina}, desc: {repr(string_building)}")
#         # if string_building.startswith("\n"): string_building = string_building[1:]
#         # print(string_building)
#         # print("="*20)
#
# with open(exam_effect_data_file,encoding="utf-8") as f:
#     content = f.read()
#     content = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", content)
#     content = content.replace('\t', '    ')
#     exam_effect_data = yaml.load(content, Loader=yaml.CLoader)
#
#
#
#     print(f"effect_type_list: {set([item['effectType'] for item in exam_effect_data])}")
#
#     for effect in exam_effect_data:
#         description = List[ProduceDescriptionItem](
#             texts=[item.get("text") for item in effect.get("produceDescriptions")],
#             types=[item.get("produceDescriptionType") for item in effect.get("produceDescriptions")]
#         )
#         print("id:",effect.get("id"))
#         print("type",effect.get("effectType"))
#         print(description)
#         print()

from src.utils.game_database_tools import GakumasDatabase_ExamEffectDataUtils

effect_db = GakumasDatabase_ExamEffectDataUtils()
print(set([i.effectType for i in effect_db.get_all_item()]))
print(len([i.effectType for i in effect_db.get_all_item()]))
print(len(set([i.effectType for i in effect_db.get_all_item()])))
i: ProduceExamEffect
for i in effect_db.get_all_item():
    print("id", i.id)
    print("type", i.effectType)
    string_building = ""
    i18n_building = ""

    for c in i.produceDescriptions:
        if c.text is None:
            string_building += "\n"
        else:
            string_building += c.text
    # c_i18n: GeneralProduceDescriptionsLocalization
    for c_i18n in i.localization.produceDescriptions:
        # print(c_i18n)
        if c_i18n.text is None:
            i18n_building += "\n"
        else:
            i18n_building += c_i18n.text
    print(string_building)
    print(i18n_building)
    print()