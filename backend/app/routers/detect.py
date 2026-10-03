import json
import logging
import uuid

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from backend.app.core.limiter import get_user_key, limiter
from backend.app.core.security import get_current_user, get_optional_user, get_db
from backend.app.models.detection import DetectionResultDB
from backend.app.models.user import UserDB
from backend.app.services.detect_service import (
    apply_threshold,
    calc_area_stats,
    calc_ndvi,
    check_registration,
    detect_change,
    evaluate_models,
    evaluate_scan,
    load_score_map,
    mask_to_geojson,
    model_availability,
    otsu_threshold,
    save_score_map,
    rebuild_fusion_from_score,
    recommend_threshold_from_images,
)
from backend.app.services.detect_service import imwrite
from backend.app.services.detection_pipeline import (
    SUPPORTED_MODELS,
    decode_image as _decode_image,
    run_detection,
)
from backend.app.services.record_access import find_owned_detection, result_url
from backend.app.services.record_access import url_to_path as _url_to_path

router = APIRouter(tags=["检测"])
logger = logging.getLogger(__name__)


def _result_url(request: Request, filename: str) -> str:
    """构建绝对路径的结果图片 URL，兼容代理和直连场景。

    Request -> base_url 的适配留在这里；URL 约定本身在 record_access，
    全系统只有那一份。
    """
    return result_url(str(request.base_url).rstrip("/"), filename)


@router.get("/detect/models")
async def list_models():
    """对外声明真实可用的模型清单。

    注册表里登记的模型多于实际部署的（部分权重未随仓库分发）。前端据此渲染
    选项，就不会把跑不出结果的模型摆给用户选。available=false 的仍然可以请求，
    但只会得到 503，故这里一并说明原因。
    """
    availability = model_availability()
    return JSONResponse(content={
        "code": 200,
        "models": [
            {
                "name": name,
                "available": ok,
                "reason": "" if ok else "权重未部署",
            }
            for name, ok in availability.items()
        ],
        "available": [n for n, ok in availability.items() if ok],
    })


