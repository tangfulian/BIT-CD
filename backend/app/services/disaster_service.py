"""农业灾害定损。

诚实性前提（本模块的设计中心）：

    模型给出的 score 是「该像素发生变化的置信度」，**不是「减产率」**。
    两者之间没有任何经过验证的换算关系。

因此本模块严格区分两类数值：

    系统算出的  各级受灾面积 —— 由像素占比摊派得到，可复现
    调用方假设的 损失率、亩产、单价 —— 由人给定，不是模型推断的结论

返回体里用 assumptions 字段把后者单独列出来，前端与导出文件都必须把它们
连同「假设」标记一起展示，不得渲染成系统测算结论。
"""

import numpy as np

SEVERITY_LEVELS = ("mild", "moderate", "severe", "total")
SEVERITY_LABELS = {
    "mild": "轻度",
    "moderate": "中度",
    "severe": "重度",
    "total": "绝收",
}

# 分级下界（score 值）。mild 为下界以下的全部变化像素。
# 这是一组**可调假设**，不是行业标准值：它把"模型确信度"当作"受灾程度"的
# 代理，这个代理关系本身需要实地抽样校验。界面必须允许修改并如此说明。
DEFAULT_GRADE_BOUNDS = {
    "moderate": 0.60,
    "severe": 0.75,
    "total": 0.92,
}

# 各等级对应的减产比例（假设值）。
# 理赔实务中"全部损失"通常指损失率≥80%，此处绝收按 100% 计。
DEFAULT_LOSS_RATES = {
    "mild": 0.20,
    "moderate": 0.40,
    "severe": 0.70,
    "total": 1.00,
}

# 分作物示例参考值。**不是统计年鉴数据**，仅供演示时给出量级；
# 界面每一项都可编辑，并标注"示例参考值，请按当地统计年鉴或保险条款替换"。
DEFAULT_CROP_PARAMS = {
    "玉米连作": {"yield_per_mu": 550.0, "price_per_kg": 2.30},
    "玉米-大豆轮作": {"yield_per_mu": 480.0, "price_per_kg": 2.60},
    "大豆连作": {"yield_per_mu": 140.0, "price_per_kg": 4.60},
    "水稻": {"yield_per_mu": 520.0, "price_per_kg": 2.70},
    "杂粮作物": {"yield_per_mu": 200.0, "price_per_kg": 3.50},
}

# 查勘成本**参考区间**（元/亩）。来自农业保险遥感技术应用规范相关的行业公开
# 报道，**不是本项目实测数据**。这里只用于展示与说明取值依据。
SURVEY_COST_REFERENCE = {
    "manual_per_mu": (8.0, 12.0),
    "remote_per_mu": (2.0, 5.0),
    "manual_days": 15,
    "remote_days": 5,
    "source_note": "行业公开报道区间（非本项目实测），可在界面调整",
}

# 实际参与计算的点估计值：取上述区间的中值。区间本身在界面上另行展示，
# 以便使用者知道这个数是怎么来的、以及它的不确定范围有多大。
DEFAULT_SURVEY_COSTS = {
    "manual_per_mu": 10.0,
    "remote_per_mu": 3.5,
    "manual_days": SURVEY_COST_REFERENCE["manual_days"],
    "remote_days": SURVEY_COST_REFERENCE["remote_days"],
    "source_note": SURVEY_COST_REFERENCE["source_note"],
}

ASSUMPTION_NOTE = "示例参考值，请按当地统计年鉴或保险条款替换"


