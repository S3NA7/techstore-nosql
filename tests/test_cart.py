import pytest

from src.services.cart import CartService


@pytest.fixture
def cart(r, oplog):
    return CartService(r, ttl=604800, oplog=oplog)


def test_chave_segue_padrao():
    assert CartService.chave("cli_1") == "carrinho:cli_1"


def test_adicionar_acumula_quantidade(cart):
    assert cart.adicionar("cli_1", "NB-001", 2) == 2
    assert cart.adicionar("cli_1", "NB-001", 3) == 5
    assert cart.itens("cli_1") == {"NB-001": 5}


def test_itens_devolve_ints_e_total(cart):
    cart.adicionar("cli_1", "NB-001")
    cart.adicionar("cli_1", "MS-002", 4)
    itens = cart.itens("cli_1")
    assert itens == {"NB-001": 1, "MS-002": 4}
    assert all(isinstance(q, int) for q in itens.values())
    assert cart.total_itens("cli_1") == 5


def test_definir_quantidade_e_zero_remove_item(cart):
    cart.adicionar("cli_1", "NB-001", 2)
    cart.definir_quantidade("cli_1", "NB-001", 7)
    assert cart.itens("cli_1") == {"NB-001": 7}
    cart.definir_quantidade("cli_1", "NB-001", 0)
    assert cart.itens("cli_1") == {}


def test_remover_item(cart):
    cart.adicionar("cli_1", "NB-001")
    cart.adicionar("cli_1", "MS-002")
    cart.remover("cli_1", "NB-001")
    assert cart.itens("cli_1") == {"MS-002": 1}


def test_limpar_apaga_chave(cart, r):
    cart.adicionar("cli_1", "NB-001")
    cart.limpar("cli_1")
    assert r.exists("carrinho:cli_1") == 0
    assert cart.itens("cli_1") == {}
    assert cart.total_itens("cli_1") == 0


def test_carrinho_tem_ttl(cart, r):
    cart.adicionar("cli_1", "NB-001")
    assert 0 < r.ttl("carrinho:cli_1") <= 604800


def test_oplog_registra_redis(cart, oplog):
    cart.adicionar("cli_1", "NB-001")
    op = oplog.recentes()[0]
    assert op.banco == "Redis" and "HINCRBY" in op.operacao
