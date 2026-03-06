from typing import Optional, List
from pydantic import BaseModel, Field

class WechatConfig(BaseModel):
    """
    企业微信插件配置
    对应 OpenClaw-Wechat 的 configSchema
    """
    enabled: bool = Field(default=True, description="是否启用 WeCom 渠道")
    
    # 企业信息
    corp_id: str = Field(..., description="企业微信 Corp ID")
    corp_secret: str = Field(..., description="企业微信 Corp Secret")
    agent_id: int = Field(..., description="企业微信 Agent ID")
    
    # 回调配置
    token: str = Field(..., description="回调 Token")
    encoding_aes_key: str = Field(..., description="回调 EncodingAESKey")
    webhook_path: str = Field(default="/wecom/callback", description="Webhook 路径")
    
    # 代理配置 (可选)
    outbound_proxy: Optional[str] = Field(default=None, description="WeCom 出站 API 代理")
    
    # 消息处理配置
    bot_enabled: bool = Field(default=False, description="是否启用 Bot 模式")
    stream_enabled: bool = Field(default=False, description="是否启用流式回复")
