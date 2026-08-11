# =============================================================================
# desensitize backend Dockerfile
# =============================================================================
# 构建命令: cd docker && ./build_image.sh
# =============================================================================

FROM ubuntu:24.04

ARG DEBIAN_FRONTEND=noninteractive

# 1. 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget ca-certificates \
    libgl1 libglib2.0-0 \
    python3 python3-pip python3-venv \
  && rm -rf /var/lib/apt/lists/*

# 2. 工作目录
WORKDIR /app

# 3. 创建独立 Python 虚拟环境
RUN python3 -m venv /opt/venv
ENV PATH=/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# 4. 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -i https://mirrors.ustc.edu.cn/pypi/simple -r requirements.txt

# 5. 拷贝应用代码
COPY app/ ./app/

# 6. 运行环境变量
ENV DESENSITIZE_DATA_DIR=/data

# 7. 创建数据目录
RUN mkdir -p "$DESENSITIZE_DATA_DIR"

# 8. 暴露端口
EXPOSE 5000

# 9. 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD wget --no-verbose --tries=1 -qO- http://127.0.0.1:5000/health > /dev/null 2>&1 || exit 1

# 10. 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5000"]
