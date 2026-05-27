"""
图完整性验证脚本
检查节点数、边数、孤立节点、引用完整性等
"""

import os
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_client import Neo4jClient


def verify_graph(client):
    """执行完整验证，返回报告"""
    report = {"passed": [], "warnings": [], "errors": []}

    # 1. 节点统计
    node_stats = client.run(
        "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS count ORDER BY label"
    )
    total_nodes = sum(r["count"] for r in node_stats)
    report["node_stats"] = node_stats
    print(f"\n[节点统计] 共 {total_nodes} 个节点:")
    for r in node_stats:
        print(f"  {r['label']}: {r['count']}")

    if total_nodes == 0:
        report["warnings"].append("数据库中无节点")
    else:
        report["passed"].append(f"节点统计: {total_nodes} 个节点")

    # 2. 边统计
    edge_stats = client.run(
        "MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS count ORDER BY type"
    )
    total_edges = sum(r["count"] for r in edge_stats)
    report["edge_stats"] = edge_stats
    print(f"\n[边统计] 共 {total_edges} 条边:")
    for r in edge_stats:
        print(f"  {r['type']}: {r['count']}")

    # 3. 孤立节点
    isolated = client.run(
        "MATCH (n) WHERE NOT (n)--() "
        "RETURN labels(n)[0] AS type, n.编号 AS id, "
        "COALESCE(n.姓名, n.名称, n.标题) AS name"
    )
    report["isolated_nodes"] = isolated
    if isolated:
        report["warnings"].append(f"发现 {len(isolated)} 个孤立节点")
        print(f"\n[警告] 孤立节点 ({len(isolated)} 个):")
        for node in isolated:
            print(f"  [{node['type']}] {node['id']} - {node['name']}")
    else:
        report["passed"].append("无孤立节点")
        print("\n[通过] 无孤立节点")

    # 4. 边引用完整性（边的端点必须存在）
    edge_types = ["relation", "at", "link", "involved", "occurred_at", "evt_relation"]
    for etype in edge_types:
        # 检查是否有节点缺少编号
        result = client.run(
            f"MATCH (a)-[r:{etype}]->(b) "
            f"WHERE a.编号 IS NULL OR b.编号 IS NULL "
            f"RETURN count(*) AS bad_count"
        )
        bad = result[0]["bad_count"] if result else 0
        if bad > 0:
            report["errors"].append(f"{etype} 边有 {bad} 条端点缺少编号")

    if not report["errors"]:
        report["passed"].append("所有边的端点编号完整")
        print("[通过] 所有边的端点编号完整")

    # 5. 检查必填属性
    required_checks = {
        "char": ["编号", "姓名"],
        "Location": ["编号", "名称"],
        "Info": ["编号", "标题", "内容", "知识层"],
        "Event": ["编号", "标题", "时间"],
    }
    for label, fields in required_checks.items():
        for field in fields:
            result = client.run(
                f"MATCH (n:{label}) WHERE n.`{field}` IS NULL OR n.`{field}` = '' "
                f"RETURN count(*) AS missing"
            )
            missing = result[0]["missing"] if result else 0
            if missing > 0:
                report["warnings"].append(f"{label} 有 {missing} 个节点缺少 {field}")
                print(f"[警告] {label} 有 {missing} 个节点缺少 {field}")

    # 6. 知识层范围检查
    bad_level = client.run(
        "MATCH (n:Info) WHERE NOT n.知识层 IN [1, 2, 3] "
        "RETURN n.编号 AS id, n.知识层 AS level"
    )
    if bad_level:
        report["errors"].append(f"有 {len(bad_level)} 个 Info 节点知识层无效")
        for row in bad_level:
            print(f"[错误] {row['id']} 知识层={row['level']} (应为 1/2/3)")

    # 7. 事件类型检查
    bad_type = client.run(
        "MATCH (e:Event) WHERE e.类型 IS NOT NULL "
        "AND NOT e.类型 IN ['行动', '交流', '转折', '状态变化'] "
        "RETURN e.编号 AS id, e.类型 AS type"
    )
    if bad_type:
        report["warnings"].append(f"有 {len(bad_type)} 个 Event 类型不在枚举范围")
        for row in bad_type:
            print(f"[警告] {row['id']} 类型={row['type']}")

    # 汇总
    print("\n" + "=" * 50)
    p = len(report["passed"])
    w = len(report["warnings"])
    e = len(report["errors"])
    print(f"验证完成: {p} 通过, {w} 警告, {e} 错误")

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="图完整性验证")
    parser.add_argument("--uri", default=os.environ.get("NEO4J_URI", "bolt://localhost:7687"))
    parser.add_argument("--user", default=os.environ.get("NEO4J_USER", "neo4j"))
    parser.add_argument("--password", default=os.environ.get("NEO4J_PASSWORD", ""))
    parser.add_argument("--json", action="store_true", help="JSON 输出完整报告")
    args = parser.parse_args()

    with Neo4jClient(args.uri, args.user, args.password) as client:
        report = verify_graph(client)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
