"""一次性迁移：15_声音 母带从按人物目录（<char>/<key>.wav）重组为按章节
（<chapter_stem>/<scene_block_id>/<key>.wav）——段信息从 key 自身解析，无需查图。

用法（项目根）：
  python .claude/skills/section-voice-publisher/scripts/migrate_voice_layout.py --dry-run
  python .claude/skills/section-voice-publisher/scripts/migrate_voice_layout.py           # 执行
  python ... --prune-legacy                                # 迁移后删 legacy L00xx 孤儿（图已无该类节点）

- rename 同盘原子；解析失败的文件只报告不动。
- legacy 识别：key 末段（行节点 id）形如 L\\d+ 的为台词.jsonl 时代产物（图上节点已删/从未建）。
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from voice_bundler import split_voice_key  # noqa: E402

_ROOT = Path(__file__).resolve().parents[4]
_MASTER = _ROOT / "15_声音"
_LEGACY_NODE = re.compile(r"^L\d+$")


def main():
    ap = argparse.ArgumentParser(description="15_声音 目录迁移：按人物 → 按章节")
    ap.add_argument("--dry-run", action="store_true", help="只列出计划不执行")
    ap.add_argument("--prune-legacy", action="store_true",
                    help="删除 legacy 孤儿（行 id 形如 L00xx 的旧产物）")
    args = ap.parse_args()

    wavs = sorted(_MASTER.glob("*/*.wav"))
    plan, bad, legacy = [], [], []
    for wav in wavs:
        t = split_voice_key(wav.stem)
        if t is None:
            bad.append(wav)
            continue
        if _LEGACY_NODE.match(t[3]):
            legacy.append(wav)
            continue
        dst = _MASTER / t[1] / t[2] / wav.name
        plan.append((wav, dst))

    for wav, dst in plan:
        mark = "MOVE" if not dst.exists() else "SKIP(exists)"
        print(f"{mark}: {wav.relative_to(_ROOT)} -> {dst.relative_to(_ROOT)}")
        if not args.dry_run and not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            wav.rename(dst)
    for w in bad:
        print(f"UNPARSED(不动): {w.relative_to(_ROOT)}")
    for w in legacy:
        print(f"LEGACY: {w.relative_to(_ROOT)}")
        if args.prune_legacy and not args.dry_run:
            w.unlink()

    # 迁移成功后清空角色目录（仅当目录已空）
    if not args.dry_run:
        for d in sorted(_MASTER.iterdir()):
            if d.is_dir() and not any(d.iterdir()) and d.name not in ("requirements", "sfx_raw"):
                d.rmdir()
                print(f"RMDIR(空): {d.name}")
    n = len(plan) - sum(1 for _, d in plan if d.exists() and not args.dry_run)
    print(f"\n[done] 计划迁移 {len(plan)}，解析失败 {len(bad)}，legacy {len(legacy)}"
          f"{'（dry-run 未执行）' if args.dry_run else ''}")


if __name__ == "__main__":
    main()
