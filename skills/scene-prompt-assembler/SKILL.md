---
name: scene-prompt-assembler
description: |
  从调用方传入的场景数据（Scene 字段 + Location 名）组装场景图层提示词，派生为 prompt 文件并返回其路径。
  按 layer_type 分模式（background/floor/decor/mask）；当前实现 background，其余为 V2 TODO。
  纯产出层：不读写图数据库、不写 status，所有数据由调用方通过 data 参数提供。
  在需要为场景图层节点组装提示词或被其他 skill 调用时使用。
argument-hint: <layer_type> <data_json>
arguments:
  - layer_type
  - data
allowed-tools: Read, Bash, Write, Edit
---

> **纯产出层**：本 skill 只负责组装 prompt 文件并**返回文件路径**，**不读写图数据库、不写 status**。节点 `prompt_path` 字段与 `status` 由调用方（scene-layer-designer）在「保存结果」步统一写入。`status=-1`（作废重做）时调用方会再次调用本 skill 覆盖旧 prompt 文件——本 skill 每次被调用都重新组装并覆盖。

# 场景图层提示词组装

从调用方传入的**Scene 字段 + Location 名**组装场景图层提示词，派生为 **prompt 文件**并返回文件路径。不读写图数据库——所有数据由调用方通过 `data` 参数传入。

## 核心转换：Scene 字段 → 自然语言场景描述

Scene 的视觉维度以**自由文本 + 标签**存储。组装时将各维度展开为**自然语言描述句**，按 reference 模板的 `用途→主体(空间)→环境(远中近景)→光影→风格` 结构组织成完整 prompt。

- `composition`（远/中/近景分层）→ 远中近景三段连贯描述
- `lighting`（主光源+色温+环境光）→ 光影段
- `atmosphere` / `time_of_day` / `weather` → 主体与环境段的氛围、时间、天气

## 编写原则

- **用途开头**：提示词开头声明图片用途（如"游戏对话背景图"），让模型理解生成目标
- **自然语言优先**：用连贯描述句，而非逗号关键词
- **主体 → 环境 → 光影 → 风格**：先场景空间，再远中近景，再光影，画风放末尾
- **场景无角色**：末尾须含「无角色」（场景图不出现角色立绘，与角色 #00FF00 背景互斥；已并入风格收尾串）
- **硬约束收尾**：末尾风格词以 `00_init/美术风格.md`「提示词硬约束」节的**风格收尾串**为准——本文件与模板**不写死该串**，每次组装从源头读取并原样拼接；凭记忆写旧串即为漂移 bug
- **只提取不创作**：内容来自 data 参数（Scene 字段）和 `00_init/美术风格.md`，不臆造

## 输出流程

1. 解析 data，提取 `scene.*` 字段、`location.name`、`node.id`，以及调用方声明的 `output_path`
2. 从 `00_init/美术风格.md` 读取「场景美术风格」块（基础定位、渲染、色彩、提示词硬约束）——风格收尾串以其中「提示词硬约束」为准
3. 按 layer_type 对应模式组装 markdown prompt（见下方各模式 + reference 模板）
4. 用 **Write 工具**写 prompt 文件到调用方在 data 中声明的 `output_path`（不经 shell，markdown 无损；目录不存在时 Write 自动创建）。**路径由调用方决定，assembler 透传，不自行拼接**
5. **返回 prompt 文件路径**给调用方（由调用方写入节点 `prompt_path` 字段）

> prompt 文件路径由调用方在 `output_path` 入参中声明，assembler 透传使用。

## 模式A：background（文生图）✅ V1 实现

为场景背景图层组装提示词。完整的远中近景场景图，是 dialogue/ui 场景的唯一图层，也是 functional/combat 场景的最底层。详细维度映射与各 scene_type 模板见 [references/template-场景提示词.md](references/template-场景提示词.md)。

**data 参数结构**：
```json
{
  "scene": {
    "scene_type": "dialogue", "name": "...", "time_of_day": "...", "weather": "...",
    "atmosphere": "...", "composition": "...", "lighting": "...",
    "color_direction": "..."
  },
  "location": {"name": "..."},
  "node": {"id": "<scenelayer_node_id>"},
  "output_path": "07_场景美术/<loc_name>/<scene_name>/background/prompt.md"
}
```

组装（按 `用途→主体→环境→光影→风格`）：
1. **用途**：按 `scene_type` 取用途前缀（dialogue→"游戏对话背景图"，functional/combat→"游戏场景背景图"，ui→"游戏UI背景"）
2. **主体**：`location.name` + `scene.name` 点明场景空间，接 `atmosphere` 氛围句、`time_of_day`/`weather` 时间天气
3. **环境**：展开 `composition` 的远/中/近景为三段连贯描述
4. **光影**：展开 `lighting`（主光源方向+色温+环境光）
5. **风格**：`color_direction`（如有），末尾拼接美术风格.md「提示词硬约束」的风格收尾串（含「无角色」，动态读取不写死；风格全局统一，无 per-scene 风格标签）

## 模式B/C/D：floor / decor / mask 🚧 V2 TODO

- **floor（地面层）**：俯视角地表纹理提示词，色调描述为主
- **decor（陈设层）**：9宫格/4宫格 JSON（仅色调），见 [references/template-图层JSON.md](references/template-图层JSON.md)
- **mask（遮罩层）**：独立前景遮挡图，透明通道

> 当前项目为对话游戏，仅需 background 层。其余 layer_type 的模式留待 V2 实现；scene-layer-designer 在 V1 命中这些 layer_type 时记日志跳过。

## 参考文档

- [场景提示词模板](references/template-场景提示词.md) — 用途→主体→环境→光影→风格 结构、各 scene_type 模板、检查清单（模式A）
- [图层JSON模板](references/template-图层JSON.md) — 装饰层/遮罩层 JSON 格式（模式C，V2）

> 模板的**结构**有效，但数据源以本文件各模式的 data 结构（Scene 字段）为准。
