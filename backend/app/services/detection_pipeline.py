"""检测的编排层。

这套编排（MD5 去重缓存、影像解码、结果落盘、建检测记录）此前整段压在
routers/detect.py 的请求处理函数里，后果是**只有走 HTTP 才能跑一次检测** ——
工具通道需要在不经 HTTP 的情况下复用同一套语义，所以把它下沉到这里：
路由器与工具层调用同一个函数，不存在两份实现各自漂移的可能。

依赖方向：本模块可以 import detect_service（纯计算层），反过来不行 ——
纯计算层不碰数据库。

base_url 是普通字符串而不是 Request：调用方有两个，一个是 HTTP 请求，
另一个是工具循环里的进程内调用，后者没有 Request 可用。返回给前端的
结果 URL 必须是绝对地址，所以由调用方把 base_url 传进来。
"""
import hashlib
import logging
import os
import uuid
from io import BytesIO

import cv2
from fastapi import HTTPException
from PIL import Image
from sqlalchemy.orm import Session

from backend.app.models.detection import DetectionResultDB

# 刻意 import 模块而不是 `from ... import detect_change`。
#
# 测试用 monkeypatch.setattr("backend.app.services.detect_service.detect_change", ...)
# 打桩（conftest 的 autouse 夹具 mock_detect_service，目的就是别在测试里加载
# PyTorch 权重）。`from X import y` 会在本模块首次导入时把当时那个函数对象
# 绑进本模块命名空间，之后对 detect_service 的替换就再也影响不到这里 ——
# 那样桩会静默失效，测试会真的去跑一遍模型推理，而且**仍然通过**，
# 只是测的东西已经不是原来那个了。按模块属性调用才能让打桩始终生效。
from backend.app.services import detect_service
from backend.app.services.record_access import (
    RESULTS_DIR,
    find_owned_series,
    result_url,
    rewrite_url,
    url_to_path,
)

logger = logging.getLogger(__name__)

SUPPORTED_MODELS = [
    "BIT",
    "DIFF",
    "FC_SIAM_DIFF",
    "SNUNET",
    "CHANGEFORMER",
    "AFCF3D",
    "BIT_LuojiaSET",
]


def decode_image(data: bytes, name: str = "影像", mode: str | None = "RGB", size: int = 256):
    """把上传的字节解码为模型输入。

    非法图片此前会抛 UnidentifiedImageError 一路冒到外层，变成客户端无法解析的
    裸 500 文本；这里统一拦截为 400 并给出可读原因。
    """
    try:
        img = Image.open(BytesIO(data))
        if mode:
            img = img.convert(mode)
        if size:
            img = img.resize((size, size), Image.BILINEAR)
        return img
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"{name} 不是有效的图片文件") from exc


def _imwrite(path, img) -> None:
    if not cv2.imwrite(path, img):
        raise RuntimeError(f"无法写入文件: {path}")


