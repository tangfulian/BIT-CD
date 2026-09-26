# -*- coding: utf-8 -*-
"""把 async 端点里的同步重活（模型推理 / 第三方 SDK 调用）移入线程池。

背景：detect / compare / evaluate / ai 等端点声明为 async def，但内部同步调用
torch 前向（CPU 上数百毫秒到数秒）与 dashscope SDK（网络往返数秒）。单 worker 部署下，
一次检测期间事件循环被占满，所有请求（含前端轮询的状态页）全部卡住。
"""
import pathlib, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = pathlib.Path(r"d:\A汤福连的比赛与实验\BIT_CD")


def patch(rel, pairs, add_import_after):
    p = ROOT / rel
    t = p.read_text(encoding='utf-8')
    if 'run_in_threadpool' not in t:
        t = t.replace(add_import_after,
                      add_import_after + '\nfrom starlette.concurrency import run_in_threadpool', 1)
        print(f"✓ {rel}: 已加 import")
    n_total = 0
    for a, b in pairs:
        n = t.count(a)
        if n != 1:
            print(f"  ⚠ 匹配 {n} 次（预期 1），跳过：{a.splitlines()[0][:60]}")
            continue
        t = t.replace(a, b)
        n_total += 1
    p.write_text(t, encoding='utf-8')
    print(f"✓ {rel}: 包装 {n_total} 处同步调用")


print("=== detect.py ===")
patch(
    'backend/app/routers/detect.py',
    [
        # detect 端点
        ("""    score_map, change_mask, heatmap, fusion, stats = detect_change(
        img_t1, img_t2, threshold, model, unique_id
    )""",
         """    # 模型推理是同步 CPU 重活：放进线程池，避免阻塞事件循环
    score_map, change_mask, heatmap, fusion, stats = await run_in_threadpool(
        detect_change, img_t1, img_t2, threshold, model, unique_id
    )"""),
        # 推荐阈值
        ("""    recommended = recommend_threshold_from_images(img_t1, img_t2)""",
         """    recommended = await run_in_threadpool(recommend_threshold_from_images, img_t1, img_t2)"""),
        # 多模型对比
        ("""        _, change_mask, heatmap, fusion, stats = detect_change(
            img_t1, img_t2, threshold, model_name, model_uid
        )""",
         """        _, change_mask, heatmap, fusion, stats = await run_in_threadpool(
            detect_change, img_t1, img_t2, threshold, model_name, model_uid
        )"""),
        # 配准检查
        ("""    result = check_registration(img_t1, img_t2)""",
         """    result = await run_in_threadpool(check_registration, img_t1, img_t2)"""),
        # 模型评估
        ("""    results = evaluate_models(img_t1, img_t2, img_label, model_list, threshold)""",
         """    results = await run_in_threadpool(evaluate_models, img_t1, img_t2, img_label, model_list, threshold)"""),
        # 阈值扫描
        ("""    results = evaluate_scan(img_t1, img_t2, img_label, model_list, thresholds)""",
         """    results = await run_in_threadpool(evaluate_scan, img_t1, img_t2, img_label, model_list, thresholds)"""),
    ],
    add_import_after='from fastapi.responses import JSONResponse',
)

print()
print("=== ai.py ===")
patch(
    'backend/app/routers/ai.py',
    [
        ("""        reply = chat(chat_req.user_input, chat_req.history, SYSTEM_CHAT_PROMPT)""",
         """        # dashscope SDK 是同步阻塞调用（网络往返数秒），移入线程池
        reply = await run_in_threadpool(chat, chat_req.user_input, chat_req.history, SYSTEM_CHAT_PROMPT)"""),
        ("""        analysis = chat(user_input, [], SYSTEM_ANALYSIS_PROMPT)""",
         """        analysis = await run_in_threadpool(chat, user_input, [], SYSTEM_ANALYSIS_PROMPT)"""),
        ("""        result = classify_change(
            change_ratio=classify_req.change_ratio,
            change_pixel=classify_req.change_pixel,
            total_pixel=classify_req.total_pixel,
            threshold=classify_req.threshold,
            location=classify_req.location,
            land_type=classify_req.land_type,
            crop_type=classify_req.crop_type,
            t1_time=classify_req.t1_time,
            t2_time=classify_req.t2_time,
        )""",
         """        result = await run_in_threadpool(
            lambda: classify_change(
                change_ratio=classify_req.change_ratio,
                change_pixel=classify_req.change_pixel,
                total_pixel=classify_req.total_pixel,
                threshold=classify_req.threshold,
                location=classify_req.location,
                land_type=classify_req.land_type,
                crop_type=classify_req.crop_type,
                t1_time=classify_req.t1_time,
                t2_time=classify_req.t2_time,
            )
        )"""),
    ],
    add_import_after='from fastapi import APIRouter, Depends, HTTPException, Request',
)
