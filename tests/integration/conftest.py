"""Testes de integração: exigem os três bancos rodando (docker compose up -d).

Todo o pacote é pulado quando algum banco não responde, para que a suíte
unitária continue passando em qualquer máquina.
"""
import pytest

from src.config import Settings
from src.db.mongo import get_mongo_db, verificar_conexao as mongo_ok
from src.db.neo4j_client import Neo4jService
from src.db.redis_client import get_redis, verificar_conexao as redis_ok


@pytest.fixture(scope="session")
def settings():
    return Settings.from_env()


@pytest.fixture(scope="session")
def bancos(settings):
    db = get_mongo_db(settings)
    r = get_redis(settings)
    neo = Neo4jService(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password, settings.neo4j_database)
    indisponiveis = [nome for nome, ok in (("MongoDB", mongo_ok(db)), ("Redis", redis_ok(r)),
                                            ("Neo4j", neo.verificar_conexao())) if not ok]
    if indisponiveis:
        neo.close()
        pytest.skip(f"bancos indisponíveis: {', '.join(indisponiveis)} (rode `docker compose up -d`)")
    yield db, r, neo
    neo.close()
