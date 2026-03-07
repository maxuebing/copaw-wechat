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
    msg_type = getattr(msg, 'type', 'unknown')
    
    if msg_type == 'text':
        logger.info(f"Received text message from {msg.source}: {msg.content}")
        return {"type": "text", "content": msg.content, "source": msg.source}
    
    elif msg_type == 'image':
        logger.info(f"Received image message from {msg.source}: {msg.image}")
        return {"type": "image", "content": msg.image, "source": msg.source}
    
    elif msg_type == 'voice':
        logger.info(f"Received voice message from {msg.source}: {msg.media_id}")
        return {"type": "voice", "content": msg.media_id, "source": msg.source}
    
    elif msg_type == 'video':
        logger.info(f"Received video message from {msg.source}: {msg.media_id}")
        return {"type": "video", "content": msg.media_id, "source": msg.source}
    
    # elif msg_type == 'file':
    #     logger.info(f"Received file message from {msg.source}: {msg.media_id}")
    #     return {"type": "file", "content": msg.media_id, "source": msg.source}

    # 事件处理
    elif msg_type == 'event':
        event_type = getattr(msg, 'event', 'unknown')
        if event_type == 'subscribe':
            logger.info(f"User subscribed: {msg.source}")
            return {"type": "event", "event": "subscribe", "source": msg.source}

        elif event_type == 'unsubscribe':
            logger.info(f"User unsubscribed: {msg.source}")
            return {"type": "event", "event": "unsubscribe", "source": msg.source}
        
        elif event_type == 'click':
            logger.info(f"Menu click event: {msg.key} from {msg.source}")
            return {"type": "event", "event": "click", "key": msg.key, "source": msg.source}

        elif event_type == 'view':
            logger.info(f"Menu view event: {msg.url} from {msg.source}")
            return {"type": "event", "event": "view", "url": msg.url, "source": msg.source}
        
        elif event_type == 'location':
            logger.info(f"Location event from {msg.source}")
            return {"type": "event", "event": "location", "latitude": msg.latitude, "longitude": msg.longitude, "source": msg.source}
    
    else:
        logger.warning(f"Received unknown message type: {type(msg)}")
        return {"type": "unknown", "content": str(msg), "source": getattr(msg, 'source', 'unknown')}
