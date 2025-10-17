class ADBConnectMode:
    USB = "USB"
    NETWORK = "Network"

class ADBOperation:
    class ScrollDirection:
        """
        屏幕滚动方向
        """
        VERTICAL = "VERTICAL"      # 上下组合
        HORIZONTAL = "HORIZONTAL"    # 左右组合

    class ScreenCaptureService:
        """
        屏幕截图服务
        """
        ADB = "ADB"
        uiautomator2 = "uiautomator2"
        aScreenCap = "aScreenCap"
        DroidCast = "DroidCast"

    class TouchService:
        """
        点击服务
        """
        ADB = "ADB"
        uiautomator2 = "uiautomator2"
