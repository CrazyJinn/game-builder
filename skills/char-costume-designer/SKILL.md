---
name: char-costume-designer
description: |
  推进 CostumeStyle 图节点：查询状态 → 分析事件着装需求并生成内容 → 保存结果（复用加 wears 边；新建 MERGE 节点+边+内容，status=1 已完成）。
  在需要为角色创建/追加着装方案时使用。
argument-hint: <char_id>
arguments:
  - char_id
allowed-tools: Read, Bash, Write, Edit
---

# 着装设计（CostumeStyle）

为角色的每个事件分析着装需求，推进 CostumeStyle 节点并绑定 `wears` 边（Event → CostumeStyle）。新建着装写入内容后即 `status=1`（已完成，无审批），直接参与下游 IllusDesign 生产。

## 参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| char_id | 角色节点 ID（snowflake Base62） | 必传 |

## 流程（三段式：查状态 → 完成任务 → 保存结果）

> 本 skill 是 CostumeStyle 内容与 status 的唯一写入点。「保存结果」步对复用与新建两种情况分别写入。

### 1. 查询目标节点状态

通过 `${CLAUDE_SKILL_DIR}/../../scripts/cypher_exec.py` 查询角色 + 外貌 + 已有着装 + 事件着装绑定：

```cypher
// 角色 + 外貌 + 已有着装
MATCH (ch:Character {id: '<char_id>'})
OPTIONAL MATCH (ch)-[:has_appearance]->(app:AppearanceStyle)
OPTIONAL MATCH (ch)-[:has_costume]->(cos:CostumeStyle)
RETURN ch, app, collect(cos) AS costumes;

// 事件 + 场景 + 已有着装绑定
MATCH (ch:Character {id: '<char_id>'})-[r:involved]->(e:Event)
OPTIONAL MATCH (e)-[:occurred_at]->(s:Location)
OPTIONAL MATCH (e)-[:wears]->(cos:CostumeStyle)
RETURN e.id AS event_id, e.title AS event_title, r.role AS role, r.detail AS detail,
       s.id AS loc_id, s.name AS loc_name, s.description AS loc_desc,
       cos.id AS costume_id, cos.name AS costume_name
ORDER BY e.id;
```

### 2. 完成任务

对每个**没有 `wears` 边的 Event** 分析着装需求：

1. 提取事件上下文：事件 detail（角色行为）、Location 环境、角色身份（character_tags）。
2. 判断是否可复用已有 CostumeStyle：
   - 例如：已有"职场御姐着装"，事件发生在"星耀电竞办公室" → 可复用
   - 例如：已有"职场御姐着装"，事件发生在"咖啡店约会" → 需要新着装
3. 按着装需求分组：同一着装可覆盖的事件归为一组，每组对应一个 CostumeStyle（复用已有 or 新建）。
4. 对需**新建**的组，生成 snowflake id 并按下方字段表填写内容：

   | 维度 | 属性 | 示例 | 说明 |
   |------|------|------|------|
   | 名称 | name | `沈暮雪-休闲约会着装` | 自由文本（角色名 + 着装场景描述） |
   | 着装风格 | outfit_style | 休闲 / 正式 / 运动 / 性感 / 可爱 / 学院 / 街头 / 古风 / 慵懒 | 可多选 |
   | 服装 | garment | `棉白衬衫` | `棉质白衬衫;蕾丝女式三角内裤;黑色丝袜` |
   | 鞋类 | footwear | 运动鞋 / 皮鞋 / 靴 / 帆布鞋 / 凉鞋 / 高跟鞋 / 赤足 | 单选 |
   | 配饰类型 | accessory_type | 耳饰 / 项链 / 手表 / 眼镜 / 戒指 / 发饰 / 手持物 | 可多选 |

   **内容生成规则**：
   1. 可参考 `00_init/世界设定.md`（风格不违背世界观）；角色配色参考 Character 的 `color_direction`，**但不强求一致**。
   2. 服装款式/颜色统一记录在 `garment`，多件用 `;` 分隔；每件含必选（材质+颜色+类型）与可选（领型/滚边/层次/剪裁/质感氛围等，不宜过多）。
   3. 配饰放入 `accessory_type`，具体样式用自定义标签值补充。

### 3. 保存结果

#### 复用已有 CostumeStyle 的事件组（只加 wears 边）

```cypher
MATCH (e:Event {id: '<event_id>'}), (cos:CostumeStyle {id: '<costume_id>'})
MERGE (e)-[r:wears]->(cos) SET r.sync = false;
```

复用无需审批，直接生效。

#### 新建 CostumeStyle 的事件组（MERGE 节点+边+内容，status=1 已完成）

```cypher
MERGE (cos:CostumeStyle {id: '<snowflake_id>'})
  ON CREATE SET cos.status = 1;
MATCH (ch:Character {id: '<char_id>'}), (cos:CostumeStyle {id: '<snowflake_id>'})
MERGE (ch)-[r:has_costume]->(cos) SET r.sync = true;
MATCH (e:Event) WHERE e.id IN ['<event_id_1>', '<event_id_2>', ...]
MATCH (cos:CostumeStyle {id: '<snowflake_id>'})
MERGE (e)-[r:wears]->(cos) SET r.sync = false;
MATCH (cos:CostumeStyle {id: '<snowflake_id>'})
SET cos.name = '<角色名-着装描述>',
    cos.outfit_style = '...', cos.garment = '...', cos.footwear = '...', cos.accessory_type = '...',
    cos.status = 1;
```

**status 写入**：新建着装创建即 `status = 1`（已完成，无审批）。复用操作不涉及新节点 status。

最后汇总：复用了哪些已有 CostumeStyle（哪些事件）、新建了哪些（status=1 已完成）。

## 参考文档

- [着装设定模板](references/template-着装设定.md) — 各字段规则
