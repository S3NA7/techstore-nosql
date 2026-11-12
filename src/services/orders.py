"""Histórico de pedidos (MongoDB) e avaliações de produtos (Neo4j)."""
from __future__ import annotations

from datetime import date

from pymongo import DESCENDING
from pymongo.database import Database

from src.observability import OpLog

AVALIAR = """
MERGE (c:Cliente {id: $cliente_id})
  ON CREATE SET c.nome = $nome
WITH c
MATCH (p:Produto {sku: $sku})
MERGE (c)-[r:AVALIOU]->(p)
SET r.nota = $nota, r.data = date($data)
RETURN r.nota AS nota
"""

NOTA_DADA = """
MATCH (:Cliente {id: $cliente_id})-[r:AVALIOU]->(:Produto {sku: $sku})
RETURN r.nota AS nota
"""

NOTAS_DO_CLIENTE = """
MATCH (:Cliente {id: $cliente_id})-[r:AVALIOU]->(p:Produto)
RETURN p.sku AS sku, r.nota AS nota
"""


class OrderService:
    def __init__(self, db: Database, neo4j, oplog: OpLog | None = None):
        self.db = db
        self.neo4j = neo4j
        self.oplog = oplog

    def _log(self, banco: str, operacao: str, detalhe: str) -> None:
        if self.oplog:
            self.oplog.registrar(banco, operacao, detalhe)

    def pedidos_do_cliente(self, cliente_id: str) -> list[dict]:
        pedidos = list(self.db.pedidos.find({"cliente.id": cliente_id}).sort("criado_em", DESCENDING))
        self._log("MongoDB", "find", f"pedidos {{cliente.id: {cliente_id}}} sort criado_em desc")
        return pedidos

    def avaliar(self, cliente_id: str, sku: str, nota: int) -> None:
        """Grava/atualiza a aresta (:Cliente)-[:AVALIOU {nota, data}]->(:Produto)."""
        if not 1 <= int(nota) <= 5:
            raise ValueError("A nota deve estar entre 1 e 5.")
        cliente = self.db.clientes.find_one({"_id": cliente_id}, {"nome": 1}) or {}
        self.neo4j.run(AVALIAR, cliente_id=cliente_id, nome=cliente.get("nome", cliente_id),
                       sku=sku, nota=int(nota), data=date.today().isoformat())

    def nota_dada(self, cliente_id: str, sku: str) -> int | None:
        linhas = self.neo4j.run(NOTA_DADA, cliente_id=cliente_id, sku=sku)
        return int(linhas[0]["nota"]) if linhas else None

    def notas_do_cliente(self, cliente_id: str) -> dict[str, int]:
        """Todas as notas do cliente em uma única consulta: {sku: nota}."""
        linhas = self.neo4j.run(NOTAS_DO_CLIENTE, cliente_id=cliente_id)
        return {l["sku"]: int(l["nota"]) for l in linhas}
