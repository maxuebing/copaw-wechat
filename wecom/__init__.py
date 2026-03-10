# -*- coding: utf-8 -*-
"""CoPaw 企业微信渠道插件

提供企业微信智能机器人消息收发功能。
"""

from .channel import WeComChannel

__all__ = ["WeComChannel"]

__version__ = "2.0.1"  # 修复 aibot_respond_msg 消息类型错误 (40008)
