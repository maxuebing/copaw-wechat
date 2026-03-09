# CoPaw 企业微信渠道插件

[![PyPI](https://img.shields.io/pypi/v/copaw-wechat)](https://pypi.org/project/copaw-wechat/)
[![Python](https://img.shields.io/pypi/pyversions/copaw-wechat)](https://pypi.org/project/copaw-wechat/)
[![License](https://img.shields.io/pypi/l/copaw-wechat)](https://github.com/copaw/copaw-wechat/blob/main/LICENSE)

企业微信（WeCom）智能机器人渠道插件，用于 [CoPaw](https://copaw.agentscope.io/)。

## 功能特性

- 支持企业微信智能机器人消息接收
- 支持文本、图片、文件等多模态消息
- 支持单聊和群聊
- 支持引用消息
- 消息去重
- 访问控制（白名单）

## 安装

```bash
pip install copaw-wechat
```

## 配置

### 环境变量

| 环境变量 | 说明 | 必填 |
|----------|------|------|
| `WECOM_CHANNEL_ENABLED` | 是否启用 | 否 |
| `WECOM_CORP_ID` | 企业 ID | 是 |
| `WECOM_SECRET` | 应用 Secret | 是 |
| `WECOM_AIBOT_ID` | 智能机器人 ID | 是 |
| `WECOM_TOKEN` | 回调验证 Token | 是 |
| `WECOM_ENCODING_AES_KEY` | 加解密 Key（43 字符） | 是 |
| `WECOM_BOT_PREFIX` | 机器人前缀 | 否 |
| `WECOM_CALLBACK_HOST` | 回调服务器地址 | 否 |
| `WECOM_CALLBACK_PORT` | 回调服务器端口 | 否 |

### Config JSON

在 `~/.copaw/config.json` 中添加：

```json
{
  "channels": {
    "wecom": {
      "enabled": true,
      "corp_id": "ww123456",
      "secret": "your_secret",
      "aibot_id": "AIBOTID",
      "token": "your_token",
      "encoding_aes_key": "kWxPEV2UEDyxWpmyfnZero4FJfiPZOyP2JfV8LqMyj",
      "bot_prefix": "[BOT] ",
      "callback_host": "0.0.0.0",
      "callback_port": 8765
    }
  }
}
```

## 企业微信配置

### 1. 创建智能机器人

1. 登录企业微信管理后台
2. 进入「应用管理」→「应用」→「自建」
3. 创建应用，选择「智能机器人」能力

### 2. 配置回调

在应用详情页：

1. 进入「智能机器人」→「回调配置」
2. 填写回调 URL：`http://your-server:8765/wecom/callback`
3. 配置 Token 和 EncodingAESKey
4. 启用「接收消息」事件

### 3. 获取凭证

在「应用管理」→「应用」中获取：
- 企业 ID (corp_id)
- 应用 Secret (secret)
- 智能机器人 ID (aibot_id)

## 使用

启动 CoPaw 服务：

```bash
copaw app
```

## 开发

```bash
# 克隆仓库
git clone https://github.com/copaw/copaw-wechat.git
cd copaw-wechat

# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest

# 代码格式化
black .
ruff check .

# 类型检查
mypy .
```

## 许可证

MIT License

## 相关链接

- [CoPaw 官网](https://copaw.agentscope.io/)
- [CoPaw GitHub](https://github.com/modelscope/agentscope)
- [企业微信开发文档](https://developer.work.weixin.qq.com/)
