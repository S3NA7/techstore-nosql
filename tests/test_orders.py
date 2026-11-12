from datetime import datetime

import pytest

from src.services.orders import OrderService
from tests.fakes import FakeNeo4j


@pytest.fixture
def orders(db, oplog):
    return OrderService(db, FakeNeo4j(), oplog=oplog)


def test_pedidos_do_cliente_ordena_por_data_desc(orders, db):
    db.pedidos.insert_many([
        {"_id": "ped_1", "cliente": {"id": "cli_1"}, "total": 10, "criado_em": datetime(2026, 1, 1)},
        {"_id": "ped_2", "cliente": {"id": "cli_1"}, "total": 20, "criado_em": datetime(2026, 3, 1)},
        {"_id": "ped_3", "cliente": {"id": "cli_2"}, "total": 30, "criado_em": datetime(2026, 2, 1)},
    ])
    assert [p["_id"] for p in orders.pedidos_do_cliente("cli_1")] == ["ped_2", "ped_1"]


def test_avaliar_rejeita_nota_fora_de_1_a_5(orders):
    with pytest.raises(ValueError):
        orders.avaliar("cli_1", "NB-001", 0)
    with pytest.raises(ValueError):
        orders.avaliar("cli_1", "NB-001", 6)
    assert orders.neo4j.chamadas == []


def test_avaliar_envia_merge_avaliou(orders):
    orders.avaliar("cli_1", "NB-001", 5)
    query, params = orders.neo4j.chamadas[0]
    assert "MERGE (c)-[r:AVALIOU]->(p)" in query and "SET r.nota" in query
    assert params["cliente_id"] == "cli_1" and params["sku"] == "NB-001" and params["nota"] == 5


def test_nota_dada_le_do_grafo(db):
    neo = FakeNeo4j(respostas=[[{"nota": 4}], []])
    orders = OrderService(db, neo)
    assert orders.nota_dada("cli_1", "NB-001") == 4
    assert orders.nota_dada("cli_1", "NB-002") is None


def test_notas_do_cliente_devolve_dict_por_sku(db):
    neo = FakeNeo4j(respostas=[[{"sku": "NB-001", "nota": 5}, {"sku": "JG-001", "nota": 3}]])
    orders = OrderService(db, neo)
    assert orders.notas_do_cliente("cli_1") == {"NB-001": 5, "JG-001": 3}
    assert neo.chamadas[0][1] == {"cliente_id": "cli_1"}
