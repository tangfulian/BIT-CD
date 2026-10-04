"""检查前端引用的 i18n 键是否在**两份** locale 里都存在。

为什么需要这个：
    i18n.js 的 _translateElement 是 `key in dict ? dict[key] : key` ——
    找不到键时会把**原始 key 字符串**写进 textContent。也就是说写错一个键名，
    界面不会报错，只会显示 "bigscreen.totalArea" 这种东西，中英都一样坏。
    批量汇总条的 batch.sumTotal 就是这么坏的（两份 locale 都没有那个键）。

用法：
    python scripts/check_i18n_keys.py            # 只报告
    python scripts/check_i18n_keys.py --strict   # 有缺失时以非零码退出（给 CI / 提交前用）
"""
import re
import sys
from pathlib import Path

# Windows 控制台默认是 GBK，报告里的 ✓ ✗ ⚠ 会直接抛 UnicodeEncodeError，
# 把一次「没有任何问题」的检查变成崩溃。改走 UTF-8 并允许替换，别让输出编码
# 决定检查的成败。
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
LOCALES = FRONTEND / "js" / "locales"

# 只检查这些形态；动态拼接的（如 I18n.t('agent.' + mode)）天然抓不到，
# 会在下面的「无法静态判定」里提示，不算失败。
DATA_I18N = re.compile(r'data-i18n(?:-[\w-]+)?="([^"]+)"')
I18N_T = re.compile(r"I18n\.t\(\s*['\"]([^'\"]+)['\"]")
# t('...') 的简写（各页面里 const t = I18n.t.bind(I18n) 之类）
T_SHORT = re.compile(r"(?<![\w.])t\(\s*['\"]([a-zA-Z][\w.]*\.[\w.]+)['\"]")


def keys_in(path: Path) -> set[str]:
    src = path.read_text(encoding="utf-8")
    return set(re.findall(r'^\s*"([^"]+)":', src, re.M))


def values_in(path: Path) -> dict[str, str]:
    src = path.read_text(encoding="utf-8")
    return dict(re.findall(r'^\s*"([^"]+)":\s*"([^"]*)"', src, re.M))


# 抓 <tag ... data-i18n="key" ...>文本</tag> 里的文本（不处理嵌套，够用）
ELEM_WITH_TEXT = re.compile(
    r"<(\w+)([^>]*\bdata-i18n=\"([^\"]+)\"[^>]*)>([^<>]*)</\1>", re.S
)


def main() -> int:
    zh = keys_in(LOCALES / "zh-CN.js")
    en = keys_in(LOCALES / "en.js")
    zhv = values_in(LOCALES / "zh-CN.js")

    used: dict[str, set[str]] = {}
    targets = [FRONTEND / "index.html"] + sorted((FRONTEND / "js").glob("*.js"))
    for f in targets:
        if f.name in ("zh-CN.js", "en.js") or f.parent.name == "locales":
            continue
        text = f.read_text(encoding="utf-8")
        found = set(DATA_I18N.findall(text)) | set(I18N_T.findall(text)) | set(T_SHORT.findall(text))
        for k in found:
            used.setdefault(k, set()).add(str(f.relative_to(ROOT)))

    # 动态拼接的键（'model.' + value）会以裸前缀出现，结尾是点，不算缺失。
    # 拼接处还会被正则连引号一起吞进来，例如
    #   data-i18n="status.req.' + key + '"
    # 会捕获成 `status.req.' + key + '` —— 这种也一律不算键。
    # 代价是这一族键**静态查不到**，靠浏览器里的中英双语断言兜底
    # （见 status.req.* ：9 个桶名的中英两种渲染都在运行时验过）。
    KEY_SHAPE = re.compile(r"[A-Za-z][\w.-]*\Z")

    def real(k: str) -> bool:
        if not KEY_SHAPE.match(k):
            return False
        return not k.endswith(".") and not k.startswith("unit.")

    missing_zh = {k: v for k, v in used.items() if k not in zh and real(k)}
    missing_en = {k: v for k, v in used.items() if k not in en and real(k)}

    print(f"locale 键数：zh {len(zh)} / en {len(en)}")
    print(f"前端静态引用的键：{len(used)}")
    print()

    problems = 0
    if missing_zh:
        problems += len(missing_zh)
        print("✗ zh-CN 里缺失（界面会显示原始 key 字符串）：")
        for k, files in sorted(missing_zh.items()):
            print(f"    {k}   ← {', '.join(sorted(files))}")
    if missing_en:
        problems += len(missing_en)
        print("✗ en 里缺失（英文模式回落到中文或显示原始 key）：")
        for k, files in sorted(missing_en.items()):
            print(f"    {k}   ← {', '.join(sorted(files))}")
    if not (missing_zh or missing_en):
        print("✓ 前端引用的键在两份 locale 里都存在")

    only_en = en - zh
    if only_en:
        print(f"\n只有 en 有的键（{len(only_en)} 个）：{sorted(only_en)[:10]}")

    # HTML 元素上的 data-i18n：元素里的中文应与 locale 的 zh 值一致。
    # 不一致说明接线**改掉了中文界面文案** —— 有时是想要的（页面文案是旧版），
    # 但必须逐条确认，因为它是用户可见的变化。
    drift = []
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    for m in ELEM_WITH_TEXT.finditer(html):
        key, text = m.group(3), m.group(4).strip()
        if not text or not real(key) or key not in zhv:
            continue
        if text != zhv[key]:
            drift.append((key, text, zhv[key]))
    if drift:
        print(f"\n⚠ HTML 元素文字与 locale 值不一致（{len(drift)} 处，接线会改掉中文界面文案）：")
        for key, text, val in drift[:15]:
            print(f"    {key}\n        页面写: {text}\n        locale: {val}")
        if len(drift) > 15:
            print(f"    …另有 {len(drift) - 15} 处")

    return 1 if (problems and "--strict" in sys.argv) else 0


if __name__ == "__main__":
    sys.exit(main())
