"""
Neo4j Bolt 连接客户端
使用 neo4j Python driver 通过 bolt:// 协议连接 Neo4j 数据库
"""

import os
import sys
from neo4j import GraphDatabase


class Neo4jClient:
    """Neo4j 连接客户端，使用 bolt:// 协议"""

    def __init__(self, uri=None, user=None, password=None):
        self.uri = uri or os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        self.user = user or os.environ.get("NEO4J_USER", "neo4j")
        self.password = password or os.environ.get("NEO4J_PASSWORD", "")
        self.driver = None

    def connect(self):
        """建立连接"""
        if not self.password:
            print("错误：未设置密码。请通过参数或 NEO4J_PASSWORD 环境变量提供。")
            sys.exit(1)
        self.driver = GraphDatabase.driver(
            self.uri, auth=(self.user, self.password)
        )
        self.driver.verify_connectivity()
        print(f"已连接: {self.uri}")
        return self

    def close(self):
        """关闭连接"""
        if self.driver:
            self.driver.close()
            print("连接已关闭")

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.close()

    def run(self, cypher, parameters=None):
        """执行单条 Cypher，返回结果列表"""
        with self.driver.session() as session:
            result = session.run(cypher, parameters or {})
            return [record.data() for record in result]

    def run_in_transaction(self, cypher_list):
        """在单个事务中顺序执行多条 Cypher"""
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
        """执行写操作（MERGE/CREATE/SET），返回统计信息"""
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
    """工厂函数：创建并连接客户端"""
    client = Neo4jClient(uri, user, password)
    client.connect()
    return client


if __name__ == "__main__":
    # 快速连接测试
    with Neo4jClient() as client:
        result = client.run("RETURN 1 AS test")
        print(f"连接测试: {result}")
