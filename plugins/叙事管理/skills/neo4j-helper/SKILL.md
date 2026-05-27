---
name: neo4j-helper
description: |
  Neo4j 自然语言查询助手。接收任意自然语言问题，基于图 Schema 自动生成 Cypher 并执行，
  以结构化方式返回结果。同时保留数据导入、去重、验证等管理能力。
  触发条件：(1) 用户向图数据库提出任何问题或查询请求
  (2) 用户提到"查图"、"图数据库"、"谁和谁"、"什么关系"、"事件"、"时间线"等查询意图
  (3) 用户要求将提取结果导入 Neo4j 或执行 Cypher
  (4) 用户要求查询 Neo4j 数据、检查图完整性、查看节点统计
  (5) 用户要求"查一下"、"看看"等涉及图数据内容的请求
  前置依赖：Neo4j 服务已启动，neo4j Python 包已安装（pip install neo4j）。
allowed-tools: Read, Bash, Write, Edit
---

# Neo4j Helper — 自然语言查询接口

接收自然语言问题 → 生成 Cypher → 执行 → 结构化返回结果。

## 连接配置

本地固定配置，无需环境变量：

- URI: `bolt://localhost:7687`
- User: `neo4j`
- Password: `12345678`

---

## 核心工作流：自然语言查询

### 第一步：理解用户意图

分析用户的自然语言问题，判断查询类型：
- **实体查询**：查某个/某些人物、地点、事件、信息
- **关系查询**：查两个实体之间的关系、关系路径
- **事件查询**：时间线、因果链、某个时间段的事件
- **统计查询**：数量、分布、排名、密度
- **信息层查询**：按知识层级查询信息
- **聚合查询**：跨实体、跨类型的复杂分析

### 第二步：获取图 Schema

查询前必须先读取 Schema 以生成正确的 Cypher。Schema 位于 `00_init/Schema.md`。

**图模型摘要（快速参考）：**

4 种节点：`char`（人物）、`Location`（地点）、`Info`（信息）、`Event`（事件）

6 种边：

| 边 | 方向 | 属性 |
|----|------|------|
| `relation` | char → char | type, detail |
| `at` | char → Location | type, detail |
| `link` | 任意 → Info | type, detail, time |
| `involved` | char → Event | role, detail |
| `occurred_at` | Event → Location | detail |
| `evt_relation` | Event → Event | type, detail |

节点通用主键：`编号`（char_NNN / loc_NNN / info_NNN / evt_NNN）

### 第三步：生成 Cypher

**规则：**
1. 所有查询必须使用参数化 Cypher（`$param`）防止注入
2. 只生成 MATCH/RETURN 查询，**绝不生成** CREATE/MERGE/DELETE/SET/DROP 等写操作
3. 为所有 MATCH 添加合理的 LIMIT（默认 100，关系查询可放宽到 300）
4. 使用 `COALESCE(n.姓名, n.名称, n.标题)` 处理不同节点的名称字段
5. 复杂查询拆分为多步，先获取 ID 再查关系

**生成模板参考（见 [references/cypher-templates.md](references/cypher-templates.md)）：**

| 用户意图 | Cypher 模式 |
|---------|------------|
| "某某是谁" / "查某角色" | `MATCH (n:char) WHERE n.姓名 CONTAINS $name RETURN n` |
| "A 和 B 什么关系" | `MATCH p=shortestPath((a:char)-[*..4]-(b:char)) ...` |
| "某角色参与的事件" | `MATCH (c:char)-[r:involved]->(e:Event) ...` |
| "时间线" / "事件按时间排" | `MATCH (e:Event) RETURN e ORDER BY e.时间` |
| "事件因果链" | `MATCH (e1:Event)-[r:evt_relation {type:'因果'}]->(e2:Event) ...` |
| "某地点发生了什么" | `MATCH (e:Event)-[:occurred_at]->(l:Location) ...` |
| "某信息的深层关联" | `MATCH (entity)-[r:link]->(i:Info {知识层: $level}) ...` |
| "图里有多少/统计" | `MATCH (n) RETURN labels(n)[0] AS type, count(*) AS count` |
| "关联最多的角色" | `MATCH (n)-[r]-() RETURN ... count(r) AS degree ORDER BY degree DESC` |

