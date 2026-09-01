"""声音脚本路径配置：模型权重，统一读 settings.json/env。

本模块位于 .claude/skills/section-voice-publisher/scripts/，被同目录的 voice_clone_runner
`from paths import` 引用。所有脚本不硬编码 D:/。
优先级：env var > settings.json（项目根，gitignore），无默认值——未配置即报错。

迁机器：改 settings.json 的 voice.model_dir（或设 VOICE_MODEL_DIR 环境变量）即可，不动代码。
"""
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))  # .claude/skills/section-voice-publisher/scripts/


def _find_project_root(start: str) -> str:
    """向上搜索项目根（含 settings.json 与 .claude/scripts/cypher_exec.py 的目录），
    不依赖固定层级——脚本再搬迁也不碎。"""
    cur = start
    while True:
        if os.path.exists(os.path.join(cur, "settings.json")) and os.path.isdir(
            os.path.join(cur, ".claude", "scripts")
        ):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            raise RuntimeError(f"未找到项目根（从 {start} 向上搜索失败）")
        cur = parent


_PROJECT_ROOT = _find_project_root(_HERE)


# 项目根（manifest / 图字段里的产物路径惯例为项目根相对，正斜杠分隔）
PROJECT_ROOT = _PROJECT_ROOT


def to_abs(p: str) -> str:
    """项目根相对路径 → 绝对路径（已是绝对路径则原样返回）。"""
    return p if os.path.isabs(p) else os.path.join(PROJECT_ROOT, p)


def to_rel(p: str) -> str:
    """绝对路径 → 项目根相对路径（统一正斜杠，manifest/图字段惯例）。"""
    return os.path.relpath(p, PROJECT_ROOT).replace(os.sep, "/")


def _read_voice_settings() -> dict:
    """读项目根 settings.json 的 voice 节（gitignore，可选）。"""
    p = os.path.join(_PROJECT_ROOT, "settings.json")
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f).get("voice", {})
        except Exception:
            pass
    return {}


_voice = _read_voice_settings()

# 模型权重根（Qwen VoiceDesign/Base 都在这下）。
# 无默认值：未配置即报错（settings.json voice.model_dir 或 VOICE_MODEL_DIR 环境变量）。
_model_dir = os.environ.get("VOICE_MODEL_DIR") or _voice.get("model_dir")
if not _model_dir:
    raise RuntimeError(
        "未配置模型目录：在项目根 settings.json 设 voice.model_dir 或设 VOICE_MODEL_DIR 环境变量"
    )
MODEL_DIR = _model_dir
QWEN_VOICE_DESIGN = os.path.join(MODEL_DIR, "Qwen3-TTS-12Hz-1.7B-VoiceDesign")
QWEN_BASE = os.path.join(MODEL_DIR, "Qwen3-TTS-12Hz-1.7B-Base")  # Voice Clone（多候选试听 + 逐句配音：audition / publish）