@router.post("/detect")
@limiter.limit("30/minute", key_func=get_user_key)
async def detect(
    request: Request,
    img1: UploadFile = File(...),
    img2: UploadFile = File(...),
    model: str = Form(...),
    threshold: float = Form(...),
    lat_lng: str = Form(""),
    location: str = Form(""),
    change_type: str = Form(""),
    t1_time: str = Form(""),
    t2_time: str = Form(""),
    # 多时相序列归属，可选。不传即维持原有行为（独立的一次检测）。
    series_id: int = Form(0),
    phase_index: int = Form(-1),
    current_user = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    img1_bytes = await img1.read()
    img2_bytes = await img2.read()

    # 编排整段（去重缓存、解码、落盘、建记录）已下沉到 detection_pipeline，
    # 因为工具通道需要在没有 HTTP 请求的情况下复用同一套语义 —— 留两份
    # 实现必然漂移。模型推理是同步 CPU 重活，所以整体放进线程池。
    result = await run_in_threadpool(
        run_detection,
        img1_bytes=img1_bytes,
        img2_bytes=img2_bytes,
        model=model,
        threshold=threshold,
        base_url=str(request.base_url).rstrip("/"),
        db=db,
        user_id=current_user.id if current_user is not None else None,
        lat_lng=lat_lng,
        location=location,
        change_type=change_type,
        t1_time=t1_time,
        t2_time=t2_time,
        series_id=series_id,
        phase_index=phase_index,
    )
    return JSONResponse(content=result)


@router.post("/recommend-threshold")
@limiter.limit("30/minute", key_func=get_user_key)
async def recommend_threshold(request: Request, img1: UploadFile = File(...), img2: UploadFile = File(...)):
    img1_bytes = await img1.read()
    img2_bytes = await img2.read()
    img_t1 = _decode_image(img1_bytes, "T1 影像", mode="L")
    img_t2 = _decode_image(img2_bytes, "T2 影像", mode="L")
    recommended = await run_in_threadpool(recommend_threshold_from_images, img_t1, img_t2)
    return {"code": 200, "threshold": recommended}


@router.post("/detect/compare")
@limiter.limit("10/minute", key_func=get_user_key)
async def detect_compare(
    request: Request,
    img1: UploadFile = File(...),
    img2: UploadFile = File(...),
    models: str = Form(...),
    threshold: float = Form(...),
    lat_lng: str = Form(""),
    location: str = Form(""),
    change_type: str = Form(""),
    t1_time: str = Form(""),
    t2_time: str = Form(""),
    current_user = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """多模型对比检测：同一对影像用多个模型检测并并排对比结果。"""
    try:
        model_list = json.loads(models)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="models 参数格式错误，应为 JSON 数组")
    if not isinstance(model_list, list) or len(model_list) == 0:
        raise HTTPException(status_code=400, detail="至少选择一个模型")
    for m in model_list:
        if m not in SUPPORTED_MODELS:
            raise HTTPException(status_code=400, detail=f"不支持的模型: {m}")

    unique_id = str(uuid.uuid4())
    img1_bytes = await img1.read()
    img2_bytes = await img2.read()
    img_t1 = _decode_image(img1_bytes, "T1 影像")
    img_t2 = _decode_image(img2_bytes, "T2 影像")

    results = {}
    first_detection_id = None

    for i, model_name in enumerate(model_list):
        model_uid = f"{unique_id}_{model_name}"
        score_map, change_mask, heatmap, fusion, stats = await run_in_threadpool(
            detect_change, img_t1, img_t2, threshold, model_name, model_uid
        )

        mask_filename = f"{model_uid}_mask.png"
        heat_filename = f"{model_uid}_heat.png"
        fusion_filename = f"{model_uid}_fusion.png"
        score_filename = f"{model_uid}_score.png"
        imwrite(f"results/{mask_filename}", change_mask)
        imwrite(f"results/{heat_filename}", heatmap)
        imwrite(f"results/{fusion_filename}", fusion)
        # 概率图必须落盘。此前这里把 detect_change 返回的第一位丢掉了（写成 `_,`），
        # 于是对比检测建的记录永远缺 score_url，在**灾害定损 / Otsu / 重调阈值**
        # 三条路径上全被拒（「该记录缺少概率图」）—— 单张检测一直是对的，只有这条
        # 路径漏了。这就是手抄一份编排的代价：抄的时候少抄了一行。
        save_score_map(score_map, f"results/{score_filename}")

        results[model_name] = {
            "mask": _result_url(request, mask_filename),
            "heat": _result_url(request, heat_filename),
            "fusion": _result_url(request, fusion_filename),
            "score": _result_url(request, score_filename),
            "stats": stats,
        }

        # 第一个模型的结果写入 DB 作为主记录（仅登录用户）
        if i == 0 and current_user is not None:
            # T2 只为落库的那一条存：/detect/rethreshold 由 score 路径推出
            # {uid}_t2.png 来重建融合图，缺了就重建不出来。其余模型不落库，
            # 存了没人用，而 results/ 已经堆了几千个文件。
            # 用 PIL 保存而不是 cv2：cv2 按 BGR 解释数组，会红蓝互换。
            img_t2.save(f"results/{model_uid}_t2.png")
            detection = DetectionResultDB(
                user_id=current_user.id,
                model=model_name,
                threshold=threshold,
                ratio=stats["ratio"],
                change_pixel=stats["change_pixel"],
                total_pixel=stats["total_pixel"],
                lat_lng=lat_lng,
                location=location,
                change_type=change_type,
                t1_time=t1_time,
                t2_time=t2_time,
                mask_url=_result_url(request, mask_filename),
                heat_url=_result_url(request, heat_filename),
                fusion_url=_result_url(request, fusion_filename),
                score_url=_result_url(request, score_filename),
            )
            db.add(detection)
            db.commit()
            db.refresh(detection)
            first_detection_id = detection.id

    if current_user is not None:
        logger.info("模型对比: user=%s models=%s threshold=%.2f", current_user.username, model_list, threshold)
    else:
        logger.info("游客模型对比: models=%s threshold=%.2f", model_list, threshold)

    return JSONResponse(
        content={
            "code": 200,
            "msg": "模型对比检测完成",
            "detection_id": first_detection_id,
            "results": results,
        }
    )


@router.post("/detect/rethreshold")
@limiter.limit("20/minute", key_func=get_user_key)
async def rethreshold(
    request: Request,
    detection_id: int = Form(...),
    threshold: float = Form(...),
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """基于已有 score_map 和新的阈值重新生成 mask/heatmap/fusion。"""
    detection = find_owned_detection(db, current_user.id, detection_id)
    if not detection:
        raise HTTPException(status_code=404, detail="检测记录不存在")
    if not detection.score_url:
        raise HTTPException(status_code=400, detail="该记录缺少 score_map，无法重新调阈值")

    score_path = _url_to_path(detection.score_url)
    try:
        score_map = load_score_map(score_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="score_map 文件已丢失")

    change_mask, heatmap = apply_threshold(score_map, threshold)
    h, w = score_map.shape
    total_pixel = h * w
    change_pixel = int(np.sum(change_mask > 0))
    ratio = round(change_pixel / total_pixel * 100, 2)

    unique_id = str(uuid.uuid4())[:8]
    mask_filename = f"rethresh_{detection_id}_{unique_id}_mask.png"
    heat_filename = f"rethresh_{detection_id}_{unique_id}_heat.png"
    imwrite(f"results/{mask_filename}", change_mask)
    imwrite(f"results/{heat_filename}", heatmap)

    fusion_filename = f"rethresh_{detection_id}_{unique_id}_fusion.png"
    fusion = rebuild_fusion_from_score(score_path, change_mask)
    if fusion is not None:
        imwrite(f"results/{fusion_filename}", fusion)

    detection.threshold = round(threshold, 4)
    detection.ratio = ratio
    detection.change_pixel = change_pixel
    detection.total_pixel = total_pixel
    detection.mask_url = _result_url(request, mask_filename)
    detection.heat_url = _result_url(request, heat_filename)
    if fusion is not None:
        detection.fusion_url = _result_url(request, fusion_filename)
    else:
        # 早期记录没存 T2，重建不出来。置空而不是留着旧图——否则前端会同时
        # 显示新掩膜和旧融合图，两张图互相矛盾，比少一张图更糟。
        detection.fusion_url = None
    db.commit()

    return JSONResponse(content={
        "code": 200,
        "msg": "阈值已更新",
        "detection_id": detection_id,
        "mask": detection.mask_url,
        "heat": detection.heat_url,
        "fusion": detection.fusion_url,
        "stats": {
            "total_pixel": total_pixel,
            "change_pixel": change_pixel,
            "ratio": ratio,
            "threshold": round(threshold, 4),
        },
    })


@router.post("/detect/otsu")
@limiter.limit("20/minute", key_func=get_user_key)
async def compute_otsu(
    request: Request,
    detection_id: int = Form(...),
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """对已有检测结果的 score_map 计算 Otsu 最优阈值。"""
    detection = find_owned_detection(db, current_user.id, detection_id)
    if not detection:
        raise HTTPException(status_code=404, detail="检测记录不存在")
    if not detection.score_url:
        raise HTTPException(status_code=400, detail="该记录缺少 score_map")

    score_path = _url_to_path(detection.score_url)
    try:
        score_map = load_score_map(score_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="score_map 文件已丢失")

    best = otsu_threshold(score_map)
    return JSONResponse(content={"code": 200, "threshold": best})


@router.post("/detect/export-geojson")
@limiter.limit("20/minute", key_func=get_user_key)
async def export_geojson(
    request: Request,
    detection_id: int = Form(...),
    simplify: str = Form("true"),
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """导出变化掩膜为 GeoJSON 多边形。"""
    detection = find_owned_detection(db, current_user.id, detection_id)
    if not detection or not detection.mask_url:
        raise HTTPException(status_code=404, detail="检测记录不存在或无掩膜")

    mask_path = _url_to_path(detection.mask_url)
    mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise HTTPException(status_code=404, detail="掩膜文件已丢失")

    geojson = mask_to_geojson(mask, simplify=simplify.lower() != "false")
    return JSONResponse(content={"code": 200, "geojson": geojson})


@router.post("/detect/ndvi")
@limiter.limit("30/minute", key_func=get_user_key)
async def compute_ndvi(
    request: Request,
    img: UploadFile = File(...),
):
    """计算上传影像的 NDVI（归一化植被指数）。

    这里返回的多半是近似值而非定量 NDVI：上传解码基于 PIL，而 PIL 会把
    4 波段影像读成 RGBA（第 4 波段当作 alpha），近红外到不了 calc_ndvi。
    响应中的 approximate / note 字段如实说明了这一点，前端须展示该提示。

    mode=None 是刻意的不作为：不主动把影像压成 RGB，以免在将来换成能保留
    波段的数据源后，又因为这里丢通道而白费。单波段等不足 3 波的输入仍回退
    为 RGB，避免下游按索引取通道时报错。
    """
    img_bytes = await img.read()
    img_pil = _decode_image(img_bytes, "影像", mode=None, size=0)
    if len(img_pil.getbands()) < 3:
        img_pil = img_pil.convert("RGB")
    ndvi_result = calc_ndvi(img_pil)
    return JSONResponse(content={"code": 200, "ndvi": ndvi_result})


@router.post("/detect/check-registration")
@limiter.limit("30/minute", key_func=get_user_key)
async def check_img_registration(
    request: Request,
    img1: UploadFile = File(...),
    img2: UploadFile = File(...),
):
    """检查双时相影像是否配准对齐。"""
    img1_bytes = await img1.read()
    img2_bytes = await img2.read()
    img_t1 = _decode_image(img1_bytes, "T1 影像", size=0)
    img_t2 = _decode_image(img2_bytes, "T2 影像", size=0)
    result = await run_in_threadpool(check_registration, img_t1, img_t2)
    return JSONResponse(content={"code": 200, "registration": result})


@router.post("/detect/area-stats")
@limiter.limit("20/minute", key_func=get_user_key)
async def compute_area_stats(
    request: Request,
    detection_id: int = Form(...),
    resolution: float = Form(0),
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """计算变化区域的面积统计（支持传入空间分辨率 m/px）。"""
    detection = find_owned_detection(db, current_user.id, detection_id)
    if not detection or not detection.mask_url:
        raise HTTPException(status_code=404, detail="检测记录不存在或无掩膜")

    mask_path = _url_to_path(detection.mask_url)
    mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise HTTPException(status_code=404, detail="掩膜文件已丢失")

    res = resolution if resolution > 0 else None
    stats = calc_area_stats(mask, resolution_m_per_px=res)
    return JSONResponse(content={"code": 200, "area_stats": stats})


@router.post("/evaluate")
@limiter.limit("10/minute", key_func=get_user_key)
async def evaluate(
    request: Request,
    img1: UploadFile = File(...),
    img2: UploadFile = File(...),
    label: UploadFile = File(...),
    models: str = Form(...),
    threshold: float = Form(0.5),
    current_user: UserDB = Depends(get_current_user),
):
    """批量评估：一对影像 + 真值标签，运行多个模型并计算 Precision/Recall/F1/IoU。"""
    try:
        model_list = json.loads(models)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="models 参数格式错误")
    for m in model_list:
        if m not in SUPPORTED_MODELS:
            raise HTTPException(status_code=400, detail=f"不支持的模型: {m}")

    img1_bytes = await img1.read()
    img2_bytes = await img2.read()
    label_bytes = await label.read()

    img_t1 = _decode_image(img1_bytes, "T1 影像")
    img_t2 = _decode_image(img2_bytes, "T2 影像")
    img_label = _decode_image(label_bytes, "标签影像", mode=None)

    results = await run_in_threadpool(evaluate_models, img_t1, img_t2, img_label, model_list, threshold)

    return JSONResponse(content={
        "code": 200,
        "msg": "评估完成",
        "results": results,
    })


@router.post("/evaluate/scan")
@limiter.limit("5/minute", key_func=get_user_key)
async def evaluate_scan_endpoint(
    request: Request,
    img1: UploadFile = File(...),
    img2: UploadFile = File(...),
    label: UploadFile = File(...),
    models: str = Form(...),
    current_user: UserDB = Depends(get_current_user),
):
    """阈值扫描：对一对影像用多阈值评估，返回 F1/Precision/Recall/IoU 曲线。"""
    try:
        model_list = json.loads(models)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="models 参数格式错误")
    for m in model_list:
        if m not in SUPPORTED_MODELS:
            raise HTTPException(status_code=400, detail=f"不支持的模型: {m}")

    img1_bytes = await img1.read()
    img2_bytes = await img2.read()
    label_bytes = await label.read()

    img_t1 = _decode_image(img1_bytes, "T1 影像")
    img_t2 = _decode_image(img2_bytes, "T2 影像")
    img_label = _decode_image(label_bytes, "标签影像", mode=None)

    thresholds = [round(i * 0.05, 2) for i in range(1, 20)]
    results = await run_in_threadpool(evaluate_scan, img_t1, img_t2, img_label, model_list, thresholds)

    return JSONResponse(content={
        "code": 200,
        "msg": "阈值扫描完成",
        "results": results,
    })