### 第四步：执行查询

使用 `execute_cypher.py` 执行生成的 Cypher：

```bash
python scripts/execute_cypher.py -c "<cypher>" --password <password> --json
```

或从文件执行复杂查询：

```bash
python scripts/query_graph.py <command> --password <password>
```

**执行原则：**
- 优先使用 `--json` 输出以便结构化解析
- 如果查询可能返回大量数据，先执行 COUNT 预估行数
- 查询失败时，根据错误信息调整 Cypher 并重试

### 第五步：结构化返回

将查询结果组织为结构化的自然语言回答，格式如下：

**单实体查询：**
```
## [实体类型] [名称]

| 属性 | 值 |
|------|-----|
| 编号 | char_001 |
| 姓名 | ... |
| ... | ... |

**关联关系：**
- → [关系类型] → [目标实体]
- ← [关系类型] ← [目标实体]
```

**关系查询：**
```
## [A] 与 [B] 的关系

[直接关系 / 最短路径 / 无直接关系]

路径：A —[关系]→ C —[关系]→ B
```

**列表/统计查询：**
```
## 查询结果（共 N 条）

| # | 字段1 | 字段2 | ... |
|---|-------|-------|-----|
| 1 | ... | ... | ... |
```

**事件时间线：**
```
## 时间线

- **2024-04-11**：[事件标题] — [类型]
- **2024-04-12**：[事件标题] — [类型]
  → 因果 → [下一个事件]
```

---

## Schema 探查（可选前置步骤）

如果不确定图中实际有哪些数据，先执行探查：

```bash
# 查看统计
python scripts/query_graph.py stats --password <password>

# 查看所有节点标签
python scripts/execute_cypher.py -c "CALL db.labels()" --password <password> --json

# 查看所有边类型
python scripts/execute_cypher.py -c "CALL db.relationshipTypes()" --password <password> --json

# 查看某标签的属性键
python scripts/execute_cypher.py -c "MATCH (n:char) WITH n LIMIT 1 RETURN keys(n) AS props" --password <password> --json
```

---

## 脚本清单

所有脚本位于 `scripts/` 目录。

### 查询类（自然语言查询主要使用）

| 脚本 | 用途 |
|------|------|
| `neo4j_client.py` | 连接客户端核心类（基础依赖） |
| `execute_cypher.py` | 执行任意 Cypher 查询（**主要入口**） |
| `query_graph.py` | 预定义查询（stats/nodes/relations/events/isolated/info） |

### 管理类（数据导入和维护）

| 脚本 | 用途 |
|------|------|
| `test_connection.py` | 连接测试 |
| `import_csv.py` | 导入 CSV 到 Neo4j |
| `check_dedup.py` | 去重检查与合并 |
| `verify_graph.py` | 图完整性验证 |

### 管理操作详细用法

**数据导入：**
```bash
# CSV 导入
python scripts/import_csv.py <csv_dir> --password <password>

# LOAD CSV 服务端导入
python scripts/import_csv.py <csv_dir> --password <password> --cypher <csv_dir>/import.cypher
```

**去重：**
```bash
python scripts/check_dedup.py check --password <password>
python scripts/check_dedup.py merge --label char --field 姓名 --keep char_001 --password <password>
```

**验证：**
```bash
python scripts/verify_graph.py --password <password>
```

---

## 错误处理

| 错误 | 原因 | 处理 |
|------|------|------|
| `ConnectionRefusedError` | Neo4j 未启动 | 提示用户启动 Neo4j 服务 |
| `AuthError` | 密码错误 | 检查 NEO4J_PASSWORD 环境变量 |
| `SyntaxError` | Cypher 语法错误 | 调整查询重试 |
| `NotFoundError` | 标签/属性不存在 | 用 Schema 探查确认实际结构 |
| 空结果 | 数据未导入或条件过严 | 放宽条件或建议先导入数据 |

---

## Resources

- [references/bolt-connection.md](references/bolt-connection.md) — bolt 连接配置
- [references/cypher-templates.md](references/cypher-templates.md) — Cypher 查询模板
- 项目 Schema：`00_init/Schema.md`
