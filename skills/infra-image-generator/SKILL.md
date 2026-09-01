---
name: infra-image-generator
description: |
  OfoxAI Images API 调用层（纯产出）。读取 prompt 文件、调用 API 生成图片并返回图片路径。
  文生图（无参考图）/ 图生图（带参考图），由是否有 ref_image_path 决定。
  不读写图数据库、不写 status。在需要生成美术图片或被其他 skill 调用时使用。
argument-hint: <prompt_path> <output_path> [<ref_image_path>]
arguments:
  - prompt_path
  - output_path
  - ref_image_path
allowed-tools: Read, Bash, Write, Edit
---

> **纯产出层**：本 skill 只负责读取 prompt 文件、调用 API 生成图片并**返回图片路径**，**不读写图数据库、不写 status**。节点 `image_path` 字段与 `status` 由调用方（生产 skill）在「保存结果」步统一写入。`status=-1`（作废重做）时调用方会再次调用本 skill 重新生成并覆盖旧图片——本 skill 每次被调用都重新生成。

# OfoxAI 图片生成

读取 prompt 文件，调用 API 生成图片，返回图片路径。**不组装提示词、不读取风格文件、不查目标节点。**

脚本：`${CLAUDE_SKILL_DIR}/scripts/ofoxai_api.py`

---

## API Key

脚本自动从**工作目录**向上搜索 `settings.json`，读取 `ofox_api_key` 字段。无需手动传参。

确保工作目录或其上级目录存在 `settings.json`：
```json
{ "ofox_api_key": "sk-of-xxxxx" }
```

---

## 流程

### 1. 读取 prompt

从调用方传入的 `prompt_path`（参数 `$0`）读取 prompt 文件内容。

### 2. 确定生成方式

由是否传入 `ref_image_path`（参数 `$2`）决定：

| 场景 | ref_image_path | 生成方式 |
|------|----------------|---------|
| 文生图（如 DesignSheet） | 未传 | 纯文本生成 |
| 图生图（如 IllusDesign / StandingIllustration） | 传入 | 以参考图为底图 |

参考图路径由调用方（生产 skill）从已存在的前驱节点查得后传入。

### 3. 生成图片

> **`--size` 判定优先级**：① 若 prompt 文本中写明分辨率（如「分辨率 1024×1536」），以其为准；② 否则按生成方式默认——文生图 1024x1024，图生图沿用参考图比例或 1024x1024；③ 仍无法确定时向用户确认。

#### 文生图（无参考图）

prompt 经管道直送（支持多行 markdown，不经 shell 字面量）：

```bash
cat "<prompt_path>" \
  | python "${CLAUDE_SKILL_DIR}/scripts/ofoxai_api.py" submit --prompt-stdin \
      --size 1024x1024 -o "<output_path>"
```

#### 图生图（带参考图）

参考图 `--image` 是短路径，走命令行参数：

```bash
cat "<prompt_path>" \
  | python "${CLAUDE_SKILL_DIR}/scripts/ofoxai_api.py" submit --prompt-stdin \
      --image "<ref_image_path>" --size 1024x1024 -o "<output_path>"
```

### 4. 返回图片路径

将 `output_path`（生成的图片路径）返回给调用方，由调用方写入节点 `image_path` 字段。

---

## 脚本参数

### submit

```bash
python "${CLAUDE_SKILL_DIR}/scripts/ofoxai_api.py submit "<prompt>" [options]
```

| 参数 | 必填 | 说明 |
|------|:----:|------|
| prompt | Y | 图像描述文本（从 prompt 文件读取，经 `--prompt-stdin` 管道传入） |
| `--model` | N | 默认 `openai/gpt-image-2` |
| `--size` | Y | 输出尺寸，gpt-image-2 最大边 3840px，两边 16 的倍数 |
| `--quality` | - | **已强制为 `low`** |
| `--n` | N | 生成数量，默认 1 |
| `--image` | N | 参考图路径，可多次指定 |
| `-o, --output` | N | 直接保存路径（跳过 wait） |

### wait / download

```bash
python "${CLAUDE_SKILL_DIR}/scripts/ofoxai_api.py wait '<json|file>' ./output.png
python "${CLAUDE_SKILL_DIR}/scripts/ofoxai_api.py download <url> ./output.png
```

## 错误处理

| HTTP 状态码 | 处理 |
|-------------|------|
| 400 | 检查参数格式和尺寸 |
| 401 | 检查 API Key |
| 402 | 余额不足，充值后重试 |
| 429 | 等待后重试 |
| 500 | 重试 |

## 参考文档

- [完整 API 参数](references/api-reference.md)
