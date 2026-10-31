"""前端 ES 模块的语法检查。

为什么需要：2026-10-31 清理 i18n 孤儿键时，`locales/zh-CN.js` 里少了一个逗号，
整个前端的模块图全部加载失败 —— 页面白屏，而 `check_i18n_keys.py` 用的是正则、
照样报「✓」。Python 测试也碰不到前端，于是这个问题一路进了提交。

这里用 node 把每个 `.js` 当 ES 模块解析一遍。node 只在 CI 与装有它的开发机
上跑；没有 node 就跳过，不把「没装 node」当成失败。

注意 `node --check` 对 `.js` 按 CommonJS 解析，遇到 import/export 会误报，
所以先复制成 `.mjs` 再检查。
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="没有 node，跳过前端语法检查"
)


def _modules():
    files = sorted(FRONTEND.glob("js/**/*.js")) + sorted(FRONTEND.glob("*.js"))
    # config.local.js 是本地私有配置，不入库，可能不存在
    return [f for f in files if f.name != "config.local.js"]


def test_all_frontend_modules_parse(tmp_path):
    broken = []
    for src in _modules():
        target = tmp_path / (src.stem + ".mjs")
        shutil.copyfile(src, target)
        proc = subprocess.run(
            ["node", "--check", str(target)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            msg = (proc.stderr or "").strip().splitlines()
            broken.append(f"{src.relative_to(ROOT)}\n  " + "\n  ".join(msg[:4]))

    assert not broken, "以下前端模块有语法错误：\n\n" + "\n\n".join(broken)


def test_locale_files_are_balanced():
    """locale 是纯对象字面量，括号/引号数量对不上一定是坏的。

    比 node 那条更弱，但不需要 node，本地也能跑。
    """
    for name in ("zh-CN.js", "en.js"):
        src = (FRONTEND / "js" / "locales" / name).read_text(encoding="utf-8")
        assert src.count("{") == src.count("}"), f"{name} 花括号不配对"
        # 每个键值对行都必须以逗号或结尾的 } 收尾
        lines = [l for l in src.splitlines() if l.strip().startswith('"')]
        bad = [l for l in lines[:-1] if not l.rstrip().endswith(",")]
        assert not bad, f"{name} 这些行缺逗号：{bad[:3]}"
