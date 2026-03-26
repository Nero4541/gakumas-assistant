"""
WebView2 COM 接口绑定 — 通过 ctypes 手动构造 COM vtable
加载 WebView2Loader.dll → 创建 Environment → 创建 Controller → 配置透明 → Navigate
"""
import ctypes
import ctypes.wintypes as wt
import os
import json
from ctypes import (
    HRESULT, POINTER, byref, c_void_p, c_int, c_ulong, c_wchar_p,
    cast, Structure, WINFUNCTYPE,
)

from src.native_webview.constants import (
    GUID, RECT, COREWEBVIEW2_COLOR,
    IID_IUnknown,
    IID_ICoreWebView2Environment,
    IID_ICoreWebView2Controller,
    IID_ICoreWebView2Controller2,
    IID_ICoreWebView2,
    IID_ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler,
    IID_ICoreWebView2CreateCoreWebView2ControllerCompletedHandler,
    IID_ICoreWebView2WebMessageReceivedEventHandler,
    IID_ICoreWebView2WebMessageReceivedEventArgs,
    IID_ICoreWebView2AddScriptToExecuteOnDocumentCreatedCompletedHandler,
)


# =====================================================================
# 辅助: 手动构造 COM 回调对象
# =====================================================================
def _guid_eq(a: GUID, b: GUID) -> bool:
    return (a.Data1 == b.Data1 and a.Data2 == b.Data2 and a.Data3 == b.Data3
            and bytes(a.Data4) == bytes(b.Data4))


class _COMCallbackBase:
    """
    手动构造 COM 回调对象的基类。
    子类需设置 _iid 和 _invoke_sig，并实现 _invoke 方法。

    vtable 布局: [QueryInterface, AddRef, Release, Invoke]
    """
    _instances: list = []  # prevent GC

    def __init__(self):
        # prevent garbage collection of pointers
        self._prevent_gc = []
        self._ref_count = c_ulong(1)

        # 定义 vtable 函数签名
        QI_TYPE = WINFUNCTYPE(HRESULT, c_void_p, POINTER(GUID), POINTER(c_void_p))
        ADDREF_TYPE = WINFUNCTYPE(c_ulong, c_void_p)
        RELEASE_TYPE = WINFUNCTYPE(c_ulong, c_void_p)

        qi_func = QI_TYPE(self._query_interface)
        addref_func = ADDREF_TYPE(self._add_ref)
        release_func = RELEASE_TYPE(self._release)
        invoke_func = self._invoke_sig(self._invoke)

        self._prevent_gc.extend([qi_func, addref_func, release_func, invoke_func])

        # 构建 vtable 数组
        vtable_array = (c_void_p * 4)(
            cast(qi_func, c_void_p),
            cast(addref_func, c_void_p),
            cast(release_func, c_void_p),
            cast(invoke_func, c_void_p),
        )
        self._vtable = vtable_array
        self._prevent_gc.append(vtable_array)

        # COM 对象 = 指向 vtable 指针的指针
        self._vtable_ptr = cast(ctypes.pointer(vtable_array), c_void_p)
        self._prevent_gc.append(self._vtable_ptr)

        self._com_ptr = ctypes.pointer(self._vtable_ptr)
        self._prevent_gc.append(self._com_ptr)

        _COMCallbackBase._instances.append(self)

    @property
    def ptr(self) -> c_void_p:
        return cast(self._com_ptr, c_void_p)

    def _query_interface(self, this, riid, ppv):
        riid_val = riid[0]
        if _guid_eq(riid_val, IID_IUnknown) or _guid_eq(riid_val, self._iid):
            ppv[0] = cast(self._com_ptr, c_void_p)
            self._ref_count.value += 1
            return 0  # S_OK
        ppv[0] = c_void_p(0)
        return 0x80004002  # E_NOINTERFACE

    def _add_ref(self, this):
        self._ref_count.value += 1
        return self._ref_count.value

    def _release(self, this):
        self._ref_count.value -= 1
        return self._ref_count.value

    def _invoke(self, *args):
        raise NotImplementedError


