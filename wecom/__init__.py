# -*- coding: utf-8 -*-
"""CoPaw 企业微信渠道插件

提供企业微信智能机器人消息收发功能。
"""

from .channel import WeComChannel

__all__ = ["WeComChannel"]

__version__ = "2.1.1"  # 使用 Base64 Data URL 解决 AI 模型无法访问本地图片路径的问题
