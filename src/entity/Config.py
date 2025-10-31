import copy
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Any, Tuple

from src.constants.device.adb import ADBOperation, ADBConnectMode


@dataclass
class ConfigItem:
    """
    配置项
    """
    # 默认值
    default_value: Any
    # 数据类型
    data_type: type = str
    # 验证规则（正则表达式）
    verify: Optional[str] = None
    # 是否启用验证
    use_verify: bool = False
    # 配置项实际值
    value: Any = None
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
    def __init__(self):
        # 遍历类定义的所有 ConfigItem
        for name, attr in vars(type(self)).items():
            if isinstance(attr, ConfigItem):
                # 深拷贝，生成实例独立副本
                setattr(self, name, copy.deepcopy(attr))
            elif isinstance(attr, _BaseConfigGroup):
                # 嵌套结构的情况（递归初始化）
                setattr(self, name, attr.__class__())

    def __str__(self):
            return self._to_str()

    def _to_str(self, indent=0):
        lines = []
        prefix = " " * indent
        for name, attr in vars(self).items():  # 只遍历实例属性
            if isinstance(attr, ConfigItem):
                lines.append(f"{prefix}{name}: {attr.value!r}")
            elif isinstance(attr, _BaseConfigGroup):
                lines.append(f"{prefix}{name}:")
                lines.append(attr._to_str(indent + 4))
        return "\n".join(lines)

class _Base(_BaseConfigGroup):
    # 脚本运行模式
    run_mode = ConfigItem(default_value="PC", data_type=str, verify=r"Phone|PC", use_verify=True)
    # 游戏窗口名
    game_window_name = ConfigItem(default_value="gakumas", data_type=str)
    # adb连接模式
    adb_connect_mode = ConfigItem(
        default_value=ADBConnectMode.NETWORK,
        data_type=str,
        verify="|".join(v for k, v in ADBConnectMode.__dict__.items() if not k.startswith("__") and not callable(v)),
        use_verify=True
    )
    # adb地址
    adb_host = ConfigItem(default_value="127.0.0.1", data_type=str)
    # adb端口(Network)
    adb_port = ConfigItem(default_value="5555", data_type=int)
    # adb端口(USB)
    adb_serial = ConfigItem(default_value="", data_type=str)
    # Android截图服务
    android_screen_capture_service = ConfigItem(
        default_value=ADBOperation.ScreenCaptureService.ADB,
        data_type=str,
        verify="|".join(k for k in ADBOperation.ScreenCaptureService.__dict__ if not k.startswith("__") and not callable(k)),
        use_verify=True
    )
    # Android点击服务
    android_touch_service = ConfigItem(
        default_value="ADB",
        data_type=str,
        verify="|".join(k for k in ADBOperation.TouchService.__dict__ if not k.startswith("__") and not callable(k)),
        use_verify=True
    )
    # 游戏APP名
    game_package_name = ConfigItem(default_value="com.bandainamcoent.idolmaster_gakuen", data_type=str)
    # 禁用任务列表
    disabled_tasks = ConfigItem(default_value=[], data_type=list)
    # 是否启用自动运行
    enabled_auto_startup = ConfigItem(default_value=False, data_type=bool)
    # 自动运行触发时间
    auto_startup_time = ConfigItem(default_value="12:00", data_type=str)

class _Task:

    class DispatchWork(_BaseConfigGroup):
        # 每次重新配置工作时间
        reconfigure_work_hours = ConfigItem(default_value=True, data_type=bool)
        # 工作时间
        working_hours = ConfigItem(default_value="12H", data_type=str, verify=r"4H|8H|12H", use_verify=True)

    class AutoPurchase(_BaseConfigGroup):
        # 是否购买每周礼包
        weekly_gift = ConfigItem(default_value=True, data_type=bool)
        # 每日购买的物品
        daily_buy_list = ConfigItem(default_value=[], data_type=list)

    class AutoContest(_BaseConfigGroup):
        # 挑战前自动重新配置队伍
        auto_reconfigure_team_before_challenge = ConfigItem(default_value=False, data_type=bool)
        # 挑战顺序
        challenge_order = ConfigItem(default_value="random", data_type=str, verify=r"random|highest_power|lowest_power|balanced_power", use_verify=True)

