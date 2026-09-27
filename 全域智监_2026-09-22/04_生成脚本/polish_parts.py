# -*- coding: utf-8 -*-
"""Apply the consistency fixes reported by the workflow reviewers."""
import re, pathlib, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

PARTS = pathlib.Path(r"d:\A汤福连的比赛与实验\BIT_CD\.claude\tex_parts")

SUBSEC_DOT = (re.compile(r'\\subsection\{(\d)、'), r'\\subsection{\1.')
YEAR_DASH = (re.compile(r'(\d{4})-(\d{4})年'), r'\1—\2年')

EDITS = {
    'team.tex': [
        ('模型训练（ResNet50-BIT）', '模型训练（BIT，ResNet18 骨干）'),
        SUBSEC_DOT,
    ],
    'g1.tex': [
        ('搭配ResNet骨干网络', '搭配ResNet18骨干网络'),
        ('；ResNet骨干网络则负责', '；ResNet18骨干网络则负责'),
        ('以ResNet骨干提取', '以ResNet18骨干提取'),
    ],
    'g2.tex': [
        ('+快速更新', '+ 快速更新'),
    ],
    'g3.tex': [
        YEAR_DASH,
    ],
    'g4.tex': [SUBSEC_DOT],
    'g5.tex': [
        ('GF-2的四项关键参数', 'GF-2的关键技术参数'),
        ('四项参数彼此配合，共同支撑起', '上述参数与数据保障条件彼此配合，共同支撑起'),
        ('数据自主可控：从“用得上”到“用得住”', '数据自主可控：从“用得上”到“用得久”'),
        SUBSEC_DOT,
    ],
    'g7.tex': [SUBSEC_DOT],
    'g8.tex': [SUBSEC_DOT],
}

for name, rules in EDITS.items():
    p = PARTS / name
    t = p.read_text(encoding='utf-8')
    t0, hits = t, []
    for rule in rules:
        if isinstance(rule[0], str):
            pat, rep = re.compile(re.escape(rule[0])), rule[1]
        else:
            pat, rep = rule
        t, n = pat.subn(rep, t)
        if n:
            hits.append(f'{n}×{pat.pattern[:28]}')
    if t != t0:
        p.write_text(t, encoding='utf-8')
    print(f'{name:10s} {"OK  " + ", ".join(hits) if hits else "无需改动"}')
