# 发现查询参考

7 种检查类型及其 Cypher 查询、结果格式和建议生成规则。

---

## 1. orphans — 孤立节点

**目的**：找出零边的节点（可能被遗漏或未完成关联）。

```cypher
MATCH (n) WHERE NOT (n)--()
RETURN labels(n)[0] AS label, n.id AS id,
       COALESCE(n.name, n.title) AS name
```

**建议模板**：
- priority: `medium`
- "XX {name}({id}) 没有任何关联关系，建议添加至少一条边"

**典型发现**：
- status=0 的角色（刚导入还没建边）
- 新加的地点还没关联到事件

---

## 2. missing-relations — 缺失人物关系

**目的**：两个角色共同参与事件但没有 `relation` 边。这是叙事图中最有价值的发现。

```cypher
MATCH (c1:Character)-[:involved]->(e:Event)<-[:involved]-(c2:Character)
WHERE c1.id < c2.id
  AND NOT (c1)-[:relation]-(c2)
RETURN c1.id AS char1_id, c1.name AS char1_name,
       c2.id AS char2_id, c2.name AS char2_name,
       COLLECT(DISTINCT e.title) AS shared_events,
       COUNT(DISTINCT e) AS shared_count
ORDER BY shared_count DESC
```

**建议模板**：
- priority: `high`
- "A 和 B 共同参与 [事件列表]，但没有人物关系边"
- action: `ADD_EDGE relation(char1_id, char2_id) {type: '?', detail: '?'}`

**注意**：
- 使用 `c1.id < c2.id` 避免重复对
- `NOT (c1)-[:relation]-(c2)` 是无向检查（双向都没边）

---

## 3. events-no-location — 事件无地点

**目的**：没有 `occurred_at` 边的事件。

```cypher
MATCH (e:Event)
WHERE NOT (e)-[:occurred_at]->(:Location)
RETURN e.id AS id, e.title AS title, e.time AS time, e.type AS type
ORDER BY e.time
```

**建议模板**：
- priority: `medium`
- "事件「title」(id, time) 缺少地点关联"
- action: `ADD_EDGE occurred_at(evt_id, <location_id>) {detail: '?'}`

---

## 4. temporal-gaps — 时间线缺口

**目的**：连续事件之间超过 N 天的空白区间。由于本项目的 Event.时间 是混合格式（"开场"、"Day 5 上午"），需要在 Python 中解析。

```cypher
MATCH (e:Event) RETURN e.id AS id, e.title AS title, e.time AS time
```

**Python 后处理逻辑**：
```python
def parse_day(time_str):
    if time_str == "开场": return -1
    m = re.match(r"Day\s*(\d+)", time_str)
    return int(m.group(1)) if m else None

# 排序后计算相邻事件的间隔
events.sort(key=lambda x: x["day_num"])
for i in range(len(events)-1):
    gap = events[i+1]["day_num"] - events[i]["day_num"]
    if gap > threshold:  # 默认 3
        # 报告缺口
```

**建议模板**：
- priority: `high`
- "Day X 到 Day Y 之间有 N 天空缺（from_event → to_event）"
- action: "建议在 Day X+1 ~ Day Y-1 之间补充事件"

**阈值说明**：
- 默认 threshold=3（超过3天无事件视为缺口）
- 30天叙事中，3天空缺可能意味着缺少日常事件

---

## 5. info-no-links — 信息未关联

**目的**：Info 节点没有被任何实体的 `link` 边指向。

```cypher
MATCH (i:Info)
WHERE NOT ()-[:link]->(i)
RETURN i.id AS id, i.title AS title, i.knowledge_level AS level
ORDER BY i.knowledge_level
```

**建议模板**：
- priority: `medium`
- "信息「title」(id, knowledge_level N) 未关联到任何实体"
- action: `ADD_EDGE link(???, info_id) {type: '涉及', detail: '?'}`

---

## 6. chars-no-faction — 角色无阵营

**目的**：参与了事件但没有 `BELONGS_TO` 边的角色。仅对有实际活动的角色检查。

```cypher
MATCH (c:Character)
WHERE NOT (c)-[:BELONGS_TO]->(:Faction)
  AND (c)-[:involved]->(:Event)
RETURN c.id AS id, c.name AS name,
       COUNT { (c)-[:involved]->(:Event) } AS event_count
ORDER BY event_count DESC
```

**建议模板**：
- priority: `low`（不是所有角色都需要阵营）
- "角色「name」(id) 参与了 N 个事件但无阵营归属"
- action: "如果属于某阵营: ADD_EDGE BELONGS_TO(char_id, <faction_id>) {role: '?'}"

**注意**：
- priority 设为 `low` 因为很多角色确实无阵营（如路人、独立角色）
- 仅供用户参考，不强制

---

## 7. events-unlinked — 事件未入链

**目的**：没有 `evt_relation` 出入边的事件（孤立于事件链之外）。

```cypher
MATCH (e:Event)
WHERE NOT (e)-[:evt_relation]-()
RETURN e.id AS id, e.title AS title, e.time AS time
ORDER BY e.time
```

**建议模板**：
- priority: `low`（事件可以独立存在）
- "事件「title」(id, time) 未接入事件链（无因果/先后/包含关系）"
- action: `ADD_EDGE evt_relation(<evt_id>, id) {type: '因果|先后|包含', detail: '?'}`

---

## 优先级规则

| 级别 | 含义 | 检查类型 |
|------|------|---------|
| 🔴 high | 影响叙事完整性 | missing-relations, temporal-gaps |
| 🟡 medium | 影响图数据质量 | orphans, events-no-location, info-no-links |
| 🟢 low | 锦上添花 | chars-no-faction, events-unlinked |

## 输出格式

```json
{
  "summary": {
    "total_checks": 7,
    "total_suggestions": 12,
    "high": 3, "medium": 5, "low": 4
  },
  "suggestions": [
    {
      "priority": "high",
      "type": "missing_relation",
      "description": "苏晓禾和沈暮雪共同参与3个事件但无人物关系边",
      "action": "ADD_EDGE relation(<char1_id>, <char2_id>) {type: '?', detail: '?'}",
      "char1_id": "<snowflake_id>",
      "char2_id": "<snowflake_id>"
    }
  ],
  "details": { ... }
}
```
