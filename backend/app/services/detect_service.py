import logging
import os
import sys
import threading
import time
import uuid

import cv2
import numpy as np
import torch
import torchvision.transforms as transforms
from PIL import Image

logger = logging.getLogger(__name__)


def _imwrite(path, img):
    if not cv2.imwrite(path, img):
        raise RuntimeError(f"无法写入文件: {path}")

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from backend.app.core.config import ML_CONFIG, MODEL_CONFIGS


class ModelNotAvailableError(RuntimeError):
    """模型权重缺失，无法提供推理服务。

    未训练的网络同样能跑通前向并输出"看似正常"的变化检测结果，且以 HTTP 200
    返回，前端与用户无从分辨 —— 因此权重缺失必须显式失败，而不是静默降级。
    """

    def __init__(self, model_type: str, ckpt_path: str):
        self.model_type = model_type
        self.ckpt_path = ckpt_path
        others = [m for m, ok in model_availability().items() if ok and m != model_type]
        hint = ("当前可用：" + "、".join(others)) if others else "当前没有其他可用模型"
        super().__init__(
            f"模型 {model_type} 未部署：缺少权重文件 {ckpt_path}。{hint}。"
        )


_device = None
_cd_models = {}
_model_locks = {}
_model_lock = threading.Lock()


def resolve_checkpoint_path(model_type):
    """模型权重的绝对路径；无需权重的模型（如 DIFF）返回 None。"""
    cfg = MODEL_CONFIGS.get(model_type)
    if cfg is None or cfg["net_G"] is None:
        return None
    return os.path.join(
        ML_CONFIG["checkpoint_root"], cfg["project_name"], cfg["checkpoint_name"]
    )


def is_model_available(model_type):
    """该模型此刻是否真的能出结果。

    注册表里有、磁盘上没有的模型（FC_SIAM_DIFF / SNUNET / CHANGEFORMER 就属于
    这种），调用时只会拿到 503。与其让前端把不可用的模型列出来让用户撞墙，
    不如提供一个可查询的真实能力清单。
    """
    cfg = MODEL_CONFIGS.get(model_type)
    if cfg is None:
        return False          # 注册表里根本没有这个模型
    if cfg["net_G"] is None:
        return True           # 不需要权重即可工作（像素差分）
    return os.path.exists(resolve_checkpoint_path(model_type))


def model_availability():
    """{模型名: 是否可用}，覆盖注册表中全部模型。"""
    return {name: is_model_available(name) for name in MODEL_CONFIGS}


def get_device():
    global _device
    if _device is None:
        from core import utils
        from argparse import Namespace

        args = Namespace(**ML_CONFIG)
        utils.get_device(args)
        _device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return _device


def get_model(model_type="BIT"):
    global _cd_models, _model_locks
    if model_type in _cd_models:
        return _cd_models[model_type]

    if model_type == "AFCF3D":
        return _get_afcf3d_model()

    cfg = MODEL_CONFIGS.get(model_type)
    if cfg is None or cfg["net_G"] is None:
        raise ValueError("不支持的模型类型: %s" % model_type)

    # 每个模型独立锁，防止并发请求同时加载同一模型
    with _model_lock:
        if model_type not in _model_locks:
            _model_locks[model_type] = threading.Lock()
        lock = _model_locks[model_type]

    with lock:
        if model_type in _cd_models:
            return _cd_models[model_type]

        from argparse import Namespace
        from models.basic_model import CDEvaluator

        args = Namespace(**ML_CONFIG)
        args.device = get_device()
        args.net_G = cfg["net_G"]
        args.project_name = cfg["project_name"]
        args.checkpoint_name = cfg["checkpoint_name"]
        args.checkpoint_dir = os.path.join(args.checkpoint_root, args.project_name)

        logger.info("加载模型 %s (net_G=%s, checkpoint=%s/%s)",
                    model_type, cfg["net_G"], cfg["project_name"], cfg["checkpoint_name"])

        cd_evaluator = CDEvaluator(args)
        ckpt_path = os.path.join(args.checkpoint_dir, cfg["checkpoint_name"])
        if not os.path.exists(ckpt_path):
            raise ModelNotAvailableError(model_type, ckpt_path)
        cd_evaluator.load_checkpoint(cfg["checkpoint_name"])
        logger.info("模型 %s 已加载 CD 预训练权重", model_type)
        cd_evaluator.eval()
        _cd_models[model_type] = cd_evaluator
        return cd_evaluator


