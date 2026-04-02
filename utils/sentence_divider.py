"""
句子分割器 - 适配 AstrBot 的简化版本
从 Open-LLM-VTuber 移植，移除了不必要的依赖
"""

import logging
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# Constants for additional checks
COMMAS = [
    ",",
    "，",
    "、",
    "；",
]

END_PUNCTUATIONS = [".", "!", "?", "。", "！", "？", "...", "。。。"]

ABBREVIATIONS = [
    "Mr.",
    "Mrs.",
    "Dr.",
    "Prof.",
    "Inc.",
    "Ltd.",
    "Jr.",
    "Sr.",
    "e.g.",
    "i.e.",
    "vs.",
    "St.",
    "Rd.",
]


def is_complete_sentence(text: str) -> bool:
    """检查文本是否以句子结尾标点符号结束"""
    text = text.strip()
    if not text:
        return False

    if any(text.endswith(abbrev) for abbrev in ABBREVIATIONS):
        return False

    return any(text.endswith(punct) for punct in END_PUNCTUATIONS)


def contains_comma(text: str) -> bool:
    """检查文本是否包含逗号"""
    return any(comma in text for comma in COMMAS)


def comma_splitter(text: str) -> tuple[str, str]:
    """在第一个逗号处分割文本"""
    if not text:
        return "", ""

    for comma in COMMAS:
        if comma in text:
            split_text = text.split(comma, 1)
            return split_text[0].strip() + comma, split_text[1].strip()
    return text, ""


def contains_end_punctuation(text: str) -> bool:
    """检查文本是否包含句子结尾标点"""
    return any(punct in text for punct in END_PUNCTUATIONS)


def segment_text_by_regex(text: str) -> tuple[list[str], str]:
    """使用正则表达式将文本分割为完整句子"""
    if not text:
        return [], ""

    complete_sentences = []
    remaining_text = text.strip()

    # Create pattern for matching sentences ending with any end punctuation
    escaped_punctuations = [re.escape(p) for p in END_PUNCTUATIONS]
    pattern = r"(.*?(?:[" + "|".join(escaped_punctuations) + r"]))"

    while remaining_text:
        match = re.search(pattern, remaining_text)
        if not match:
            break

        end_pos = match.end(1)
        potential_sentence = remaining_text[:end_pos].strip()

        # Skip if sentence ends with abbreviation
        if any(potential_sentence.endswith(abbrev) for abbrev in ABBREVIATIONS):
            remaining_text = remaining_text[end_pos:].lstrip()
            continue

        complete_sentences.append(potential_sentence)
        remaining_text = remaining_text[end_pos:].lstrip()

    return complete_sentences, remaining_text


class TagState(Enum):
    """文本中标签的状态"""

    START = "start"
    INSIDE = "inside"
    END = "end"
    SELF_CLOSING = "self"
    NONE = "none"


@dataclass
class TagInfo:
    """标签信息"""

    name: str
    state: TagState

    def __str__(self) -> str:
        if self.state == TagState.NONE:
            return "none"
        return f"{self.name}:{self.state.value}"


@dataclass
class SentenceWithTags:
    """带有标签信息的句子"""

    text: str
    tags: list[TagInfo]


