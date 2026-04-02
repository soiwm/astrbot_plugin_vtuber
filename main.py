"""
AstrBot VTuber 插件主类
完全模仿 astrbot_plugin_desktop_assistant 的平台适配器模式
"""

import asyncio
import base64
import json
import os
import time
import traceback
import uuid
from pathlib import Path
from typing import Optional

import aiohttp
from aiohttp import web

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Plain
from astrbot.api.star import Context, Star
from astrbot.core import db_helper
from astrbot.core.message.components import Record
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
)
from astrbot.core.platform.astr_message_event import MessageSesion
from astrbot.core.platform.register import (
    platform_cls_map,
    platform_registry,
    register_platform_adapter,
)

from .utils.emotion_analyzer import EmotionAnalyzer


def _message_chain_to_text(message) -> str:
    """将消息链转换为纯文本"""
    if message is None:
        return ""
    if isinstance(message, str):
        return message.strip()
    if isinstance(message, (bytes, bytearray)):
        try:
            return message.decode("utf-8", errors="ignore").strip()
        except Exception:
            return ""
    chain = getattr(message, "chain", None)
    if chain:
        parts = []
        for comp in chain:
            if isinstance(comp, Plain):
                parts.append(comp.text)
            elif hasattr(comp, "text") and comp.text:
                parts.append(str(comp.text))
        result = "".join(parts).strip()
        if result:
            return result
    if hasattr(message, "get_plain_text"):
        try:
            result = message.get_plain_text()
            if isinstance(result, str) and result:
                return result.strip()
        except Exception:
            pass
    return ""


