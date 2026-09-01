"""台词.md 拆分对齐进图（SecScript → 逐句 LineAudio，produces{order} 大间距排序）。

section-voice-publisher 第一步「拆分进图」的唯一实现。把已批定稿（SecScript=11 的
台词.md，人读 Markdown）幂等拆分为图节点：

  parse_md  解析 台词.md → 行序列（say/narrate/transition/label/ending；**选择**块跳过——
            choice 及配套 jump 暂不进图，建模后续设计；解析失败抛 ValueError 带行号）
  align     md 行 vs 图已有行 difflib 对齐（签名 = op+who+text）→ 保留/更新/新建/删除
  split     经 cypher_exec.py（--stdin --multi 单事务）写图 + 产出报告 JSON

数据模型（00_init/Schema/剧情.md）：
  行身份 = 节点雪花 id（voice key 末段，插入/删除行不影响其他行）
  顺序   = produces 边 order：初始 (i+1)*1000；两句之间插入取 (上+下)//2 中点；
           同缝隙多行均分；中点耗尽（分配后非严格递增）→ 全节重排（order 不进
           voice key，重排安全）
  恢复   = sync 级联置 -1 的行：text_sha1 匹配且 wav 在 → 10（音频复用，保守进审）；
           非 say 行 → 11（无音频语义，拆分即完成）；否则 0
  微调   = 人工改 md 重批后重拆：未变行原样保留（含已批 11），只有改动句置 0
           ——单句修改不丢

CLI:
  python script_splitter.py split --section <sec_id> [--report out.json] [--dry-run]
退码：0 成功（或 dry-run）/ 1 前置校验或解析失败 / 2 参数错。
"""
import argparse
import difflib
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

def _find_repo_root(start: Path) -> Path:
    """向上搜索项目根（含 .claude/scripts/cypher_exec.py 的目录），不依赖固定层级。"""
    for p in (start, *start.parents):
        if (p / ".claude" / "scripts" / "cypher_exec.py").exists():
            return p
    raise RuntimeError("未找到项目根（向上搜索 .claude/scripts/cypher_exec.py 失败）")


