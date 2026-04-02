"""
对话相关类型定义
"""

from collections.abc import Callable, Coroutine
from typing import Any

# WebSocket 发送函数类型
WebSocketSend = Callable[[str], Coroutine[Any, Any, None]]
