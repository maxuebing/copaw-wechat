# -*- coding: utf-8 -*-
"""测试配置类"""

import pytest

from copaw_wechat.config import WeComConfig


class TestWeComConfig:
    """测试 WeComConfig 类"""

    def test_default_values(self):
        """测试默认值"""
        config = WeComConfig()
        assert config.enabled is False
        assert config.bot_prefix == "[BOT] "
        assert config.corp_id == ""
        assert config.secret == ""
        assert config.aibot_id == ""
        assert config.token == ""
        assert config.encoding_aes_key == ""
        assert config.media_dir == "~/.copaw/media"
        assert config.callback_host == "0.0.0.0"
        assert config.callback_port == 8765
        assert config.dm_policy == "open"
        assert config.group_policy == "open"
        assert config.allow_from == []
        assert config.deny_message == ""

    def test_from_dict(self):
        """测试从字典创建"""
        data = {
            "enabled": True,
            "corp_id": "ww123456",
            "secret": "secret",
            "aibot_id": "AIBOTID",
            "token": "token",
            "encoding_aes_key": "k" * 43,
            "bot_prefix": "[BOT]",
            "callback_port": 9000,
        }

        config = WeComConfig.from_dict(data)
        assert config.enabled is True
        assert config.corp_id == "ww123456"
        assert config.secret == "secret"
        assert config.aibot_id == "AIBOTID"
        assert config.token == "token"
        assert config.encoding_aes_key == "k" * 43
        assert config.bot_prefix == "[BOT]"
        assert config.callback_port == 9000

    def test_to_dict(self):
        """测试转换为字典"""
        config = WeComConfig(
            enabled=True,
            corp_id="ww123456",
            secret="secret",
        )

        data = config.to_dict()
        assert data["enabled"] is True
        assert data["corp_id"] == "ww123456"
        assert data["secret"] == "secret"

    def test_validate_success(self):
        """测试验证 - 成功"""
        config = WeComConfig(
            enabled=True,
            corp_id="ww123456",
            secret="secret",
            aibot_id="AIBOTID",
            token="token",
            encoding_aes_key="k" * 43,
        )

        errors = config.validate()
        assert errors == []

    def test_validate_errors(self):
        """测试验证 - 失败"""
        config = WeComConfig()
        errors = config.validate()

        assert len(errors) > 0
        assert "corp_id 不能为空" in errors
        assert "secret 不能为空" in errors
        assert "aibot_id 不能为空" in errors
        assert "token 不能为空" in errors
        assert "encoding_aes_key 不能为空" in errors


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