def _get_afcf3d_model():
    """加载 AFCF3D-Net 模型（3D 卷积架构，独立于 CDEvaluator）"""
    global _cd_models, _model_locks

    with _model_lock:
        if "AFCF3D" not in _model_locks:
            _model_locks["AFCF3D"] = threading.Lock()
        lock = _model_locks["AFCF3D"]

    with lock:
        if "AFCF3D" in _cd_models:
            return _cd_models["AFCF3D"]

        import torchvision
        from models.afcf3d import Netmodel

        device = get_device()
        cfg = MODEL_CONFIGS["AFCF3D"]

        logger.info("加载 AFCF3D-Net 模型 (checkpoint=%s/%s)",
                    cfg["project_name"], cfg["checkpoint_name"])

        resnet = torchvision.models.resnet18(pretrained=True)
        model = Netmodel(32, resnet)
        model = model.to(device)

        ckpt_path = os.path.join(ML_CONFIG["checkpoint_root"], cfg["project_name"], cfg["checkpoint_name"])
        if not os.path.exists(ckpt_path):
            raise ModelNotAvailableError("AFCF3D", ckpt_path)
        # weights_only=False required for custom model architectures (checkpoints are trusted)
        state_dict = torch.load(ckpt_path, map_location=device, weights_only=False)
        model.load_state_dict(state_dict)
        logger.info("AFCF3D-Net 权重加载成功: %s", ckpt_path)
        model.eval()
        _cd_models["AFCF3D"] = model
        return model


def detect_change(img1_pil, img2_pil, threshold, model_type, unique_id):
    device = get_device()

    transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])

    if model_type == "DIFF":
        score_map = _diff_change_detect(img1_pil, img2_pil)
    elif model_type == "AFCF3D":
        t1 = transform(img1_pil).unsqueeze(0).to(device)
        t2 = transform(img2_pil).unsqueeze(0).to(device)
        t1 = t1.unsqueeze(2)  # (1, 3, 1, 256, 256)
        t2 = t2.unsqueeze(2)
        x = torch.cat([t1, t2], dim=2)  # (1, 3, 2, 256, 256)
        with torch.no_grad():
            model = get_model("AFCF3D")
            pred = model(x)
            score_map = pred.squeeze().cpu().numpy()
    else:
        t1 = transform(img1_pil).unsqueeze(0).to(device)
        t2 = transform(img2_pil).unsqueeze(0).to(device)
        batch = {"A": t1, "B": t2, "name": [unique_id], "ori_size": [(256, 256)]}
        with torch.no_grad():
            cd_model = get_model(model_type)
            score_map = cd_model._forward_pass(batch).squeeze().cpu().numpy()

    h, w = score_map.shape
    change_mask = (score_map > threshold).astype(np.uint8) * 255
    heatmap = _get_heatmap(score_map)
    fusion = get_fusion(img2_pil, change_mask)

    total_pixel = h * w
    change_pixel = int(np.sum(change_mask > 0))
    ratio = round(change_pixel / total_pixel * 100, 2)

    return score_map, change_mask, heatmap, fusion, {
        "total_pixel": total_pixel,
        "change_pixel": change_pixel,
        "ratio": ratio,
        "threshold": round(threshold, 2),
    }


def save_score_map(score_map, path):
    """将 score_map 保存为 PNG（0-1 float → 0-255 uint8），供前端重新调阈值。"""
    score_uint8 = (np.clip(score_map, 0, 1) * 255).astype(np.uint8)
    _imwrite(path, score_uint8)


def load_score_map(path):
    """从 PNG 加载 score_map，恢复到 0-1 float 范围。"""
    arr = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if arr is None:
        raise FileNotFoundError("score_map 文件不存在: %s" % path)
    return arr.astype(np.float32) / 255.0


def apply_threshold(score_map, threshold):
    """对 score_map 应用阈值，返回 mask / heatmap / fusion (PIL Image 输入时用 img2_pil)。"""
    change_mask = (score_map > threshold).astype(np.uint8) * 255
    heatmap = _get_heatmap(score_map)
    return change_mask, heatmap


