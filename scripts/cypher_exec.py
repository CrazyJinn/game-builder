"""
cypher_exec.py — Neo4j Cypher 执行脚本（统一图读写入口）

所有 skill 读写 Neo4j 图数据库的唯一脚本。Cypher 由调用方（LLM）即时生成，
本脚本只负责执行与结构化返回。连接 bolt://localhost:7687，user neo4j。

密码来源：
    --password  >  NEO4J_PASSWORD 环境变量  >  工作目录向上搜索的 settings.json: neo4j_password

CLI 用法：
    # 单条查询，JSON 输出
    python ${CLAUDE_SKILL_DIR}/../../scripts/cypher_exec.py -c "MATCH (n:Character) RETURN n.name AS name" --json

    # 多语句文件，单事务执行（导入场景）
    python ${CLAUDE_SKILL_DIR}/../../scripts/cypher_exec.py -f path/to/import.cypher --multi --json

    # 从 stdin
    echo "MATCH (n) RETURN count(n) AS c" | python ${CLAUDE_SKILL_DIR}/../../scripts/cypher_exec.py --stdin --json

    # 裸标量输出（管道消费，如取一个 id）
    python ${CLAUDE_SKILL_DIR}/../../scripts/cypher_exec.py -c "MATCH (c:Character {name:'陆择'}) RETURN c.id" --raw

作为模块导入（被 graph_builder.py 等脚本复用连接客户端）：
    from cypher_exec import Neo4jClient, create_client
    with Neo4jClient() as client:
        rows = client.run("MATCH (n) RETURN n LIMIT 5")
        stats = client.run_write("MERGE (n:Test {id:'x'})")  # 返回 nodes_created 等
        results = client.run_in_transaction(["MATCH (a) RETURN a", "MATCH (b) RETURN b"])

支持 -c/-f/--stdin/--multi/--json/--raw。--multi 按 ; 分割多语句在单事务顺序执行，
正确处理字符串字面量内的 ; 与行注释 //。

── 写 Cypher 的核心约束（skill 生成 Cypher 时遵循）────────────

1. 先读 Schema：用 Read 工具读 00_init/Schema/*.md，按其中的节点/边/属性英文名与
   方向生成 Cypher。Schema 是唯一事实来源。
2. 直接内联值，不用 $param：CLI 下 $param 会被 Shell 解析。值直接写进语句字面量
   （字符串用单引号，转义内部单引号）。长语句用 -f 文件或 --stdin。
3. 写操作用 MERGE：保证幂等，重复执行不产生重复节点/边。
4. 必须指定标签：MERGE (n:DesignSheet {id:'...'})，不要裸 MERGE (n {id:...})。
5. 属性名严格按 Schema 英文名：如 prompt_path、image_path、status、sync。
6. 查询加 LIMIT：避免全表扫描，如 ... RETURN n LIMIT 50。
7. 多语句按依赖排序：先建节点、再建边；--multi 在单事务内顺序执行。
8. status 白名单：仅 -1/0/1/2/10/11（见 00_init/Schema/角色美术.md 与
   55_dashboard/core/status.py）。生产态 0/1/2，审批专属 10(待审)/11(批准)，作废 -1。
"""

import os
import sys
import json
import argparse
from pathlib import Path
from urllib.parse import urlparse, unquote

from neo4j import GraphDatabase


# ─── 连接配置 ────────────────────────────────────────────────

def find_settings() -> dict:
    """从当前工作目录向上搜索 settings.json（最多 8 层）。"""
    dir_path = Path(os.getcwd()).resolve()
    for _ in range(8):
        candidate = dir_path / "settings.json"
        if candidate.exists():
            with open(candidate, "r", encoding="utf-8") as f:
                return json.load(f)
        parent = dir_path.parent
        if parent == dir_path:
            break
        dir_path = parent
    return {}


