import copy
import platform
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Any, Tuple, Dict

from src.constants.device.adb import ADBOperation, ADBConnectMode
from src.utils.logger import logger


def _config_enum_values(enum_cls) -> List[str]:
    return [
        value for key, value in enum_cls.__dict__.items()
        if not key.startswith("__") and isinstance(value, str)
    ]


def _default_run_mode() -> str:
    return "PC" if platform.system() == "Windows" else "Phone"


def _run_mode_options() -> List[Dict[str, Any]]:
    pc_option: Dict[str, Any] = {
        "title": "电脑端（DMM）",
        "value": "PC",
    }
    try:
        from src.core.device.windows_compat import (
            get_windows_unavailability_reason,
            windows_pc_mode_is_available,
        )

        if not windows_pc_mode_is_available():
            pc_option["disabled"] = True
            pc_option["disabled_reason"] = get_windows_unavailability_reason()
    except Exception:
        if platform.system() != "Windows":
            pc_option["disabled"] = True
            pc_option["disabled_reason"] = "PC / DMM 模式仅支持 Windows。"

    return [
        pc_option,
        {"title": "手机端", "value": "Phone"},
    ]


@dataclass
class ConfigItemUI:
    label: Optional[str] = None
    hint: Optional[str] = None
    component: Optional[str] = None
    options: List[Dict[str, Any]] = field(default_factory=list)
    visible_if: Optional[Dict[str, Any]] = None
    readonly: bool = False
    resettable: bool = False
    auto_generate: bool = True
    order: int = 0

    def to_json_dict(self) -> dict:
        return {
            "label": self.label,
            "hint": self.hint,
            "component": self.component,
            "options": self.options,
            "visible_if": self.visible_if,
            "readonly": self.readonly,
            "resettable": self.resettable,
            "auto_generate": self.auto_generate,
            "order": self.order,
        }


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
    # 前端展示元数据
    ui: ConfigItemUI = field(default_factory=ConfigItemUI)

    def __post_init__(self):
        if self.value is None:
            self.value = copy.deepcopy(self.default_value)

    def set(self, value: Any, touch: bool = True):
        self.value = value
        if touch:
            self.last_modified_time = datetime.now()
        return self.value

    def reset(self, touch: bool = True):
        return self.set(copy.deepcopy(self.default_value), touch=touch)

    def unwrap(self):
        return self.value

    def __repr__(self):
        return repr(self.value)

    def __str__(self):
        return str(self.value)

    def __bool__(self):
        return bool(self.value)

    def __len__(self):
        return len(self.value)

    def __iter__(self):
        return iter(self.value)

    def __contains__(self, item):
        return item in self.value

    def __getitem__(self, item):
        return self.value[item]

    def __getattr__(self, item):
        return getattr(self.value, item)

    def __eq__(self, other):
        if isinstance(other, ConfigItem):
            other = other.value
        return self.value == other

    def __int__(self):
        return int(self.value)

    def __float__(self):
        return float(self.value)


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
    """脚本基本配置"""

    # 脚本运行模式
    run_mode = ConfigItem(
        default_value=_default_run_mode(),
        data_type=str,
        verify=r"Phone|PC",
        use_verify=True,
        ui=ConfigItemUI(
            label="运行模式",
            hint="脚本的执行模式（需重启生效）",
            component="select",
            options=_run_mode_options(),
            order=10,
        )
    )
    # 游戏窗口名
    game_window_name = ConfigItem(
        default_value="gakumas",
        data_type=str,
        ui=ConfigItemUI(
            label="游戏窗口名",
            hint="默认：gakumas（修改后需重启生效）",
            resettable=True,
            visible_if={"base.run_mode": "PC"},
            order=100,
        )
    )
    # 自动启动游戏
    auto_start_game = ConfigItem(
        default_value=False,
        data_type=bool,
        ui=ConfigItemUI(
            label="自动启动游戏",
            hint="当游戏未启动时是否自动启动游戏",
            component="switch",
            order=20,
        )
    )
    # adb连接模式
    adb_connect_mode = ConfigItem(
        default_value=ADBConnectMode.NETWORK,
        data_type=str,
        verify="|".join(v for k, v in ADBConnectMode.__dict__.items() if not k.startswith("__") and not callable(v)),
        use_verify=True,
        ui=ConfigItemUI(
            label="ADB连接模式",
            hint="安卓调试桥的连接模式，手机建议使用USB，模拟器可使用网络连接（修改后需重启生效）",
            component="select",
            options=[
                {"title": "网络连接", "value": "Network"},
                {"title": "USB连接", "value": "USB"},
            ],
            visible_if={"base.run_mode": "Phone"},
            order=30,
        )
    )
    # adb地址
    adb_host = ConfigItem(
        default_value="127.0.0.1",
        data_type=str,
        ui=ConfigItemUI(
            label="ADB主机名",
            hint="安卓调试桥的ip地址，模拟器一般是127.0.0.1",
            resettable=True,
            visible_if={"base.run_mode": "Phone", "base.adb_connect_mode": "Network"},
            order=40,
        )
    )
    # adb端口(Network)
    adb_port = ConfigItem(
        default_value="5555",
        data_type=int,
        ui=ConfigItemUI(
            label="ADB端口",
            hint="安卓调试桥的端口，默认5555，Android11以上为系统随机",
            component="number",
            resettable=True,
            visible_if={"base.run_mode": "Phone", "base.adb_connect_mode": "Network"},
            order=50,
        )
    )
    # adb端口(USB)
    adb_serial = ConfigItem(
        default_value="",
        data_type=str,
        ui=ConfigItemUI(
            label="通过USB连接的ADB设备",
            hint="请选择通过USB连接的设备，如未找到设备请尝试刷新列表",
            component="adb_devices",
            visible_if={"base.run_mode": "Phone", "base.adb_connect_mode": "USB"},
            order=60,
        )
    )
    # Android截图服务
    android_screen_capture_service = ConfigItem(
        default_value=ADBOperation.ScreenCaptureService.ADB,
        data_type=str,
        verify="|".join(_config_enum_values(ADBOperation.ScreenCaptureService)),
        use_verify=True,
        ui=ConfigItemUI(
            label="ADB截图方式",
            hint="scrcpy / DroidCast 的延迟通常优于 ADB 截图；scrcpy 需要将官方 Releases 的 scrcpy-server 放到 bin",
            component="select",
            options=[
                {"title": "scrcpy", "value": "scrcpy"},
                {"title": "DroidCast", "value": "DroidCast"},
                {"title": "ADB", "value": "ADB"},
            ],
            visible_if={"base.run_mode": "Phone"},
            order=70,
        )
    )
    # Android点击服务
    android_touch_service = ConfigItem(
        default_value=ADBOperation.TouchService.ADB,
        data_type=str,
        verify="|".join(_config_enum_values(ADBOperation.TouchService)),
        use_verify=True,
        ui=ConfigItemUI(
            label="ADB点击屏幕方式",
            hint="可选 MaaTouch / minitouch / scrcpy；MaaTouch 需放入官方构建产物到 bin/maatouch 或用 workflow 生成，minitouch 需放入官方构建产物到 bin/minitouch 且当前只支持 Android 9 及以下",
            component="select",
            options=[
                {"title": "MaaTouch", "value": "maatouch"},
                {"title": "minitouch", "value": "minitouch"},
                {"title": "scrcpy", "value": "scrcpy"},
                {"title": "ADB", "value": "ADB"},
            ],
            visible_if={"base.run_mode": "Phone"},
            order=80,
        )
    )
    # 游戏APP名
    game_package_name = ConfigItem(
        default_value="com.bandainamcoent.idolmaster_gakuen",
        data_type=str,
        ui=ConfigItemUI(
            label="游戏包名",
            hint="默认：com.bandainamcoent.idolmaster_gakuen（修改后需重启生效）",
            resettable=True,
            visible_if={"base.run_mode": "Phone"},
            order=90,
        )
    )
    # 禁用任务列表
    disabled_tasks = ConfigItem(
        default_value=[],
        data_type=list,
        ui=ConfigItemUI(
            label="禁用任务列表",
            hint="配置禁用任务列表",
            component="disabled_tasks",
            order=110,
        )
    )
    # 是否启用自动运行
    enabled_auto_startup = ConfigItem(
        default_value=False,
        data_type=bool,
        ui=ConfigItemUI(
            label="每日自动执行脚本",
            hint="开启后会在设定时间自动开始执行任务队列",
            component="switch",
            order=120,
        )
    )
    # 自动运行触发时间
    auto_startup_time = ConfigItem(
        default_value="12:00",
        data_type=str,
        verify=r"(?:[01]\d|2[0-3]):[0-5]\d",
        use_verify=True,
        ui=ConfigItemUI(
            label="自动运行触发时间",
            hint="24小时制，格式为 HH:MM",
            component="time",
            visible_if={"base.enabled_auto_startup": True},
            order=130,
        )
    )
    # 是否启用资源仓库更新检查
    enabled_check_resource_updates = ConfigItem(
        default_value=False,
        data_type=bool,
        ui=ConfigItemUI(
            label="定时检查资源仓库更新",
            hint="按设定周期检查 assets/GakumasTranslationData 与 assets/gakumasu-diff 是否有上游更新",
            component="switch",
            order=135,
        )
    )
    # 启动时检查资源仓库更新
    check_resource_updates_on_startup = ConfigItem(
        default_value=False,
        data_type=bool,
        ui=ConfigItemUI(
            label="启动时检查资源仓库更新",
            hint="每次启动后立即检查一次资源仓库更新",
            component="switch",
            order=136,
        )
    )
    # 资源仓库定时检查周期
    resource_update_check_period = ConfigItem(
        default_value="daily",
        data_type=str,
        verify=r"daily|every_3_days|weekly",
        use_verify=True,
        ui=ConfigItemUI(
            label="资源仓库检查周期",
            hint="仅用于定时检查",
            component="select",
            options=[
                {"title": "每天", "value": "daily"},
                {"title": "每 3 天", "value": "every_3_days"},
                {"title": "每周", "value": "weekly"},
            ],
            visible_if={"base.enabled_check_resource_updates": True},
            order=137,
        )
    )


