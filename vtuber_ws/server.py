"""
WebSocket 服务器
从 Open-LLM-VTuber 移植并简化为 AstrBot 适配版本
"""

import asyncio
import json
import logging
import uuid

from ..core.service_context import ServiceContext
from .handler import WebSocketHandler

logger = logging.getLogger(__name__)


class SimpleWebSocket:
    """简化的 WebSocket 连接包装器"""

    def __init__(self, send_func=None, receive_func=None):
        self.send_func = send_func
        self.receive_func = receive_func
        self._closed = False

    async def send_text(self, text: str):
        """发送文本消息"""
        if self.send_func:
            await self.send_func(text)

    async def receive_json(self):
        """接收 JSON 消息"""
        if self.receive_func:
            data = await self.receive_func()
            if isinstance(data, str):
                return json.loads(data)
            return data
        raise NotImplementedError("receive_func not set")

    async def accept(self):
        """接受连接"""
        pass

    async def close(self):
        """关闭连接"""
        self._closed = True


class VTuberWebSocketServer:
    """
    VTuber WebSocket 服务器 - 管理与前端的连接
    兼容 Open-LLM-VTuber-Web 前端协议
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 6191,
        service_context: ServiceContext = None,
    ):
        """
        初始化 WebSocket 服务器

        参数:
            host: 监听地址
            port: 监听端口
            service_context: 服务上下文
        """
        self.host = host
        self.port = port
        self.service_context = service_context or ServiceContext()
        self.websocket_handler = WebSocketHandler(self.service_context)
        self._server_task: asyncio.Task | None = None
        self._running = False
        self._connections = {}
        self.on_message = None
        self.on_ai_response = None

    async def start(self):
        """启动 WebSocket 服务器（使用内部服务器）"""
        self._running = True
        logger.info(f"VTuber WebSocket Server starting on {self.host}:{self.port}")
        # 实际的服务器启动由插件主类中的 FastAPI 处理
        # 这里只是设置状态

    async def stop(self):
        """停止 WebSocket 服务器"""
        self._running = False

        # 主动关闭所有连接
        for client_uid, websocket in list(self._connections.items()):
            try:
                await websocket.close()
            except Exception as e:
                logger.debug(f"Error closing connection {client_uid}: {e}")
        self._connections.clear()

        # 取消服务器任务（带超时）
        if self._server_task:
            self._server_task.cancel()
            try:
                await asyncio.wait_for(self._server_task, timeout=2.0)
            except asyncio.CancelledError:
                pass
            except asyncio.TimeoutError:
                logger.warning("Server task timeout during shutdown")
            except Exception as e:
                logger.debug(f"Error stopping server task: {e}")

        logger.info("VTuber WebSocket Server stopped")

    async def handle_client(self, websocket):
        """
        处理客户端连接

        参数:
            websocket: WebSocket 连接对象
        """
        client_uid = str(uuid.uuid4())
        logger.info(f"New client connected: {client_uid}")

        try:
            await websocket.accept()

            async def send_func(text: str):
                await websocket.send_text(text)

            await self.websocket_handler.handle_new_connection(send_func, client_uid)
            self._connections[client_uid] = websocket

            while self._running:
                try:
                    data = await websocket.receive_json()
                    await self.websocket_handler.handle_message(client_uid, data)

                    # 回调通知有新消息
                    if self.on_message:
                        await self.on_message(client_uid, data)

                except Exception as e:
                    logger.error(f"Error handling message from {client_uid}: {e}")
                    break

        except Exception as e:
            logger.error(f"Client connection error: {e}")
        finally:
            await self.websocket_handler.handle_disconnect(client_uid)
            if client_uid in self._connections:
                del self._connections[client_uid]
            logger.info(f"Client disconnected: {client_uid}")

    async def send_ai_response(
        self,
        client_uid: str,
        text: str,
        expressions: list = None,
        audio_path: str = None,
    ):
        """
        发送 AI 响应到前端

        参数:
            client_uid: 客户端 ID
            text: 响应文本
            expressions: 表情列表
            audio_path: 音频文件路径
        """
        context = self.websocket_handler.get_context(client_uid)
        if not context:
            logger.warning(f"Context not found for client {client_uid}")
            return

        from ..agent.output_types import Actions, DisplayText
        from ..utils.stream_audio import prepare_audio_payload

        display_text = DisplayText(text=text)
        actions = Actions(expressions=expressions or [])

        if audio_path:
            payload = prepare_audio_payload(
                audio_path=audio_path,
                display_text=display_text,
                actions=actions,
            )
        else:
            payload = prepare_audio_payload(
                audio_path=None,
                display_text=display_text,
                actions=actions,
            )

        if client_uid in self._connections:
            try:
                await self._connections[client_uid].send_text(json.dumps(payload))
            except Exception as e:
                logger.error(f"Failed to send AI response: {e}")

    async def broadcast_text(
        self, text: str, expressions: list = None, audio_path: str = None
    ):
        """
        向所有连接的客户端广播消息

        参数:
            text: 要广播的文本
            expressions: 表情列表
            audio_path: 音频文件路径
        """
        for client_uid in list(self._connections.keys()):
            await self.send_ai_response(client_uid, text, expressions, audio_path)

    def get_service_context(self) -> ServiceContext:
        """获取服务上下文"""
        return self.service_context

    def set_on_message_callback(self, callback):
        """设置消息回调"""
        self.on_message = callback
        self.websocket_handler.on_text_input = callback
