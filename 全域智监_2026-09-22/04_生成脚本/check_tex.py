# -*- coding: utf-8 -*-
"""Validate the assembled LaTeX file for structural integrity."""
import re, sys, io
from collections import Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

path = r"d:\A汤福连的比赛与实验\BIT_CD\项目计划书.tex"
t = open(path, encoding='utf-8').read()
body = '\n'.join(l for l in t.split('\n') if not l.strip().startswith('%'))

print('=== 1. 环境配对 ===')
cb = Counter(re.findall(r'\\begin\{(\w+\*?)\}', body))
ce = Counter(re.findall(r'\\end\{(\w+\*?)\}', body))
diff = {k: (cb[k], ce[k]) for k in set(cb) | set(ce) if cb[k] != ce[k]}
print('  不配对:', diff if diff else 'OK 全部配对')
print('  环境统计:', dict(sorted(cb.items())))

print('=== 2. 花括号 ===')
lb, rb = body.count('{'), body.count('}')
print(f'  左 {lb} / 右 {rb}', 'OK' if lb == rb else '!!! 不匹配')

print('=== 3. 未转义特殊字符 ===')
print('  裸 % :', len(re.findall(r'(?<!\\)%', body)))
print('  裸 _ :', len(re.findall(r'(?<!\\)_', body)))
print('  裸 # :', len(re.findall(r'(?<!\\)#', body)))

print('=== 4. 图片空位 ===')
ph = [p.strip() for p in re.findall(r'【图片空位：([^】]+)】', t)]
print('  空位数:', len(ph), '| 唯一文件数:', len(set(ph)))
print('  文件:', sorted(set(ph)))

print('=== 5. 章节 / 引用 ===')
print('  section   :', len(re.findall(r'\\section\{', body)))
print('  subsection:', len(re.findall(r'\\subsection\{', body)))
cites = set()
for m in re.findall(r'\\cite\{([^}]+)\}', body):
    cites.update(x.strip() for x in m.split(','))
bibs = set(re.findall(r'\\bibitem\{(\w+)\}', body))
print('  cite 键:', sorted(cites))
print('  文献键:', sorted(bibs))
print('  未定义引用:', sorted(cites - bibs) or 'OK')

print('=== 6. label / caption ===')
labs = re.findall(r'\\label\{([^}]+)\}', body)
dup = [k for k, v in Counter(labs).items() if v > 1]
caps = re.findall(r'\\caption\{([^}]{0,40})', body)
print('  label 数:', len(labs), '| 重复:', dup or 'OK')
print('  caption 数:', len(caps))
print('  caption 手写图号残留:', [c for c in caps if re.match(r'^\s*(图|表)\s*\d', c)] or 'OK 无残留')

print('=== 7. 章节标题清单 ===')
for s in re.findall(r'\\section\{([^}]*)\}', body):
    print('  ', s)
