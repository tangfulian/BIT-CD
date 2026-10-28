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
# torch 的 CPU 轮子来源。默认官方源；国内服务器建议覆盖成镜像：
#   docker compose build --build-arg TORCH_FIND_LINKS=https://mirrors.aliyun.com/pytorch-wheels/cpu/
#
# 为什么用 --find-links 而不是 --index-url：官方源是 PEP 503 索引，但国内镜像
# 只是平铺目录，index-url 用不了。--find-links 两种都能吃，依赖仍从上面配置的
# PyPI 镜像解析。实测官方源在国内约 1.6 KB/s，196 MB 的轮子 40 分钟下不完；
# 换成阿里云后 28 MB/s。
ARG TORCH_FIND_LINKS=https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir torch torchvision --find-links "${TORCH_FIND_LINKS}"
RUN pip install --no-cache-dir -r requirements.txt

# Pillow 必须单独覆盖安装，原因见 requirements.txt 末尾：
# browser-use 精确锁死 pillow==12.3.0，而该版本有 28 个已修复于 13.0.0 的漏洞
# （TIFF/PDF 解码器越界与堆溢出），本系统又在解析用户上传的影像。
# 两者写进同一个 requirements 会让 pip ResolutionImpossible；pillow 自身无依赖，
# 用 --no-deps 覆盖这个过严的传递约束是安全的。
RUN pip install --no-cache-dir --no-deps pillow==13.0.0

# 安装 Playwright Chromium 浏览器（AI Agent 需要）
#
# 浏览器下载源同样做成可覆盖的。国内构建建议：
#   --build-arg PLAYWRIGHT_DOWNLOAD_HOST=https://registry.npmmirror.com/-/binary/playwright
# 实测官方 CDN 约 74 KB/s、该镜像约 17 MB/s。留空则走官方源。
ARG PLAYWRIGHT_DOWNLOAD_HOST=""
ENV PLAYWRIGHT_DOWNLOAD_HOST=${PLAYWRIGHT_DOWNLOAD_HOST}
RUN playwright install-deps chromium && playwright install chromium

COPY . .

# 兼容旧 import 路径（misc 已迁移到 core/misc）
RUN cp -r core/misc misc

RUN mkdir -p uploads results samples/predict data && chmod 777 data

EXPOSE 8000

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
