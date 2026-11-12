"""Checkout: o único fluxo que escreve nos três bancos ao mesmo tempo.

Ordem das operações em `finalizar`:
1. Lê o carrinho no Redis e os produtos (estoque fresco) no MongoDB; valida.
2. MongoDB: grava o pedido (snapshot de itens e preços) e decrementa o estoque.
3. Neo4j: MERGE do cliente e das arestas (:Cliente)-[:COMPROU]->(:Produto).
4. Redis: apaga o carrinho e invalida o cache dos produtos (estoque mudou).

Se a validação falha (carrinho vazio, estoque insuficiente) nada é gravado.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pymongo.database import Database

from src.observability import OpLog
from src.services.cart import CartService
from src.services.catalog import CatalogService

REGISTRAR_COMPRA = """
MERGE (c:Cliente {id: $cliente_id})
  ON CREATE SET c.nome = $nome
WITH c
UNWIND $itens AS item
MATCH (p:Produto {sku: item.sku})
MERGE (c)-[r:COMPROU {pedido_id: $pedido_id}]->(p)
SET r.data = datetime($data), r.quantidade = item.quantidade
RETURN count(r) AS arestas
"""


class CarrinhoVazioError(Exception):
    def __init__(self):
        super().__init__("O carrinho está vazio.")


class EstoqueInsuficienteError(Exception):
    def __init__(self, sku: str, nome: str, disponivel: int, pedido: int):
        self.sku, self.nome, self.disponivel, self.pedido = sku, nome, disponivel, pedido
        super().__init__(f"Estoque insuficiente para {nome} ({sku}): disponível {disponivel}, pedido {pedido}.")


class CheckoutService:
    def __init__(self, db: Database, redis, neo4j, cart: CartService, catalog: CatalogService,
                 oplog: OpLog | None = None):
        self.db = db
        self.redis = redis
        self.neo4j = neo4j
        self.cart = cart
        self.catalog = catalog
        self.oplog = oplog

    def _log(self, banco: str, operacao: str, detalhe: str) -> None:
        if self.oplog:
            self.oplog.registrar(banco, operacao, detalhe)

    def resumo(self, cliente_id: str) -> dict:
        """Junta carrinho (Redis) com produtos (Mongo). Remove do carrinho SKUs que não existem mais."""
        carrinho = self.cart.itens(cliente_id)
        produtos = self.catalog.obter_varios(list(carrinho))
        itens = []
        for sku, quantidade in carrinho.items():
            produto = produtos.get(sku)
            if produto is None:
                self.cart.remover(cliente_id, sku)
                continue
            preco = float(produto["preco"])
            itens.append({
                "sku": sku,
                "nome": produto["nome"],
                "preco_unitario": preco,
                "quantidade": quantidade,
                "subtotal": round(preco * quantidade, 2),
                "estoque": int(produto.get("estoque", 0)),
            })
        return {
            "itens": itens,
            "total": round(sum(i["subtotal"] for i in itens), 2),
            "quantidade_itens": sum(i["quantidade"] for i in itens),
        }

    def finalizar(self, cliente: dict, forma_pagamento: str, endereco: dict) -> dict:
        cliente_id = cliente["_id"]
        resumo = self.resumo(cliente_id)
        if not resumo["itens"]:
            raise CarrinhoVazioError()
        for item in resumo["itens"]:
            if item["quantidade"] > item["estoque"]:
                raise EstoqueInsuficienteError(item["sku"], item["nome"], item["estoque"], item["quantidade"])

        agora = datetime.now()
        pedido = {
            "_id": f"ped_{uuid.uuid4().hex[:12]}",
            "cliente": {"id": cliente_id, "nome": cliente.get("nome"), "email": cliente.get("email")},
            "itens": [{k: v for k, v in i.items() if k != "estoque"} for i in resumo["itens"]],
            "total": resumo["total"],
            "forma_pagamento": forma_pagamento,
            "endereco_entrega": endereco,
            "status": "confirmado",
            "criado_em": agora,
        }

        # 1) MongoDB: pedido + estoque
        self.db.pedidos.insert_one(pedido)
        self._log("MongoDB", "insert_one", f"pedidos {{_id: {pedido['_id']}, total: {pedido['total']}}}")
        for item in pedido["itens"]:
            self.db.produtos.update_one({"_id": item["sku"]}, {"$inc": {"estoque": -item["quantidade"]}})
            self._log("MongoDB", "update_one", f"produtos {{_id: {item['sku']}}} $inc estoque -{item['quantidade']}")

        # 2) Neo4j: arestas COMPROU
        self.neo4j.run(
            REGISTRAR_COMPRA,
            cliente_id=cliente_id,
            nome=cliente.get("nome") or cliente_id,
            pedido_id=pedido["_id"],
            data=agora.isoformat(timespec="seconds"),
            itens=[{"sku": i["sku"], "quantidade": i["quantidade"]} for i in pedido["itens"]],
        )

        # 3) Redis: limpa carrinho e invalida cache
        self.cart.limpar(cliente_id)
        for item in pedido["itens"]:
            self.catalog.invalidar_cache(item["sku"])
        return pedido
