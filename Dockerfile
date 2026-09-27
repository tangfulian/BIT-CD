FROM python:3.11-slim

# 替换为阿里云 Debian 镜像源（加速国内下载）
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    chromium \
    fonts-wqy-microhei \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 替换 pip 为阿里云源（加速 pip 安装）
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple

COPY requirements.txt .
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

# 安装 Playwright Chromium 浏览器（AI Agent 需要）
RUN playwright install-deps chromium && playwright install chromium

COPY . .

# 兼容旧 import 路径（misc 已迁移到 core/misc）
RUN cp -r core/misc misc

RUN mkdir -p uploads results samples/predict data && chmod 777 data

EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
