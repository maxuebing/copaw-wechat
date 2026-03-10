# -*- coding: utf-8 -*-
"""CoPaw 企业微信渠道插件

提供企业微信智能机器人消息收发功能。
"""

from .channel import WeComChannel

__all__ = ["WeComChannel"]

__version__ = "2.0.2"  # 修复图片 URL 缺少扩展名导致 AgentScope 报错的问题