# =====================================================================
# COM vtable accessor helpers
# =====================================================================
def _vtable(com_ptr):
    """获取 COM 对象的 vtable (c_void_p 数组的首地址)"""
    ptr = cast(com_ptr, POINTER(c_void_p))
    vtable_addr = ptr[0]
    return vtable_addr


def _call_com(com_ptr, vtable_index, restype, *argtypes_and_args):
    """
    调用 COM 接口方法。
    com_ptr: COM 对象指针
    vtable_index: vtable 中的方法索引 (0=QI, 1=AddRef, 2=Release, 3+= 接口方法)
    restype: 返回类型
    argtypes_and_args: (argtypes_tuple, args_tuple)
    """
    argtypes, args = argtypes_and_args
    vt_addr = cast(com_ptr, POINTER(c_void_p))[0]
    func_addr = cast(vt_addr, POINTER(c_void_p))[vtable_index]
    func_type = WINFUNCTYPE(restype, c_void_p, *argtypes)
    func = func_type(func_addr)
    return func(com_ptr, *args)


# =====================================================================
# ICoreWebView2Environment 方法 wrapper
# =====================================================================
class ICoreWebView2EnvironmentWrapper:
    def __init__(self, ptr):
        self.ptr = ptr

    def CreateCoreWebView2Controller(self, hwnd, handler_ptr):
        """vtable index 3: CreateCoreWebView2Controller(HWND, handler)"""
        return _call_com(
            self.ptr, 3, HRESULT,
            (wt.HWND, c_void_p), (hwnd, handler_ptr)
        )


# =====================================================================
# ICoreWebView2Controller 方法 wrapper
# =====================================================================
class ICoreWebView2ControllerWrapper:
    def __init__(self, ptr):
        self.ptr = ptr

    def get_CoreWebView2(self):
        """vtable index 7: get_CoreWebView2(ICoreWebView2**)"""
        out = c_void_p(0)
        hr = _call_com(self.ptr, 7, HRESULT, (POINTER(c_void_p),), (byref(out),))
        if hr != 0:
            raise OSError(f"get_CoreWebView2 failed: 0x{hr & 0xFFFFFFFF:08x}")
        return out

    def put_IsVisible(self, visible: bool):
        """vtable index 9"""
        _call_com(self.ptr, 9, HRESULT, (c_int,), (int(visible),))

    def put_Bounds(self, rect: RECT):
        """vtable index 10: put_Bounds(RECT)"""
        _call_com(self.ptr, 10, HRESULT,
                  (wt.LONG, wt.LONG, wt.LONG, wt.LONG),
                  (rect.left, rect.top, rect.right, rect.bottom))

    def NotifyParentWindowPositionChanged(self):
        """vtable index 13"""
        _call_com(self.ptr, 13, HRESULT, (), ())

    def MoveFocus(self, reason=1):
        """vtable index 12: MoveFocus(COREWEBVIEW2_MOVE_FOCUS_REASON)"""
        _call_com(self.ptr, 12, HRESULT, (c_int,), (reason,))

    def put_DefaultBackgroundColor(self, color: COREWEBVIEW2_COLOR):
        """
        ICoreWebView2Controller2::put_DefaultBackgroundColor (vtable index 22)
        Controller2 继承自 Controller, Controller 有 20 个方法 (index 3-22),
        Controller2 在其后追加: get_DefaultBackgroundColor(23), put_DefaultBackgroundColor(24)
        实际上, IUnknown(3) + Controller 自身方法(17个) = 20, Controller2 追加2个 = 22,23
        """
        # 先 QueryInterface 拿 Controller2
        controller2 = c_void_p(0)
        qi_func_type = WINFUNCTYPE(HRESULT, c_void_p, POINTER(GUID), POINTER(c_void_p))
        vt_addr = cast(self.ptr, POINTER(c_void_p))[0]
        qi_addr = cast(vt_addr, POINTER(c_void_p))[0]
        qi = qi_func_type(qi_addr)
        iid = IID_ICoreWebView2Controller2
        hr = qi(self.ptr, byref(iid), byref(controller2))
        if hr != 0:
            raise OSError(f"QueryInterface for Controller2 failed: 0x{hr & 0xFFFFFFFF:08x}")

        # ICoreWebView2Controller2 vtable:
        #   IUnknown: 0-2 (QI, AddRef, Release)
        #   ICoreWebView2Controller: 3-19 (17 methods)
        #   ICoreWebView2Controller2: 20=get_DefaultBackgroundColor, 21=put_DefaultBackgroundColor
        # 传递 COREWEBVIEW2_COLOR 作为按值参数 (4 bytes packed as uint32)
        color_val = (color.A | (color.R << 8) | (color.G << 16) | (color.B << 24))
        put_func_type = WINFUNCTYPE(HRESULT, c_void_p, ctypes.c_uint32)
        vt2_addr = cast(controller2, POINTER(c_void_p))[0]
        put_addr = cast(vt2_addr, POINTER(c_void_p))[21]
        put_func = put_func_type(put_addr)
        hr = put_func(controller2, color_val)
        if hr != 0:
            raise OSError(f"put_DefaultBackgroundColor failed: 0x{hr & 0xFFFFFFFF:08x}")


