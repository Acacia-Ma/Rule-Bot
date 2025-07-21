# GitHub Actions 工作流配置

## Docker 构建工作流

本项目包含一个自动化的 Docker 构建工作流，当推送到主分支或创建标签时会自动触发。

### 功能特性

- 🔄 自动触发：推送到 `master`、`dev` 分支、创建版本标签或PR到这些分支时触发
- 🐳 多平台构建：支持 `linux/amd64`、`linux/arm64`、`linux/arm/v7` 架构
- 🏷️ 智能标签：自动生成合适的 Docker 标签
- 📦 缓存优化：使用 GitHub Actions 缓存加速构建
- 🚀 自动推送：构建完成后自动推送到 Docker Hub

### 必需的 GitHub Secrets

在 GitHub 仓库设置中配置以下 Secrets：

1. **DOCKERHUB_USERNAME**: 你的 Docker Hub 用户名
2. **DOCKERHUB_TOKEN**: Docker Hub 访问令牌（不是密码）

#### 配置步骤

1. **进入仓库设置**：
   - 在你的 GitHub 仓库页面，点击 "Settings" 标签
   - 在左侧菜单中找到 "Secrets and variables" → "Actions"

2. **添加 DOCKERHUB_USERNAME**：
   - 点击 "New repository secret"
   - Name: `DOCKERHUB_USERNAME`
   - Value: 你的 Docker Hub 用户名（例如：`aethersailor`）

3. **添加 DOCKERHUB_TOKEN**：
   - 再次点击 "New repository secret"
   - Name: `DOCKERHUB_TOKEN`
   - Value: 你的 Docker Hub 访问令牌（不是登录密码）

### 如何获取 Docker Hub Token

1. 登录 [Docker Hub](https://hub.docker.com/)
2. 进入 Account Settings → Security
3. 点击 "New Access Token"
4. 输入令牌名称（如 "GitHub Actions"）
5. 复制生成的令牌

### 标签规则

工作流会根据以下规则自动生成 Docker 标签：

- **master分支推送**: `aethersailor/rule-bot:latest`
- **dev分支推送**: `aethersailor/rule-bot:dev`
- **版本标签推送**: `aethersailor/rule-bot:v1.0.0` 和 `aethersailor/rule-bot:latest`
- **PR**: `aethersailor/rule-bot:pr-123`

### 手动触发

如果需要手动触发构建，可以：

1. 在 GitHub 仓库页面点击 "Actions" 标签
2. 选择 "Build and Push Docker Image" 工作流
3. 点击 "Run workflow" 按钮

### 注意事项

- 确保 Dockerfile 在项目根目录
- 工作流使用 Docker Buildx 进行多平台构建
- 构建过程会使用 GitHub Actions 缓存以提高效率 