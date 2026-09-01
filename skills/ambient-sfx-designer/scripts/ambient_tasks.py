"""环境音行任务生成（系统 python 跑）：查单节 op=transition status=0 的图行（+ narrate 内嵌声景）→ jobs JSON。

track 由本脚本预计算（amb-<stem>-<block>-<node_id>，复用 voice_bundler 单源构造），
杜绝 LLM 手拼 key。块归属按 produces.order 遍历遇 op=scene 行切块推导（行上不冗余存）。
"""
import argparse
import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS.parent.parent / "section-voice-publisher" / "scripts"))
from voice_bundler import _run_cypher, chapter_stem_from_meta, make_ambient_track  # noqa: E402


def collect(section_id: str) -> list:
    rows = _run_cypher(
        "MATCH (ch:Chapter)-[:has_section]->(sec:Section {id:'" + section_id + "'}) "
        "OPTIONAL MATCH (sec)-[:has_outline]->(ol:SecOutline)-[:produces]->(sc:SecScript) "
        "OPTIONAL MATCH (sc)-[p:produces]->(l:LineAudio) "
        "RETURN ch.chapter_no AS no, ch.title AS title, sc.id AS sc_id, "
        "l.id AS lid, l.op AS op, l.text AS text, l.ambient_text AS ambient_text, "
        "l.ambient_track AS ambient_track, "
        "l.status AS status, l.scene_block_id AS block, p.order AS ord "
        "ORDER BY p.order"
    )
    if not rows or not rows[0].get("sc_id"):
        raise SystemExit(f"Section {section_id} 无 SecScript（先定稿+拆分）")
    stem = chapter_stem_from_meta(rows[0]["no"], rows[0]["title"])

    jobs, seen_any_line = [], False
    for r in rows:
        if not r.get("lid"):
            continue
        seen_any_line = True
        block = r.get("block") or ""  # 行上直读块归属（scene 行已去图化）
        if r["op"] in ("transition", "ambient"):  # ambient 为存量值兼容（已改名 transition）
            kind, text = "transition", r.get("text") or ""
        elif r["op"] == "narrate" and r.get("ambient_text"):
            kind, text = "ambience", r["ambient_text"]  # 氛围型：语义在旁白行 ambient_text
        else:
            continue
        if r.get("status") != 0:
            continue  # 只挑待产行（被驳回/未产/stale 均归一于 0）
        track = r.get("ambient_track") or make_ambient_track(stem, block, r["lid"])
        jobs.append({"node_id": r["lid"], "track": track, "stem": stem,
                     "block": block, "text": text, "kind": kind})
    if not seen_any_line:
        raise SystemExit(f"Section {section_id} 图无行（先 section-voice-publisher 拆分）")
    return jobs


def main():
    ap = argparse.ArgumentParser(description="环境音行任务生成（op=transition status=0 + 氛围 narrate → jobs JSON）")
    ap.add_argument("--section", required=True)
    ap.add_argument("-o", "--out", default="-", help="输出路径（默认打印 stdout）")
    args = ap.parse_args()

    jobs = collect(args.section)
    data = json.dumps(jobs, ensure_ascii=False, indent=2)
    if args.out == "-":
        print(data)
    else:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(data, encoding="utf-8")
    print(f"[tasks] {len(jobs)} 条环境音待产", file=sys.stderr)


if __name__ == "__main__":
    main()
