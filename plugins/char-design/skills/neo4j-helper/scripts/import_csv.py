"""
CSV 数据导入 Neo4j
从 narrative-csv-extractor 输出的 CSV 文件导入节点和边
支持 LOAD CSV (服务端导入) 和逐行 MERGE (客户端导入) 两种模式
"""

import os
import sys
import csv
import argparse
import glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_client import Neo4jClient


# === Schema 定义：节点类型 → 标签和属性映射 ===

NODE_SCHEMAS = {
    "char": {
        "label": "char",
        "id_field": "编号",
        "set_fields": ["姓名", "性别", "description", "出生年份"],
    },
    "location": {
        "label": "Location",
        "id_field": "编号",
        "set_fields": ["名称", "描述"],
    },
    "info": {
        "label": "Info",
        "id_field": "编号",
        "set_fields": ["标题", "内容"],
        "int_fields": ["知识层"],
    },
    "event": {
        "label": "Event",
        "id_field": "编号",
        "set_fields": ["标题", "时间", "描述", "类型"],
    },
}

EDGE_SCHEMAS = {
    "relation": {
        "from_label": "char", "to_label": "char",
        "fields": ["type", "detail"],
    },
    "at": {
        "from_label": "char", "to_label": "Location",
        "fields": ["type", "detail"],
    },
    "link": {
        "from_label": None, "to_label": "Info",
        "fields": ["type", "detail", "time"],
    },
    "involved": {
        "from_label": "char", "to_label": "Event",
        "fields": ["role", "detail"],
    },
    "occurred_at": {
        "from_label": "Event", "to_label": "Location",
        "fields": ["detail"],
    },
    "evt_relation": {
        "from_label": "Event", "to_label": "Event",
        "fields": ["type", "detail"],
    },
}


def _build_node_cypher(schema, row):
    """构建节点 MERGE 语句"""
    label = schema["label"]
    id_field = schema["id_field"]
    id_val = row.get(id_field, "").strip()
    if not id_val:
        return None

    props = []
    for field in schema.get("set_fields", []):
        val = row.get(field, "").strip()
        if val:
            escaped = val.replace("'", "\\'").replace('"', '\\"')
            props.append(f"n.{field} = '{escaped}'")
    for field in schema.get("int_fields", []):
        val = row.get(field, "").strip()
        if val:
            props.append(f"n.{field} = toInteger('{val}')")

    set_clause = ",\n    ".join(props) if props else ""
    cypher = f"MERGE (n:{label} {{{id_field}: '{id_val}'}})"
    if set_clause:
        cypher += f"\nSET {set_clause}"
    return cypher


def _build_edge_cypher(edge_type, schema, row):
    """构建边 MERGE 语句"""
    from_id = row.get("from_id", "").strip()
    to_id = row.get("to_id", "").strip()
    if not from_id or not to_id:
        return None

    from_label = schema["from_label"]
    to_label = schema["to_label"]

    # link 边的 from 可以是任意类型，需要动态查找
    if from_label is None:
        match_from = f"MATCH (a {{编号: '{from_id}'}})"
    else:
        match_from = f"MATCH (a:{from_label} {{编号: '{from_id}'}})"

    match_to = f"MATCH (b:{to_label} {{编号: '{to_id}'}})"

    props = []
    for field in schema["fields"]:
        val = row.get(field, "").strip()
        if val:
            escaped = val.replace("'", "\\'").replace('"', '\\"')
            props.append(f"{field}: '{escaped}'")

    props_clause = ", ".join(props)
    if props_clause:
        edge = f"[:{edge_type} {{{props_clause}}}]"
    else:
        edge = f"[:{edge_type}]"

    return f"{match_from}\n{match_to}\nMERGE (a)-{edge}->(b)"


def import_nodes(client, csv_dir):
    """导入所有节点 CSV"""
    total_created = 0
    for node_type, schema in NODE_SCHEMAS.items():
        pattern = os.path.join(csv_dir, f"nodes_{node_type}.csv")
        files = glob.glob(pattern)
        if not files:
            continue

        filepath = files[0]
        print(f"\n导入 {node_type} 节点: {filepath}")

        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                cypher = _build_node_cypher(schema, row)
                if cypher:
                    client.run_write(cypher)
                    count += 1

        print(f"  处理 {count} 条 {node_type} 节点")
        total_created += count

    return total_created


def import_edges(client, csv_dir):
    """导入所有边 CSV"""
    total_created = 0
    for edge_type, schema in EDGE_SCHEMAS.items():
        pattern = os.path.join(csv_dir, f"edges_{edge_type}.csv")
        files = glob.glob(pattern)
        if not files:
            continue

        filepath = files[0]
        print(f"\n导入 {edge_type} 边: {filepath}")

        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                cypher = _build_edge_cypher(edge_type, schema, row)
                if cypher:
                    client.run_write(cypher)
                    count += 1

        print(f"  处理 {count} 条 {edge_type} 边")
        total_created += count

    return total_created


def import_from_cypher_file(client, cypher_path):
    """执行 import.cypher 文件（LOAD CSV 方式）"""
    print(f"\n执行 Cypher 文件: {cypher_path}")
    with open(cypher_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 按 ;; 分割语句
    statements = [s.strip() for s in content.split(";;") if s.strip()]
    results = client.run_in_transaction(statements)
    print(f"  执行了 {len(statements)} 条语句")
    return len(statements)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="导入 CSV 数据到 Neo4j")
    parser.add_argument("csv_dir", help="包含 CSV 文件的目录路径")
    parser.add_argument("--uri", default=os.environ.get("NEO4J_URI", "bolt://localhost:7687"))
    parser.add_argument("--user", default=os.environ.get("NEO4J_USER", "neo4j"))
    parser.add_argument("--password", default=os.environ.get("NEO4J_PASSWORD", ""))
    parser.add_argument("--cypher", help="直接执行 import.cypher 文件（LOAD CSV 模式）")
    args = parser.parse_args()

    with Neo4jClient(args.uri, args.user, args.password) as client:
        if args.cypher:
            import_from_cypher_file(client, args.cypher)
        else:
            node_count = import_nodes(client, args.csv_dir)
            edge_count = import_edges(client, args.csv_dir)
            print(f"\n导入完成: {node_count} 个节点, {edge_count} 条边")
