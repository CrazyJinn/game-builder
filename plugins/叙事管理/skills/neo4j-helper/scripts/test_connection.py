"""
Neo4j 连接测试脚本
验证 bolt:// 连接、数据库版本、基本读写能力
"""

import sys
import os
import argparse

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from neo4j_client import Neo4jClient


def test_connection(uri, user, password):
    """测试 Neo4j 连接"""
    print("=" * 50)
    print("Neo4j 连接测试")
    print("=" * 50)

    try:
        client = Neo4jClient(uri, user, password)
        client.connect()
    except Exception as e:
        print(f"[失败] 无法连接: {e}")
        print("\n排查建议:")
        print("  1. 确认 Neo4j 服务已启动")
        print("  2. 确认 bolt 端口 (默认 7687) 未被占用")
        print("  3. 确认用户名和密码正确")
        print("  4. 如需远程连接，确认 neo4j.conf 中已开启 bolt 监听")
        return False

    # 测试基本信息
    try:
        info = client.run("CALL dbms.components() YIELD name, versions, edition")
        if info:
            print(f"[通过] 数据库: {info[0]['name']} {info[0]['edition']}")
            print(f"        版本: {', '.join(info[0]['versions'])}")
    except Exception as e:
        print(f"[警告] 无法获取数据库信息: {e}")

    # 测试读操作
    try:
        result = client.run("RETURN 1 AS value")
        assert result[0]["value"] == 1
        print("[通过] 读操作正常")
    except Exception as e:
        print(f"[失败] 读操作异常: {e}")
        return False

    # 测试写操作（创建临时节点后删除）
    try:
        stats = client.run_write(
            "CREATE (t:_test_node {msg: 'hello'}) RETURN t"
        )
        assert stats["nodes_created"] == 1
        print("[通过] 写操作正常")

        # 清理
        client.run_write("MATCH (t:_test_node) DELETE t")
        print("[通过] 清理测试数据")
    except Exception as e:
        print(f"[失败] 写操作异常: {e}")
        return False

    # 显示现有节点统计
    try:
        counts = client.run(
            "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS count "
            "ORDER BY count DESC"
        )
        if counts:
            print("\n当前数据库节点统计:")
            for row in counts:
                print(f"  {row['label']}: {row['count']}")
        else:
            print("\n数据库为空（无节点）")
    except Exception as e:
        print(f"[警告] 无法统计节点: {e}")

    client.close()
    print("\n" + "=" * 50)
    print("全部测试通过!")
    print("=" * 50)
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Neo4j 连接测试")
    parser.add_argument("--uri", default=os.environ.get("NEO4J_URI", "bolt://localhost:7687"))
    parser.add_argument("--user", default=os.environ.get("NEO4J_USER", "neo4j"))
    parser.add_argument("--password", default=os.environ.get("NEO4J_PASSWORD", ""))
    args = parser.parse_args()

    success = test_connection(args.uri, args.user, args.password)
    sys.exit(0 if success else 1)
