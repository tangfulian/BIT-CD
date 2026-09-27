"""多时相序列的趋势分析。

本模块全是纯函数，不碰数据库、不调外部服务，便于单测。

分析口径上有几处必须说清楚，它们都以 caveats 字段随结果一起返回，
前端不得省略：

1. 每个区间是一次**独立**检测，不是对同一现象的连续累计测量。相邻区间
   检出的变化未必是同一种地物变化。
2. 「突变点」是启发式判定（速率超过其余区间中位数的两倍），**不是统计检验**，
   期次少时尤其容易误报。
3. R² 在 n=3~5 时极不稳定，必须结合 n 一起判读。
4. 日期由使用者填写，系统无法校验影像的真实拍摄时间。
5. 本模块**不外推**未来期次 —— 黑土退化存在政策干预等拐点，线性外推会给出
   看似精确实则无依据的预测。
"""
import re
from datetime import date

MONTH_RE = re.compile(r"^(\d{4})-(\d{1,2})$")

# 判定突变点的倍数阈值：某区间速率超过其余区间中位数这么多倍时标出
BREAKPOINT_RATIO = 2.0
# 少于这么多个区间时不做突变点判定（样本太少，判了也是噪声）
MIN_INTERVALS_FOR_BREAKPOINT = 3


def parse_month(value):
    """"2024-05" → date(2024, 5, 1)；无法解析返回 None。

    只接受 年-月。日粒度对退化监测没有意义，且界面上的控件就是 month 型。
    """
    if not value:
        return None
    m = MONTH_RE.match(str(value).strip())
    if not m:
        return None
    year, month = int(m.group(1)), int(m.group(2))
    if not (1 <= month <= 12) or not (1900 <= year <= 2200):
        return None
    return date(year, month, 1)


def build_intervals(records, area_mu=0.0):
    """把序列成员整理成按时间排序的区间列表。

    records: [{"detection_id", "t1_time", "t2_time", "ratio",
               "change_pixel", "total_pixel", "model", "change_type"}]

    返回 (intervals, skipped)：
      intervals —— 起止日期可解析的记录，按起始日期升序
      skipped   —— 因日期缺失/非法被排除的记录，附原因（如实告知，不静默丢弃）
    """
    intervals = []
    skipped = []

    for r in records:
        start = parse_month(r.get("t1_time"))
        end = parse_month(r.get("t2_time"))
        if start is None or end is None:
            skipped.append({
                "detection_id": r.get("detection_id"),
                "reason": "缺少有效的影像日期（需形如 2024-05）",
                "t1_time": r.get("t1_time", ""),
                "t2_time": r.get("t2_time", ""),
            })
            continue
        if end <= start:
            skipped.append({
                "detection_id": r.get("detection_id"),
                "reason": "末期日期不晚于首期日期",
                "t1_time": r.get("t1_time", ""),
                "t2_time": r.get("t2_time", ""),
            })
            continue

        days = (end - start).days
        years = days / 365.25
        ratio_pct = float(r.get("ratio") or 0.0)
        # 区间变化面积 = 地块总面积 × 该期变化比例。地块面积由使用者提供，
        # 未提供时面积与面积速率均为 None，只给百分比口径。
        change_area_mu = round(area_mu * ratio_pct / 100.0, 4) if area_mu else None

        intervals.append({
            "detection_id": r.get("detection_id"),
            "model": r.get("model", ""),
            "change_type": r.get("change_type", ""),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "days": days,
            "years": round(years, 4),
            "ratio_pct": ratio_pct,
            "change_pixel": r.get("change_pixel"),
            "total_pixel": r.get("total_pixel"),
            "change_area_mu": change_area_mu,
            "rate_pct_per_year": round(ratio_pct / years, 4) if years > 0 else None,
            "rate_area_per_year": (
                round(change_area_mu / years, 4)
                if (change_area_mu is not None and years > 0) else None
            ),
        })

    intervals.sort(key=lambda i: (i["start"], i["end"]))
    return intervals, skipped


def _linear_fit(xs, ys):
    """最小二乘直线拟合。返回 (slope, intercept, r2) 或 None。

    r2 在 y 全为同值时无定义（总平方和为 0），此时返回 None 而不是 1.0 ——
    给一个漂亮的 1.0 会让人误以为拟合得很好。
    """
    n = len(xs)
    if n < 2:
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    if sxx == 0:
        return None
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x

    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    r2 = None if ss_tot == 0 else round(1 - ss_res / ss_tot, 4)
    return round(slope, 6), round(intercept, 6), r2


