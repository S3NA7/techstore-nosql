"""Conexão com o Neo4j, no modelo sugerido pelo enunciado (seção 3.2).

Grafo:
  (:Cliente {id, nome})
  (:Produto {sku, nome, preco, categoria})
  (:Categoria {nome})
  (:Cliente)-[:COMPROU {pedido_id, data, quantidade}]->(:Produto)
  (:Cliente)-[:AVALIOU {nota, data}]->(:Produto)
  (:Produto)-[:PERTENCE_A]->(:Categoria)
"""
from __future__ import annotations

from neo4j import GraphDatabase

from src.observability import OpLog

CONSTRAINTS = [
    "CREATE CONSTRAINT cliente_id IF NOT EXISTS FOR (c:Cliente) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT produto_sku IF NOT EXISTS FOR (p:Produto) REQUIRE p.sku IS UNIQUE",
    "CREATE CONSTRAINT categoria_nome IF NOT EXISTS FOR (c:Categoria) REQUIRE c.nome IS UNIQUE",
]


class Neo4jService:
    def __init__(self, uri: str, user: str, password: str, database: str = "neo4j",
                 oplog: OpLog | None = None):
        self.driver = GraphDatabase.driver(uri, auth=(user, password), connection_timeout=5)
        self.database = database
        self.oplog = oplog

    def run(self, query: str, **params) -> list[dict]:
        """Executa um Cypher e devolve as linhas como dicionários."""
        if self.oplog:
            self.oplog.registrar("Neo4j", "CYPHER", " ".join(query.split())[:300])
        with self.driver.session(database=self.database) as session:
            result = session.run(query, **params)
            return [record.data() for record in result]

    def ensure_constraints(self) -> None:
        for cypher in CONSTRAINTS:
            self.run(cypher)

    def verificar_conexao(self) -> bool:
        try:
            self.driver.verify_connectivity()
            return True
        except Exception:
            return False

    def close(self) -> None:
        self.driver.close()
