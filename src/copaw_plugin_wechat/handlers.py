import logging
from wechatpy.messages import TextMessage, ImageMessage, VoiceMessage, VideoMessage
# FileMessage 可能在某些版本不可用，暂时移除
# from wechatpy.messages import FileMessage
from wechatpy.events import SubscribeEvent, UnsubscribeEvent, ClickEvent, ViewEvent, LocationEvent

logger = logging.getLogger(__name__)

async def handle_message(msg):
    """
    处理不同类型的微信消息
    """
    if isinstance(msg, TextMessage):
        logger.info(f"Received text message from {msg.source}: {msg.content}")
        return {"type": "text", "content": msg.content, "source": msg.source}
    
    elif isinstance(msg, ImageMessage):
        logger.info(f"Received image message from {msg.source}: {msg.image}")
        return {"type": "image", "content": msg.image, "source": msg.source}
    
    elif isinstance(msg, VoiceMessage):
        logger.info(f"Received voice message from {msg.source}: {msg.media_id}")
        return {"type": "voice", "content": msg.media_id, "source": msg.source}
    
    elif isinstance(msg, VideoMessage):
        logger.info(f"Received video message from {msg.source}: {msg.media_id}")
        return {"type": "video", "content": msg.media_id, "source": msg.source}
    
    # elif isinstance(msg, FileMessage):
    #     logger.info(f"Received file message from {msg.source}: {msg.media_id}")
    #     return {"type": "file", "content": msg.media_id, "source": msg.source}

    # 事件处理
    elif isinstance(msg, SubscribeEvent):
        logger.info(f"User subscribed: {msg.source}")
        return {"type": "event", "event": "subscribe", "source": msg.source}

    elif isinstance(msg, UnsubscribeEvent):
        logger.info(f"User unsubscribed: {msg.source}")
        return {"type": "event", "event": "unsubscribe", "source": msg.source}
    
    elif isinstance(msg, ClickEvent):
        logger.info(f"Menu click event: {msg.key} from {msg.source}")
        return {"type": "event", "event": "click", "key": msg.key, "source": msg.source}

    elif isinstance(msg, ViewEvent):
        logger.info(f"Menu view event: {msg.url} from {msg.source}")
        return {"type": "event", "event": "view", "url": msg.url, "source": msg.source}
    
    elif isinstance(msg, LocationEvent):
        logger.info(f"Location event from {msg.source}")
        return {"type": "event", "event": "location", "latitude": msg.latitude, "longitude": msg.longitude, "source": msg.source}
    
    else:
        logger.warning(f"Received unknown message type: {type(msg)}")
        return {"type": "unknown", "content": str(msg), "source": msg.source}
