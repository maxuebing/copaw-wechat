import logging
from fastapi import APIRouter, Request, HTTPException, Response
from typing import Optional, Callable, Dict, Any, Union
from pydantic import ValidationError
from wechatpy.messages import BaseMessage
from wechatpy.exceptions import InvalidSignatureException

from .config import WechatConfig
from .wechat_client import WechatClient
from .handlers import handle_message

logger = logging.getLogger(__name__)

class WechatPlugin:
    def __init__(self, config: WechatConfig):
        self.config = config
        self.client = WechatClient(config)
        self.router = APIRouter()
        self.agent_callback: Optional[Callable[[Dict[str, Any]], Union[None, str, Dict[str, Any]]]] = None
        
        self.setup_routes()

    def register_agent_callback(self, callback: Callable[[Dict[str, Any]], Union[None, str, Dict[str, Any]]]):
        """
        注册 Agent 回调函数，用于将消息传递给 CoPaw
        如果回调函数返回字符串，则插件会尝试进行“被动回复”。
        """
        self.agent_callback = callback

    def setup_routes(self):
        @self.router.get(self.config.webhook_path)
        async def verify_url(msg_signature: str, timestamp: str, nonce: str, echostr: str):
            """
            验证回调 URL (GET 请求)
            """
            try:
                echo_str = self.client.verify_signature(msg_signature, timestamp, nonce, echostr)
                return Response(content=echo_str, media_type="text/plain")
            except InvalidSignatureException:
                logger.error("Invalid signature")
                raise HTTPException(status_code=403, detail="Invalid signature")
            except Exception as e:
                logger.error(f"Verify URL failed: {e}")
                raise HTTPException(status_code=500, detail="Internal Server Error")

        @self.router.post(self.config.webhook_path)
        async def receive_message(request: Request, msg_signature: str, timestamp: str, nonce: str):
            """
            接收消息回调 (POST 请求)
            """
            try:
                xml_data = await request.body()
                msg = self.client.handle_message(msg_signature, timestamp, nonce, xml_data)
                
                if msg:
                    parsed_msg = await handle_message(msg)
                    if self.agent_callback:
                        # 触发回调并检查是否有被动回复内容
                        # 注意：被动回复必须在 5 秒内完成响应
                        reply_content = await self.agent_callback(parsed_msg)
                        
                        if reply_content and isinstance(reply_content, str):
                            encrypted_reply = self.client.create_passive_reply(msg, reply_content)
                            return Response(content=encrypted_reply, media_type="application/xml")
                        elif reply_content and isinstance(reply_content, dict) and reply_content.get("type") == "text":
                            encrypted_reply = self.client.create_passive_reply(msg, reply_content["content"])
                            return Response(content=encrypted_reply, media_type="application/xml")
                    
                    return Response(content="success", media_type="text/plain")
                else:
                    return Response(content="success", media_type="text/plain")
            except Exception as e:
                logger.error(f"Receive message failed: {e}")
                raise HTTPException(status_code=500, detail="Internal Server Error")

    async def send_text(self, to_user: str, content: str):
        """
        发送文本消息
        """
        return self.client.send_text(to_user, content)

    async def send_image(self, to_user: str, image_path: str):
        """
        发送图片消息
        """
        with open(image_path, 'rb') as f:
            media_id = self.client.upload_media('image', f)['media_id']
        return self.client.send_image(to_user, media_id)

def create_plugin(config_dict: dict) -> WechatPlugin:
    """
    创建插件实例
    """
    try:
        config = WechatConfig(**config_dict)
        return WechatPlugin(config)
    except ValidationError as e:
        logger.error(f"Invalid configuration: {e}")
        raise
