# analyze 查询：10 种叙事缺口检查

> analyze 阶段依次跑下列检查，输出 `--json` 结果供 LLM 归纳为**修改建议 JSON 数组**（每项 = 自然语言描述 + 可执行 cypher，格式见文末[输出格式](#输出格式修改建议-json-数组)）。
> 这些检查偏向**叙事缺口发现**（与 nrt-graph-builder 的 7 种**数据质量**检查互补，仅 temporal_gaps 重叠）。
> 节点/边定义见 [00_init/Schema/叙事基础.md](../../../00_init/Schema/叙事基础.md)（Character / Event / Location / Info + 6 边）。

每条查询用 `python ${CLAUDE_SKILL_DIR}/../../scripts/cypher_exec.py -c "<cypher>" --json` 执行。LLM 读 JSON 输出后做必要的后处理与建议生成。写 cypher 规则见 [cypher_exec.py](../../scripts/cypher_exec.py) 顶部 docstring。

---

## 聚焦模式（focus 子图限定）

传入 `focus`（角色名/id 或其他基础实体）时，本轮检查收窄到锚点的 1-2 跳子图，而非全图。通用模式：先 `MATCH` 锚点，再沿基础层边扩展到相关实体，检查只在该子图内进行。下文各检查给「全图版」查询；focus 版按下列代表模式改写。

**代表 1 · character_arcs（聚焦角色 X 的弧）**——只看 X 的事件：

```cypher
MATCH (c:Character) WHERE c.name='<focus>' OR c.id='<focus>'
OPTIONAL MATCH (c)-[:involved]->(e:Event)
RETURN c.id AS id, c.name AS name, c.priority AS priority,
       count(e) AS events, collect(e.time) AS times
```

若 X 的 events 少或时间断层 → 建议为 X 补 Event（补节点类）。这正是「第 2 轮聚焦新角色 X → 为 X 补事件」的实现。

**代表 2 · implicit_relations（聚焦 X 的隐含关系）**——只看与 X 共现的角色：

```cypher
MATCH (c:Character) WHERE c.name='<focus>' OR c.id='<focus>'
MATCH (c)-[:involved]->(e:Event)<-[:involved]-(b:Character)
WHERE NOT (c)-[:relation]-(b)
RETURN b.name AS b, collect(e.title) AS shared_events, count(e) AS shared
ORDER BY shared DESC LIMIT 50
```

shared ≥ 2 → 建议补 X→b 的 relation 边（补边类）。

**其余检查的 focus 收窄规则**：
- temporal_gaps / event_chains / narrative_density：限定到 focus 参与的事件（`MATCH (c:Character{...})-[:involved]->(e:Event)` 后以这些 e 为范围）。
- subgraph_connectivity / relationship_evolution：限定到 focus 角色。
- info_depth：限定到 focus 关联的 Info（`MATCH (c)-[:link]->(i:Info)` 或 focus 事件的 Info）。
- scene_utilization / bridge_scenes：限定到 focus 出现的 Location。

未传 focus 时，全部走下文「全图版」查询（等价于首轮全图体检）。

---

## 1. temporal_gaps（时间线缺口）

找出事件时间线上的大间隔（叙事空白期，可能需要补过渡事件）。

```cypher
MATCH (e:Event) WHERE e.time IS NOT NULL
RETURN e.id AS id, e.title AS title, e.time AS time
ORDER BY e.time LIMIT 200
```

后处理：LLM 解析 `time`（如"第N天"），计算相邻事件间隔，间隔过大处 → high 建议补桥接事件（**补节点类**，cypher 见末尾模板）。

## 2. character_arcs（角色弧完整性）

判断每个角色的活跃度：active（持续参与）/ vanished（中途消失）/ no_events（无事件）。

```cypher
MATCH (c:Character)
OPTIONAL MATCH (c)-[:involved]->(e:Event)
RETURN c.id AS id, c.name AS name, c.priority AS priority,
       count(e) AS events, collect(e.time) AS times
ORDER BY events DESC
```

后处理：核心角色（P0/P1）若 events 少或时间分布断层 → medium/high 建议补角色弧事件（**补节点类**）。

## 3. implicit_relations（隐含关系）

共同参与事件但无 `relation` 边的角色对——可能存在未显式记录的关系。

```cypher
MATCH (a:Character)-[:involved]->(e:Event)<-[:involved]-(b:Character)
WHERE elementId(a) < elementId(b)
  AND NOT (a)-[:relation]-(b)
RETURN a.name AS a, b.name AS b,
       collect(e.title) AS shared_events, count(e) AS shared
ORDER BY shared DESC LIMIT 50
```

建议：shared ≥ 2 的角色对 → high 建议补 `relation` 边（**补边类**；type/detail 由 LLM 推断建议值，cypher 见末尾模板）。

## 4. event_chains（事件链断裂）

孤立事件（无 `evt_relation` 因果/时序链接）。

```cypher
MATCH (e:Event)
WHERE NOT (e)-[:evt_relation]->() AND NOT (e)<-[:evt_relation]-()
RETURN e.id AS id, e.title AS title, e.time AS time
ORDER BY e.time LIMIT 100
```

建议：孤立的关键事件 → medium 建议建立因果链（补 `evt_relation` 边，**补边类**）。

## 5. scene_utilization（场景利用率）

各 Location 承载的事件数，找未被充分利用或过载的场景。

```cypher
MATCH (l:Location)
OPTIONAL MATCH (e:Event)-[:occurred_at]->(l)
RETURN l.id AS id, l.name AS name, count(e) AS events
ORDER BY events ASC LIMIT 100
```

> 纯统计型，通常**不产出**写 cypher（无明确补全动作）；仅过载/空置极突出时可在 description 提示。

## 6. info_depth（信息深度）

知识层（Info.knowledge_level 1/2/3）分布 + 孤立信息（无任何边）。

```cypher
MATCH (i:Info)
RETURN i.knowledge_level AS level, count(i) AS cnt ORDER BY level
```

```cypher
MATCH (i:Info) WHERE NOT (i)--()
RETURN i.id AS id, i.title AS title LIMIT 100
```

建议：孤立 Info → medium 建议链接到实体（补 `at` / `link` 边，**补边类**）。

## 7. subgraph_connectivity（子图连通性）

各角色的连接广度（涉及的 Location / 事件 / 其他角色）。

```cypher
MATCH (c:Character)
OPTIONAL MATCH (c)-[:involved]->(e:Event)-[:occurred_at]->(l:Location)
RETURN c.id AS id, c.name AS name,
       count(DISTINCT e) AS events, count(DISTINCT l) AS locations
ORDER BY locations ASC LIMIT 100
```

建议：核心角色 locations 偏少 → low 建议拓展场景（补 `at` 边，**补边类**）。

## 8. relationship_evolution（关系演化）

现有 `relation` 边，判断是否需要记录演化（关系随时间变化）。

```cypher
MATCH (a:Character)-[r:relation]-(b:Character)
WHERE elementId(a) < elementId(b)
RETURN a.name AS a, b.name AS b, r.type AS type, r.detail AS detail
LIMIT 100
```

建议：长跨度关系 → low 建议补充关系变化事件。

## 9. bridge_scenes（桥接场景）

连接多个人物/故事线的场景（高价值枢纽）。

```cypher
MATCH (l:Location)<-[:occurred_at]-(e:Event)<-[:involved]-(c:Character)
WITH l, collect(DISTINCT c.name) AS chars, count(DISTINCT e) AS events
WHERE size(chars) >= 3
RETURN l.name AS location, chars, events
ORDER BY size(chars) DESC LIMIT 50
```

> 统计型，识别枢纽场景的叙事价值；通常**不产出**写 cypher。

## 10. narrative_density（叙事密度）

每天/每时间段的事件密度，找过密或过稀处。

```cypher
MATCH (e:Event) WHERE e.time IS NOT NULL
RETURN e.time AS time, count(e) AS events
ORDER BY e.time LIMIT 200
```

后处理：LLM 计算每个时间段的事件数，过稀处可结合 temporal_gaps 补事件；过密/过稀突出时在 description 提示。通常**不单独产出**写 cypher。

---

## 输出格式：修改建议 JSON 数组

analyze 结果归纳为 JSON 数组（顶层 `[...]`），落盘 `02_剧情数据/<日期>_建议.json`。每项：

```json
{
  "check": "implicit_relations",
  "priority": "high",
  "reason": "陆择与沈暮雪共同参与 3 个事件（陆择加入星耀电竞、训练赛首胜、赛后庆功）但无 relation 边",
  "content": "建议补 relation 边（建议 type=恋爱、detail=待确认，可调整）",
  "cypher": "MATCH (a:Character{id:'Nv93TkkkgC'}),(b:Character{id:'Kx2Ab9Zz'}) MERGE (a)-[:relation{type:'恋爱',detail:'待确认'}]->(b);"
}
```

| 字段 | 说明 |
|------|------|
| check | 检查类型（上述 10 种之一） |
| priority | high / medium / low |
| reason | 提出建议的原因：analyze 发现了什么缺口/问题 |
| content | 建议内容：做什么补全；含 LLM 推断建议值时标注「可调整」 |
| cypher | 开箱可执行的单条 cypher（`;` 结尾）。纯统计型检查无补全动作时该条不产出 |
| round（可选） | 本轮轮次（文件名 `round<N>` 的 N），便于跨轮溯源 |
| focus（可选） | 本轮聚焦实体名；未聚焦时为「全图」 |

**筛选原则**：只对「确实可操作」的发现产出建议。补边/补节点类检查（implicit_relations、event_chains、info_depth、subgraph_connectivity、temporal_gaps、character_arcs）产出 cypher；纯统计型（scene_utilization、bridge_scenes、narrative_density）默认不产出，避免噪声。

### cypher 生成规则

保证每条 cypher 开箱可执行（遵循 [cypher_exec.py](../../scripts/cypher_exec.py) 顶部 docstring）：

1. **补边类**：端点用 analyze 查出的**真实 id** `MATCH`，再 `MERGE` 边；创意字段（type/detail/role 等）由 LLM 推断建议值填入。

   ```cypher
   MATCH (a:Character{id:'<id_a>'}),(b:Character{id:'<id_b>'})
   MERGE (a)-[:relation{type:'恋爱',detail:'待确认'}]->(b);
   ```

2. **补节点类**（temporal_gaps / character_arcs 需新增 Event）：`$SF_GEN -n 1 -q` 生成新 id，创意字段（title/time/type/description）LLM 推断建议值；需挂边时节点语句在前、边语句在后，`;` 分隔，合为同一条 cypher。

   ```cypher
   MERGE (n:Event{id:'<new_id>'}) SET n.title='训练间隙的日常', n.time='Day 6', n.type='交流';
   MATCH (n:Event{id:'<new_id>'}),(c:Character{id:'<id_c>'}) MERGE (c)-[:involved{role:'参与者'}]->(n);
   ```

3. **通用**：`MERGE` 幂等、内联值（不用 `$param`）、必须指定标签、字符串单引号（内部 `'` 转义 `\'`）、`;` 结尾。

---

## 范围限定（基础节点）

自增长只动**基础层**，产出的 cypher 只能操作：

- **节点**：`Character` / `Event` / `Location` / `Info` / `Choice`
- **边**：`relation` / `involved` / `occurred_at` / `at` / `link` / `evt_relation` / `presents` / `option`

**禁止**在建议 cypher 里出现美术层（AppearanceStyle/CostumeStyle/DesignSheet/IllusDesign/StandingIllustration）、场景层（Scene/SceneLayer）、剧情编排层（Chapter）的节点或边——这些走各自的生产链，不在自增长范围。Choice 现属基础层，`presents`/`option` 边可纳入自增长（如补 Choice 的戏剧分化、补 option 落点事件）。
