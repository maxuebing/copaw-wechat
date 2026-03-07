import logging
import json
import xml.etree.ElementTree as ET
from typing import Optional, Dict, Any, Union
from wechatpy.enterprise import WeChatClient as BaseWeChatClient
from wechatpy.enterprise.crypto import WeChatCrypto
from wechatpy.exceptions import InvalidSignatureException
from wechatpy.enterprise.exceptions import InvalidCorpIdException
from wechatpy import parse_message
from wechatpy.replies import TextReply
import requests
import time
import random

from .config import WechatConfig

logger = logging.getLogger(__name__)

class WechatClient:
    def __init__(self, config: WechatConfig):
        self.config = config
        self.client: Optional[BaseWeChatClient] = None
        
        # 仅当配置了 corp_secret 时初始化主动发送客户端
        if self.config.corp_secret:
            self.client = BaseWeChatClient(
                self.config.corp_id,
                self.config.corp_secret
            )
            
            # 如果配置了代理，设置 session 代理
            if self.config.outbound_proxy:
                proxies = {
                    "http": self.config.outbound_proxy,
                    "https": self.config.outbound_proxy
                }
                self.client.session.proxies.update(proxies)
        
        self.crypto = WeChatCrypto(
            self.config.token,
            self.config.encoding_aes_key,
            self.config.corp_id
        )

    def verify_signature(self, signature: str, timestamp: str, nonce: str, echostr: str) -> str:
        """
        验证回调 URL 签名
        """
        try:
            return self.crypto.check_signature(
                signature,
                timestamp,
                nonce,
                echostr
            )
        except InvalidSignatureException:
            logger.error("Invalid signature")
            raise

    def handle_message(self, signature: str, timestamp: str, nonce: str, data: Union[str, bytes]) -> Optional[Dict[str, Any]]:
        """
        处理接收到的消息
        1. 验证签名
        2. 解密消息
        3. 解析 XML 或 JSON
        """
        try:
            if isinstance(data, bytes):
                data = data.decode('utf-8')

            # 尝试判断是否为 JSON
            is_json = False
            try:
                if data.strip().startswith('{'):
                    json_data = json.loads(data)
                    is_json = True
            except json.JSONDecodeError:
                is_json = False

            if is_json:
                # 处理 JSON 格式
                encrypt_content = json_data.get("encrypt") or json_data.get("Encrypt")
                if not encrypt_content:
                    logger.error("Missing encrypt field in JSON")
                    return None
                
                # 构造伪 XML 以利用 wechatpy 进行解密
                # 注意：WeChatCrypto.decrypt_message 内部会解析 XML 提取 Encrypt 节点
                # 我们构造一个包含 Encrypt 节点的 XML
                fake_xml = f"<xml><ToUserName><![CDATA[{self.config.corp_id}]]></ToUserName><Encrypt><![CDATA[{encrypt_content}]]></Encrypt></xml>"
                decrypted_xml = self.crypto.decrypt_message(
                    fake_xml,
                    signature,
                    timestamp,
                    nonce
                )
            else:
                # 处理 XML 格式
                decrypted_xml = self.crypto.decrypt_message(
                    data,
                    signature,
                    timestamp,
                    nonce
                )
                
        except (InvalidSignatureException, InvalidCorpIdException) as e:
            logger.error(f"Failed to decrypt message: {e}")
            raise

        msg = parse_message(decrypted_xml)
        logger.info(f"Received message: {msg}")
            
        return msg

    def create_passive_reply(self, msg: Any, content: str, reply_format: str = "xml") -> Union[str, Dict[str, Any]]:
        """
        生成被动回复消息 (XML 格式且加密，或者 JSON 格式且加密)
        """
        reply = TextReply(content=content, message=msg)
        xml = reply.render()
        timestamp = str(int(time.time()))
        nonce = str(random.randint(100000, 999999))
        
        encrypted_xml = self.crypto.encrypt_message(xml, nonce, timestamp)
        
        if reply_format == "json":
            # 解析加密后的 XML，提取字段并构造 JSON
            try:
                root = ET.fromstring(encrypted_xml)
                encrypt_content = root.find("Encrypt").text
                msg_signature = root.find("MsgSignature").text
                
                return {
                    "encrypt": encrypt_content,
                    "msgsignature": msg_signature,
                    "timestamp": timestamp,
                    "nonce": nonce
                }
            except Exception as e:
                logger.error(f"Failed to convert encrypted XML to JSON: {e}")
                # Fallback to XML if conversion fails
                return encrypted_xml
        
        return encrypted_xml

    def send_text(self, user_id: str, content: str):
        """
        发送文本消息
        """
        if not self.client or not self.config.agent_id:
            logger.error("Active sending failed: corp_secret or agent_id is not configured")
            return None
            
        try:
            return self.client.message.send_text(
                self.config.agent_id,
                user_id,
                content
            )
        except Exception as e:
            logger.error(f"Failed to send text message: {e}")
            raise

    def send_image(self, user_id: str, media_id: str):
        """
        发送图片消息
        """
        if not self.client or not self.config.agent_id:
            logger.error("Active sending failed: corp_secret or agent_id is not configured")
            return None

        try:
            return self.client.message.send_image(
                self.config.agent_id,
                user_id,
                media_id
            )
        except Exception as e:
            logger.error(f"Failed to send image message: {e}")
            raise

    def upload_media(self, media_type: str, file_obj):
        """
        上传临时素材
        """
        if not self.client:
            logger.error("Media upload failed: corp_secret is not configured")
            return None

        try:
            return self.client.media.upload(media_type, file_obj)
        except Exception as e:
            logger.error(f"Failed to upload media: {e}")
            raise
