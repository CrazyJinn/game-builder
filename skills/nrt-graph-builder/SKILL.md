---
name: nrt-graph-builder
description: |
  自增长图构建器。支持手动添加和自动发现两种模式，增量式构建 Neo4j 叙事图数据库。
  手动模式：用户用自然语言描述实体和关系，技能解析后直接写入 Neo4j。
  发现模式：通过图算法发现缺失节点、孤立子图、时间缺口等，给出可操作建议。
  触发条件：(1) 用户要求新增角色/地点/事件到图数据库
  (2) 用户提到"加角色"、"新增事件"、"添加关系"、"建图"、"补数据"
  (3) 用户要求检查图的完整性缺口或发现缺失实体
  (4) 流程管理器需要增量写入图数据
  前置依赖：Neo4j 服务已启动，neo4j Python 包已安装。
allowed-tools: Read, Bash
---

# 自增长图构建器

## 连接配置

- URI: `bolt://localhost:7687`
- User: `neo4j`
- Password: `12345678`（或环境变量 `NEO4J_PASSWORD`）

## 脚本位置

```bash
# 本 skill 脚本
SCRIPT=".claude/skills/nrt-graph-builder/scripts/graph_builder.py"

# cypher 执行脚本（.claude/scripts，用于查询已有实体）
CYPHER_EXEC="python ${CLAUDE_SKILL_DIR}/../../scripts/cypher_exec.py"

# snowflake ID 生成器
SF_GEN="python ${CLAUDE_SKILL_DIR}/../../scripts/snowflake_base62.py"
```

---

## 模式一：手动添加

### Step 1: 解析用户输入

从自然语言中识别：

**实体**（新节点）：
- 人物：姓名、性别、描述、标签、出生年份等
- 地点：名称、描述
- 事件：标题、时间、类型、描述
- 信息：标题、内容、知识层
- 阵营/地点类型（如用户提及）

**关系**（新边，从文本中推断）：
- "是星耀电竞的选手" → `BELONGS_TO(char, faction_id) {role: "选手"}`
- "参与了第5天的聚会" → `involved(char_id, event_id) {role: "参与者"}`
- "发生在咖啡店" → `occurred_at(event_id, location_id)`
- "和XX是恋人" → `relation(char_A_id, char_B_id) {type: "恋爱"}`
- "导致XX事件" → `evt_relation(event_A_id, event_B_id) {type: "因果"}`

### Step 2: 查找已有实体

对用户提到的已有实体（如"陈默"、"星耀电竞"），通过名称从数据库查找：

```bash
$CYPHER_EXEC \
  -c "MATCH (c:Character) WHERE c.name='陈默' RETURN c.id AS id, c.name AS name, labels(c)[0] AS label" \
  --json
```

如果实体已存在，复用其 snowflake ID。如果不存在，标记为待创建。

### Step 3: 生成新节点 ID

新节点使用 snowflake Base62 ID：

```bash
# 为新节点生成 ID
python $SF_GEN -n 3 -q
# 输出 3 个 snowflake ID（每行一个）
```

### Step 4: 执行写入

**方案A — 使用 add-nodes + add-edges（推荐，自带ID分配和端点验证）**：

```bash
# 创建节点（脚本自动分配 snowflake ID）
python $SCRIPT add-nodes \
  --nodes '[{"label":"char","props":{"name":"张三","gender":"男"}}]' \
  --password 12345678

# 创建边（使用已有实体的 snowflake ID）
python $SCRIPT add-edges \
  --edges '[{"type":"BELONGS_TO","from_id":"<snowflake_id>","to_id":"<faction_id>","props":{"role":"选手"}}]' \
  --password 12345678
```

**方案B — 使用 execute-tx（需要手动拼 ID，适合复杂批量操作）**：

```bash
python $SCRIPT execute-tx \
  --cypher '["MERGE (c:Character {id: '"'"'<snowflake_id>'"'"'}) SET c.name='"'"'张三'"'"'", "MATCH ... MERGE ..."]' \
  --password 12345678
```

### Step 5: 报告

向用户报告：创建了哪些节点（名称 + snowflake ID）、哪些边（类型+方向）。

---

## 模式二：图算法发现

### Step 1: 运行发现

```bash
# 运行全部检查
python $SCRIPT discover --password 12345678

# 只运行特定检查
python $SCRIPT discover --type missing-relations --password 12345678
```

**7 种检查类型**：

| 类型 | 检查内容 | 优先级 |
|------|---------|--------|
| `orphans` | 零边的孤立节点 | 🟡 medium |
| `missing-relations` | 共享事件但无 relation 边的角色对 | 🔴 high |
| `events-no-location` | 无 occurred_at 边的事件 | 🟡 medium |
| `temporal-gaps` | 时间线上超过3天的空缺区间 | 🔴 high |
| `info-no-links` | 未被 link 边关联的 Info 节点 | 🟡 medium |
| `chars-no-faction` | 有活动但无 BELONGS_TO 边的角色 | 🟢 low |
| `events-unlinked` | 无 evt_relation 边的事件 | 🟢 low |

### Step 2: 呈现建议

将输出中的 `suggestions` 数组按优先级呈现给用户：

```
🔴 高优先级 (3条)
  1. 苏晓禾 和 沈暮雪 共同参与3个事件但无人物关系边
     → ADD_EDGE relation(<char_id_1>, <char_id_2>) {type: '?', detail: '?'}
  2. Day 10 到 Day 15 之间有 5 天空缺
     → 建议在 Day 11 ~ Day 14 之间补充事件
  ...

🟡 中优先级 (2条)
  1. 事件「陆择车祸死亡」缺少地点关联
     → ADD_EDGE occurred_at(<event_id>, <location_id>) {detail: '?'}
  ...

🟢 低优先级 (1条)
  1. 角色「陆择」参与了15个事件但无阵营归属
     → 如果属于某阵营: ADD_EDGE BELONGS_TO(<char_id>, <faction_id>) {role: '?'}
```

### Step 3: 用户确认后执行

用户选择要执行的建议，转入手动模式的 Step 3-5。

---

## 边方向速查

创建边时必须遵守方向规则：

| 边类型 | From → To | 属性 |
|--------|-----------|------|
| relation | Character → Character | type, detail |
| at | Character → Location | type, detail |
| link | 任意 → Info | type, detail, time |
| involved | Character → Event | role, detail |
| occurred_at | Event → Location | detail |
| evt_relation | Event → Event | type, detail |
| BELONGS_TO | Character → Faction | role |
| CATEGORIZED_AS | Location → LocationType | 无 |

---

## 错误处理

- **连接失败**：提示"请先启动 Neo4j 服务"
- **端点不存在**：报告缺失端点，建议先创建或通过名称查找确认 ID
- **重复边**：MERGE 幂等，不报错，报告"已存在"
- **方向错误**：脚本预校验边类型规则
