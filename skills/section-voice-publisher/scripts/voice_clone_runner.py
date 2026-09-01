"""Qwen3 声音链脚本（设计 + 配音全链：char-voice-design 候选/试听 + section-voice-publisher 逐句配音）。

**env/.venv-qwen（项目内 venv, Python 3.14 + Qwen3-TTS）跑——项目唯一声音链 venv。**

> 本脚本承担声音链全部合成：设计音色出 ref_audio（VoiceDesign）+ 逐句配音 clone
> （Base Voice Clone，`publish` 子命令）。早期 CosyVoice3 inference_instruct2 后端
> （cosyvoice_runner.py）已废弃删除。
>
> 子命令：`ensure-ref`（单 ref，下游配音用） / `design-candidates`（多候选流程第一步：
> 同一 instruct × N 次采样出候选 ref 24k + candidates.json manifest） / `audition`
> （第二步：Qwen3 Base Voice Clone 出每候选 3 情绪试听，情绪靠试听句文本语义自适应） /
> `publish`（逐句配音：按角色 ref + tts_text 变体逐句 clone，母带 → 15_声音/<chapter_stem>/<scene_block_id>/；
> 情绪由 tts_text 变体承载，emotion 不参与合成参数；clone_mode 逐句选演绎通道——
> icl（缺省）=ref 韵律迁移 / xvec=仅说话人向量文本主导演绎，每角色按模式懒建 prompt）。

前置：
  - Qwen VoiceDesign / Base 模型路径：from paths import（读 settings.json）
  - VoiceDesign（instruct + ref_text + ref_audio_path）

输出：ref_audio 落 VoiceDesign.ref_audio_path（如 14_声音设计/<char>/<char>_ref.wav，24kHz），publish 用。
"""
import argparse
import json
import os
import sys

# 脚本所在目录自动在 sys.path[0]，无需 insert 即可 `from paths import`
import torch
import soundfile as sf
from qwen_tts import Qwen3TTSModel
from paths import QWEN_VOICE_DESIGN as VOICE_DESIGN_PATH, QWEN_BASE, to_abs, to_rel
from voice_bundler import split_voice_key, normalize_clone_mode

# 多候选流程默认值：每角色候选数 + 情绪试听文本（每情绪一句，语义与情绪匹配）。
# audition_texts 固化进 candidates.json（单一源），本脚本 audition 子命令消费——
# Qwen3 Base clone 无 instruct 通道，情绪演绎靠试听句文本语义自适应（README 明示能力）。
DEFAULT_COUNT = 3
DEFAULT_AUDITION_TEXTS = {
    "平静": "今天的会议记录我已经整理好了，放在你桌上了。",
    "高兴": "太好了，我们真的赢了，今晚我请大家吃饭！",
    "愤怒": "我说过多少次了，这份文件不能再出错！",
}


def load_design_model(path=VOICE_DESIGN_PATH, device="cuda:0") -> Qwen3TTSModel:
    return Qwen3TTSModel.from_pretrained(
        path, device_map=device, dtype=torch.bfloat16, attn_implementation="sdpa",
    )


def load_base_model(path=QWEN_BASE, device="cuda:0") -> Qwen3TTSModel:
    """Qwen3-TTS-Base（Voice Clone 用；与 VoiceDesign 是两个权重两个实例）。"""
    return Qwen3TTSModel.from_pretrained(
        path, device_map=device, dtype=torch.bfloat16, attn_implementation="sdpa",
    )


def ensure_ref(voice_design: dict, design_model=None, device="cuda:0") -> str:
    """确保角色 ref_audio 就绪：ref_audio_path 文件存在则复用，否则 VoiceDesign 合成并写盘。

    voice_design 字段：instruct / ref_text / ref_audio_path
    返回 ref_audio 路径。
    """
    ref_audio_path = voice_design.get("ref_audio_path")
    if ref_audio_path and os.path.exists(ref_audio_path):
        return ref_audio_path
    if design_model is None:
        design_model = load_design_model(device=device)
    instruct = voice_design["instruct"]
    ref_text = voice_design["ref_text"]
    ref_wavs, sr = design_model.generate_voice_design(text=ref_text, language="Chinese", instruct=instruct)
    if ref_audio_path:
        os.makedirs(os.path.dirname(ref_audio_path) or ".", exist_ok=True)
        sf.write(ref_audio_path, ref_wavs[0], sr)
    return ref_audio_path


