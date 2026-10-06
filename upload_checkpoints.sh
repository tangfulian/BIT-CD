#!/bin/bash
# ============================================================
# BIT_CD 模型权重上传脚本
# 用法: 在本地 Windows 终端（Git Bash 或 PowerShell）运行
#       chmod +x upload_checkpoints.sh && ./upload_checkpoints.sh
# ============================================================
set -e

# 服务器地址**不要写死在仓库里**：这个仓库是公开的，写死等于公布
# 服务器 IP 并明示 root 可 SSH 登录。用环境变量传入：
#   export DEPLOY_HOST=root@你的服务器IP && ./upload_checkpoints.sh
SERVER="${DEPLOY_HOST:?请先设置 DEPLOY_HOST，例如: export DEPLOY_HOST=root@1.2.3.4}"
REMOTE_DIR="${REMOTE_DIR:-/opt/BIT_CD}"

echo "=== 上传模型权重到服务器 ==="

# 上传各个 checkpoint（只传存在的）
MODELS=("BIT_LEVIR" "AFCF3D" "BIT_LuojiaSET")

for model in "${MODELS[@]}"; do
    if [ -f "checkpoints/$model/best_ckpt.pt" ]; then
        echo "上传 $model/best_ckpt.pt ..."
        scp "checkpoints/$model/best_ckpt.pt" "$SERVER:$REMOTE_DIR/checkpoints/$model/"
    else
        echo "跳过 $model (文件不存在)"
    fi
done

echo "=== 上传完成 ==="
echo "请 SSH 到服务器重启服务: ssh $SERVER 'cd $REMOTE_DIR && docker compose restart'"
