"""清理 results/ 里没人引用的文件。

## 为什么需要这个脚本

results/ 只增不减：每次检测写 4~5 个文件，而删掉检测记录**不会**删文件。
用久了里面绝大多数是孤儿（实测某次 16631 个文件里 15861 个是孤儿，占 96.6%）。

## 判据不能只看数据库的 URL 字段

有一类文件**不记录在任何字段里**，是按约定推导出来的：

    rethreshold 重建融合图时，由 score_url 推出同期 T2：
        t2_path = score_path.replace("_score.png", "_t2.png")
    （见 services/detect_service.py::rebuild_fusion_from_score）

所以「数据库 URL 里没提到 = 孤儿」是**错的** —— 照这个删会干掉在用的 _t2.png，
那些记录的「重新调阈值」就永久失效，报「缺少 T2 影像，无法重建融合图」。
本脚本把这类推导文件也算进保留集。

用法：
    python scripts/clean_results.py            # 只报告，不动文件（默认）
    python scripts/clean_results.py --delete   # 真的删
"""

import argparse
import pathlib
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RESULTS = ROOT / "results"
DB = ROOT / "blackland.db"


def referenced_names(db_path=DB) -> set[str]:
    """当前应该保留的文件名集合。"""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    refs: set[str] = set()
    try:
        tables = [r[0] for r in con.execute(
            "select name from sqlite_master where type='table'")]
        for t in tables:
            cols = [r[1] for r in con.execute(f"pragma table_info({t})")]
            path_cols = [c for c in cols if "url" in c.lower() or "path" in c.lower()]
            for col in path_cols:
                for (v,) in con.execute(f"select {col} from {t} where {col} is not null"):
                    if isinstance(v, str) and v.strip():
                        refs.add(v.rsplit("/", 1)[-1])
    finally:
        con.close()

    # 由 score_url 推导出的 T2（不在任何字段里）
    derived = {n.replace("_score.png", "_t2.png")
               for n in refs if n.endswith("_score.png")}
    return refs | derived


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--delete", action="store_true",
                    help="真的删除。不加则只报告。")
    ap.add_argument("--results-dir", default=str(RESULTS))
    args = ap.parse_args()

    d = pathlib.Path(args.results_dir)
    if not d.is_dir():
        print(f"目录不存在: {d}")
        return 1

    keep = referenced_names()
    files = [p for p in d.iterdir() if p.is_file()]
    orphans = [p for p in files if p.name not in keep]
    freed = sum(p.stat().st_size for p in orphans)

    print(f"数据库引用（含由 score_url 推导的 _t2.png）: {len(keep)} 个")
    print(f"磁盘上: {len(files)} 个文件，{sum(p.stat().st_size for p in files)/1e6:.1f} MB")
    print(f"孤儿:   {len(orphans)} 个，{freed/1e6:.1f} MB")

    if not args.delete:
        for p in orphans[:5]:
            print(f"    (示例) {p.name}")
        if len(orphans) > 5:
            print(f"    ……另有 {len(orphans) - 5} 个")
        print("\n这是只读预览。确认无误后加 --delete 执行。")
        return 0

    for p in orphans:
        p.unlink()

    left = [p for p in d.iterdir() if p.is_file()]
    missing = [n for n in keep if not (d / n).exists()]
    print(f"\n已删除 {len(orphans)} 个，释放 {freed/1e6:.1f} MB")
    print(f"剩余 {len(left)} 个")
    # 删完必须复查：保留集里有没有被误删的
    print(f"引用但已缺失: {len(missing)} 个" + ("" if not missing else " ← 有问题！"))
    for n in missing[:5]:
        print("   !!", n)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
