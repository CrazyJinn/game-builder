# CSV 格式规范与 LOAD CSV 导入模板

## CSV 格式规范

| 规则 | 说明 |
|------|------|
| 编码 | UTF-8 with BOM（Excel 兼容） |
| 分隔符 | 逗号 `,` |
| 引用 | 双引号 `"` 包裹含逗号/换行/引号的字段 |
| 转义 | 字段内双引号用 `""` 表示 |
| 表头 | 首行为列名，与叙事基础字段名一致 |
| 空值 | 必填列不可空，选填列留空（不写 NULL） |

### 引用示例

```csv
id,title,content,knowledge_level
<snowflake_id>,正常标题,正常内容,1
<snowflake_id>,"含逗号，需要引号","内容也有逗号，和换行
第二行",2
<snowflake_id>,含"引号"的标题,"内容含""引号""需转义",3
```

## 文件命名

- 节点: `nodes_{节点类型小写}.csv`（如 `nodes_char.csv`、`nodes_info.csv`、`nodes_location.csv`）
- 边: `edges_{边类型小写}.csv`（如 `edges_relation.csv`、`edges_involved.csv`）
- 导入脚本: `import.cypher`
- 摘要: `_summary.md`
- 输出目录: `01_叙事数据/csv/`

只生成有数据的文件。

## 列定义

### 节点 CSV

#### nodes_char.csv

| 列名 | 必填 | 类型 | 说明 |
|------|------|------|------|
| id | 是 | string | snowflake Base62 |
| name | 是 | string | |
| gender | 否 | string | 男/女 |
| description | 否 | string | 人物简介 |
| birth_year | 否 | int | 如 2003 |
| character_tags | 否 | string | 人设标签，逗号分隔，如"沉默寡言, 外冷内热" |

#### nodes_location.csv

| 列名 | 必填 | 类型 | 说明 |
|------|------|------|------|
| id | 是 | string | snowflake Base62 |
| name | 是 | string | |
| description | 否 | string | |

#### nodes_info.csv

| 列名 | 必填 | 类型 | 说明 |
|------|------|------|------|
| id | 是 | string | snowflake Base62 |
| title | 是 | string | |
| content | 是 | string | |
| knowledge_level | 是 | int | 1/2/3 |

#### nodes_event.csv

| 列名 | 必填 | 类型 | 说明 |
|------|------|------|------|
| id | 是 | string | snowflake Base62 |
| title | 是 | string | |
| time | 是 | string | 日期格式，如 2024-04-11 |
| description | 否 | string | |
| type | 否 | string | 行动/交流/转折/状态变化 |

### 边 CSV

所有边 CSV 均以 `from_id` 和 `to_id` 开头。

#### edges_relation.csv

Character → Character

| 列名 | 必填 | 说明 |
|------|------|------|
| from_id | 是 | Character id |
| to_id | 是 | Character id |
| type | 是 | 关系类型，如"恋爱""亲属""同事""仇人" |
| detail | 否 | 关系详情，如"恋爱中""已分手""姐弟" |
| start_time | 否 | 关系建立时间 |
| end_time | 否 | 关系结束时间（空=持续中） |

#### edges_involved.csv

Character → Event

| 列名 | 必填 | 说明 |
|------|------|------|
| from_id | 是 | Character id |
| to_id | 是 | Event id |
| role | 是 | 如"当事人""目击者""受害者""施害者""参与者" |
| detail | 否 | 角色详情 |

#### edges_occurred_at.csv

Event → Location

| 列名 | 必填 | 说明 |
|------|------|------|
| from_id | 是 | Event id |
| to_id | 是 | Location id |
| detail | 否 | 如"跳江地点""约会地点" |

#### edges_at.csv

Character → Location

| 列名 | 必填 | 说明 |
|------|------|------|
| from_id | 是 | Character id |
| to_id | 是 | Location id |
| type | 是 | 关联类型，如"居住""前往""工作" |
| detail | 否 | |
| start_time | 否 | 关联开始时间 |
| end_time | 否 | 关联结束时间（空=持续中） |