ROOT = _find_repo_root(Path(__file__).resolve())     # 项目根
CYPHER_EXEC = ROOT / ".claude" / "scripts" / "cypher_exec.py"
sys.path.insert(0, str(ROOT / ".claude" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # 同目录：voice_bundler
from snowflake_base62 import SnowflakeGenerator  # noqa: E402
from voice_bundler import voice_master_path  # noqa: E402

ORDER_STEP = 1000          # 初始间距
SAY_DEFAULT_POS = "left"   # say 行立绘位兜底（单人块规则值；update 沿用存量时的兜底）


def _block_pos_map(md_rows_in_block: list) -> dict:
    """块内 say 行 who（按首次说话序）→ 立绘位（md 不写 pos，块级规则值即缺省值）：
    1 人 left（独白靠左，与对话框正文起始位一致）/ 2 人先说话者 left 后说话者 right（对话分侧）/
    ≥3 人按首话序 left/right/center（第 4+ 人兜底 center）。"""
    whos = []
    for m in md_rows_in_block:
        if m.get("op") == "say" and m.get("who") and m["who"] not in whos:
            whos.append(m["who"])
    if not whos:
        return {}
    if len(whos) == 1:
        seats = ["left"]
    elif len(whos) == 2:
        seats = ["left", "right"]
    else:
        seats = ["left", "right", "center"]
    return {w: (seats[i] if i < len(seats) else "center") for i, w in enumerate(whos)}

_GEN = SnowflakeGenerator()


def text_sha1(text: str) -> str:
    """台词文本指纹（stale 判定唯一依据，不做 normalize）。与 voice_bundler._text_sha1 同实现。"""
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()


def _q(v) -> str:
    """Cypher 字符串字面量（单引号，转义 \\ 与 '）。None → null。"""
    if v is None:
        return "null"
    s = str(v).replace("\\", "\\\\").replace("'", "\\'")
    return f"'{s}'"


def _run_cypher(cypher: str) -> list:
    """调 cypher_exec.py --json，提取返回的 JSON 数组（cypher_exec 输出含连接提示行）。"""
    proc = subprocess.run(
        [sys.executable, str(CYPHER_EXEC), "-c", cypher, "--json"],
        capture_output=True, text=True, encoding="utf-8",
    )
    out = proc.stdout
    start, end = out.find("["), out.rfind("]")
    if start == -1 or end == -1:
        raise RuntimeError(
            f"cypher_exec 未返回 JSON（退出码 {proc.returncode}）:\nstderr: {proc.stderr}\nstdout: {out}"
        )
    return json.loads(out[start:end + 1])


def _run_cypher_multi(statements: list) -> None:
    """多语句单事务写图（--stdin --multi）；任一失败整体回滚。"""
    tx = "\n".join(statements)
    proc = subprocess.run(
        [sys.executable, str(CYPHER_EXEC), "--stdin", "--multi"],
        input=tx, capture_output=True, text=True, encoding="utf-8",
    )
    if proc.returncode != 0:
        raise RuntimeError(f"写图失败（退出码 {proc.returncode}）:\n{proc.stderr}")


# ── 解析 台词.md ─────────────────────────────────────────────

_SCENE_RE = re.compile(r"^##\s+(\S+)\s+(.+?)\s*(?:（([^）]*)）)?\s*$")
_NARRATE_RE = re.compile(r"^旁白\s*:\s*(.+)$")
# 说话行不支持 [表情] 标注（演出层已与台词分离）：角色名排除 [ 与 ]，残留标注（陆择[微笑]:x）
# 因 group(1) 无法跨 [ 而整行不匹配 → 落入末尾 ValueError 显式拦截
_SAY_RE = re.compile(r"^([^:\[\]]+?)\s*:\s*(.+)$")
_LABEL_RE = re.compile(r"^\*\*分支\s*[:：]\s*(.+?)\s*\*\*$")
_ENDING_RE = re.compile(r"^\*\*结局\*\*\s*[:：]\s*(BE|TE|HE|NE)\s*(?:——|—)\s*(.+)$")
_CHOICE_RE = re.compile(r"^\*\*选择\*\*\s*$")
# 环境音行（与旁白同级别，保留字「环境音」）；必须先于 _SAY_RE 匹配，否则被说话行正则吃掉
_AMBIENT_RE = re.compile(r"^环境音\s*[:：]\s*(.+)$")
# 氛围型环境音：旁白行内嵌标注【环境音:<语义>】（至多一个，与旁白同出）
_INLINE_AMBIENT_RE = re.compile(r"【环境音[:：]([^】]+)】")


def _strip_inline_ambient(narration: str, lineno: int, raw: str) -> tuple:
    """旁白正文 → (纯正文, 氛围语义 or None)。至多一个内嵌标注，多个报错。"""
    found = _INLINE_AMBIENT_RE.findall(narration)
    if len(found) > 1:
        raise ValueError(f"台词.md 第 {lineno} 行内嵌环境音标注多于一个：{raw!r}")
    text = _INLINE_AMBIENT_RE.sub("", narration).strip() if found else narration
    return text, (found[0].strip() if found else None)


def parse_md(path) -> dict:
    """解析 台词.md → {"rows": [...], "blocks": [{block, scene_name}, ...]}。

    - 场景二级标题**不产生图行**（scene 行已去图化）：块定义进 blocks（写入
      SecScript.scene_blocks），后续行各带 scene_block_id（行上存块归属）。
    - 行 dict：op/who/text/kind/scene_block_id(+ambient_text：氛围型旁白)。演出层（立绘
      选择）不在拆分期——由配音判断期选绘建 LineAudio-[:uses]->StandingIllustration 边。
    - `#` 节标题与空行忽略；`**选择**` 块（含其下 `- ` 选项行）整体跳过（choice 不进图）。
    - 无法识别的行抛 ValueError（带行号与原文）——skill 依报错修 md。
    """
    rows, blocks = [], []
    cur_block = None
    in_choice = False
    text = Path(path).read_text(encoding="utf-8")
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#") and not line.startswith("##"):
            continue  # 空行 / 一级节标题
        if _CHOICE_RE.match(line):
            in_choice = True
            continue
        if in_choice:
            if line.startswith("-"):
                continue  # 选择块内的选项行
            in_choice = False  # 其他行 = 选择块结束，继续正常解析
        if line.startswith("##"):
            m = _SCENE_RE.match(line)
            if not m:
                raise ValueError(f"台词.md 第 {n} 行场景标题格式错误：{raw!r}"
                                 "（应为 ## <scene_block_id> <Scene 名>（<时段>））")
            cur_block = m.group(1)
            blocks.append({"block": cur_block, "scene_name": m.group(2).strip()})
            continue
        if cur_block is None:
            raise ValueError(f"台词.md 第 {n} 行出现在首个场景标题之前：{raw!r}")
        m = _NARRATE_RE.match(line)
        if m:
            body, amb = _strip_inline_ambient(m.group(1).strip(), n, raw)
            row = {"op": "narrate", "text": body, "scene_block_id": cur_block}
            if amb:
                row["ambient_text"] = amb
            rows.append(row)
            continue
        m = _AMBIENT_RE.match(line)
        if m:
            rows.append({"op": "transition", "text": m.group(1).strip(),
                         "scene_block_id": cur_block})
            continue
        m = _LABEL_RE.match(line)
        if m:
            rows.append({"op": "label", "text": m.group(1).strip(),
                         "scene_block_id": cur_block})
            continue
        m = _ENDING_RE.match(line)
        if m:
            rows.append({"op": "ending", "kind": m.group(1), "text": m.group(2).strip(),
                         "scene_block_id": cur_block})
            continue
        m = _SAY_RE.match(line)
        if m:
            rows.append({"op": "say", "who": m.group(1).strip(),
                         "text": m.group(2).strip(), "scene_block_id": cur_block})
            continue
        raise ValueError(f"台词.md 第 {n} 行无法解析：{raw!r}（格式规范见 chapter-dialoguer SKILL.md）")
    if not blocks:
        raise ValueError("台词.md 缺场景二级标题（## <scene_block_id> <Scene 名>（<时段>））")
    return {"rows": rows, "blocks": blocks}


def _sig(r: dict) -> tuple:
    """对齐签名：ending 用 kind+落点，narrate 含内嵌氛围语义（标注变化=氛围音变），
    其余 op+who+text。存量 op=scene 图行（已去图化）在此签名下必然落入 delete；
    存量 op=ambient 归一为 transition（改名兼容，防历史图行对齐断裂误置 0 重配）。"""
    op = r.get("op")
    if op == "ambient":
        op = "transition"
    if op == "ending":
        return ("ending", "", (r.get("kind") or "") + "——" + (r.get("text") or ""))
    if op == "narrate":
        return ("narrate", "", (r.get("text") or "") + "⟨" + (r.get("ambient_text") or "") + "⟩")
    return (op, r.get("who") or "", r.get("text") or "")


def _row_name(m: dict) -> str:
    """行正文即 name。"""
    return m.get("text") or ""


def _wav_exists(voice_key: str) -> bool:
    """母带是否已生成（-1 恢复判定）。路径从 key 自身解析（15_声音/<stem>/<block>/），
    不查图不按角色目录——章改名后图上现算的 stem 会指错旧 wav 位置。"""
    if not voice_key:
        return False
    try:
        return voice_master_path(ROOT, voice_key).exists()
    except ValueError:
        return False


def _purge_line_audio_files(g: dict, report: dict) -> None:
    """删除行时清理其音频产物：母带 + 运行时副本 + Godot .import 伴生。
    say 行按 voice_key（voices 目录），ambient 行按 ambient_track（sfx 目录）。"""
    keys = [k for k in (g.get("voice_key"), g.get("ambient_track")) if k]
    purged = []
    for key in keys:
        try:
            master = voice_master_path(ROOT, key)
        except ValueError:
            continue
        runtime_root = ROOT / "99_game" / "assets" / ("sfx" if key.startswith("amb-") else "voices")
        for p in (master, runtime_root / f"{key}.wav", Path(str(master) + ".import"),
                  Path(str(runtime_root / f"{key}.wav") + ".import")):
            if p.exists():
                p.unlink()
                purged.append(str(p))
    if purged:
        report.setdefault("purged", []).extend(purged)


# ── 对齐 ─────────────────────────────────────────────────────

def align(md_rows: list, graph_rows: list) -> dict:
    """md 行 vs 图行（须按 order 升序）→ {keep, update, create, delete} 计划。

    keep   equal：签名全同（text 必相同）。-1 恢复 / 演出字段 diff 在 build_actions 处理
    update replace 块按位置配对：沿用图行 id/order，字段全量更新，status=0（stale 重配）
    create md 独有：新节点（雪花 id）+ order 中点
    delete 图独有：DETACH DELETE（wav 留盘）
    """
    sm = difflib.SequenceMatcher(None, [_sig(r) for r in graph_rows], [_sig(r) for r in md_rows])
    plan = {"keep": [], "update": [], "create": [], "delete": []}
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                plan["keep"].append({"graph": graph_rows[i1 + k], "md": md_rows[j1 + k]})
        elif tag == "delete":
            plan["delete"].extend({"graph": g} for g in graph_rows[i1:i2])
        elif tag == "insert":
            plan["create"].extend({"md": m} for m in md_rows[j1:j2])
        else:  # replace：按位置配对，多出部分按删/建
            n = min(i2 - i1, j2 - j1)
            for k in range(n):
                plan["update"].append({"graph": graph_rows[i1 + k], "md": md_rows[j1 + k]})
            plan["delete"].extend({"graph": g} for g in graph_rows[i1 + n:i2])
            plan["create"].extend({"md": m} for m in md_rows[j1 + n:j2])
    return plan


def assign_orders(md_rows: list, plan: dict) -> tuple:
    """给最终序列（md 顺序）分配 order。返回 (seq, reordered)。

    seq = [{md, action, graph?, id, order}]。create 行取上下邻居中点（同缝隙多行均分
    gap/(n+1)）；头/尾插入外推 ±1000；分配后非严格递增（或旧行缺 order）→ 全节重排
    (i+1)*1000（reordered=True，order 不进 voice key，重排安全）。
    """
    by_md = {}
    for action in ("keep", "update"):
        for it in plan[action]:
            by_md[id(it["md"])] = (action, it)
    seq = []
    for m in md_rows:
        hit = by_md.get(id(m))
        if hit:
            action, it = hit
            seq.append({"md": m, "action": action,
                        "graph": it["graph"], "id": it["graph"]["id"],
                        "order": it["graph"].get("ord")})
        else:
            seq.append({"md": m, "action": "create", "graph": None,
                        "id": _GEN.next_id_base62(), "order": None})
    if any(item["action"] != "create" and item["order"] is None for item in seq):
        for i, item in enumerate(seq, 1):  # 旧图行缺 order：直接全节重排
            item["order"] = i * ORDER_STEP
        return seq, True
    _fill_creates(seq)
    if not _strictly_increasing(seq):
        for i, item in enumerate(seq, 1):
            item["order"] = i * ORDER_STEP
        return seq, True
    return seq, False


def _fill_creates(seq: list) -> None:
    """为连续 create 段分配中点 order（同缝隙多行均分；头尾外推）。原地修改。"""
    i = 0
    while i < len(seq):
        if seq[i]["action"] != "create":
            i += 1
            continue
        j = i
        while j < len(seq) and seq[j]["action"] == "create":
            j += 1
        n = j - i
        prev_o = seq[i - 1]["order"] if i > 0 else None
        next_o = seq[j]["order"] if j < len(seq) else None
        if prev_o is None and next_o is None:      # 全新节：顺序铺开
            for k in range(n):
                seq[i + k]["order"] = (k + 1) * ORDER_STEP
        elif prev_o is None:                        # 头部插入：向左外推
            for k in range(n):
                seq[i + k]["order"] = next_o - ORDER_STEP * (n - k)
        elif next_o is None:                        # 尾部插入：向右外推
            for k in range(n):
                seq[i + k]["order"] = prev_o + ORDER_STEP * (k + 1)
        else:                                       # 缝隙均分 (prev, next)
            gap = next_o - prev_o
            step = gap // (n + 1)
            for k in range(n):
                seq[i + k]["order"] = prev_o + step * (k + 1) if step > 0 else prev_o
        i = j


def _strictly_increasing(seq: list) -> bool:
    return all(a["order"] < b["order"] for a, b in zip(seq, seq[1:]))


# ── 动作生成（恢复 / 演出 diff / 字段更新 / 建删） ──────────────

def _set_props(m: dict, pos) -> str:
    """行字段全量 SET 子句（update/create 用）。status：音频行（say 配音 / transition
    转场音效 / 带内嵌氛围的 narrate）=0 待产；其余非音频行 =11。"""
    has_amb = m["op"] == "narrate" and m.get("ambient_text")
    return ", ".join([
        f"l.name={_q(_row_name(m))}",
        f"l.op={_q(m['op'])}",
        f"l.who={_q(m.get('who'))}",
        f"l.pos={_q(pos)}",
        f"l.text={_q(m.get('text'))}",
        f"l.kind={_q(m.get('kind'))}",
        f"l.scene_block_id={_q(m.get('scene_block_id'))}",
        f"l.ambient_text={_q(m.get('ambient_text'))}",
        f"l.text_sha1={_q(text_sha1(m.get('text') or ''))}",
        f"l.status={0 if m['op'] in ('say', 'transition') or has_amb else 11}",
    ])


def build_actions(seq: list, plan: dict, sc_id: str) -> tuple:
    """最终序列 → (cypher 语句列表, 报告 dict)。含 keep 的 -1 恢复、块归属补写与演出字段 diff。"""
    stmts = []
    report = {"counts": {"kept": 0, "created": 0, "updated": 0, "deleted": 0, "restored": 0},
              "created": [], "updated": [], "deleted": [], "restored": [], "warnings": []}

    for it in plan["delete"]:  # 图有 md 无：删行 + 清理音频产物（母带/运行时副本/.import）
        g = it["graph"]
        _purge_line_audio_files(g, report)
        stmts.append(f"MATCH (l:LineAudio {{id:{_q(g['id'])}}}) DETACH DELETE l;")
        report["deleted"].append({"id": g["id"], "op": g.get("op"),
                                  "text": (g.get("text") or "")[:30]})

    pos_map = {}  # 块内 who → 规则立绘位（块级分配：对话分侧/单人靠左，块切换重算）
    prev_block = None
    for idx, item in enumerate(seq):
        m, action, oid, order = item["md"], item["action"], item["id"], item["order"]
        if m.get("scene_block_id") != prev_block:
            prev_block = m.get("scene_block_id")
            blk_rows = []
            for it2 in seq[idx:]:
                if it2["md"].get("scene_block_id") != prev_block:
                    break
                blk_rows.append(it2["md"])
            pos_map = _block_pos_map(blk_rows)
        if action == "create":
            pos = pos_map.get(m.get("who") or "") if m["op"] == "say" else None
            stmts.append(
                f"MERGE (l:LineAudio {{id:{_q(oid)}}}) "
                f"ON CREATE SET {_set_props(m, pos)} "
                f"WITH l MATCH (sc:SecScript {{id:{_q(sc_id)}}}) "
                f"MERGE (sc)-[r:produces]->(l) SET r.order={order}, r.sync=true;"
            )
            report["created"].append({"id": oid, "op": m["op"], "order": order,
                                      "text": (m.get("text") or m.get("scene_block_id") or "")[:30]})
        elif action == "update":  # 台词变了（stale）：沿用 id/order，全量更新，置 0 重配
            g = item["graph"]
            pos = g.get("pos")
            if m["op"] == "say":
                pos = pos_map.get(m.get("who") or "") or pos
            stmts.append(f"MATCH (l:LineAudio {{id:{_q(oid)}}}) SET {_set_props(m, pos)};")
            # 氛围型旁白：正文改了但 ambient_text 未变且音频已在 → 保留已产（置 10 进审），
            # 不白白重做环境音（音频跟语义走，不跟旁白正文走）
            if m.get("ambient_text") and m.get("ambient_text") == g.get("ambient_text") \
                    and g.get("ambient_track") and _wav_exists(g["ambient_track"]):
                stmts.append(f"MATCH (l:LineAudio {{id:{_q(oid)}}}) SET l.status=10, "
                             f"l.ambient_track={_q(g['ambient_track'])};")
                report.setdefault("reused_amb", []).append({"id": oid})
            if m["op"] == "say":
                pos_map[m.get("who") or ""] = pos or SAY_DEFAULT_POS
            report["updated"].append({"id": oid, "op": m["op"],
                                      "text": (m.get("text") or "")[:30]})
        else:  # keep：未变行。仅 -1 恢复、演出字段 diff（op 归一/pos）与块归属补写，status 0/10/11 原样保留
            g = item["graph"]
            if g.get("op") == "ambient" and m["op"] == "transition":
                # 存量 op=ambient 改名归一（幂等自愈；_sig 已归一防对齐断裂，此处落图）
                stmts.append(f"MATCH (l:LineAudio {{id:{_q(oid)}}}) SET l.op='transition';")
                g = {**g, "op": "transition"}
            if g.get("scene_block_id") != m.get("scene_block_id"):
                # scene 行去图化的存量迁移：行上补写块归属（不动 status，幂等）
                stmts.append(f"MATCH (l:LineAudio {{id:{_q(oid)}}}) "
                             f"SET l.scene_block_id={_q(m.get('scene_block_id'))};")
            if g.get("status") == -1:
                # 非音频行恢复 11；音频行按「键在 +（say 另需 text_sha1 匹配）+ 母带 wav 在」恢复 10
                track = g.get("ambient_track")
                if m["op"] == "say":
                    ok = g.get("voice_key") and g.get("text_sha1") == text_sha1(m.get("text") or "") \
                        and _wav_exists(g.get("voice_key"))
                    new_status = 10 if ok else 0
                elif m["op"] == "ambient" or m.get("ambient_text"):
                    ok = track and _wav_exists(track)
                    new_status = 10 if ok else 0
                else:
                    new_status = 11
                stmts.append(f"MATCH (l:LineAudio {{id:{_q(oid)}}}) SET l.status={new_status};")
                report["restored"].append({"id": oid, "to": new_status})
            if m["op"] == "say":
                want = pos_map.get(m.get("who") or "")
                if want and g.get("pos") != want:  # 演出 diff：存量 pos 与块规则不一致 → 自愈补写
                    stmts.append(f"MATCH (l:LineAudio {{id:{_q(oid)}}}) SET l.pos={_q(want)};")
                    report.setdefault("pos_fixed", []).append({"id": oid, "to": want})
            report["counts"]["kept"] += 1

    report["counts"].update(created=len(report["created"]), updated=len(report["updated"]),
                            deleted=len(report["deleted"]), restored=len(report["restored"]))
    return stmts, report


def _order_statements(seq: list, sc_id: str, reordered: bool) -> list:
    """order 写入：create 行已在建边语句带 order；重排时对已有行补 SET order。"""
    if not reordered:
        return []
    return [
        f"MATCH (sc:SecScript {{id:{_q(sc_id)}}})-[r:produces]->(l:LineAudio {{id:{_q(item['id'])}}}) "
        f"SET r.order={item['order']};"
        for item in seq if item["action"] != "create"
    ]


# ── split 主流程 ─────────────────────────────────────────────

def split(section_id: str, dry_run: bool = False) -> dict:
    """拆分对齐进图。前置：SecScript=11。返回报告 dict（查询/解析/写图失败 raise）。"""
    rows = _run_cypher(
        "MATCH (:Section {id:'" + section_id + "'})-[:has_outline]->(:SecOutline)"
        "-[:produces]->(sc:SecScript) "
        "RETURN sc.id AS sc_id, sc.script_path AS p, sc.status AS st LIMIT 1"
    )
    if not rows:
        raise ValueError(f"Section {section_id} 无 SecScript（先跑 chapter-dialoguer 产定稿）")
    sc_id, script_path, st = rows[0]["sc_id"], rows[0]["p"], rows[0]["st"]
    if st != 11:
        raise ValueError(f"SecScript.status={st}（须 11 定稿已批才能拆分进图）")
    if not script_path:
        raise ValueError("SecScript.script_path 为空")
    parsed = parse_md(script_path)
    md_rows, blocks = parsed["rows"], parsed["blocks"]

    graph_rows = _run_cypher(
        "MATCH (sc:SecScript {id:'" + sc_id + "'})-[p:produces]->(l:LineAudio) "
        "RETURN l.id AS id, l.op AS op, l.who AS who, l.pos AS pos, "
        "l.text AS text, l.kind AS kind, l.scene_block_id AS scene_block_id, "
        "l.ambient_text AS ambient_text, "
        "l.status AS status, l.attempts AS attempts, l.voice_key AS voice_key, "
        "l.ambient_track AS ambient_track, l.text_sha1 AS text_sha1, p.order AS ord "
        "ORDER BY p.order"
    )

    plan = align(md_rows, graph_rows)
    seq, reordered = assign_orders(md_rows, plan)
    stmts, report = build_actions(seq, plan, sc_id)
    # 块定义写入 SecScript.scene_blocks（scene 行已去图化，块元数据的图上落点）
    stmts.append(f"MATCH (sc:SecScript {{id:{_q(sc_id)}}}) "
                 f"SET sc.scene_blocks={_q(json.dumps(blocks, ensure_ascii=False))};")
    stmts = _order_statements(seq, sc_id, reordered) + stmts
    report.update({"section_id": section_id, "sc_id": sc_id, "script_path": script_path,
                   "reordered": reordered, "statements": len(stmts), "dry_run": dry_run,
                   "blocks": blocks})
    if stmts and not dry_run:
        _run_cypher_multi(stmts)
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="台词.md 拆分对齐进图（SecScript→逐句 LineAudio）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_split = sub.add_parser("split", help="拆分进图")
    p_split.add_argument("--section", required=True, help="Section 节点 ID（snowflake）")
    p_split.add_argument("--report", help="报告 JSON 落盘路径（缺省仅 stdout）")
    p_split.add_argument("--dry-run", action="store_true", help="只产计划不写图")
    args = ap.parse_args(argv)

    try:
        report = split(args.section, dry_run=args.dry_run)
    except (ValueError, RuntimeError) as e:
        sys.stderr.write(f"拆分失败: {e}\n")
        return 1
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(text + "\n", encoding="utf-8")
    print(text)
    c = report["counts"]
    print(f"OK: kept={c['kept']} created={c['created']} updated={c['updated']} "
          f"deleted={c['deleted']} restored={c['restored']} reordered={report['reordered']}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
