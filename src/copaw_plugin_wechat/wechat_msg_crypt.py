import base64
import hashlib
import json
import string
import random
import struct
import socket
import time
from Crypto.Cipher import AES
import logging

logger = logging.getLogger(__name__)


class FormatException(Exception):
    """格式异常类"""
    pass


def throw_exception(message, exception_type):
    """抛出异常并记录日志"""
    logger.error(message)
    raise exception_type(message)


class WechatMsgCrypt:
    """企业微信消息加解密类"""
    
    def __init__(self, token, encoding_aes_key, receive_id):
        """初始化
        
        Args:
            token: 企业微信Token
            encoding_aes_key: 加密密钥
            receive_id: 接收方ID
        """
        try:
            self.key = base64.b64decode(encoding_aes_key + "=")
            assert len(self.key) == 32
        except Exception:
            throw_exception(
                f"[error]: EncodingAESKey invalid! encoding_aes_key: {encoding_aes_key}",
                FormatException,
            )
        self.token = token
        self.receive_id = receive_id

    def verify_url(self, msg_signature, timestamp, nonce, echostr):
        """验证URL
        
        Args:
            msg_signature: 签名串
            timestamp: 时间戳
            nonce: 随机串
            echostr: 随机串
            
        Returns:
            解密后的echostr
        """
        sha1 = Sha1()
        ret, signature = sha1.get_sha1(self.token, timestamp, nonce, echostr)
        if ret != 0:
            throw_exception("签名计算失败", FormatException)
        if signature != msg_signature:
            throw_exception("签名校验失败", FormatException)
        
        pc = PrpCrypt(self.key)
        ret, decrypted = pc.decrypt(echostr, self.receive_id)
        if ret != 0:
            throw_exception("解密失败", FormatException)
        return decrypted

    def encrypt_msg(self, reply_msg, nonce, timestamp=None):
        """加密消息
        
        Args:
            reply_msg: 待回复的消息（JSON格式字符串）
            nonce: 随机串
            timestamp: 时间戳，为None时使用当前时间
            
        Returns:
            加密后的消息JSON字符串
        """
        pc = PrpCrypt(self.key)
        ret, encrypt = pc.encrypt(reply_msg, self.receive_id)
        if ret != 0:
            return None
            
        if timestamp is None:
            timestamp = int(time.time())
            
        sha1 = Sha1()
        ret, signature = sha1.get_sha1(self.token, timestamp, nonce, encrypt)
        if ret != 0:
            return None
            
        json_parser = JsonParser()
        return json_parser.generate(encrypt, signature, timestamp, nonce)

    def decrypt_msg(self, encrypt):
        """解密消息
        
        Args:
            encrypt: 加密的消息
            
        Returns:
            tuple: (状态码, 解密后的JSON内容)
        """
        pc = PrpCrypt(self.key)
        return pc.decrypt(encrypt, self.receive_id)


class Sha1:
    """SHA1签名计算类"""

    @staticmethod
    def _ensure_string(value):
        """确保值为字符串类型"""
        if isinstance(value, bytes):
            return value.decode('utf-8')
        return str(value)

    def get_sha1(self, token, timestamp, nonce, encrypt):
        """生成SHA1签名
        
        Args:
            token: 票据
            timestamp: 时间戳
            nonce: 随机字符串
            encrypt: 密文
            
        Returns:
            tuple: (状态码, 签名)
        """
        try:
            # 统一转换为字符串类型
            params = [self._ensure_string(param) for param in [token, timestamp, nonce, encrypt]]
            params.sort()
            
            sha = hashlib.sha1()
            sha.update("".join(params).encode("utf-8"))
            return 0, sha.hexdigest()
        except Exception as e:
            logger.error(f"签名计算失败: {e}")
            throw_exception("签名计算失败", FormatException)


class JsonParser:
    """JSON消息解析类"""
    
    RESPONSE_TEMPLATE = {
        "encrypt": "%(msg_encrypt)s",
        "msgsignature": "%(msg_signature)s",
        "timestamp": "%(timestamp)s",
        "nonce": "%(nonce)s"
    }

    def extract(self, json_text):
        """提取加密消息
        
        Args:
            json_text: JSON字符串
            
        Returns:
            tuple: (状态码, 加密消息)
        """
        try:
            json_dict = json.loads(json_text)
            return 0, json_dict["encrypt"]
        except Exception:
            throw_exception("解析JSON失败", FormatException)

    def generate(self, encrypt, signature, timestamp, nonce):
        """生成JSON消息
        
        Args:
            encrypt: 加密后的消息密文
            signature: 安全签名
            timestamp: 时间戳
            nonce: 随机字符串
            
        Returns:
            JSON字符串
        """
        # 确保encrypt为字符串类型
        if isinstance(encrypt, bytes):
            encrypt = encrypt.decode('utf-8')
            
        response_data = {
            "encrypt": encrypt,
            "msgsignature": signature,
            "timestamp": str(timestamp),
            "nonce": str(nonce),
        }
        return json.dumps(response_data, ensure_ascii=False)


