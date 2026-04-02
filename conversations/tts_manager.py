"""
TTS 任务管理器 - 管理 TTS 任务并确保有序发送到前端
从 Open-LLM-VTuber 移植并简化
"""

import asyncio
import json
import re
import uuid
from datetime import datetime

from astrbot.api import logger

from ..agent.output_types import Actions, DisplayText
from ..utils.stream_audio import prepare_audio_payload
from .types import WebSocketSend


class SimpleTTSEngine:
    """
    简单的 TTS 引擎接口
    AstrBot 集成时可以替换为真实的 TTS 引擎
    """

    async def async_generate_audio(
        self, text: str, file_name_no_ext: str = None
    ) -> str:
        """
        异步生成音频文件

        参数:
            text: 要合成的文本
            file_name_no_ext: 文件名（不含扩展名）

        返回:
            音频文件路径
        """
        # 这是一个占位实现
        # 实际使用时应该集成 AstrBot 的 TTS 功能
        logger.warning(f"SimpleTTSEngine: TTS not implemented, text: {text[:50]}...")
        return None

    def remove_file(self, file_path: str) -> None:
        """移除生成的音频文件"""
        pass


class TTSTaskManager:
    """管理 TTS 任务并确保有序发送到前端，同时允许并行 TTS 生成"""

    def __init__(self, tts_engine=None) -> None:
        self.task_list: list[asyncio.Task] = []
        self._payload_queue: asyncio.Queue[tuple[dict, int]] = asyncio.Queue()
        self._sender_task: asyncio.Task | None = None
        self._sequence_counter = 0
        self._next_sequence_to_send = 0
        self.tts_engine = tts_engine or SimpleTTSEngine()
        self._running = True

    async def speak(
        self,
        tts_text: str,
        display_text: DisplayText,
        actions: Actions | None,
        websocket_send: WebSocketSend,
    ) -> None:
        """
        排队 TTS 任务，同时保持发送顺序

        参数:
            tts_text: 要合成的文本
            display_text: 在 UI 中显示的文本
            actions: Live2D 模型动作
            websocket_send: WebSocket 发送函数
        """
        if len(re.sub(r'[\s.,!?，。！？\'"』」）】\s]+', "", tts_text)) == 0:
            logger.debug("Empty TTS text, sending silent display payload")
            current_sequence = self._sequence_counter
            self._sequence_counter += 1

            if not self._sender_task or self._sender_task.done():
                self._sender_task = asyncio.create_task(
                    self._process_payload_queue(websocket_send)
                )

            await self._send_silent_payload(display_text, actions, current_sequence)
            return

        logger.debug(f"Queuing TTS task for: '{tts_text[:50]}...'")

        current_sequence = self._sequence_counter
        self._sequence_counter += 1

        if not self._sender_task or self._sender_task.done():
            self._sender_task = asyncio.create_task(
                self._process_payload_queue(websocket_send)
            )

        task = asyncio.create_task(
            self._process_tts(
                tts_text=tts_text,
                display_text=display_text,
                actions=actions,
                sequence_number=current_sequence,
            )
        )
        task.add_done_callback(self._on_task_done)
        self.task_list.append(task)

    def _on_task_done(self, task: asyncio.Task) -> None:
        """任务完成回调，从列表中移除已完成的任务"""
        try:
            self.task_list.remove(task)
        except ValueError:
            pass

    async def _process_payload_queue(self, websocket_send: WebSocketSend) -> None:
        """
        按正确顺序处理和发送 payload
        持续运行直到所有 payload 处理完毕
        """
        buffered_payloads: dict[int, dict] = {}

        while self._running:
            try:
                payload, sequence_number = await asyncio.wait_for(
                    self._payload_queue.get(), timeout=1.0
                )
                buffered_payloads[sequence_number] = payload

                while self._next_sequence_to_send in buffered_payloads:
                    next_payload = buffered_payloads.pop(self._next_sequence_to_send)
                    try:
                        await websocket_send(json.dumps(next_payload))
                    except Exception as e:
                        logger.error(f"Error sending payload: {e}")
                    self._next_sequence_to_send += 1

                self._payload_queue.task_done()

            except asyncio.TimeoutError:
                if self._payload_queue.empty():
                    break
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in payload queue processing: {e}")

    async def _send_silent_payload(
        self,
        display_text: DisplayText,
        actions: Actions | None,
        sequence_number: int,
    ) -> None:
        """排队静音音频 payload"""
        audio_payload = prepare_audio_payload(
            audio_path=None,
            display_text=display_text,
            actions=actions,
        )
        await self._payload_queue.put((audio_payload, sequence_number))

    async def _process_tts(
        self,
        tts_text: str,
        display_text: DisplayText,
        actions: Actions | None,
        sequence_number: int,
    ) -> None:
        """处理 TTS 生成并排球结果以进行有序发送"""
        audio_file_path = None
        try:
            audio_file_path = await self._generate_audio(tts_text)
            payload = prepare_audio_payload(
                audio_path=audio_file_path,
                display_text=display_text,
                actions=actions,
            )
            await self._payload_queue.put((payload, sequence_number))

        except Exception as e:
            logger.error(f"Error preparing audio payload: {e}")
            payload = prepare_audio_payload(
                audio_path=None,
                display_text=display_text,
                actions=actions,
            )
            await self._payload_queue.put((payload, sequence_number))

        finally:
            if audio_file_path:
                self.tts_engine.remove_file(audio_file_path)
                logger.debug("Audio cache file cleaned.")

    async def _generate_audio(self, text: str) -> str:
        """从文本生成音频文件"""
        logger.debug(f"Generating audio for '{text[:50]}...'")
        file_name = (
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"
        )
        return await self.tts_engine.async_generate_audio(
            text=text,
            file_name_no_ext=file_name,
        )

    async def clear(self) -> None:
        """清除所有待处理任务并重置状态"""
        self._running = False

        for task in self.task_list:
            if not task.done():
                task.cancel()

        if self.task_list:
            await asyncio.gather(*self.task_list, return_exceptions=True)

        self.task_list.clear()

        if self._sender_task and not self._sender_task.done():
            self._sender_task.cancel()
            try:
                await self._sender_task
            except asyncio.CancelledError:
                pass

        self._sequence_counter = 0
        self._next_sequence_to_send = 0
        self._payload_queue = asyncio.Queue()
        self._running = True
