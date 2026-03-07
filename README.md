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
将插件源码软链接或拷贝到 CoPaw 的自定义插件目录（注意：必须是 `custom_channels`，不是 `plugins`）：
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
- 插件目录软链接是否正确（是否在 `custom_channels` 下）
- 插件代码是否能被正确导入
- 插件类是否正确继承自 `BaseChannel` 并实现了 `from_config`
- `config.json` 中是否配置了 `wechat` 字段

## 5. 配置 CoPaw

CoPaw 启动后会扫描 `custom_channels` 目录加载插件。请在 `~/.copaw/config.json`（或 Docker 对应路径）的 `channels` 部分添加 `wechat` 配置项。

**注意：配置必须放在 `channels` 字典下！**

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

## 6. 企业微信后台配置指南

为了让 CoPaw 能够接收并回复消息，您需要在企业微信后台完成配置。本插件支持两种工作模式：**全功能模式**（推荐）和 **轻量机器人模式**。

### 通用配置步骤（所有模式必做）

1.  **创建自建应用**：
    - 登录 [企业微信管理后台](https://work.weixin.qq.com/wework_admin/frame)。
    - 进入 **应用管理** -> **应用** -> **创建应用**。
    - 应用名称建议填写 **“CoPaw 助手”**。
    - 可见范围选择需要使用机器人的成员或部门。

2.  **开启 API 接收消息**：
    - 在应用详情页，找到 **“API 接收消息”** 栏，点击 **“设置 API 接收”**。
    - **URL**：填写您的服务器公网地址 + Webhook 路径。
      - 示例：`http://your-server-ip:port/wecom/callback`
    - **Token** & **EncodingAESKey**：随机获取，并填入 CoPaw 的 `config.json`。
    - 点击保存验证。

3.  **获取 CorpID**：
    - 在 **我的企业** -> **企业信息** 最下方找到。

### 模式选择与差异配置

#### 模式 A：全功能模式（推荐）
*   **特点**：支持主动发送消息、异步回复、无 5 秒超时限制，适合复杂的 AI 推理场景。
*   **额外配置**：
    - 获取应用的 **Secret** 和 **AgentId**。
    - 在 `config.json` 中填入 `corp_secret` 和 `agent_id`。

#### 模式 B：轻量机器人模式（智能机器人模式）
*   **特点**：配置简单，仅支持被动回复（用户发一句，机器人回一句）。
*   **配置**：无需 `corp_secret` 和 `agent_id`。
*   **限制**：**必须在 5 秒内完成回复**。如果 AI 思考时间过长，会导致回复失败。仅建议在简单的问答场景或调试时使用。
*   **注意**：在此模式下，请确保 CoPaw 的处理逻辑足够快。

