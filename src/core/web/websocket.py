import asyncio
import json
from typing import Optional

from starlette.websockets import WebSocket

from src.constants.websocket_actions import WebsocketActions
from src.entity.Base import SingletonMeta
from src.entity.WebSocketData import WebSocketData
from src.utils.json_encoder import ComplexEncoder
from src.utils.logger import logger


class WebSocketManager(metaclass=SingletonMeta):
    _active_connections: list[WebSocket]
    _loop: asyncio.AbstractEventLoop
    _init: bool = False

    def __init__(self):
        if self._init:
            return
        self.active_connections: list[WebSocket] = []
        self._loop = asyncio.get_event_loop()  # 事件循环
        self._init = True
        logger.add(sink=self._broadcast_log)

    def _broadcast_log(self, message):
        record = message.record
        data = WebSocketData(message={
            "time": record["time"],
            "level": record["level"].name,
            "message": record.get("message"),
        })
        self.broadcast_action_sync(WebsocketActions.Logger.BroadcastLog, data)

    def set_fastapi_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    async def connect(self, websocket: WebSocket):
        """接收新的 WebSocket 连接并接受消息"""
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        """移除 WebSocket 连接"""
        self.active_connections.remove(websocket)

    @staticmethod
    async def send_message(data: WebSocketData, websocket: WebSocket):
        """向特定 WebSocket 发送消息"""
        if msg := data.message:
            await websocket.send_text(json.dumps(msg, cls=ComplexEncoder))
        if data := data.data:
            await websocket.send_bytes(data)

    async def broadcast(self, data: WebSocketData):
        """向所有 WebSocket 连接发送消息"""
        for connection in self.active_connections:
            await self.send_message(data, connection)

    def send_message_sync(self, data: WebSocketData, websocket: WebSocket):
        """供后台线程调用的同步方法，发送消息"""
        asyncio.run_coroutine_threadsafe(self.send_message(data, websocket), self._loop)

    def broadcast_sync(self, data: WebSocketData):
        """供后台线程调用的同步方法，广播消息"""
        asyncio.run_coroutine_threadsafe(self.broadcast(data), self._loop)

    async def send_action(self, websocket: WebSocket, action: str, data: Optional[WebSocketData] = None):
        """发送动作数据到指定客户端"""
        await self.send_message(WebSocketData(message={
            "action": WebsocketActions.BaseActionFlag+":"+action,
            "data": {} if data is None else data.message
        }), websocket)

    def send_action_sync(self, websocket: WebSocket, action: str, data: Optional[WebSocketData] = None):
        """发送动作数据到指定客户端"""
        self.send_message_sync(WebSocketData(message={
            "action": WebsocketActions.BaseActionFlag+":"+action,
            "data": {} if data is None else data.message
        }), websocket)

    def broadcast_action_sync(self, action: str, data: Optional[WebSocketData] = None):
        """
        广播动作数据给所有客户端
        :param action: 动作名
        :param data: 数据
        """
        self.broadcast_sync(WebSocketData(message={
            "action": WebsocketActions.BaseActionFlag+":"+action,
            "data": {} if data is None else data.message
        }))
