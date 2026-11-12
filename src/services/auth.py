"""Autenticação: cadastro/login no MongoDB e sessão (token) no Redis.

Por que assim?
- O cadastro do cliente é um documento durável -> MongoDB (coleção `clientes`).
- O token de login é volátil e precisa expirar sozinho -> Redis com TTL
  (`sessao:{token}` -> cliente_id). Cada acesso renova o TTL (sessão deslizante).
- Senhas nunca são gravadas em texto puro: PBKDF2-HMAC-SHA256 com salt por usuário.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime

from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from src.observability import OpLog

PBKDF2_ITERACOES = 200_000
CAMPOS_SENSIVEIS = ("senha_hash", "salt")


class EmailJaCadastradoError(Exception):
    pass


def hash_senha(senha: str, salt: bytes | None = None) -> tuple[str, str]:
    """Devolve (hash_hex, salt_hex). Gera salt de 16 bytes quando não informado."""
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), salt, PBKDF2_ITERACOES)
    return digest.hex(), salt.hex()


def verificar_senha(senha: str, hash_hex: str, salt_hex: str) -> bool:
    calculado, _ = hash_senha(senha, bytes.fromhex(salt_hex))
    return hmac.compare_digest(calculado, hash_hex)


def _publico(cliente: dict | None) -> dict | None:
    if cliente is None:
        return None
    return {k: v for k, v in cliente.items() if k not in CAMPOS_SENSIVEIS}


class AuthService:
    def __init__(self, db: Database, redis, session_ttl: int, oplog: OpLog | None = None):
        self.db = db
        self.redis = redis
        self.session_ttl = session_ttl
        self.oplog = oplog

    # ---------- helpers ----------
    def _log(self, banco: str, operacao: str, detalhe: str) -> None:
        if self.oplog:
            self.oplog.registrar(banco, operacao, detalhe)

    @staticmethod
    def chave_sessao(token: str) -> str:
        return f"sessao:{token}"

    @staticmethod
    def novo_token() -> str:
        return secrets.token_urlsafe(32)

    # ---------- MongoDB ----------
    def registrar(self, nome: str, email: str, senha: str) -> dict:
        email = email.strip().lower()
        if self.db.clientes.find_one({"email": email}):
            raise EmailJaCadastradoError(email)
        senha_hash, salt = hash_senha(senha)
        cliente = {
            "_id": f"cli_{uuid.uuid4().hex[:8]}",
            "nome": nome.strip(),
            "email": email,
            "senha_hash": senha_hash,
            "salt": salt,
            "criado_em": datetime.now(),
        }
        try:
            self.db.clientes.insert_one(cliente)
        except DuplicateKeyError as exc:  # índice único protege contra corrida
            raise EmailJaCadastradoError(email) from exc
        self._log("MongoDB", "insert_one", f"clientes {{_id: {cliente['_id']}, email: {email}}}")
        return _publico(cliente)

    # ---------- MongoDB + Redis ----------
    def login(self, email: str, senha: str) -> str | None:
        email = email.strip().lower()
        cliente = self.db.clientes.find_one({"email": email})
        self._log("MongoDB", "find_one", f"clientes {{email: {email}}}")
        if not cliente or not verificar_senha(senha, cliente["senha_hash"], cliente["salt"]):
            return None
        token = self.novo_token()
        self.redis.set(self.chave_sessao(token), cliente["_id"], ex=self.session_ttl)
        self._log("Redis", "SET EX", f"{self.chave_sessao(token)[:24]}… -> {cliente['_id']} (TTL {self.session_ttl}s)")
        return token

    def logout(self, token: str) -> None:
        self.redis.delete(self.chave_sessao(token))
        self._log("Redis", "DEL", f"{self.chave_sessao(token)[:24]}…")

    def cliente_do_token(self, token: str | None) -> dict | None:
        """Resolve o token para o cliente; renova o TTL (sessão deslizante)."""
        if not token:
            return None
        chave = self.chave_sessao(token)
        cliente_id = self.redis.get(chave)
        if not cliente_id:
            return None
        self.redis.expire(chave, self.session_ttl)
        cliente = self.db.clientes.find_one({"_id": cliente_id})
        self._log("Redis", "GET + EXPIRE", f"{chave[:24]}… -> {cliente_id}")
        return _publico(cliente)
