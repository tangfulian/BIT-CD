#!/bin/bash
# ============================================================
# BIT_CD 服务器一键部署
# 在阿里云 Ubuntu 22.04 上以 root 运行: bash deploy.sh
# ============================================================
set -e

GITHUB_REPO="https://github.com/tangfulian/BIT-CD.git"
APP_DIR="/opt/BIT_CD"

echo "=== [1/4] 安装 Docker ==="
if ! command -v docker &> /dev/null; then
    apt-get update && apt-get install -y ca-certificates curl
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list
    apt-get update && apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
fi

echo "=== [2/4] 克隆项目 ==="
mkdir -p /opt
if [ -d "$APP_DIR" ]; then
    cd "$APP_DIR" && git pull
else
    git clone "$GITHUB_REPO" "$APP_DIR"
fi
cd "$APP_DIR"

echo "=== [3/4] 检查 .env ==="
if [ ! -f .env ]; then
    echo "错误: 请先创建 .env 文件！"
    echo "参考 .env.production 填写你的 API Key，然后: cp .env.production .env"
    exit 1
fi

mkdir -p checkpoints results uploads samples/predict

echo "=== [4/4] 启动服务 ==="
docker compose up -d --build

echo ""
echo "部署完成！访问: http://39.105.162.133:8000"
echo "管理员: admin"
echo "管理密码: 见 .env 中的 ADMIN_DEFAULT_PASSWORD"
echo "查看日志: docker compose logs -f"
