import pytest

from src.services.auth import AuthService, EmailJaCadastradoError, hash_senha, verificar_senha


@pytest.fixture
def auth(db, r, oplog):
    return AuthService(db, r, session_ttl=1800, oplog=oplog)


def test_hash_senha_e_verificacao():
    h, salt = hash_senha("123456")
    assert verificar_senha("123456", h, salt)
    assert not verificar_senha("654321", h, salt)
    h2, _ = hash_senha("123456", salt=bytes.fromhex(salt))
    assert h2 == h


def test_registrar_e_login_devolve_token(auth, r):
    cliente = auth.registrar("Ana Souza", "Ana@TechStore.com", "123456")
    assert cliente["_id"].startswith("cli_") and "senha_hash" not in cliente
    assert cliente["email"] == "ana@techstore.com"
    token = auth.login("ana@techstore.com", "123456")
    assert token
    assert r.get(f"sessao:{token}") == cliente["_id"]
    assert 1700 < r.ttl(f"sessao:{token}") <= 1800


def test_login_senha_errada_e_email_inexistente_devolvem_none(auth):
    auth.registrar("Ana", "ana@techstore.com", "123456")
    assert auth.login("ana@techstore.com", "errada") is None
    assert auth.login("ninguem@techstore.com", "123456") is None


def test_registrar_email_duplicado_lanca_erro(auth):
    auth.registrar("Ana", "ana@techstore.com", "123456")
    with pytest.raises(EmailJaCadastradoError):
        auth.registrar("Outra Ana", "ANA@techstore.com", "abcdef")


def test_cliente_do_token_valido_e_expirado(auth, r):
    auth.registrar("Ana", "ana@techstore.com", "123456")
    token = auth.login("ana@techstore.com", "123456")
    cliente = auth.cliente_do_token(token)
    assert cliente["nome"] == "Ana" and "senha_hash" not in cliente
    r.delete(f"sessao:{token}")  # simula expiração do TTL
    assert auth.cliente_do_token(token) is None
    assert auth.cliente_do_token("token-inexistente") is None


def test_logout_remove_token(auth, r):
    auth.registrar("Ana", "ana@techstore.com", "123456")
    token = auth.login("ana@techstore.com", "123456")
    auth.logout(token)
    assert r.exists(f"sessao:{token}") == 0
    assert auth.cliente_do_token(token) is None


def test_oplog_registra_operacoes(auth, oplog):
    auth.registrar("Ana", "ana@techstore.com", "123456")
    auth.login("ana@techstore.com", "123456")
    bancos = {op.banco for op in oplog.recentes()}
    assert bancos == {"MongoDB", "Redis"}
