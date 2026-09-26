"""Comprehensive API test suite for BIT_CD system."""
import requests, json, io, sys
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
r = requests.post(f'{BASE}/login', json={'username': 'admin', 'password': 'admin123'})
if r.status_code != 200:
    print('Cannot login - aborting tests')
    sys.exit(1)
tok = r.json()['token']
H = {'Authorization': f'Bearer {tok}'}

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
test('POST /profile/change-password', 'POST', '/profile/change-password',
     headers=H, json={'old_password': 'admin123', 'new_password': 'Test999'})
test('POST /profile/change-password (restore)', 'POST', '/profile/change-password',
     headers=H, json={'old_password': 'Test999', 'new_password': 'admin123'})

# ===== 3. Detection =====
print('=== 3. Detection ===')
r = test('POST /detect (BIT)', 'POST', '/detect', exp=200,
         data={'model': 'BIT', 'threshold': 0.5, **base_data},
         files=files_ab, headers=H)
det_id = None
if r and r.status_code == 200:
    d = r.json()
    det_id = d.get('detection_id')
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
test('POST /detect/compare', 'POST', '/detect/compare', exp=200,
     data={'models': json.dumps(['BIT', 'DIFF']), 'threshold': 0.5, **base_data},
     files=files_ab, headers=H)

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
            print(f'  [BUG] History response missing score_url field')
            bugs.append('history-no-score-url')
test('DELETE /history (404 expected)', 'DELETE', '/history', exp=404, headers=H, params={'record_id': '99999'})

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
