"""Comprehensive API test suite for BIT_CD system."""
import requests, json, io, os, pathlib, sys
from PIL import Image
import numpy as np

BASE = 'http://127.0.0.1:8000'
pass_cnt = 0
fail_cnt = 0
bugs = []

def test(name, method, url, exp=None, **kw):
    global pass_cnt, fail_cnt
    try:
        r = requests.request(method, f'{BASE}{url}', timeout=60, **kw)
        ok = exp is None or r.status_code == exp
        if ok:
            pass_cnt += 1
        else:
            fail_cnt += 1
            try:
                d = str(r.json())[:200]
            except Exception:
                d = r.text[:200]
            print(f'  [FAIL({r.status_code})] {name} -> {d}')
            bugs.append(name)
        return r
    except Exception as e:
        fail_cnt += 1
        print(f'  [ERR] {name} -> {e}')
        bugs.append(name)
        return None

# ===== Setup =====
# 直接在本地签发令牌，不再走 /login。
#
# 原因：/login 现在强制校验验证码，而 verify_captcha 拿不到 captcha_id 时直接返回
# False（见 core/captcha.py），脚本没法自动识别图片，这条路走不通。
# 原先写的是明文 admin123 硬 POST /login —— 既过不了验证码，那个口令也早就不是
# 真实密码了，于是脚本每次都在这里 `Cannot login` 然后 sys.exit(1)，下面整套检查
# 等于从来没跑过。
#
# 这么改只对得起「本机冒烟」这个前提：脚本本来就只打 127.0.0.1，导入的是同一份
# config（它按绝对路径加载 .env，所以拿到的是同一个 SECRET_KEY），不改动被测服务
# 的任何鉴权逻辑。
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from backend.app.core.security import create_access_token  # noqa: E402

ADMIN_USER = os.getenv('SMOKE_ADMIN_USER', 'admin')
tok = create_access_token({'sub': ADMIN_USER, 'role': 'admin'})
H = {'Authorization': f'Bearer {tok}'}
print(f'已为 {ADMIN_USER} 本地签发令牌（绕过验证码，仅限本机冒烟）')

np.random.seed(42)
img1 = Image.fromarray(np.random.randint(0, 255, (256, 256, 3), dtype=np.uint8))
arr2 = np.array(img1.copy()).astype(np.int16)
arr2[100:150, 100:150] = np.clip(arr2[100:150, 100:150] + 80, 0, 255)
img2 = Image.fromarray(arr2.astype(np.uint8))
gt = Image.fromarray(
    np.where(
        (np.arange(256)[:, None] >= 100) & (np.arange(256)[:, None] < 150)
        & (np.arange(256)[None, :] >= 100) & (np.arange(256)[None, :] < 150),
        255, 0,
    ).astype(np.uint8),
)

def buf(img):
    b = io.BytesIO()
    img.save(b, format='PNG')
    b.seek(0)
    return b.read()

b1, b2, bg = buf(img1), buf(img2), buf(gt)
files_ab = {'img1': ('1.png', b1, 'image/png'), 'img2': ('2.png', b2, 'image/png')}
files_abl = {'img1': ('1.png', b1, 'image/png'), 'img2': ('2.png', b2, 'image/png'), 'label': ('gt.png', bg, 'image/png')}
base_data = {'lat_lng': '', 'location': '', 'change_type': '', 't1_time': '', 't2_time': ''}

# ===== 1. Public Endpoints =====
print('=== 1. Public Endpoints ===')
test('GET /status', 'GET', '/status')
test('GET /captcha', 'GET', '/captcha')
test('POST /recommend-threshold', 'POST', '/recommend-threshold', files=files_ab)

# ===== 2. Auth =====
print('=== 2. Auth ===')
test('GET /profile', 'GET', '/profile', headers=H)
# 只验证「旧密码不对就该被拒」，不真的改口令。
#
# 原来这里是真的把管理员密码改成 Test999 再改回去，两个问题：
#   1. 冒烟脚本不该有这种副作用 —— 两次调用之间脚本一挂，管理员就被锁在门外了
#   2. 路径是 PUT 不是 POST（见 routers/auth.py），写法本身就注定 405
test('PUT /profile/change-password (wrong old pwd rejected)',
     'PUT', '/profile/change-password', exp=400,
     headers=H, json={'old_password': '__definitely_not_the_password__',
                      'new_password': 'Test999'})

# ===== 3. Detection =====
print('=== 3. Detection ===')
r = test('POST /detect (BIT)', 'POST', '/detect', exp=200,
         data={'model': 'BIT', 'threshold': 0.5, **base_data},
         files=files_ab, headers=H)
det_id = None
created_ids = []          # 本次冒烟造出来的记录，收尾时逐条删掉
if r and r.status_code == 200:
    d = r.json()
    det_id = d.get('detection_id')
    if det_id:
        created_ids.append(det_id)
    for field in ['mask', 'heat', 'fusion', 'score', 'detection_id', 'stats']:
        if field not in d:
            print(f'  [BUG] detect response missing "{field}"')
            bugs.append(f'detect-missing-{field}')
    print(f'  det_id={det_id} ratio={d["stats"]["ratio"]}%')

    # Cache hit
    r2 = test('POST /detect (cache)', 'POST', '/detect', exp=200,
              data={'model': 'BIT', 'threshold': 0.5, **base_data},
              files=files_ab, headers=H)
    if r2 and r2.status_code == 200:
        # 缓存命中返回的是**同一条既有记录**的 id，不会再建一行（实测确认：
        # 调用前后表里的 id 集合不变）。登记它只是为了让「登记集 = 实际存在过的行」
        # 这件事在两个分支上都成立 —— 收尾时会去重，重复登记不会重复删。
        cid = r2.json().get('detection_id')
        if cid:
            created_ids.append(cid)
        msg = r2.json().get('msg', '')
        if 'cache' in msg.lower() or '缓存' in msg:
            print('  [cache hit confirmed]')

