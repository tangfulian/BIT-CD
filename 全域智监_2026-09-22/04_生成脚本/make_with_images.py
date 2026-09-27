# -*- coding: utf-8 -*-
"""Generate 项目计划书_带图版.tex: replace every image placeholder with a real
\\includegraphics pointing at ./项目计划书_图片/ . The placeholder version
(项目计划书.tex) is left untouched.
"""
import re, pathlib, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = pathlib.Path(r"d:\A汤福连的比赛与实验\BIT_CD")
SRC = BASE / "项目计划书.tex"
OUT = BASE / "项目计划书_带图版.tex"
IMG_REL = "项目计划书图片"

t = SRC.read_text(encoding='utf-8')

# 1) figure 环境内的占位
pat_fig = re.compile(
    r'\\fbox\{\\parbox\[c\]\[4\.5cm\]\[c\]\{0\.8\\textwidth\}\{\\centering 【图片空位：([^】]+)】[^}]*\}\}'
)
# 2) 表格单元格内的占位
pat_tab = re.compile(
    r'\\fbox\{\\parbox\[c\]\[[0-9.]+cm\]\[c\]\{[0-9.]+cm\}\{\\centering 【图片空位】\\scriptsize\s*([^}]+?)\}\}'
)

# 逐行处理，注释行（% 开头）原样保留，避免误替换文件头的示例代码
lines, n_fig, n_tab = [], 0, 0
for line in t.split('\n'):
    if line.lstrip().startswith('%'):
        lines.append(line)
        continue
    line, a = pat_fig.subn(
        lambda m: r'\includegraphics[width=0.8\textwidth]{' + IMG_REL + '/' + m.group(1).strip() + '}', line)
    line, b = pat_tab.subn(
        lambda m: r'\includegraphics[width=2.4cm]{' + IMG_REL + '/' + m.group(1).strip() + '}', line)
    n_fig += a; n_tab += b
    lines.append(line)
t = '\n'.join(lines)

# 3) 头部说明替换为带图版说明
header_old = re.search(r'%  图片说明：.*?% =+\n', t, re.S)
if header_old:
    new_header = (
        "%  本文件为【带图版】：正文中原图片位置已替换为真实图片引用，\n"
        "%  图片位于 ./" + IMG_REL + "/ 目录，可直接 xelatex 编译出带图成品。\n"
        "%  （保留图片空位的版本见 项目计划书.tex）\n"
        "% ============================================================\n"
    )
    t = t.replace(header_old.group(0), new_header)

OUT.write_text(t, encoding='utf-8')

left = len(re.findall(r'图片空位', t))
print(f"输出: {OUT.name}")
print(f"  figure 内替换: {n_fig} 处")
print(f"  表格内替换:   {n_tab} 处")
print(f"  合计替换:     {n_fig + n_tab} 处")
print(f"  残留占位:     {left} 处" + ("（应为说明文字中的提法）" if left else ""))
print(f"  大小: {OUT.stat().st_size/1024:.1f} KB")
