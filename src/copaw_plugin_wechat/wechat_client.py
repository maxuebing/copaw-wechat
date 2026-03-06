import logging
from typing import Optional, Dict, Any
from wechatpy.enterprise import WeChatClient as BaseWeChatClient
from wechatpy.enterprise.crypto import WeChatCrypto
from wechatpy.exceptions import InvalidSignatureException
from wechatpy.enterprise.exceptions import InvalidCorpIdException
from wechatpy.messages import parse_message
from wechatpy.replies import TextReply
import requests

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

    def handle_message(self, signature: str, timestamp: str, nonce: str, xml_data: str) -> Optional[Dict[str, Any]]:
        """
        处理接收到的消息
        1. 验证签名
        2. 解密消息
        3. 解析 XML
        """
        try:
            decrypted_xml = self.crypto.decrypt_message(
                xml_data,
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
