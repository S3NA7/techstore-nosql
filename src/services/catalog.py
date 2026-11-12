"""Catálogo de produtos: leitura no MongoDB com cache e ranking no Redis.

Estratégia de cache (Cache-Aside + TTL + invalidação explícita):
- cache:produto:{sku}  -> JSON do documento, TTL = CACHE_TTL. Lido antes do Mongo;
  gravado após a leitura no Mongo; apagado quando o produto muda (preço/estoque).
- cache:busca:{sha1}   -> JSON da lista de resultados de uma busca, TTL = 60 s.
  Apagado em bloco quando qualquer produto muda (resultados contêm preço).
- ranking:produtos_acessados -> ZSET; ZINCRBY a cada visualização de produto.
"""
from __future__ import annotations

import hashlib
import json
import re

from pymongo import ASCENDING, DESCENDING
from pymongo.database import Database

from src.observability import OpLog

TTL_BUSCA = 60
CHAVE_RANKING = "ranking:produtos_acessados"
ORDENS = {
    "relevancia": [("nome", ASCENDING)],
    "menor_preco": [("preco", ASCENDING), ("nome", ASCENDING)],
    "maior_preco": [("preco", DESCENDING), ("nome", ASCENDING)],
    "nome": [("nome", ASCENDING)],
}


def _json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


ATUALIZAR_PRECO_NO_GRAFO = "MATCH (p:Produto {sku: $sku}) SET p.preco = $preco RETURN p.sku AS sku"


