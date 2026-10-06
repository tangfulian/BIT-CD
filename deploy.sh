#!/bin/bash
# ============================================================
# BIT_CD 服务器一键部署
# 在阿里云 Ubuntu 22.04 上以 root 运行: bash deploy.sh
# ============================================================
set -e

GITHUB_REPO="https://github.com/tangfulian/BIT-CD.git"
APP_DIR="/opt/BIT_CD"

# 服务器公网地址，只用于最后打印访问链接。
# 不要把真实 IP 写在这里：这个仓库是公开的，写死等于把服务器地址公布出去。
# 需要时用环境变量传入：DEPLOY_HOST=1.2.3.4 bash deploy.sh
DEPLOY_HOST="${DEPLOY_HOST:-<你的服务器IP>}"

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
    echo "错误: 当前目录下没有 .env！"
    echo ""
    echo "  .env 与 .env.production 都在 .gitignore 里，不会随仓库分发，"
    echo "  需要在部署机上用仓库里的模板自己创建："
    echo ""
    echo "      cp .env.example .env"
    echo ""
    echo "  然后按注释填入 JWT_SECRET、ADMIN_DEFAULT_PASSWORD、DASHSCOPE_API_KEY 等。"
    exit 1
fi

mkdir -p checkpoints results uploads samples/predict

echo "=== [4/4] 启动服务 ==="
docker compose up -d --build

echo ""
echo "部署完成！访问: http://${DEPLOY_HOST}:8000"
echo "管理员: admin"
echo "管理密码: 见 .env 中的 ADMIN_DEFAULT_PASSWORD"
echo "查看日志: docker compose logs -f"
