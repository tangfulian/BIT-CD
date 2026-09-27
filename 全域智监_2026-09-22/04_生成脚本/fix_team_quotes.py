# -*- coding: utf-8 -*-
"""Convert ASCII straight quotes to Chinese curly quotes in team.tex."""
import pathlib, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

Q, L, R = chr(34), chr(8220), chr(8221)
p = pathlib.Path(r"d:\A汤福连的比赛与实验\BIT_CD\.claude\tex_parts\team.tex")
t = p.read_text(encoding='utf-8')
n = t.count(Q)
out, opening = [], True
for ch in t:
    if ch == Q:
        out.append(L if opening else R)
        opening = not opening
    else:
        out.append(ch)
p.write_text(''.join(out), encoding='utf-8')
print(f"team.tex: 转换 {n} 个 ASCII 引号（{n // 2} 对）→ 中文弯引号")
