# Rule-Bot

一个专门管理 Clash 规则的 Telegram 机器人，支持域名查询、添加直连规则等功能。通过智能检测和自动管理，帮助用户轻松维护 Clash 的直连规则列表。

## ⚡ 快速开始

1. **克隆项目**
```bash
git clone https://github.com/your-username/Rule-Bot.git
cd Rule-Bot
```

2. **配置环境变量**
编辑 `docker-compose.yml`，填入您的配置信息

3. **启动服务**
```bash
docker-compose up -d
```

4. **开始使用**
在 Telegram 中找到您的机器人，发送 `/start` 开始使用

## 🚀 功能特性

### 📋 域名管理
- ✅ 域名查询：检查域名是否已在规则中
- ✅ 域名添加：支持多种 URL 格式，自动提取二级域名
- ✅ 智能提取：支持完整 URL、带端口、带路径等格式
- ✅ 重复检测：防止重复添加相同域名
- ✅ **Commit 链接**：成功添加后提供 GitHub commit 链接
- ❌ **.cn 域名限制**：**.cn 域名默认直连，不可手动添加**

### 🔍 智能检测
- ✅ GitHub 规则检查：检查域名是否已在直连规则中
- ✅ GEOSITE:CN 检查：检查域名是否已在中国直连列表中
- ✅ DNS 解析检查：检查域名 IP 是否在中国大陆
- ✅ NS 服务器检查：检查域名 NS 服务器位置
- ✅ 智能建议：根据检查结果提供添加建议

### 🛡️ 访问控制
- ✅ **群组验证**：可要求用户加入指定 Telegram 群组才能使用
- ✅ 可配置启用/禁用群组验证功能
- ✅ 自动提示用户加入群组

### 📊 数据统计
- ✅ 实时统计：显示当前规则数量和 GEOSITE 域名数量
- ✅ 自动更新：定时更新 GeoIP 和 GEOSITE 数据

### 🔧 系统特性
- ✅ Docker 部署：完整的 Docker Compose 配置
- ✅ 环境配置：通过环境变量进行配置
- ✅ 自动重启：容器异常时自动重启
- ✅ 日志记录：详细的操作日志

## ⚙️ 配置选项

### 🔐 群组验证配置
```yaml
# 群组验证 (可选: 要求用户加入指定群组才能使用机器人)
# 留空则关闭此功能
- REQUIRED_GROUP_ID=your_group_id_here
- REQUIRED_GROUP_NAME=Your Group Name
- REQUIRED_GROUP_LINK=https://t.me/your_group_link
```

### 📝 域名格式支持
```
✅ 支持的格式：
• example.com
• www.example.com
• https://example.com
• https://www.example.com/path/to/page
• sub.example.com
• ftp://example.com
• example.com:8080
• https://sub.example.com/page?param=value#anchor

❌ 不支持的格式：
• *.cn 域名（默认直连，不可添加）
```

## 🚦 添加规则逻辑

1. **格式检查**：验证输入格式，提取二级域名
2. **域名限制**：拒绝 .cn 域名添加
3. **重复检查**：检查 GitHub 规则和 GEOSITE:CN 中是否已存在
4. **智能判断**：
   - 域名 IP 在中国大陆 → 直接添加
   - 域名 IP 不在中国，但 NS 在中国 → 直接添加  
   - 域名 IP 和 NS 都不在中国 → 拒绝添加

## 🎯 Commit 格式

所有操作都会在 GitHub 上创建规范的 commit 记录：

```
标题: Add direct domain example.com by Telegram Bot (@username)
描述: 用户提供的域名描述（可选）
```

```
标题: Remove direct domain example.com by Telegram Bot (@username)
描述: (空)
```

## 部署方式

### 环境要求
- Docker 20.10+
- Docker Compose 2.0+
- Python 3.11+ (本地开发)

### 快速部署

1. **克隆项目**
```bash
git clone https://github.com/your-username/Rule-Bot.git
cd Rule-Bot
```

2. **配置参数**

编辑 `docker-compose.yml` 文件，在 environment 部分填入您的配置：

