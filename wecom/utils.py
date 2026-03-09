# -*- coding: utf-8 -*-
"""企业微信渠道工具函数"""

import asyncio
import base64
import hashlib
import logging
import mimetypes
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from .constants import (
    WECOM_ACCESS_TOKEN_TTL,
    WECOM_TOKEN_REFRESH_BEFORE_SECONDS,
    WECOM_USER_INFO_FETCH_TIMEOUT,
)

logger = logging.getLogger(__name__)


def get_file_mime_type(file_path: str) -> str:
    """获取文件 MIME 类型

    Args:
        file_path: 文件路径

    Returns:
        MIME 类型字符串
    """
    mime_type, _ = mimetypes.guess_type(file_path)
    return mime_type or "application/octet-stream"


def get_file_extension(mime_type: str) -> str:
    """从 MIME 类型获取文件扩展名

    Args:
        mime_type: MIME 类型

    Returns:
        文件扩展名（包含点号）
    """
    ext = mimetypes.guess_extension(mime_type)
    return ext or ".bin"


def calculate_md5(data: bytes) -> str:
    """计算数据的 MD5 值

    Args:
        data: 二进制数据

    Returns:
        MD5 哈希字符串（小写）
    """
    return hashlib.md5(data).hexdigest()


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


def normalize_markdown(text: str) -> str:
    """标准化 Markdown 格式（适配企业微信）

    Args:
        text: 原始 Markdown 文本

    Returns:
        标准化后的 Markdown 文本
    """
    # 企业微信 Markdown 支持的子集
    # 标题、加粗、链接、行内代码、引用、字体颜色

    # 确保标题前有空格
    lines = text.split("\n")
    result = []

    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("#"):
            # 计算井号数量
            num_hash = len(line) - len(line.lstrip("#"))
            if num_hash > 0 and num_hash <= 6:
                if len(line) > num_hash and line[num_hash] != " ":
                    line = "#" * num_hash + " " + line[num_hash:]

        result.append(line)

    return "\n".join(result)


async def download_file(
    session: aiohttp.ClientSession,
    url: str,
    timeout: int = 30,
) -> Optional[bytes]:
    """下载文件

    Args:
        session: aiohttp 会话
        url: 文件 URL
        timeout: 超时时间（秒）

    Returns:
        文件内容，失败返回 None
    """
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status == 200:
                return await resp.read()
            logger.warning(f"下载文件失败: status={resp.status}, url={url}")
            return None

    except asyncio.TimeoutError:
        logger.warning(f"下载文件超时: url={url}")
        return None
    except Exception as e:
        logger.warning(f"下载文件异常: url={url}, error={e}")
        return None


async def upload_media_to_wecom(
    session: aiohttp.ClientSession,
    access_token: str,
    file_path: str,
    media_type: str = "file",
) -> Optional[str]:
    """上传媒体文件到企业微信

    Args:
        session: aiohttp 会话
        access_token: 访问令牌
        file_path: 文件路径
        media_type: 媒体类型（file/image/voice）

    Returns:
        media_id，失败返回 None
    """
    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/upload_media?key={access_token}&type={media_type}"

    try:
        file_path_obj = Path(file_path).expanduser()

        if not file_path_obj.exists():
            logger.error(f"文件不存在: {file_path}")
            return None

        with open(file_path_obj, "rb") as f:
            files = {
                "media": (file_path_obj.name, f, get_file_mime_type(str(file_path_obj)))
            }

            async with session.post(url, data=files) as resp:
                data = await resp.json()

                if data.get("errcode") == 0:
                    return data.get("media_id")
                else:
                    logger.error(f"上传文件失败: {data}")
                    return None

    except Exception as e:
        logger.error(f"上传文件异常: {e}")
        return None


def build_text_message(content: str) -> dict:
    """构建文本消息

    Args:
        content: 文本内容

    Returns:
        消息体
    """
    return {
        "msgtype": "text",
        "text": {
            "content": content
        }
    }


def build_markdown_message(content: str) -> dict:
    """构建 Markdown 消息

    Args:
        content: Markdown 内容

    Returns:
        消息体
    """
    return {
        "msgtype": "markdown",
        "markdown": {
            "content": normalize_markdown(content)
        }
    }


def build_image_message(base64_data: str, md5: str) -> dict:
    """构建图片消息

    Args:
        base64_data: Base64 编码的图片数据
        md5: 图片 MD5

    Returns:
        消息体
    """
    return {
        "msgtype": "image",
        "image": {
            "base64": base64_data,
            "md5": md5
        }
    }


def build_mixed_message(items: List[dict]) -> dict:
    """构建图文混排消息

    Args:
        items: 消息项列表，每项为 {"msgtype": "text", "text": {"content": "..."}} 格式

    Returns:
        消息体
    """
    return {
        "msgtype": "mixed",
        "mixed": {
            "msg_item": items
        }
    }


def build_stream_message(stream_id: str, status: int, content: str = "") -> dict:
    """构建流式消息

    Args:
        stream_id: 流式消息 ID
        status: 状态（1=继续，2=结束）
        content: 消息内容

    Returns:
        消息体
    """
    msg = {
        "msgtype": "stream",
        "stream": {
            "id": stream_id,
            "status": status
        }
    }

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


class TokenManager:
    """访问令牌管理器"""

    def __init__(self, corp_id: str, secret: str):
        """初始化

        Args:
            corp_id: 企业 ID
            secret: 应用 Secret
        """
        self.corp_id = corp_id
        self.secret = secret
        self._token: Optional[str] = None
        self._expires_at: float = 0
        self._lock = asyncio.Lock()

    async def get_token(self, session: aiohttp.ClientSession) -> str:
        """获取有效的访问令牌

        Args:
            session: aiohttp 会话

        Returns:
            访问令牌
        """
        async with self._lock:
            # 检查是否需要刷新
            if self._token and (self._expires_at - WECOM_TOKEN_REFRESH_BEFORE_SECONDS) > asyncio.get_event_loop().time():
                return self._token

            # 获取新令牌
            url = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
            params = {
                "corpid": self.corp_id,
                "corpsecret": self.secret
            }

            async with session.get(url, params=params) as resp:
                data = await resp.json()

                if data.get("errcode") == 0:
                    self._token = data.get("access_token")
                    expires_in = data.get("expires_in", WECOM_ACCESS_TOKEN_TTL)
                    self._expires_at = asyncio.get_event_loop().time() + expires_in
                    return self._token
                else:
                    raise RuntimeError(f"获取访问令牌失败: {data}")

    def clear(self):
        """清除缓存的令牌"""
        self._token = None
        self._expires_at = 0
