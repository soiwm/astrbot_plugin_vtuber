"""
音频处理工具 - 处理音频分块和音量计算
从 Open-LLM-VTuber 移植
"""

import base64
import logging
from typing import Any

try:
    from pydub import AudioSegment
    from pydub.utils import make_chunks

    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False
    logging.warning("pydub not available, audio processing will be limited")

from ..agent.output_types import Actions, DisplayText

logger = logging.getLogger(__name__)


def _get_volume_by_chunks(audio: "AudioSegment", chunk_length_ms: int) -> list:
    """
    计算每个音频块的归一化音量 (RMS)

    参数:
        audio: 音频片段
        chunk_length_ms: 每个音频块的长度（毫秒）

    返回:
        每个块的归一化音量列表
    """
    if not PYDUB_AVAILABLE:
        return []

    chunks = make_chunks(audio, chunk_length_ms)
    volumes = [chunk.rms for chunk in chunks]
    max_volume = max(volumes) if volumes else 0
    if max_volume == 0:
        return [0.0] * len(volumes)
    return [volume / max_volume for volume in volumes]


def prepare_audio_payload(
    audio_path: str | None,
    chunk_length_ms: int = 20,
    display_text: DisplayText = None,
    actions: Actions = None,
    forwarded: bool = False,
) -> dict[str, Any]:
    """
    准备发送到广播端点的音频 payload
    如果 audio_path 为 None，则返回 audio=None 的 payload 用于静音显示

    参数:
        audio_path: 要处理的音频文件路径，或 None 用于静音显示
        chunk_length_ms: 每个音频块的长度（毫秒）
        display_text: 与音频一起显示的文本
        actions: 与音频关联的动作

    返回:
        要发送的音频 payload
    """
    if isinstance(display_text, DisplayText):
        display_text = display_text.to_dict()

    if not audio_path or not PYDUB_AVAILABLE:
        return {
            "type": "audio",
            "audio": None,
            "volumes": [],
            "slice_length": chunk_length_ms,
            "display_text": display_text,
            "actions": actions.to_dict() if actions else None,
            "forwarded": forwarded,
        }

    try:
        audio = AudioSegment.from_file(audio_path)
        audio_bytes = audio.export(format="wav").read()
    except Exception as e:
        logger.error(f"Error loading or converting audio file '{audio_path}': {e}")
        return {
            "type": "audio",
            "audio": None,
            "volumes": [],
            "slice_length": chunk_length_ms,
            "display_text": display_text,
            "actions": actions.to_dict() if actions else None,
            "forwarded": forwarded,
        }

    audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
    volumes = _get_volume_by_chunks(audio, chunk_length_ms)

    payload = {
        "type": "audio",
        "audio": audio_base64,
        "volumes": volumes,
        "slice_length": chunk_length_ms,
        "display_text": display_text,
        "actions": actions.to_dict() if actions else None,
        "forwarded": forwarded,
    }

    return payload
