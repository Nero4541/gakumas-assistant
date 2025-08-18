import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List


@dataclass
class ConfigItem:
    """
    配置项
    """
    # 默认值
    default_value: any
    # 数据类型
    data_type: type = str
    # 验证规则（正则表达式）
    verify: Optional[str] = None
    # 是否启用验证
    use_verify: bool = False
    # 配置项实际值
    value: any = None
    # 最后修改时间
    last_modified_time: datetime = None

    def __post_init__(self):
        if self.value is None:
            self.value = self.default_value

@dataclass
class ConfigVerifyError:
    section: str
    field: str
    message: str

    def __str__(self):
        return f"[{self.section}.{self.field}]: {self.message}"

class _BaseConfigGroup:
    def __str__(self):
        return self._to_str()

    def _to_str(self, indent=0):
        lines = []
        prefix = " " * indent
        for name, attr in vars(type(self)).items():
            if isinstance(attr, ConfigItem):
                val = getattr(self, name).value
                lines.append(f"{prefix}{name}: {val!r}")
            else:
                val = getattr(self, name)
                if isinstance(val, _BaseConfigGroup):
                    lines.append(f"{prefix}{name}:")
                    lines.append(val._to_str(indent + 4))
        return "\n".join(lines)

class Base(_BaseConfigGroup):
    # 脚本运行模式
    run_mode = ConfigItem(default_value="PC", data_type=str, verify=r"Phone|PC", use_verify=True)
    # 游戏窗口名
    game_window_name = ConfigItem(default_value="gakumas", data_type=str)
    # adb连接模式
    adb_connect_mode = ConfigItem(default_value="Network", data_type=str, verify=r"USB|Network", use_verify=True)
    # adb地址
    adb_host = ConfigItem(default_value="127.0.0.1", data_type=str)
    # adb端口
    adb_port = ConfigItem(default_value="5555", data_type=int)
    # 游戏APP名
    game_package_name = ConfigItem(default_value="com.bandainamcoent.idolmaster_gakuen", data_type=str)
    # 禁用任务列表
    disabled_tasks = ConfigItem(default_value=[], data_type=list)
    # 是否启用自动运行
    enabled_auto_startup = ConfigItem(default_value=False, data_type=bool)
    # 自动运行触发时间
    auto_startup_time = ConfigItem(default_value="12:00", data_type=str)

class Task__AutoPurchase(_BaseConfigGroup):
    # 是否购买每周礼包
    weekly_gift = ConfigItem(default_value=True, data_type=bool)
    # 每日购买的物品
    daily_buy_list = ConfigItem(default_value=[], data_type=list)

@dataclass
class Config(_BaseConfigGroup):
    base = Base()
    task__auto_purchase = Task__AutoPurchase()

    @classmethod
    def to_json_dict(cls) -> dict:
        config_dict = {}

        for section_name in dir(cls):
            if section_name.startswith("__"):
                continue

            section = getattr(cls, section_name)
            if not hasattr(section, "__dict__"):
                continue

            section_dict = {}
            for attr_name in dir(section):
                if attr_name.startswith("__"):
                    continue

                item = getattr(section, attr_name)
                if isinstance(item, ConfigItem):
                    section_dict[attr_name] = {
                        "value": item.value if item.value is not None else item.default_value,
                        "default_value": item.default_value,
                        "verify": item.verify,
                        "use_verify": item.use_verify,
                        "last_modified_time": item.last_modified_time.isoformat() if item.last_modified_time else None
                    }

            if section_dict:
                config_dict[section_name] = section_dict

        return config_dict

    @classmethod
    def from_json_dict(cls, data: dict) -> tuple[bool, List[ConfigVerifyError]]:
        """
        从 dict 加载到 Config，并进行类型与正则校验
        返回: (是否成功, 错误列表)
        """
        config_instance = cls()
        errors: List[ConfigVerifyError] = []

        for section_name, section_data in data.items():
            if not hasattr(config_instance, section_name):
                continue
            section_obj = getattr(config_instance, section_name)
            for attr_name, item_data in section_data.items():
                if not hasattr(section_obj, attr_name):
                    continue
                config_item: ConfigItem = getattr(section_obj, attr_name)
                value = item_data.get("value", config_item.default_value)
                # 类型校验
                if value is not None and not isinstance(value, config_item.data_type):
                    try:
                        value = config_item.data_type(value)
                    except Exception:
                        errors.append(ConfigVerifyError(
                            section_name,
                            attr_name,
                            f"类型错误，应为 {config_item.data_type.__name__}"
                        ))
                        continue  # 跳过赋值
                # 正则校验
                if config_item.use_verify and config_item.verify:
                    if not re.fullmatch(config_item.verify, str(value)):
                        errors.append(ConfigVerifyError(
                            section_name,
                            attr_name,
                            f"值 '{value}' 不符合正则规则: {config_item.verify}"
                        ))
                        continue  # 跳过赋值
                # 赋值
                config_item.value = value
                # 最后修改时间
                if item_data.get("last_modified_time"):
                    try:
                        config_item.last_modified_time = datetime.fromisoformat(item_data["last_modified_time"])
                    except Exception:
                        errors.append(ConfigVerifyError(
                            section_name,
                            attr_name,
                            f"last_modified_time 格式错误: {item_data['last_modified_time']}"
                        ))

        return len(errors) == 0, errors