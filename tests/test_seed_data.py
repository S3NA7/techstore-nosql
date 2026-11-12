from scripts.seed import (
    CATEGORIAS,
    PERSONAS,
    carregar_produtos,
    gerar_avaliacoes,
    gerar_clientes,
    gerar_pedidos,
    seed_mongo,
)


def test_produtos_json_tem_skus_unicos_e_campos_obrigatorios():
    produtos = carregar_produtos()
    assert len(produtos) >= 35
    skus = [p["sku"] for p in produtos]
    assert len(skus) == len(set(skus))
    obrigatorios = {"sku", "nome", "marca", "categoria", "preco", "estoque", "descricao", "tags", "imagem",
                    "especificacoes"}
    for p in produtos:
        assert obrigatorios <= set(p), p["sku"]
        assert p["preco"] > 0 and p["estoque"] >= 0 and p["tags"]
    assert {p["categoria"] for p in produtos} == set(CATEGORIAS)
    notebook = next(p for p in produtos if p["categoria"] == "Notebooks")["especificacoes"]
    jogo = next(p for p in produtos if p["categoria"] == "Jogos")["especificacoes"]
    assert "memoria_ram_gb" in notebook and "plataforma" in jogo  # esquema flexível por categoria


def test_gerar_clientes_inclui_demo_e_e_deterministico():
    a = gerar_clientes(n=30, seed=42)
    b = gerar_clientes(n=30, seed=42)
    assert a == b and len(a) == 30
    assert len({c["email"] for c in a}) == 30
    ana = next(c for c in a if c["email"] == "ana@techstore.com")
    assert ana["persona"] == "gamer" and ana["_id"].startswith("cli_")
    assert "senha_hash" in ana and "salt" in ana and "senha" not in ana
    assert {"rua", "cidade", "uf", "cep"} <= set(ana["endereco"])


def test_gerar_pedidos_respeita_persona():
    produtos = carregar_produtos()
    clientes = gerar_clientes(n=10, seed=1)
    pedidos = gerar_pedidos(clientes, produtos, n=60, seed=1)
    assert len(pedidos) == 60
    assert {p["cliente"]["id"] for p in pedidos} == {c["_id"] for c in clientes}  # todos compram
    persona_por_id = {c["_id"]: c["persona"] for c in clientes}
    categoria_por_sku = {p["sku"]: p["categoria"] for p in produtos}
    dentro = total = 0
    for ped in pedidos:
        assert ped["_id"].startswith("ped_") and ped["total"] > 0 and ped["status"] == "entregue"
        for item in ped["itens"]:
            total += 1
            dentro += categoria_por_sku[item["sku"]] in PERSONAS[persona_por_id[ped["cliente"]["id"]]]
    assert dentro / total >= 0.7


def test_gerar_avaliacoes_notas_validas_e_unicas():
    produtos = carregar_produtos()
    clientes = gerar_clientes(n=10, seed=2)
    pedidos = gerar_pedidos(clientes, produtos, n=60, seed=2)
    avaliacoes = gerar_avaliacoes(pedidos, seed=2)
    assert avaliacoes and all(1 <= a["nota"] <= 5 for a in avaliacoes)
    pares = [(a["cliente_id"], a["sku"]) for a in avaliacoes]
    assert len(pares) == len(set(pares))


def test_seed_mongo_em_mongomock_popula_tres_colecoes(db):
    produtos = carregar_produtos()
    clientes = gerar_clientes(n=5, seed=3)
    pedidos = gerar_pedidos(clientes, produtos, n=10, seed=3)
    seed_mongo(db, produtos, clientes, pedidos)
    assert db.produtos.count_documents({}) == len(produtos)
    assert db.produtos.find_one({"_id": produtos[0]["sku"]})["nome"] == produtos[0]["nome"]
    assert db.clientes.count_documents({}) == 5
    assert db.pedidos.count_documents({}) == 10
    seed_mongo(db, produtos, clientes, pedidos)  # recarga é idempotente
    assert db.produtos.count_documents({}) == len(produtos)
    assert db.clientes.count_documents({}) == 5
