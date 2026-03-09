# -*- coding: utf-8 -*-
"""测试加解密功能"""

import pytest

from copaw_wechat.crypto import WeComCrypto, WeComCryptoError


class TestWeComCrypto:
    """测试 WeComCrypto 类"""

    def test_init_valid_key(self):
        """测试初始化 - 有效密钥"""
        # 43 字符的 Base64 编码密钥
        key = "kWxPEV2UEDyxWpmyfnZer0PLfJfPZOyP2JV3LqMyjx"
        crypto = WeComCrypto(key)
        assert crypto is not None
        assert len(crypto.aes_key) == 32

    def test_init_invalid_key(self):
        """测试初始化 - 无效密钥"""
        with pytest.raises(WeComCryptoError):
            WeComCrypto("short_key")

    def test_encrypt_decrypt(self):
        """测试加密解密"""
        key = "kWxPEV2UEDyxWpmyfnZer0PLfJfPZOyP2JV3LqMyjx"
        crypto = WeComCrypto(key)

        plaintext = '{"msgtype":"text","text":{"content":"hello"}}'
        corp_id = "ww123456"

        # 加密
        ciphertext = crypto.encrypt(plaintext, corp_id)
        assert ciphertext
        assert isinstance(ciphertext, str)

        # 解密
        decrypted_msg, decrypted_corp_id = crypto.decrypt(ciphertext)
        assert decrypted_msg == plaintext
        assert decrypted_corp_id == corp_id

    def test_signature(self):
        """测试签名验证"""
        key = "kWxPEV2UEDyxWpmyfnZer0PLfJfPZOyP2JV3LqMyjx"
        crypto = WeComCrypto(key)

        timestamp = "1234567890"
        nonce = "random"
        encrypt = "encrypted_text"

        # 生成签名
        signature = crypto.generate_signature(timestamp, nonce, encrypt)

        # 验证签名
        assert crypto.verify_signature(signature, timestamp, nonce, encrypt)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
