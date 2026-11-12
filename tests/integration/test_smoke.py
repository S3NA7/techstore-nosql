"""Fluxo completo contra os bancos reais: carga -> login -> busca -> carrinho -> checkout -> recomendação.

ATENÇÃO: recarrega os três bancos (seed --reset). Só roda com `pytest -m integration`."""
import pytest

from scripts.seed import CLIENTE_DEMO, SENHA_PADRAO, main as seed_main
from src.services.auth import AuthService
from src.services.cart import CartService
from src.services.catalog import CatalogService
from src.services.checkout import CheckoutService
from src.services.orders import OrderService
from src.services.recommendations import RecommendationService


@pytest.mark.integration
def test_fluxo_completo_nos_tres_bancos(bancos, settings):
    db, r, neo = bancos
    assert seed_main(["--reset"]) == 0

    # MongoDB carregado
    assert db.produtos.count_documents({}) == 42
    assert db.clientes.count_documents({}) == 30
    assert db.pedidos.count_documents({}) == 160

    # Neo4j carregado
    contagem = neo.run("MATCH (c:Cliente)-[r:COMPROU]->(:Produto) RETURN count(DISTINCT c) AS clientes, count(r) AS compras")[0]
    assert contagem["clientes"] == 30 and contagem["compras"] >= 160

    # Login (Mongo + Redis)
    auth = AuthService(db, r, settings.session_ttl)
    token = auth.login(CLIENTE_DEMO["email"], SENHA_PADRAO)
    assert token and auth.cliente_do_token(token)["nome"] == CLIENTE_DEMO["nome"]
    ana = auth.cliente_do_token(token)

    # Busca com cache
    catalog = CatalogService(db, r, settings.cache_ttl)
    assert len(catalog.buscar("PlayStation")) >= 2
    produto, origem1 = catalog.obter_produto("JG-003")
    _, origem2 = catalog.obter_produto("JG-003")
    assert (origem1, origem2) == ("mongo", "cache")

    # Recomendações da Ana (gamer) existem
    recs = RecommendationService(neo)
    assert len(recs.quem_comprou_tambem_comprou(ana["_id"])) >= 1
    assert len(recs.populares_na_categoria("Jogos")) >= 1
    nos, arestas = recs.subgrafo_cliente(ana["_id"])
    assert nos and arestas

    # Carrinho + checkout escrevem nos três bancos
    cart = CartService(r, settings.cart_ttl)
    checkout = CheckoutService(db, r, neo, cart, catalog)
    estoque_antes = db.produtos.find_one({"_id": "JG-003"})["estoque"]
    cart.adicionar(ana["_id"], "JG-003", 1)
    pedido = checkout.finalizar(ana, "pix", ana["endereco"])
    assert db.pedidos.find_one({"_id": pedido["_id"]})["status"] == "confirmado"
    assert db.produtos.find_one({"_id": "JG-003"})["estoque"] == estoque_antes - 1
    assert cart.itens(ana["_id"]) == {}
    aresta = neo.run("MATCH (:Cliente {id: $id})-[r:COMPROU {pedido_id: $pid}]->(p:Produto) RETURN p.sku AS sku",
                     id=ana["_id"], pid=pedido["_id"])
    assert aresta == [{"sku": "JG-003"}]

    # Avaliação e caminho da recomendação
    orders = OrderService(db, neo)
    orders.avaliar(ana["_id"], "JG-003", 5)
    assert orders.nota_dada(ana["_id"], "JG-003") == 5
    caminho = recs.caminho_recomendacao(ana["_id"], recs.quem_comprou_tambem_comprou(ana["_id"])[0]["sku"])
    assert caminho and caminho[0]["rotulo"] == "Cliente" and caminho[-1]["rotulo"] == "Produto"

    auth.logout(token)
    assert auth.cliente_do_token(token) is None
