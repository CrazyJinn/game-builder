---
name: char-stand-designer
description: |
  推进 StandingIllustration 图节点：查询状态 → 组装提示词/生成图片 → 保存结果（MERGE 兜底建节点+边，写产物与 status）。
  入参 stand_id——只推进指定的单个立绘变体，由 plot-design 按 depicts 引用按需触发。变体需求由 section-voice-publisher 配音判断期选绘兜底建缺口（LLM 为 say 行按台词氛围选立绘，池中无贴切变体时经 portrait_binder apply 建 status=0 缺口节点并写 description 变体氛围），本 skill 逐个交付生成，不做角色级批量备货、不按角色优先级补全数量。
argument-hint: <stand_id>
arguments:
  - stand_id
allowed-tools: Read, Bash, Write, Edit
---

> **status=-1 = 作废重做**：当 StandingIllustration 被 sync 级联重置为 `status=-1` 时，即使 `prompt_path`/`image_path` 已存在，也**必须重新生成并覆盖**（重走 0→1→2）。`-1` 与 `0` 都视为"需生成"起点；`-1` 明确表示有旧产物要覆盖，**禁止因文件已存在而跳过**。

# 立绘变体（StandingIllustration）

从 IllusDesign 拓展出不同表情、动作的单张立绘，表情和动作参考 LanguageStyle 生成。

**按需单变体模式**（stand_id）：只推进指定的那一个 StandingIllustration（通常由 `section-voice-publisher` 配音判断期选绘兜底建的 `status=0` 缺口节点，经 `plot-design` 按 depicts 引用触发）。**变体需求来自剧本**——选绘 LLM 在配音判断期为 say 行按台词氛围选立绘，判定池中无贴切变体时兜底建缺口（节点带 `description` 变体氛围）；本 skill 逐个交付生成，**不做角色级批量备货、不按角色优先级（P0/P1/P2）补全数量**，避免为未被剧情引用的变体浪费出图 API。

## 参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| stand_id | 单个立绘变体 ID（StandingIllustration 节点 id） | 必传 |

## 流程（三段式：查状态 → 完成任务 → 保存结果）

> 本 skill 是 status 的唯一写入点；提示词与图片由子 skill 纯产出，本 skill 在「保存结果」步统一写入图。

### 1. 查询目标节点状态

通过 `${CLAUDE_SKILL_DIR}/../../scripts/cypher_exec.py` 查询。

```cypher
MATCH (stand:StandingIllustration {id:'<stand_id>'})
MATCH (illus:IllusDesign)-[:expands_to]->(stand)
MATCH (voice:LanguageStyle)-[:ref_style]->(stand)
MATCH (ch:Character)-[:has_voice_style]->(voice)
OPTIONAL MATCH (illus)-[:outfit_for]->(cos:CostumeStyle)
RETURN ch.name AS char_name, ch.id AS char_id,
       voice.id AS voice_id, voice.emotion_patterns AS emotion_patterns,
       illus.id AS illus_id, illus.image_path AS illus_image, illus.status AS illus_status,
       cos.name AS cos_name,
       stand.id AS stand_id, stand.variant_label AS variant_label, stand.status AS status,
       stand.eye AS eye, stand.brow AS brow, stand.mouth AS mouth,
       stand.head_angle AS head_angle, stand.hand AS hand, stand.foot AS foot,
       stand.description AS description
```

- **前驱校验**：`illus_status = 11`（IllusDesign 已批准），否则停止并提示上游未就绪（由 `plot-design` 委派 `char-design` 推进 IllusDesign 后再来）。
- **节点已存在**（由 `section-voice-publisher` 的选绘 apply 兜底建为 `status=0`，`description` 已含变体氛围）：直接按 status 决定推进起点。`variant_label` 已在节点上；若 `eye`/`brow`/`mouth`/`head_angle`/`hand`/`foot` 标签缺失，按 `variant_label` 与 `description` 语义推导并在保存步补写。
- 本 skill **只处理这一个 stand**，不枚举其他变体、不补全数量。

> 查不到（stand_id 不存在 / 缺上游 `expands_to` 或 `ref_style`）→ 报告并停止。

### 2. 完成任务

推进这一个变体：

#### 组装提示词

使用 Skill 工具调用 `char-prompt-assembler`，参数 `StandingIllustration '<data_json>'`：

```json
{
  "stand": { "description":"<stand.description——变体氛围，出图的首要依据>", "tags": {"variant_label":"...","eye":"...","brow":"...","mouth":"...","head_angle":"...","hand":"...","foot":"..."} },
  "voice": { "emotion_patterns":"...", "description":"..." },
  "character": { "id":"<char_id>", "name":"<char_name>" },
  "node": { "id":"<stand_id>" },
  "output_path": "06_角色美术/<char_name>/<cos_name>/立绘/<variant_label>.md"
}
```

char-prompt-assembler 组装 prompt 文件到 `06_角色美术/<char_name>/<cos_name>/立绘/<variant_label>.md`（与图片同目录同名）并返回路径 `PROMPT_PATH`。

#### 生成图片

使用 Skill 工具调用 `infra-image-generator`，参数 `<PROMPT_PATH> <OUTPUT_PATH> <illus_image>`（图生图，以 IllusDesign 图片为参考）：

`OUTPUT_PATH = 06_角色美术/<char_name>/<cos_name>/立绘/<variant_label>.png`。infra-image-generator 返回路径 `IMAGE_PATH`。

### 3. 保存结果（MERGE 兜底 + 写产物 + 推进 status）

一次性写入（节点通常已存在，MERGE 幂等）：

```cypher
MERGE (stand:StandingIllustration {id: '<stand_id>'})
  ON CREATE SET stand.status = 0, stand.variant_label = '<variant_label>',
                stand.eye = '<...>', stand.brow = '<...>', stand.mouth = '<...>',
                stand.head_angle = '<...>', stand.hand = '<...>', stand.foot = '<...>';
MATCH (illus:IllusDesign {id: '<illus_id>'}), (stand:StandingIllustration {id: '<stand_id>'})
MERGE (illus)-[r:expands_to]->(stand) SET r.sync = true, r.variant_label = '<variant_label>';
MATCH (voice:LanguageStyle {id: '<voice_id>'}), (stand:StandingIllustration {id: '<stand_id>'})
MERGE (voice)-[r:ref_style]->(stand) SET r.sync = true;
MATCH (stand:StandingIllustration {id: '<stand_id>'})
SET stand.prompt_path = '<PROMPT_PATH>',
    stand.image_path  = '<IMAGE_PATH>',
    stand.status = 10;                      // 图片完成即待审（直写，不经 submit）
```

**status 写入**：固定 `10`（待审）。StandingIllustration 是终端节点，无下游。

## 参考文档

- 提示词组装：[char-prompt-assembler](../char-prompt-assembler/SKILL.md) Mode C
- 图片生成：[infra-image-generator](../infra-image-generator/SKILL.md)
- 按需触发方：[plot-design](../../agents/plot-design.md) agent（按 depicts 引用传 stand_id）
