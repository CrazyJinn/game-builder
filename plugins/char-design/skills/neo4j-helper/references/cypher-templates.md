# Cypher 模板参考

模板中的节点标签、边类型、属性名以实际 Schema 为准。以下基于项目 Schema（叙事基础 + 角色美术）作为示例。

字段名使用 schema 中定义的英文名。节点标签使用 schema 中的英文名（Character / Event / Scene / Info）。

## 目录

- [节点 CRUD](#节点-crud)
- [边 CRUD](#边-crud)
- [关系图查询](#关系图查询)
- [事件链查询](#事件链查询)
- [信息层查询](#信息层查询)
- [统计查询](#统计查询)
- [批量操作](#批量操作)
- [条件与流程控制](#条件与流程控制)

---

## 节点 CRUD

### 创建/更新节点（MERGE 幂等）

```cypher
// Character
MERGE (n:Character {id: $id})
SET n.name = $name, n.gender = $gender, n.birth_year = toInteger($birth_year)

// Scene
MERGE (n:Scene {id: $id})
SET n.name = $name, n.description = $desc

// Event
MERGE (n:Event {id: $id})
SET n.title = $title, n.time = $time, n.type = $type

// Info
MERGE (n:Info {id: $id})
SET n.title = $title, n.content = $content, n.knowledge_level = toInteger($level)
```

### 查询节点

```cypher
// 按 id 查询
MATCH (n {id: $id}) RETURN n

// 按标签查询全部
MATCH (n:Character) RETURN n.id, n.name, n.gender

// 模糊搜索
MATCH (n:Character) WHERE n.name CONTAINS $keyword RETURN n

// 按属性筛选
MATCH (n:Info {knowledge_level: $level}) RETURN n

// 多条件组合
MATCH (n:Character)
WHERE n.gender = '女' AND n.birth_year >= toInteger($year)
RETURN n ORDER BY n.birth_year
```

### 更新节点属性

```cypher
// 单字段更新
MATCH (n:Character {id: $id}) SET n.status = $status

// 多字段更新
MATCH (n:Character {id: $id})
SET n.status = $status, n.prompt_path = $path

// 条件更新（CASE WHEN）
MATCH (n:Character {id: $id})
SET n.status = CASE
  WHEN n.status = 0 THEN 1
  WHEN n.status = 1 THEN 2
  ELSE n.status
END

// 追加标签
MATCH (n {id: $id}) SET n:Processed

// 移除属性
MATCH (n:Character {id: $id}) REMOVE n.temp_field
```

### 删除节点

```cypher
// 删除节点及其所有边
MATCH (n {id: $id}) DETACH DELETE n

// 仅删除无边的孤立节点
MATCH (n) WHERE NOT (n)--() DELETE n

// 按标签批量删除
MATCH (n:TestNode) DETACH DELETE n
```

---

## 边 CRUD

### 创建/更新边（MERGE 幂等）

```cypher
// relation: Character → Character
MATCH (a:Character {id: $from_id}), (b:Character {id: $to_id})
MERGE (a)-[:relation {type: $type, detail: $detail}]->(b)

// at: Character → Scene
MATCH (a:Character {id: $from_id}), (b:Scene {id: $to_id})
MERGE (a)-[:at {type: $type, detail: $detail}]->(b)

// involved: Character → Event
MATCH (a:Character {id: $from_id}), (b:Event {id: $to_id})
MERGE (a)-[:involved {role: $role, detail: $detail}]->(b)

// link: 任意 → Info
MATCH (a {id: $from_id}), (b:Info {id: $to_id})
MERGE (a)-[:link {type: $type, detail: $detail, time: $time}]->(b)

// occurred_at: Event → Scene
MATCH (a:Event {id: $from_id}), (b:Scene {id: $to_id})
MERGE (a)-[:occurred_at {detail: $detail}]->(b)

// evt_relation: Event → Event
MATCH (a:Event {id: $from_id}), (b:Event {id: $to_id})
MERGE (a)-[:evt_relation {type: $type, detail: $detail}]->(b)
```

### 查询边

```cypher
// 某实体的所有关系
MATCH (n {id: $id})-[r]-(other)
RETURN type(r) AS edge_type, labels(other)[0] AS target_type,
       other.id AS target_id, properties(r) AS edge_props

// 特定类型的边
MATCH (a:Character)-[r:relation]->(b:Character)
RETURN a.name, r.type, r.detail, b.name

// 某事件的所有参与者
MATCH (a:Character)-[r:involved]->(e:Event {id: $id})
RETURN a.name, r.role, r.detail
```

### 更新边属性

```cypher
// 更新边的属性
MATCH (a:Character {id: $from_id})-[r:relation]->(b:Character {id: $to_id})
SET r.detail = $new_detail

// 添加边属性
MATCH (a {id: $from_id})-[r:link]->(b:Info {id: $to_id})
SET r.time = $time, r.verified = true
```

### 删除边

```cypher
// 删除指定边
MATCH (a:Character {id: $from_id})-[r:relation]->(b:Character {id: $to_id})
DELETE r

// 删除某类型的所有边
MATCH (a:Character)-[r:at]->(b:Scene) DELETE r
```

---

## 关系图查询

### 角色关系图

```cypher
// 某角色的所有直接关系
MATCH (c:Character {id: $id})-[r]-(other)
RETURN c, r, other

// 两角色间最短路径
MATCH path = shortestPath(
  (a:Character {id: $from_id})-[*..5]-(b:Character {id: $to_id})
)
RETURN path

// 角色关系网（全部角色间关系）
MATCH (a:Character)-[r:relation]->(b:Character)
RETURN a.id, a.name, type(r) AS edge, r.type, r.detail, b.id, b.name
```

### 多跳路径

```cypher
// 最多 3 跳
MATCH path = (a:Character {id: $id})-[*1..3]-(other)
RETURN path LIMIT 300

// 全关联图（限制数量）
MATCH (n)-[r]->(m)
RETURN n.id AS from, type(r) AS edge, properties(r) AS props, m.id AS to
LIMIT 200
```

---

## 事件链查询

### 时间线

```cypher
// 全部事件按时间排序
MATCH (e:Event)
RETURN e.id, e.title, e.time, e.type
ORDER BY e.time

// 某时间段的事件
MATCH (e:Event)
WHERE e.time >= $start_date AND e.time <= $end_date
RETURN e ORDER BY e.time
```

### 因果链

```cypher
// 直接因果关系
MATCH (e1:Event)-[r:evt_relation {type: '因果'}]->(e2:Event)
RETURN e1.title AS cause, r.detail, e2.title AS effect

// 完整因果路径
MATCH path = (e1:Event)-[:evt_relation*1..5]->(e2:Event)
WHERE ALL(r IN relationships(path) WHERE r.type = '因果')
RETURN [n IN nodes(path) | n.title] AS chain
```

### 时间缺口检测

```cypher
MATCH (e1:Event)
WITH e1 ORDER BY e1.time
WITH e1, e1.time AS t1
MATCH (e2:Event)
WHERE e2.time > t1
WITH e1, e2, duration.between(date(e1.time), date(e2.time)).days AS gap
ORDER BY gap DESC
WHERE gap > 30
RETURN e1.title AS before, e1.time AS before_date,
       e2.title AS after, e2.time AS after_date,
       gap AS days_gap
```

---

## 信息层查询

```cypher
// 按 knowledge_level 统计
MATCH (n:Info)
RETURN n.knowledge_level AS level, count(*) AS count ORDER BY level

// 某 level 信息及其关联实体
MATCH (entity)-[r:link]->(i:Info {knowledge_level: $level})
RETURN labels(entity)[0] AS type, entity.id AS id,
       entity.name AS name,
       i.id AS info_id, i.title AS info_title
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
RETURN labels(n)[0] AS type, n.id, n.name

// 密度最高节点
MATCH (n)-[r]-()
RETURN labels(n)[0] AS type, n.id,
       n.name,
       count(r) AS degree
ORDER BY degree DESC LIMIT 10

// 某标签的属性分布
MATCH (n:Character) RETURN n.gender AS gender, count(*) AS count
```

---

## 批量操作

### UNWIND 批量创建

```cypher
// 批量创建节点
UNWIND $nodes AS node
MERGE (n:Character {id: node.id})
SET n.name = node.name, n.gender = node.gender

// 批量创建边
UNWIND $edges AS edge
MATCH (a {id: edge.from_id}), (b {id: edge.to_id})
MERGE (a)-[:relation {type: edge.type, detail: edge.detail}]->(b)
```

### LOAD CSV 批量导入

```cypher
// 导入节点
LOAD CSV WITH HEADERS FROM 'file:///nodes_char.csv' AS row
MERGE (n:Character {id: row.id})
SET n.name = row.name, n.gender = row.gender, n.description = row.description

// 导入边
LOAD CSV WITH HEADERS FROM 'file:///edges_relation.csv' AS row
MATCH (a:Character {id: row.from_id}), (b:Character {id: row.to_id})
MERGE (a)-[:relation {type: row.type, detail: row.detail}]->(b)
```

**LOAD CSV 路径说明**：
- `file:///` 前缀：相对于 Neo4j 的 `dbms.directories.import` 目录
- Windows 绝对路径：`file:///C:/path/to/file.csv`
- 中文 CSV 需 UTF-8 编码（含 BOM 更佳）

---

## 条件与流程控制

### CASE WHEN 条件更新

```cypher
// 状态流转
MATCH (n:Character {id: $id})
SET n.status = CASE
  WHEN n.status = 0 THEN 1
  WHEN n.status = 1 THEN 2
  WHEN n.status = 2 THEN 3
  ELSE n.status
END
RETURN n.id, n.status

// 条件返回
MATCH (n:Character)
RETURN n.name,
  CASE n.gender
    WHEN '男' THEN '男性角色'
    WHEN '女' THEN '女性角色'
    ELSE '未知'
  END AS gender_label
```

### WITH 管道

```cypher
// 先聚合再筛选
MATCH (n:Character)-[r]-()
WITH n, count(r) AS degree
WHERE degree > 5
RETURN n.name, degree ORDER BY degree DESC
```

### FOREACH 条件操作

```cypher
// 条件批量更新
MATCH (n:Character)
WHERE n.status = 0
FOREACH (_ IN CASE WHEN n.gender = '女' THEN [1] ELSE [] END |
  SET n.priority = 'high'
)
```

---

## 美术图构建

基于 `schema/02_角色美术.md` 定义，为角色构建完整的美术生产链子图。

### 创建美术节点

```cypher
// LanguageStyle — 语言风格
MERGE (n:LanguageStyle {id: $id})
SET n.name = $name, n.path = $path, n.description = $desc, n.status = 0

// AppearanceStyle — 外貌特征
MERGE (n:AppearanceStyle {id: $id})
SET n.name = $name, n.appearance = $appearance,
    n.color_direction = $color_dir, n.shape_language = $shape_lang,
    n.visual_tone = $visual_tone, n.first_impression = $first_imp,
    n.memory_points = $mem_pts, n.status = 0

// CostumeStyle — 着装特征
MERGE (n:CostumeStyle {id: $id})
SET n.name = $name, n.default_outfit = $outfit,
    n.material_direction = $mat_dir, n.posture = $posture,
    n.accessories = $accessories, n.status = 0

// DesignSheet — 三视图设计稿
MERGE (n:DesignSheet {id: $id})
SET n.prompt_path = $prompt_path, n.image_path = $image_path, n.status = 0

// IllusDesign — 立绘设计图
MERGE (n:IllusDesign {id: $id})
SET n.prompt_path = $prompt_path, n.image_path = $image_path,
    n.adaptation_notes = $notes, n.status = 0

// StandingIllustration — 立绘变体
MERGE (n:StandingIllustration {id: $id})
SET n.variant_label = $label, n.prompt_path = $prompt_path,
    n.image_path = $image_path, n.status = 0

// Faction — 阵营（按需）
MERGE (n:Faction {id: $id})
SET n.name = $name, n.description = $desc,
    n.visual_identity = $vis_id, n.color_direction = $color_dir,
    n.material_direction = $mat_dir
```

### 创建美术边

```cypher
// has_appearance: Character → AppearanceStyle（sync=true）
MATCH (a:Character {id: $from_id}), (b:AppearanceStyle {id: $to_id})
MERGE (a)-[r:has_appearance]->(b)
SET r.sync = true

// has_costume: Character → CostumeStyle（sync=true）
MATCH (a:Character {id: $from_id}), (b:CostumeStyle {id: $to_id})
MERGE (a)-[r:has_costume]->(b)
SET r.sync = true

// has_voice_style: Character → LanguageStyle（sync=true）
MATCH (a:Character {id: $from_id}), (b:LanguageStyle {id: $to_id})
MERGE (a)-[r:has_voice_style]->(b)
SET r.sync = true

// produces: AppearanceStyle → DesignSheet（sync=true）
MATCH (a:AppearanceStyle {id: $from_id}), (b:DesignSheet {id: $to_id})
MERGE (a)-[r:produces]->(b)
SET r.sync = true

// produces: DesignSheet → IllusDesign（sync=false）
MATCH (a:DesignSheet {id: $from_id}), (b:IllusDesign {id: $to_id})
MERGE (a)-[r:produces]->(b)
SET r.sync = false

// outfit_for: CostumeStyle → IllusDesign（sync=false）
MATCH (a:CostumeStyle {id: $from_id}), (b:IllusDesign {id: $to_id})
MERGE (a)-[r:outfit_for]->(b)
SET r.sync = false

// context_for: Scene → IllusDesign（sync=false）
MATCH (a:Scene {id: $from_id}), (b:IllusDesign {id: $to_id})
MERGE (a)-[r:context_for]->(b)
SET r.sync = false

// expands_to: IllusDesign → StandingIllustration（sync=true）
MATCH (a:IllusDesign {id: $from_id}), (b:StandingIllustration {id: $to_id})
MERGE (a)-[r:expands_to]->(b)
SET r.variant_label = $label, r.sync = true

// ref_style: LanguageStyle → StandingIllustration（sync=true）
MATCH (a:LanguageStyle {id: $from_id}), (b:StandingIllustration {id: $to_id})
MERGE (a)-[r:ref_style]->(b)
SET r.sync = true

// groups: Faction → Character（sync=false）
MATCH (a:Faction {id: $from_id}), (b:Character {id: $to_id})
MERGE (a)-[r:groups]->(b)
SET r.role = $role, r.sync = false
```

### 批量构建角色美术子图

一次性为某个角色创建完整的美术子图结构（不含 IllusDesign/StandingIllustration，需手动指定场景）：

> 美术风格不从图数据库获取，而是从 `00_init/美术风格.md` 文件读取。

```cypher
// Step 1: 创建数据节点
MERGE (app:AppearanceStyle {id: $app_id})
SET app.name = $app_name, app.status = 0;

MERGE (cos:CostumeStyle {id: $cos_id})
SET cos.name = $cos_name, cos.status = 0;

MERGE (voice:LanguageStyle {id: $voice_id})
SET voice.name = $voice_name, voice.status = 0;

// Step 2: 连接 Character → 数据节点
MATCH (ch:Character {id: $char_id}), (app:AppearanceStyle {id: $app_id})
MERGE (ch)-[r:has_appearance]->(app) SET r.sync = true;

MATCH (ch:Character {id: $char_id}), (cos:CostumeStyle {id: $cos_id})
MERGE (ch)-[r:has_costume]->(cos) SET r.sync = true;

MATCH (ch:Character {id: $char_id}), (voice:LanguageStyle {id: $voice_id})
MERGE (ch)-[r:has_voice_style]->(voice) SET r.sync = true;

// Step 3: 创建 DesignSheet
MERGE (ds:DesignSheet {id: $design_id})
SET ds.status = 0;

// Step 4: AppearanceStyle → DesignSheet（produces）
MATCH (app:AppearanceStyle {id: $app_id}), (ds:DesignSheet {id: $design_id})
MERGE (app)-[r:produces]->(ds) SET r.sync = true;
```

### 为指定场景创建 IllusDesign + StandingIllustration

```cypher
// Step 1: 创建 IllusDesign
MERGE (illus:IllusDesign {id: $illus_id})
SET illus.status = 0;

// Step 2: 连接三个上游（sync=false，不自动级联）
MATCH (ds:DesignSheet {id: $design_id}), (illus:IllusDesign {id: $illus_id})
MERGE (ds)-[r:produces]->(illus) SET r.sync = false;

MATCH (cos:CostumeStyle {id: $cos_id}), (illus:IllusDesign {id: $illus_id})
MERGE (cos)-[r:outfit_for]->(illus) SET r.sync = false;

MATCH (s:Scene {id: $scene_id}), (illus:IllusDesign {id: $illus_id})
MERGE (s)-[r:context_for]->(illus) SET r.sync = false;

// Step 3: 创建 StandingIllustration 变体（以"微笑"为例）
MERGE (stand:StandingIllustration {id: $stand_id})
SET stand.variant_label = $label, stand.status = 0;

MATCH (illus:IllusDesign {id: $illus_id}), (stand:StandingIllustration {id: $stand_id})
MERGE (illus)-[r:expands_to]->(stand)
SET r.variant_label = $label, r.sync = true;

MATCH (voice:LanguageStyle {id: $voice_id}), (stand:StandingIllustration {id: $stand_id})
MERGE (voice)-[r:ref_style]->(stand) SET r.sync = true;
```

---

## Sync 级联查询

当上游节点更新时，沿 `sync=true` 边 BFS 级联重置下游节点 status。

### 单轮级联：查找 sync=true 下游

```cypher
// 查找某个节点的所有 sync=true 出边下游
MATCH (src {id: $source_id})-[r]->(dst)
WHERE r.sync = true
RETURN dst.id AS id, labels(dst)[0] AS type, type(r) AS edge_type
```

### 重置下游节点 status

```cypher
// 将指定节点 status 重置为 0
MATCH (n {id: $node_id})
SET n.status = 0
RETURN n.id, labels(n)[0] AS type
```

### 批量重置多个节点

```cypher
// 按节点 ID 列表批量重置
UNWIND $ids AS nid
MATCH (n {id: nid})
SET n.status = 0
RETURN n.id, labels(n)[0] AS type
```

### 级联算法（在 agent 层迭代执行）

```
1. 初始化队列 = [source_node_id]，已访问集合 = {}
2. 循环直到队列为空:
   a. 取出队首 current_id
   b. 若 current_id 在已访问集合中，跳过
   c. 将 current_id 加入已访问集合
   d. 执行"单轮级联"查询找到所有 sync=true 下游
   e. 对每个下游节点: 重置 status=0, 加入队列
3. 返回已访问集合（除 source 外的所有节点）
```

### 级联路径示例

```
外貌变更 appearance_001:
  appearance_001 →[produces✅]→ design_001 →[produces❌]→ (停止)
  受影响: design_001

语言风格变更 voice_001:
  voice_001 →[ref_style✅]→ stand_001, stand_002, ...
  受影响: 所有关联的 StandingIllustration
```

---

## 子图状态查询

查询角色完整的美术子图状态，用于 `status` 命令和流程推进判断。

### 查询角色全部美术节点

```cypher
// 方式1：从 Character 出发，多跳遍历
MATCH (ch:Character {id: $char_id})
OPTIONAL MATCH (ch)-[r1]->(data)
OPTIONAL MATCH (data)-[r2*0..3]->(downstream)
RETURN ch.id AS char_id,
       type(r1) AS edge1, labels(data)[0] AS data_type, data.id AS data_id, data.status AS data_status,
       [rel IN r2 | type(rel)] AS edges2,
       labels(downstream)[0] AS ds_type, downstream.id AS ds_id, downstream.status AS ds_status

// 方式2：按类型分查（更清晰）
MATCH (ch:Character {id: $char_id})
OPTIONAL MATCH (ch)-[:has_appearance]->(app:AppearanceStyle)
OPTIONAL MATCH (ch)-[:has_costume]->(cos:CostumeStyle)
OPTIONAL MATCH (ch)-[:has_voice_style]->(voice:LanguageStyle)
OPTIONAL MATCH (app)-[:produces]->(ds:DesignSheet)
OPTIONAL MATCH (ds)-[:produces]->(illus:IllusDesign)
OPTIONAL MATCH (illus)-[:expands_to]->(stand:StandingIllustration)
OPTIONAL MATCH (voice)-[:ref_style]->(stand2:StandingIllustration)
RETURN ch.id AS char_id,
       app.id AS appearance_id, app.status AS appearance_status,
       cos.id AS costume_id, cos.status AS costume_status,
       voice.id AS voice_id, voice.status AS voice_status,
       ds.id AS design_id, ds.status AS design_status,
       collect(DISTINCT {id: illus.id, status: illus.status}) AS illus_nodes,
       collect(DISTINCT {id: stand.id, status: stand.status, label: stand.variant_label}) AS stand_nodes
```

### 查询待处理节点

```cypher
// 数据节点 status=0（可立即由 concept-designer 处理）
MATCH (ch:Character {id: $char_id})-[:has_appearance|has_costume|has_voice_style]->(n)
WHERE n.status = 0
RETURN labels(n)[0] AS type, n.id AS id

// DesignSheet status=0（需要 AppearanceStyle 已完成）
MATCH (ch:Character {id: $char_id})-[:has_appearance]->(app:AppearanceStyle)
MATCH (app)-[:produces]->(ds:DesignSheet {status: 0})
WHERE app.status = 1
RETURN ds.id AS id

// DesignSheet status=1（提示词完成，可生成图片）
MATCH (ch:Character {id: $char_id})-[:has_appearance]->(app:AppearanceStyle)
MATCH (app)-[:produces]->(ds:DesignSheet {status: 1})
RETURN ds.id AS id, ds.prompt_path AS prompt_path

// IllusDesign status=0（需要 DesignSheet 已完成）
MATCH (ds:DesignSheet {status: 2})-[:produces]->(illus:IllusDesign {status: 0})
RETURN illus.id AS id

// StandingIllustration status=0（需要 IllusDesign 已完成）
MATCH (illus:IllusDesign {status: 2})-[:expands_to]->(stand:StandingIllustration {status: 0})
RETURN stand.id AS id, stand.variant_label AS label
```

### ID 分配

```cypher
// 查询某前缀的最大编号
MATCH (n) WHERE n.id STARTS WITH $prefix
RETURN n.id ORDER BY n.id DESC LIMIT 1

// 用法：查询 'appearance_' 返回 'appearance_003'，则新 ID = 'appearance_004'
// 无结果时从 _001 开始
```
