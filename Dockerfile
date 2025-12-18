# 多阶段构建：编译阶段
FROM python:3.11-slim AS builder

# 设置工作目录
WORKDIR /app

# 安装基础编译工具 (为了支持 psutil 等可能没有 wheel 的包)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc6-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 预编译所有包为wheel格式
#Slim 镜像通常可以直接下载二进制 wheel，无需编译，速度极快
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# 运行阶段：使用最小化镜像
FROM python:3.11-slim

# 设置运行时环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1
ENV TZ=Asia/Shanghai

# 安装运行时依赖
# 使用 apt-get 替代 apk
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && update-ca-certificates \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app

# 从编译阶段复制预编译的wheel包
COPY --from=builder /wheels /wheels

# 安装预编译的包
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

# 复制应用代码
COPY src/ ./src/
COPY start.sh .

# 编译所有 Python 文件为字节码，删除源码
RUN python -m compileall -b src/ && \
    find src/ -name "*.py" -delete && \
    find src/ -name "__pycache__" -type d -exec chmod 755 {} \;

# 使用非root用户运行
RUN groupadd -r appuser && useradd -r -g appuser -s /bin/sh -u 1000 appuser && \
    chown -R appuser:appuser /app && \
    chmod +x start.sh
USER appuser

EXPOSE 8080

CMD ["./start.sh"] 