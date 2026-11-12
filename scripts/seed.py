"""Carga inicial dos três bancos (MongoDB, Redis e Neo4j).

Uso:
    python scripts/seed.py            # cria índices/constraints e carrega os dados
    python scripts/seed.py --reset    # apaga tudo antes de carregar

Gera dados fictícios em português (Faker pt_BR) de forma determinística:
- 42 produtos reais de eletrônicos/games (scripts/data/produtos.json)
- 30 clientes com "persona" (gamer, profissional, mobile), senha 123456
- 160 pedidos históricos coerentes com a persona (para o grafo recomendar bem)
- avaliações (1 a 5) para ~70 % dos itens comprados

Usuário de demonstração: ana@techstore.com / 123456
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import unicodedata
import uuid
from datetime import datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from faker import Faker  # noqa: E402

from src.services.auth import hash_senha  # noqa: E402

ARQUIVO_PRODUTOS = RAIZ / "scripts" / "data" / "produtos.json"
CATEGORIAS = ["Notebooks", "Smartphones", "Periféricos", "Consoles", "Jogos", "Áudio", "Acessórios"]
PERSONAS = {
    "gamer": ["Consoles", "Jogos", "Periféricos"],
    "profissional": ["Notebooks", "Periféricos", "Áudio"],
    "mobile": ["Smartphones", "Áudio", "Acessórios"],
}
SENHA_PADRAO = "123456"
CLIENTE_DEMO = {"nome": "Ana Souza", "email": "ana@techstore.com", "persona": "gamer"}
FORMAS_PAGAMENTO = ["pix", "cartao", "boleto"]


# ----------------------------------------------------------------------------
# Geração de dados (puro, determinístico, testável sem banco)
# ----------------------------------------------------------------------------
def carregar_produtos() -> list[dict]:
    with open(ARQUIVO_PRODUTOS, encoding="utf-8") as f:
        return json.load(f)


def _slug(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return "".join(ch for ch in sem_acento.lower() if ch.isalnum() or ch == " ").replace(" ", ".")


def gerar_clientes(n: int = 30, seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    fake = Faker("pt_BR")
    fake.seed_instance(seed)
    personas = list(PERSONAS)
    clientes = []
    emails = set()
    for i in range(n):
        if i == 0:
            nome, email, persona = CLIENTE_DEMO["nome"], CLIENTE_DEMO["email"], CLIENTE_DEMO["persona"]
        else:
            nome = fake.name()
            email = f"{_slug(nome)}{i}@exemplo.com"
            persona = personas[(i - 1) % len(personas)]
        if email in emails:
            email = f"{i}.{email}"
        emails.add(email)
        senha_hash, salt = hash_senha(SENHA_PADRAO, salt=rng.randbytes(16))
        clientes.append({
            "_id": f"cli_{rng.getrandbits(32):08x}",
            "nome": nome,
            "email": email,
            "senha_hash": senha_hash,
            "salt": salt,
            "persona": persona,
            "endereco": {
                "rua": fake.street_address(),
                "cidade": fake.city(),
                "uf": fake.estado_sigla(),
                "cep": fake.postcode(),
            },
            "criado_em": datetime(2026, 1, 1) + timedelta(days=rng.randint(0, 200)),
        })
    return clientes


def _escolher_produto(rng: random.Random, produtos: list[dict], persona: str) -> dict:
    """80 % das vezes escolhe um produto das categorias da persona."""
    if rng.random() < 0.8:
        candidatos = [p for p in produtos if p["categoria"] in PERSONAS[persona]]
    else:
        candidatos = produtos
    return rng.choice(candidatos)


def gerar_pedidos(clientes: list[dict], produtos: list[dict], n: int = 160, seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    agora = datetime.now()
    # garante pelo menos um pedido por cliente, depois completa aleatoriamente
    compradores = list(clientes) if n >= len(clientes) else rng.sample(clientes, n)
    compradores += [rng.choice(clientes) for _ in range(n - len(compradores))]
    pedidos = []
    for cliente in compradores:
        itens: dict[str, dict] = {}
        for _ in range(rng.choice([1, 1, 2, 2, 3])):
            p = _escolher_produto(rng, produtos, cliente["persona"])
            qtd = rng.choice([1, 1, 1, 2]) if p["categoria"] in ("Jogos", "Acessórios") else 1
            if p["sku"] in itens:
                itens[p["sku"]]["quantidade"] += qtd
            else:
                itens[p["sku"]] = {"sku": p["sku"], "nome": p["nome"], "preco_unitario": float(p["preco"]),
                                   "quantidade": qtd}
        for item in itens.values():
            item["subtotal"] = round(item["preco_unitario"] * item["quantidade"], 2)
        criado_em = agora - timedelta(days=rng.randint(1, 180), hours=rng.randint(0, 23), minutes=rng.randint(0, 59))
        pedidos.append({
            "_id": f"ped_{rng.getrandbits(48):012x}",
            "cliente": {"id": cliente["_id"], "nome": cliente["nome"], "email": cliente["email"]},
            "itens": list(itens.values()),
            "total": round(sum(i["subtotal"] for i in itens.values()), 2),
            "forma_pagamento": rng.choice(FORMAS_PAGAMENTO),
            "endereco_entrega": cliente["endereco"],
            "status": "entregue",
            "criado_em": criado_em,
        })
    pedidos.sort(key=lambda p: p["criado_em"])
    return pedidos


def gerar_avaliacoes(pedidos: list[dict], seed: int = 42, produtos: list[dict] | None = None,
                     clientes: list[dict] | None = None) -> list[dict]:
    """~70 % dos itens comprados recebem nota; notas mais altas dentro da persona."""
    rng = random.Random(seed)
    categoria_por_sku = {p["sku"]: p["categoria"] for p in (produtos or carregar_produtos())}
    persona_por_id = {c["_id"]: c["persona"] for c in (clientes or [])}
    avaliacoes: dict[tuple[str, str], dict] = {}
    for ped in pedidos:
        cliente_id = ped["cliente"]["id"]
        for item in ped["itens"]:
            chave = (cliente_id, item["sku"])
            if chave in avaliacoes or rng.random() > 0.7:
                continue
            persona = persona_por_id.get(cliente_id)
            dentro = persona is not None and categoria_por_sku.get(item["sku"]) in PERSONAS[persona]
            nota = rng.choice([4, 5, 5, 4, 3]) if dentro else rng.choice([2, 3, 4, 3, 5])
            avaliacoes[chave] = {
                "cliente_id": cliente_id,
                "sku": item["sku"],
                "nota": nota,
                "data": (ped["criado_em"] + timedelta(days=rng.randint(2, 15))).date().isoformat(),
            }
    return list(avaliacoes.values())


# ----------------------------------------------------------------------------
# Carga nos bancos
# ----------------------------------------------------------------------------
def seed_mongo(db, produtos: list[dict], clientes: list[dict], pedidos: list[dict]) -> dict:
    """Substitui o conteúdo das coleções (idempotente) e cria os índices."""
    from src.db.mongo import ensure_indexes

    db.produtos.delete_many({})
    db.clientes.delete_many({})
    db.pedidos.delete_many({})
    docs_produtos = [dict(p, _id=p["sku"], criado_em=datetime.now()) for p in produtos]
    db.produtos.insert_many(docs_produtos)
    db.clientes.insert_many([dict(c) for c in clientes])
    if pedidos:
        db.pedidos.insert_many([dict(p) for p in pedidos])
    ensure_indexes(db)
    return {"produtos": len(docs_produtos), "clientes": len(clientes), "pedidos": len(pedidos)}


def seed_neo4j(svc, produtos: list[dict], clientes: list[dict], pedidos: list[dict],
               avaliacoes: list[dict], reset: bool = False) -> dict:
    if reset:
        svc.run("MATCH (n) DETACH DELETE n")
    svc.ensure_constraints()
    svc.run("UNWIND $categorias AS nome MERGE (:Categoria {nome: nome})", categorias=CATEGORIAS)
    svc.run(
        """
        UNWIND $produtos AS p
        MERGE (x:Produto {sku: p.sku})
        SET x.nome = p.nome, x.preco = p.preco, x.categoria = p.categoria, x.marca = p.marca
        WITH x, p
        MATCH (c:Categoria {nome: p.categoria})
        MERGE (x)-[:PERTENCE_A]->(c)
        """,
        produtos=[{"sku": p["sku"], "nome": p["nome"], "preco": float(p["preco"]),
                   "categoria": p["categoria"], "marca": p["marca"]} for p in produtos],
    )
    svc.run(
        "UNWIND $clientes AS c MERGE (x:Cliente {id: c.id}) SET x.nome = c.nome, x.persona = c.persona",
        clientes=[{"id": c["_id"], "nome": c["nome"], "persona": c.get("persona")} for c in clientes],
    )
    compras = [
        {"cliente_id": ped["cliente"]["id"], "sku": item["sku"], "pedido_id": ped["_id"],
         "quantidade": item["quantidade"], "data": ped["criado_em"].isoformat(timespec="seconds")}
        for ped in pedidos for item in ped["itens"]
    ]
    svc.run(
        """
        UNWIND $compras AS r
        MATCH (c:Cliente {id: r.cliente_id}), (p:Produto {sku: r.sku})
        MERGE (c)-[k:COMPROU {pedido_id: r.pedido_id}]->(p)
        SET k.data = datetime(r.data), k.quantidade = r.quantidade
        """,
        compras=compras,
    )
    svc.run(
        """
        UNWIND $avaliacoes AS a
        MATCH (c:Cliente {id: a.cliente_id}), (p:Produto {sku: a.sku})
        MERGE (c)-[r:AVALIOU]->(p)
        SET r.nota = a.nota, r.data = date(a.data)
        """,
        avaliacoes=avaliacoes,
    )
    return {"categorias": len(CATEGORIAS), "produtos": len(produtos), "clientes": len(clientes),
            "COMPROU": len(compras), "AVALIOU": len(avaliacoes)}


def seed_redis(r, produtos: list[dict], seed: int = 42) -> dict:
    """Limpa estado volátil e popula o ranking de produtos mais acessados."""
    rng = random.Random(seed)
    apagadas = 0
    for padrao in ("cache:*", "carrinho:*", "sessao:*", "ranking:*"):
        chaves = list(r.scan_iter(match=padrao))
        if chaves:
            apagadas += r.delete(*chaves)
    ranking = {p["sku"]: rng.randint(5, 120) for p in produtos}
    r.zadd("ranking:produtos_acessados", ranking)
    return {"chaves_apagadas": apagadas, "ranking": len(ranking)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Carga inicial do TechStore (MongoDB + Redis + Neo4j)")
    parser.add_argument("--reset", action="store_true", help="apaga os dados existentes antes de carregar")
    parser.add_argument("--clientes", type=int, default=30)
    parser.add_argument("--pedidos", type=int, default=160)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    from src.config import Settings
    from src.db.mongo import get_mongo_db
    from src.db.neo4j_client import Neo4jService
    from src.db.redis_client import get_redis

    settings = Settings.from_env()
    print("Gerando dados...")
    produtos = carregar_produtos()
    clientes = gerar_clientes(args.clientes, args.seed)
    pedidos = gerar_pedidos(clientes, produtos, args.pedidos, args.seed)
    avaliacoes = gerar_avaliacoes(pedidos, args.seed, produtos, clientes)

    print(f"MongoDB  ({settings.mongo_uri}/{settings.mongo_db})...")
    db = get_mongo_db(settings)
    if args.reset:
        db.client.drop_database(settings.mongo_db)
    print("  ", seed_mongo(db, produtos, clientes, pedidos))

    print(f"Redis    ({settings.redis_host}:{settings.redis_port})...")
    print("  ", seed_redis(get_redis(settings), produtos, args.seed))

    print(f"Neo4j    ({settings.neo4j_uri})...")
    svc = Neo4jService(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password, settings.neo4j_database)
    try:
        print("  ", seed_neo4j(svc, produtos, clientes, pedidos, avaliacoes, reset=True))
    finally:
        svc.close()

    print(f"\nPronto. Login de demonstração: {CLIENTE_DEMO['email']} / {SENHA_PADRAO}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
