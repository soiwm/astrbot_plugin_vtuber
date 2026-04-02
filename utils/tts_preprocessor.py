"""
TTS 文本预处理器 - 清理文本用于 TTS 合成
从 Open-LLM-VTuber 移植
"""

import logging
import re

logger = logging.getLogger(__name__)


def tts_filter(
    text: str,
    remove_special_char: bool = True,
    ignore_brackets: bool = True,
    ignore_parentheses: bool = True,
    ignore_asterisks: bool = True,
    ignore_angle_brackets: bool = True,
) -> str:
    """
    过滤文本用于 TTS 合成

    参数:
        text: 要过滤的原始文本
        remove_special_char: 是否移除特殊字符
        ignore_brackets: 是否移除方括号内容 [...]
        ignore_parentheses: 是否移除圆括号内容 (...)
        ignore_asterisks: 是否移除星号
        ignore_angle_brackets: 是否移除尖括号内容 <...>

    返回:
        过滤后的文本
    """
    if not text:
        return ""

    result = text

    # 移除方括号内容
    if ignore_brackets:
        result = re.sub(r"\[.*?\]", "", result)

    # 移除圆括号内容
    if ignore_parentheses:
        result = re.sub(r"\(.*?\)", "", result)

    # 移除尖括号内容
    if ignore_angle_brackets:
        result = re.sub(r"<.*?>", "", result)

    # 移除星号
    if ignore_asterisks:
        result = result.replace("*", "")

    # 移除特殊字符
    if remove_special_char:
        # 保留基本的标点符号
        result = re.sub(r'[^\w\s.,!?。！？，、；："\']', "", result)

    # 清理多余的空白
    result = re.sub(r"\s+", " ", result).strip()

    return result