def ensure_refs(profiles: dict, device="cuda:0") -> dict:
    """批量 ensure_ref：profiles={char: VoiceDesign}。复用 design_model（整批加载一次）。

    跳过缺 instruct/ref_text 的角色（警告不阻断）。
    返回 {char: ref_audio_path}。
    """
    design_model = None
    produced = {}
    for char, profile in profiles.items():
        if not profile.get("instruct") or not profile.get("ref_text"):
            print(f"[skip] {char}: 缺 instruct/ref_text")
            continue
        ref_path = profile.get("ref_audio_path")
        if ref_path and os.path.exists(ref_path):
            print(f"[reuse] {char}: {ref_path}")
            produced[char] = ref_path
            continue
        if design_model is None:
            design_model = load_design_model(device=device)
        ref = ensure_ref(profile, design_model=design_model, device=device)
        produced[char] = ref
        print(f"[design] {char}: {ref}")
    return produced


def design_candidates(profiles: dict, device="cuda:0") -> dict:
    """按 profiles={char: {instruct, ref_text, candidates_dir, count?}} 出 N 个候选 ref + manifest。

    同一 instruct × N 次独立采样（库默认 do_sample 开）出 N 个音色变体；候选 wav 已存在
    即跳过（断点续跑）。写 candidates_dir/candidates.json：候选 ref（24kHz 原生，
    设计阶段不产 16k）+ audition_texts 常量（单一源）。情绪试听由本脚本 audition
    子命令（Qwen3 Base clone）接续。
    返回 {char: manifest 相对路径}。
    """
    design_model = None
    manifests = {}
    for char, profile in profiles.items():
        if not profile.get("instruct") or not profile.get("ref_text"):
            print(f"[skip] {char}: 缺 instruct/ref_text")
            continue
        instruct, ref_text = profile["instruct"], profile["ref_text"]
        count = int(profile.get("count", DEFAULT_COUNT))
        cand_dir = to_abs(profile["candidates_dir"])
        os.makedirs(cand_dir, exist_ok=True)

        entries = []  # [{key, ref(24k 原生)}]
        todo = []
        for i in range(1, count + 1):
            key = f"c{i}"
            ref = os.path.join(cand_dir, f"{char}_{key}_ref.wav")
            entries.append({"key": key, "ref": ref})
            if not os.path.exists(ref):
                todo.append(key)
        if todo:
            if design_model is None:
                design_model = load_design_model(device=device)
            # 批量采样：单 instruct 广播到多条 text，同批独立采样出不同音色变体
            ref_wavs, sr = design_model.generate_voice_design(
                text=[ref_text] * len(todo), language="Chinese", instruct=instruct)
            for key, wav in zip(todo, ref_wavs):
                sf.write(next(e["ref"] for e in entries if e["key"] == key), wav, sr)
            print(f"[design] {char}: {len(todo)} 候选 -> {cand_dir}")
        else:
            print(f"[reuse] {char}: {count} 候选已存在")

        manifest_path = os.path.join(cand_dir, "candidates.json")
        manifest = {
            "char": char,
            "instruct": instruct,
            "ref_text": ref_text,
            "audition_texts": DEFAULT_AUDITION_TEXTS,
            "candidates": [
                {"key": e["key"], "ref": to_rel(e["ref"]), "auditions": {}}
                for e in entries
            ],
        }
        # 断点续跑：保留 audition 已回填的产物路径
        if os.path.exists(manifest_path):
            try:
                old = json.loads(open(manifest_path, encoding="utf-8").read())
                old_aud = {c.get("key"): c.get("auditions", {}) for c in old.get("candidates", [])}
                for c in manifest["candidates"]:
                    c["auditions"] = old_aud.get(c["key"], {}) or {}
            except (ValueError, OSError):
                pass
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        manifests[char] = to_rel(manifest_path)
        print(f"[manifest] {char}: {manifest_path}")
    return manifests


