# Bolt 连接配置指南

## 连接参数

| 参数 | 默认值 | 环境变量 | 说明 |
|------|--------|---------|------|
| URI | `bolt://localhost:7687` | `NEO4J_URI` | bolt:// 协议连接 |
| User | `neo4j` | `NEO4J_USER` | 用户名 |
| Password | 12345678 | `NEO4J_PASSWORD` | 密码（必须） |

## 使用方式

### 1. 环境变量（推荐）

```bash
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="12345678"
```

### 2. 命令行参数

```bash
python scripts/test_connection.py --uri bolt://localhost:7687 --user neo4j --password your_password
```

### 3. 代码中直接使用

```python
from neo4j_client import Neo4jClient

# 方式一：with 语句自动管理连接
with Neo4jClient(password="your_password") as client:
    result = client.run("MATCH (n) RETURN count(n) AS total")

# 方式二：手动管理
client = Neo4jClient(password="your_password")
client.connect()
result = client.run("MATCH (n) RETURN count(n) AS total")
client.close()
```

### 4. Claude 执行命令模板

```
python scripts/test_connection.py --password <password>
python scripts/import_csv.py <csv_dir> --password <password>
python scripts/execute_cypher.py -c "MATCH (n) RETURN n LIMIT 10" --password <password>
python scripts/query_graph.py stats --password <password>
python scripts/check_dedup.py check --password <password>
python scripts/verify_graph.py --password <password>
```

## Neo4j 服务管理

### 启动/停止（Windows）

```bash
# Neo4j Desktop: 通过 GUI 操作
# 或命令行:
neo4j console        # 前台运行
neo4j start          # 后台服务启动
neo4j stop           # 停止
neo4j status         # 查看状态
```

### 验证 bolt 端口

```bash
# 测试端口是否监听
netstat -an | findstr 7687
```

### neo4j.conf 关键配置

```properties
# 启用 bolt 连接
dbms.connector.bolt.enabled=true
dbms.connector.bolt.listen_address=0.0.0.0:7687

# 导入目录（LOAD CSV 使用）
dbms.directories.import=import
```

## Python 依赖

```bash
pip install neo4j
```

最低版本要求：`neo4j >= 5.0`
