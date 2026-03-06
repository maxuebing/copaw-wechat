# CoPaw WeChat (WeCom) 插件

这是一个用于 [CoPaw](https://github.com/agentscope/copaw) 的企业微信（WeCom）插件，实现了与企业微信自建应用的对接。

参考项目：[OpenClaw-Wechat](https://github.com/dingxiang-me/OpenClaw-Wechat)

## 功能特性

- **消息接收**：支持接收文本、图片、语音、视频、文件等类型的消息。
- **消息发送**：支持发送文本、图片消息。
- **安全验证**：自动处理企业微信的回调 URL 签名验证和消息加解密。
- **代理支持**：支持配置 HTTP/HTTPS 代理。

## 安装

1. 确保已安装 Python 3.8+。
2. 克隆仓库并安装：

```bash
git clone git@github.com:maxuebing/copaw-wechat-bot.git
cd copaw-wechat-bot
pip install -r requirements.txt
pip install .
```

## 配置

CoPaw 会在工作目录下生成配置文件（默认为 `~/.copaw/config.json`）。请在 `channels` 部分添加 `wechat` 配置项。

### 配置参数说明

| 参数名 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `corp_id` | str | 是 | 企业微信 Corp ID |
| `corp_secret` | str | 是 | 企业微信 Corp Secret |
| `agent_id` | int | 是 | 企业微信 Agent ID |
| `token` | str | 是 | 回调 Token (对应企业微信后台的 Token) |
| `encoding_aes_key` | str | 是 | 回调 EncodingAESKey (对应企业微信后台的 EncodingAESKey) |
| `webhook_path` | str | 否 | Webhook 路径，默认为 `/wecom/callback` |
| `outbound_proxy` | str | 否 | HTTP 代理地址，例如 `http://127.0.0.1:7890` |
| `allow_from` | list | 否 | 允许发送消息的用户 ID 列表（白名单） |

### 配置示例

```json
{
  "channels": {
    "wechat": {
      "enabled": true,
      "corp_id": "wwxxxxxxxxxxxxxxxx",
      "corp_secret": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
      "agent_id": 1000001,
      "token": "xxxxxxxxxxxx",
      "encoding_aes_key": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
      "webhook_path": "/wecom/callback",
      "allow_from": ["user1", "user2"]
    }
  }
}
```

## 使用方法

### 1. 初始化插件

```python
from copaw_plugin_wechat import create_plugin

config = {
    "corp_id": "wwxxxxxxxxxxxxxxxx",
    "corp_secret": "your_secret",
    "agent_id": 1000001,
    "token": "your_token",
    "encoding_aes_key": "your_aes_key"
}

plugin = create_plugin(config)
```

### 2. 注册到 FastAPI 应用

CoPaw 使用 FastAPI 作为 Web 框架，你需要将插件的路由注册到主应用中。

```python
from fastapi import FastAPI

app = FastAPI()
app.include_router(plugin.router)
```

### 3. 处理接收到的消息

注册回调函数来处理接收到的消息：

```python
async def on_message(msg):
    print(f"Received message: {msg}")
    # 在这里调用 CoPaw 的 Agent 进行处理
    # response = await agent.process(msg['content'])
    # await plugin.send_text(msg['source'], response)

plugin.register_agent_callback(on_message)
```

## 企业微信后台配置

1. 登录 [企业微信管理后台](https://work.weixin.qq.com/wework_admin/frame)。
2. 进入 **应用管理** -> **自建** -> **创建应用**。
3. 获取 `AgentId` and `Secret`。
4. 在 **接收消息** 部分，点击 **设置 API 接收**。
   - **URL**: `http://your-server-ip:port/wecom/callback` (注意替换为你实际部署的 IP 和端口，以及配置的 `webhook_path`)
   - **Token**: 对应配置中的 `token`
   - **EncodingAESKey**: 对应配置中的 `encoding_aes_key`
5. 点击 **保存**，企业微信会发送 GET 请求验证 URL，如果插件运行正常且配置正确，将会验证通过。
