# -*- coding: utf-8 -*-
"""Final validation for both deliverables (placeholder version + image version)."""
import re, sys, io, pathlib
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = pathlib.Path(r"d:\A汤福连的比赛与实验\BIT_CD")
FILES = ["项目计划书.tex", "项目计划书_带图版.tex"]

for name in FILES:
    p = BASE / name
    t = p.read_text(encoding='utf-8')
    body = '\n'.join(l for l in t.split('\n') if not l.lstrip().startswith('%'))
    cn = len(re.findall(r'[一-鿿]', t))

    print(f"\n{'='*56}\n{name}   ({p.stat().st_size/1024:.1f} KB | 中文字 {cn})\n{'='*56}")

    cb = Counter(re.findall(r'\\begin\{(\w+\*?)\}', body))
    ce = Counter(re.findall(r'\\end\{(\w+\*?)\}', body))
    bad_env = {k: (cb[k], ce[k]) for k in set(cb) | set(ce) if cb[k] != ce[k]}
    print("环境配对        :", "OK" if not bad_env else f"!!! {bad_env}")
    print("环境明细        :", dict(sorted(cb.items())))
    lb, rb = body.count('{'), body.count('}')
    print(f"花括号          : {lb} / {rb}", "OK" if lb == rb else "!!! 不匹配")
    print("裸特殊字符 %/_/#:", len(re.findall(r'(?<!\\)%', body)),
          len(re.findall(r'(?<!\\)_', body)), len(re.findall(r'(?<!\\)#', body)))
    print('ASCII 直引号 "  :', body.count('"'))
    print("章节 section    :", len(re.findall(r'\\section\{', body)),
          "| subsection:", len(re.findall(r'\\subsection\{', body)))
    print("caption         :", len(re.findall(r'\\caption\{', body)),
          "| label:", len(re.findall(r'\\label\{', body)))
    labs = re.findall(r'\\label\{([^}]+)\}', body)
    dup = [k for k, v in Counter(labs).items() if v > 1]
    print("label 重复      :", dup or "OK")

    if "带图版" in name:
        inc = re.findall(r'\\includegraphics\[[^\]]*\]\{([^}]+)\}', body)
        missing = [q for q in inc if not (BASE / q).exists()]
        print(f"图片引用        : {len(inc)} 处，缺失: {missing or '无'}")
    else:
        ph_fig = len(re.findall(r'【图片空位：', body))
        ph_tab = len(re.findall(r'【图片空位】', body))
        print(f"图片空位        : figure 内 {ph_fig} + 表格内 {ph_tab} = {ph_fig + ph_tab}")