class _Task:
    """任务配置"""

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
        # 自动刷新可购买列表（免费）
        refresh_shop = ConfigItem(default_value=True, data_type=bool)
        # 使用石头刷新列表
        use_gem_refresh = ConfigItem(default_value=False, data_type=bool)

    class AutoContest(_BaseConfigGroup):
        # 挑战前自动重新配置队伍
        auto_reconfigure_team_before_challenge = ConfigItem(default_value=False, data_type=bool)
        # 挑战顺序
        challenge_order = ConfigItem(default_value="random", data_type=str, verify=r"random|highest_power|lowest_power|balanced_power", use_verify=True)

class _DMMPlayerConfig(_BaseConfigGroup):
    """DMMPlayer启动器配置"""
    game_exe_path = ConfigItem(
        default_value="",
        data_type=str,
        ui=ConfigItemUI(
            label="游戏安装目录",
            hint="游戏安装路径，指向gakumas.exe（默认自动获取，非必要无需修改）",
            visible_if={"base.run_mode": "PC"},
            order=140,
        )
    )
    viewer_id = ConfigItem(
        default_value="",
        data_type=str,
        ui=ConfigItemUI(
            label="Viewer ID",
            hint="自动获取，非必要无需修改",
            readonly=True,
            visible_if={"base.run_mode": "PC"},
            order=150,
        )
    )
    open_id = ConfigItem(
        default_value="",
        data_type=str,
        ui=ConfigItemUI(
            label="Open ID",
            hint="自动获取，非必要无需修改",
            readonly=True,
            visible_if={"base.run_mode": "PC"},
            order=160,
        )
    )
    pf_token = ConfigItem(
        default_value="",
        data_type=str,
        ui=ConfigItemUI(
            label="PF Token",
            hint="自动获取，非必要无需修改",
            readonly=True,
            visible_if={"base.run_mode": "PC"},
            order=170,
        )
    )


