# Cypher 查询模板

## 目录

- [节点操作](#节点操作)
- [边操作](#边操作)
- [关系图查询](#关系图查询)
- [事件链查询](#事件链查询)
- [信息层查询](#信息层查询)
- [统计查询](#统计查询)
- [LOAD CSV 导入](#load-csv-导入)

---

## 节点操作

### 创建/更新节点（MERGE 幂等）

```cypher
// 人物
MERGE (n:char {编号: 'char_001'})
SET n.姓名 = '胖猫', n.性别 = '男', n.出生年份 = toInteger(2003)

// 地点
MERGE (n:Location {编号: 'loc_001'})
SET n.名称 = '重庆长江大桥', n.描述 = '重庆市地标性桥梁'

// 信息
MERGE (n:Info {编号: 'info_001'})
SET n.标题 = '转账记录', n.内容 = '累计转账51万元', n.知识层 = toInteger(2)

// 事件
MERGE (n:Event {编号: 'evt_001'})
SET n.标题 = '胖猫从重庆长江大桥跳江', n.时间 = '2024-04-11', n.类型 = '行动'
```

### 查询节点

```cypher
// 按编号查询
MATCH (n {编号: 'char_001'}) RETURN n

// 按标签查询全部
MATCH (n:char) RETURN n.编号, n.姓名, n.性别

// 模糊搜索
MATCH (n:char) WHERE n.姓名 CONTAINS '猫' RETURN n

// 按属性筛选
MATCH (n:Info {知识层: 2}) RETURN n
```

### 删除节点（连同边）

```cypher
MATCH (n:char {编号: 'char_999'}) DETACH DELETE n
```

---

## 边操作

### 创建/更新边（MERGE 幂等）

```cypher
// 人物关系
MATCH (a:char {编号: 'char_001'}), (b:char {编号: 'char_002'})
MERGE (a)-[:relation {type: '恋爱', detail: '网恋中'}]->(b)

// 人物-地点
MATCH (a:char {编号: 'char_001'}), (b:Location {编号: 'loc_001'})
MERGE (a)-[:at {type: '前往', detail: '跳江'}]->(b)

// 人物-事件
MATCH (a:char {编号: 'char_001'}), (b:Event {编号: 'evt_001'})
MERGE (a)-[:involved {role: '当事人', detail: '跳江者'}]->(b)

// 信息关联
MATCH (a {编号: 'char_001'}), (b:Info {编号: 'info_001'})
MERGE (a)-[:link {type: '涉及', detail: '主角相关信息'}]->(b)

// 事件-地点
MATCH (a:Event {编号: 'evt_001'}), (b:Location {编号: 'loc_001'})
MERGE (a)-[:occurred_at {detail: '跳江地点'}]->(b)

// 事件-事件
MATCH (a:Event {编号: 'evt_001'}), (b:Event {编号: 'evt_002'})
MERGE (a)-[:evt_relation {type: '因果', detail: '导致'}]->(b)
```

### 查询边

```cypher
// 查询某人物的所有关系
MATCH (a:char {编号: 'char_001'})-[r]-(b)
RETURN type(r) AS edge_type, labels(b)[0] AS target_type, b.编号 AS target_id

// 查询特定类型的边
MATCH (a:char)-[r:relation]->(b:char)
RETURN a.姓名, r.type, r.detail, b.姓名

// 查询事件的所有参与者
MATCH (a:char)-[r:involved]->(e:Event {编号: 'evt_001'})
RETURN a.姓名, r.role, r.detail
```

---

## 关系图查询

### 角色完整关系图

```cypher
// 某角色的所有直接关系
MATCH (c:char {编号: 'char_001'})-[r]-(other)
RETURN c, r, other

// 角色间关系路径（最多3跳）
MATCH path = (a:char {编号: 'char_001'})-[*1..3]-(b:char)
RETURN path

// 角色关系网（所有角色间关系）
MATCH (a:char)-[r:relation]->(b:char)
RETURN a.编号, a.姓名, type(r) AS edge, r.type, r.detail, b.编号, b.姓名
```

### 实体关系全图

```cypher
// 所有关联（限制数量）
MATCH (n)-[r]->(m)
RETURN n.编号 AS from, type(r) AS edge, properties(r) AS props, m.编号 AS to
LIMIT 200
```

---

## 事件链查询

### 时间线

```cypher
// 按时间排序的所有事件
MATCH (e:Event)
RETURN e.编号, e.标题, e.时间, e.类型
ORDER BY e.时间

// 某时间段的事件
MATCH (e:Event)
WHERE e.时间 >= '2024-01-01' AND e.时间 <= '2024-12-31'
RETURN e ORDER BY e.时间
```

### 因果链

```cypher
// 事件因果链（前因→后果）
MATCH (e1:Event)-[r:evt_relation {type: '因果'}]->(e2:Event)
RETURN e1.标题 AS cause, r.detail, e2.标题 AS effect

// 完整因果路径
MATCH path = (e1:Event)-[:evt_relation*1..5]->(e2:Event)
WHERE ALL(r IN relationships(path) WHERE r.type = '因果')
RETURN [n IN nodes(path) | n.标题] AS chain
```

### 时间线缺口检测

```cypher
// 查找事件间隔超过30天的时间段
MATCH (e1:Event)
WITH e1 ORDER BY e1.时间
WITH e1, e1.时间 AS t1
MATCH (e2:Event)
WHERE e2.时间 > t1
WITH e1, e2, duration.between(date(e1.时间), date(e2.时间)).days AS gap
ORDER BY gap DESC
WHERE gap > 30
RETURN e1.标题 AS before, e1.时间 AS before_date,
       e2.标题 AS after, e2.时间 AS after_date,
       gap AS days_gap
```

---

## 信息层查询

### 按知识层统计

```cypher
MATCH (n:Info)
RETURN n.知识层 AS level, count(*) AS count
ORDER BY level
```

### 按层查询信息及其关联实体

```cypher
// 深层信息及其关联
MATCH (entity)-[r:link]->(i:Info {知识层: 3})
RETURN labels(entity)[0] AS type, entity.编号 AS id,
       COALESCE(entity.姓名, entity.名称, entity.标题) AS name,
       i.编号 AS info_id, i.标题 AS info_title
```

### 信息因果链

```cypher
MATCH (i1:Info)-[r:link {type: '因果'}]->(i2:Info)
RETURN i1.标题 AS cause, r.detail, i2.标题 AS effect
```

---

## 统计查询

```cypher
// 各类型节点数
MATCH (n) RETURN labels(n)[0] AS type, count(*) AS count ORDER BY count DESC

// 各类型边数
MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS count ORDER BY count DESC

// 孤立节点
MATCH (n) WHERE NOT (n)--()
RETURN labels(n)[0] AS type, n.编号, COALESCE(n.姓名, n.名称, n.标题) AS name

// 密度最高的节点（关联最多的实体）
MATCH (n)-[r]-()
RETURN labels(n)[0] AS type, n.编号 AS id,
       COALESCE(n.姓名, n.名称, n.标题) AS name,
       count(r) AS degree
ORDER BY degree DESC LIMIT 10
```

---

## LOAD CSV 导入

### 从 CSV 批量导入节点

```cypher
LOAD CSV WITH HEADERS FROM 'file:///nodes_char.csv' AS row
MERGE (n:char {编号: row.编号})
SET n.姓名 = row.姓名,
    n.性别 = row.性别,
    n.description = row.description,
    n.出生年份 = toInteger(row.出生年份)
```

### 从 CSV 批量导入边

```cypher
LOAD CSV WITH HEADERS FROM 'file:///edges_relation.csv' AS row
MATCH (a:char {编号: row.from_id})
MATCH (b:char {编号: row.to_id})
MERGE (a)-[:relation {type: row.type, detail: row.detail}]->(b)
```

### LOAD CSV 文件路径说明

- `file:///` 前缀：相对于 Neo4j 的 `dbms.directories.import` 目录
- Windows 绝对路径：`file:///C:/path/to/file.csv`
- 中文 CSV 需确保 UTF-8 编码（含 BOM 更佳）