class Neo4jClient:
    """Neo4j 连接客户端，使用 bolt:// 协议。"""

    def __init__(self, uri=None, user=None, password=None):
        self.uri = uri or os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        self.user = user or os.environ.get("NEO4J_USER", "neo4j")
        # 密码优先级：显式参数 > 环境变量 > settings.json（无硬编码默认）
        self.password = (
            password
            or os.environ.get("NEO4J_PASSWORD")
            or find_settings().get("neo4j_password")
        )
        self.driver = None

    def connect(self):
        """建立连接。"""
        if not self.password:
            print(
                "错误：未设置密码。请在工作目录的 settings.json 设置 neo4j_password 字段，"
                "或通过 --password / NEO4J_PASSWORD 环境变量提供。",
                file=sys.stderr,
            )
            sys.exit(1)
        self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
        self.driver.verify_connectivity()
        print(f"已连接: {self.uri}", file=sys.stderr)
        return self

    def close(self):
        """关闭连接。"""
        if self.driver:
            self.driver.close()
            print("连接已关闭", file=sys.stderr)

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.close()

    def run_query(self, cypher, parameters=None):
        """run() 的别名。"""
        return self.run(cypher, parameters)

    def run(self, cypher, parameters=None):
        """执行单条 Cypher，返回结果列表。"""
        with self.driver.session() as session:
            result = session.run(cypher, parameters or {})
            return [record.data() for record in result]

    def run_in_transaction(self, cypher_list):
        """在单个事务中顺序执行多条 Cypher。"""
        with self.driver.session() as session:
            with session.begin_transaction() as tx:
                results = []
                for cypher in cypher_list:
                    cypher = cypher.strip()
                    if not cypher or cypher.startswith("//"):
                        continue
                    result = tx.run(cypher)
                    results.append([record.data() for record in result])
                tx.commit()
                return results

    def run_write(self, cypher, parameters=None):
        """执行写操作（MERGE/CREATE/SET），返回统计信息。"""
        with self.driver.session() as session:
            result = session.run(cypher, parameters or {})
            summary = result.consume()
            counters = summary.counters
            return {
                "nodes_created": counters.nodes_created,
                "nodes_deleted": counters.nodes_deleted,
                "relationships_created": counters.relationships_created,
                "relationships_deleted": counters.relationships_deleted,
                "properties_set": counters.properties_set,
                "labels_added": counters.labels_added,
            }


def create_client(uri=None, user=None, password=None):
    """工厂函数：创建并连接客户端。"""
    client = Neo4jClient(uri, user, password)
    client.connect()
    return client


# ─── Cypher 文本处理 ──────────────────────────────────────────

def resolve_file_path(path):
    """解析文件路径，支持 file:/// URI 和普通路径。"""
    if path.startswith("file:///"):
        # file:///D:/foo/bar.cypher → D:/foo/bar.cypher
        parsed = urlparse(path)
        resolved = unquote(parsed.path)
        # Windows: 去掉开头的 /
        if resolved.startswith("/") and len(resolved) > 2 and resolved[2] == ":":
            resolved = resolved[1:]
        return resolved
    return path


def split_cypher_statements(text):
    """将多语句文本按 ; 分割为独立 Cypher 语句列表。

    正确处理：
    - 字符串字面量内的 ;（不作为分隔符）
    - 行注释 //：仅当不在字符串字面量内时视为注释，剥离整行；
      字符串内的 //（如 URL）不会被误判。
    """
    statements = []
    current = []
    in_string = False       # 是否在字符串字面量内
    string_char = None      # 当前字符串的引号字符 (' 或 ")
    escape_next = False     # 上一个字符是否为转义符 \

    i = 0
    n = len(text)
    while i < n:
        ch = text[i]

        # 行注释 //（仅当不在字符串内）：跳过到行尾，不写入 current
        if not in_string and ch == '/' and i + 1 < n and text[i + 1] == '/':
            while i < n and text[i] != '\n':
                i += 1
            continue  # 留下 \n 给主循环处理（保持换行语义）

        if escape_next:
            current.append(ch)
            escape_next = False
            i += 1
            continue
        if ch == '\\' and in_string:
            current.append(ch)
            escape_next = True
            i += 1
            continue
        if in_string:
            current.append(ch)
            if ch == string_char:
                in_string = False
            i += 1
            continue
        # 不在字符串内
        if ch in ("'", '"'):
            current.append(ch)
            in_string = True
            string_char = ch
        elif ch == ';':
            stmt = ''.join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
        else:
            current.append(ch)
        i += 1

    # 处理末尾无 ; 的残余
    stmt = ''.join(current).strip()
    if stmt:
        statements.append(stmt)

    return statements


# ─── 执行与输出 ───────────────────────────────────────────────

def execute_and_print(client, cypher, output_json=False):
    """执行单条 Cypher 并打印结果。"""
    results = client.run(cypher)
    if output_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        if not results:
            print("(无结果)")
            return
        # 打印表格
        keys = list(results[0].keys())
        col_widths = {k: max(len(str(k)), *(len(str(r.get(k, ""))) for r in results)) for k in keys}
        col_widths = {k: min(w, 40) for k, w in col_widths.items()}

        header = " | ".join(k.ljust(col_widths[k]) for k in keys)
        sep = "-+-".join("-" * col_widths[k] for k in keys)
        print(header)
        print(sep)
        for row in results:
            line = " | ".join(str(row.get(k, ""))[:col_widths[k]].ljust(col_widths[k]) for k in keys)
            print(line)
        print(f"\n({len(results)} 行)")