def grade_severity(score_map, change_mask, grade_bounds=None):
    """把变化像素按 score 值分四级。

    score_map: 0-1 浮点数组（模型输出的变化概率）
    change_mask: 0/255 uint8，仅 mask>0 的像素参与分级
    grade_bounds: {moderate, severe, total} 三个下界，缺省用 DEFAULT_GRADE_BOUNDS

    返回 {level: {"pixels": int, "share": float}}，share 为该级占全部变化像素的比例。
    没有变化像素时全部为 0（调用方需自行避免除零）。
    """
    bounds = dict(DEFAULT_GRADE_BOUNDS)
    if grade_bounds:
        for key in ("moderate", "severe", "total"):
            if grade_bounds.get(key) is not None:
                bounds[key] = float(grade_bounds[key])

    mask = np.asarray(change_mask) > 0
    score = np.asarray(score_map, dtype=np.float32)

    if mask.shape != score.shape:
        raise ValueError(
            f"掩膜与概率图尺寸不一致: {mask.shape} vs {score.shape}"
        )

    changed = score[mask]
    total_changed = int(changed.size)

    if total_changed == 0:
        return {
            lvl: {"pixels": 0, "share": 0.0} for lvl in SEVERITY_LEVELS
        }

    counts = {
        "mild": int(np.sum(changed < bounds["moderate"])),
        "moderate": int(
            np.sum((changed >= bounds["moderate"]) & (changed < bounds["severe"]))
        ),
        "severe": int(
            np.sum((changed >= bounds["severe"]) & (changed < bounds["total"]))
        ),
        "total": int(np.sum(changed >= bounds["total"])),
    }

    return {
        lvl: {
            "pixels": counts[lvl],
            "share": round(counts[lvl] / total_changed, 6),
        }
        for lvl in SEVERITY_LEVELS
    }


def assess(
    score_map,
    change_mask,
    area_mu,
    yield_per_mu,
    price_per_kg,
    loss_rates=None,
    grade_bounds=None,
    survey_costs=None,
):
    """定损计算。全部为确定性算术，不依赖任何模型或外部服务。

    各级面积按「该级像素数 / **影像总像素数**」摊派到地块总面积。

    分母必须是总像素而不是变化像素：地块面积对应整幅影像，只有发生变化的那
    部分才受灾。若按变化像素摊派，四级面积之和会等于地块总面积，等于无论检出
    多少变化都把整块地报成受灾 —— 一块 100 亩的地检出 3.81% 变化时会报出
    100 亩受灾，而不是 3.81 亩。

    返回体里的 assumptions 列出所有由人给定、而非本系统推断的数值。
    """
    rates = dict(DEFAULT_LOSS_RATES)
    if loss_rates:
        for lvl in SEVERITY_LEVELS:
            if loss_rates.get(lvl) is not None:
                rates[lvl] = float(loss_rates[lvl])

    graded = grade_severity(score_map, change_mask, grade_bounds)
    changed_px = sum(g["pixels"] for g in graded.values())
    total_px = int(np.asarray(change_mask).size)

    area_mu = float(area_mu or 0.0)
    yield_per_mu = float(yield_per_mu or 0.0)
    price_per_kg = float(price_per_kg or 0.0)

    levels = []
    total_loss = 0.0
    affected_area = 0.0

    for lvl in SEVERITY_LEVELS:
        # 各级面积 = 地块总面积 × 该级像素数 / 影像总像素数
        # 无变化像素时为 0，不会除零
        lvl_area = (
            round(area_mu * graded[lvl]["pixels"] / total_px, 4)
            if total_px else 0.0
        )
        # 损失 = 面积 × 亩产 × 单价 × 该级减产比例
        lvl_loss = round(lvl_area * yield_per_mu * price_per_kg * rates[lvl], 2)
        levels.append({
            "level": lvl,
            "label": SEVERITY_LABELS[lvl],
            "pixels": graded[lvl]["pixels"],
            "share": graded[lvl]["share"],
            "area_mu": lvl_area,
            "loss_rate": rates[lvl],
            "loss_yuan": lvl_loss,
        })
        total_loss += lvl_loss
        affected_area += lvl_area

    costs = dict(DEFAULT_SURVEY_COSTS)
    if survey_costs:
        for key in ("manual_per_mu", "remote_per_mu", "manual_days", "remote_days"):
            if survey_costs.get(key) is not None:
                costs[key] = survey_costs[key]

    manual_per_mu = float(costs["manual_per_mu"])
    remote_per_mu = float(costs["remote_per_mu"])
    manual_cost = round(affected_area * manual_per_mu, 2)
    remote_cost = round(affected_area * remote_per_mu, 2)

    return {
        "levels": levels,
        "affected_area_mu": round(affected_area, 4),
        "plot_area_mu": round(area_mu, 4),
        "change_pixel": changed_px,
        "total_loss_yuan": round(total_loss, 2),
        "survey_cost": {
            "manual_per_mu": manual_per_mu,
            "remote_per_mu": remote_per_mu,
            "manual_cost_yuan": manual_cost,
            "remote_cost_yuan": remote_cost,
            "saving_yuan": round(manual_cost - remote_cost, 2),
            "manual_days": costs["manual_days"],
            "remote_days": costs["remote_days"],
            "source_note": costs.get("source_note", SURVEY_COST_REFERENCE["source_note"]),
        },
        # 诚实性核心：这些是人给的假设，不是系统推断出来的结论
        "assumptions": [
            {"key": "yield_per_mu", "label": "亩产", "value": yield_per_mu,
             "unit": "kg/亩", "note": ASSUMPTION_NOTE},
            {"key": "price_per_kg", "label": "单价", "value": price_per_kg,
             "unit": "元/kg", "note": ASSUMPTION_NOTE},
            *[
                {"key": f"loss_rate.{lvl}", "label": f"{SEVERITY_LABELS[lvl]}减产比例",
                 "value": rates[lvl], "unit": "比例", "note": ASSUMPTION_NOTE}
                for lvl in SEVERITY_LEVELS
            ],
            {"key": "grade_bounds", "label": "受灾分级下界",
             "value": grade_bounds or dict(DEFAULT_GRADE_BOUNDS), "unit": "score",
             "note": "把模型确信度当作受灾程度的代理，需实地抽样校验"},
            {"key": "survey_cost", "label": "查勘成本单价",
             "value": {"manual": manual_per_mu, "remote": remote_per_mu},
             "unit": "元/亩",
             "note": costs.get("source_note", SURVEY_COST_REFERENCE["source_note"])},
        ],
        "formula": {
            "area": "各级面积 = 地块总面积 × (该级像素数 / 影像总像素数)",
            "loss": "各级损失 = 各级面积 × 亩产 × 单价 × 该级减产比例",
            "saving": "节省 = (人工查勘单价 − 遥感定损单价) × 受灾面积",
        },
    }


