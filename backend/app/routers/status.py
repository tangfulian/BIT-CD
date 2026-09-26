import logging
import os
import sys
from datetime import datetime, timezone

import psutil
import torch
from fastapi import APIRouter, Request

from backend.app.core.limiter import limiter
import backend.app.services.detect_service as detect_svc

router = APIRouter(tags=["系统状态"])
logger = logging.getLogger(__name__)

_start_time = datetime.now(timezone.utc)

_request_counts = {
    "detect": 0,
    "register": 0,
    "login": 0,
    "chat": 0,
    "analysis": 0,
    "regeo": 0,
    "history": 0,
    "compare": 0,
    "recommend": 0,
}


def count(endpoint: str):
    """累加请求计数。

    此前对未预置的 key 静默丢弃，导致 _path_map 的 24 个映射只有 9 个真正计数，
    状态页的请求分布系统性失真；改为按需建桶。
    """
    _request_counts[endpoint] = _request_counts.get(endpoint, 0) + 1


@router.get("/status")
@limiter.limit("30/minute")
def system_status(request: Request):
    uptime = datetime.now(timezone.utc) - _start_time
    days = uptime.days
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    uptime_str = f"{days}天 {hours}小时 {minutes}分钟 {seconds}秒"
    device = detect_svc.get_device()
    total_req = sum(_request_counts.values())

    cpu = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    try:
        import shutil
        _uploads_path = os.path.abspath("uploads")
        disk_uploads = shutil.disk_usage(_uploads_path) if os.path.exists(_uploads_path) else None
    except Exception:
        disk_uploads = None
    try:
        _results_path = os.path.abspath("results")
        disk_results = shutil.disk_usage(_results_path) if os.path.exists(_results_path) else None
    except Exception:
        disk_results = None

    return {
        "code": 200,
        "data": {
            "model": "BIT_CD (base_transformer_pos_s4_dd8)",
            "device": str(device),
            "uptime": uptime_str,
            "uptime_seconds": int(uptime.total_seconds()),
            "requests": _request_counts,
            "total_requests": total_req,
            "database": "SQLite (blackland.db)",
            "python_version": sys.version.split()[0],
            "pytorch_version": torch.__version__,
            "cpu_percent": cpu,
            "memory_used_gb": round(mem.used / (1024**3), 1),
            "memory_total_gb": round(mem.total / (1024**3), 1),
            "memory_percent": mem.percent,
            "disk_uploads_gb": round(disk_uploads.used / (1024**3), 1) if disk_uploads else None,
            "disk_results_gb": round(disk_results.used / (1024**3), 1) if disk_results else None,
        },
    }