def otsu_threshold(score_map):
    """对 score_map 计算 Otsu 最优阈值。返回 0-1 范围的 float。"""
    score_uint8 = (np.clip(score_map, 0, 1) * 255).astype(np.uint8)
    otsu_val, _ = cv2.threshold(score_uint8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return round(float(otsu_val) / 255.0, 4)


def recommend_threshold_from_images(img1_pil, img2_pil):
    arr1 = np.array(img1_pil, dtype=np.float32)
    arr2 = np.array(img2_pil, dtype=np.float32)
    diff = np.abs(arr1 - arr2)
    if np.max(diff) < 1e-6:
        return 0.5
    diff_uint8 = (diff / np.max(diff) * 255).astype(np.uint8)
    otsu_threshold, _ = cv2.threshold(diff_uint8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    recommended = otsu_threshold / 255.0
    return round(max(0.1, min(0.9, recommended)), 4)


def _diff_change_detect(img1_pil, img2_pil):
    gray1 = cv2.cvtColor(np.array(img1_pil), cv2.COLOR_RGB2GRAY)
    gray2 = cv2.cvtColor(np.array(img2_pil), cv2.COLOR_RGB2GRAY)
    diff = cv2.absdiff(gray1, gray2)
    return diff.astype(np.float32) / 255.0


def _get_heatmap(score_map):
    score_norm = (score_map - score_map.min()) / (score_map.max() - score_map.min() + 1e-8)
    return cv2.applyColorMap(np.uint8(score_norm * 255), cv2.COLORMAP_JET)


def get_fusion(img, mask, alpha=0.6):
    """把掩膜半透明叠加到 T2 原图上。img 为 PIL Image 或 HWC 数组。"""
    img_arr = np.array(img)
    mask_rgb = np.dstack([mask, mask, mask])
    return cv2.addWeighted(img_arr, 1 - alpha, mask_rgb, alpha, 0)


def rebuild_fusion_from_score(score_path, change_mask):
    """由 score_map 路径推出同期的 T2，重建融合图。

    /detect 会把 T2 以 {uid}_t2.png 与 {uid}_score.png 相邻存下，所以这里
    可以直接由 score_map 路径推出 T2，无需改表结构。
    早期记录（存这份 T2 之前产生的）找不到文件，返回 None 由调用方决定
    如何处理——绝不能退回去用旧融合图，那会和刚生成的掩膜自相矛盾。
    """
    t2_path = score_path.replace("_score.png", "_t2.png")
    if not os.path.exists(t2_path):
        logger.warning("缺少 T2 影像，无法重建融合图: %s", t2_path)
        return None
    try:
        with Image.open(t2_path) as t2:
            return get_fusion(t2.convert("RGB"), change_mask)
    except Exception:
        logger.exception("重建融合图失败: %s", t2_path)
        return None


def mask_to_geojson(mask, simplify=True):
    """将变化掩膜转换为 GeoJSON FeatureCollection（多边形轮廓）。
    mask: uint8 [H,W] 0/255
    返回 dict 可直接 JSON.dumps。"""
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    features = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 4:  # 过滤噪音点
            continue
        if simplify and len(cnt) > 4:
            epsilon = 0.005 * cv2.arcLength(cnt, True)
            cnt = cv2.approxPolyDP(cnt, epsilon, True)
        coords = cnt.squeeze().tolist()
        if len(cnt.shape) == 3 and cnt.shape[1] == 1:
            if len(coords) < 3:
                continue
        else:
            coords = [[float(x), float(y)] for x, y in coords]
            if len(coords) < 3:
                continue
        features.append({
            "type": "Feature",
            "properties": {"area_px": round(area, 1)},
            "geometry": {"type": "Polygon", "coordinates": [coords + [coords[0]]]},
        })
    return {"type": "FeatureCollection", "features": features}


def calc_area_stats(change_mask, resolution_m_per_px=None):
    """计算变化面积统计。resolution_m_per_px 为每像素对应米数，不传则只给像素数。"""
    total_px = int(change_mask.shape[0] * change_mask.shape[1])
    change_px = int(np.sum(change_mask > 0))
    ratio_pct = round(change_px / total_px * 100, 2)
    result = {
        "total_pixel": total_px,
        "change_pixel": change_px,
        "ratio_pct": ratio_pct,
    }
    if resolution_m_per_px:
        m2_per_px = resolution_m_per_px ** 2
        result["change_area_m2"] = round(change_px * m2_per_px, 2)
        result["change_area_mu"] = round(change_px * m2_per_px / 666.67, 2)  # 亩
        result["change_area_ha"] = round(change_px * m2_per_px / 10000, 4)   # 公顷
        result["resolution_m"] = resolution_m_per_px
    return result


def calc_ndvi(img_pil):
    """计算 NDVI（归一化植被指数）。

    近红外的来源有两种，可解释性差别极大，所以结果里一并声明：

    - 影像确有第 4 个非 alpha 波段时，按 RGBN 惯例取第 4 波段作近红外，
      此时 approximate=False，是通常意义上的 NDVI。
    - 只有 RGB 时没有近红外可用，退而用蓝波段顶替（approximate=True）。
      这不是定量 NDVI —— 蓝波段与近红外的光谱响应没有对应关系，其数值
      只在同一批影像内部有相对意义，不能跨影像比较，也不能当作植被覆盖度。
      此前该字段对二者不加区分，界面上把近似值当成真实 NDVI 展示。

    需要清楚的是：**当前实际输入几乎必然走近似路径**。上传解码基于 PIL，
    而 PIL 会把 4 波段 TIFF 直接读成 RGBA（第 4 波段被当作 alpha），
    多光谱影像的近红外根本传不到这里。上面那条真近红外分支是为将来换成
    能保留波段的数据源（如 tifffile/rasterio 直读 GeoTIFF）预留的，
    在此之前 approximate 恒为 True，界面必须始终显示该提示。
    """
    bands = img_pil.getbands()
    arr = np.array(img_pil, dtype=np.float32)

    if len(bands) >= 4 and bands[3] != "A":
        nir = arr[:, :, 3]
        nir_source = "band4"
        approximate = False
        note = "近红外取自影像第 4 波段。"
    else:
        nir = arr[:, :, 2]
        nir_source = "blue_proxy"
        approximate = True
        note = (
            "影像无近红外波段，此处以蓝波段近似，不是定量 NDVI；"
            "数值仅可在同一批影像内作相对比较，不可作为植被覆盖度使用。"
        )

    red = arr[:, :, 0]
    denom = nir + red
    denom[denom == 0] = 1.0
    ndvi_clamped = np.clip((nir - red) / denom, -1, 1)

    # NDVI 分类
    water = int(np.sum(ndvi_clamped < 0))
    bare = int(np.sum((ndvi_clamped >= 0) & (ndvi_clamped < 0.2)))
    veg_low = int(np.sum((ndvi_clamped >= 0.2) & (ndvi_clamped < 0.4)))
    veg_mid = int(np.sum((ndvi_clamped >= 0.4) & (ndvi_clamped < 0.6)))
    veg_high = int(np.sum(ndvi_clamped >= 0.6))

    return {
        "ndvi_min": round(float(ndvi_clamped.min()), 4),
        "ndvi_max": round(float(ndvi_clamped.max()), 4),
        "ndvi_mean": round(float(ndvi_clamped.mean()), 4),
        "ndvi_std": round(float(ndvi_clamped.std()), 4),
        "classification": {
            "water": water, "bare_soil": bare,
            "low_veg": veg_low, "mid_veg": veg_mid, "high_veg": veg_high,
        },
        "approximate": approximate,
        "nir_source": nir_source,
        "n_bands": len(bands),
        "note": note,
    }


def check_registration(img1_pil, img2_pil):
    """快速检查两幅影像是否配准对齐：检查尺寸 + 亮度相关性。"""
    if img1_pil.size != img2_pil.size:
        return {"aligned": False, "reason": f"尺寸不一致: {img1_pil.size} vs {img2_pil.size}", "score": 0.0}

    g1 = cv2.cvtColor(np.array(img1_pil), cv2.COLOR_RGB2GRAY).astype(np.float32)
    g2 = cv2.cvtColor(np.array(img2_pil), cv2.COLOR_RGB2GRAY).astype(np.float32)

    # 归一化互相关系数
    g1_n = g1 - g1.mean()
    g2_n = g2 - g2.mean()
    corr = np.sum(g1_n * g2_n) / (np.sqrt(np.sum(g1_n ** 2)) * np.sqrt(np.sum(g2_n ** 2)) + 1e-8)
    corr = round(float(corr), 4)

    if corr < 0.3:
        return {"aligned": False, "reason": f"空间相关性过低 ({corr})，可能未配准", "score": corr}
    return {"aligned": True, "reason": "尺寸一致，相关性正常", "score": corr}


def compute_metrics(pred_mask, gt_mask):
    """计算二分类变化检测指标。pred_mask/gt_mask: uint8 [H,W] 0/255。"""
    pred_bool = (pred_mask > 127)
    gt_bool = (gt_mask > 127)
    tp = int(np.sum(pred_bool & gt_bool))
    fp = int(np.sum(pred_bool & ~gt_bool))
    fn = int(np.sum(~pred_bool & gt_bool))
    tn = int(np.sum(~pred_bool & ~gt_bool))

    precision = tp / (tp + fp) * 100 if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) * 100 if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    iou = tp / (tp + fp + fn) * 100 if (tp + fp + fn) > 0 else 0.0

    return {
        "precision": round(precision, 2),
        "recall": round(recall, 2),
        "f1": round(f1, 2),
        "iou": round(iou, 2),
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
    }


def evaluate_models(img1_pil, img2_pil, label_pil, model_list, threshold=0.5, save_masks=False):
    """批量评估多个模型：对同一对影像运行所有模型，与真值标签对比。"""
    device = get_device()

    transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])
    t1_tensor = transform(img1_pil).unsqueeze(0).to(device)
    t2_tensor = transform(img2_pil).unsqueeze(0).to(device)

    gt_arr = np.array(label_pil.convert("L"), dtype=np.uint8)
    if gt_arr.max() <= 1:
        gt_arr = (gt_arr * 255).astype(np.uint8)

    results = {}
    for model_name in model_list:
        t0 = time.perf_counter()
        if model_name == "DIFF":
            score_map = _diff_change_detect(img1_pil, img2_pil)
        elif model_name == "AFCF3D":
            img_5d = torch.cat([t1_tensor.unsqueeze(2), t2_tensor.unsqueeze(2)], dim=2)
            with torch.no_grad():
                model = get_model("AFCF3D")
                score_map = model(img_5d).squeeze().cpu().numpy()
        else:
            with torch.no_grad():
                cd_model = get_model(model_name)
                batch = {"A": t1_tensor, "B": t2_tensor, "name": ["eval"], "ori_size": [(256, 256)]}
                score_map = cd_model._forward_pass(batch).squeeze().cpu().numpy()
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)

        pred_mask = (score_map > threshold).astype(np.uint8) * 255
        metrics = compute_metrics(pred_mask, gt_arr)
        metrics["threshold"] = round(threshold, 2)
        metrics["time_ms"] = elapsed_ms

        if save_masks:
            uid = str(uuid.uuid4())[:8]
            _imwrite(f"results/eval_{model_name}_{uid}_mask.png", pred_mask)
            metrics["mask_url"] = f"/results/eval_{model_name}_{uid}_mask.png"

        results[model_name] = metrics

    return results


