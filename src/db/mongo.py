"""Conexão com o MongoDB e criação de índices.

Coleções:
- produtos  : catálogo com especificações flexíveis (_id = SKU)
- clientes  : cadastro + hash de senha (_id = "cli_xxxxxxxx")
- pedidos   : pedidos finalizados com snapshot dos itens (_id = "ped_xxxxxxxxxxxx")
"""
from __future__ import annotations

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.database import Database

from src.config import Settings


def get_mongo_db(settings: Settings) -> Database:
    client = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=3000)
    return client[settings.mongo_db]


def ensure_indexes(db: Database) -> None:
    """Cria os índices usados pela aplicação (idempotente)."""
    db.produtos.create_index([("categoria", ASCENDING)], name="idx_categoria")
    db.produtos.create_index([("marca", ASCENDING)], name="idx_marca")
    db.produtos.create_index([("preco", ASCENDING)], name="idx_preco")
    db.clientes.create_index([("email", ASCENDING)], name="idx_email_unico", unique=True)
    db.pedidos.create_index(
        [("cliente.id", ASCENDING), ("criado_em", DESCENDING)], name="idx_pedidos_cliente_data"
    )


def verificar_conexao(db: Database) -> bool:
    try:
        db.client.admin.command("ping")
        return True
    except Exception:
        return False
