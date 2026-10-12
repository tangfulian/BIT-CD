"""Agent 工具通道的**端到端**闭环：真发自然语言，看意图→执行→回灌→汇报整条链。

三个测试的分工（别重复跑）：
    eval_agent_intent.py   只问模型「你打算调哪个」，不执行      —— 零副作用、测提示词
    agent_tools_test.py    直调工具处理器，绕开模型             —— 零 LLM 调用、测处理器
    本文件                 走完整闭环，含真实模型往返           —— 花 LLM 调用、测编排层

**会消耗 LLM 调用**：每条指令 1~3 次往返。默认 3 条，日常跑够用；
想多测就改 CASES。

三条用例覆盖三种情形，取舍的理由：
  - 「能力询问」测的是系统提示词第 8 条（这类问题没有对应接口，不该调工具）。
    这一条最容易退化 —— 模型一旦开始「先查一下再说」，它会去调 list_models
    然后答非所问。
  - 另外两条是常规查询，顺带验第 7 条（参数齐了就直接调，不要为了确认多查一次）。
    **轮数是重要信号**：本该 1 轮的走了 2 轮，说明提示词在退化。

不校验工具名以外的内容（回复措辞交给模型自由发挥），只校验：
结构正确、success 为真、调了该调的、没调不该调的。

用法：
    python api.py                    # 另开一个终端
    python scripts/agent_e2e_test.py
"""

import json
import os
import pathlib
import sys

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from backend.app.core.security import create_access_token    # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = os.getenv("BITCD_BASE", "http://127.0.0.1:8000")
H = {"Authorization": "Bearer " + create_access_token({"sub": "admin", "role": "admin"})}

# (标题, 指令, 期望调用的工具；空表示「不该调任何工具」)
CASES = [
    ("能力询问 —— 提示词第 8 条", "你能做什么？", []),
    ("模型清单", "现在有哪些变化检测模型可以用？", ["list_models"]),
    ("历史查询", "我最近做过哪些检测？", ["list_detections"]),
]

OK, BAD = 0, []


def check(label, cond, detail=""):
    global OK
    if cond:
        OK += 1
        print(f"  PASS  {label}")
    else:
        BAD.append(label)
        print(f"  FAIL  {label}   {detail}")


def main():
    for title, instruction, expect in CASES:
        print(f"\n=== {title} ===")
        print(f"  指令: {instruction}")
        try:
            r = requests.post(f"{BASE}/agent/execute-tools", headers=H, timeout=180,
                              data={"instruction": instruction})
        except Exception as e:
            check(f"{title}：请求发出", False, f"{type(e).__name__}: {e}")
            continue

        check("HTTP 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
        if r.status_code != 200:
            continue

        body = r.json()
        check("code == 200", body.get("code") == 200, str(body)[:200])
        check("success 为真", body.get("success") is True, f"errors={body.get('errors')}")

        used = [t.get("tool") or t.get("name") for t in (body.get("tool_trace") or [])]
        print(f"  调用工具: {used}   轮数: {body.get('total_steps')}   "
              f"耗时: {body.get('duration_seconds')}s")
        print(f"  最终回复: {str(body.get('final_result'))[:150]}")

        check("最终回复非空", bool(str(body.get("final_result") or "").strip()),
              str(body)[:200])
        if expect:
            check(f"调用了 {expect}", all(t in used for t in expect), f"实际 {used}")
            check("没有多余轮次（第 7 条：能直接答就别多查一次）",
                  len(used) <= len(expect) + 1, f"实际 {used}")
        else:
            check("没有调用任何工具（第 8 条）", used == [], f"实际 {used}")

    print(f"\n{'=' * 52}\n{OK} passed, {len(BAD)} failed")
    for b in BAD:
        print("  -", b)
    return 1 if BAD else 0


if __name__ == "__main__":
    sys.exit(main())