#### edges_link.csv

Character / Event / Location → Info（因果仅限 Info → Info）

| 列名 | 必填 | 说明 |
|------|------|------|
| from_id | 是 | Character/Event/Location/Info id |
| to_id | 是 | Info id |
| type | 是 | "涉及" 或 "因果" |
| detail | 否 | 关联说明 |
| time | 否 | 信息关联发生的时间 |

> type=`因果` 仅用于 Info → Info，表示原因→结果。
> from_id 仅限 Character、Event、Location、Info 四种节点。

#### edges_evt_relation.csv

Event → Event

| 列名 | 必填 | 说明 |
|------|------|------|
| from_id | 是 | Event id |
| to_id | 是 | Event id |
| type | 是 | "因果"/"先后"/"包含" |
| detail | 否 | 关联说明 |

> type 方向语义：因果 = 前因→后果；先后 = 时间顺序；包含 = 大事件→子事件

## LOAD CSV 导入模板

### import.cypher 格式规则

| 规则 | 说明 |
|------|------|
| 格式 | **内联 MERGE**，所有数据直接写在 cypher 中，不使用 LOAD CSV |
| 分隔符 | `;`（单分号），每条语句以 `;` 结尾 |
| 注释 | **不使用 `//` 注释**，说明写在 `_summary.md` |
| 导入顺序 | 节点在前，边在后；节点按 Character → Location → Event → Info 排列 |
| 字符串 | Cypher 单引号 `'...'`，内容中的 `'` 需转义为 `\'` |

> 不使用 LOAD CSV 的原因：LOAD CSV 的 `file:///` 依赖 Neo4j import 目录，内联 MERGE 可直接用 `cypher_exec.py -f --multi --json` 执行，零文件路径依赖。

> `//` 注释会导致 `cypher_exec.py` 的 `split_cypher_statements` 跳过整段语句，因此 import.cypher 中不得包含任何 `//` 注释。

### 节点模板

```cypher
MERGE (n:Character {id: '<id>'}) SET n.name = '<姓名>', n.gender = '<性别>', n.description = '<简介>', n.character_tags = '<标签>';
MERGE (n:Location {id: '<id>'}) SET n.name = '<名称>', n.description = '<描述>';
MERGE (n:Event {id: '<id>'}) SET n.title = '<标题>', n.time = '<时间>', n.description = '<描述>', n.type = '<类型>';
MERGE (n:Info {id: '<id>'}) SET n.title = '<标题>', n.content = '<内容>', n.knowledge_level = <1/2/3>;
```

### 边模板

```cypher
MATCH (a:Character {id: '<from_id>'}), (b:Character {id: '<to_id>'}) MERGE (a)-[:relation {type: '<关系类型>', detail: '<详情>'}]->(b);
MATCH (a:Character {id: '<from_id>'}), (b:Event {id: '<to_id>'}) MERGE (a)-[:involved {role: '<角色>', detail: '<详情>'}]->(b);
MATCH (a:Event {id: '<from_id>'}), (b:Location {id: '<to_id>'}) MERGE (a)-[:occurred_at {detail: '<详情>'}]->(b);
MATCH (a:Character {id: '<from_id>'}), (b:Location {id: '<to_id>'}) MERGE (a)-[:at {type: '<关联类型>', detail: '<详情>'}]->(b);
MATCH (a:Character {id: '<from_id>'}), (b:Info {id: '<to_id>'}) MERGE (a)-[:link {type: '涉及', detail: '<详情>', time: '<时间>'}]->(b);
MATCH (a:Info {id: '<from_id>'}), (b:Info {id: '<to_id>'}) MERGE (a)-[:link {type: '因果', detail: '<详情>'}]->(b);
MATCH (a:Event {id: '<from_id>'}), (b:Event {id: '<to_id>'}) MERGE (a)-[:evt_relation {type: '<因果/先后/包含>', detail: '<详情>'}]->(b);
```