# ===== 4. Rethreshold & Otsu =====
print('=== 4. Rethreshold & Otsu ===')
if det_id:
    test('POST /detect/rethreshold', 'POST', '/detect/rethreshold', exp=200,
         data={'detection_id': det_id, 'threshold': 0.7}, headers=H)
    r = test('POST /detect/otsu', 'POST', '/detect/otsu', exp=200,
             data={'detection_id': det_id}, headers=H)
    if r and r.status_code == 200:
        ot = r.json().get('threshold', 0)
        if not (0 < ot < 1):
            print(f'  [BUG] Otsu threshold out of range: {ot}')
            bugs.append('otsu-range')

# ===== 5. Multi-Model Compare =====
print('=== 5. Multi-Model Compare ===')
r = test('POST /detect/compare', 'POST', '/detect/compare', exp=200,
         data={'models': json.dumps(['BIT', 'DIFF']), 'threshold': 0.5, **base_data},
         files=files_ab, headers=H)
if r and r.status_code == 200:
    # compare 只把**第一个模型**落库（见 routers/detect.py 的 i == 0 分支），
    # 返回的 detection_id 就是那一条。漏登记它，收尾后就会在库里留一条垃圾记录 ——
    # 之前那两条残留就是这么来的。
    cid = r.json().get('detection_id')
    if cid:
        created_ids.append(cid)

# ===== 6. Evaluate =====
print('=== 6. Evaluate ===')
r = test('POST /evaluate', 'POST', '/evaluate', exp=200,
         data={'models': json.dumps(['BIT', 'DIFF']), 'threshold': 0.5},
         files=files_abl, headers=H)
if r and r.status_code == 200:
    results = r.json().get('results', {})
    for m, v in results.items():
        if 'time_ms' not in v:
            print(f'  [BUG] {m} missing time_ms')
            bugs.append(f'eval-{m}-no-time_ms')
        print(f'  {m}: F1={v.get("f1")}% IoU={v.get("iou")}% time_ms={v.get("time_ms")}ms')

r = test('POST /evaluate/scan', 'POST', '/evaluate/scan', exp=200,
         data={'models': json.dumps(['BIT', 'DIFF'])},
         files=files_abl, headers=H)
if r and r.status_code == 200:
    for m, curve in r.json().get('results', {}).items():
        if len(curve) != 19:
            print(f'  [BUG] {m} scan has {len(curve)} thresholds (expected 19)')
            bugs.append(f'scan-{m}-count')
        else:
            print(f'  {m}: {len(curve)} thresholds, peak F1={max(p["f1"] for p in curve):.1f}%')

# ===== 7. History =====
print('=== 7. History ===')
r = test('GET /history', 'GET', '/history', headers=H)
if r and r.status_code == 200:
    records = r.json().get('data', [])
    if records:
        if 'score' not in records[0] and 'score_url' not in records[0]:
            print('  [BUG] History response missing score_url field')
            bugs.append('history-no-score-url')
# 单条删除的正确路径是 /history/{id}，**不是** /history?record_id=...
#
# 原写法打到的是「清空全部历史」那个接口（DELETE /history），而它返回 200，
# 于是这一项还「通过」了 —— 代价是把整个检测历史删掉。这个坑真踩过，
# 195 条本地记录就是这么没的。改路径之外，顺带把它挪到本文件自造的记录上测，
# 避免再去碰用户已有数据。
test('DELETE /history/99999 (single record, 404 expected)', 'DELETE',
     '/history/99999', exp=404, headers=H)

# ===== 8. AI Security =====
print('=== 8. AI Security ===')
test('POST /ai/chat (no auth)', 'POST', '/ai/chat', exp=401, json={'message': 'hello'})
test('POST /ai/analysis-detect-result (no auth)', 'POST', '/ai/analysis-detect-result', exp=401, json={'detection_id': 1})

# ===== 9. Admin =====
print('=== 9. Admin ===')
test('GET /admin/users', 'GET', '/admin/users', headers=H)

# ===== 10. Annotation =====
print('=== 10. Annotation ===')
if det_id:
    test('POST /annotation/{id}', 'POST', f'/annotation/{det_id}', exp=200, headers=H,
         json={'annotation_data': 'data:image/png;base64,test123'})
    test('GET /annotation/{id}', 'GET', f'/annotation/{det_id}', exp=200, headers=H)

# ===== 11. 收尾：只删本次自造的那一条 =====
# 用单条删除接口，绝不用 DELETE /history（那是清空全部）。
print('=== 11. Cleanup ===')
# 必须去重：缓存命中那条分支会把同一个 id 登记两次，重复删除第二次必然 404，
# 看起来像接口的 bug，其实是登记重了。（真踩过，日志里一眼可见同一 id 删两次。）
for i in dict.fromkeys(created_ids):
    test(f'DELETE /history/{i} (own record)', 'DELETE',
         f'/history/{i}', exp=200, headers=H)
if not created_ids:
    print('  （本次没有造出记录）')

# ===== Summary =====
print(f'\n{"="*50}')
print(f'RESULTS: {pass_cnt} passed, {fail_cnt} failed, {len(bugs)} bugs')
if bugs:
    print('Bugs found:')
    for b in bugs:
        print(f'  - {b}')

# Bug: verify history records include score_url
if 'history-no-score-url' in bugs:
    print('\n--- History score_url investigation ---')
    r = requests.get(f'{BASE}/history', headers=H)
    rec = r.json().get('data', [{}])[0] if r.json().get('data') else {}
    print(f'History record keys: {list(rec.keys())}')
