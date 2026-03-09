# CoPaw 企业微信渠道插件

企业微信（WeCom）智能机器人渠道插件，用于 [CoPaw](https://copaw.agentscope.io/)。

## 功能特性

- 支持企业微信智能机器人消息接收
- 支持文本、图片、文件等多模态消息
- 支持单聊和群聊
- 支持引用消息
- 消息去重
- 访问控制（白名单）

## 安装

### 方式一：软链接安装（推荐）

#### Ubuntu/Debian 系统

```bash
# 1. 克隆仓库
git clone https://github.com/maxuebing/copaw-wechat.git
cd copaw-wechat

# 2. 安装依赖（使用 --break-system-packages 或虚拟环境）
pip install --break-system-packages -r requirements.txt

# 3. 创建软链接到 CoPaw 自定义频道目录
ln -s $(pwd)/wecom ~/.copaw/custom_channels/wecom

# 4. 重启 CoPaw 服务
copow app
```

**或者使用虚拟环境（推荐）：**
```bash
# 创建虚拟环境
python3 -m venv ~/.venv/copaw-wechat
source ~/.venv/copaw-wechat/bin/activate

# 安装依赖
pip install -r requirements.txt

# 安装完成后，确保 CoPaw 能找到依赖包
pip install --break-system-packages -r requirements.txt
```

#### macOS 系统

```bash
# 1. 克隆仓库
git clone https://github.com/maxuebing/copaw-wechat.git
cd copaw-wechat

# 2. 安装依赖
pip install -r requirements.txt

# 3. 创建软链接
ln -s $(pwd)/wecom ~/.copaw/custom_channels/wecom

# 4. 重启 CoPaw 服务
copaw app
```

#### Windows 系统

```powershell
# 1. 克隆仓库
git clone https://github.com/maxuebing/copaw-wechat.git
cd copaw-wechat

# 2. 安装依赖
pip install -r requirements.txt

# 3. 创建软链接（需要管理员权限）
mklink /D "C:\Users\YourName\.copaw\custom_channels\wecom" "C:\path\to\copaw-wechat\wecom"

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
      "encoding_aes_key": "43字符的Base64密钥",
      "bot_prefix": "[BOT] "
    }
  }
}
```

### 企业微信后台配置

1. 创建智能机器人应用
2. 配置回调 URL: `http://your-server:8765/wecom/callback`
3. 设置 Token 和 EncodingAESKey
4. 启用「接收消息」事件

## 使用

启动 CoPaw 服务：

```bash
copaw app
```

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
├── channel.py       # WeComChannel 主类
├── constants.py     # 常量定义
├── crypto.py        # 加解密工具
├── utils.py         # 工具函数
└── config.py        # 配置类
```

## 依赖

- `aiohttp>=3.8.0` - HTTP 客户端和服务器
- `pycryptodome>=3.15.0` - 加解密库
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
sudo apt install python3-aiohttp python3-pycryptodome
```

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
- [企业微信开发文档](https://developer.work.weixin.qq.com/)
- [仓库地址](https://github.com/maxuebing/copaw-wechat)
