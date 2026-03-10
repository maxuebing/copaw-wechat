# CoPaw 企业微信渠道插件

企业微信（WeCom）智能机器人渠道插件，用于 [CoPaw](https://copaw.agentscope.io/)。

## 功能特性

- **WebSocket 长连接**：无需公网 IP，内网友好
- 无需消息加解密
- 支持文本、图片、文件等多模态消息
- **自动解密企业微信图片**：使用消息中的 `aeskey` 自动解密加密图片
- 支持单聊和群聊
- 自动重连和心跳保活
- 访问控制（白名单）

## 更新日志

### v2.1.9
- **修复**: 修复 `mixed` 类型消息中图片未获取 `aeskey` 导致无法解密的问题。

### v2.1.8
- **新增**: 支持企业微信图片自动解密。从消息中的 `image.aeskey` 字段获取解密密钥，无需额外配置。
- **修复**: 彻底解决企业微信图片加密导致的 `The image format is illegal and cannot be opened` 错误。

### v2.1.7
- **新增**: 支持企业微信图片解密（AES-256-CBC）。如果图片被加密，插件会自动使用配置的 `encoding_aes_key` 解密。
- **新增**: 新增 `encoding_aes_key` 配置参数（43位字符），用于解密企业微信图片。
- **修复**: 彻底解决企业微信图片加密导致的 `The image format is illegal and cannot be opened` 错误。

### v2.1.4
- **修复**: 自动检测图片格式（通过文件头识别），修复企业微信图片强制使用 `image/jpeg` 导致的 `InvalidParameter: The image format is illegal and cannot be opened` 错误。

### v2.1.3
- **增强**: 增强图片路径处理，确保所有本地路径都转换为 Base64，防止 API 报错。

### v2.1.1
- **修复**: 将本地缓存的图片转换为 Base64 Data URL 传递给 CoPaw，解决了 AI 模型（如 OpenAI）无法访问本地文件路径导致的 `InternalError`。

### v2.1.0
- **新增**: 引入本地媒体缓存机制（`~/.copaw/media/wecom`）。
- **修复**: 彻底解决企业微信图片 URL 缺少扩展名导致 AgentScope/OpenAI 校验报错的问题（通过在本地保存时强制添加 `.jpg` 后缀）。
- **优化**: 同时支持图片和普通文件的本地缓存与自动后缀识别。

### v2.0.2
- **修复**: 尝试通过 `#.jpg` 锚点解决扩展名问题（已在 v2.1.0 中被更可靠的本地缓存方案替代）。

### v2.0.1
- **修复**: 解决 `aibot_respond_msg` 回复 `40008` (invalid message type) 错误，统一使用 `markdown` 类型发送。
- **优化**: 增加 WebSocket 消息解析的健壮性，处理 `ServerTimeoutError` 异常。
- **增强**: 增加跨线程发送消息的运行状态检查与回调日志。

### v2.0.0
- **新增**: 实现企业微信智能机器人 WebSocket 长连接模式。

<img width="1603" height="800" alt="image" src="https://github.com/user-attachments/assets/84dbd2dc-d362-4eb1-bfc9-3b17f1b1d9c2" />


## 安装

### 方式一：软链接安装（推荐）

```bash
# 1. 克隆仓库
git clone https://github.com/maxuebing/copaw-wechat.git
cd copaw-wechat

# 2. 安装依赖
pip install -r requirements.txt

# 3. 创建软链接到 CoPaw 自定义频道目录
ln -s $(pwd)/wecom ~/.copaw/custom_channels/wecom

# 4. 重启 CoPaw 服务
copaw app
```

### 方式二：直接复制

```bash
# 1. 克隆仓库
git clone https://github.com/maxuebing/copaw-wechat.git
cd copaw-wechat

# 2. 复制到 CoPaw 自定义频道目录
cp -r wecom ~/.copaw/custom_channels/

# 3. 安装依赖
pip install -r requirements.txt

# 4. 重启 CoPaw 服务
copaw app
```

## 配置

### 企业微信后台配置

1. 进入智能机器人管理后台
2. 开启「API 模式」并选择「长连接」
3. 获取 **BotID** 和 **Secret**（长连接专用）

### Config JSON

在 `~/.copaw/config.json` 中添加：

```json
{
  "channels": {
    "wecom": {
      "enabled": true,
      "bot_id": "YOUR_BOT_ID",
      "secret": "YOUR_SECRET",
      "encoding_aes_key": "YOUR_ENCODING_AES_KEY",
      "bot_prefix": "[BOT] "
    }
  }
}
```

### 配置说明

| 字段 | 说明 | 必填 | 默认值 |
|------|------|------|--------|
| `enabled` | 是否启用 | 否 | `false` |
| `bot_id` | 智能机器人 BotID | 是 | - |
| `secret` | 长连接专用密钥 | 是 | - |
| `encoding_aes_key` | 消息加密密钥（43位），用于解密图片（可选，通常自动从消息获取） | 否 | `""` |
| `bot_prefix` | 机器人回复前缀 | 否 | `"[BOT] "` |
| `dm_policy` | 私聊策略 | 否 | `"open"` |
| `group_policy` | 群聊策略 | 否 | `"open"` |
| `allow_from` | 白名单用户 ID 列表 | 否 | `[]` |
| `deny_message` | 拒绝消息 | 否 | `""` |

> **注意**: `encoding_aes_key` 是可选的。企业微信长连接模式会自动在消息中发送 `image.aeskey` 字段，插件会使用此密钥自动解密图片。只有在特殊情况下才需要手动配置此参数。

## 验证安装

```bash
# 查看软链接
ls -la ~/.copaw/custom_channels/wecom

# 查看 CoPaw 识别的频道
copaw channels list
```

## 目录结构

```
wecom/
├── __init__.py      # 包入口，导出 WeComChannel
├── channel.py       # WeComChannel 主类（WebSocket 长连接）
├── constants.py     # 常量定义
└── utils.py         # 工具函数
```

## 依赖

- `aiohttp>=3.8.0` - HTTP 客户端和 WebSocket
- `agentscope-runtime` - CoPaw 运行时

## 常见问题

### Ubuntu/Debian 系统 `externally-managed-environment` 错误

这是 Python 3.11+ 的保护机制，有以下解决方案：

**方案 1：使用 --break-system-packages（简单但不推荐）**
```bash
pip install --break-system-packages -r requirements.txt
```

**方案 2：使用虚拟环境（推荐）**
```bash
python3 -m venv ~/.venv/copaw
source ~/.venv/copaw/bin/activate
pip install -r requirements.txt
```

**方案 3：使用系统包管理器**
```bash
sudo apt install python3-aiohttp
```

### 连接失败

1. 确认 BotID 和 Secret 正确
2. 确认企业微信后台已开启「长连接 API 模式」
3. 检查网络连接是否正常
4. 查看日志获取详细错误信息

### 软链接创建失败

如果 `ln -s` 命令失败，确保目标目录存在：
```bash
mkdir -p ~/.copaw/custom_channels
ln -s $(pwd)/wecom ~/.copaw/custom_channels/wecom
```

## 卸载

```bash
# 删除软链接
rm ~/.copaw/custom_channels/wecom

# 或删除复制的目录
rm -rf ~/.copaw/custom_channels/wecom

# 重启 CoPaw 服务
copaw app
```

## 许可证

MIT License

## 相关链接

- [CoPaw 官网](https://copaw.agentscope.io/)
- [CoPaw GitHub](https://github.com/modelscope/agentscope)
- [企业微信智能机器人长连接文档](https://developer.work.weixin.qq.com/document/path/101463)
- [仓库地址](https://github.com/maxuebing/copaw-wechat)