def build_narrative_prompt(result, location="", change_type="", crop_type=""):
    """构造定损说明草稿的 prompt。

    只喂数值，不喂图像 —— 现有 AI 链路本就不传图，prompt 里也不得暗示
    "模型看出来了什么"，否则等于伪造观测。
    """
    lines = [
        "请根据以下**已计算好的**定损数据，写一段 200-300 字的定损说明草稿，"
        "供理赔人员参考。要求：只陈述下列数据，不要推测数据中没有的信息，"
        "不要给出赔付结论。\n",
        f"地块位置：{location or '未填写'}",
        f"种植作物：{crop_type or '未填写'}",
        f"变化类型：{change_type or '未填写'}",
        f"地块总面积：{result['plot_area_mu']} 亩",
        f"受灾面积：{result['affected_area_mu']} 亩",
        f"变化像素数：{result['change_pixel']}",
        "",
        "受灾分级：",
    ]
    for lvl in result["levels"]:
        lines.append(
            f"  {lvl['label']}：{lvl['area_mu']} 亩，"
            f"假设减产比例 {lvl['loss_rate'] * 100:.0f}%，"
            f"估算损失 {lvl['loss_yuan']} 元"
        )
    lines += [
        "",
        f"估算总损失：{result['total_loss_yuan']} 元",
        f"人工查勘成本：{result['survey_cost']['manual_cost_yuan']} 元"
        f"（{result['survey_cost']['manual_per_mu']} 元/亩）",
        f"遥感定损成本：{result['survey_cost']['remote_cost_yuan']} 元"
        f"（{result['survey_cost']['remote_per_mu']} 元/亩）",
        "",
        "注意：减产比例与单价均为假设参数，请在文中如实说明这是基于假设的估算，"
        "需实地抽样核验。",
    ]
    return "\n".join(lines)


# 草稿标记。系统提示词里已要求模型自己输出，但那是 best-effort ——
# 模型可能漏。所以再用 ensure_draft_label 做一次确定性追加，
# 使"这段文字是草稿"不依赖于模型是否听话。
DRAFT_MARKER = "【AI 草稿，需人工复核；不作为理赔依据。】"

IMAGE_DISCLAIMER = "本说明由大模型根据上述数值生成，模型未接收任何影像数据。"


def ensure_draft_label(text: str) -> str:
    """确保草稿正文末尾带有标记；已有则不重复追加（幂等）。"""
    body = (text or "").rstrip()
    if DRAFT_MARKER in body:
        return body
    return f"{body}\n\n{DRAFT_MARKER}" if body else DRAFT_MARKER
