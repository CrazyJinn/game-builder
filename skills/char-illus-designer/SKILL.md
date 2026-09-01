---
name: char-illus-designer
description: |
  推进 IllusDesign 图节点：查询状态 → 组装提示词/生成图片 → 保存结果（MERGE 兜底建节点+边，写产物与 status）。
  每组 (DesignSheet, CostumeStyle) 对应一个节点，单轮直推到最大门控（图片完成即待审 10）。
  在需要生成立绘设计图或 IllusDesign 节点需推进时使用。
argument-hint: <char_id>
arguments:
  - char_id
allowed-tools: Read, Bash, Write, Edit
---

> **status=-1 = 作废重做**：当 IllusDesign 被 sync 级联重置为 `status=-1` 时，即使 `prompt_path`/`image_path` 已存在，也**必须重新生成并覆盖**（重走 0→1→2）。`-1` 与 `0` 都视为"需生成"起点；`-1` 明确表示有旧产物要覆盖，**禁止因文件已存在而跳过**。

# 立绘设计图（IllusDesign）

角色穿着特定着装的三视图设计图，由 DesignSheet（外貌基础）和 CostumeStyle（着装方案）共同决定。每组 (DesignSheet, CostumeStyle) 对应一个 IllusDesign。

## 参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| char_id | 角色 ID（snowflake Base62） | 必传 |

## 流程（三段式：查状态 → 完成任务 → 保存结果）

> 本 skill 是 status 的唯一写入点；提示词与图片由子 skill 纯产出，本 skill 在「保存结果」步统一写入图。对每套装扮（CostumeStyle）各推进一个 IllusDesign。

### 1. 查询目标节点状态

通过 `${CLAUDE_SKILL_DIR}/../../scripts/cypher_exec.py` 查询前驱 + 各 (DesignSheet, CostumeStyle) 组对应的 IllusDesign 是否已存在：

```cypher
MATCH (ch:Character {id: '<char_id>'})
MATCH (ch)-[:has_appearance]->(ap:AppearanceStyle)-[:produces]->(ds:DesignSheet)
MATCH (ch)-[:has_costume]->(cos:CostumeStyle)
OPTIONAL MATCH (ds)-[:produces]->(illus:IllusDesign)<-[:outfit_for]-(cos)
RETURN ch.name AS char_name,
       ap.height_cm AS height_cm,
       ds.id AS ds_id, ds.status AS ds_status, ds.image_path AS ds_image,
       cos.id AS cos_id, cos.name AS cos_name, cos.status AS cos_status,
       illus.id AS illus_id, illus.status AS illus_status, illus.adaptation_notes AS notes
```

- **前驱校验**：`ds_status = 11`（DesignSheet 已批准）且 `cos_status = 1`（CostumeStyle 已完成，无审批），否则停止并提示先推进上游。
- **目标节点判定**（每组）：若 `illus_id` 为空 → 生成新 snowflake id 作为 `ILLUS_ID`，本次将新建；若存在 → `ILLUS_ID = illus_id`，按 status 决定推进起点。
- 记录 `ds_image`（图生图参考图）、`cos_name`（产物路径用）。

### 2. 完成任务

对每组 (ds, cos) 推进：

#### 组装提示词

使用 Skill 工具调用 `char-prompt-assembler`，参数 `IllusDesign '<data_json>'`：

```json
{
  "costume": { "tags": {"outfit_style":"...","garment":"...","footwear":"...","accessory_type":"..."} },
  "illus": { "adaptation_notes": "<根据着装补充需求填写，如'左臂夹持文件夹'；无则空>" },
  "character": { "id":"<char_id>", "name":"<char_name>" },
  "node": { "id":"<ILLUS_ID>" },
  "output_path": "06_角色美术/<char_name>/<cos_name>/prompt.md"
}
```

在 data 中声明 `output_path = 06_角色美术/<char_name>/<cos_name>/prompt.md`；char-prompt-assembler 写入该路径并返回 `PROMPT_PATH`。

#### 生成图片

使用 Skill 工具调用 `infra-image-generator`，参数 `<PROMPT_PATH> <OUTPUT_PATH> <ds_image>`（图生图，以 DesignSheet 图片为参考）：

`OUTPUT_PATH = 06_角色美术/<char_name>/<cos_name>/立绘设计图.png`。infra-image-generator 返回路径 `IMAGE_PATH`。

### 3. 保存结果（MERGE 兜底 + 写产物 + 推进 status）

**显示缩放推算（display_scale）**：立绘按身高缩放显示（1.0=占满立绘层满高）。从第 1 步查回的 `height_cm` 推算：`display_scale = round(height_cm / 200, 4)`（参考身高 200cm，与 `99_game/tools/init_portrait_scales.py` 的 `REF_HEIGHT_DEFAULT` 一致）。`height_cm` 缺失则 `display_scale = null`（立绘按满高显示）。

对每组一次性写入（节点不存在则兜底创建）：

```cypher
MERGE (illus:IllusDesign {id: '<ILLUS_ID>'})
  ON CREATE SET illus.status = 0;
MATCH (ds:DesignSheet {id: '<ds_id>'}), (illus:IllusDesign {id: '<ILLUS_ID>'})
MERGE (ds)-[r:produces]->(illus) SET r.sync = true;
MATCH (cos:CostumeStyle {id: '<cos_id>'}), (illus:IllusDesign {id: '<ILLUS_ID>'})
MERGE (cos)-[r:outfit_for]->(illus) SET r.sync = true;
MATCH (illus:IllusDesign {id: '<ILLUS_ID>'})
SET illus.prompt_path = '<PROMPT_PATH>',
    illus.image_path  = '<IMAGE_PATH>',
    illus.adaptation_notes = '<notes>',        // 若有补充
    illus.display_scale = <scale 或 null>,     // = round(height_cm/200, 4)；height_cm 缺失则 null
    illus.status = 10;                         // 图片完成即待审（直写，不经 submit）
```

**status 写入**：固定 `10`（待审，等待 dashboard 审批）。

## 参考文档

- 提示词组装：[char-prompt-assembler](../char-prompt-assembler/SKILL.md) Mode B
- 图片生成：[infra-image-generator](../infra-image-generator/SKILL.md)