def _median(values):
    if not values:
        return None
    s = sorted(values)
    mid = len(s) // 2
    if len(s) % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2


def analyze_trend(intervals, area_mu=0.0):
    """对已排序的区间做描述性趋势分析。

    只描述已观测到的期次，不外推未来。返回体里带 caveats，
    调用方必须原样透传给前端展示。
    """
    caveats = [
        "每个区间是一次独立的变化检测，不是对同一现象的连续累计测量；"
        "相邻区间检出的变化未必属于同一种地物变化。",
        "日期由使用者填写，系统无法校验影像的真实拍摄时间。",
        "本分析只描述已观测期次，不外推未来期次，也不给出预测。",
    ]

    out = {
        "interval_count": len(intervals),
        "area_mu": area_mu or None,
        "intervals": intervals,
        "fit": None,
        "breakpoints": [],
        "summary": {},
        "caveats": caveats,
    }

    if not intervals:
        out["summary"] = {
            "note": "没有可用的区间（需要每期影像都有有效的起止日期）"
        }
        return out

    first_start = intervals[0]["start"]
    y0 = date.fromisoformat(first_start)

    # 累计口径：x 取区间中点距首期起点的天数，y 取截至该区间的累计变化
    cum_pct = 0.0
    cum_area = 0.0
    xs, ys_pct, ys_area = [], [], []
    for iv in intervals:
        cum_pct += iv["ratio_pct"]
        mid = date.fromisoformat(iv["start"]) + (
            date.fromisoformat(iv["end"]) - date.fromisoformat(iv["start"])
        ) / 2
        xs.append((mid - y0).days / 365.25)
        ys_pct.append(cum_pct)
        if area_mu:
            cum_area += iv["change_area_mu"] or 0.0
            ys_area.append(cum_area)

    use_area = bool(area_mu) and len(ys_area) == len(xs)
    ys = ys_area if use_area else ys_pct
    unit = "亩" if use_area else "%"

    fit = _linear_fit(xs, ys)
    if fit:
        slope, intercept, r2 = fit
        out["fit"] = {
            "slope": slope,
            "intercept": intercept,
            "r2": r2,
            "n": len(xs),
            "x_unit": "年（自首期起）",
            "y_unit": unit,
            "slope_meaning": f"平均每年累计变化 {slope} {unit}",
            "r2_note": (
                "y 值全部相同，R² 无定义" if r2 is None
                else ("期次很少时 R² 不稳定，请结合 n 判读" if len(xs) < 6 else "")
            ),
        }
    else:
        caveats.append("区间少于 2 个，无法做趋势拟合。")

    # 突变点：某区间速率明显高于其余区间的中位数。启发式，非统计检验。
    rates = [
        (iv["rate_area_per_year"] if use_area else iv["rate_pct_per_year"])
        for iv in intervals
    ]
    valid_rates = [r for r in rates if r is not None]
    if len(valid_rates) >= MIN_INTERVALS_FOR_BREAKPOINT:
        med = _median(valid_rates)
        if med and med > 0:
            for iv, rate in zip(intervals, rates):
                if rate is not None and rate > med * BREAKPOINT_RATIO:
                    out["breakpoints"].append({
                        "detection_id": iv["detection_id"],
                        "start": iv["start"],
                        "end": iv["end"],
                        "rate": rate,
                        "median_rate": round(med, 4),
                        "reason": f"该区间速率约为其余区间中位数的 {rate / med:.1f} 倍",
                    })
    if out["breakpoints"]:
        caveats.append(
            "「突变点」是启发式判定（速率超过其余区间中位数的 2 倍），"
            "不是统计检验，期次少时容易误报。"
        )

    last = intervals[-1]
    total_pct = round(cum_pct, 4)
    out["summary"] = {
        "first_start": first_start,
        "last_end": last["end"],
        "span_days": (date.fromisoformat(last["end"]) - y0).days,
        "total_change_ratio_pct": total_pct,
        "total_change_area_mu": round(cum_area, 4) if use_area else None,
        "mean_rate_pct_per_year": (
            round(total_pct / ((date.fromisoformat(last["end"]) - y0).days / 365.25), 4)
            if (date.fromisoformat(last["end"]) - y0).days > 0 else None
        ),
        "mean_rate_area_per_year": (
            round(cum_area / ((date.fromisoformat(last["end"]) - y0).days / 365.25), 4)
            if (use_area and (date.fromisoformat(last["end"]) - y0).days > 0) else None
        ),
    }
    return out
