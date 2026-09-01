# 边创建指南

8 种边类型的方向规则、属性 schema 和 Cypher 模板。

---

## 叙事关系边（6种）

### 1. relation — 人物关系

- **方向**：`char → char`
- **属性**：`type`（关系类型，如"恋爱""亲属""同事"）、`detail`（如"恋爱中""已分手""姐弟"）
- **方向语义**：有向，A→B 表示 A 对 B 的关系描述

```cypher
MATCH (a:Character {id: $from}), (b:Character {id: $to})
MERGE (a)-[:relation {type: $type, detail: $detail}]->(b)
```

### 2. at — 人物—地点

- **方向**：`Character → Location`
- **属性**：`type`（如"居住""前往""工作"）、`detail`

```cypher
MATCH (a:Character {id: $from}), (b:Location {id: $to})
MERGE (a)-[:at {type: $type, detail: $detail}]->(b)
```

### 3. link — 信息关联

- **方向**：`任意实体 → Info`
- **属性**：`type`（如"涉及""因果"）、`detail`、`time`
- **特殊规则**：`type=因果` 时仅用于 `Info → Info`

```cypher
// 实体关联信息
MATCH (a {id: $from}), (b:Info {id: $to})
MERGE (a)-[:link {type: $type, detail: $detail, time: $time}]->(b)

// 信息因果链（仅 Info→Info）
MATCH (a:Info {id: $from}), (b:Info {id: $to})
MERGE (a)-[:link {type: '因果', detail: $detail}]->(b)
```

### 4. involved — 人物—事件

- **方向**：`Character → Event`
- **属性**：`role`（如"当事人""目击者""受害者""施害者""参与者"）、`detail`

```cypher
MATCH (a:Character {id: $from}), (b:Event {id: $to})
MERGE (a)-[:involved {role: $role, detail: $detail}]->(b)
```

### 5. occurred_at — 事件—地点

- **方向**：`Event → Location`
- **属性**：`detail`（如"跳江地点""约会地点"）

```cypher
MATCH (a:Event {id: $from}), (b:Location {id: $to})
MERGE (a)-[:occurred_at {detail: $detail}]->(b)
```

### 6. evt_relation — 事件—事件

- **方向**：`Event → Event`
- **属性**：`type`（`因果`/`先后`/`包含`）、`detail`
- **方向语义**：`因果` = 前因→后果；`先后` = 时间顺序；`包含` = 大事件→子事件

```cypher
MATCH (a:Event {id: $from}), (b:Event {id: $to})
MERGE (a)-[:evt_relation {type: $type, detail: $detail}]->(b)
```

---

## 分组边（2种）

### 7. BELONGS_TO — 角色—阵营

- **方向**：`Character → Faction`
- **属性**：`role`（如"战队经理""战队队长""成员"）
- **注意**：无阵营角色无此边

```cypher
MATCH (a:Character {id: $from}), (b:Faction {id: $to})
MERGE (a)-[:BELONGS_TO {role: $role}]->(b)
```

### 8. CATEGORIZED_AS — 地点—类型

- **方向**：`Location → LocationType`
- **属性**：无

```cypher
MATCH (a:Location {id: $from}), (b:LocationType {id: $to})
MERGE (a)-[:CATEGORIZED_AS]->(b)
```

---

## 方向验证规则

创建边前必须验证方向正确：

| from 标签 | 允许的边类型 | to 标签 |
|-----------|------------|---------|
| Character | relation, at, link, involved, BELONGS_TO | → Character / Location / Info / Event / Faction |
| Event | occurred_at, evt_relation, link | → Location / Event / Info |
| Location | CATEGORIZED_AS, link | → LocationType / Info |
| Info | link | → Info |
| Faction | — | — |
| LocationType | — | — |
| 任意 | link | → Info |
