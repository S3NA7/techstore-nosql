"""Carrinho de compras no Redis.

Por que Redis? O carrinho muda a cada clique e precisa responder em milissegundos;
é um estado de sessão, não um registro histórico. Modelagem:

    carrinho:{cliente_id}  ->  HASH  { sku: quantidade }   (TTL = CART_TTL)

HINCRBY soma quantidades de forma atômica; o TTL descarta carrinhos abandonados.
No checkout, o conteúdo vira um pedido no MongoDB e a chave é apagada.
"""
from __future__ import annotations

from src.observability import OpLog


class CartService:
    def __init__(self, redis, ttl: int, oplog: OpLog | None = None):
        self.redis = redis
        self.ttl = ttl
        self.oplog = oplog

    @staticmethod
    def chave(cliente_id: str) -> str:
        return f"carrinho:{cliente_id}"

    def _log(self, operacao: str, detalhe: str) -> None:
        if self.oplog:
            self.oplog.registrar("Redis", operacao, detalhe)

    def adicionar(self, cliente_id: str, sku: str, quantidade: int = 1) -> int:
        chave = self.chave(cliente_id)
        nova = int(self.redis.hincrby(chave, sku, quantidade))
        self.redis.expire(chave, self.ttl)
        self._log("HINCRBY + EXPIRE", f"{chave} {sku} +{quantidade} -> {nova}")
        return nova

    def definir_quantidade(self, cliente_id: str, sku: str, quantidade: int) -> None:
        if quantidade <= 0:
            self.remover(cliente_id, sku)
            return
        chave = self.chave(cliente_id)
        self.redis.hset(chave, sku, quantidade)
        self.redis.expire(chave, self.ttl)
        self._log("HSET + EXPIRE", f"{chave} {sku} = {quantidade}")

    def remover(self, cliente_id: str, sku: str) -> None:
        chave = self.chave(cliente_id)
        self.redis.hdel(chave, sku)
        self._log("HDEL", f"{chave} {sku}")

    def limpar(self, cliente_id: str) -> None:
        chave = self.chave(cliente_id)
        self.redis.delete(chave)
        self._log("DEL", chave)

    def itens(self, cliente_id: str) -> dict[str, int]:
        chave = self.chave(cliente_id)
        bruto = self.redis.hgetall(chave)
        self._log("HGETALL", f"{chave} ({len(bruto)} itens)")
        return {sku: int(q) for sku, q in bruto.items()}

    def total_itens(self, cliente_id: str) -> int:
        bruto = self.redis.hvals(self.chave(cliente_id))
        return sum(int(q) for q in bruto)
