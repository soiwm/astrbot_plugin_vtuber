"""
Live2D 模型配置和表情映射
从 Open-LLM-VTuber 移植并简化
"""

import json
import logging
import os

logger = logging.getLogger(__name__)


class Live2dModel:
    """
    Live2D 模型类 - 准备和存储 Live2D 模型信息
    不负责向前端发送数据，仅准备 payload
    """

    def __init__(
        self,
        live2d_model_name: str = "default",
        model_dict_path: str = None,
    ):
        """
        初始化 Live2D 模型

        参数:
            live2d_model_name: 模型名称
            model_dict_path: 模型字典文件路径
        """
        self.model_dict_path = model_dict_path
        self.live2d_model_name = live2d_model_name
        self.model_info = self._get_default_model_info()
        self.emo_map = {}
        self.emo_str = ""

        if model_dict_path and os.path.exists(model_dict_path):
            try:
                self.set_model(live2d_model_name)
            except Exception as e:
                logger.warning(
                    f"Failed to load model from {model_dict_path}, using default: {e}"
                )
        else:
            self._init_default_model()

    def _get_default_model_info(self) -> dict:
        """获取默认模型信息"""
        return {
            "name": "default",
            "model": "/live2d-models/default/default.model3.json",
            "texture": None,
            "motion": None,
            "expression": None,
            "initPose": None,
            "physics": None,
            "scale": 1,
            "x": 0,
            "y": 0,
            "eyeBlink": True,
            "eyeBlinkInterval": [1, 5],
            "eyeBlinkDuration": [0.1, 0.2],
            "lipSync": True,
            "emotionMap": {
                "neutral": 0,
                "joy": 1,
                "sadness": 2,
                "anger": 3,
                "fear": 4,
                "surprise": 5,
            },
        }

    def _init_default_model(self):
        """初始化默认模型配置"""
        self.emo_map = {k.lower(): v for k, v in self.model_info["emotionMap"].items()}
        self.emo_str = " ".join([f"[{key}]," for key in self.emo_map.keys()])
        logger.info("Using default Live2D model configuration")

    def set_model(self, model_name: str) -> None:
        """
        设置模型并加载模型信息

        参数:
            model_name: 模型名称
        """
        self.model_info = self._lookup_model_info(model_name)
        self.emo_map = {k.lower(): v for k, v in self.model_info["emotionMap"].items()}
        self.emo_str = " ".join([f"[{key}]," for key in self.emo_map.keys()])
        logger.info(f"Model loaded: {model_name}")

    def _lookup_model_info(self, model_name: str) -> dict:
        """从模型字典中查找模型信息"""
        try:
            with open(self.model_dict_path, encoding="utf-8") as f:
                model_dict = json.load(f)
        except Exception as e:
            logger.error(f"Error loading model dictionary: {e}")
            return self._get_default_model_info()

        matched_model = next(
            (model for model in model_dict if model["name"] == model_name), None
        )

        if matched_model is None:
            logger.warning(f"Model {model_name} not found, using default")
            return self._get_default_model_info()

        return matched_model

    def extract_emotion(self, str_to_check: str) -> list:
        """
        从字符串中提取表情关键词

        参数:
            str_to_check: 要检查的字符串

        返回:
            找到的表情值列表
        """
        expression_list = []
        str_to_check = str_to_check.lower()

        i = 0
        while i < len(str_to_check):
            if str_to_check[i] != "[":
                i += 1
                continue
            for key in self.emo_map.keys():
                emo_tag = f"[{key}]"
                if str_to_check[i : i + len(emo_tag)] == emo_tag:
                    expression_list.append(self.emo_map[key])
                    i += len(emo_tag) - 1
                    break
            i += 1
        return expression_list

    def remove_emotion_keywords(self, target_str: str) -> str:
        """
        从字符串中移除表情关键词

        参数:
            target_str: 要处理的字符串

        返回:
            清理后的字符串
        """
        lower_str = target_str.lower()

        for key in self.emo_map.keys():
            lower_key = f"[{key}]".lower()
            while lower_key in lower_str:
                start_index = lower_str.find(lower_key)
                end_index = start_index + len(lower_key)
                target_str = target_str[:start_index] + target_str[end_index:]
                lower_str = lower_str[:start_index] + lower_str[end_index:]
        return target_str

    def get_emotion_prompt(self) -> str:
        """获取表情提示文本，用于 LLM 提示"""
        return self.emo_str
