"""
执行 Cypher 查询脚本
支持从文件或命令行参数执行 Cypher，输出 JSON 结果
"""

import os
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_client import Neo4jClient


def execute_and_print(client, cypher, output_json=False):
    """执行 Cypher 并打印结果"""
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="执行 Cypher 查询")
    parser.add_argument("--uri", default=os.environ.get("NEO4J_URI", "bolt://localhost:7687"))
    parser.add_argument("--user", default=os.environ.get("NEO4J_USER", "neo4j"))
    parser.add_argument("--password", default=os.environ.get("NEO4J_PASSWORD", ""))
    parser.add_argument("-c", "--cypher", help="要执行的 Cypher 语句")
    parser.add_argument("-f", "--file", help="要执行的 .cypher 文件路径")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    args = parser.parse_args()

    if not args.cypher and not args.file:
        parser.error("请提供 -c Cypher 语句或 -f .cypher 文件")

    cypher = args.cypher
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            cypher = f.read()

    with Neo4jClient(args.uri, args.user, args.password) as client:
        execute_and_print(client, cypher, args.json)
