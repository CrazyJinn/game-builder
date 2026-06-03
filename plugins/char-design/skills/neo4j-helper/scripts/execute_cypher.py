"""
执行 Cypher 查询脚本
支持从文件、命令行参数或 stdin 执行 Cypher，输出 JSON 结果。
支持多语句事务模式（--multi）。
"""

import os
import sys
import json
import argparse
from urllib.parse import urlparse, unquote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_client import Neo4jClient


def resolve_file_path(path):
    """解析文件路径，支持 file:/// URI 和普通路径"""
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
    """将多语句文本按 ; 分割为独立 Cypher 语句列表"""
    statements = []
    for stmt in text.split(";"):
        stripped = stmt.strip()
        # 跳过空语句和纯注释
        if stripped and not stripped.startswith("//"):
            statements.append(stripped)
    return statements


def execute_and_print(client, cypher, output_json=False):
    """执行单条 Cypher 并打印结果"""
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
    """在单个事务中执行多条 Cypher（按 ; 分割），打印结果"""
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="执行 Cypher 查询")
    parser.add_argument("--uri", default=os.environ.get("NEO4J_URI", "bolt://localhost:7687"))
    parser.add_argument("--user", default=os.environ.get("NEO4J_USER", "neo4j"))
    parser.add_argument("--password", default=os.environ.get("NEO4J_PASSWORD", ""))
    parser.add_argument("-c", "--cypher", help="要执行的 Cypher 语句（注意：$param 会被 Shell 解析，推荐用 -f 或 --stdin）")
    parser.add_argument("-f", "--file", help="要执行的 .cypher 文件路径（支持 file:/// URI）")
    parser.add_argument("--stdin", action="store_true", help="从标准输入读取 Cypher")
    parser.add_argument("--multi", action="store_true", help="多语句事务模式：按 ; 分割，在单个事务中顺序执行")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    args = parser.parse_args()

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
        if args.multi:
            execute_multi_and_print(client, cypher, args.json)
        else:
            execute_and_print(client, cypher, args.json)
