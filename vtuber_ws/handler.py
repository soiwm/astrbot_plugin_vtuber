"""
WebSocket 消息处理器
从 Open-LLM-VTuber 移植并简化
"""

import asyncio
import json
import logging
from collections.abc import Callable
from enum import Enum

from ..core.service_context import ServiceContext

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """WebSocket 消息类型枚举"""

    CONTROL = ["interrupt-signal", "ping"]
    CONVERSATION = ["text-input"]


class WebSocketHandler:
    """处理 WebSocket 连接和消息路由"""

    def __init__(self, default_context: ServiceContext):
        """初始化 WebSocket 处理器"""
        self.client_connections: dict[str, Callable] = {}
        self.client_contexts: dict[str, ServiceContext] = {}
        self.current_conversation_tasks: dict[str, asyncio.Task | None] = {}
        self.default_context = default_context
        self._message_handlers = self._init_message_handlers()
        self.on_text_input: Callable | None = None

    def _init_message_handlers(self) -> dict[str, Callable]:
        """初始化消息类型到处理器的映射"""
        return {
            "interrupt-signal": self._handle_interrupt,
            "text-input": self._handle_text_input,
            "ping": self._handle_heartbeat,
        }

    async def handle_new_connection(self, send_func: Callable, client_uid: str) -> None:
        """
        处理新的 WebSocket 连接设置

        参数:
            send_func: 发送文本的函数
            client_uid: 客户端唯一标识符
        """
        try:
            session_context = await self._init_service_context(send_func, client_uid)

            self.client_connections[client_uid] = send_func
            self.client_contexts[client_uid] = session_context

            await self._send_initial_messages(send_func, client_uid, session_context)

            logger.info(f"Connection established for client {client_uid}")

        except Exception as e:
            logger.error(
                f"Failed to initialize connection for client {client_uid}: {e}"
            )
            raise

    async def _send_initial_messages(
        self, send_func: Callable, client_uid: str, context: ServiceContext
    ):
        """发送初始连接消息到客户端"""
        await send_func(
            json.dumps({"type": "full-text", "text": "Connection established"})
        )

        await send_func(
            json.dumps(
                {
                    "type": "set-model-and-conf",
                    "model_info": context.live2d_model.model_info,
                    "conf_name": context.character_config.conf_name,
                    "conf_uid": context.character_config.conf_uid,
                    "client_uid": client_uid,
                }
            )
        )

    async def _init_service_context(
        self, send_func: Callable, client_uid: str
    ) -> ServiceContext:
        """通过克隆默认上下文为新会话初始化服务上下文"""
        context = ServiceContext()
        await context.load_cache(
            live2d_model=self.default_context.live2d_model,
            tts_engine=self.default_context.tts_engine,
            send_text=send_func,
            client_uid=client_uid,
        )
        return context

    async def handle_message(self, client_uid: str, data: dict) -> None:
        """
        处理 WebSocket 消息

        参数:
            client_uid: 客户端标识符
            data: 消息数据
        """
        msg_type = data.get("type")
        if not msg_type:
            logger.warning("Message received without type")
            return

        handler = self._message_handlers.get(msg_type)
        if handler:
            await handler(client_uid, data)
        else:
            logger.warning(f"Unknown message type: {msg_type}")

    async def _handle_interrupt(self, client_uid: str, data: dict) -> None:
        """处理对话中断"""
        logger.info(f"Interrupt signal received from {client_uid}")
        if client_uid in self.current_conversation_tasks:
            task = self.current_conversation_tasks[client_uid]
            if task and not task.done():
                task.cancel()

        if client_uid in self.client_contexts:
            self.client_contexts[client_uid].tts_manager.clear()

    async def _handle_text_input(self, client_uid: str, data: dict) -> None:
        """处理文本输入"""
        text = data.get("text", "")
        logger.info(f"Text input from {client_uid}: {text[:50]}...")

        if self.on_text_input:
            await self.on_text_input(client_uid, text)

    async def _handle_heartbeat(self, client_uid: str, data: dict) -> None:
        """处理心跳消息"""
        if client_uid in self.client_connections:
            try:
                await self.client_connections[client_uid](
                    json.dumps({"type": "heartbeat-ack"})
                )
            except Exception as e:
                logger.error(f"Error sending heartbeat ack: {e}")

    async def handle_disconnect(self, client_uid: str) -> None:
        """处理客户端断开连接"""
        if client_uid in self.current_conversation_tasks:
            task = self.current_conversation_tasks[client_uid]
            if task and not task.done():
                task.cancel()
            self.current_conversation_tasks.pop(client_uid, None)

        if client_uid in self.client_contexts:
            await self.client_contexts[client_uid].close()
            self.client_contexts.pop(client_uid, None)

        self.client_connections.pop(client_uid, None)
        logger.info(f"Client {client_uid} disconnected")

    def get_context(self, client_uid: str) -> ServiceContext | None:
        """获取客户端的服务上下文"""
        return self.client_contexts.get(client_uid)
