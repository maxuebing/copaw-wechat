# -*- coding: utf-8 -*-
"""企业微信渠道工具函数"""

import mimetypes
from typing import List, Optional


def extract_text_from_mixed(mixed: dict) -> str:
    """从图文混排消息中提取文本

    Args:
        mixed: 图文混排消息体

    Returns:
        提取的文本内容
    """
    texts = []
    msg_items = mixed.get("msg_item", [])

    for item in msg_items:
        msg_type = item.get("msgtype", "")

        if msg_type == "text":
            content = item.get("text", {}).get("content", "")
            texts.append(content)
        elif msg_type == "image":
            texts.append("[图片]")
        elif msg_type == "voice":
            texts.append("[语音]")
        elif msg_type == "file":
            texts.append("[文件]")

    return "".join(texts)


def build_text_message(content: str) -> dict:
    """构建文本消息

    Args:
        content: 文本内容

    Returns:
        消息体
    """
    return {"msgtype": "text", "text": {"content": content}}


def build_markdown_message(content: str) -> dict:
    """构建 Markdown 消息

    Args:
        content: Markdown 内容

    Returns:
        消息体
    """
    return {"msgtype": "markdown", "markdown": {"content": content}}


def build_mixed_message(items: List[dict]) -> dict:
    """构建图文混排消息

    Args:
        items: 消息项列表

    Returns:
        消息体
    """
    return {"msgtype": "mixed", "mixed": {"msg_item": items}}


def build_stream_message(stream_id: str, status: int, content: str = "") -> dict:
    """构建流式消息

    Args:
        stream_id: 流式消息 ID
        status: 状态（1=继续，2=结束）
        content: 消息内容

    Returns:
        消息体
    """
    msg = {"msgtype": "stream", "stream": {"id": stream_id, "status": status}}

    if content:
        msg["stream"]["content"] = content

    return msg


def is_group_chat(chattype: str) -> bool:
    """判断是否为群聊

    Args:
        chattype: 会话类型

    Returns:
        是否为群聊
    """
    return chattype == "group"


def sender_display_string(userid: str, nickname: Optional[str] = None) -> str:
    """获取发送者显示字符串

    Args:
        userid: 用户 ID
        nickname: 昵称（可选）

    Returns:
        显示字符串
    """
    if nickname:
        return f"{nickname}#{userid[:8]}"
    return f"unknown#{userid[:8]}"


def normalize_markdown(text: str) -> str:
    """标准化 Markdown 格式（适配企业微信）

    Args:
        text: 原始 Markdown 文本

    Returns:
        标准化后的 Markdown 文本
    """
    lines = text.split("\n")
    result = []

    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("#"):
            num_hash = len(line) - len(line.lstrip("#"))
            if num_hash > 0 and num_hash <= 6:
                if len(line) > num_hash and line[num_hash] != " ":
                    line = "#" * num_hash + " " + line[num_hash:]

        result.append(line)

    return "\n".join(result)


def get_file_mime_type(file_path: str) -> str:
    """获取文件 MIME 类型

    Args:
        file_path: 文件路径

    Returns:
        MIME 类型字符串
    """
    mime_type, _ = mimetypes.guess_type(file_path)
    return mime_type or "application/octet-stream"
