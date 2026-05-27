"""
图数据查询脚本
按 Schema 查询节点、边、关系图、事件链等
"""

import os
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from neo4j_client import Neo4jClient


def query_all_nodes(client, label=None):
    """查询所有节点或指定标签的节点"""
    if label:
        return client.run(f"MATCH (n:{label}) RETURN n LIMIT 500")
    return client.run("MATCH (n) RETURN n LIMIT 500")


def query_node_by_id(client, node_id):
    """按编号查询节点及其关系"""
    result = client.run(
        "MATCH (n {编号: $id}) "
        "OPTIONAL MATCH (n)-[r]-(m) "
        "RETURN n, type(r) AS rel_type, m, "
        "CASE WHEN startNode(r) = n THEN '出' ELSE '入' END AS direction",
        {"id": node_id}
    )
    return result


def query_character_relations(client, char_id=None):
    """查询角色关系"""
    if char_id:
        return client.run(
            "MATCH (a:char {编号: $id})-[r:relation]->(b:char) "
            "RETURN a.姓名 AS from_name, b.姓名 AS to_name, "
            "r.type AS rel_type, r.detail AS detail",
            {"id": char_id}
        )
    return client.run(
        "MATCH (a:char)-[r:relation]->(b:char) "
        "RETURN a.姓名 AS from_name, b.姓名 AS to_name, "
        "r.type AS rel_type, r.detail AS detail"
    )


def query_event_chain(client):
    """查询事件因果链（按时间排序）"""
    return client.run(
        "MATCH (e:Event) "
        "OPTIONAL MATCH (e)-[r:evt_relation]->(e2:Event) "
        "RETURN e.编号 AS id, e.标题 AS title, e.时间 AS time, e.类型 AS type, "
        "collect({target: e2.标题, rel_type: r.type, detail: r.detail}) AS next_events "
        "ORDER BY e.时间"
    )


def query_isolated_nodes(client):
    """查询孤立节点（无任何边）"""
    return client.run(
        "MATCH (n) WHERE NOT (n)--() "
        "RETURN labels(n)[0] AS type, n.编号 AS id, "
        "COALESCE(n.姓名, n.名称, n.标题) AS name "
        "ORDER BY type, id"
    )


def query_stats(client):
    """查询图统计信息"""
    nodes = client.run(
        "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS count ORDER BY count DESC"
    )
    edges = client.run(
        "MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS count ORDER BY count DESC"
    )
    return {"nodes": nodes, "edges": edges}


def query_info_by_knowledge_level(client, level=None):
    """按知识层查询信息节点"""
    if level is not None:
        return client.run(
            "MATCH (n:Info {知识层: toInteger($level)}) RETURN n",
            {"level": str(level)}
        )
    return client.run(
        "MATCH (n:Info) RETURN n.知识层 AS level, count(*) AS count "
        "ORDER BY n.知识层"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="查询 Neo4j 图数据")
    parser.add_argument("--uri", default=os.environ.get("NEO4J_URI", "bolt://localhost:7687"))
    parser.add_argument("--user", default=os.environ.get("NEO4J_USER", "neo4j"))
    parser.add_argument("--password", default=os.environ.get("NEO4J_PASSWORD", ""))
    parser.add_argument("--json", action="store_true", help="JSON 输出")

    sub = parser.add_subparsers(dest="command")

    # stats
    sub.add_parser("stats", help="图统计信息")

    # nodes
    p_nodes = sub.add_parser("nodes", help="查询节点")
    p_nodes.add_argument("--label", help="节点标签 (char/Location/Info/Event)")
    p_nodes.add_argument("--id", help="按编号查询")

    # relations
    p_rel = sub.add_parser("relations", help="查询角色关系")
    p_rel.add_argument("--id", help="指定角色编号")

    # events
    sub.add_parser("events", help="查询事件链")

    # isolated
    sub.add_parser("isolated", help="查询孤立节点")

    # info
    p_info = sub.add_parser("info", help="查询信息节点")
    p_info.add_argument("--level", type=int, help="知识层 (1/2/3)")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    with Neo4jClient(args.uri, args.user, args.password) as client:
        if args.command == "stats":
            data = query_stats(client)
            print(json.dumps(data, ensure_ascii=False, indent=2))
        elif args.command == "nodes":
            if args.id:
                results = query_node_by_id(client, args.id)
            else:
                results = query_all_nodes(client, args.label)
            print(json.dumps(results, ensure_ascii=False, indent=2) if args.json else results)
        elif args.command == "relations":
            results = query_character_relations(client, args.id)
            print(json.dumps(results, ensure_ascii=False, indent=2))
        elif args.command == "events":
            results = query_event_chain(client)
            print(json.dumps(results, ensure_ascii=False, indent=2))
        elif args.command == "isolated":
            results = query_isolated_nodes(client)
            print(json.dumps(results, ensure_ascii=False, indent=2))
        elif args.command == "info":
            results = query_info_by_knowledge_level(client, args.level)
            print(json.dumps(results, ensure_ascii=False, indent=2))
