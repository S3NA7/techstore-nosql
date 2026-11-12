import pytest

from src.services.cart import CartService
from src.services.catalog import CatalogService
from src.services.checkout import CarrinhoVazioError, CheckoutService, EstoqueInsuficienteError
from tests.fakes import FakeNeo4j

CLIENTE = {"_id": "cli_1", "nome": "Ana Souza", "email": "ana@techstore.com"}
ENDERECO = {"rua": "Rua A, 10", "cidade": "João Pessoa", "uf": "PB", "cep": "58000-000"}


@pytest.fixture
def ctx(db, r, oplog):
    db.produtos.insert_many([
        {"_id": "NB-001", "nome": "Notebook", "marca": "Acer", "categoria": "Notebooks", "preco": 5000.0, "estoque": 2},
        {"_id": "MS-001", "nome": "Mouse", "marca": "Logitech", "categoria": "Periféricos", "preco": 100.0, "estoque": 10},
    ])
    neo = FakeNeo4j()
    cart = CartService(r, ttl=1000, oplog=oplog)
    catalog = CatalogService(db, r, cache_ttl=300, oplog=oplog)
    checkout = CheckoutService(db, r, neo, cart, catalog, oplog=oplog)
    return db, r, neo, cart, catalog, checkout


def test_resumo_calcula_subtotais_e_total(ctx):
    db, r, neo, cart, catalog, checkout = ctx
    cart.adicionar("cli_1", "NB-001", 1)
    cart.adicionar("cli_1", "MS-001", 3)
    resumo = checkout.resumo("cli_1")
    assert resumo["quantidade_itens"] == 4
    assert resumo["total"] == 5300.0
    por_sku = {i["sku"]: i for i in resumo["itens"]}
    assert por_sku["MS-001"]["subtotal"] == 300.0 and por_sku["MS-001"]["estoque"] == 10


def test_finalizar_grava_pedido_decrementa_estoque_cria_grafo_e_limpa_carrinho(ctx):
    db, r, neo, cart, catalog, checkout = ctx
    cart.adicionar("cli_1", "NB-001", 1)
    cart.adicionar("cli_1", "MS-001", 2)
    catalog.obter_produto("NB-001")  # popula cache, que deve ser invalidado
    assert r.exists("cache:produto:NB-001") == 1

    pedido = checkout.finalizar(CLIENTE, "pix", ENDERECO)

    # MongoDB: pedido gravado com snapshot
    assert pedido["_id"].startswith("ped_") and pedido["status"] == "confirmado"
    assert pedido["cliente"] == {"id": "cli_1", "nome": "Ana Souza", "email": "ana@techstore.com"}
    assert pedido["total"] == 5200.0 and pedido["forma_pagamento"] == "pix"
    assert db.pedidos.find_one({"_id": pedido["_id"]})["endereco_entrega"] == ENDERECO
    assert db.produtos.find_one({"_id": "NB-001"})["estoque"] == 1
    assert db.produtos.find_one({"_id": "MS-001"})["estoque"] == 8
    # Neo4j: relacionamentos COMPROU
    assert len(neo.chamadas) == 1
    query, params = neo.chamadas[0]
    assert "MERGE (c:Cliente {id: $cliente_id})" in query and "COMPROU" in query
    assert params["pedido_id"] == pedido["_id"]
    assert sorted(i["sku"] for i in params["itens"]) == ["MS-001", "NB-001"]
    # Redis: carrinho limpo e cache invalidado
    assert cart.itens("cli_1") == {}
    assert r.exists("cache:produto:NB-001") == 0


def test_finalizar_carrinho_vazio_lanca_erro(ctx):
    db, r, neo, cart, catalog, checkout = ctx
    with pytest.raises(CarrinhoVazioError):
        checkout.finalizar(CLIENTE, "pix", ENDERECO)
    assert db.pedidos.count_documents({}) == 0


def test_estoque_insuficiente_nao_grava_nada(ctx):
    db, r, neo, cart, catalog, checkout = ctx
    cart.adicionar("cli_1", "NB-001", 5)  # só há 2
    with pytest.raises(EstoqueInsuficienteError) as exc:
        checkout.finalizar(CLIENTE, "pix", ENDERECO)
    assert exc.value.sku == "NB-001" and exc.value.disponivel == 2 and "Notebook" in str(exc.value)
    assert db.pedidos.count_documents({}) == 0
    assert db.produtos.find_one({"_id": "NB-001"})["estoque"] == 2
    assert cart.itens("cli_1") == {"NB-001": 5}
    assert neo.chamadas == []


def test_sku_inexistente_no_carrinho_e_ignorado_e_removido(ctx):
    db, r, neo, cart, catalog, checkout = ctx
    cart.adicionar("cli_1", "MS-001", 1)
    cart.adicionar("cli_1", "XX-999", 1)  # produto removido do catálogo
    resumo = checkout.resumo("cli_1")
    assert [i["sku"] for i in resumo["itens"]] == ["MS-001"]
    assert cart.itens("cli_1") == {"MS-001": 1}
    pedido = checkout.finalizar(CLIENTE, "cartao", ENDERECO)
    assert [i["sku"] for i in pedido["itens"]] == ["MS-001"]
