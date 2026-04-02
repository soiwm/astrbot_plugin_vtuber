"""
装饰器链 - 处理文本流，分句、表情提取等
从 Open-LLM-VTuber 移植并简化
"""

from collections.abc import AsyncIterator, Callable
from functools import wraps
from typing import Any

from astrbot.api import logger

from ..core.live2d_model import Live2dModel
from ..utils.sentence_divider import (
    SentenceDivider,
    SentenceWithTags,
    TagState,
)
from ..utils.tts_preprocessor import tts_filter as filter_text
from .output_types import Actions, DisplayText, SentenceOutput


def sentence_divider(
    faster_first_response: bool = True,
    segment_method: str = "regex",
    valid_tags: list[str] = None,
):
    """
    将 token 流转换为带有标签的句子的装饰器

    参数:
        faster_first_response: 是否启用更快的首次响应
        segment_method: 句子分割方法
        valid_tags: 要处理的有效标签列表
    """

    def decorator(
        func: Callable[..., AsyncIterator[str | dict[str, Any]]],
    ) -> Callable[..., AsyncIterator[SentenceWithTags | dict[str, Any]]]:
        @wraps(func)
        async def wrapper(
            *args, **kwargs
        ) -> AsyncIterator[SentenceWithTags | dict[str, Any]]:
            divider = SentenceDivider(
                faster_first_response=faster_first_response,
                segment_method=segment_method,
                valid_tags=valid_tags or ["think"],
            )
            stream_from_func = func(*args, **kwargs)

            async for item in divider.process_stream(stream_from_func):
                if isinstance(item, SentenceWithTags):
                    logger.debug(
                        f"sentence_divider yielding sentence: {item.text[:50]}..."
                    )
                yield item

        return wrapper

    return decorator


def actions_extractor(live2d_model: Live2dModel):
    """
    从句子中提取动作的装饰器
    """

    def decorator(
        func: Callable[..., AsyncIterator[SentenceWithTags | dict[str, Any]]],
    ) -> Callable[
        ..., AsyncIterator[tuple[SentenceWithTags, Actions] | dict[str, Any]]
    ]:
        @wraps(func)
        async def wrapper(
            *args, **kwargs
        ) -> AsyncIterator[tuple[SentenceWithTags, Actions] | dict[str, Any]]:
            stream = func(*args, **kwargs)
            async for item in stream:
                if isinstance(item, SentenceWithTags):
                    sentence = item
                    actions = Actions()
                    if not any(
                        tag.state in [TagState.START, TagState.END]
                        for tag in sentence.tags
                    ):
                        expressions = live2d_model.extract_emotion(sentence.text)
                        if expressions:
                            actions.expressions = expressions
                    yield sentence, actions
                elif isinstance(item, dict):
                    yield item
                else:
                    logger.warning(
                        f"actions_extractor received unexpected type: {type(item)}"
                    )

        return wrapper

    return decorator


def display_processor():
    """
    处理显示文本的装饰器
    """

    def decorator(
        func: Callable[
            ..., AsyncIterator[tuple[SentenceWithTags, Actions] | dict[str, Any]]
        ],
    ) -> Callable[
        ...,
        AsyncIterator[tuple[SentenceWithTags, DisplayText, Actions] | dict[str, Any]],
    ]:
        @wraps(func)
        async def wrapper(
            *args, **kwargs
        ) -> AsyncIterator[
            tuple[SentenceWithTags, DisplayText, Actions] | dict[str, Any]
        ]:
            stream = func(*args, **kwargs)

            async for item in stream:
                if (
                    isinstance(item, tuple)
                    and len(item) == 2
                    and isinstance(item[0], SentenceWithTags)
                ):
                    sentence, actions = item
                    text = sentence.text

                    for tag in sentence.tags:
                        if tag.name == "think":
                            if tag.state == TagState.START:
                                text = "("
                            elif tag.state == TagState.END:
                                text = ")"

                    display = DisplayText(text=text)
                    yield sentence, display, actions
                elif isinstance(item, dict):
                    yield item
                else:
                    logger.warning(
                        f"display_processor received unexpected type: {type(item)}"
                    )

        return wrapper

    return decorator


def tts_filter(
    remove_special_char: bool = True,
    ignore_brackets: bool = True,
    ignore_parentheses: bool = True,
    ignore_asterisks: bool = True,
    ignore_angle_brackets: bool = True,
):
    """
    过滤 TTS 文本的装饰器
    """

    def decorator(
        func: Callable[
            ...,
            AsyncIterator[
                tuple[SentenceWithTags, DisplayText, Actions] | dict[str, Any]
            ],
        ],
    ) -> Callable[..., AsyncIterator[SentenceOutput | dict[str, Any]]]:
        @wraps(func)
        async def wrapper(
            *args, **kwargs
        ) -> AsyncIterator[SentenceOutput | dict[str, Any]]:
            stream = func(*args, **kwargs)

            async for item in stream:
                if (
                    isinstance(item, tuple)
                    and len(item) == 3
                    and isinstance(item[1], DisplayText)
                ):
                    sentence, display, actions = item
                    if any(tag.name == "think" for tag in sentence.tags):
                        tts = ""
                    else:
                        tts = filter_text(
                            text=display.text,
                            remove_special_char=remove_special_char,
                            ignore_brackets=ignore_brackets,
                            ignore_parentheses=ignore_parentheses,
                            ignore_asterisks=ignore_asterisks,
                            ignore_angle_brackets=ignore_angle_brackets,
                        )

                    logger.debug(f"display: {display.text[:50]}...")
                    logger.debug(f"tts: {tts[:50]}...")

                    yield SentenceOutput(
                        display_text=display,
                        tts_text=tts,
                        actions=actions,
                    )
                elif isinstance(item, dict):
                    yield item
                else:
                    logger.warning(f"tts_filter received unexpected type: {type(item)}")

        return wrapper

    return decorator
