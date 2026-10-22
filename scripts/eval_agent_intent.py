"""Agent 意图解析准确率评测。

## 测什么

给定一句自然语言指令，看 Agent **首轮选择调用哪个工具**是否与预期一致。

## 为什么只测首轮、且不真的执行工具

三层理由，缺一不可：

1. **意图解析就是「选对工具」这一步。** 后续的参数填写、结果汇报是另外的能力，
   混在一起测就分不清是哪一环出错。
2. **不执行工具 = 无副作用。** `run_detection` 会往用户的检测历史里写记录，
   `assess_disaster` 会读概率图算一遍。评测不该改动数据。
3. **省调用。** 每次评测只花一次模型往返。整套用例几十条，成本可控。

## 用法

    python scripts/eval_agent_intent.py                # 跑全部用例
    python scripts/eval_agent_intent.py -v             # 打印每条的选择与理由
    python scripts/eval_agent_intent.py --limit 10     # 只跑前 10 条（调试用）
    python scripts/eval_agent_intent.py --case intent_models_01

需要 `.env` 里配好 `LLM_API_KEY`。
"""

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from backend.app.core import llm_budget                    # noqa: E402
from backend.app.services.tool_agent_service import (      # noqa: E402
    SYSTEM_PROMPT,
    _attachment_block,
    _post_chat,
    _tool_schemas,
)

CASES_PATH = pathlib.Path(__file__).resolve().parent / "agent_intent_cases.json"


def first_tool(instruction: str, file_paths: list[str]) -> tuple[str | None, str]:
    """跑一轮，返回 (首轮选的工具名 或 None, 模型的文字输出)。

    刻意不复用 execute_tool_agent —— 那个会真的执行工具。这里只问到模型
    「你打算调哪个」为止。
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT + _attachment_block(file_paths)},
        {"role": "user", "content": instruction},
    ]
    message = _post_chat(messages, _tool_schemas(file_paths))
    calls = message.get("tool_calls") or []
    if not calls:
        return None, (message.get("content") or "").strip()
    return (calls[0].get("function") or {}).get("name") or "", (message.get("content") or "").strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true", help="逐条打印选择结果")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 条")
    ap.add_argument("--case", type=str, default="", help="只跑指定 id")
    ap.add_argument("--json", type=str, default="", help="把结果写到指定文件")
    ap.add_argument("--cases", type=str, default="",
                    help="用例文件，默认 agent_intent_cases.json。"
                         "调提示词后请换用 agent_intent_cases_heldout.json 验证 —— "
                         "在拿来发现问题的集合上重跑，数字会虚高。")
    ap.add_argument("--repeat", type=int, default=1,
                    help="每条重复跑 N 次。工具通道 temperature=0.2 不是 0，"
                         "实测同一用例连跑 6 次会出现 5:1 的分裂 —— "
                         "单次跑出来的数字带几点噪声，想当真就设 3。")
    args = ap.parse_args()

    cases_path = pathlib.Path(args.cases) if args.cases else CASES_PATH
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    print(f"用例文件：{cases_path.name}")
    if args.case:
        cases = [c for c in cases if c["id"] == args.case]
    elif args.limit:
        cases = cases[: args.limit]
    if not cases:
        print("没有匹配的用例")
        return 1

    print(f"用例数：{len(cases)}    日预算剩余：{llm_budget.usage()['remaining']}\n")

    passed, failed, errored = [], [], []
    unstable = []
    for i, c in enumerate(cases, 1):
        expect = c["expect_first"]          # list：任一命中即算对；[] 表示不该调工具
        picks, texts = [], []
        try:
            for _ in range(max(1, args.repeat)):
                tool_name, reply = first_tool(c["instruction"], c.get("file_paths") or [])
                picks.append(tool_name)
                texts.append(reply)
        except Exception as exc:
            errored.append((c, f"{type(exc).__name__}: {exc}"))
            print(f"  [{i:>3}/{len(cases)}] {c['id']:<28} 调用失败 {type(exc).__name__}")
            continue

        # 归一化「没调工具」：first_tool 在无 tool_calls 时返回 None，但工具名为空
        # 时也可能返回 ""。两者都当「没调工具」这一个状态看。
        # 早先这里直接写 `got in expect`，而 Python 里 `None in []` 是 False ——
        # 于是所有「不该调工具」的用例即便表现完全正确也被判错，把准确率
        # 从 ~78% 压成了 56%。**判据写反了比没有判据更危险**，因为它会给出
        # 一个看起来精确的错误数字。
        def hit(g):
            return ((g or None) is None) if not expect else ((g or None) in expect)

        oks = [hit(g) for g in picks]
        got = picks[0]
        text = texts[0]
        # 重复采样时，只要不是每次都过就算没通过 —— 分裂本身就是要暴露的信息
        ok = all(oks)
        splintered = len(set(oks)) > 1
        if splintered:
            unstable.append((c, picks))
        (passed if ok else failed).append((c, got, text))

        if splintered:
            dist = {}
            for g in picks:
                k = g or "(不调工具)"
                dist[k] = dist.get(k, 0) + 1
            detail = "  ".join(f"{k}×{v}" for k, v in dist.items())
            print(f"  [{i:>3}/{len(cases)}] 波 {c['id']:<28} {sum(oks)}/{len(oks)}   {detail}")
        elif not ok or args.verbose:
            print(f"  [{i:>3}/{len(cases)}] {'OK ' if ok else '错 '} {c['id']:<28} "
                  f"选了 {got or '(未调工具)'}  期望 {expect or '(不调工具)'}")
            if not ok and text:
                print(f"         模型说：{text[:90]}")

    total = len(passed) + len(failed)
    print("\n" + "=" * 60)
    if total:
        rate = len(passed) / total * 100
        print(f"意图解析准确率：{len(passed)}/{total} = {rate:.1f}%"
              + (f"   （每条重复 {args.repeat} 次，全对才算通过）" if args.repeat > 1 else ""))
    if unstable:
        print(f"行为不稳定：{len(unstable)} 条（不同轮次结果不一致，本身就是信息）")
        for c, picks in unstable:
            dist = {}
            for g in picks:
                dist[g or "(不调工具)"] = dist.get(g or "(不调工具)", 0) + 1
            print(f"  {c['id']:<28} " + "  ".join(f"{k}×{v}" for k, v in dist.items()))
    if errored:
        print(f"调用失败：{len(errored)} 条（不计入准确率）")
    print(f"日预算用量：{llm_budget.usage()}")

    if failed and not args.verbose:
        print("\n未通过的用例（加 -v 看完整输出）：")
        for c, got, _ in failed:
            print(f"  {c['id']:<28} 选了 {got or '(未调工具)'}  期望 {c['expect_first'] or '(不调工具)'}")

    if args.json:
        pathlib.Path(args.json).write_text(json.dumps({
            "rate": round(len(passed) / total * 100, 2) if total else None,
            "passed": len(passed), "failed": len(failed), "errored": len(errored),
            "failures": [{"id": c["id"], "instruction": c["instruction"],
                          "expected": c["expect_first"], "got": got}
                         for c, got, _ in failed],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n结果已写入 {args.json}")

    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
