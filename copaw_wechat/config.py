# -*- coding: utf-8 -*-
"""企业微信渠道配置类"""

from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class WeComConfig:
    """企业微信渠道配置

    对应 config.json 中的 channels.wecom 配置
    """

    # 基础配置
    enabled: bool = False
    bot_prefix: str = "[BOT] "
    corp_id: str = ""
    secret: str = ""
    aibot_id: str = ""
    token: str = ""
    encoding_aes_key: str = ""

    # 可选配置
    media_dir: str = "~/.copaw/media"
    callback_host: str = "0.0.0.0"
    callback_port: int = 8765
    callback_path: str = "/wecom/callback"

    # 消息过滤
    filter_tool_messages: bool = False
    filter_thinking: bool = False

    # 访问控制
    dm_policy: str = "open"  # open | whitelist
    group_policy: str = "open"  # open | whitelist
    allow_from: Optional[List[str]] = None
    deny_message: str = ""

    # 代理配置（可选）
    http_proxy: str = ""
    http_proxy_auth: str = ""

    def __post_init__(self):
        """初始化后处理"""
        if self.allow_from is None:
            self.allow_from = []

    @classmethod
    def from_dict(cls, data: dict) -> "WeComConfig":
        """从字典创建配置

        Args:
            data: 配置字典

        Returns:
            WeComConfig 实例
        """
        return cls(
            enabled=data.get("enabled", False),
            bot_prefix=data.get("bot_prefix", "[BOT] "),
            corp_id=data.get("corp_id", ""),
            secret=data.get("secret", ""),
            aibot_id=data.get("aibot_id", ""),
            token=data.get("token", ""),
            encoding_aes_key=data.get("encoding_aes_key", ""),
            media_dir=data.get("media_dir", "~/.copaw/media"),
            callback_host=data.get("callback_host", "0.0.0.0"),
            callback_port=data.get("callback_port", 8765),
            callback_path=data.get("callback_path", "/wecom/callback"),
            filter_tool_messages=data.get("filter_tool_messages", False),
            filter_thinking=data.get("filter_thinking", False),
            dm_policy=data.get("dm_policy", "open"),
            group_policy=data.get("group_policy", "open"),
            allow_from=data.get("allow_from"),
            deny_message=data.get("deny_message", ""),
            http_proxy=data.get("http_proxy", ""),
            http_proxy_auth=data.get("http_proxy_auth", ""),
        )

    def to_dict(self) -> dict:
        """转换为字典

        Returns:
            配置字典
        """
        return {
            "enabled": self.enabled,
            "bot_prefix": self.bot_prefix,
            "corp_id": self.corp_id,
            "secret": self.secret,
            "aibot_id": self.aibot_id,
            "token": self.token,
            "encoding_aes_key": self.encoding_aes_key,
            "media_dir": self.media_dir,
            "callback_host": self.callback_host,
            "callback_port": self.callback_port,
            "callback_path": self.callback_path,
            "filter_tool_messages": self.filter_tool_messages,
            "filter_thinking": self.filter_thinking,
            "dm_policy": self.dm_policy,
            "group_policy": self.group_policy,
            "allow_from": self.allow_from,
            "deny_message": self.deny_message,
            "http_proxy": self.http_proxy,
            "http_proxy_auth": self.http_proxy_auth,
        }

    def validate(self) -> List[str]:
        """验证配置

        Returns:
            错误信息列表，空列表表示验证通过
        """
        errors = []

        if not self.corp_id:
            errors.append("corp_id 不能为空")

        if not self.secret:
            errors.append("secret 不能为空")

        if not self.aibot_id:
            errors.append("aibot_id 不能为空")

        if not self.token:
            errors.append("token 不能为空")

        if not self.encoding_aes_key:
            errors.append("encoding_aes_key 不能为空")
        elif len(self.encoding_aes_key) != 43:
            errors.append("encoding_aes_key 长度必须为 43 字符")

        if self.callback_port < 1 or self.callback_port > 65535:
            errors.append("callback_port 必须在 1-65535 之间")

        return errors
