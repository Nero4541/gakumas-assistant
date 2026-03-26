"""
Win32 / COM / WebView2 常量、结构体、GUID 定义
仅依赖 Python 标准库 ctypes
"""
import ctypes
import ctypes.wintypes as wt
from ctypes import Structure, c_int, c_uint, c_void_p, c_ubyte, POINTER, WINFUNCTYPE

# ---------------------------------------------------------------------------
# Win32 窗口样式
# ---------------------------------------------------------------------------
WS_OVERLAPPED = 0x00000000
WS_POPUP = 0x80000000
WS_CHILD = 0x40000000
WS_MINIMIZE = 0x20000000
WS_VISIBLE = 0x10000000
WS_MAXIMIZEBOX = 0x00010000
WS_MINIMIZEBOX = 0x00020000
WS_SYSMENU = 0x00080000
WS_THICKFRAME = 0x00040000
WS_CAPTION = 0x00C00000
WS_CLIPCHILDREN = 0x02000000

WS_EX_APPWINDOW = 0x00040000
WS_EX_NOREDIRECTIONBITMAP = 0x00200000

# 无边框 + 可缩放 + 最小化/最大化/关闭
FRAMELESS_STYLE = (WS_POPUP | WS_THICKFRAME | WS_MINIMIZEBOX
                   | WS_MAXIMIZEBOX | WS_SYSMENU | WS_CLIPCHILDREN)

# ---------------------------------------------------------------------------
# Win32 消息
# ---------------------------------------------------------------------------
WM_CREATE = 0x0001
WM_DESTROY = 0x0002
WM_MOVE = 0x0003
WM_SIZE = 0x0005
WM_ACTIVATE = 0x0006
WM_SETFOCUS = 0x0007
WM_CLOSE = 0x0010
WM_PAINT = 0x000F
WM_ERASEBKGND = 0x0014
WM_NCCALCSIZE = 0x0083
WM_NCHITTEST = 0x0084
WM_NCLBUTTONDOWN = 0x00A1
WM_GETMINMAXINFO = 0x0024
WM_DPICHANGED = 0x02E0
WM_USER = 0x0400

# WM_NCHITTEST 返回值
HTCLIENT = 1
HTCAPTION = 2
HTLEFT = 10
HTRIGHT = 11
HTTOP = 12
HTTOPLEFT = 13
HTTOPRIGHT = 14
HTBOTTOM = 15
HTBOTTOMLEFT = 16
HTBOTTOMRIGHT = 17

# ShowWindow 参数
SW_HIDE = 0
SW_NORMAL = 1
SW_SHOWMINIMIZED = 2
SW_SHOWMAXIMIZED = 3
SW_MAXIMIZE = 3
SW_SHOWNOACTIVATE = 4
SW_SHOW = 5
SW_MINIMIZE = 6
SW_RESTORE = 9

# ---------------------------------------------------------------------------
# Windows DPI awareness
# ---------------------------------------------------------------------------
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)

# ---------------------------------------------------------------------------
# DWM 相关
# ---------------------------------------------------------------------------
class MARGINS(Structure):
    _fields_ = [
        ("cxLeftWidth", c_int),
        ("cxRightWidth", c_int),
        ("cyTopHeight", c_int),
        ("cyBottomHeight", c_int),
    ]

# ---------------------------------------------------------------------------
# Win32 结构体
# ---------------------------------------------------------------------------
class POINT(Structure):
    _fields_ = [("x", wt.LONG), ("y", wt.LONG)]

class RECT(Structure):
    _fields_ = [
        ("left", wt.LONG),
        ("top", wt.LONG),
        ("right", wt.LONG),
        ("bottom", wt.LONG),
    ]

class MSG(Structure):
    _fields_ = [
        ("hwnd", wt.HWND),
        ("message", wt.UINT),
        ("wParam", wt.WPARAM),
        ("lParam", wt.LPARAM),
        ("time", wt.DWORD),
        ("pt", POINT),
    ]

class MINMAXINFO(Structure):
    _fields_ = [
        ("ptReserved", POINT),
        ("ptMaxSize", POINT),
        ("ptMaxPosition", POINT),
        ("ptMinTrackSize", POINT),
        ("ptMaxTrackSize", POINT),
    ]

class NCCALCSIZE_PARAMS(Structure):
    _fields_ = [
        ("rgrc", RECT * 3),
    ]

WNDPROC = WINFUNCTYPE(ctypes.c_long, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)

