# -*- coding: utf-8 -*-
"""企业微信加解密工具

参考企业微信加解密方案：AES-256-CBC，PKCS#7 填充
"""

import base64
import struct
from typing import Tuple

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad, pad


class WeComCryptoError(Exception):
    """加解密异常"""


class WeComCrypto:
    """企业微信消息加解密

    使用 AES-256-CBC 模式，PKCS#7 填充
    """

    def __init__(self, encoding_aes_key: str):
        """初始化加解密器

        Args:
            encoding_aes_key: Base64 编码的 AES Key（43 字符）
        """
        if not encoding_aes_key or len(encoding_aes_key) != 43:
            raise WeComCryptoError(
                f"encoding_aes_key 长度必须为 43 字符，当前: {len(encoding_aes_key)}"
            )

        # Base64 解码得到 32 字节的 AES Key
        self.aes_key = base64.b64decode(encoding_aes_key + "=")

    def encrypt(self, plaintext: str, corp_id: str) -> str:
        """加密消息

        Args:
            plaintext: 待加密的明文（JSON 字符串）
            corp_id: 企业 ID

        Returns:
            加密后的 Base64 字符串
        """
        # 组合明文：随机字符串(16B) + corp_id + plaintext + corp_id
        text = plaintext.encode("utf-8")
        corp_id_bytes = corp_id.encode("utf-8")

        # 生成 16 字节随机字符串
        import os
        random_str = os.urandom(16)

        # 组合：random + len(corp_id) + corp_id + len(text) + text
        # 企业微信格式：random(16) + msg_len(4) + msg + receive_corpid
        msg = random_str + struct.pack(">I", len(text)) + text + corp_id_bytes

        # AES 加密
        cipher = AES.new(self.aes_key, AES.MODE_CBC, self.aes_key[:16])
        ciphertext = cipher.encrypt(pad(msg, AES.block_size))

        # Base64 编码
        return base64.b64encode(ciphertext).decode("utf-8")

    def decrypt(self, ciphertext: str) -> Tuple[str, str]:
        """解密消息

        Args:
            ciphertext: Base64 编码的密文

        Returns:
            (msg, corp_id) 元组
        """
        try:
            # Base64 解码
            encrypted = base64.b64decode(ciphertext)

            # AES 解密
            cipher = AES.new(self.aes_key, AES.MODE_CBC, self.aes_key[:16])
            decrypted = unpad(cipher.decrypt(encrypted), AES.block_size)

            # 解析：random(16) + msg_len(4) + msg + receive_corpid
            random_str = decrypted[:16]
            msg_len = struct.unpack(">I", decrypted[16:20])[0]
            msg = decrypted[20:20 + msg_len].decode("utf-8")
            corp_id = decrypted[20 + msg_len:].decode("utf-8")

            return msg, corp_id

        except Exception as e:
            raise WeComCryptoError(f"解密失败: {e}")

    def verify_signature(self, msg_signature: str, timestamp: str,
                        nonce: str, encrypt: str) -> bool:
        """验证签名

        Args:
            msg_signature: 签名
            timestamp: 时间戳
            nonce: 随机字符串
            encrypt: 加密的消息

        Returns:
            签名是否有效
        """
        import hashlib

        # 按字典序排序并拼接
        tmp_arr = [self.aes_key.decode("utf-8", errors="ignore"), timestamp, nonce, encrypt]
        tmp_arr.sort()
        tmp_str = "".join(tmp_arr)

        # SHA1 哈希
        tmp_str = hashlib.sha1(tmp_str.encode("utf-8")).hexdigest()

        return tmp_str == msg_signature

    def generate_signature(self, timestamp: str, nonce: str,
                          encrypt: str) -> str:
        """生成签名

        Args:
            timestamp: 时间戳
            nonce: 随机字符串
            encrypt: 加密的消息

        Returns:
            签名字符串
        """
        import hashlib

        # 按字典序排序并拼接
        tmp_arr = [self.aes_key.decode("utf-8", errors="ignore"), timestamp, nonce, encrypt]
        tmp_arr.sort()
        tmp_str = "".join(tmp_arr)

        # SHA1 哈希
        return hashlib.sha1(tmp_str.encode("utf-8")).hexdigest()


def pkcs7_unpad(data: bytes) -> bytes:
    """PKCS#7 去除填充

    Args:
        data: 填充后的数据

    Returns:
        去除填充后的数据
    """
    padding_len = data[-1]
    return data[:-padding_len]


def pkcs7_pad(data: bytes, block_size: int = 32) -> bytes:
    """PKCS#7 填充

    Args:
        data: 原始数据
        block_size: 块大小（默认 32）

    Returns:
        填充后的数据
    """
    padding_len = block_size - (len(data) % block_size)
    padding = bytes([padding_len] * padding_len)
    return data + padding