def evaluate_scan(img1_pil, img2_pil, label_pil, model_list, thresholds):
    """阈值扫描：对同一对影像用多个阈值评估，返回每模型每阈值的 F1。"""
    device = get_device()
    transform = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])
    t1_tensor = transform(img1_pil).unsqueeze(0).to(device)
    t2_tensor = transform(img2_pil).unsqueeze(0).to(device)

    gt_arr = np.array(label_pil.convert("L"), dtype=np.uint8)
    if gt_arr.max() <= 1:
        gt_arr = (gt_arr * 255).astype(np.uint8)

    results = {}
    for model_name in model_list:
        if model_name == "DIFF":
            score_map = _diff_change_detect(img1_pil, img2_pil)
        elif model_name == "AFCF3D":
            img_5d = torch.cat([t1_tensor.unsqueeze(2), t2_tensor.unsqueeze(2)], dim=2)
            with torch.no_grad():
                model = get_model("AFCF3D")
                score_map = model(img_5d).squeeze().cpu().numpy()
        else:
            with torch.no_grad():
                cd_model = get_model(model_name)
                batch = {"A": t1_tensor, "B": t2_tensor, "name": ["scan"], "ori_size": [(256, 256)]}
                score_map = cd_model._forward_pass(batch).squeeze().cpu().numpy()

        curve = []
        for t in thresholds:
            pred_mask = (score_map > t).astype(np.uint8) * 255
            m = compute_metrics(pred_mask, gt_arr)
            curve.append({"threshold": round(t, 2), "f1": m["f1"], "precision": m["precision"], "recall": m["recall"], "iou": m["iou"]})
        results[model_name] = curve

    return results