def audition(manifest_path: str, device="cuda:0") -> dict:
    """按 candidates.json 给每候选出情绪试听（Qwen3 Base Voice Clone，env/.venv-qwen）。

    README「Voice Design then Clone」流程：每候选一次 create_voice_clone_prompt(ref, ref_text)
    （ref_text 须与 ref 音频逐字一致——统一长句天然满足），逐情绪 generate_voice_clone。
    Base clone 无 instruct 通道，情绪演绎靠试听句文本语义自适应（试听句本身语义与情绪匹配）。
    试听 wav 已存在即跳过（断点续跑）；回填 manifest 的 auditions 并落盘。
    返回 {"produced": wav 数, "failed": [候选 key]}；failed 非空时调用方视为失败。
    """
    manifest_path = to_abs(manifest_path)
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    char = manifest["char"]
    ref_text = manifest["ref_text"]
    audition_texts = manifest.get("audition_texts") or DEFAULT_AUDITION_TEXTS
    model = load_base_model(device=device)

    produced, failed = 0, []
    for cand in manifest["candidates"]:
        key = cand["key"]
        ref = to_abs(cand["ref"])
        if not os.path.exists(ref):
            print(f"[skip] {char}/{key}: 无候选 ref（先跑 design-candidates）")
            failed.append(key)
            continue
        # 每候选构建一次可复用 prompt（提取 codec code + 说话人向量）
        prompt = model.create_voice_clone_prompt(ref_audio=ref, ref_text=ref_text)
        auditions = cand.setdefault("auditions", {})
        for emo, text in audition_texts.items():
            out = os.path.join(os.path.dirname(ref), f"{char}_{key}_{emo}.wav")
            if not os.path.exists(out):
                wavs, sr = model.generate_voice_clone(
                    text=text, language="Chinese", voice_clone_prompt=prompt)
                sf.write(out, wavs[0], sr)
                produced += 1
                print(f"[audition] {char}/{key} {emo} -> {to_rel(out)}")
            auditions[emo] = to_rel(out)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"[audition] {char}: produced={produced}, failed={failed}")
    return {"produced": produced, "failed": failed}


