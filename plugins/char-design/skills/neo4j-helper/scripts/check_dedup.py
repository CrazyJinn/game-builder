"""
去重检查脚本
检测 Neo4j 中的重复节点和冗余关系
"""

import os
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_client import Neo4jClient


def check_duplicate_ids(client):
    """检查每种节点类型中是否有重复编号"""
    labels = ["char", "Location", "Info", "Event"]
    issues = []

    for label in labels:
        result = client.run(
            f"MATCH (n:{label}) "
            f"WITH n.编号 AS id, collect(n) AS nodes "
            f"WHERE size(nodes) > 1 "
            f"RETURN id, size(nodes) AS dup_count"
        )
        if result:
            for row in result:
                issues.append({
                    "type": "重复编号",
                    "label": label,
                    "编号": row["id"],
                    "重复数量": row["dup_count"],
                })

    return issues


def check_duplicate_names(client):
    """检查名称/姓名相同的节点"""
    checks = [
        ("char", "姓名"),
        ("Location", "名称"),
        ("Info", "标题"),
        ("Event", "标题"),
    ]
    warnings = []

    for label, field in checks:
        result = client.run(
            f"MATCH (n:{label}) "
            f"WITH n.`{field}` AS val, collect(n.编号) AS ids "
            f"WHERE size(ids) > 1 AND val IS NOT NULL AND val <> '' "
            f"RETURN val, ids"
        )
        if result:
            for row in result:
                warnings.append({
                    "type": "疑似重名",
                    "label": label,
                    "字段": field,
                    "值": row["val"],
                    "编号列表": row["ids"],
                })

    return warnings


def check_duplicate_edges(client):
    """检查重复边（同类型同方向同 from/to）"""
    edge_types = ["relation", "at", "link", "involved", "occurred_at", "evt_relation"]
    issues = []

    for etype in edge_types:
        result = client.run(
            f"MATCH (a)-[r:{etype}]->(b) "
            f"WITH a.编号 AS from_id, b.编号 AS to_id, count(r) AS cnt "
            f"WHERE cnt > 1 "
            f"RETURN from_id, to_id, cnt"
        )
        if result:
            for row in result:
                issues.append({
                    "type": "重复边",
                    "边类型": etype,
                    "from": row["from_id"],
                    "to": row["to_id"],
                    "数量": row["cnt"],
                })

    return issues


def merge_duplicates(client, label, field, keep_id):
    """合并重复节点：将 keep_id 以外的节点的边迁移到 keep_id，然后删除重复节点"""
    # 查找所有同字段的节点
    result = client.run(
        f"MATCH (n:{label}) WHERE n.`{field}` IS NOT NULL "
        f"RETURN n.编号 AS id, n.`{field}` AS val"
    )

    from collections import defaultdict
    groups = defaultdict(list)
    for row in result:
        groups[row["val"]].append(row["id"])

    merged = 0
    for val, ids in groups.items():
        if len(ids) < 2:
            continue
        if keep_id not in ids:
            continue
        # 迁移其他节点的边到保留节点
        for dup_id in ids:
            if dup_id == keep_id:
                continue
            # 入边
            client.run_write(
                f"MATCH (other)-[r]->(dup:{label} {{编号: '{dup_id}'}}) "
                f"MATCH (keep:{label} {{编号: '{keep_id}'}}) "
                f"CREATE (other)-[r2]->(keep) SET r2 = properties(r) "
                f"DELETE r"
            )
            # 出边
            client.run_write(
                f"MATCH (dup:{label} {{编号: '{dup_id}'}})-[r]->(other) "
                f"MATCH (keep:{label} {{编号: '{keep_id}'}}) "
                f"CREATE (keep)-[r2]->(other) SET r2 = properties(r) "
                f"DELETE r"
            )
            # 删除重复节点
            client.run_write(
                f"MATCH (dup:{label} {{编号: '{dup_id}'}}) DELETE dup"
            )
            merged += 1
            print(f"  合并: {dup_id} -> {keep_id} ({label}.{field}={val})")

    return merged


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Neo4j 去重检查")
    parser.add_argument("--uri", default=os.environ.get("NEO4J_URI", "bolt://localhost:7687"))
    parser.add_argument("--user", default=os.environ.get("NEO4J_USER", "neo4j"))
    parser.add_argument("--password", default=os.environ.get("NEO4J_PASSWORD", ""))
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("check", help="检查所有去重问题")
    sub.add_parser("check-ids", help="仅检查重复编号")
    sub.add_parser("check-names", help="仅检查重名")
    sub.add_parser("check-edges", help="仅检查重复边")

    p_merge = sub.add_parser("merge", help="合并重复节点")
    p_merge.add_argument("--label", required=True, help="节点标签")
    p_merge.add_argument("--field", required=True, help="匹配字段")
    p_merge.add_argument("--keep", required=True, help="保留的节点编号")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    with Neo4jClient(args.uri, args.user, args.password) as client:
        if args.command in ("check", "check-ids"):
            issues = check_duplicate_ids(client)
            if issues:
                print("=== 重复编号 ===")
                for i in issues:
                    print(f"  [{i['label']}] {i['编号']} 重复 {i['重复数量']} 次")
            elif args.command == "check-ids":
                print("无重复编号")

        if args.command in ("check", "check-names"):
            warnings = check_duplicate_names(client)
            if warnings:
                print("\n=== 疑似重名 ===")
                for w in warnings:
                    print(f"  [{w['label']}] {w['字段']}=\"{w['值']}\" → 编号: {w['编号列表']}")
            elif args.command == "check":
                print("\n无重名问题")

        if args.command in ("check", "check-edges"):
            issues = check_duplicate_edges(client)
            if issues:
                print("\n=== 重复边 ===")
                for i in issues:
                    print(f"  [{i['边类型']}] {i['from']} -> {i['to']} ({i['数量']} 条)")
            elif args.command == "check":
                print("\n无重复边")

        if args.command == "merge":
            count = merge_duplicates(client, args.label, args.field, args.keep)
            print(f"\n合并完成: 迁移并删除 {count} 个重复节点")
