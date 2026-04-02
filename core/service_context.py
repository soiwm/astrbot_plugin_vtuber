"""
服务上下文 - 聚合所有服务
从 Open-LLM-VTuber 移植并简化
"""

import logging
import os
import sys

# 支持两种导入方式
try:
    from ..conversations.tts_manager import SimpleTTSEngine, TTSTaskManager
    from ..conversations.types import WebSocketSend
    from .live2d_model import Live2dModel
except ImportError:
    # 绝对导入模式（独立运行时）
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from conversations.tts_manager import SimpleTTSEngine, TTSTaskManager
    from conversations.types import WebSocketSend
    from core.live2d_model import Live2dModel

logger = logging.getLogger(__name__)


class ServiceContext:
    """
    服务上下文 - 聚合所有服务的容器
    """

    def __init__(self):
        self.live2d_model: Live2dModel = Live2dModel()
        self.tts_engine = SimpleTTSEngine()
        self.tts_manager: TTSTaskManager = TTSTaskManager(self.tts_engine)
        self.send_text: WebSocketSend | None = None
        self.client_uid: str | None = None
        self.config = {}
        self.character_config = type(
            "obj", (object,), {"conf_name": "default", "conf_uid": "default"}
        )()

    async def load_cache(
        self,
        config=None,
        system_config=None,
        character_config=None,
        live2d_model=None,
        tts_engine=None,
        send_text=None,
        client_uid=None,
        **kwargs,
    ):
        """加载缓存的服务"""
        if config:
            self.config = config
        if character_config:
            self.character_config = character_config
        if live2d_model:
            self.live2d_model = live2d_model
        if tts_engine:
            self.tts_engine = tts_engine
            self.tts_manager = TTSTaskManager(tts_engine)
        if send_text:
            self.send_text = send_text
        if client_uid:
            self.client_uid = client_uid

    async def close(self):
        """关闭服务并清理资源"""
        self.tts_manager.clear()
        logger.info("ServiceContext closed")

    def set_tts_engine(self, tts_engine):
        """设置 TTS 引擎"""
        self.tts_engine = tts_engine
        self.tts_manager = TTSTaskManager(tts_engine)

    def set_live2d_model(self, model_name: str, model_dict_path: str = None):
        """设置 Live2D 模型"""
        self.live2d_model = Live2dModel(model_name, model_dict_path)
