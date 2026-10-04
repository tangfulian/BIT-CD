# -*- coding: utf-8 -*-
"""批量修复：models 的 misc 依赖、conftest 的验证码与限流、冒烟脚本移出 tests"""
import pathlib, shutil, sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ROOT = pathlib.Path(r"D:\BIT_CD")

# 1) models/ 依赖顶层 misc 包（仓库中不存在，仅靠 Dockerfile 拷贝维持）→ 改为 core.misc
FIXES = {
    'models/basic_model.py': [('from misc.imutils', 'from core.misc.imutils')],
    'models/trainer.py': [
        ('from misc.metric_tool', 'from core.misc.metric_tool'),
        ('from misc.logger_tool', 'from core.misc.logger_tool'),
    ],
}
for rel, subs in FIXES.items():
    p = ROOT / rel
    t = p.read_text(encoding='utf-8')
    n = 0
    for a, b in subs:
        if a in t:
            t = t.replace(a, b)
            n += 1
    p.write_text(t, encoding='utf-8')
    print(f"✓ {rel}: 修正 {n} 处 import")

# 2) conftest.py：绕过验证码 + 重置限流（否则 register/login 全部 422 / 429）
cf = ROOT / 'tests/conftest.py'
t = cf.read_text(encoding='utf-8')
if 'bypass_captcha' not in t:
    t += '''

@pytest.fixture(autouse=True)
def bypass_captcha(monkeypatch):
    """测试环境跳过图形验证码：register/login 会校验验证码，不绕过则全部 422"""
    import importlib
    from backend.app.core import captcha as captcha_mod
    monkeypatch.setattr(captcha_mod, "verify_captcha", lambda *a, **k: True)
    for name in ("auth", "admin"):
        try:
            mod = importlib.import_module(f"backend.app.routers.{name}")
            if hasattr(mod, "verify_captcha"):
                monkeypatch.setattr(mod, "verify_captcha", lambda *a, **k: True)
        except Exception:
            pass


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """每个用例前重置限流计数，避免跨用例累积触发 429"""
    from backend.app.core.limiter import limiter
    if not hasattr(limiter, "reset"):
        try:
            limiter._storage.reset()
        except Exception:
            pass
    else:
        limiter.reset()
    yield
'''
    cf.write_text(t, encoding='utf-8')
    print("✓ tests/conftest.py: 追加 bypass_captcha / reset_rate_limiter")
else:
    print("· tests/conftest.py: 已包含绕过逻辑，跳过")

# 3) tests/test_full_api.py 在模块顶层就跑 requests 并在失败时 sys.exit(1)，
#    pytest 收集阶段即执行 → 直接中断整个测试会话。移出 tests/ 作为手工冒烟脚本
src = ROOT / 'tests/test_full_api.py'
dst = ROOT / 'scripts/smoke_test.py'
if src.exists():
    shutil.move(str(src), str(dst))
    print("✓ tests/test_full_api.py → scripts/smoke_test.py（不再被 pytest 收集）")
else:
    print("· tests/test_full_api.py 不存在，跳过")

# 4) 把该项目根的 hack 目录也清掉（改为 core.misc 后不再需要）
print()
print("完成。")
