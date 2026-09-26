# -*- coding: utf-8 -*-
"""第二批修复：前端存储型 XSS 转义、.dockerignore 补齐、检查其他未转义点"""
import pathlib, sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = pathlib.Path(r"d:\A汤福连的比赛与实验\BIT_CD")

# ---------- 1) .dockerignore 补 .env.production ----------
di = ROOT / '.dockerignore'
t = di.read_text(encoding='utf-8')
if '.env.production' not in t:
    t = t.replace('.env\n', '.env\n.env.production\n.env.*.local\n', 1)
    di.write_text(t, encoding='utf-8')
    print("✓ .dockerignore: 已补 .env.production（此前会被 COPY . . 打进生产镜像）")
else:
    print("· .dockerignore 已包含 .env.production")

# ---------- 2) history.js 的用户可控字段转义 ----------
hj = ROOT / 'frontend/js/history.js'
t = hj.read_text(encoding='utf-8')
print(f"\nhistory.js 是否可用 Utils：{'是' if 'Utils.' in t else '否 —— 需确认全局可用性'}")

SUBS = [
    ("var displayModel = item.model || t('unknown');",
     "var displayModel = Utils.escapeHtml(item.model) || t('unknown');"),
    ("var displayLocation = item.location ? ' · ' + item.location : \"\";",
     "var displayLocation = item.location ? ' · ' + Utils.escapeHtml(item.location) : \"\";"),
    ("(item.model || '-')", "Utils.escapeHtml(item.model || '-')"),
    ("(item.change_type || '-')", "Utils.escapeHtml(item.change_type || '-')"),
    ("(item.location || '-')", "Utils.escapeHtml(item.location || '-')"),
]
total = 0
for a, b in SUBS:
    n = t.count(a)
    if n:
        t = t.replace(a, b)
        total += n
        print(f"  {n} 处 → {b[:64]}")
hj.write_text(t, encoding='utf-8')
print(f"✓ history.js: 共转义 {total} 处")

# ---------- 3) 扫描其他文件里"用户可控字段直接进 innerHTML"的同类问题 ----------
print("\n=== 其他文件中的同类风险点扫描 ===")
USER_FIELDS = ['item.location', 'item.change_type', 'item.model', 'data.location',
               'data.change_type', 'chatHistory', 'user_input', 'result.analysis']
for f in sorted((ROOT / 'frontend/js').glob('*.js')):
    src = f.read_text(encoding='utf-8')
    for i, line in enumerate(src.split('\n'), 1):
        if 'innerHTML' not in line:
            continue
        for fld in USER_FIELDS:
            if fld in line and 'escapeHtml' not in line:
                print(f"  ⚠ {f.name}:{i}  {line.strip()[:96]}")
                break
