# -*- coding: utf-8 -*-
"""CoPaw 企业微信渠道插件

提供企业微信智能机器人消息收发功能。
"""

from .channel import WeComChannel

__all__ = ["WeComChannel"]

__version__ = "2.1.5"  # 增强调试：添加 HTTP 请求头和响应头日志，帮助诊断图片下载问题

# Monkey Patch: 修复 agentscope 对图片路径后缀校验过于严格的问题，以及 API 无法访问本地路径的问题
# 当历史记录中存在本地图片路径（无论是否有后缀）时，都会导致 TypeError 或 API 400 错误
try:
    from agentscope.formatter import _openai_formatter
    import os
    import base64
    import mimetypes

    if hasattr(_openai_formatter, "_to_openai_image_url"):
        _original_to_openai_image_url = _openai_formatter._to_openai_image_url

        def _get_image_base64(path: str) -> str:
            """尝试读取文件并转换为 Base64，如果失败则返回占位符"""
            try:
                # 去掉可能的 file:// 前缀
                if path.startswith("file://"):
                    path = path[7:]
                
                # 尝试找到文件 (考虑之前可能追加了后缀)
                real_path = path
                if not os.path.exists(real_path):
                    for ext in [".jpg", ".png", ".jpeg", ".gif", ".webp"]:
                        if os.path.exists(path + ext):
                            real_path = path + ext
                            break
                
                if os.path.exists(real_path) and os.path.isfile(real_path):
                    mime_type, _ = mimetypes.guess_type(real_path)
                    if not mime_type:
                        mime_type = "image/jpeg"
                        
                    with open(real_path, "rb") as f:
                        encoded = base64.b64encode(f.read()).decode("utf-8")
                        return f"data:{mime_type};base64,{encoded}"
            except Exception as e:
                print(f"[WeCom Patch] 图片转 Base64 失败: {e}", flush=True)
            
            # 返回 1x1 透明 GIF 占位符，防止 API 报错
            print(f"[WeCom Patch] 无法读取图片 {path}，使用占位符代替", flush=True)
            return "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"

        def _patched_to_openai_image_url(url: str) -> str:
            # 1. 如果已经是 http/https 或 data: 开头，直接返回（除了可能的 agentscope 校验）
            if url.startswith("http") or url.startswith("data:"):
                try:
                    return _original_to_openai_image_url(url)
                except TypeError:
                    # 如果是 http url 但没后缀，可能也需要处理？
                    # 但主要是处理 data: 或带 token 的 url
                    pass
            
            # 2. 对于任何看起来像本地路径的字符串，都尝试转换为 Base64
            # 即使它有后缀并通过了 agentscope 校验，但 API 无法访问本地路径，所以必须转换
            if not url.startswith("http") and not url.startswith("data:"):
                return _get_image_base64(url)

            # 3. 其他情况，尝试原来的逻辑（主要是为了捕获 TypeError 并修复）
            try:
                return _original_to_openai_image_url(url)
            except TypeError as e:
                if "should end with" in str(e):
                    # 再次尝试作为本地文件处理（虽然前面已经处理过了，为了保险）
                    return _get_image_base64(url)
                raise e

        _openai_formatter._to_openai_image_url = _patched_to_openai_image_url
        print("[WeCom] 已应用 AgentScope 图片路径增强补丁 (Base64)", flush=True)

except (ImportError, AttributeError) as e:
    # 可能会因为 agentscope 版本不同而失败，但这不影响主要功能
    pass

