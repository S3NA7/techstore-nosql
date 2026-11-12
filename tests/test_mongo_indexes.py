import mongomock

from src.db.mongo import ensure_indexes


def test_ensure_indexes_creates_unique_email():
    db = mongomock.MongoClient().techstore
    ensure_indexes(db)
    info = db.clientes.index_information()
    unicos = [v for k, v in info.items() if v.get("key") == [("email", 1)]]
    assert unicos and unicos[0].get("unique") is True
    assert any(v.get("key") == [("categoria", 1)] for v in db.produtos.index_information().values())
    assert any(v.get("key") == [("cliente.id", 1), ("criado_em", -1)] for v in db.pedidos.index_information().values())
