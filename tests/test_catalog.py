import pytest

from src.services.catalog import CatalogService

PRODUTOS = [
    {"_id": "NB-001", "nome": "Notebook Gamer X", "marca": "Acer", "categoria": "Notebooks",
     "preco": 5999.0, "estoque": 5, "descricao": "RTX 4060", "tags": ["gamer", "notebook"],
     "especificacoes": {"memoria_ram_gb": 16}},
    {"_id": "NB-002", "nome": "Notebook Office", "marca": "Dell", "categoria": "Notebooks",
     "preco": 3499.0, "estoque": 8, "descricao": "Leve", "tags": ["trabalho"], "especificacoes": {}},
    {"_id": "MS-001", "nome": "Mouse Sem Fio", "marca": "Logitech", "categoria": "Periféricos",
     "preco": 199.0, "estoque": 30, "descricao": "Ergonômico", "tags": ["mouse", "wireless"],
     "especificacoes": {"dpi": 1600}},
    {"_id": "TC-001", "nome": "Teclado Mecânico", "marca": "Redragon", "categoria": "Periféricos",
     "preco": 299.0, "estoque": 12, "descricao": "Combo com mouse pad", "tags": ["teclado", "gamer"],
     "especificacoes": {}},
]


@pytest.fixture
def catalog(db, r, oplog):
    db.produtos.insert_many(PRODUTOS)
    return CatalogService(db, r, cache_ttl=300, oplog=oplog)


def test_obter_produto_segunda_chamada_vem_do_cache(catalog, r):
    p1, origem1 = catalog.obter_produto("NB-001")
    p2, origem2 = catalog.obter_produto("NB-001")
    assert (origem1, origem2) == ("mongo", "cache")
    assert p1["nome"] == p2["nome"] == "Notebook Gamer X"
    assert r.exists("cache:produto:NB-001") == 1
    assert 0 < r.ttl("cache:produto:NB-001") <= 300


def test_obter_produto_inexistente(catalog):
    assert catalog.obter_produto("XX-999") == (None, "mongo")


def test_obter_produto_incrementa_ranking(catalog, r):
    catalog.obter_produto("NB-001")
    catalog.obter_produto("NB-001")
    catalog.obter_produto("MS-001", registrar_acesso=False)
    assert r.zscore("ranking:produtos_acessados", "NB-001") == 2.0
    assert r.zscore("ranking:produtos_acessados", "MS-001") is None
    assert catalog.mais_acessados(5)[0] == ("NB-001", 2.0)


def test_atualizar_preco_invalida_cache(catalog, r):
    catalog.obter_produto("NB-001")
    assert r.exists("cache:produto:NB-001") == 1
    catalog.atualizar_preco("NB-001", 4999.0)
    assert r.exists("cache:produto:NB-001") == 0
    p, origem = catalog.obter_produto("NB-001")
    assert origem == "mongo" and p["preco"] == 4999.0


def test_buscar_por_texto_encontra_nome_e_tag(catalog):
    skus = {p["_id"] for p in catalog.buscar("mouse")}
    assert skus == {"MS-001", "TC-001"}  # nome e descrição/tag


def test_buscar_por_categoria_e_ordem(catalog):
    res = catalog.buscar(categoria="Notebooks", ordem="menor_preco")
    assert [p["_id"] for p in res] == ["NB-002", "NB-001"]
    res = catalog.buscar(categoria="Notebooks", ordem="maior_preco")
    assert [p["_id"] for p in res] == ["NB-001", "NB-002"]
    res = catalog.buscar(marca="Dell")
    assert [p["_id"] for p in res] == ["NB-002"]


def test_buscar_com_caracteres_de_regex_nao_quebra(catalog):
    assert catalog.buscar("C++ (") == []
    assert catalog.buscar("*") == []


def test_buscar_usa_cache_de_consulta(catalog, r):
    catalog.buscar("mouse")
    chaves = r.keys("cache:busca:*")
    assert len(chaves) == 1
    assert 0 < r.ttl(chaves[0]) <= 60
    # segunda chamada: resultado igual, origem cache
    assert [p["_id"] for p in catalog.buscar("mouse")] == ["MS-001", "TC-001"]


def test_obter_varios_e_listas(catalog):
    varios = catalog.obter_varios(["NB-001", "MS-001", "XX-999"])
    assert set(varios) == {"NB-001", "MS-001"}
    assert catalog.categorias() == ["Notebooks", "Periféricos"]
    assert catalog.marcas() == ["Acer", "Dell", "Logitech", "Redragon"]


def test_buscar_com_origem_informa_cache_ou_mongo(catalog):
    res1, origem1 = catalog.buscar_com_origem("mouse")
    res2, origem2 = catalog.buscar_com_origem("mouse")
    assert (origem1, origem2) == ("mongo", "cache")
    assert [p["_id"] for p in res1] == [p["_id"] for p in res2] == ["MS-001", "TC-001"]


def test_atualizar_preco_sincroniza_preco_no_grafo(db, r):
    from tests.fakes import FakeNeo4j
    neo = FakeNeo4j()
    db.produtos.insert_many(PRODUTOS)
    catalog = CatalogService(db, r, cache_ttl=300, neo4j=neo)
    catalog.atualizar_preco("NB-001", 4999.0)
    assert db.produtos.find_one({"_id": "NB-001"})["preco"] == 4999.0
    query, params = neo.chamadas[0]
    assert "MATCH (p:Produto {sku: $sku})" in query and "SET p.preco = $preco" in query
    assert params == {"sku": "NB-001", "preco": 4999.0}
