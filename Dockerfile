# 多阶段构建：编译阶段
FROM python:3.11-alpine AS builder

# 设置构建参数
ARG BUILDKIT_INLINE_CACHE=1

# 安装编译依赖（包括 Rust 编译器）
RUN apk add --no-cache \
    gcc \
    g++ \
    make \
    libffi-dev \
    libsodium-dev \
    musl-dev \
    python3-dev \
    rust \
    cargo \
    openssl-dev \
    pkgconfig

# 设置 Rust 编译优化
ENV RUSTFLAGS="-C target-cpu=native"
ENV CARGO_NET_GIT_FETCH_WITH_CLI=true
ENV CARGO_BUILD_JOBS=2
ENV OPENSSL_DIR=/usr
ENV OPENSSL_LIBDIR=/usr/lib
ENV PKG_CONFIG_PATH=/usr/lib/pkgconfig
ENV PKG_CONFIG_LIBDIR=/usr/lib/pkgconfig

# ARMv7 特定优化
ENV PIP_NO_BUILD_ISOLATION=1
ENV PIP_USE_PEP517=0

# 复制依赖文件
COPY requirements.txt .

# 针对不同架构的编译优化
RUN if [ "$(uname -m)" = "armv7l" ]; then \
        echo "ARMv7 detected, using optimized build strategy..." && \
        # 对于 armv7，优先使用预编译包，减少编译时间
        pip install --no-cache-dir --only-binary=all -r requirements.txt && \
        pip wheel --no-cache-dir --wheel-dir /wheels --only-binary=all -r requirements.txt || \
        (echo "Pre-built packages failed, trying minimal compilation..." && \
         # 如果预编译包失败，尝试最小化编译
         pip install --no-cache-dir --only-binary=all python-telegram-bot==20.7 requests==2.31.0 python-dotenv==1.0.0 loguru==0.7.2 schedule==1.2.0 && \
         pip wheel --no-cache-dir --wheel-dir /wheels --only-binary=all python-telegram-bot==20.7 requests==2.31.0 python-dotenv==1.0.0 loguru==0.7.2 schedule==1.2.0 && \
         # 对于需要编译的包，使用更保守的策略
         pip wheel --no-cache-dir --wheel-dir /wheels --no-deps aiohttp==3.9.1 PyGithub==2.1.1 dnspython==2.4.2); \
    else \
        echo "Other architecture detected, using standard build..." && \
        pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt; \
    fi && \
    pip install --no-cache-dir --upgrade pip setuptools wheel

# 运行阶段：使用最小化镜像
FROM python:3.11-alpine

# 设置运行时环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1

# 安装运行时依赖（最小化）
RUN apk add --no-cache \
    curl \
    ca-certificates \
    && rm -rf /var/cache/apk/* \
    && update-ca-certificates

WORKDIR /app

# 从编译阶段复制预编译的wheel包
COPY --from=builder /wheels /wheels

# 安装预编译的包（避免编译）
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

# 复制应用代码（分层复制，优化缓存）
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

# 健康检查（暂时禁用，因为应用可能没有健康检查端点）
# HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
#     CMD curl -f http://localhost:8080/health || exit 1

EXPOSE 8080

CMD ["./start.sh"] 