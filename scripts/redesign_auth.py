# -*- coding: utf-8 -*-
"""重做登录/注册界面：土壤剖面式左右分栏，配色取自黑土地物性。

设计要点（对照 frontend-design skill 点名的模板化特征逐项规避）：
  · 不用白色圆角卡片 + 柔和阴影（SaaS-card kit）
  · 不用「近黑 + 单一酸绿」的科技暗色套路 → 深褐底 + 秸秆金主强调
  · 删掉副标题的中圆点 meta 写法
  · 输入框左侧 2px 竖线形似田埂边界，聚焦时由土褐转作物绿（唯一的记忆点）
所有表单 ID 原样保留，不影响既有 JS 绑定。
"""
import pathlib, re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = pathlib.Path(r"d:\A汤福连的比赛与实验\BIT_CD")

NEW_CSS = '''/* ============================ 登录 / 注册 ============================
   配色取自黑土地物性：母质层/耕作层/土粒边界/秸秆/作物，而非通用的绿色科技风。
   ==================================================================== */
.auth-container {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
    background: #1E1710;
    /* 极淡的等距横线，暗示耕层剖面 */
    background-image: repeating-linear-gradient(0deg, rgba(201,162,77,0.05) 0 1px, transparent 1px 46px);
    position: relative;
    z-index: 1000;
}

.auth-overlay-close {
    position: absolute;
    top: 22px; right: 26px;
    width: 34px; height: 34px;
    display: flex; align-items: center; justify-content: center;
    background: transparent;
    border: 1px solid #453626;
    border-radius: 3px;
    color: #948A7C;
    font-size: 20px; line-height: 1;
    cursor: pointer;
    transition: color .15s, border-color .15s;
}
.auth-overlay-close:hover { color: #E9E5DC; border-color: #C9A24D; }

/* 主面板：一块完整的土壤板，左右分区用细线切开，不做卡片堆 */
.auth-card {
    display: grid;
    grid-template-columns: 1fr 1fr;
    width: min(880px, 100%);
    background: #2C2318;
    border: 1px solid #453626;
    border-radius: 4px;
    overflow: hidden;
}

/* ---- 左侧：系统标识 ---- */
.auth-logo {
    padding: 48px 40px;
    display: flex;
    flex-direction: column;
    justify-content: center;
    background:
        repeating-linear-gradient(90deg, rgba(201,162,77,0.06) 0 1px, transparent 1px 34px),
        #241C14;
    border-right: 1px solid #453626;
}
.auth-logo img {
    width: 56px; height: 56px;
    margin: 0 0 20px;
    display: block;
}
.auth-logo h1 {
    font-size: 23px;
    font-weight: 600;
    line-height: 1.45;
    letter-spacing: .01em;
    color: #E9E5DC;
    margin: 0 0 12px;
}
.auth-logo p {
    font-size: 13px;
    line-height: 1.75;
    color: #948A7C;
    margin: 0;
    max-width: 22em;
}

/* ---- 右侧：表单 ---- */
.auth-form { padding: 44px 40px; }
.auth-form.hidden { display: none; }
.auth-form .form-group { margin-bottom: 18px; }

.auth-form label {
    display: block;
    font-size: 12px;
    font-weight: 500;
    letter-spacing: .04em;
    color: #948A7C;
    margin-bottom: 7px;
}

/* 输入框：左缘那条 2px 竖线是"田埂"，聚焦时转为作物绿 */
.auth-form input {
    width: 100%;
    min-height: 44px;
    padding: 11px 13px;
    background: #1E1710;
    border: 1px solid #453626;
    border-left: 2px solid #5A4630;
    border-radius: 3px;
    color: #E9E5DC;
    font-size: 15px;
    font-family: inherit;
    transition: border-color .15s, background .15s;
}
.auth-form input::placeholder { color: #6B6155; }
.auth-form input:hover { border-left-color: #7A5F3E; }
.auth-form input:focus,
.auth-form input:focus-visible {
    outline: none;
    border-color: #453626;
    border-left-color: #7BA05B;
    background: #221A12;
}

/* 验证码 */
.captcha-group { margin-bottom: 22px; }
.captcha-row { display: flex; gap: 10px; align-items: stretch; }
.captcha-img {
    width: 116px; height: 44px;
    flex-shrink: 0;
    border: 1px solid #453626;
    border-left: 2px solid #5A4630;
    border-radius: 3px;
    background: #E9E5DC;
    cursor: pointer;
    transition: border-color .15s;
}
.captcha-img:hover { border-left-color: #C9A24D; }
.captcha-input { flex: 1; min-width: 0; }
.captcha-refresh {
    width: 44px; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
    background: transparent;
    border: 1px solid #453626;
    border-radius: 3px;
    color: #948A7C;
    cursor: pointer;
    padding: 0;
    transition: color .15s, border-color .15s;
}
.captcha-refresh:hover { color: #C9A24D; border-color: #C9A24D; }

/* 主按钮用秸秆金：从黑土地里长出来的颜色，避开通用的绿色主按钮 */
.auth-form .btn-primary {
    width: 100%;
    min-height: 46px;
    margin-top: 6px;
    background: #C9A24D;
    color: #1E1710;
    border: none;
    border-radius: 3px;
    font-size: 15px;
    font-weight: 600;
    font-family: inherit;
    letter-spacing: .02em;
    cursor: pointer;
    box-shadow: none;
    transition: background .15s;
}
.auth-form .btn-primary::after { display: none; }
.auth-form .btn-primary:hover { background: #D8B45F; }
.auth-form .btn-primary:active { background: #B8933F; }
.auth-form .btn-primary:disabled { background: #5A4A2E; color: #948A7C; cursor: not-allowed; }

.auth-form .btn-secondary {
    width: 100%;
    min-height: 42px;
    margin-top: 10px;
    background: transparent;
    color: #948A7C;
    border: 1px solid #453626;
    border-radius: 3px;
    font-size: 13.5px;
    font-family: inherit;
    cursor: pointer;
    transition: color .15s, border-color .15s;
}
.auth-form .btn-secondary:hover { color: #E9E5DC; border-color: #7A5F3E; }

/* 窄屏：左侧标识折到顶部 */
@media (max-width: 760px) {
    .auth-card { grid-template-columns: 1fr; }
    .auth-logo {
        padding: 24px;
        flex-direction: row;
        align-items: center;
        gap: 14px;
        border-right: none;
        border-bottom: 1px solid #453626;
    }
    .auth-logo img { width: 40px; height: 40px; margin: 0; }
    .auth-logo h1 { font-size: 17px; margin: 0 0 2px; }
    .auth-logo p { font-size: 12px; max-width: none; }
    .auth-form { padding: 26px 24px; }
}
'''