```yaml
environment:
  # ========== 请在下方填入您的配置 ==========
  # Telegram Bot Token (从 @BotFather 获取)
  - TELEGRAM_BOT_TOKEN=你的机器人 Token
  
  # GitHub Personal Access Token (需要 repo 权限)
  - GITHUB_TOKEN=你的 GitHub Token
  
  # GitHub Repository (格式: 用户名/仓库名)
  - GITHUB_REPO=your_username/your_repository_name
  
  # 直连规则文件路径 (相对于仓库根目录)
  - DIRECT_RULE_FILE=your_direct_rule_file_path
  
  # 代理规则文件路径 (可选，暂不使用)
  - PROXY_RULE_FILE=your_proxy_rule_file_path
  
  # 日志级别 (可选: DEBUG, INFO, WARNING, ERROR)
  - LOG_LEVEL=INFO
  # ========================================
```

3. **启动服务**
```bash
docker-compose up -d
```

4. **查看日志**
```bash
docker-compose logs -f rule-bot
```

### 配置说明

#### Telegram Bot Token
1. 向 [@BotFather](https://t.me/BotFather) 发送 `/newbot`
2. 按照提示创建机器人
3. 复制获得的 token

#### GitHub Token
1. 访问 [GitHub Settings > Personal access tokens](https://github.com/settings/tokens)
2. 点击 "Generate new token (classic)"
3. 选择 `repo` 权限
4. 复制生成的 token

#### 配置项详细说明

| 配置项 | 说明 | 示例 |
|--------|------|------|
| `TELEGRAM_BOT_TOKEN` | Telegram 机器人 Token | `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11` |
| `GITHUB_TOKEN` | GitHub 个人访问令牌 | `ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` |
| `GITHUB_REPO` | 目标 GitHub 仓库 | `your_username/your_repository_name` |
| `DIRECT_RULE_FILE` | 直连规则文件路径 | `your_direct_rule_file_path` |
| `PROXY_RULE_FILE` | 代理规则文件路径 | `your_proxy_rule_file_path` |
| `LOG_LEVEL` | 日志级别 | `INFO` |

#### 权限要求
- GitHub token 需要对目标仓库的 **write** 权限
- 机器人会自动创建 commit 来添加规则
- 如果要修改其他人的仓库，需要先 Fork 到自己账号下

## 使用方法

### 基本命令
- `/start` - 开始使用机器人
- `/help` - 查看帮助信息
- `/query` - 快速查询域名
- `/add` - 快速添加规则

### 操作流程

#### 查询域名
1. 点击 "🔍 查询域名" 或发送 `/query`
2. 输入要查询的域名
3. 查看详细的查询结果

#### 添加直连规则
1. 点击 "➕ 添加直连规则"
2. 输入要添加的域名
3. 系统自动检查域名状态
4. 根据提示确认添加
5. 可选择添加说明信息
6. 自动提交到 GitHub

### 支持的域名格式
- `example.com`
- `www.example.com`
- `https://example.com`
- `http://example.com/path`

## 工作原理

### 域名检查流程
1. **防重复检查**
   - 检查域名是否已在 GitHub 规则中
   - 检查二级域名是否已存在
   - 检查是否在 GEOSITE:CN 中

2. **DNS 解析检查**
   - 使用 DoH 查询域名 IP
   - 附加 EDNS 参数模拟中国境内查询
   - 查询 NS 服务器信息

3. **IP 归属地检查**
   - 使用 GeoIP 数据库查询 IP 归属地
   - 检查域名和 NS 服务器是否在中国大陆

4. **添加决策**
   - 域名 IP 在中国 + NS 在中国：直接添加
   - 域名 IP 在中国 + NS 不在中国：直接添加
   - 域名 IP 不在中国 + NS 在中国：询问用户确认
   - 域名 IP 不在中国 + NS 不在中国：拒绝添加

### 数据更新
- GeoIP 数据：每 6 小时自动更新
- GeoSite 数据：每 6 小时自动更新
- 内存索引：数据更新后自动重建

## 📁 目录结构

```
Rule-Bot/
├── docker-compose.yml     # Docker Compose 配置（包含环境变量配置）
├── Dockerfile            # Docker 镜像构建文件
├── requirements.txt      # Python 依赖包列表
├── start.sh             # 容器启动脚本
├── README.md            # 项目说明文档
└── src/                 # 源代码目录
    ├── main.py          # 主程序入口点
    ├── config.py        # 配置管理模块
    ├── bot.py           # Telegram 机器人核心
    ├── data_manager.py  # 数据管理器（GeoIP/GeoSite）
    ├── handlers/        # 消息处理器
    │   └── handler_manager.py  # 主要消息处理逻辑
    ├── services/        # 核心服务模块
    │   ├── dns_service.py      # DNS 查询服务
    │   ├── geoip_service.py    # GeoIP 数据服务
    │   ├── github_service.py   # GitHub API 服务
    │   ├── domain_checker.py   # 域名检查服务
    │   └── group_service.py    # 群组验证服务
    └── utils/           # 工具模块
        └── domain_utils.py     # 域名处理工具
```

## 🔧 故障排除

### 常见问题

1. **机器人无响应**
   - 检查 Telegram Bot Token 是否正确
   - 查看容器日志：`docker-compose logs rule-bot`
   - 确认机器人没有被封禁或限制

2. **GitHub 操作失败**
   - 检查 GitHub Token 权限（需要 `repo` 权限）
   - 确认目标仓库存在且有写入权限
   - 检查 Token 是否过期或被撤销

3. **域名解析失败**
   - 检查网络连接
   - 确认 DoH 服务器可访问
   - 检查防火墙设置

4. **数据加载失败**
   - 检查网络连接
   - 查看 GeoIP/GeoSite 数据下载情况
   - 确认数据源 URL 可访问

5. **群组验证失败**
   - 检查群组 ID 是否正确
   - 确认机器人已加入群组
   - 检查群组链接是否有效

### 日志查看
```bash
# 查看实时日志
docker-compose logs -f rule-bot

# 查看最近日志
docker-compose logs --tail=100 rule-bot
```

### 重启服务
```bash
# 重启所有服务
docker-compose restart

# 重启机器人
docker-compose restart rule-bot

# 重新构建并启动
docker-compose up -d --build
```

## 💻 开发说明

### 本地开发
1. 安装 Python 3.11+
2. 安装依赖：`pip install -r requirements.txt`
3. 配置环境变量（参考 docker-compose.yml）
4. 运行：`python -m src.main`

### 技术栈
- **Python 3.11+**: 主要开发语言
- **python-telegram-bot**: Telegram Bot API 客户端
- **PyGithub**: GitHub API 客户端
- **aiohttp**: 异步 HTTP 客户端
- **dnspython**: DNS 查询库
- **loguru**: 日志管理
- **Docker**: 容器化部署

### 代码特点
- **模块化设计**: 各功能独立，易于维护
- **异步编程**: 使用 asyncio 提高性能
- **完善的错误处理**: 详细的异常捕获和日志记录
- **内存索引优化**: 快速查询 GeoIP/GeoSite 数据
- **配置驱动**: 所有配置通过环境变量管理

## 📄 许可证

本项目采用 MIT 许可证，详见 [LICENSE](LICENSE) 文件。

Copyright (c) 2024 AetherSailor

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

### 贡献指南
1. Fork 本项目
2. 创建特性分支：`git checkout -b feature/your-feature`
3. 提交更改：`git commit -m 'Add some feature'`
4. 推送分支：`git push origin feature/your-feature`
5. 提交 Pull Request

## 📝 更新日志

<details>
<summary>点击展开查看更新日志</summary>

### v0.1.0 (当前版本)
- 🎉 初始版本发布
- ✅ 支持域名查询和添加直连规则
- ✅ 自动 GeoIP/GeoSite 数据更新
- ✅ 完整的 Docker 部署方案
- ✅ 群组验证功能
- ✅ 智能域名检测和重复检查
- ✅ 详细的日志记录和错误处理
- ✅ GitHub Actions 多架构构建支持
- ✅ 优化的 Docker 镜像标签策略

### 技术特性
- 多阶段 Docker 构建优化
- 支持 linux/amd64, linux/arm64, linux/arm/v7, linux/386 架构
- 智能缓存策略和构建性能优化
- 完整的错误处理和日志系统
- 模块化代码设计

</details> 