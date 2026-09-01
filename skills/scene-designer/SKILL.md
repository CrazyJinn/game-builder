---
name: scene-designer
description: |
  推进 Scene 图节点：查询状态 → 从 Location 及其事件推导场景切分 → 保存结果（已有场景跳过；新建场景 MERGE 节点+has_scene 边+内容，status=1 已完成）。
  在需要为地点创建/追加场景视觉设定时使用。
argument-hint: <loc_id>
arguments:
  - loc_id
allowed-tools: Read, Bash, Write, Edit
---

> **status=-1 = 作废重做**：当 Scene 被 sync 级联重置为 `status=-1` 时（Location 被编辑），即使各属性已有值，也**必须重新生成并覆盖**。`-1` 与 `0` 都视为"需生成"起点；`-1` 明确表示旧内容作废，**禁止因属性已有值而跳过**。

# 场景设计（Scene）

为地点的每个视觉子空间推导场景设定，推进 Scene 节点并绑定 `has_scene` 边（Location → Scene）。新建场景写入内容后即 `status=1`（已完成，无审批），直接参与下游 SceneLayer 生产。

## 参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| loc_id | 地点节点 ID（snowflake Base62） | 必传 |

## 流程（三段式：查状态 → 完成任务 → 保存结果）

> 本 skill 是 Scene 内容与 status 的唯一写入点。「保存结果」步对已有场景（跳过）与新建场景分别处理。

### 1. 查询目标节点状态

通过 `${CLAUDE_SKILL_DIR}/../../scripts/cypher_exec.py` 查询地点 + 已有场景 + 该地点上的事件（场景切分依据）：

```cypher
// 地点 + 已有场景
MATCH (l:Location {id: '<loc_id>'})
OPTIONAL MATCH (l)-[:has_scene]->(s:Scene)
RETURN l, collect(s) AS scenes;

// 该地点上的事件（场景切分依据）
MATCH (e:Event)-[:occurred_at]->(l:Location {id: '<loc_id>'})
RETURN e.id AS event_id, e.title AS title, e.description AS desc, e.time AS time
ORDER BY e.id;
```

### 2. 完成任务（场景切分）

对 Location 的每个**未被已有 Scene 覆盖的视觉子空间**分析：

1. **提取上下文**：Location.name + Location.description + 该 Location 上的 Event（标题/描述/时间）。
2. **场景切分**（LLM 推导）：按 Event 在该 Location 内的发生位置聚类为「同一视觉子空间」——同一区域发生的多个事件归为一组，每组对应一个 Scene。例如咖啡店 Location，事件分别发生在「点餐台」「座位区」「门外」→ 3 个 Scene。
3. **去重**：已有 Scene（步骤 1 的 scenes）已覆盖的子空间跳过，不重复创建。
4. 对需**新建**的 Scene，生成 snowflake id 并按下方字段表填写内容：

   | 维度 | 属性 | 示例 | 说明 |
   |------|------|------|------|
   | 名称 | name | `咖啡店-点餐台` | `[Location名]-[区域]` |
   | 场景类型 | scene_type | dialogue / functional / combat / ui | 按事件性质：纯对话→dialogue，功能交互→functional，战斗→combat，界面→ui |
   | 时段 | time_of_day | 清晨/白天/黄昏/夜晚 | 从 Event.time 和描述推导 |
   | 天气 | weather | 晴/阴/雨/雪/雾 | 从事件描述推导 |
   | 氛围 | atmosphere | `空气里弥漫咖啡香，慵懒午后` | 自由文本：整体氛围一句话 |
   | 构图 | composition | `远景：吧台与菜单牌；中景：点餐台台面；近景：收银机与杯具` | 自由文本：远/中/近景分层（分号分隔） |
   | 光影 | lighting | `主光源从右上方照射，暖黄色调，环境光柔和偏橙` | 自由文本：主光源方向+色温+环境光 |
   | 配色逻辑 | color_direction | `主色咖啡棕，辅色奶白，点缀暖橙` | 自由文本：主辅点缀色与明暗逻辑 |
   | 概要 | description | `咖啡店的点餐区域` | 1-2 句 |

   **内容生成规则**：
   1. 构图（composition）须明确远/中/近景三段，是下游 SceneLayer 背景提示词的主体来源。
   2. 光影（lighting）须含主光源方向+色温+环境光，是提示词光影段来源。
   3. 配色与光效由 color_direction/lighting 自由定调。

### 3. 保存结果

#### 已有 Scene 覆盖的子空间

跳过（不重复创建）。

#### 新建 Scene（MERGE 节点+边+内容，status=1 已完成）

对每个新建 Scene 一次性写入（节点不存在则兜底创建）：

```cypher
MERGE (s:Scene {id: '<snowflake_id>'})
  ON CREATE SET s.status = 0;
MATCH (l:Location {id: '<loc_id>'}), (s:Scene {id: '<snowflake_id>'})
MERGE (l)-[r:has_scene]->(s) SET r.sync = true;
MATCH (s:Scene {id: '<snowflake_id>'})
SET s.name = '<Location名-区域>',
    s.scene_type = '...', s.time_of_day = '...', s.weather = '...',
    s.atmosphere = '...', s.composition = '...', s.lighting = '...',
    s.color_direction = '...',
    s.description = '...',
    s.status = 1;
```

**status 写入**：新建场景创建即 `status = 1`（已完成，无审批）。

最后汇总：跳过了哪些已有 Scene，新建了哪些（status=1 已完成）。

## 参考文档

- [场景美术 Schema](00_init/Schema/场景美术.md) — Scene 节点字段、scene_type 与所需图层
- [场景美术风格](00_init/美术风格.md) — 渲染与色彩基调、提示词硬约束（风格收尾串）
