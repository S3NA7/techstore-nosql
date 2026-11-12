"""Os clientes precisam falhar rápido quando um banco não responde (tela de erro, não travamento)."""
from src.config import Settings
from src.db.mongo import get_mongo_db
from src.db.redis_client import get_redis


def test_redis_tem_timeout_de_conexao_e_de_leitura():
    kwargs = get_redis(Settings()).connection_pool.connection_kwargs
    assert kwargs["socket_connect_timeout"] == 3
    assert kwargs["socket_timeout"] == 3  # sem isto, um proxy que aceita e não responde trava o app


def test_mongo_tem_timeout_de_selecao_de_servidor():
    db = get_mongo_db(Settings())
    assert db.client.options.server_selection_timeout == 3.0


def test_redis_nao_faz_retentativas_com_backoff():
    # redis-py >= 6 tenta 3 vezes com backoff exponencial por padrão: com o container parado,
    # a tela ficaria ~20 s travada antes de mostrar o erro.
    assert get_redis(Settings()).get_retry().get_retries() == 0
