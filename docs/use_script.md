# Gakumas Assistant使用手册

## 安装前的碎碎念
### 是否支持汉化版
当前版本暂未支持

### 是否支持DMM版本
当前版本主要为DMM版本开发，手机适配上可能会出现问题

### 是否支持手机？只能电脑用吗？
暂时无移植到手机上的计划，实时图像推理对性能的需求会比较高

### 是否支持非标分辨率
按理来说是支持的，在程序设计时就采用的是全目标识别的架构

## 下载和安装
### 系统要求
在开始安装 Gakumas Assistant 之前：  
如果你打算在安卓模拟器上使用 Gakumas Assistant，先检查模拟器是否满足这些设置要求：  
- 系统版本：Android 10+  
- 支持Google Play
- 能正常使用ADB
- 已开启游戏加速器或代理且网络通畅  
> 如果是使用安卓设备+有线ADB运行 Gakumas Assistant，则需关闭ADB安全设置(否则无法获取屏幕或无法点击)

如果是打算在PC(DMM)上使用 Gakumas Assistant，请保证系统环境有剩余的性能完成实时图像推理  
> DMM模式下Gakumas Assistant会自动申请管理员权限用于屏幕点击  

此外，**必须关闭汉化插件**，当前版本仍未支持汉化版本。

### 可能需要修改的脚本运行设置
在开始使用Gakumas Assistant前，你可能需要更改部分静态设置项，这些设置项无法在脚本设置页面更改  
这些设置项在**config.py**中
```python
from src.constants.yolo.model_type import YoloModelType

# Web服务器监听地址
web_server_host: str = "127.0.0.1"
# Web服务器监听端口
web_server_port: int = 8000
# 是否自动打开浏览器
auto_open_web_browser: bool = False
# 是否自动重载服务器
auto_reload_server: bool = False
# 是否启用Debug模式
debug: bool = True

# 【勿动】定义Yolo模型路径
model_config = {
    YoloModelType.BASE_UI: "model/base_ui.onnx",
    YoloModelType.PRODUCER: "model/producer.onnx"
}
```