class Pkcs7Encoder:
    """PKCS7填充算法类"""
    
    BLOCK_SIZE = 32

    def encode(self, text):
        """填充补位
        
        Args:
            text: 需要填充的明文
            
        Returns:
            补位后的字节串
        """
        if isinstance(text, str):
            text = text.encode('utf-8')
            
        text_length = len(text)
        amount_to_pad = self.BLOCK_SIZE - (text_length % self.BLOCK_SIZE)
        if amount_to_pad == 0:
            amount_to_pad = self.BLOCK_SIZE
            
        pad = bytes([amount_to_pad])
        return text + pad * amount_to_pad

    def decode(self, decrypted):
        """删除补位字符
        
        Args:
            decrypted: 解密后的明文
            
        Returns:
            删除补位后的明文
        """
        if isinstance(decrypted, str):
            decrypted = decrypted.encode('utf-8')
            
        pad = decrypted[-1] if isinstance(decrypted[-1], int) else ord(decrypted[-1])
        if not (1 <= pad <= 32):
            pad = 0
        return decrypted[:-pad] if pad > 0 else decrypted


class PrpCrypt:
    """AES加解密类"""
    
    def __init__(self, key):
        self.key = key
        self.mode = AES.MODE_CBC

    @staticmethod
    def get_random_str():
        """生成16位随机字符串"""
        chars = string.ascii_letters + string.digits
        return ''.join(random.choices(chars, k=16))

    def encrypt(self, text, receive_id):
        """加密明文
        
        Args:
            text: 需要加密的明文
            receive_id: 接收方ID
            
        Returns:
            tuple: (状态码, 加密结果)
        """
        try:
            # 统一转换为字符串
            if isinstance(text, bytes):
                text = text.decode('utf-8')
            if isinstance(receive_id, bytes):
                receive_id = receive_id.decode('utf-8')
                
            # 构建加密内容
            random_str = self.get_random_str()
            text_bytes = text.encode('utf-8')
            receive_id_bytes = receive_id.encode('utf-8')
            
            content = (
                random_str.encode('utf-8')
                + struct.pack("I", socket.htonl(len(text_bytes)))
                + text_bytes
                + receive_id_bytes
            )
            
            # 填充和加密
            pkcs7 = Pkcs7Encoder()
            padded_content = pkcs7.encode(content)
            
            cryptor = AES.new(self.key, self.mode, self.key[:16])
            ciphertext = cryptor.encrypt(padded_content)
            
            return 0, base64.b64encode(ciphertext)
        except Exception as e:
            logger.error(f"加密失败: {e}")
            throw_exception("加密失败", FormatException)

    def decrypt(self, text, receive_id):
        """解密密文
        
        Args:
            text: 密文
            receive_id: 接收方ID
            
        Returns:
            tuple: (状态码, 解密后的JSON内容)
        """
        try:
            # 确保receive_id为字节类型以便比较
            if isinstance(receive_id, str):
                receive_id = receive_id.encode('utf-8')
                
            # 解密
            cryptor = AES.new(self.key, self.mode, self.key[:16])
            plain_text = cryptor.decrypt(base64.b64decode(text))
            
            # 获取填充字节数并去除填充
            pad = plain_text[-1]
            if not (1 <= pad <= 32):
                pad = 0
                
            # 解析内容
            content = plain_text[16:-pad] if pad > 0 else plain_text[16:]
            json_len = socket.ntohl(struct.unpack("I", content[:4])[0])
            json_content = content[4:json_len + 4]
            from_receive_id = content[json_len + 4:]
            
            # 验证receive_id
            if len(from_receive_id) > 0 and from_receive_id != receive_id:
                throw_exception(
                    f"receive_id不匹配。期望：{receive_id}，实际：{from_receive_id}",
                    FormatException,
                )
                
            return 0, json_content.decode('utf-8')
        except Exception as e:
            logger.error(f"解密失败: {e}")
            throw_exception("解密失败", FormatException)


# 保持向后兼容性的别名
wechat_msg_crypt = WechatMsgCrypt
