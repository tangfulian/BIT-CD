# -*- coding: utf-8 -*-
"""把 index.html 里硬编码的高德 Key 迁移到不入库的 config.local.js。

安全性：脚本本身读取并搬运 Key，但**不向输出打印任何凭据内容**（只报告长度）。
"""
import pathlib, re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = pathlib.Path(r"d:\A汤福连的比赛与实验\BIT_CD")

idx = ROOT / 'frontend/index.html'
t = idx.read_text(encoding='utf-8')

m = re.search(r'(https://webapi\.amap\.com/maps\?[^\s"\']*?key=)([A-Za-z0-9]+)', t)
if not m:
    print("· 未找到硬编码的高德 Key，无需迁移")
    sys.exit(0)

key_len = len(m.group(2))
full_key = m.group(2)

# 1) 写入本地配置文件（不入库）
local = ROOT / 'frontend/js/config.local.js'
local.write_text(
    '// 本地密钥配置 —— 本文件已加入 .gitignore，不会提交到仓库。\n'
    '// 部署到新环境时：复制 config.local.example.js 为 config.local.js 并填入真实密钥。\n'
    'window.__APP_LOCAL_CONFIG__ = {\n'
    f'    amapKey: "{full_key}"\n'
    '};\n',
    encoding='utf-8',
)
print(f"✓ 已写入 frontend/js/config.local.js（密钥长度 {key_len} 字符，内容未打印）")

# 2) 生成可入库的模板
example = ROOT / 'frontend/js/config.local.example.js'
example.write_text(
    '// 本地密钥配置模板：复制本文件为 config.local.js 并填入真实值。\n'
    '// config.local.js 已加入 .gitignore，真实密钥不会进入版本库。\n'
    'window.__APP_LOCAL_CONFIG__ = {\n'
    '    // 高德开放平台 Web 端 JS API Key（建议同时配置域名白名单）\n'
    '    amapKey: "YOUR_AMAP_WEB_KEY"\n'
    '};\n',
    encoding='utf-8',
)
print("✓ 已生成 frontend/js/config.local.example.js（模板，可入库）")

# 3) 替换 index.html 中的硬编码 script 标签为动态加载
LOADER = (
    '    <!-- 高德地图：密钥由 js/config.local.js 提供（该文件不入库），缺失时自动降级 -->\n'
    '    <script src="js/config.local.js"></script>\n'
    '    <script>\n'
    '      (function () {\n'
    '        var key = (window.__APP_LOCAL_CONFIG__ && window.__APP_LOCAL_CONFIG__.amapKey) || "";\n'
    '        if (!key) {\n'
    '          console.warn("[配置] 未提供高德 Key，地图相关功能不可用。"\n'
    '            + "请复制 js/config.local.example.js 为 js/config.local.js 并填入 Key。");\n'
    '          return;\n'
    '        }\n'
    '        var s = document.createElement("script");\n'
    '        s.src = "https://webapi.amap.com/maps?v=2.0&key=" + encodeURIComponent(key);\n'
    '        s.async = true;\n'
    '        document.head.appendChild(s);\n'
    '      })();\n'
    '    </script>'
)

lines = t.split('\n')
done = False
for i, line in enumerate(lines):
    if 'webapi.amap.com/maps' in line and 'key=' in line:
        lines[i] = LOADER
        done = True
        break
if not done:
    print("⚠ 未能在 index.html 中定位该 script 标签")
    sys.exit(1)
idx.write_text('\n'.join(lines), encoding='utf-8')
print("✓ index.html 已改为运行时加载（不再含密钥）")

# 4) .gitignore 追加
gi = ROOT / '.gitignore'
g = gi.read_text(encoding='utf-8')
if 'config.local.js' not in g:
    gi.write_text(g.rstrip('\n') + '\n\n# 本地密钥配置（不入库）\nfrontend/js/config.local.js\n', encoding='utf-8')
    print("✓ .gitignore 已加入 frontend/js/config.local.js")
else:
    print("· .gitignore 已包含该规则")

# 5) 复核：确认仓库版本中已无密钥
after = idx.read_text(encoding='utf-8')
still = re.search(r'webapi\.amap\.com/maps\?[^\s"\']*?key=[A-Za-z0-9]{16,}', after)
print()
print("复核 index.html 是否仍含密钥：", "是 ⚠️" if still else "否 ✓")
