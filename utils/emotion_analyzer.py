"""
Emotion Analyzer for VTuber Plugin
Analyzes text sentiment and maps to Live2D expressions
Reference: astrbot_plugin_emotionai_pro
"""

import asyncio
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

EMOTION_DIMENSIONS = [
    "joy",
    "sadness",
    "anger",
    "surprise",
    "fear",
    "disgust",
    "neutral",
]

POSITIVE_WORDS = [
    "好",
    "开心",
    "高兴",
    "快乐",
    "谢谢",
    "感谢",
    "喜欢",
    "爱",
    "不错",
    "棒",
    "可爱",
    "漂亮",
    "美丽",
    "相信",
    "太好了",
    "哈哈",
    "嘻嘻",
    "棒极了",
    "完美",
    "太棒了",
    "真棒",
    "好耶",
    "好开心",
    "好喜欢",
    "太可爱",
    "厉害",
    "优秀",
    "精彩",
    "赞",
    "牛",
    "强",
    "厉害了",
    "太强了",
    "好厉害",
    "感动",
    "温暖",
    "幸福",
    "甜蜜",
    "温馨",
    "治愈",
    "开心极了",
    "超级开心",
    "非常开心",
]

NEGATIVE_WORDS = [
    "讨厌",
    "生气",
    "愤怒",
    "烦",
    "恨",
    "滚",
    "傻",
    "笨",
    "蠢",
    "垃圾",
    "不愿意",
    "不爽",
    "不高兴",
    "难过",
    "伤心",
    "痛苦",
    "绝望",
    "崩溃",
    "烦死了",
    "气死",
    "讨厌死了",
    "恶心",
    "反感",
    "厌恶",
    "烦躁",
    "郁闷",
    "沮丧",
    "失落",
    "失望",
    "遗憾",
    "可惜",
    "心疼",
    "心碎",
    "悲伤",
]

SURPRISE_WORDS = [
    "哇",
    "天哪",
    "什么",
    "真的吗",
    "不会吧",
    "怎么可能",
    "太意外了",
    "震惊",
    "惊讶",
    "没想到",
    "居然",
    "竟然",
    "意外",
    "惊喜",
    "吓到",
    "吓死",
    "吓一跳",
    "不可思议",
    "难以置信",
    "哇塞",
    "卧槽",
    "我靠",
]

SADNESS_WORDS = [
    "难过",
    "伤心",
    "哭",
    "眼泪",
    "悲伤",
    "痛苦",
    "心碎",
    "绝望",
    "失落",
    "沮丧",
    "郁闷",
    "遗憾",
    "可惜",
    "心疼",
    "可怜",
    "悲伤",
    "泪目",
    "哭了",
    "想哭",
    "好难过",
    "好伤心",
    "好心疼",
    "泪流满面",
    "受伤",
    "伤口",
    "流血",
    "疼",
    "痛",
    "不舒服",
    "生病",
    "医院",
]

ANGER_WORDS = [
    "生气",
    "愤怒",
    "气死",
    "烦死",
    "讨厌",
    "滚",
    "混蛋",
    "王八蛋",
    "可恶",
    "该死",
    "该死的",
    "他妈",
    "草",
    "操",
    "靠",
    "烦人",
    "火大",
    "恼火",
    "暴怒",
    "怒",
    "怒了",
    "炸了",
    "气炸了",
]

FEAR_WORDS = [
    "害怕",
    "恐惧",
    "担心",
    "担忧",
    "焦虑",
    "紧张",
    "不安",
    "惶恐",
    "惊恐",
    "恐慌",
    "吓人",
    "可怕",
    "恐怖",
    "吓死",
    "吓坏",
    "胆战心惊",
]