# =====================================================================
# ICoreWebView2 方法 wrapper
# =====================================================================
class ICoreWebView2Wrapper:
    def __init__(self, ptr):
        self.ptr = ptr

    def Navigate(self, url: str):
        """vtable index 5: Navigate(LPCWSTR)"""
        _call_com(self.ptr, 5, HRESULT, (c_wchar_p,), (url,))

    def AddScriptToExecuteOnDocumentCreated(self, script: str, handler_ptr):
        """vtable index 9: AddScriptToExecuteOnDocumentCreated(LPCWSTR, handler)"""
        _call_com(self.ptr, 9, HRESULT,
                  (c_wchar_p, c_void_p), (script, handler_ptr))

    def add_WebMessageReceived(self, handler_ptr):
        """vtable index 13: add_WebMessageReceived(handler, token*)"""
        token = ctypes.c_int64(0)
        _call_com(self.ptr, 13, HRESULT,
                  (c_void_p, POINTER(ctypes.c_int64)),
                  (handler_ptr, byref(token)))
        return token

    def ExecuteScript(self, script: str, handler_ptr=None):
        """vtable index 17: ExecuteScript(LPCWSTR, handler)"""
        _call_com(self.ptr, 17, HRESULT,
                  (c_wchar_p, c_void_p), (script, handler_ptr or c_void_p(0)))

    def PostWebMessageAsJson(self, json_str: str):
        """vtable index 19: PostWebMessageAsJson(LPCWSTR)"""
        _call_com(self.ptr, 19, HRESULT, (c_wchar_p,), (json_str,))


# =====================================================================
# WebMessageReceivedEventArgs wrapper
# =====================================================================
class WebMessageReceivedEventArgsWrapper:
    def __init__(self, ptr):
        self.ptr = ptr

    def TryGetWebMessageAsString(self) -> str:
        """vtable index 5: TryGetWebMessageAsString(LPWSTR*)"""
        out = c_wchar_p()
        _call_com(self.ptr, 5, HRESULT, (POINTER(c_wchar_p),), (byref(out),))
        result = out.value if out.value else ""
        # Free COM string
        if out:
            ctypes.windll.ole32.CoTaskMemFree(out)
        return result


