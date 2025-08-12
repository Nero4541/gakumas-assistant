# import yaml
from src.utils.diff_tools import GakumasuDiffItemDataUtils

# from src.utils.string_tools import string_match
#
# # 读取 YAML 文件
# with open("../assets/gakumasu-diff/Item.yaml", "r", encoding="utf-8") as f:
#     data = yaml.safe_load(f)
#
#     print("data rows:", len(data))
#     names = []
#     descriptions = []
#     for row in data:
#         names.append(row["name"])
#         descriptions.append(row["description"])
#
#     result = string_match("[世界一可愛い私1藤田ことねのピー", names)
#     print(result, descriptions[names.index(result.result)])

items_database = GakumasuDiffItemDataUtils("../assets/gakumasu-diff/Item.yaml")
print(items_database.search("センスノート(ダンス)"))