def execute_multi_and_print(client, cypher_text, output_json=False):
    """在单个事务中执行多条 Cypher（按 ; 分割），打印结果。"""
    statements = split_cypher_statements(cypher_text)
    if not statements:
        print("(无有效语句)")
        return

    results = client.run_in_transaction(statements)
    if output_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for i, (stmt, res) in enumerate(zip(statements, results), 1):
            # 截断显示语句
            preview = stmt.replace("\n", " ")[:80]
            print(f"\n--- 语句 {i}: {preview}{'...' if len(stmt) > 80 else ''} ---")
            if not res:
                print("(无结果)")
            else:
                keys = list(res[0].keys())
                col_widths = {k: max(len(str(k)), *(len(str(r.get(k, ""))) for r in res)) for k in keys}
                col_widths = {k: min(w, 40) for k, w in col_widths.items()}
                header = " | ".join(k.ljust(col_widths[k]) for k in keys)
                sep = "-+-".join("-" * col_widths[k] for k in keys)
                print(header)
                print(sep)
                for row in res:
                    line = " | ".join(str(row.get(k, ""))[:col_widths[k]].ljust(col_widths[k]) for k in keys)
                    print(line)
                print(f"({len(res)} 行)")


def execute_raw_and_print(client, cypher):
    """执行单条 Cypher，仅当结果为单行单列标量时输出裸值到 stdout（管道消费专用）。"""
    results = client.run(cypher)
    if len(results) != 1:
        print(f"错误：--raw 模式要求结果恰好 1 行，实际 {len(results)} 行", file=sys.stderr)
        sys.exit(1)
    row = results[0]
    if len(row) != 1:
        print(f"错误：--raw 模式要求结果恰好 1 列，实际 {len(row)} 列: {list(row.keys())}", file=sys.stderr)
        sys.exit(1)
    value = next(iter(row.values()))
    if value is None:
        print("错误：--raw 模式结果为 null（目标字段可能未设置）", file=sys.stderr)
        sys.exit(1)
    if isinstance(value, (list, dict)):
        print(f"错误：--raw 模式要求标量值，实际复合类型 {type(value).__name__}", file=sys.stderr)
        sys.exit(1)
    sys.stdout.write(str(value))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="执行 Cypher 查询")
    parser.add_argument("--uri", default=os.environ.get("NEO4J_URI", "bolt://localhost:7687"))
    parser.add_argument("--user", default=os.environ.get("NEO4J_USER", "neo4j"))
    parser.add_argument("--password", default=None, help="Neo4j 密码（默认读 NEO4J_PASSWORD 环境变量或 settings.json）")
    parser.add_argument("-c", "--cypher", help="要执行的 Cypher 语句（注意：$param 会被 Shell 解析，推荐用 -f 或 --stdin）")
    parser.add_argument("-f", "--file", help="要执行的 .cypher 文件路径（支持 file:/// URI）")
    parser.add_argument("--stdin", action="store_true", help="从标准输入读取 Cypher")
    parser.add_argument("--multi", action="store_true", help="多语句事务模式：按 ; 分割，在单个事务中顺序执行")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    parser.add_argument("--raw", action="store_true", help="裸标量输出：仅当结果为单行单列标量时，输出裸值到 stdout（管道消费专用，不加 JSON/表格包装）")
    args = parser.parse_args()

    if args.raw and (args.multi or args.json):
        parser.error("--raw 与 --multi/--json 互斥")

    # 收集 Cypher 输入
    cypher = None
    if args.stdin:
        cypher = sys.stdin.read()
    elif args.file:
        file_path = resolve_file_path(args.file)
        with open(file_path, "r", encoding="utf-8") as f:
            cypher = f.read()
    elif args.cypher:
        cypher = args.cypher

    if not cypher:
        parser.error("请提供 -c Cypher 语句、-f .cypher 文件或 --stdin")

    with Neo4jClient(args.uri, args.user, args.password) as client:
        if args.raw:
            execute_raw_and_print(client, cypher)
        elif args.multi:
            execute_multi_and_print(client, cypher, args.json)
        else:
            execute_and_print(client, cypher, args.json)