# =====================================================================
# 回调接口实现
# =====================================================================
class EnvironmentCompletedHandler(_COMCallbackBase):
    """ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler"""
    _iid = IID_ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler
    _invoke_sig = WINFUNCTYPE(HRESULT, c_void_p, HRESULT, c_void_p)

    def __init__(self, callback):
        self._callback = callback
        super().__init__()

    def _invoke(self, this, error_code, environment):
        self._callback(error_code, environment)
        return 0


class ControllerCompletedHandler(_COMCallbackBase):
    """ICoreWebView2CreateCoreWebView2ControllerCompletedHandler"""
    _iid = IID_ICoreWebView2CreateCoreWebView2ControllerCompletedHandler
    _invoke_sig = WINFUNCTYPE(HRESULT, c_void_p, HRESULT, c_void_p)

    def __init__(self, callback):
        self._callback = callback
        super().__init__()

    def _invoke(self, this, error_code, controller):
        self._callback(error_code, controller)
        return 0


class WebMessageReceivedHandler(_COMCallbackBase):
    """ICoreWebView2WebMessageReceivedEventHandler"""
    _iid = IID_ICoreWebView2WebMessageReceivedEventHandler
    _invoke_sig = WINFUNCTYPE(HRESULT, c_void_p, c_void_p, c_void_p)

    def __init__(self, callback):
        self._callback = callback
        super().__init__()

    def _invoke(self, this, sender, args):
        self._callback(sender, args)
        return 0


class ScriptCompletedHandler(_COMCallbackBase):
    """ICoreWebView2AddScriptToExecuteOnDocumentCreatedCompletedHandler"""
    _iid = IID_ICoreWebView2AddScriptToExecuteOnDocumentCreatedCompletedHandler
    _invoke_sig = WINFUNCTYPE(HRESULT, c_void_p, HRESULT, c_wchar_p)

    def __init__(self, callback=None):
        self._callback = callback
        super().__init__()

    def _invoke(self, this, error_code, script_id):
        if self._callback:
            self._callback(error_code, script_id)
        return 0


