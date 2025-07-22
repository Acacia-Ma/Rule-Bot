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
ENV CARGO_BUILD_JOBS=4
ENV OPENSSL_DIR=/usr
ENV OPENSSL_LIBDIR=/usr/lib
ENV PKG_CONFIG_PATH=/usr/lib/pkgconfig
ENV PKG_CONFIG_LIBDIR=/usr/lib/pkgconfig

# 复制依赖文件
COPY requirements.txt .

# 预编译所有包为wheel格式，使用并行编译
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt \
    && pip install --no-cache-dir --upgrade pip setuptools wheel \
    || (echo "Wheel build failed, trying with pre-built packages..." && \
        pip install --no-cache-dir --only-binary=all -r requirements.txt && \
        pip wheel --no-cache-dir --wheel-dir /wheels --only-binary=all -r requirements.txt)

# 运行阶段：使用最小化镜像
FROM python:3.11-alpine

# 设置运行时环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1
ENV TZ=Asia/Shanghai

# 安装运行时依赖（最小化）
RUN apk add --no-cache \
    curl \
    ca-certificates \
    tzdata \
    && rm -rf /var/cache/apk/* \
    && update-ca-certificates \
    && cp /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && echo "Asia/Shanghai" > /etc/timezone

WORKDIR /app

# 从编译阶段复制预编译的wheel包
COPY --from=builder /wheels /wheels

# 安装预编译的包（避免编译）
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

# 复制应用代码并编译为字节码
COPY src/ ./src/
COPY start.sh .

# 编译所有 Python 文件为字节码，删除源码
RUN python -m compileall -b src/ && \
    find src/ -name "*.py" -delete && \
    # 确保 __pycache__ 目录存在且可访问
    find src/ -name "__pycache__" -type d -exec chmod 755 {} \;

# 创建必要目录
RUN mkdir -p /app/data /app/logs

# 使用非root用户运行（安全考虑）
RUN addgroup -g 1000 appuser && \
    adduser -D -s /bin/sh -u 1000 -G appuser appuser && \
    chown -R appuser:appuser /app && \
    chmod +x start.sh && \
    # 确保数据目录有正确的权限
    mkdir -p /app/data/geoip /app/data/geosite && \
    chown -R appuser:appuser /app/data
USER appuser

# 健康检查（暂时禁用，因为应用可能没有健康检查端点）
# HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
#     CMD curl -f http://localhost:8080/health || exit 1

EXPOSE 8080

CMD ["./start.sh"] 