class VTuberMessageEvent(AstrMessageEvent):
    """VTuber 平台的消息事件"""

    _emotion_analyzer: EmotionAnalyzer | None = None

    def __init__(
        self,
        message_str: str,
        message_obj: AstrBotMessage,
        platform_meta: PlatformMetadata,
        session_id: str,
        ws_client: web.WebSocketResponse,
        emotion_map: dict = None,
        context=None,
    ) -> None:
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.ws_client = ws_client
        self._response_text = ""
        self._user_message_stored = False
        self._emotion_map = emotion_map or {}
        self._streaming_completed = False
        self._context = context

        if VTuberMessageEvent._emotion_analyzer is None and context:
            VTuberMessageEvent._emotion_analyzer = EmotionAnalyzer(context=context)

    async def _store_user_message(self):
        """存储用户消息到 PlatformMessageHistory"""
        if self._user_message_stored:
            return
        self._user_message_stored = True
        try:
            await db_helper.insert_platform_message_history(
                platform_id="vtuber",
                user_id=self.session_id,
                content={
                    "type": "user",
                    "message": [{"type": "text", "text": self.message_str}],
                },
                sender_id=self.message_obj.sender.user_id
                if self.message_obj.sender
                else "vtuber_user",
                sender_name=self.message_obj.sender.nickname
                if self.message_obj.sender
                else "VTuber User",
            )
        except Exception as e:
            logger.error(f"Error storing user message to history: {e}")

    async def _store_bot_message(self, text: str):
        """存储机器人消息到 PlatformMessageHistory"""
        try:
            await db_helper.insert_platform_message_history(
                platform_id="vtuber",
                user_id=self.session_id,
                content={"type": "bot", "message": [{"type": "text", "text": text}]},
                sender_id="bot",
                sender_name="bot",
            )
        except Exception as e:
            logger.error(f"Error storing bot message to history: {e}")

    def _get_expression_from_emotion(self, emotion: str) -> int | None:
        """Map emotion to expression index using emotionMap"""
        if not self._emotion_map:
            return None
        return self._emotion_map.get(emotion.lower())

    async def _analyze_and_get_expressions(
        self, user_message: str, ai_response: str
    ) -> list[int]:
        """Analyze emotions and return expression indices"""
        if not self._emotion_analyzer:
            return []

        try:
            scores = await self._emotion_analyzer.analyze(user_message, ai_response)
            dominant = self._emotion_analyzer.get_dominant_emotion(scores)
            expression_idx = self._get_expression_from_emotion(dominant)

            if expression_idx is not None:
                logger.info(
                    f"Emotion analysis: {dominant} -> expression {expression_idx}"
                )
                return [expression_idx]

        except Exception as e:
            logger.error(f"Emotion analysis failed: {e}")

        return []

    async def send(self, message: MessageChain | None) -> None:
        if message is None:
            return

        audio_base64 = await self._extract_audio_from_message(message)

        if self._streaming_completed:
            if audio_base64:
                logger.info(
                    f"Sending audio only (streaming completed), length: {len(audio_base64)}"
                )
                try:
                    payload = {
                        "type": "audio-only",
                        "audio": audio_base64,
                    }
                    await self.ws_client.send_json(payload)
                except Exception as e:
                    logger.error(f"Error sending audio to WebSocket client: {e}")
            return

        self._streaming_completed = True

        await self._store_user_message()

        text = _message_chain_to_text(message)
        if text:
            self._response_text = text
            await self._store_bot_message(text)

            expressions = await self._analyze_and_get_expressions(
                self.message_str, text
            )

            try:
                payload = {"type": "full-text", "text": text, "name": "AI"}
                if expressions:
                    payload["expressions"] = expressions
                if audio_base64:
                    payload["audio"] = audio_base64
                    logger.info(
                        f"Sending audio with message, length: {len(audio_base64)}"
                    )
                await self.ws_client.send_json(payload)
            except Exception as e:
                logger.error(f"Error sending to WebSocket client: {e}")

    async def _extract_audio_from_message(self, message: MessageChain) -> str | None:
        """Extract audio from Record component and return as Base64"""
        if not message or not hasattr(message, "chain"):
            return None

        for comp in message.chain:
            if isinstance(comp, Record):
                try:
                    audio_path = comp.file
                    if not audio_path:
                        continue

                    if audio_path.startswith("http://") or audio_path.startswith(
                        "https://"
                    ):
                        audio_base64 = await self._download_audio_as_base64(audio_path)
                        if audio_base64:
                            return audio_base64
                    elif audio_path.startswith("file:///"):
                        local_path = audio_path[8:]
                        return self._read_audio_file_as_base64(local_path)
                    elif audio_path.startswith("base64://"):
                        return audio_path[9:]
                    else:
                        return self._read_audio_file_as_base64(audio_path)

                except Exception as e:
                    logger.error(f"Error extracting audio from Record: {e}")

        return None

    def _read_audio_file_as_base64(self, file_path: str) -> str | None:
        """Read local audio file and return as Base64"""
        if not os.path.exists(file_path):
            logger.warning(f"Audio file not found: {file_path}")
            return None

        try:
            with open(file_path, "rb") as f:
                audio_data = f.read()
            return base64.b64encode(audio_data).decode("utf-8")
        except Exception as e:
            logger.error(f"Error reading audio file: {e}")
            return None

    async def _download_audio_as_base64(self, url: str) -> str | None:
        """Download audio from URL and return as Base64"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 200:
                        audio_data = await resp.read()
                        return base64.b64encode(audio_data).decode("utf-8")
                    else:
                        logger.error(f"Failed to download audio: HTTP {resp.status}")
                        return None
        except Exception as e:
            logger.error(f"Error downloading audio: {e}")
            return None

    async def send_streaming(self, generator, use_fallback: bool = False) -> None:
        await self._store_user_message()

        async for chain in generator:
            text = _message_chain_to_text(chain)
            if text:
                self._response_text += text
                try:
                    await self.ws_client.send_json(
                        {"type": "full-text", "text": text, "name": "AI"}
                    )
                except Exception as e:
                    logger.error(f"Error sending streaming to WebSocket client: {e}")

        if self._response_text:
            await self._store_bot_message(self._response_text)

            expressions = await self._analyze_and_get_expressions(
                self.message_str, self._response_text
            )
            if expressions:
                try:
                    await self.ws_client.send_json(
                        {
                            "type": "expression",
                            "expressions": expressions,
                        }
                    )
                    logger.info(f"Sent expressions after streaming: {expressions}")
                except Exception as e:
                    logger.error(f"Error sending expressions: {e}")

        self._streaming_completed = True

    def get_response_text(self) -> str:
        return self._response_text


ws_server_instance: Optional["VTuberWebSocketServer"] = None


class VTuberWebSocketServer:
    """VTuber WebSocket 服务器"""

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 6191,
        on_client_connect=None,
        on_client_disconnect=None,
        on_message=None,
        default_model: str = "mao_pro",
        models_path: str = "",
    ) -> None:
        self.host = host
        self.port = port
        self.on_client_connect = on_client_connect
        self.on_client_disconnect = on_client_disconnect
        self.on_message = on_message
        self.default_model = default_model
        self.models_path = models_path

        self._ws_clients: dict[str, web.WebSocketResponse] = {}
        self._session_models: dict[str, dict] = {}
        self._running = False
        self._http_runner: web.AppRunner | None = None
        self._http_task: asyncio.Task | None = None
        self._plugin_dir = Path(__file__).parent
        self._model_dict: list = []

    def get_active_clients_count(self) -> int:
        return len(self._ws_clients)

    def get_connected_client_ids(self) -> list[str]:
        return list(self._ws_clients.keys())

    def get_model_info_for_session(self, session_id: str) -> dict | None:
        """Get model info for a specific session"""
        return self._session_models.get(session_id)

    def set_model_for_session(self, session_id: str, model_info: dict):
        """Set model info for a specific session"""
        self._session_models[session_id] = model_info

    async def send_to_client(self, session_id: str, message: dict) -> bool:
        if session_id not in self._ws_clients:
            return False
        try:
            await self._ws_clients[session_id].send_json(message)
            return True
        except Exception as e:
            logger.error(f"Error sending to client {session_id}: {e}")
            return False

    async def broadcast(self, message: dict) -> int:
        sent = 0
        for session_id, ws in list(self._ws_clients.items()):
            try:
                await ws.send_json(message)
                sent += 1
            except Exception as e:
                logger.error(f"Error broadcasting to {session_id}: {e}")
        return sent

    async def start(self) -> bool:
        try:
            self._running = True
            self._load_model_dict()

            app = web.Application()
            app.router.add_get("/", self._handle_index)
            app.router.add_get("/health", self._handle_health)
            app.router.add_get("/test/send", self._handle_test_send)
            app.router.add_post("/test/send", self._handle_test_send)
            app.router.add_get("/client-ws", self._handle_websocket)

            live2d_models_dir = self._find_live2d_models_dir()
            if live2d_models_dir:
                app.router.add_static("/live2d-models", live2d_models_dir)
                logger.info(f"Mounted Live2D models from: {live2d_models_dir}")

            self._http_runner = web.AppRunner(app)
            await self._http_runner.setup()

            site = web.TCPSite(self._http_runner, self.host, self.port)
            await site.start()

            logger.info(
                f"VTuber WebSocket server running on http://{self.host}:{self.port}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to start VTuber WebSocket server: {e}")
            return False

    async def stop(self):
        self._running = False

        # Close all active WebSocket connections first
        if self._ws_clients:
            logger.info(f"Closing {len(self._ws_clients)} WebSocket connections...")
            for client_id, ws in list(self._ws_clients.items()):
                try:
                    await ws.close()
                except Exception as e:
                    logger.debug(f"Error closing WebSocket for {client_id}: {e}")
            self._ws_clients.clear()

        if self._http_runner:
            await self._http_runner.cleanup()
        if self._http_task:
            self._http_task.cancel()
        logger.info("VTuber WebSocket server stopped")

    def _load_model_dict(self):
        if self.models_path:
            models_dir = Path(self.models_path)
            if not models_dir.is_absolute():
                models_dir = self._plugin_dir / self.models_path
            model_dict_path = models_dir / "model_dict.json"
            if not model_dict_path.exists():
                model_dict_path = self._plugin_dir / "model_dict.json"
        else:
            model_dict_path = self._plugin_dir / "model_dict.json"
        
        if model_dict_path.exists():
            try:
                with open(model_dict_path, encoding="utf-8") as f:
                    self._model_dict = json.load(f)
                logger.info(f"Loaded {len(self._model_dict)} Live2D models from {model_dict_path}")
            except Exception as e:
                logger.error(f"Error loading model_dict.json: {e}")

    def _find_live2d_models_dir(self) -> Path | None:
        possible_paths = [
            self._plugin_dir.parent.parent / "live2d-models",
            Path("d:/AstrBot-dev/live2d-models"),
        ]
        for path in possible_paths:
            if path.exists() and path.is_dir():
                return path
        return None

    async def _handle_index(self, request: web.Request) -> web.Response:
        return web.json_response(
            {
                "message": "VTuber Plugin is running!",
                "websocket_endpoint": "/client-ws",
                "connected_clients": len(self._ws_clients),
                "live2d_models": [m.get("name") for m in self._model_dict],
            }
        )

    async def _handle_health(self, request: web.Request) -> web.Response:
        return web.json_response(
            {
                "status": "ok",
                "plugin": "vtuber",
                "connected_clients": len(self._ws_clients),
                "live2d_models_loaded": len(self._model_dict),
            }
        )

    async def _handle_test_send(self, request: web.Request) -> web.Response:
        text = request.query.get("text", "Hello! [joy] This is a test message.")
        payload = {
            "type": "full-text",
            "text": text,
            "name": "AI",
        }
        sent_count = await self.broadcast(payload)
        return web.json_response(
            {
                "status": "sent",
                "text": text,
                "sent_to_clients": sent_count,
            }
        )

    async def _handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        session_id = f"vtuber_user_{uuid.uuid4().hex[:8]}"
        self._ws_clients[session_id] = ws
        logger.info(f"VTuber client connected: {session_id}")

        if self.on_client_connect:
            await self.on_client_connect(session_id, ws)

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    try:
                        data = json.loads(msg.data)
                        if self.on_message:
                            await self.on_message(session_id, data, ws)
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON from client {session_id}")
                elif msg.type == web.WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {ws.exception()}")
        finally:
            if session_id in self._ws_clients:
                del self._ws_clients[session_id]
            if self.on_client_disconnect:
                await self.on_client_disconnect(session_id)
            logger.info(f"VTuber client disconnected: {session_id}")

        return ws


@register_platform_adapter(
    adapter_name="vtuber",
    desc="VTuber Web Client - 提供 Live2D 虚拟形象对话功能",
    default_config_tmpl={
        "type": "vtuber",
        "enable": True,
        "id": "vtuber",
        "ws_host": "0.0.0.0",
        "ws_port": 6191,
        "live2d_model": "default",
    },
    adapter_display_name="VTuber Web Client",
    support_streaming_message=True,
)
class VTuberAdapter(Platform):
    """VTuber 平台适配器"""

    def __init__(self, platform_config: dict, event_queue: asyncio.Queue):
        super().__init__(platform_config, event_queue)
        self.config = platform_config
        self._running = False
        self._stop_event = asyncio.Event()
        self._context: Context | None = None

        self.metadata = PlatformMetadata(
            name="vtuber",
            description="VTuber Web Client",
            id="vtuber",
            support_proactive_message=False,
        )

        self.session_id = f"vtuber!user!{uuid.uuid4().hex[:8]}"

        logger.info("VTuber 平台适配器已初始化")

    def set_context(self, context: Context):
        """Set the context for emotion analysis"""
        self._context = context

    def _get_emotion_map(self, session_id: str) -> dict:
        """Get emotion map for the current model"""
        if not ws_server_instance:
            return {}

        model_info = ws_server_instance.get_model_info_for_session(session_id)
        if model_info:
            return model_info.get("emotionMap", {})
        return {}

    def meta(self) -> PlatformMetadata:
        return self.metadata

    async def send_by_session(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ):
        logger.debug(
            f"[send_by_session] platform_name={session.platform_name}, "
            f"session_id={session.session_id}, content={str(message_chain)[:50]}..."
        )

        try:
            msg_data = {
                "type": "message",
                "content": _message_chain_to_text(message_chain),
                "session_id": session.session_id,
            }
            if ws_server_instance:
                await ws_server_instance.send_to_client(session.session_id, msg_data)
        except Exception as e:
            logger.error(f"WebSocket 发送消息失败: {e}")

        await super().send_by_session(session, message_chain)

    def run(self):
        return self._run()

    async def _run(self):
        logger.info("VTuber 平台适配器启动中...")

        try:
            self._running = True
            self.status = self.status.__class__.RUNNING

            await self._stop_event.wait()

        except Exception as e:
            logger.error(f"VTuber 平台适配器运行错误: {e}")
            logger.error(traceback.format_exc())

    def handle_user_message(
        self,
        session_id: str,
        text: str,
        ws_client: web.WebSocketResponse,
        sender_id: str = "vtuber_user",
        sender_name: str = "VTuber User",
    ):
        """处理用户输入的消息"""
        if not text or not text.strip():
            return

        message_parts = [Plain(text)]

        abm = AstrBotMessage()
        abm.self_id = "vtuber"
        abm.sender = MessageMember(str(sender_id), sender_name)
        abm.type = MessageType.FRIEND_MESSAGE
        abm.session_id = session_id
        abm.message_id = str(uuid.uuid4())
        abm.timestamp = int(time.time())
        abm.message = message_parts
        abm.message_str = text
        abm.raw_message = {"source": "vtuber_ws", "client_uid": session_id}

        emotion_map = self._get_emotion_map(session_id)

        msg_event = VTuberMessageEvent(
            message_str=text,
            message_obj=abm,
            platform_meta=self.metadata,
            session_id=session_id,
            ws_client=ws_client,
            emotion_map=emotion_map,
            context=self._context,
        )

        logger.info(
            f"[VTuberAdapter] unified_msg_origin={msg_event.unified_msg_origin}, "
            f"platform_meta.id={self.metadata.id}"
        )

        self.commit_event(msg_event)
        logger.info(f"已提交 VTuber 消息事件: {text[:50]}...")

    async def terminate(self):
        logger.info("正在停止 VTuber 平台适配器...")
        self._running = False
        self._stop_event.set()
        self.status = self.status.__class__.STOPPED
        logger.info("VTuber 平台适配器已停止")


class Main(Star):
    """
    AstrBot VTuber 插件 - 主类
    完全模仿 astrbot_plugin_desktop_assistant 的架构
    """

    def __init__(self, context: Context, config: dict) -> None:
        super().__init__(context)
        global ws_server_instance

        self.context = context
        self.config = config
        self._adapter: VTuberAdapter | None = None

        ws_host = config.get("ws_host", "0.0.0.0")
        ws_port = config.get("ws_port", 6191)
        try:
            ws_port = int(ws_port)
        except (TypeError, ValueError):
            logger.warning(f"无效的 ws_port 配置: {ws_port}，将使用默认端口 6191")
            ws_port = 6191

        models_path = config.get("model_dict_path", "")
        if models_path:
            logger.info(f"Using custom model_dict_path: {models_path}")

        ws_server_instance = VTuberWebSocketServer(
            host=ws_host,
            port=ws_port,
            on_client_connect=self._on_client_connect,
            on_client_disconnect=self._on_client_disconnect,
            on_message=self._on_client_message,
            default_model=config.get("live2d_model", "mao_pro"),
            models_path=models_path,
        )

        try:
            platform_config = {
                "type": "vtuber",
                "enable": True,
                "id": "vtuber",
                "ws_host": ws_host,
                "ws_port": ws_port,
                "live2d_model": config.get("live2d_model", "default"),
            }
            self._adapter = VTuberAdapter(
                platform_config=platform_config,
                event_queue=self.context.platform_manager.event_queue,
            )
            self._adapter.set_context(self.context)
            self.context.platform_manager.platform_insts.append(self._adapter)
            logger.info("vtuber 平台适配器已手动注册到 platform_insts")
        except Exception as e:
            logger.error(f"手动注册 vtuber 平台适配器失败: {e}")

        asyncio.create_task(self._start_ws_server())

        logger.info("VTuber 插件已加载（平台适配器模式）")

    async def _start_ws_server(self):
        if ws_server_instance:
            success = await ws_server_instance.start()
            if not success:
                logger.error("VTuber WebSocket 服务器启动失败")

    async def _on_client_connect(self, session_id: str, ws: web.WebSocketResponse):
        """客户端连接回调"""
        try:
            existing_session = await db_helper.get_platform_session_by_id(session_id)
            if not existing_session:
                await db_helper.create_platform_session(
                    creator="vtuber_user",
                    platform_id="vtuber",
                    session_id=session_id,
                    display_name="VTuber Session",
                    is_group=0,
                )
                logger.info(f"Created PlatformSession for VTuber client: {session_id}")
        except Exception as e:
            logger.error(f"Failed to create PlatformSession: {e}")

        await ws.send_json({"type": "full-text", "text": "Connection established"})

        if ws_server_instance:
            models_path_config = {
                "type": "config",
                "models_path": ws_server_instance.models_path,
                "default_model": ws_server_instance.default_model,
            }
            await ws.send_json(models_path_config)
            logger.info(f"Sent config: models_path={ws_server_instance.models_path}")

        if ws_server_instance and ws_server_instance._model_dict:
            # 根据 default_model 配置选择模型
            model_info = None
            default_model_name = ws_server_instance.default_model
            for m in ws_server_instance._model_dict:
                if m.get("name") == default_model_name:
                    model_info = m
                    break
            # 如果没找到，使用第一个模型
            if not model_info:
                model_info = ws_server_instance._model_dict[0]
                logger.warning(
                    f"Model '{default_model_name}' not found, using first model: {model_info.get('name')}"
                )

            await ws.send_json(
                {
                    "type": "set-model-and-conf",
                    "model_info": model_info,
                    "conf_name": "default",
                    "conf_uid": "default",
                    "client_uid": session_id,
                }
            )
            ws_server_instance.set_model_for_session(session_id, model_info)
            logger.info(f"Sent model config: {model_info.get('name')}")

            await asyncio.sleep(0.2)
            await ws.send_json(
                {
                    "type": "control",
                    "text": "conversation-chain-start",
                }
            )
            logger.info("Sent ready control message")

    async def _on_client_disconnect(self, session_id: str):
        """客户端断开回调"""
        logger.info(f"Client disconnected: {session_id}")

    async def _on_client_message(
        self, session_id: str, data: dict, ws: web.WebSocketResponse
    ):
        """处理客户端消息"""
        msg_type = data.get("type")
        if msg_type == "ping":
            await ws.send_json({"type": "heartbeat-ack"})
        elif msg_type == "text-input":
            text = data.get("text", "")
            logger.info(f"Received text from client {session_id}: {text[:50]}...")
            await self._handle_user_input(session_id, text, ws)

    async def _handle_user_input(
        self, session_id: str, text: str, ws: web.WebSocketResponse
    ):
        """处理用户输入"""
        if not text or not text.strip():
            return

        try:
            await ws.send_json({"type": "control", "text": "conversation-chain-start"})

            if self._adapter:
                self._adapter.handle_user_message(
                    session_id=session_id,
                    text=text,
                    ws_client=ws,
                )
            else:
                logger.warning("VTuber 适配器未初始化")
                await ws.send_json(
                    {
                        "type": "full-text",
                        "text": "[Error] VTuber adapter not initialized",
                        "name": "System",
                    }
                )

        except Exception as e:
            logger.error(f"Error handling user input: {e}", exc_info=True)
            await ws.send_json(
                {
                    "type": "full-text",
                    "text": f"[Error] Failed to process message: {str(e)}",
                    "name": "System",
                }
            )

    async def terminate(self):
        """插件终止时的清理操作"""
        global ws_server_instance

        logger.info("正在清理 VTuber 插件...")

        if ws_server_instance:
            await ws_server_instance.stop()
            ws_server_instance = None

        adapter_name = "vtuber"

        if adapter_name in platform_cls_map:
            del platform_cls_map[adapter_name]
            logger.debug(f"已从 platform_cls_map 中移除适配器: {adapter_name}")

        for pm in platform_registry[:]:
            if pm.name == adapter_name:
                platform_registry.remove(pm)
                logger.debug(f"已从 platform_registry 中移除适配器: {adapter_name}")
                break

        logger.info("VTuber 插件清理完成")