# =====================================================================
# WebView2 管理器
# =====================================================================
class WebView2Manager:
    """
    管理 WebView2 的生命周期:
    1. 加载 WebView2Loader.dll
    2. 创建 Environment
    3. 创建 Controller (绑定到 HWND)
    4. 配置透明背景
    5. 注入 JS Bridge
    6. Navigate 到目标 URL
    """

    def __init__(self, hwnd, url, on_ready=None, on_message=None):
        self.hwnd = hwnd
        self.url = url
        self.on_ready = on_ready  # callback(webview2_manager)
        self.on_message = on_message  # callback(message_dict)

        self.environment = None  # ICoreWebView2EnvironmentWrapper
        self.controller = None  # ICoreWebView2ControllerWrapper
        self.webview = None  # ICoreWebView2Wrapper

        self._handlers = []  # prevent GC

        # 设置环境变量避免白色闪烁
        os.environ["WEBVIEW2_DEFAULT_BACKGROUND_COLOR"] = "00000000"

        self._load_and_create()

    def _find_loader_dll(self) -> str:
        """查找 WebView2Loader.dll"""
        candidates = [
            os.path.join(os.getcwd(), "bin", "WebView2Loader.dll"),
            os.path.join(os.path.dirname(__file__), "..", "..", "bin", "WebView2Loader.dll"),
        ]
        for path in candidates:
            path = os.path.abspath(path)
            if os.path.isfile(path):
                return path
        raise FileNotFoundError(
            "WebView2Loader.dll not found. Place it in the bin/ directory."
        )

    def _load_and_create(self):
        """加载 DLL 并创建 WebView2 Environment"""
        dll_path = self._find_loader_dll()
        loader = ctypes.windll.LoadLibrary(dll_path)

        # STDAPI CreateCoreWebView2EnvironmentWithOptions(
        #   PCWSTR browserExecutableFolder,
        #   PCWSTR userDataFolder,
        #   ICoreWebView2EnvironmentOptions* options,
        #   ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler* handler)
        create_env = loader.CreateCoreWebView2EnvironmentWithOptions
        create_env.restype = HRESULT
        create_env.argtypes = [c_wchar_p, c_wchar_p, c_void_p, c_void_p]

        handler = EnvironmentCompletedHandler(self._on_environment_created)
        self._handlers.append(handler)

        # userDataFolder 放在 .cache/webview2
        user_data = os.path.join(os.getcwd(), ".cache", "webview2")
        os.makedirs(user_data, exist_ok=True)

        hr = create_env(None, user_data, None, handler.ptr)
        if hr != 0:
            raise OSError(f"CreateCoreWebView2EnvironmentWithOptions failed: 0x{hr & 0xFFFFFFFF:08x}")

    def _on_environment_created(self, error_code, env_ptr):
        if error_code != 0:
            raise OSError(f"Environment creation failed: 0x{error_code & 0xFFFFFFFF:08x}")

        self.environment = ICoreWebView2EnvironmentWrapper(env_ptr)

        handler = ControllerCompletedHandler(self._on_controller_created)
        self._handlers.append(handler)

        self.environment.CreateCoreWebView2Controller(self.hwnd, handler.ptr)

    def _on_controller_created(self, error_code, ctrl_ptr):
        if error_code != 0:
            raise OSError(f"Controller creation failed: 0x{error_code & 0xFFFFFFFF:08x}")

        self.controller = ICoreWebView2ControllerWrapper(ctrl_ptr)

        # 设置透明背景
        transparent = COREWEBVIEW2_COLOR(A=0, R=0, G=0, B=0)
        try:
            self.controller.put_DefaultBackgroundColor(transparent)
        except OSError:
            pass  # 如果失败则跳过（可能 Runtime 版本过旧）

        # 获取 ICoreWebView2
        wv_ptr = self.controller.get_CoreWebView2()
        self.webview = ICoreWebView2Wrapper(wv_ptr)

        # 注册 WebMessage 回调
        if self.on_message:
            msg_handler = WebMessageReceivedHandler(self._on_web_message)
            self._handlers.append(msg_handler)
            self.webview.add_WebMessageReceived(msg_handler.ptr)

        # 设置初始 Bounds
        self.resize_to_window()

        # 显示 WebView
        self.controller.put_IsVisible(True)

        # 通知就绪
        if self.on_ready:
            self.on_ready(self)

        # 导航到目标 URL
        self.webview.Navigate(self.url)

    def _on_web_message(self, sender, args_ptr):
        """处理从 JS 发来的 postMessage"""
        if not self.on_message:
            return
        try:
            args = WebMessageReceivedEventArgsWrapper(args_ptr)
            msg_str = args.TryGetWebMessageAsString()
            if msg_str:
                msg = json.loads(msg_str)
                self.on_message(msg)
        except Exception:
            pass

    def inject_script(self, script: str):
        """注入 JS 到所有后续加载的文档"""
        if not self.webview:
            return
        handler = ScriptCompletedHandler()
        self._handlers.append(handler)
        self.webview.AddScriptToExecuteOnDocumentCreated(script, handler.ptr)

    def execute_script(self, script: str):
        """在当前页面执行 JS"""
        if not self.webview:
            return
        self.webview.ExecuteScript(script)

    def post_message(self, data: dict):
        """向 JS 发送消息"""
        if not self.webview:
            return
        self.webview.PostWebMessageAsJson(json.dumps(data))

    def navigate(self, url: str):
        if self.webview:
            self.webview.Navigate(url)

    def resize_to_window(self):
        """将 WebView Bounds 设置为父窗口的客户区大小"""
        if not self.controller:
            return
        rect = RECT()
        ctypes.windll.user32.GetClientRect(self.hwnd, byref(rect))
        self.controller.put_Bounds(rect)

    def notify_parent_moved(self):
        if self.controller:
            self.controller.NotifyParentWindowPositionChanged()
