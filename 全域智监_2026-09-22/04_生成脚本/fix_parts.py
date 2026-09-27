# -*- coding: utf-8 -*-
"""Batch-fix common issues found by the consistency review:
   1) ASCII straight quotes -> Chinese curly quotes (paired)
   2) remove stray space between number and Chinese unit / \%
   3) strip hand-written 图N/表N prefix inside \caption (LaTeX auto-numbers)
   4) strip hand-written 图N/表N inside image-placeholder text
"""
import re, pathlib, shutil, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

PARTS = pathlib.Path(r"d:\A汤福连的比赛与实验\BIT_CD\.claude\tex_parts")
BK = pathlib.Path(r"d:\A汤福连的比赛与实验\BIT_CD\.claude\tex_parts_backup")
BK.mkdir(exist_ok=True)


def fix_quotes(text):
    out, opening = [], True
    for ch in text:
        if ch == '"':
            out.append('“' if opening else '”')
            opening = not opening
        else:
            out.append(ch)
    return ''.join(out)


report = []
for f in sorted(PARTS.glob("*.tex")):
    src = f.read_text(encoding='utf-8')
    t0 = src
    shutil.copy(f, BK / f.name)

    n_dq = t0.count('"')
    t = fix_quotes(t0)

    t, n_unit = re.subn(r'([0-9])\s+([秒张万亿个年份月日农万户元])', r'\1\2', t)
    t, n_pct = re.subn(r'([0-9])\s+(\\%)', r'\1\2', t)

    t, n_cap = re.subn(r'\\caption\{(?:图|表)\s*[0-9]+\s*', r'\\caption{', t)
    t, n_ph = re.subn(r'(】)\s*(?:图|表)\s*[0-9]+\s*', r'\1', t)

    if t != t0:
        f.write_text(t, encoding='utf-8')
    report.append((f.name, n_dq // 2, n_unit + n_pct, n_cap, n_ph))

print(f"{'file':12s} {'引号对':>6s} {'数字空格':>8s} {'caption去号':>11s} {'占位去号':>9s}")
for name, q, u, c, p in report:
    print(f"{name:12s} {q:6d} {u:8d} {c:11d} {p:9d}")
print(f"\n备份目录: {BK}")