class EmotionAnalyzer:
    """Emotion analyzer for VTuber expressions"""

    def __init__(self, context=None, llm_timeout: float = 10.0):
        self.context = context
        self.llm_timeout = llm_timeout
        self._llm_failures = 0
        self._llm_available = True

    async def analyze(self, user_message: str, ai_response: str) -> dict[str, int]:
        """
        Analyze emotions from conversation

        Args:
            user_message: User's input message
            ai_response: AI's response

        Returns:
            Dict with emotion scores: {"joy": 2, "sadness": 0, ...}
        """
        try:
            if self._llm_available and self.context:
                result = await self._analyze_with_llm(user_message, ai_response)
                if result:
                    self._llm_failures = 0
                    return result

            self._llm_failures += 1
            if self._llm_failures >= 3:
                self._llm_available = False
                logger.info("LLM analysis disabled after 3 failures")

        except Exception as e:
            logger.error(f"LLM emotion analysis failed: {e}")

        return self._analyze_with_keywords(user_message, ai_response)

    async def _analyze_with_llm(
        self, user_message: str, ai_response: str
    ) -> dict[str, int] | None:
        """Use LLM for emotion analysis"""
        try:
            providers = self.context.get_all_providers()
            if not providers:
                return None

            provider = self._find_provider(providers)
            if not provider:
                return None

            prompt = self._build_prompt(user_message, ai_response)

            result = await asyncio.wait_for(
                self._call_provider(provider, prompt),
                timeout=self.llm_timeout,
            )

            if result:
                return self._parse_llm_result(result)

        except asyncio.TimeoutError:
            logger.warning("LLM analysis timeout")
        except Exception as e:
            logger.error(f"LLM analysis error: {e}")

        return None

    def _find_provider(self, providers: list) -> Any | None:
        """Find a suitable LLM provider"""
        for provider in providers:
            name = getattr(provider, "name", "").lower()
            if "deepseek" in name or "default" in name:
                return provider
        return providers[0] if providers else None

    async def _call_provider(self, provider: Any, prompt: str) -> str | None:
        """Call LLM provider"""
        try:
            if hasattr(provider, "text_chat"):
                if asyncio.iscoroutinefunction(provider.text_chat):
                    result = await provider.text_chat(prompt)
                else:
                    result = provider.text_chat(prompt)
                return self._extract_text(result)

            if hasattr(provider, "chat_completion"):
                messages = [{"role": "user", "content": prompt}]
                if asyncio.iscoroutinefunction(provider.chat_completion):
                    result = await provider.chat_completion(messages=messages)
                else:
                    result = provider.chat_completion(messages=messages)
                return self._extract_text(result)

        except Exception as e:
            logger.error(f"Provider call error: {e}")

        return None

    def _extract_text(self, response: Any) -> str:
        """Extract text from LLM response"""
        if isinstance(response, str):
            return response.strip()

        for attr in ["completion_text", "text", "content", "response"]:
            if hasattr(response, attr):
                val = getattr(response, attr)
                if isinstance(val, str):
                    return val.strip()

        if isinstance(response, dict):
            if "content" in response:
                return response["content"].strip()
            if "choices" in response and response["choices"]:
                choice = response["choices"][0]
                if "message" in choice and "content" in choice["message"]:
                    return choice["message"]["content"].strip()

        return ""

    def _build_prompt(self, user_message: str, ai_response: str) -> str:
        """Build analysis prompt"""
        return f"""Analyze the emotions in this conversation and return a JSON object.

User: {user_message}
AI: {ai_response}

Return ONLY a JSON object with these emotion scores (0-3):
{{"joy": 0, "sadness": 0, "anger": 0, "surprise": 0, "fear": 0, "disgust": 0, "neutral": 1}}

Rules:
- Only one emotion should have the highest score
- neutral should be 1 when emotions are unclear
- joy: happiness, excitement, pleasure
- sadness: sorrow, grief, disappointment
- anger: frustration, rage, annoyance
- surprise: shock, amazement, unexpected
- fear: anxiety, worry, dread
- disgust: aversion, repulsion"""

    def _parse_llm_result(self, text: str) -> dict[str, int] | None:
        """Parse LLM analysis result"""
        try:
            json_match = re.search(r"\{[^}]+\}", text, re.DOTALL)
            if json_match:
                import json

                data = json.loads(json_match.group())
                result = {}
                for emotion in EMOTION_DIMENSIONS:
                    value = data.get(emotion, 0)
                    if isinstance(value, (int, float)):
                        result[emotion] = min(3, max(0, int(value)))
                    else:
                        result[emotion] = 0

                if not any(v > 0 for v in result.values()):
                    result["neutral"] = 1

                return result

        except Exception as e:
            logger.error(f"Failed to parse LLM result: {e}")

        return None

    def _analyze_with_keywords(
        self, user_message: str, ai_response: str
    ) -> dict[str, int]:
        """Fallback keyword-based analysis"""
        combined = (user_message + " " + ai_response).lower()

        scores = {
            "joy": self._count_words(combined, POSITIVE_WORDS),
            "sadness": self._count_words(combined, SADNESS_WORDS),
            "anger": self._count_words(combined, ANGER_WORDS),
            "surprise": self._count_words(combined, SURPRISE_WORDS),
            "fear": self._count_words(combined, FEAR_WORDS),
            "disgust": 0,
            "neutral": 0,
        }

        max_emotion = max(scores, key=scores.get)
        max_score = scores[max_emotion]

        if max_score == 0:
            return {
                "neutral": 1,
                "joy": 0,
                "sadness": 0,
                "anger": 0,
                "surprise": 0,
                "fear": 0,
                "disgust": 0,
            }

        scores[max_emotion] = min(3, max_score)

        for emotion in scores:
            if emotion != max_emotion:
                scores[emotion] = 0

        return scores

    def _count_words(self, text: str, words: list[str]) -> int:
        """Count matching words in text"""
        count = 0
        for word in words:
            if word in text:
                count += 1
        return count

    def get_dominant_emotion(self, scores: dict[str, int]) -> str:
        """Get the dominant emotion from scores"""
        max_score = 0
        dominant = "neutral"

        for emotion, score in scores.items():
            if score > max_score:
                max_score = score
                dominant = emotion

        return dominant
