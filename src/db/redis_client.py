"""Conexão com o Redis.

Chaves usadas pela aplicação (ver docs/arquitetura.md):
- sessao:{token}              STRING  -> cliente_id        (TTL = SESSION_TTL)
- carrinho:{cliente_id}       HASH    sku -> quantidade    (TTL = CART_TTL)
- cache:produto:{sku}         STRING  JSON do produto      (TTL = CACHE_TTL)
- cache:busca:{sha1}          STRING  JSON da lista        (TTL = 60s)
- ranking:produtos_acessados  ZSET    sku -> nº de acessos (sem TTL)
"""
from __future__ import annotations

import redis
from redis.backoff import NoBackoff
from redis.retry import Retry

from src.config import Settings


def get_redis(settings: Settings) -> redis.Redis:
    """Cliente com falha rápida: se o Redis estiver fora, a tela mostra o erro em ~3 s em vez de travar."""
    return redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=3,  # o proxy do Docker Desktop aceita a conexão mesmo com o container parado
        retry=Retry(NoBackoff(), 0),  # redis-py >= 6 faria 3 retentativas com backoff (~20 s)
    )


def verificar_conexao(r: redis.Redis) -> bool:
    try:
        return bool(r.ping())
    except Exception:
        return False
