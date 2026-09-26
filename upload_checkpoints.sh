#!/bin/bash
# ============================================================
# BIT_CD 模型权重上传脚本
# 用法: 在本地 Windows 终端（Git Bash 或 PowerShell）运行
#       chmod +x upload_checkpoints.sh && ./upload_checkpoints.sh
# ============================================================
set -e

SERVER="root@39.105.162.133"
REMOTE_DIR="/opt/BIT_CD"

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
