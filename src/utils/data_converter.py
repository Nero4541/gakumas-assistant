import dataclasses
from typing import Type, Dict

_FIELD_META_CACHE = {}

class DataConverter:

    @staticmethod
    def _analyze_dataclass(target_dataclass: Type) -> Dict[str, tuple]:
        """
        预处理 Dataclass 的字段信息，避免运行时重复反射
        """
        if target_dataclass in _FIELD_META_CACHE:
            return _FIELD_META_CACHE[target_dataclass]

        meta = {}
        # 优先使用 dataclasses.fields 以支持继承和 Field 配置，但 annotations 更快
        # 这里为了保持原逻辑兼容性，并提升速度，混合处理
        if not hasattr(target_dataclass, "__annotations__"):
            _FIELD_META_CACHE[target_dataclass] = {}
            return {}

        for f_name, f_type in target_dataclass.__annotations__.items():
            # 预先判断类型
            origin = getattr(f_type, "__origin__", None)
            is_list = origin is list
            is_dataclass = hasattr(f_type, "__dataclass_fields__")

            nested_type = None
            if is_list:
                # 提取 List[T] 中的 T
                args = getattr(f_type, "__args__", [])
                if args:
                    nested_type = args[0]
                    # 检查 T 是否为 dataclass
                    if not hasattr(nested_type, "__dataclass_fields__"):
                        nested_type = None # 基础类型 List，无需递归
            elif is_dataclass:
                nested_type = f_type

            # 只有需要特殊处理（List 或 Nested Dataclass）才存入 meta
            # 普通字段直接赋值即可，无需记录在 meta 中以节省查找时间
            if is_list or is_dataclass:
                meta[f_name] = (is_list, nested_type)

        _FIELD_META_CACHE[target_dataclass] = meta
        return meta

    @classmethod
    def from_dict(cls, target_dataclass, data):
        """
        入口方法：建议只在这里加 logger.catch，不要加在递归内部
        """
        # 这里可以加 @logger.catch，但请确保不要加在 _inner_from_dict 上
        return cls._inner_from_dict(target_dataclass, data)

    @classmethod
    def _inner_from_dict(cls, target_dataclass, data):
        # 1. 基础类型直接返回
        if not hasattr(target_dataclass, "__dataclass_fields__"):
            return data

        # 2. 获取预计算的元数据
        field_meta = cls._analyze_dataclass(target_dataclass)

        kwargs = {}

        # 3. 遍历数据而非遍历字段 (如果 data 字段通常少于 dataclass 字段)
        # 或者遍历 dataclass 字段 (更安全，确保结构正确)
        # 这是一个针对大量数据的极速路径：

        for f_name, f_type in target_dataclass.__annotations__.items():
            value = data.get(f_name, dataclasses.MISSING)

            if value is dataclasses.MISSING:
                continue

            if value is None:
                kwargs[f_name] = None
                continue

            # 检查是否需要特殊处理 (List 或 Nested)
            meta_info = field_meta.get(f_name)

            if meta_info:
                is_list, nested_type = meta_info

                if is_list:
                    if nested_type:
                        # 递归处理 List[Dataclass]
                        kwargs[f_name] = [cls._inner_from_dict(nested_type, v) for v in value]
                    else:
                        # 普通 List
                        kwargs[f_name] = value
                else:
                    # 递归处理 Nested Dataclass
                    kwargs[f_name] = cls._inner_from_dict(nested_type, value)
            else:
                # 简单字段直接赋值
                kwargs[f_name] = value

        return target_dataclass(**kwargs)