---
name: char-design-sheet
description: |
  推进 DesignSheet 图节点：查询状态 → 组装提示词/生成图片 → 保存结果（MERGE 兜底建节点+边，写产物与 status）。
  单轮直推到最大门控（图片完成即待审 10）。在需要生成角色设计图或 DesignSheet 节点需推进时使用。
argument-hint: <char_id>
arguments:
  - char_id
allowed-tools: Read, Bash, Write, Edit
---

> **status=-1 = 作废重做**：当 DesignSheet 被 sync 级联重置为 `status=-1` 时，即使 `prompt_path`/`image_path` 已存在，也**必须重新生成并覆盖**（重走 0→1→2）。`-1` 与 `0` 都视为"需生成"起点；`-1` 明确表示有旧产物要覆盖，**禁止因文件已存在而跳过**。

# 设计图（DesignSheet）

每个角色一个 DesignSheet 节点，对应三视图设计稿。

## 参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| char_id | 角色 ID（snowflake Base62） | 必传 |

## 流程（三段式：查状态 → 完成任务 → 保存结果）

> 本 skill 是 status 的唯一写入点；提示词与图片由子 skill（char-prompt-assembler / infra-image-generator）纯产出，本 skill 在「保存结果」步统一写入图。

### 1. 查询目标节点状态

通过 `${CLAUDE_SKILL_DIR}/../../scripts/cypher_exec.py` 查询前驱 + 目标 DesignSheet 是否已存在：

```cypher
MATCH (ch:Character {id: '<char_id>'})-[:has_appearance]->(app:AppearanceStyle)
OPTIONAL MATCH (app)-[:produces]->(ds:DesignSheet)
RETURN ch.name AS char_name, app.id AS app_id, app.status AS app_status,
       ds.id AS ds_id, ds.status AS ds_status
```

- **前驱校验**：`app_status >= 1`（外貌已由 char-concept-designer 设计），否则停止并提示先推进概念设计。
- **目标节点判定**：
  - 若 `ds_id` 为空（DesignSheet 不存在）→ 生成新 snowflake id 作为 `DESIGN_ID`，本次将新建：
    ```bash
    python "${CLAUDE_SKILL_DIR}/../../scripts/snowflake_base62.py" -n 1 -q
    ```
  - 若 `ds_id` 存在 → `DESIGN_ID = ds_id`；按 `ds_status` 决定推进起点（`-1`/`0` 需重做，`1` 已有提示词，`10` 待审不可推进，`11` 已完成）。
- 记录 `char_name`（产物路径用）与 `app_id`（保存步建 `produces` 边用）。

### 2. 完成任务

按当前 status 单轮直推到图片完成（待审 10）：

#### 组装提示词

使用 Skill 工具调用 `char-prompt-assembler`，参数 `DesignSheet '<data_json>'`：

```json
{
  "appearance": { "tags": {...}, "appearance":"...","visual_tone":"...","first_impression":"..." },
  "character": { "id":"<char_id>", "name":"<char_name>", "color_direction":"..." },
  "node": { "id":"<DESIGN_ID>" },
  "output_path": "06_角色美术/<char_name>/prompt.md"
}
```

在 data 中声明 `output_path = 06_角色美术/<char_name>/prompt.md`；char-prompt-assembler 写入该路径并返回 `PROMPT_PATH`。

#### 生成图片

使用 Skill 工具调用 `infra-image-generator`，参数 `<PROMPT_PATH> <OUTPUT_PATH>`（文生图，无参考图）：

`OUTPUT_PATH = 06_角色美术/<char_name>/设计图.png`。infra-image-generator 生成图片并返回路径 `IMAGE_PATH`。

### 3. 保存结果（MERGE 兜底 + 写产物 + 推进 status）

一次性写入（节点不存在则兜底创建）：

```cypher
// 兜底建节点+边（ON CREATE 仅初始化，不覆盖已推进的 status）
MERGE (ds:DesignSheet {id: '<DESIGN_ID>'})
  ON CREATE SET ds.status = 0;
MATCH (app:AppearanceStyle {id: '<app_id>'}), (ds:DesignSheet {id: '<DESIGN_ID>'})
MERGE (app)-[r:produces]->(ds) SET r.sync = true;
// 写产物 + 推进 status
MATCH (ds:DesignSheet {id: '<DESIGN_ID>'})
SET ds.prompt_path = '<PROMPT_PATH>',
    ds.image_path  = '<IMAGE_PATH>',
    ds.status = 10;                      // 图片完成即待审（直写，不经 submit）
```

**status 写入**：固定 `10`（待审，等待 dashboard 审批）。

## 参考文档

- 提示词组装：[char-prompt-assembler](../char-prompt-assembler/SKILL.md) Mode A
- 图片生成：[infra-image-generator](../infra-image-generator/SKILL.md)