def run_detection(
    *,
    img1_bytes: bytes,
    img2_bytes: bytes,
    model: str,
    threshold: float,
    base_url: str,
    db: Session,
    user_id: int | None = None,
    lat_lng: str = "",
    location: str = "",
    change_type: str = "",
    t1_time: str = "",
    t2_time: str = "",
    series_id: int = 0,
    phase_index: int = -1,
) -> dict:
    """跑一次单张变化检测，返回与 HTTP 接口完全一致的响应体。

    同步阻塞函数（模型推理是 CPU 重活），调用方负责放进线程池。

    user_id 为 None 表示游客检测：不查缓存、不落库，只出图。这个语义与
    /detect 原本的 get_optional_user 行为一致，保留它是为了让工具通道
    也能在未登录时工作。
    """
    if model not in SUPPORTED_MODELS:
        raise HTTPException(status_code=400, detail=f"不支持的模型: {model}")

    # 归属校验：不允许把检测挂到别人的序列上
    if series_id:
        if user_id is None:
            raise HTTPException(status_code=401, detail="指定序列需要登录")
        if not find_owned_series(db, user_id, series_id):
            raise HTTPException(status_code=404, detail="序列不存在")

    unique_id = str(uuid.uuid4())

    image_hash = None
    if user_id is not None:
        image_hash = hashlib.md5(img1_bytes + img2_bytes).hexdigest()
        cached = db.query(DetectionResultDB).filter(
            DetectionResultDB.image_pair_hash == image_hash,
            DetectionResultDB.model == model,
            DetectionResultDB.threshold == float(threshold),
            DetectionResultDB.user_id == user_id,
        ).first()
        if cached and cached.score_url:
            score_path = url_to_path(cached.score_url)
            if os.path.exists(score_path):
                logger.info("命中缓存: image_hash=%s model=%s", image_hash, model)
                return {
                    "code": 200,
                    "msg": "检测完成（缓存）",
                    "model": model,
                    "detection_id": cached.id,
                    "mask": rewrite_url(base_url, cached.mask_url),
                    "heat": rewrite_url(base_url, cached.heat_url),
                    "fusion": rewrite_url(base_url, cached.fusion_url),
                    "score": rewrite_url(base_url, cached.score_url),
                    "stats": {
                        "total_pixel": cached.total_pixel,
                        "change_pixel": cached.change_pixel,
                        "ratio": cached.ratio,
                        "threshold": cached.threshold,
                    },
                }

    img_t1 = decode_image(img1_bytes, "T1 影像")
    img_t2 = decode_image(img2_bytes, "T2 影像")

    score_map, change_mask, heatmap, fusion, stats = detect_service.detect_change(
        img_t1, img_t2, threshold, model, unique_id
    )

    score_filename = f"{unique_id}_score.png"
    mask_filename = f"{unique_id}_mask.png"
    heat_filename = f"{unique_id}_heat.png"
    fusion_filename = f"{unique_id}_fusion.png"
    t2_filename = f"{unique_id}_t2.png"
    detect_service.save_score_map(score_map, f"{RESULTS_DIR}/{score_filename}")
    _imwrite(f"{RESULTS_DIR}/{mask_filename}", change_mask)
    _imwrite(f"{RESULTS_DIR}/{heat_filename}", heatmap)
    _imwrite(f"{RESULTS_DIR}/{fusion_filename}", fusion)
    # 留一份 T2（256×256，与掩膜同尺寸）供重调阈值时重建融合图。
    # 融合图 = alpha 混合(T2, 掩膜)，没有 T2 就重建不出来——此前
    # /detect/rethreshold 正是卡在这里，只能留下与掩膜自相矛盾的旧融合图。
    # 用 PIL 保存而不是 cv2：cv2 按 BGR 解释数组，直接存 PIL 的 RGB 会红蓝互换。
    img_t2.save(f"{RESULTS_DIR}/{t2_filename}")

    detection_id = None
    if user_id is not None:
        detection = DetectionResultDB(
            user_id=user_id,
            model=model,
            threshold=threshold,
            ratio=stats["ratio"],
            change_pixel=stats["change_pixel"],
            total_pixel=stats["total_pixel"],
            lat_lng=lat_lng,
            location=location,
            change_type=change_type,
            t1_time=t1_time,
            t2_time=t2_time,
            mask_url=result_url(base_url, mask_filename),
            heat_url=result_url(base_url, heat_filename),
            fusion_url=result_url(base_url, fusion_filename),
            score_url=result_url(base_url, score_filename),
            image_pair_hash=image_hash,
            series_id=series_id or None,
            phase_index=phase_index if phase_index >= 0 else None,
        )
        db.add(detection)
        db.commit()
        db.refresh(detection)
        detection_id = detection.id
        logger.info("检测请求: model=%s threshold=%.2f user_id=%s", model, threshold, user_id)
    else:
        logger.info("游客检测: model=%s threshold=%.2f", model, threshold)

    return {
        "code": 200,
        "msg": "检测成功！",
        "model": model,
        "detection_id": detection_id,
        "mask": result_url(base_url, mask_filename),
        "heat": result_url(base_url, heat_filename),
        "fusion": result_url(base_url, fusion_filename),
        "score": result_url(base_url, score_filename),
        "stats": stats,
    }