@dataclass
class Config(_BaseConfigGroup):
    base: _Base = field(default_factory=_Base)
    dmm_player: _DMMPlayerConfig = field(default_factory=_DMMPlayerConfig)
    task__auto_purchase: _Task.AutoPurchase = field(default_factory=_Task.AutoPurchase)
    task__auto_contest: _Task.AutoContest = field(default_factory=_Task.AutoContest)
    task__dispatch_work: _Task.DispatchWork = field(default_factory=_Task.DispatchWork)

    def to_json_dict(self) -> dict:
        def serialize_group(group):
            result = {}
            for name, attr in vars(group).items():  # 遍历实例属性
                if isinstance(attr, ConfigItem):
                    value = None
                    if attr.value is not None:
                        value = attr.value
                    elif attr.default_value is not None:
                        value = attr.default_value
                    else:
                        target_type = attr.data_type
                        if target_type == bool:
                            value = False
                        elif target_type == int:
                            value = 0
                        elif target_type == float:
                            value = 0.0
                        elif target_type in [dict, list, tuple]:
                            value = target_type([])
                        elif target_type == str:
                            value = ""
                        else:
                            logger.warning(f"Unsupported cast type: {target_type}")

                    result[name] = {
                        "value": value,
                        "default_value": attr.default_value,
                        "data_type": attr.data_type.__name__,
                        "verify": attr.verify,
                        "use_verify": attr.use_verify,
                        "last_modified_time": attr.last_modified_time.isoformat() if attr.last_modified_time else None,
                        "ui": attr.ui.to_json_dict(),
                    }
                elif isinstance(attr, _BaseConfigGroup):
                    result[name] = serialize_group(attr)
            return result

        return serialize_group(self)

    def get_item(self, path: str) -> ConfigItem:
        current = self
        for key in path.split("."):
            if not hasattr(current, key):
                raise AttributeError(f"Config path not found: {path}")
            current = getattr(current, key)
        if not isinstance(current, ConfigItem):
            raise AttributeError(f"Config path is not a ConfigItem: {path}")
        return current

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
                    item.set(value)

                elif isinstance(item, _BaseConfigGroup):
                    # 递归处理嵌套
                    apply_group(item, attr_value, full_name)

        apply_group(self, data)
        return not bool(errors), errors
