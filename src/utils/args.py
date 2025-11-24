import argparse

parser = argparse.ArgumentParser(description="Command line interface for gakumas")
parser.add_argument('--not_use_webview', help='不使用WebView', action="store_true", default=False)
parser.add_argument('--host', type=str, help='服务器绑定地址，默认为localhost',default="localhost")
parser.add_argument('--port', type=int, help='服务器绑定端口，默认为8000',default=8000)
parser.add_argument('--http_server_info', help='启用Http服务器日志', action="store_true", default=False)
args = parser.parse_args()