css = ROOT / 'frontend/css/styles.css'
t = css.read_text(encoding='utf-8')

start = t.index('.auth-container {')
end_marker = '.captcha-refresh:hover {'
end = t.index(end_marker)
end = t.index('}', end) + 1          # 收在 .captcha-refresh:hover 的右括号

old_block = t[start:end]
t2 = t[:start] + NEW_CSS.rstrip() + t[end:]
css.write_text(t2, encoding='utf-8')
print(f"✓ CSS: 替换 auth 样式块（{old_block.count(chr(10))} 行 → {NEW_CSS.count(chr(10))} 行）")

# ---------- HTML：副标题改成用途说明，去掉中圆点 meta ----------
idx = ROOT / 'frontend/index.html'
h = idx.read_text(encoding='utf-8')
old_p = '<p data-i18n="auth.subtitle">BLACKLAND CD · 黑土地保护智能平台</p>'
new_p = '<p data-i18n="auth.subtitle">上传两期卫星影像，自动识别耕地变化位置与面积</p>'
if old_p in h:
    h = h.replace(old_p, new_p)
    idx.write_text(h, encoding='utf-8')
    print("✓ HTML: 副标题改为用途说明（去掉中圆点 meta 写法）")
else:
    print("· HTML: 副标题未匹配（i18n 可能已覆盖），跳过")

# ---------- 同步 i18n 词表 ----------
for loc in ('zh-CN.js', 'en.js'):
    f = ROOT / 'frontend/js/locales' / loc
    if not f.exists():
        continue
    s = f.read_text(encoding='utf-8')
    if loc == 'zh-CN.js':
        old, new = '"auth.subtitle": "BLACKLAND CD · 黑土地保护智能平台"', '"auth.subtitle": "上传两期卫星影像，自动识别耕地变化位置与面积"'
    else:
        old, new = '"auth.subtitle": "BLACKLAND CD · Black Land Protection Platform"', '"auth.subtitle": "Upload two satellite images to locate and measure cropland change"'
    if old in s:
        f.write_text(s.replace(old, new), encoding='utf-8')
        print(f"✓ i18n {loc}: 副标题已同步")
    else:
        print(f"· i18n {loc}: 未匹配到副标题键")
