import logging

logger = logging.getLogger(__name__)

async def handle_message(msg):
    """
    处理微信消息
    目前仅处理文本消息，忽略其他类型
    """
    msg_type = msg.get("type") if isinstance(msg, dict) else getattr(msg, 'type', 'unknown')
    
    if msg_type == 'text':
        content = msg.get("content") if isinstance(msg, dict) else msg.content
        source = msg.get("source") if isinstance(msg, dict) else msg.source
        logger.info(f"Received text message from {source}: {content}")
        return {"type": "text", "content": content, "source": source}
    
    else:
        logger.warning(f"Ignored non-text message type: {msg_type}")
        return None
