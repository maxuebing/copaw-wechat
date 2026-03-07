from typing import Optional, List
from pydantic import BaseModel, Field

class WechatConfig(BaseModel):
    """
    企业微信插件配置
    专注于企业内部开发-服务端API-智能机器人
    """
    enabled: bool = Field(default=True, description="是否启用 WeCom 渠道")
    
    # 企业信息
    corp_id: str = Field(..., description="企业微信 Corp ID (必填)")
    # corp_secret: Optional[str] = Field(default=None, description="企业微信 Corp Secret (可选，暂未启用)")
    # agent_id: Optional[int] = Field(default=None, description="企业微信 Agent ID (可选，暂未启用)")
    
    # 回调配置
    token: str = Field(..., description="回调 Token")
    encoding_aes_key: str = Field(..., description="回调 EncodingAESKey")
    webhook_path: str = Field(default="/wecom/callback", description="Webhook 路径")
    
    # 代理配置 (可选)
    outbound_proxy: Optional[str] = Field(default=None, description="WeCom 出站 API 代理")
    
    # 消息处理配置
    bot_enabled: bool = Field(default=False, description="是否启用 Bot 模式")
    stream_enabled: bool = Field(default=False, description="是否启用流式回复")
