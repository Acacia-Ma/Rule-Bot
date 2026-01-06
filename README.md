# Rule-Bot

一个用于管理 Clash 规则的 Telegram 机器人，支持域名查询与直连规则添加。

- ✅ 自动检查 GitHub 规则与 GEOSITE:CN
- ✅ DNS / NS 归属地判断，给出添加建议
- ✅ 群组验证与群组 @ 提及模式
- ✅ Docker 部署，支持 `linux/amd64` 与 `linux/arm64`

> 不提供 Windows 支持，仅建议 Docker 部署。

## ⚡ 快速开始（Docker）

1) 创建 `docker-compose.yml`

```yaml
services:
  rule-bot:
    image: aethersailor/rule-bot:latest
    container_name: rule-bot
    restart: unless-stopped
    environment:
      - TELEGRAM_BOT_TOKEN=你的机器人 Token
      - GITHUB_TOKEN=你的 GitHub Token
      - GITHUB_REPO=your_username/your_repository
      - DIRECT_RULE_FILE=rule/Custom_Direct.list
```

2) 启动

```bash
docker compose up -d
```

3) 查看日志

```bash
docker compose logs -f rule-bot
```

## ⚙️ 配置一览

### 必需参数

- `TELEGRAM_BOT_TOKEN`：从 @BotFather 获取
- `GITHUB_TOKEN`：需要 `repo` 权限
- `GITHUB_REPO`：格式 `用户名/仓库名`
- `DIRECT_RULE_FILE`：规则文件路径（仓库内）

### 可选参数（展开查看）

<details>
<summary>点击展开</summary>

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `PROXY_RULE_FILE` | 代理规则文件（暂不使用） | 空 |
| `GITHUB_COMMIT_EMAIL` | 提交邮箱 | `noreply@users.noreply.github.com` |
| `LOG_LEVEL` | 日志级别：`DEBUG/INFO/WARNING/ERROR` | `INFO` |
| `LOG_FORMAT` | 日志格式：`compact/verbose` | `compact` |
| `DATA_UPDATE_INTERVAL` | 数据更新间隔（秒） | `21600`（6 小时） |
| `DATA_DIR` | 数据目录（容器内路径） | `/app/data` |
| `DOH_SERVERS` | A 记录 DoH 列表，逗号分隔 `name=url` | 内置默认 |
| `NS_DOH_SERVERS` | NS 记录 DoH 列表，逗号分隔 `name=url` | 内置默认 |
| `REQUIRED_GROUP_ID` | 群组验证 ID | 空 |
| `REQUIRED_GROUP_NAME` | 群组验证名称 | 空 |
| `REQUIRED_GROUP_LINK` | 群组验证链接 | 空 |
| `ALLOWED_GROUP_IDS` | 群组模式允许的群组 ID，逗号分隔 | 空 |
| `TZ` | 时区 | `Asia/Shanghai` |

</details>

> 容器默认以非 root 用户运行，若挂载宿主机目录到 `/app/data`，请确保目录属主为 UID/GID 1000。

## 🧭 使用方式

### 私聊命令

- `/start`：主菜单
- `/help`：帮助信息
- `/query`：查询域名
- `/add`：添加规则入口
- `/delete`：暂不可用
- `/skip`：跳过域名说明

### 群组模式（ALLOWED_GROUP_IDS）

- 仅在白名单群组中响应
- 仅响应 **@ 机器人** 的消息
- 支持“回复包含域名的消息 + @ 机器人”

> 使用群组模式需要关闭机器人 Privacy Mode，并重新添加机器人到群组。

### 群组验证（REQUIRED_GROUP_*）

同时配置 `REQUIRED_GROUP_ID/NAME/LINK` 后生效，未通过或校验失败会拒绝访问（失败即拒绝）。

## 📌 规则逻辑（简版）

1) 解析域名并提取二级域名  
2) 检查 GitHub 规则与 GEOSITE:CN  
3) DNS / NS 归属地检测  
4) 符合条件则自动添加

> `.cn` 域名默认直连，不允许添加。

## 🐳 镜像与版本

- `latest`：稳定版
- `dev`：开发版
- `vX.Y.Z`：发布标签

## 🧩 常见问题

**群组不响应消息**
1. 关闭 Privacy Mode  
2. 重新添加机器人到群组  
3. 仅在消息中 @ 机器人  

**挂载数据目录后权限报错**
把宿主机目录 `chown -R 1000:1000` 再启动容器。

## 💻 本地开发（可选）

- Python 3.12+
- `pip install -r requirements.txt`

## 📄 许可证

GPLv3