def publish(tasks: dict, profiles: dict, out_dir, keys=None, device="cuda:0") -> dict:
    """按角色批量 Qwen3 Base Voice Clone（逐句配音母带落 out_dir/<stem>/<block>/<key>.wav）。

    tasks: {char: [{key, text, tts_text?, clone_mode?, emotion, ...}]}（voice_bundler
           tasks-from-graph 产 + skill 已填 emotion/tts_text/clone_mode）
    profiles: {char: {ref_audio_path, ref_text, ...}}（VoiceDesign 字典；ref_text 供 icl
           prompt 构建，须与 ref 音频逐字一致——统一长句天然满足；纯 xvec 批不消费）
    keys: 可选键过滤（列表）——单句/批量重生成只跑指定句；缺省 = tasks 全部。
    ref 以 24k 原生消费（Qwen3 clone 原生采样率，无 16k 重采样副产物）。
    每角色按 clone_mode 懒构建 prompt（同角色 icl/xvec 可混排）：
      icl（缺省）= ICL——ref codec + ref_text 韵律迁移，音色最稳；
      xvec = 仅说话人向量——丢 ref 韵律、文本语义主导演绎（迟疑/强情绪句；
      demo/hesitation_demo.py 变体 C 验证平静 ref 韵律会压制文本语气）。
    emotion 不参与合成参数（Base clone 无 instruct 通道）——情绪全部由 tts_text 变体承载，
    缺 tts_text 回落 text 原文；emotion 仅随 bind-graph 写图作标注。
    返回 {produced: {char: [wav_path]}, skipped: [char], failed: [{char, key, error}]}。
    逐句 try/except：单句失败记入 failed 不炸整批（bind-graph 只 bind 成功句，失败句保持
    待配下轮重挑）；首句模式的 prompt 构建失败 → 该角色全句 failed（现状粒度），
    追加模式构建失败降级为该句 failed。
    """
    key_set = {k.strip() for k in keys if k.strip()} if keys else None
    model = None  # 懒加载一次（全部角色 skip 时不加载）
    produced, skipped, failed = {}, [], []
    for char, items in tasks.items():
        todo = [it for it in items if key_set is None or it.get("key") in key_set]
        if not todo:
            continue
        profile = profiles.get(char) or {}
        ref_path = profile.get("ref_audio_path")
        ref_text = profile.get("ref_text")
        # xvec 只需 ref 音频（说话人向量）；icl 另需 ref_text（须与 ref 逐字一致）
        need_icl = any(normalize_clone_mode(it.get("clone_mode")) == "icl" for it in todo)
        if not ref_path or not os.path.exists(ref_path) or (need_icl and not ref_text):
            print(f"[skip] {char}: 缺 ref_audio_path{'/ref_text' if need_icl else ''}"
                  " 或文件不存在（先跑 ensure-ref / 补 profiles ref_text）")
            skipped.append(char)
            continue
        prompts = {}  # {mode: prompt} 按模式懒构建——只建本批实际出现的模式

        def _prompt(mode):
            if mode not in prompts:
                prompts[mode] = model.create_voice_clone_prompt(
                    ref_audio=ref_path,
                    ref_text=ref_text if mode == "icl" else None,  # xvec 忽略 ref_text
                    x_vector_only_mode=(mode == "xvec"))
            return prompts[mode]

        try:
            if model is None:
                model = load_base_model(device=device)
            _prompt(normalize_clone_mode(todo[0].get("clone_mode")))  # 首句模式提前构建：失败→该角色全句 failed
        except Exception as e:  # 模型加载/prompt 构建失败：该角色全部句记 failed，不炸整批
            for it in todo:
                failed.append({"char": char, "key": it.get("key"), "error": str(e)})
            print(f"[fail] {char}: clone prompt 构建失败: {e}")
            continue
        paths, mode_n = [], {}
        for it in todo:
            try:
                mode = normalize_clone_mode(it.get("clone_mode"))
                # 情绪承载唯一通道仍是 tts_text 变体（LLM 由原文产，加语气符号引导）；
                # mode 只换演绎通道。缺省回落原文。
                tts_input = it.get("tts_text") or it["text"]
                wavs, sr = model.generate_voice_clone(
                    text=tts_input, language="Chinese", voice_clone_prompt=_prompt(mode))
                # 母带按章节整理：15_声音/<chapter_stem>/<scene_block_id>/<key>.wav
                # （段信息从 key 自身解析，角色名不进目录）
                t = split_voice_key(it["key"])
                if t is None:
                    raise ValueError(f"key 无法解析：{it['key']!r}")
                out = os.path.join(out_dir, t[1], t[2], f"{it['key']}.wav")
                os.makedirs(os.path.dirname(out), exist_ok=True)
                sf.write(out, wavs[0], sr)
                paths.append(out)
                mode_n[mode] = mode_n.get(mode, 0) + 1
            except Exception as e:  # 单句失败不炸整批（含追加模式 prompt 构建失败）
                failed.append({"char": char, "key": it.get("key"),
                               "error": f"[{normalize_clone_mode(it.get('clone_mode'))}] {e}"})
                print(f"[fail] {char}/{it.get('key')}: {e}")
        produced[char] = paths
        dist = " / ".join(f"{m} {n}" for m, n in mode_n.items()) if mode_n else "-"
        print(f"[ok] {char}: {len(paths)} wav（{dist}，母带按 章节/场景块 归档）")
    return {"produced": produced, "skipped": skipped, "failed": failed}


