# 贡献指南

感谢您对 CoPaw 企业微信渠道插件的关注！

## 开发环境设置

```bash
# 克隆仓库
git clone https://github.com/copaw/copaw-wechat.git
cd copaw-wechat

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装开发依赖
pip install -e ".[dev]"

# 安装 CoPaw（用于测试）
pip install copaw
```

## 运行测试

```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/test_crypto.py

# 生成覆盖率报告
pytest --cov=copaw_wechat --cov-report=html
```

## 代码格式化

```bash
# 格式化代码
black .

# 检查代码规范
ruff check .

# 类型检查
mypy .
```

## 提交代码

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add some amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

### 提交消息格式

请遵循以下格式：

```
<type>: <subject>

<body>

<footer>
```

类型：
- `feat`: 新功能
- `fix`: 修复 bug
- `docs`: 文档更新
- `style`: 代码格式
- `refactor`: 重构
- `test`: 测试
- `chore`: 构建/工具链

## 问题报告

请使用 [GitHub Issues](https://github.com/copaw/copaw-wechat/issues) 报告问题。

报告问题时请提供：
- CoPaw 版本
- Python 版本
- 操作系统
- 详细的问题描述和复现步骤
- 相关的日志或错误信息
