---
name: scene-layer-designer
description: |
  推进 SceneLayer 图节点：查询状态 → 按 scene_type 查所需图层并组装提示词/生成图片 → 保存结果（MERGE 兜底建节点+边，写产物与 status）。
  V1 仅实现 background 层；floor/decor/mask 留 V2 TODO。单轮直推到最大门控（图片完成即待审 10）。
  在需要生成场景图层或 SceneLayer 节点需推进时使用。
argument-hint: <scene_id>
arguments:
  - scene_id
allowed-tools: Read, Bash, Write, Edit
---

> **status=-1 = 作废重做**：当 SceneLayer 被 sync 级联重置为 `status=-1` 时（Scene 被编辑），即使 `prompt_path`/`image_path` 已存在，也**必须重新生成并覆盖**（重走 0→1→2）。`-1` 与 `0` 都视为"需生成"起点；`-1` 明确表示有旧产物要覆盖，**禁止因文件已存在而跳过**。

# 场景图层（SceneLayer）

为场景的每个所需图层生成提示词与图片，推进 SceneLayer 节点并绑定 `has_layer` 边（Scene → SceneLayer）。图层组合由 Scene.scene_type 决定。

## 参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| scene_id | 场景节点 ID（snowflake Base62） | 必传 |

## 流程（三段式：查状态 → 完成任务 → 保存结果）

> 本 skill 是 status 的唯一写入点；提示词与图片由子 skill（scene-prompt-assembler / infra-image-generator）纯产出，本 skill 在「保存结果」步统一写入图。

### 1. 查询目标节点状态

通过 `${CLAUDE_SKILL_DIR}/../../scripts/cypher_exec.py` 查询上游 Location/Scene + 已有图层：

```cypher
MATCH (l:Location)-[:has_scene]->(s:Scene {id: '<scene_id>'})
OPTIONAL MATCH (s)-[:has_layer]->(sl:SceneLayer)
RETURN l.name AS loc_name, s.id AS scene_id, s.name AS scene_name,
       s.scene_type AS scene_type, s.status AS scene_status,
       collect(sl) AS layers;
```

- **前驱校验**：`scene_status >= 1`（Scene 已由 scene-designer 设计），否则停止并提示先推进场景设计。
- **所需图层**（按 scene_type 查表，静态映射，不进图）：

  | scene_type | 所需图层（layer_type） |
  |-----------|----------------------|
  | `dialogue` | `background` |
  | `functional` | `background`, `floor` |
  | `combat` | `background`, `floor`, `decor`, `mask` |
  | `ui` | `background` |

- **目标节点判定**：对比所需图层与已有图层（layers）；为缺失的 layer_type 生成新 snowflake id：
  ```bash
  python "${CLAUDE_SKILL_DIR}/../../scripts/snowflake_base62.py" -n <缺几个> -q
  ```
  已有图层按 status 决定推进起点（`-1`/`0` 需重做，`1` 已有提示词，`10` 待审不可推进，`11` 已完成）。
- 记录 `loc_name`（产物路径用）。

> **V1 限制**：当前仅实现 `background` 层。命中 `floor`/`decor`/`mask` 时记日志「TODO：V2 实现」并跳过，不生成产物、不建节点。

### 2. 完成任务

按当前 status 单轮直推到图片完成（待审 10），逐个所需图层推进（V1 仅 background）：

#### 组装提示词

使用 Skill 工具调用 `scene-prompt-assembler`，参数 `background '<data_json>'`：

```json
{
  "scene": {
    "scene_type": "<scene_type>", "name": "<scene_name>",
    "time_of_day": "...", "weather": "...", "atmosphere": "...",
    "composition": "...", "lighting": "...",
    "color_direction": "..."
  },
  "location": {"name": "<loc_name>"},
  "node": {"id": "<layer_id>"},
  "output_path": "07_场景美术/<loc_name>/<scene_name>/background/prompt.md"
}
```

scene 字段的值从步骤 1 查询的 Scene 节点属性读取。在 data 中声明 `output_path`；scene-prompt-assembler 写入该路径并返回 `PROMPT_PATH`。

#### 生成图片

使用 Skill 工具调用 `infra-image-generator`，参数 `<PROMPT_PATH> <OUTPUT_PATH>`（文生图，无参考图）：

`OUTPUT_PATH = 07_场景美术/<loc_name>/<scene_name>/background.png`。infra-image-generator 生成图片并返回路径 `IMAGE_PATH`。

### 3. 保存结果（MERGE 兜底 + 写产物 + 推进 status）

对每个 background 图层一次性写入（节点不存在则兜底创建）：

```cypher
// 兜底建节点+边（ON CREATE 仅初始化，不覆盖已推进的 status）
MERGE (sl:SceneLayer {id: '<layer_id>'})
  ON CREATE SET sl.status = 0, sl.layer_type = 'background';
MATCH (s:Scene {id: '<scene_id>'}), (sl:SceneLayer {id: '<layer_id>'})
MERGE (s)-[r:has_layer]->(sl) SET r.sync = true;
// 写产物 + 推进 status
MATCH (sl:SceneLayer {id: '<layer_id>'})
SET sl.name = '<scene_name>-背景',
    sl.prompt_path = '<PROMPT_PATH>',
    sl.image_path  = '<IMAGE_PATH>',
    sl.status = 10;                      // 图片完成即待审（直写，不经 submit）
```

**status 写入**：固定 `10`（待审，等待 dashboard 审批）。SceneLayer 是终端节点，无下游。

## 参考文档

- 提示词组装：[scene-prompt-assembler](../scene-prompt-assembler/SKILL.md) 模式A
- 图片生成：[infra-image-generator](../infra-image-generator/SKILL.md)
- [场景美术 Schema](00_init/Schema/场景美术.md) — scene_type 与所需图层映射