class WNDCLASSEXW(Structure):
    _fields_ = [
        ("cbSize", wt.UINT),
        ("style", wt.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", c_int),
        ("cbWndExtra", c_int),
        ("hInstance", wt.HINSTANCE),
        ("hIcon", wt.HICON),
        ("hCursor", wt.HANDLE),
        ("hbrBackground", wt.HBRUSH),
        ("lpszMenuName", wt.LPCWSTR),
        ("lpszClassName", wt.LPCWSTR),
        ("hIconSm", wt.HICON),
    ]

# ---------------------------------------------------------------------------
# WebView2 COREWEBVIEW2_COLOR
# ---------------------------------------------------------------------------
class COREWEBVIEW2_COLOR(Structure):
    _fields_ = [
        ("A", c_ubyte),
        ("R", c_ubyte),
        ("G", c_ubyte),
        ("B", c_ubyte),
    ]

# ---------------------------------------------------------------------------
# COM GUID helper
# ---------------------------------------------------------------------------
class GUID(Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]

def _make_guid(s: str) -> GUID:
    """从标准 GUID 字符串创建 GUID 结构体, e.g. '6C4819F3-...'"""
    import uuid
    u = uuid.UUID(s)
    b = u.bytes_le
    return GUID(
        int.from_bytes(b[0:4], 'little'),
        int.from_bytes(b[4:6], 'little'),
        int.from_bytes(b[6:8], 'little'),
        (ctypes.c_ubyte * 8)(*b[8:16]),
    )

# ---------------------------------------------------------------------------
# WebView2 COM Interface IIDs
# ---------------------------------------------------------------------------
# ICoreWebView2Environment
IID_ICoreWebView2Environment = _make_guid("b96d755e-0319-4e92-a296-23436f46a1fc")

# ICoreWebView2Controller
IID_ICoreWebView2Controller = _make_guid("4d00c0d1-9434-4eb6-8078-8697a560334f")

# ICoreWebView2Controller2 (has DefaultBackgroundColor)
IID_ICoreWebView2Controller2 = _make_guid("c979903e-d4ca-4228-92eb-47ee3fa96eab")

# ICoreWebView2
IID_ICoreWebView2 = _make_guid("76eceacb-0462-4d94-ac83-423a6793775e")

# ICoreWebView2_2 (has add_WebMessageReceived with improved signature)
IID_ICoreWebView2_2 = _make_guid("9E8F0CF8-E670-4B5E-B2BC-73E061E3184C")

# 回调接口 IIDs
# ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler
IID_ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler = _make_guid(
    "4e8a3389-c9d8-4bd2-b6b5-124fee6cc14d"
)

# ICoreWebView2CreateCoreWebView2ControllerCompletedHandler
IID_ICoreWebView2CreateCoreWebView2ControllerCompletedHandler = _make_guid(
    "6c4819f3-c9b7-4260-8127-c9f5bde7f68c"
)

# ICoreWebView2WebMessageReceivedEventHandler
IID_ICoreWebView2WebMessageReceivedEventHandler = _make_guid(
    "57213f19-00e6-49fa-8e07-898ea01ecbd2"
)

# ICoreWebView2WebMessageReceivedEventArgs
IID_ICoreWebView2WebMessageReceivedEventArgs = _make_guid(
    "0f99a40c-e962-4207-9e92-e3d542eff849"
)

# ICoreWebView2AddScriptToExecuteOnDocumentCreatedCompletedHandler
IID_ICoreWebView2AddScriptToExecuteOnDocumentCreatedCompletedHandler = _make_guid(
    "b99571a0-9b4c-4c1d-a5e5-12e5a98fc2d0"
)

# ICoreWebView2NavigationCompletedEventHandler
IID_ICoreWebView2NavigationCompletedEventHandler = _make_guid(
    "d33a35bf-1c49-4f98-93ab-006e0533fe1c"
)

# IUnknown
IID_IUnknown = _make_guid("00000000-0000-0000-C000-000000000046")

# ---------------------------------------------------------------------------
# GDI / Misc
# ---------------------------------------------------------------------------
CS_HREDRAW = 0x0002
CS_VREDRAW = 0x0001
COLOR_WINDOW = 5
CW_USEDEFAULT = 0x80000000

IMAGE_ICON = 1
LR_LOADFROMFILE = 0x00000010
LR_DEFAULTSIZE = 0x00000040

GWL_STYLE = -16

WM_APP_WEBVIEW_READY = WM_USER + 100  # 自定义消息: WebView2 初始化完成
