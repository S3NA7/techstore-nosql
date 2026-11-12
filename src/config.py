"""Configurações da aplicação lidas de variáveis de ambiente (.env).

Os nomes das variáveis seguem o enunciado do professor (NEO4J_URI, NEO4J_USERNAME,
NEO4J_PASSWORD, NEO4J_DATABASE) acrescidos das variáveis do MongoDB e do Redis.
Os valores padrão correspondem ao docker-compose.yml deste repositório.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, fields

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    # MongoDB — catálogo, clientes e pedidos
    mongo_uri: str = "mongodb://127.0.0.1:27017"
    mongo_db: str = "techstore"
    # Redis — sessões, carrinho, cache e ranking
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_db: int = 0
    # Neo4j — grafo de compras/avaliações e recomendações
    neo4j_uri: str = "bolt://127.0.0.1:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "techstore123"
    neo4j_database: str = "neo4j"
    # Tempos de vida (segundos)
    session_ttl: int = 1800        # token de login: 30 minutos
    cache_ttl: int = 300           # cache de produto: 5 minutos
    cart_ttl: int = 604800         # carrinho abandonado: 7 dias

    # Mapeamento campo -> variável de ambiente
    _ENV = {
        "mongo_uri": "MONGO_URI",
        "mongo_db": "MONGO_DB",
        "redis_host": "REDIS_HOST",
        "redis_port": "REDIS_PORT",
        "redis_db": "REDIS_DB",
        "neo4j_uri": "NEO4J_URI",
        "neo4j_user": "NEO4J_USERNAME",
        "neo4j_password": "NEO4J_PASSWORD",
        "neo4j_database": "NEO4J_DATABASE",
        "session_ttl": "SESSION_TTL_SECONDS",
        "cache_ttl": "CACHE_TTL_SECONDS",
        "cart_ttl": "CART_TTL_SECONDS",
    }

    @classmethod
    def from_env(cls, dotenv_path: str | None = ".env") -> "Settings":
        """Carrega o .env (se informado) e sobrescreve os padrões com o ambiente."""
        if dotenv_path:
            load_dotenv(dotenv_path, override=False)
        valores = {}
        for f in fields(cls):
            if f.name.startswith("_"):
                continue
            bruto = os.environ.get(cls._ENV[f.name])
            if bruto is None or bruto == "":
                continue
            valores[f.name] = int(bruto) if f.type in ("int", int) else bruto
        return cls(**valores)
