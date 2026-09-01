"""AudioFly 环境音生成（图行驱动的氛围层产出；**env/.venv-audiofly，Python 3.11** 跑）。

收编自 demo/ambient_demo.py（2026-08-28 验证链路）。AudioFly（讯飞开源 LDM，
ModelScope `iflytek/AudioFly`，Apache 2.0）：PixArt-MDT DiT + flan-t5-large +
BigVGAN，单次固定出 10s / 44.1kHz；ddim_steps=200 / cfg=3.5 官方推荐不建议改。

子命令：
  jobs <jobs.json>       批量生成候选：jobs = [{track, prompt, kind, count?}, ...]，
                         候选落 .tmp/ambient/<track>_c<i>.wav（10s 原生段）
  finalize <候选wav> <母带wav> --kind ambience|transition [--seconds 5|--cut 1.5] [--fade 2]
                         裁剪+淡出落母带（氛围 ~5s+淡出 / 转场 1~2s 峰值截取）

- prompt 必须英文（AudioCaps 语料训练 + flan-t5 编码）——中文语义由 skill 翻写。
- 模型加载 ~8GB 显存 fp32，一次加载批量跑全节候选（生成 ~68s/条）。
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

MODEL_DIR = r"D:/model/AudioFly"


def _find_repo_root(start: Path) -> Path:
    for p in (start, *start.parents):
        if (p / ".claude" / "scripts" / "cypher_exec.py").exists():
            return p
    raise RuntimeError("未找到项目根（向上搜索 .claude/scripts/cypher_exec.py 失败）")


ROOT = _find_repo_root(Path(__file__).resolve())


def load_model():
    """按官方快速入门加载 LatentDiffusion（ckpt 相对路径 → cwd 必须在模型根）。"""
    import torch
    import yaml

    os.chdir(MODEL_DIR)
    sys.path.insert(0, MODEL_DIR)
    from ldm.utils.util import instantiate_from_config

    configs = yaml.load(open("./config/config.yaml", "r"), Loader=yaml.FullLoader)
    model = instantiate_from_config(configs["model"])
    checkpoint = torch.load("./models/ldm/model.ckpt")
    model.load_state_dict(checkpoint, strict=False)
    model.eval()
    return model.cuda()


def cut_peak(seg: np.ndarray, sr: int, seconds: float) -> np.ndarray:
    """事件型短音效截取：取能量峰值前后保留起振的 N 秒。"""
    n = int(seconds * sr)
    if n >= len(seg):
        return seg
    win = max(1, int(0.05 * sr))
    energy = np.convolve(seg**2, np.ones(win) / win, mode="same")
    start = int(np.argmax(energy)) - int(0.15 * sr)
    start = max(0, min(start, len(seg) - n))
    return seg[start: start + n]


def fade_out(seg: np.ndarray, sr: int, fade_s: float) -> np.ndarray:
    """末尾等功率淡出（cos²）；fade 自动 clamp 到时长 30%。单声道/多声道通用：
    权重曲线 (N,) 按尾段维度扩成 (N,1,…,1) 广播（多声道各通道同一曲线）。"""
    fade = int(min(fade_s * sr, len(seg) * 0.3))
    if fade <= 0:
        return seg
    t = np.linspace(0, np.pi / 2, fade, dtype=np.float32)
    w = (np.cos(t) ** 2).reshape((-1,) + (1,) * (seg.ndim - 1))
    seg[-fade:] = seg[-fade:] * w
    return seg


def cmd_jobs(args):
    jobs = json.loads(Path(args.jobs).read_text(encoding="utf-8"))
    out_dir = ROOT / ".tmp" / "ambient"
    out_dir.mkdir(parents=True, exist_ok=True)
    import torch

    t0 = time.time()
    model = load_model()
    print(f"[load] AudioFly 就绪 {time.time()-t0:.0f}s | {len(jobs)} 条 job")
    for job in jobs:
        track, prompt = job["track"], job["prompt"]
        count = int(job.get("count", 1))  # 单候选制：不满意换 seed/prompt 重出，不做多选一
        if args.seed is not None:
            torch.manual_seed(args.seed)
        for i in range(1, count + 1):
            dst = out_dir / f"{track}_c{i}.wav"
            if dst.exists():
                print(f"[reuse] {dst.name}")
                continue
            t1 = time.time()
            model.generate_sample(
                textlist=[prompt], name=dst.stem,
                cfg=3.5, ddim_steps=200, outputdir=str(out_dir),
            )
            print(f"[gen] {dst.name}（{time.time()-t1:.0f}s）")
    print(f"[done] 候选在 {out_dir}")


def cmd_finalize(args):
    seg, sr = sf.read(args.candidate)
    seg = seg.astype(np.float32)
    if args.kind == "transition":
        seg = cut_peak(seg, sr, args.cut)
        seg = fade_out(seg, sr, args.fade)
    else:  # ambience：氛围 ~5s（取前段，AudioCaps 事件多在段首）+ 淡出
        seg = seg[: int(args.seconds * sr)]
        seg = fade_out(seg, sr, args.fade)
    dst = Path(args.master)
    dst.parent.mkdir(parents=True, exist_ok=True)
    sf.write(dst, seg, samplerate=sr)
    print(f"[done] {dst}（{len(seg)/sr:.1f}s）")


def main():
    ap = argparse.ArgumentParser(description="AudioFly 环境音生成（ambient-sfx-designer 氛围层）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("jobs", help="批量生成候选到 .tmp/ambient/")
    p1.add_argument("jobs", help="jobs JSON 路径（ambient_tasks.py 产出）")
    p1.add_argument("--seed", type=int, default=None)
    p1.set_defaults(func=cmd_jobs)
    p2 = sub.add_parser("finalize", help="候选裁剪+淡出落母带")
    p2.add_argument("candidate", help="候选 wav（.tmp/ambient/<track>_c<i>.wav）")
    p2.add_argument("master", help="母带 wav（15_声音/<stem>/<block>/<track>.wav）")
    p2.add_argument("--kind", choices=["ambience", "transition"], default="ambience")
    p2.add_argument("--seconds", type=float, default=5.0, help="氛围成品时长（秒），默认 5")
    p2.add_argument("--cut", type=float, default=1.5, help="转场成品时长（秒），默认 1.5")
    p2.add_argument("--fade", type=float, default=2.0, help="末尾淡出（秒），默认 2")
    p2.set_defaults(func=cmd_finalize)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
