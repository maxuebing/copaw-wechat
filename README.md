# CoPaw WeChat (WeCom) 插件

这是一个用于 [CoPaw](https://github.com/agentscope/copaw) 的企业微信（WeCom）插件，实现了与企业微信自建应用的对接。

参考项目：[OpenClaw-Wechat](https://github.com/dingxiang-me/OpenClaw-Wechat)

## 功能特性

- **消息接收**：支持接收文本、图片、语音、视频、文件等类型的消息。
- **消息发送**：支持发送文本、图片消息。
- **安全验证**：自动处理企业微信的回调 URL 签名验证和消息加解密。
- **代理支持**：支持配置 HTTP/HTTPS 代理。

## 安装

1. **克隆源码**：
```bash
git clone git@github.com:maxuebing/copaw-wechat.git
cd copaw-wechat
```

2. **安装依赖**：
请确保将依赖安装到 CoPaw 运行的环境中。
```bash
pip install -r requirements.txt
```

3. **注册插件**：
将插件源码软链接或拷贝到 CoPaw 的自定义插件目录（注意：必须是 `custom_channels`）：
- **本地部署**：
```bash
mkdir -p ~/.copaw/custom_channels
ln -s $(pwd)/src/copaw_plugin_wechat ~/.copaw/custom_channels/wechat
```
- **Docker 部署**：
在 `docker-compose.yml` 中挂载目录：
```yaml
volumes:
  - ./src/copaw_plugin_wechat:/app/working/custom_channels/wechat
```

## 3. 安装依赖

由于 CoPaw 运行在独立的虚拟环境中，你需要将插件依赖安装到该环境中：

```bash
# 1. 确保安装了 pip (如果报错 "No module named pip")
curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
~/.copaw/venv/bin/python3 get-pip.py

# 2. 安装插件依赖
~/.copaw/venv/bin/python3 -m pip install -r requirements.txt
```

## 4. 故障排查（自检）

如果插件没有正常加载，可以使用本项目提供的自检脚本进行诊断：

```bash
# 运行诊断脚本
~/.copaw/venv/bin/python3 debug_copaw_setup.py
```

脚本会自动检查：
- Python 环境依赖是否齐全
- 插件目录软链接是否正确
- 插件代码是否能被正确导入
- `config.json` 中是否配置了 `wechat` 字段

## 5. 配置 CoPaw

CoPaw 启动后会加载插件。请在 `~/.copaw/config.json`（或 Docker 对应路径）的 `channels` 部分添加 `wechat` 配置项。

- **本地部署**：默认配置文件路径为 `~/.copaw/config.json`。
- **Docker 部署**：如果您使用的是官方 Docker 镜像并挂载了数据卷（如 `-v copaw-data:/app/working`），配置文件通常位于挂载卷对应的 `/app/working/config.json`（在宿主机上对应的路径取决于您的 Docker 卷配置）。

### 配置参数说明

| 参数名 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `corp_id` | str | 是 | 企业微信 Corp ID (对应企业微信后台的 企业ID) |
| `corp_secret` | str | 否 | 企业微信应用的 Secret (对应企业微信后台的 Secret)。**仅在需要主动发送消息（如流式回复）时必填** |
| `agent_id` | int | 否 | 企业微信应用的 Agent ID。**仅在需要主动发送消息时必填** |
| `token` | str | 是 | 回调 Token (对应企业微信后台的 Token) |
| `encoding_aes_key` | str | 是 | 回调 EncodingAESKey (对应企业微信后台的 EncodingAESKey) |
| `webhook_path` | str | 否 | Webhook 路径，默认为 `/wecom/callback` |
| `outbound_proxy` | str | 否 | HTTP 代理地址，例如 `http://127.0.0.1:7890` |

### 配置示例

```json
{
  "channels": {
    "wechat": {
      "enabled": true,
      "corp_id": "wwxxxxxxxxxxxxxxxx",
      "token": "xxxxxxxxxxxx",
      "encoding_aes_key": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
      "webhook_path": "/wecom/callback"
      // "corp_secret": "仅在主动发消息时需要",
      // "agent_id": 1000001
    }
  }
}
```

## 企业微信后台配置

该插件支持两种对接模式：**自建应用模式** 和 **智能机器人模式**。

### 模式 1：自建应用模式 (推荐)

这是最常用的模式，支持主动发送消息。

1. 登录 [企业微信管理后台](https://work.weixin.qq.com/wework_admin/frame)。
2. 进入 **应用管理** -> **应用** -> **自建** -> **创建应用**。
3. 获取 `AgentId` 和 `Secret`。
4. 在 **接收消息** 部分，点击 **设置 API 接收**。
   - **URL**: `http://your-server-ip:port/wecom/callback`
   - **Token**: 对应配置中的 `token`
   - **EncodingAESKey**: 对应配置中的 `encoding_aes_key`
5. 保存并验证。

### 模式 2：智能机器人模式 (更轻量)

如果您只需要简单的被动对话，可以使用“智能机器人”模式。在这种模式下，您可以不配置 `corp_secret`。

1. 登录 [企业微信管理后台](https://work.weixin.qq.com/wework_admin/frame)。
2. 进入 **应用管理** -> **机器人** (位于页面底部)。
3. 创建机器人并进入详情页。
4. 开启 **API 模式**。
5. 配置 **接收回调**：
   - **URL**: `http://your-server-ip:port/wecom/callback`
   - **Token** 和 **EncodingAESKey**: 填入插件配置中。
6. 注意：此模式下机器人只能通过“被动回复”进行对话，且响应必须在 5 秒内完成。配置时 `corp_secret` 和 `agent_id` 可留空。
