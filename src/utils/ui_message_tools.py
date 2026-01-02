from src.constants.websocket_actions import WebsocketActions
from src.core.web.websocket import WebSocketManager
from src.entity.WebSocketData import WebSocketData

websocket = WebSocketManager()

class UIMessage:

    @staticmethod
    def _send(action, msg, timeout):
        websocket.broadcast_action_sync(
            action,
            WebSocketData(message={
                "message": msg,
                "close_delay": timeout,
            })
        )

    def info(self, msg, timeout=3):
        self._send(WebsocketActions.Message.ShowMessage_Info, msg, timeout)

    def warning(self, msg, timeout=3):
        self._send(WebsocketActions.Message.ShowMessage_Warning, msg, timeout)

    def error(self, msg, timeout=3):
        self._send(WebsocketActions.Message.ShowMessage_Error, msg, timeout)

    def success(self, msg, timeout=3):
        self._send(WebsocketActions.Message.ShowMessage_Success, msg, timeout)