def main():
    ap = argparse.ArgumentParser(description="Qwen3 声音链脚本（设计 ref + 逐句配音 clone，env/.venv-qwen 跑）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_ref = sub.add_parser("ensure-ref", help="确保各角色 ref_audio 就绪（复用或 VoiceDesign 合成）")
    p_ref.add_argument("--profiles", required=True, help="{char: VoiceDesign dict} JSON")
    p_ref.add_argument("--device", default="cuda:0")
    p_ref.set_defaults(_mode="ensure-ref")

    p_cand = sub.add_parser(
        "design-candidates",
        help="同一 instruct × N 次采样出候选 ref（24k）+ manifest（多候选流程第一步）")
    p_cand.add_argument("--profiles", required=True,
                        help="{char: {instruct, ref_text, candidates_dir, count?}} JSON")
    p_cand.add_argument("--device", default="cuda:0")
    p_cand.set_defaults(_mode="design-candidates")

    p_aud = sub.add_parser(
        "audition",
        help="按 candidates.json 给每候选出 3 情绪试听（Qwen3 Base Voice Clone，多候选流程第二步）")
    p_aud.add_argument("--manifest", required=True,
                       help="design-candidates 产的 candidates.json（回填 auditions）")
    p_aud.add_argument("--device", default="cuda:0")
    p_aud.set_defaults(_mode="audition")

    p_pub = sub.add_parser(
        "publish",
        help="按角色批量 Qwen3 Base Voice Clone（逐句配音母带 → 15_声音/<chapter_stem>/<scene_block_id>/，消费 tasks.json + profiles.json）")
    p_pub.add_argument("tasks", help="voice_bundler.py tasks-from-graph 产出的 tasks.json（skill 已填 emotion/tts_text/clone_mode）")
    p_pub.add_argument("--profiles", required=True, help="{char: VoiceDesign dict} JSON（需 ref_audio_path + ref_text）")
    p_pub.add_argument("--out-dir", default="15_声音", help="母带根目录（写 <out-dir>/<chapter_stem>/<scene_block_id>/<key>.wav，路径段从 key 解析；运行时副本由 chapter-publisher 发布时收录）")
    p_pub.add_argument("--keys", default=None, help="只生成指定 key（逗号分隔，单句/批量重生成用；缺省=全部）")
    p_pub.add_argument("--device", default="cuda:0")
    p_pub.set_defaults(_mode="publish")

    args = ap.parse_args()
    if args._mode == "ensure-ref":
        profiles = json.loads(open(args.profiles, encoding="utf-8").read())
        result = ensure_refs(profiles, device=args.device)
        print(f"[ensure-ref] {len(result)} 角色就绪")
    elif args._mode == "design-candidates":
        profiles = json.loads(open(args.profiles, encoding="utf-8").read())
        manifests = design_candidates(profiles, device=args.device)
        print(f"[design-candidates] {len(manifests)} 角色 manifest 就绪")
    elif args._mode == "audition":
        result = audition(args.manifest, device=args.device)
        if result["failed"]:
            sys.exit(1)  # 供 skill 感知失败（先产物后写图约束）
    elif args._mode == "publish":
        tasks = json.loads(open(args.tasks, encoding="utf-8").read())
        profiles = json.loads(open(args.profiles, encoding="utf-8").read())
        keys = args.keys.split(",") if args.keys else None
        result = publish(tasks, profiles, args.out_dir, keys=keys, device=args.device)
        total = sum(len(v) for v in result["produced"].values())
        print(f"[publish] produced={total} wav, skipped={result['skipped']}, failed={len(result['failed'])}")
        if result["failed"]:
            for f in result["failed"]:
                print(f"  failed: {f['char']}/{f['key']}: {f['error']}")
            sys.exit(1)


if __name__ == "__main__":
    main()