@dataclass
class Config(_BaseConfigGroup):
    base: _Base = field(default_factory=_Base)
    task__auto_purchase: _Task.AutoPurchase = field(default_factory=_Task.AutoPurchase)
    task__auto_contest: _Task.AutoContest = field(default_factory=_Task.AutoContest)
    task__dispatch_work: _Task.DispatchWork = field(default_factory=_Task.DispatchWork)

    def to_json_dict(self) -> dict:
        def serialize_group(group):
            result = {}
            for name, attr in vars(group).items():  # 遍历实例属性
                if isinstance(attr, ConfigItem):
                    result[name] = {
                        "value": attr.value if attr.value is not None else attr.default_value,
                        "default_value": attr.default_value,
                        "verify": attr.verify,
                        "use_verify": attr.use_verify,
                        "last_modified_time": attr.last_modified_time.isoformat() if attr.last_modified_time else None
                    }
                elif isinstance(attr, _BaseConfigGroup):
                    result[name] = serialize_group(attr)
            return result

        return serialize_group(self)

    def from_json_dict(self, data: dict) -> Tuple[bool,List[ConfigVerifyError]]:
        errors = []

        def apply_group(group, group_data, group_name=""):
            for attr_name, attr_value in group_data.items():
                if not hasattr(group, attr_name):
                    continue
                item = getattr(group, attr_name)
                full_name = f"{group_name}.{attr_name}" if group_name else attr_name

                if isinstance(item, ConfigItem):
                    value = attr_value.get("value", item.default_value)
                    # # 类型校验
                    # if value is not None and not isinstance(value, item.data_type):
                    #     try:
                    #         value = item.data_type(value)
                    #     except Exception:
                    #         errors.append(ConfigVerifyError(
                    #             group_name, attr_name, f"类型错误，应为 {item.data_type.__name__}"
                    #         ))
                    #         continue
                    #
                    # # 正则校验
                    # if item.use_verify and item.verify:
                    #     import re
                    #     if not re.fullmatch(item.verify, str(value)):
                    #         errors.append(ConfigVerifyError(
                    #             group_name, attr_name, f"值 '{value}' 不符合正则规则: {item.verify}"
                    #         ))
                    #         continue
                    #
                    # item.value = value
                    #
                    # # last_modified_time
                    # if attr_value.get("last_modified_time"):
                    #     try:
                    #         item.last_modified_time = datetime.fromisoformat(attr_value["last_modified_time"])
                    #     except Exception:
                    #         errors.append(ConfigVerifyError(
                    #             group_name, attr_name, f"last_modified_time 格式错误: {attr_value['last_modified_time']}"
                    #         ))

                    if value is None or item.value == value:
                        continue
                    if not isinstance(value, item.data_type):
                        try:
                            value = item.data_type(value)
                        except Exception:
                            errors.append(ConfigVerifyError(
                                group_name,
                                attr_name,
                                f"类型错误，应为 {item.data_type.__name__}"
                            ))
                            continue  # 跳过赋值
                    # 正则校验
                    if item.use_verify and item.verify:
                        if not re.fullmatch(item.verify, str(value)):
                            errors.append(ConfigVerifyError(
                                group_name,
                                attr_name,
                                f"值 '{value}' 不符合正则规则: {item.verify}"
                            ))
                            continue  # 跳过赋值
                    # 赋值
                    item.value = value
                    item.last_modified_time = datetime.now()

                elif isinstance(item, _BaseConfigGroup):
                    # 递归处理嵌套
                    apply_group(item, attr_value, full_name)

        apply_group(self, data)
        return not bool(errors), errors

    # @classmethod
    # def from_json_dict(cls, data: dict) -> tuple[bool, List[ConfigVerifyError]]:
    #     """
    #     从 dict 加载到 Config，并进行类型与正则校验
    #     返回: (是否成功, 错误列表)
    #     """
    #     config_instance = cls()
    #     errors: List[ConfigVerifyError] = []
    #
    #     for section_name, section_data in data.items():
    #         if not hasattr(config_instance, section_name):
    #             continue
    #         section_obj = getattr(config_instance, section_name)
    #         for attr_name, item_data in section_data.items():
    #             if not hasattr(section_obj, attr_name):
    #                 continue
    #             config_item: ConfigItem = getattr(section_obj, attr_name)
    #             value = item_data.get("value", config_item.default_value)
    #             # 类型校验
    #             if value is None or config_item.value == value:
    #                 continue
    #             if not isinstance(value, config_item.data_type):
    #                 try:
    #                     value = config_item.data_type(value)
    #                 except Exception:
    #                     errors.append(ConfigVerifyError(
    #                         section_name,
    #                         attr_name,
    #                         f"类型错误，应为 {config_item.data_type.__name__}"
    #                     ))
    #                     continue  # 跳过赋值
    #             # 正则校验
    #             if config_item.use_verify and config_item.verify:
    #                 if not re.fullmatch(config_item.verify, str(value)):
    #                     errors.append(ConfigVerifyError(
    #                         section_name,
    #                         attr_name,
    #                         f"值 '{value}' 不符合正则规则: {config_item.verify}"
    #                     ))
    #                     continue  # 跳过赋值
    #             # 赋值
    #             config_item.value = value
    #             config_item.last_modified_time = datetime.now()
    #
    #     return len(errors) == 0, errors