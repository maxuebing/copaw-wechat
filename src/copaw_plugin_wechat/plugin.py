import logging
import os
from fastapi import APIRouter, Request, HTTPException, Response

# 核武器级调试：只要文件被加载，就写文件
with open(os.path.expanduser("~/copaw_plugin_debug.log"), "a") as f:
    f.write("WechatPlugin module loaded by Python interpreter!\n")

from typing import Optional, Callable, Dict, Any, Union, List
from pydantic import ValidationError
from wechatpy.messages import BaseMessage
from wechatpy.exceptions import InvalidSignatureException

# 修正导入路径：从 copaw.app.channels.base 导入
try:
    from copaw.app.channels.base import BaseChannel
    with open(os.path.expanduser("~/copaw_plugin_debug.log"), "a") as f:
        f.write("BaseChannel imported successfully!\n")
except ImportError as e:
    with open(os.path.expanduser("~/copaw_plugin_debug.log"), "a") as f:
        f.write(f"BaseChannel import failed: {e}\n")
    # 兼容本地开发环境可能没有 copaw 包的情况
    class BaseChannel:
        def __init__(self, config: Any): pass
        async def start(self): pass
        async def stop(self): pass
        async def send_message(self, message: Dict[str, Any]): pass
        def register_agent_callback(self, callback: Callable): pass

from .config import WechatConfig
from .wechat_client import WechatClient
from .handlers import handle_message

logger = logging.getLogger(__name__)

class WechatPlugin(BaseChannel):
    channel = "wechat"
    
    def __init__(self, config: WechatConfig):
        with open(os.path.expanduser("~/copaw_plugin_debug.log"), "a") as f:
            f.write(f"WechatPlugin initialized with config: {config}\n")
        self.config = config
        self.client = WechatClient(config)
        self.router = APIRouter()
        self.agent_callback: Optional[Callable[[Dict[str, Any]], Union[None, str, Dict[str, Any]]]] = None
        
        self.setup_routes()

    async def start(self):
        """
        启动插件，通常用于初始化连接或后台任务
        对于 Webhook 类型的插件，路由注册在 __init__ 中已完成
        """
        logger.info(f"WechatPlugin started with config: corp_id={self.config.corp_id}")

    async def stop(self):
        """
        停止插件
        """
        logger.info("WechatPlugin stopped")

    async def send_message(self, message: Dict[str, Any]):
        """
        实现基类的发送消息方法，供 CoPaw 核心调用
        message 格式通常包含:
        - content: 消息内容
        - receiver: 接收者 ID (user_id)
        - type: 消息类型 (text, image 等)
        """
        try:
            receiver = message.get("receiver")
            content = message.get("content")
            msg_type = message.get("type", "text")

            if not receiver:
                logger.error("Send message failed: receiver is missing")
                return

            if msg_type == "text":
                if content:
                    await self.send_text(receiver, content)
            elif msg_type == "image":
                # 暂时只支持文本，后续可扩展
                logger.warning(f"Unsupported message type for now: {msg_type}")
            else:
                logger.warning(f"Unknown message type: {msg_type}")
        except Exception as e:
            logger.error(f"Failed to send message: {e}")

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
