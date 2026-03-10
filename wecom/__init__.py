# -*- coding: utf-8 -*-
"""CoPaw 企业微信渠道插件

提供企业微信智能机器人消息收发功能。
"""

from .channel import WeComChannel

__all__ = ["WeComChannel"]

__version__ = "2.1.2"  # 修复 AgentScope 图片路径校验过严导致 crash 的问题

# Monkey Patch: 修复 agentscope 对图片路径后缀校验过于严格的问题
# 当历史记录中存在无后缀的图片路径（如临时下载文件）时，会导致 TypeError 崩溃
try:
    from agentscope.formatter import _openai_formatter

    if hasattr(_openai_formatter, "_to_openai_image_url"):
        _original_to_openai_image_url = _openai_formatter._to_openai_image_url

        def _patched_to_openai_image_url(url: str) -> str:
            try:
                return _original_to_openai_image_url(url)
            except TypeError as e:
                # 如果校验失败，尝试追加 .jpg 后缀以绕过检查
                # 这能防止因历史记录中的坏数据导致整个 Agent 崩溃
                if "should end with" in str(e):
                    # 仅针对本地路径或看起来像文件的路径进行修补
                    if not url.startswith("http") and not url.startswith("data:"):
                        return f"{url}.jpg"
                raise e

        _openai_formatter._to_openai_image_url = _patched_to_openai_image_url
        print("[WeCom] 已应用 AgentScope 图片路径校验补丁", flush=True)

except (ImportError, AttributeError) as e:
    # 可能会因为 agentscope 版本不同而失败，但这不影响主要功能
    pass