class SentenceDivider:
    """句子分割器 - 处理 token 流并将其转换为完整句子"""

    def __init__(
        self,
        faster_first_response: bool = True,
        segment_method: str = "regex",
        valid_tags: list[str] = None,
    ):
        self.faster_first_response = faster_first_response
        self.segment_method = segment_method
        self.valid_tags = valid_tags or ["think"]
        self._is_first_sentence = True
        self._buffer = ""
        self._tag_stack = []
        self._full_response = []

    def _get_current_tags(self) -> list[TagInfo]:
        """获取当前所有活动标签"""
        return [TagInfo(tag.name, TagState.INSIDE) for tag in self._tag_stack]

    def _extract_tag(self, text: str) -> tuple[TagInfo | None, str]:
        """从文本中提取第一个标签"""
        first_tag = None
        first_pos = len(text)
        tag_type = None
        matched_tag = None

        # Check for self-closing tags
        for tag in self.valid_tags:
            pattern = f"<{tag}/>"
            match = re.search(pattern, text)
            if match and match.start() < first_pos:
                first_pos = match.start()
                first_tag = match
                tag_type = TagState.SELF_CLOSING
                matched_tag = tag

        # Check for opening tags
        for tag in self.valid_tags:
            pattern = f"<{tag}>"
            match = re.search(pattern, text)
            if match and match.start() < first_pos:
                first_pos = match.start()
                first_tag = match
                tag_type = TagState.START
                matched_tag = tag

        # Check for closing tags
        for tag in self.valid_tags:
            pattern = f"</{tag}>"
            match = re.search(pattern, text)
            if match and match.start() < first_pos:
                first_pos = match.start()
                first_tag = match
                tag_type = TagState.END
                matched_tag = tag

        if not first_tag:
            return None, text

        if tag_type == TagState.START:
            self._tag_stack.append(TagInfo(matched_tag, TagState.START))
        elif tag_type == TagState.END:
            if self._tag_stack and self._tag_stack[-1].name == matched_tag:
                self._tag_stack.pop()

        return (TagInfo(matched_tag, tag_type), text[first_tag.end() :].lstrip())

    async def _process_buffer(self) -> AsyncIterator[SentenceWithTags]:
        """处理缓冲区，生成完整句子"""
        processed_something = True
        while processed_something:
            processed_something = False
            original_buffer_len = len(self._buffer)

            if not self._buffer.strip():
                break

            # Find the next tag position
            next_tag_pos = len(self._buffer)
            for tag in self.valid_tags:
                patterns = [f"<{tag}>", f"</{tag}>", f"<{tag}/>"]
                for pattern in patterns:
                    pos = self._buffer.find(pattern)
                    if pos != -1 and pos < next_tag_pos:
                        next_tag_pos = pos

            if next_tag_pos == 0:
                tag_info, remaining = self._extract_tag(self._buffer)
                if tag_info:
                    processed_text = self._buffer[
                        : len(self._buffer) - len(remaining)
                    ].strip()
                    yield SentenceWithTags(text=processed_text, tags=[tag_info])
                    self._buffer = remaining
                    processed_something = True
                    continue

            elif next_tag_pos < len(self._buffer):
                text_before_tag = self._buffer[:next_tag_pos]
                current_tags = self._get_current_tags()

                if contains_end_punctuation(text_before_tag):
                    sentences, remaining_before = self._segment_text(text_before_tag)
                    for sentence in sentences:
                        if sentence.strip():
                            yield SentenceWithTags(
                                text=sentence.strip(),
                                tags=current_tags or [TagInfo("", TagState.NONE)],
                            )
                    self._buffer = self._buffer[len(text_before_tag) :]
                    processed_something = True
                    continue

            if original_buffer_len > 0:
                current_tags = self._get_current_tags()

                if (
                    self._is_first_sentence
                    and self.faster_first_response
                    and contains_comma(self._buffer)
                ):
                    sentence, remaining = comma_splitter(self._buffer)
                    if sentence.strip():
                        yield SentenceWithTags(
                            text=sentence.strip(),
                            tags=current_tags or [TagInfo("", TagState.NONE)],
                        )
                        self._buffer = remaining
                        self._is_first_sentence = False
                        processed_something = True
                        continue

                if contains_end_punctuation(self._buffer):
                    sentences, remaining = self._segment_text(self._buffer)
                    if sentences:
                        self._buffer = remaining
                        self._is_first_sentence = False
                        processed_something = True
                        for sentence in sentences:
                            if sentence.strip():
                                yield SentenceWithTags(
                                    text=sentence.strip(),
                                    tags=current_tags or [TagInfo("", TagState.NONE)],
                                )
                        continue

            if not processed_something:
                break

    async def _flush_buffer(self) -> AsyncIterator[SentenceWithTags]:
        """刷新缓冲区中剩余的内容"""
        async for sentence in self._process_buffer():
            yield sentence

        if self._buffer.strip():
            current_tags = self._get_current_tags()
            yield SentenceWithTags(
                text=self._buffer.strip(),
                tags=current_tags or [TagInfo("", TagState.NONE)],
            )
            self._buffer = ""

    async def process_stream(
        self, segment_stream: AsyncIterator[str | dict[str, Any]]
    ) -> AsyncIterator[SentenceWithTags | dict[str, Any]]:
        """处理 token 流，生成完整句子"""
        self._full_response = []
        self.reset()

        async for item in segment_stream:
            if isinstance(item, dict):
                async for sentence in self._process_buffer():
                    self._full_response.append(sentence.text)
                    yield sentence
                yield item
            elif isinstance(item, str):
                self._buffer += item
                async for sentence in self._process_buffer():
                    self._full_response.append(sentence.text)
                    yield sentence

        async for sentence in self._flush_buffer():
            self._full_response.append(sentence.text)
            yield sentence

    @property
    def complete_response(self) -> str:
        """获取完整响应"""
        return "".join(self._full_response)

    def _segment_text(self, text: str) -> tuple[list[str], str]:
        """使用配置的方法分割文本"""
        return segment_text_by_regex(text)

    def reset(self):
        """重置状态"""
        self._is_first_sentence = True
        self._buffer = ""
        self._tag_stack = []