class CatalogService:
    def __init__(self, db: Database, redis, cache_ttl: int, oplog: OpLog | None = None, neo4j=None):
        self.db = db
        self.redis = redis
        self.cache_ttl = cache_ttl
        self.oplog = oplog
        self.neo4j = neo4j  # opcional: mantém Produto.preco do grafo sincronizado com o Mongo

    def _log(self, banco: str, operacao: str, detalhe: str) -> None:
        if self.oplog:
            self.oplog.registrar(banco, operacao, detalhe)

    # ---------- chaves ----------
    @staticmethod
    def chave_produto(sku: str) -> str:
        return f"cache:produto:{sku}"

    @staticmethod
    def chave_busca(params: dict) -> str:
        assinatura = hashlib.sha1(_json(params).encode("utf-8")).hexdigest()[:16]
        return f"cache:busca:{assinatura}"

    # ---------- leitura de um produto ----------
    def obter_produto(self, sku: str, registrar_acesso: bool = True) -> tuple[dict | None, str]:
        """Devolve (produto, origem) com origem em {"cache", "mongo"}."""
        chave = self.chave_produto(sku)
        em_cache = self.redis.get(chave)
        if em_cache:
            self._log("Redis", "GET (cache HIT)", chave)
            produto, origem = json.loads(em_cache), "cache"
        else:
            self._log("Redis", "GET (cache MISS)", chave)
            produto = self.db.produtos.find_one({"_id": sku})
            self._log("MongoDB", "find_one", f"produtos {{_id: {sku}}}")
            origem = "mongo"
            if produto:
                self.redis.set(chave, _json(produto), ex=self.cache_ttl)
                self._log("Redis", "SET EX", f"{chave} (TTL {self.cache_ttl}s)")
        if produto and registrar_acesso:
            self.redis.zincrby(CHAVE_RANKING, 1, sku)
            self._log("Redis", "ZINCRBY", f"{CHAVE_RANKING} {sku} +1")
        return produto, origem

    def obter_varios(self, skus: list[str]) -> dict[str, dict]:
        """Leitura direta no Mongo (sem cache): usada quando o estoque precisa estar fresco."""
        if not skus:
            return {}
        docs = list(self.db.produtos.find({"_id": {"$in": list(skus)}}))
        self._log("MongoDB", "find", f"produtos {{_id: {{$in: {len(skus)} skus}}}}")
        return {d["_id"]: d for d in docs}

    # ---------- busca ----------
    def buscar(self, texto: str = "", categoria: str | None = None, marca: str | None = None,
               ordem: str = "relevancia", limite: int = 60) -> list[dict]:
        return self.buscar_com_origem(texto, categoria, marca, ordem, limite)[0]

    def buscar_com_origem(self, texto: str = "", categoria: str | None = None, marca: str | None = None,
                          ordem: str = "relevancia", limite: int = 60) -> tuple[list[dict], str]:
        """Como `buscar`, mas devolve também a origem: "cache" (Redis) ou "mongo"."""
        params = {"texto": texto.strip().lower(), "categoria": categoria, "marca": marca,
                  "ordem": ordem, "limite": limite}
        chave = self.chave_busca(params)
        em_cache = self.redis.get(chave)
        if em_cache:
            self._log("Redis", "GET (cache HIT)", chave)
            return json.loads(em_cache), "cache"

        filtro: dict = {}
        if params["texto"]:
            padrao = re.escape(params["texto"])
            filtro["$or"] = [{campo: {"$regex": padrao, "$options": "i"}}
                             for campo in ("nome", "marca", "descricao", "tags")]
        if categoria:
            filtro["categoria"] = categoria
        if marca:
            filtro["marca"] = marca

        cursor = self.db.produtos.find(filtro).sort(ORDENS.get(ordem, ORDENS["relevancia"])).limit(limite)
        resultados = list(cursor)
        self._log("MongoDB", "find", f"produtos {_json(filtro)} sort={ordem}")

        if ordem == "relevancia" and resultados:
            # relevância = produtos mais acessados primeiro (empate: ordem alfabética)
            pontuacao = {sku: float(s) for sku, s in
                         self.redis.zrevrange(CHAVE_RANKING, 0, -1, withscores=True)}
            resultados.sort(key=lambda p: -pontuacao.get(p["_id"], 0.0))

        self.redis.set(chave, _json(resultados), ex=TTL_BUSCA)
        self._log("Redis", "SET EX", f"{chave} ({len(resultados)} itens, TTL {TTL_BUSCA}s)")
        return json.loads(_json(resultados)), "mongo"

    def categorias(self) -> list[str]:
        return sorted(self.db.produtos.distinct("categoria"))

    def marcas(self) -> list[str]:
        return sorted(self.db.produtos.distinct("marca"))

    # ---------- ranking ----------
    def mais_acessados(self, n: int = 10) -> list[tuple[str, float]]:
        itens = self.redis.zrevrange(CHAVE_RANKING, 0, n - 1, withscores=True)
        self._log("Redis", "ZREVRANGE", f"{CHAVE_RANKING} 0 {n - 1} WITHSCORES")
        return [(sku, float(score)) for sku, score in itens]

    # ---------- escrita + invalidação ----------
    def atualizar_preco(self, sku: str, novo_preco: float) -> None:
        """Mongo é a fonte da verdade do preço; o grafo guarda uma cópia (para exibir recomendações)
        que é atualizada aqui, e o cache do Redis é invalidado."""
        self.db.produtos.update_one({"_id": sku}, {"$set": {"preco": float(novo_preco)}})
        self._log("MongoDB", "update_one", f"produtos {{_id: {sku}}} $set preco={novo_preco}")
        if self.neo4j is not None:
            self.neo4j.run(ATUALIZAR_PRECO_NO_GRAFO, sku=sku, preco=float(novo_preco))
        self.invalidar_cache(sku)

    def invalidar_cache(self, sku: str) -> None:
        """Cache Invalidation: apaga o produto e todas as buscas em cache."""
        self.redis.delete(self.chave_produto(sku))
        self._log("Redis", "DEL", self.chave_produto(sku))
        chaves = list(self.redis.scan_iter(match="cache:busca:*"))
        if chaves:
            self.redis.delete(*chaves)
            self._log("Redis", "DEL", f"cache:busca:* ({len(chaves)} chaves)")
