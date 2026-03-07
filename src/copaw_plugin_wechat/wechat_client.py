import logging
import json
import xml.etree.ElementTree as ET
from typing import Optional, Dict, Any, Union
from wechatpy.enterprise import WeChatClient as BaseWeChatClient
# from wechatpy.enterprise.crypto import WeChatCrypto
from .wechat_msg_crypt import WechatMsgCrypt
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
        
        self.crypto = WechatMsgCrypt(
            self.config.token,
            self.config.encoding_aes_key,
            self.config.corp_id
        )

    def verify_signature(self, signature: str, timestamp: str, nonce: str, echostr: str) -> str:
        """
        验证回调 URL 签名
        """
        try:
            return self.crypto.verify_url(
                signature,
                timestamp,
                nonce,
                echostr
            )
        except Exception as e:
            logger.error(f"Verify signature failed: {e}")
            raise InvalidSignatureException()

    def handle_message(self, signature: str, timestamp: str, nonce: str, data: Union[str, bytes]) -> Optional[Dict[str, Any]]:
        """
        处理接收到的消息
        1. 解密消息
        2. 解析 XML 或 JSON
        """
        try:
            if isinstance(data, bytes):
                data = data.decode('utf-8')

            # 尝试判断是否为 JSON
            is_json = False
            json_data = {}
            try:
                if data.strip().startswith('{'):
                    json_data = json.loads(data)
                    is_json = True
            except json.JSONDecodeError:
                is_json = False

            decrypted_content = None
            if is_json:
                # 处理 JSON 格式
                encrypt_content = json_data.get("encrypt") or json_data.get("Encrypt")
                if not encrypt_content:
                    logger.error("Missing encrypt field in JSON")
                    return None
                
                # 直接使用 WechatMsgCrypt 解密
                ret, decrypted_content = self.crypto.decrypt_msg(encrypt_content)
                if ret != 0:
                     logger.error("Decrypt message failed")
                     return None
            else:
                # 处理 XML 格式
                # 提取 Encrypt 字段
                try:
                    root = ET.fromstring(data)
                    encrypt_content = root.find("Encrypt").text
                    ret, decrypted_content = self.crypto.decrypt_msg(encrypt_content)
                    if ret != 0:
                        logger.error("Decrypt message failed")
                        return None
                except Exception as e:
                    logger.error(f"Parse XML failed: {e}")
                    return None

        except Exception as e:
            logger.error(f"Failed to decrypt message: {e}")
            raise

        logger.info(f"Decrypted content: {decrypted_content}")
        
        # 解析解密后的内容
        # 如果是 XML 字符串，使用 wechatpy.parse_message
        # 如果是 JSON 字符串，解析为 dict 并尝试转换为 wechatpy message 对象（如果需要）
        # 目前 copaw 逻辑是后续 handle_message 需要 message 对象
        
        msg = None
        if decrypted_content.strip().startswith('<'):
            msg = parse_message(decrypted_content)
        elif decrypted_content.strip().startswith('{'):
            # JSON 格式的消息内容
            # 这里需要适配，因为 copaw 下游可能期待 wechatpy 的 Message 对象
            # 暂时先尝试解析为 dict，然后手动构造一个类似的 object 或者 TextMessage
            msg_dict = json.loads(decrypted_content)
            # 简单的适配：构造一个名为 object 的类
            class DictToObj:
                def __init__(self, **entries):
                    self.__dict__.update(entries)
                    self.type = entries.get("msgtype", "text") # default text
                    self.id = entries.get("msgid", 0)
                    self.source = entries.get("FromUserName") or entries.get("from", {}).get("userid")
                    self.target = entries.get("ToUserName") or entries.get("to")
                    self.create_time = int(time.time()) # approx
                    
                    if self.type == 'text':
                         self.content = entries.get("text", {}).get("content", "")
            
            msg = DictToObj(**msg_dict)
        
        logger.info(f"Received message object: {msg}")
        return msg

    def create_passive_reply(self, msg: Any, content: str, reply_format: str = "xml") -> Union[str, Dict[str, Any]]:
        """
        生成被动回复消息 (XML 格式且加密，或者 JSON 格式且加密)
        """
        # 构造回复 JSON
        timestamp = str(int(time.time()))
        nonce = str(random.randint(100000, 999999))
        
        if reply_format == "json":
            # 构造 JSON 回复体
            reply_dict = {
                "msgtype": "text",
                "text": {
                    "content": content
                }
            }
            reply_json_str = json.dumps(reply_dict, ensure_ascii=False)
            # singularity-ai 的 encrypt_msg 生成的是 JSON 格式的加密包
            encrypted_json_str = self.crypto.encrypt_msg(reply_json_str, nonce, timestamp)
            if not encrypted_json_str:
                logger.error("Failed to encrypt JSON reply")
                return ""
            return json.loads(encrypted_json_str)
        else:
            # XML 回复
            reply = TextReply(content=content, message=msg)
            xml_content = reply.render()
            
            # 手动加密 XML
            # 我们直接调用内部的 PrpCrypt 加密
            from .wechat_msg_crypt import PrpCrypt, Sha1
            pc = PrpCrypt(self.crypto.key)
            # receive_id 通常是 CorpID
            ret, encrypt = pc.encrypt(xml_content, self.crypto.receive_id)
            if ret != 0:
                logger.error("Failed to encrypt XML reply")
                return ""
            
            if isinstance(encrypt, bytes):
                encrypt = encrypt.decode('utf-8')

            sha1 = Sha1()
            ret, signature = sha1.get_sha1(self.config.token, timestamp, nonce, encrypt)
            if ret != 0:
                 logger.error("Failed to generate signature for XML reply")
                 return ""

            # 构造加密后的 XML
            encrypted_xml = f"""<xml>
<Encrypt><![CDATA[{encrypt}]]></Encrypt>
<MsgSignature><![CDATA[{signature}]]></MsgSignature>
<TimeStamp>{timestamp}</TimeStamp>
<Nonce><![CDATA[{nonce}]]></Nonce>
</xml>"""
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
