"""Conexões compartilhadas (st.cache_resource) e serviços por sessão.

As conexões com os três bancos são criadas uma única vez por processo.
Os serviços são objetos leves recriados a cada execução, recebendo o OpLog
da sessão do usuário, para que a tela "Bastidores" mostre só o que aquele
usuário disparou.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import streamlit as st

from src.config import Settings
from src.db.mongo import get_mongo_db
from src.db.mongo import verificar_conexao as mongo_ok
from src.db.neo4j_client import Neo4jService
from src.db.redis_client import get_redis
from src.db.redis_client import verificar_conexao as redis_ok
from src.observability import OpLog
from src.services.auth import AuthService
from src.services.cart import CartService
from src.services.catalog import CatalogService
from src.services.checkout import CheckoutService
from src.services.orders import OrderService
from src.services.recommendations import RecommendationService


@dataclass
class Conexoes:
    settings: Settings
    db: object
    redis: object
    neo4j: Neo4jService


@st.cache_resource(show_spinner="Conectando aos bancos de dados...")
def conexoes() -> Conexoes:
    settings = Settings.from_env()
    return Conexoes(
        settings=settings,
        db=get_mongo_db(settings),
        redis=get_redis(settings),
        neo4j=Neo4jService(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password,
                           settings.neo4j_database),
    )


class Neo4jComLog:
    """Envolve o Neo4jService compartilhado para registrar cada Cypher no OpLog da sessão."""

    def __init__(self, base: Neo4jService, log: OpLog):
        self.base = base
        self.log = log

    def run(self, query: str, **params) -> list[dict]:
        self.log.registrar("Neo4j", "CYPHER", " ".join(query.split())[:300])
        return self.base.run(query, **params)

    def verificar_conexao(self) -> bool:
        return self.base.verificar_conexao()


def oplog() -> OpLog:
    if "oplog" not in st.session_state:
        st.session_state["oplog"] = OpLog(limite=300)
    return st.session_state["oplog"]


@dataclass
class Servicos:
    settings: Settings
    db: object
    redis: object
    neo4j: Neo4jComLog
    auth: AuthService
    catalog: CatalogService
    cart: CartService
    recs: RecommendationService
    orders: OrderService
    checkout: CheckoutService
    oplog: OpLog


def servicos() -> Servicos:
    c = conexoes()
    log = oplog()
    neo = Neo4jComLog(c.neo4j, log)
    catalog = CatalogService(c.db, c.redis, c.settings.cache_ttl, oplog=log, neo4j=neo)
    cart = CartService(c.redis, c.settings.cart_ttl, oplog=log)
    return Servicos(
        settings=c.settings,
        db=c.db,
        redis=c.redis,
        neo4j=neo,
        auth=AuthService(c.db, c.redis, c.settings.session_ttl, oplog=log),
        catalog=catalog,
        cart=cart,
        recs=RecommendationService(neo),
        orders=OrderService(c.db, neo, oplog=log),
        checkout=CheckoutService(c.db, c.redis, neo, cart, catalog, oplog=log),
        oplog=log,
    )


def cliente_logado(s: Servicos) -> dict | None:
    """Resolve o token guardado na sessão do Streamlit via Redis (renovando o TTL)."""
    token = st.session_state.get("token")
    if not token:
        return None
    cliente = s.auth.cliente_do_token(token)
    if cliente is None:
        st.session_state.pop("token", None)
        st.session_state["aviso_sessao"] = "Sua sessão expirou (o token saiu do Redis pelo TTL). Entre novamente."
    return cliente


@st.cache_data(ttl=15, show_spinner=False)
def verificar_conexoes() -> dict[str, tuple[bool, str]]:
    """Ping nos três bancos com latência; cacheado por 15 s."""
    c = conexoes()
    checagens = {
        "MongoDB": lambda: mongo_ok(c.db),
        "Redis": lambda: redis_ok(c.redis),
        "Neo4j": lambda: c.neo4j.verificar_conexao(),
    }
    resultado = {}
    for nome, fn in checagens.items():
        inicio = time.perf_counter()
        ok = fn()
        ms = (time.perf_counter() - inicio) * 1000
        resultado[nome] = (ok, f"{ms:.0f} ms" if ok else "sem resposta")
    return resultado
