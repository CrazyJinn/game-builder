---
name: neo4j-helper
description: |
  根据自然语言和图数据库 Schema 生成 Cypher 语句并执行，返回结构化结果。
  支持多语句、增删改查混杂。Schema 动态读取指定文件路径，适配不同图模型。
  触发条件：
  (1) 用户需要将自然语言转为 Cypher 并执行
  (2) 其他 skill 需要读写 Neo4j 数据（传入 schema_path 参数）
  (3) 用户提到"查图"、"图数据库"、"生成 cypher"、"导入数据"等
  (4) 用户要求测试 Neo4j 连接
  前置依赖：Neo4j 服务已启动，neo4j Python 包已安装（pip install neo4j）。
allowed-tools: Read, Bash
---

# Neo4j Skills — 生成并执行 Cypher

自然语言 + Schema → 生成 Cypher → 执行 → 结构化返回。

## 工作流

### 1. 接收输入

| 参数 | 说明 | 示例 |
|------|------|------|
| `自然语言描述` | 用户的意图描述 | "查询 char_001 的角色信息，然后把 status 改为 1" |
| `schema_path` | Schema 文件相对路径（可选，默认 `schema/Schema.md`） | `schema/01_叙事基础.md` |

### 2. 读取 Schema

用 Read 工具读取 `schema_path` 指定的文件，提取节点类型、边类型、属性、ID 规则。
只读取文件，不连接数据库。

### 3. 生成 Cypher

**最高原则：所有节点标签、边类型、属性名必须严格按照 schema 文件中定义的英文名，不得使用中文属性名，不得臆造字段。**

**规则：**

1. **直接内联值，不使用 `$param` 参数化查询**
2. 节点操作用 `MERGE`（幂等），而非 `CREATE`
3. 必须指定标签（如 `:Character`），不允许无标签操作
4. 节点和边的所有属性名以 schema 文件中的"字段"列（英文名）为准
5. 查询类语句添加 `LIMIT`（默认 100，关系/路径查询可放宽到 300）
6. 多条语句按执行顺序排列，确保依赖正确（先查后改、先节点后边）

**模板参考**：[references/cypher-templates.md](references/cypher-templates.md)

### 4. 执行

使用 `-c` 参数直接执行 Cypher 字符串（值已内联，无 `$param`）：

```bash
python "${CLAUDE_SKILL_DIR}/scripts/execute_cypher.py" -c "MATCH (n:Character {id: 'char_001'}) RETURN n" --json
```

多条语句用 `;` 分隔，加 `--multi` 开启事务模式：

```bash
python "${CLAUDE_SKILL_DIR}/scripts/execute_cypher.py" -c "MERGE (n:Character {id: 'char_001'}) SET n.name = '陆择'; MATCH (n:Character {id: 'char_001'}) RETURN n" --multi --json
```

如需传递较长 Cypher，使用 `--stdin` 管道：

```bash
cat <<'EOF' | python "${CLAUDE_SKILL_DIR}/scripts/execute_cypher.py" --stdin --multi --json
MERGE (n:Character {id: 'char_001'}) SET n.name = '陆择';
MATCH (n:Character {id: 'char_001'}) RETURN n;
EOF
```

#### 写入操作

`execute_cypher.py` 的 `--json` 输出会包含创建/更新/删除的统计。

### 5. 结果格式化

| 查询类型 | 输出格式 |
|---------|---------|
| 单实体 | 属性表格 + 关联关系列表 |
| 关系路径 | 路径描述：A —[关系]→ C —[关系]→ B |
| 列表/统计 | 编号表格 |
| 时间线 | 按时间排列的事件列表，标注因果链 |
| 写入操作 | 统计信息（创建/更新/删除数量） |

---

## Schema 探查

不确定图中数据结构时：

```bash
python "${CLAUDE_SKILL_DIR}/scripts/execute_cypher.py" -c "CALL db.labels()" --json
python "${CLAUDE_SKILL_DIR}/scripts/execute_cypher.py" -c "CALL db.relationshipTypes()" --json
python "${CLAUDE_SKILL_DIR}/scripts/execute_cypher.py" -c "MATCH (n) WITH n LIMIT 1 RETURN keys(n) AS props" --json
```

## 连接测试

```bash
python "${CLAUDE_SKILL_DIR}/scripts/test_connection.py"
```

## 连接配置

优先级从高到低：

1. 命令行参数 `--uri` / `--user` / `--password`
2. 环境变量 `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD`
3. 插件配置 `CLAUDE_PLUGIN_OPTION_neo4j_password`（自动注入）
4. 默认值：`bolt://localhost:7687` / `neo4j` / `12345678`

## 错误处理

| 错误 | 原因 | 处理 |
|------|------|------|
| `ConnectionRefusedError` | Neo4j 未启动 | 提示用户启动 Neo4j 服务 |
| `AuthError` | 密码错误 | 检查环境变量或插件配置 |
| `SyntaxError` | Cypher 语法错误 | 调整查询重试 |
| `NotFoundError` | 标签/属性不存在 | 用 Schema 探查确认实际结构 |
| 空结果 | 数据未导入或条件过严 | 放宽条件或建议先导入数据 |

## 脚本清单

所有脚本位于 `${CLAUDE_SKILL_DIR}/scripts/`。

| 脚本 | 用途 |
|------|------|
| `neo4j_client.py` | 连接客户端核心类（基础依赖） |
| `execute_cypher.py` | 执行任意 Cypher（**主要入口**，支持 `-c`/`-f`/`--stdin`/`--multi`/`--json`） |
| `test_connection.py` | 连接测试 |

## Resources

- [references/cypher-templates.md](references/cypher-templates.md) — Cypher 全量模板（CRUD + 查询 + 批量 + 美术图构建 + Sync 级联）
- [references/bolt-connection.md](references/bolt-connection.md) — Bolt 连接配置
