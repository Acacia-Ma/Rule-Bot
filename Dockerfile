# 多阶段构建：编译阶段
FROM python:3.11-alpine AS builder

# 安装编译依赖
RUN apk add --no-cache \
    gcc \
    g++ \
    make \
    libffi-dev \
    libsodium-dev \
    musl-dev \
    python3-dev

# 复制依赖文件
COPY requirements.txt .

# 预编译所有包为wheel格式
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# 运行阶段：使用最小化镜像
FROM python:3.11-alpine

# 安装运行时依赖（最小化）
RUN apk add --no-cache \
    curl \
    && rm -rf /var/cache/apk/*

WORKDIR /app

# 从编译阶段复制预编译的wheel包
COPY --from=builder /wheels /wheels

# 安装预编译的包（避免编译）
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

# 复制应用代码
COPY src/ ./src/
COPY start.sh .
RUN chmod +x start.sh

# 创建必要目录
RUN mkdir -p /app/data /app/logs

# 使用非root用户运行（安全考虑）
RUN addgroup -g 1000 appuser && \
    adduser -D -s /bin/sh -u 1000 -G appuser appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

CMD ["./start.sh"] 