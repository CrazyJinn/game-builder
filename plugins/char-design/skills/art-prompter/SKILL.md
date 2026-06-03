---
name: art-prompter
description: |
  根据图节点数据生成 AI 绘图提示词。三种模式：DesignSheet（三视图提示词）、IllusDesign（立绘设计提示词）、StandingIllustration（立绘变体提示词）。
  通用格式，不针对特定模型。
  触发条件：(1) 生成设计图提示词 (2) 生成立绘设计提示词 (3) 生成立绘变体提示词
  前置：concept-designer（数据节点 status ≥ 1），neo4j-helper（读取数据、更新图节点）。
allowed-tools: Read, Bash, Write, Edit
---

# 美术提示词生成

根据图节点数据，生成通用 AI 绘图提示词。按目标节点类型分为三种模式。

## 编写原则

自然语言优先，按 **主体→细节→风格** 组织，不使用负面提示词。详细规则和模板见 [references/](references/)。

提示词语言：**中文**。

---

## 模式A：DesignSheet 提示词

**触发**：DesignSheet 节点 status=0 时，由 agent 传入 DesignSheet ID。

### A1. 读取上游数据

通过 neo4j-helper（schema_path=`schema/02_角色美术.md`）查询：

```cypher
// 查询 DesignSheet 的上游数据
MATCH (app:AppearanceStyle)-[:produces]->(ds:DesignSheet {id: $design_id})
RETURN app, ds

// 查询关联的着装信息
MATCH (ch:Character)-[:has_appearance]->(app:AppearanceStyle)-[:produces]->(ds:DesignSheet {id: $design_id})
MATCH (ch)-[:has_costume]->(cos:CostumeStyle)
RETURN cos
```

同时从 `00_init/美术风格.md` 文件读取全局美术风格参数（画风、头身比、渲染风格等）。

前置检查：AppearanceStyle.status 必须为 1（已完成），否则跳过。

信息来源：
- AppearanceStyle 节点：appearance, color_direction, shape_language, visual_tone 等字段
- `00_init/美术风格.md`：全局美术风格（画风、头身比、渲染风格、设计图/立绘规格等）
- CostumeStyle 节点：default_outfit, accessories（可选参考）

也可从 `05_角色设计/<type>/<char_id>/美术设定.md` 文件中提取，与图节点数据交叉验证。

### A2. 生成提示词

按 [template-设计图提示词.md](references/template-设计图提示词.md) 模板生成三视图提示词。

写入 `06_角色美术/<char_id>/设计图提示词.md`。

### A3. 更新图节点

通过 neo4j-helper 更新 DesignSheet 节点：

> "更新 DesignSheet 节点（id 为 <design_id>），设置 prompt_path 为 '06_角色美术/<char_id>/设计图提示词.md'，status 设为 1"

---

## 模式B：IllusDesign 提示词

**触发**：IllusDesign 节点 status=0 时，由 agent 传入 IllusDesign ID。

### B1. 读取上游数据

通过 neo4j-helper 查询 IllusDesign 的三个上游：

```cypher
// 查询 IllusDesign 的所有上游
MATCH (ds:DesignSheet)-[:produces]->(illus:IllusDesign {id: $illus_id})
MATCH (cos:CostumeStyle)-[:outfit_for]->(illus)
MATCH (s:Scene)-[:context_for]->(illus)
RETURN ds, cos, s, illus
```

前置检查：DesignSheet.status 必须为 2（图片已生成），否则跳过。

信息来源：
- DesignSheet：image_path（基础外貌参考图）
- CostumeStyle：default_outfit, accessories（默认着装）
- Scene：name, description（环境上下文，如"雪山"→羽绒服适配）

### B2. 生成提示词

综合三个上游数据，生成场景适配的立绘设计提示词。包含：
- 基于设计图的外貌基础（不重复描述，作为参考图使用）
- 根据场景对默认着装的适配（adaptation_notes）
- 场景环境带来的视觉变化

写入 `06_角色美术/<char_id>/立绘设计/<scene_id>/提示词.md`。

### B3. 更新图节点

通过 neo4j-helper 更新 IllusDesign 节点：

> "更新 IllusDesign 节点（id 为 <illus_id>），设置 prompt_path 为 '06_角色美术/<char_id>/立绘设计/<scene_id>/提示词.md'，adaptation_notes 为 '<适配说明>'，status 设为 1"

---

## 模式C：StandingIllustration 提示词

**触发**：StandingIllustration 节点 status=0 时，由 agent 传入 StandingIllustration ID。

### C1. 读取上游数据

通过 neo4j-helper 查询：

```cypher
// 查询 StandingIllustration 的上游
MATCH (illus:IllusDesign)-[r:expands_to]->(stand:StandingIllustration {id: $stand_id})
MATCH (voice:LanguageStyle)-[:ref_style]->(stand)
RETURN illus, stand, voice, r.variant_label
```

前置检查：IllusDesign.status 必须为 2，否则跳过。

信息来源：
- IllusDesign：image_path（参考图）
- LanguageStyle：description（语言风格概要，表情/动作参考）
- variant_label：变体标签（如"微笑""生气""行走"）

### C2. 生成提示词

按 [template-立绘提示词.md](references/template-立绘提示词.md) 模板生成。提示词只描述表情和动作变化——外貌不重复（以 IllusDesign 图片为参考）。

写入 `06_角色美术/<char_id>/立绘/<scene_id>/<variant_label>/提示词.md`。

### C3. 更新图节点

通过 neo4j-helper 更新 StandingIllustration 节点：

> "更新 StandingIllustration 节点（id 为 <stand_id>），设置 prompt_path 为 '06_角色美术/<char_id>/立绘/<scene_id>/<variant_label>/提示词.md'，status 设为 1"

---

## 变体数量规则

StandingIllustration 变体数量由角色优先级决定：

| 优先级 | 变体数 | 典型变体 |
|-------|-------|---------|
| P0 主角 | 10 | 默认, 微笑, 生气, 悲伤, 惊讶, 思考, 坚定, 恐惧, 战斗, 受伤 |
| P0 核心 NPC | 10 | 根据角色定制 |
| P1 重要 NPC | 6 | 根据角色定制 |
| P2 背景 NPC | 2 | 默认 + 1 个关键表情 |

---

## 参考文档

- [设计图提示词模板](references/template-设计图提示词.md)
- [立绘提示词模板](references/template-立绘提示词.md)
