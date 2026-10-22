# 3.12 起：numpy 2.5 与 tifffile 2026 都要求 Python >= 3.12。
# CI 与本地开发环境本来就已经是 3.12，之前只有镜像卡在 3.11。
FROM python:3.12-slim

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

# Pillow 必须单独覆盖安装，原因见 requirements.txt 末尾：
# browser-use 精确锁死 pillow==12.3.0，而该版本有 28 个已修复于 13.0.0 的漏洞
# （TIFF/PDF 解码器越界与堆溢出），本系统又在解析用户上传的影像。
# 两者写进同一个 requirements 会让 pip ResolutionImpossible；pillow 自身无依赖，
# 用 --no-deps 覆盖这个过严的传递约束是安全的。
RUN pip install --no-cache-dir --no-deps pillow==13.0.0

# 安装 Playwright Chromium 浏览器（AI Agent 需要）
RUN playwright install-deps chromium && playwright install chromium

COPY . .

# 兼容旧 import 路径（misc 已迁移到 core/misc）
RUN cp -r core/misc misc

RUN mkdir -p uploads results samples/predict data && chmod 777 data

EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
