"""Dublês de teste compartilhados."""
from __future__ import annotations


class FakeNeo4j:
    """Substitui Neo4jService nos testes unitários.

    Grava cada chamada em `chamadas` como (query, params) e devolve, em ordem,
    as respostas pré-carregadas em `respostas` (lista de listas de dicts).
    """

    def __init__(self, respostas: list[list[dict]] | None = None):
        self.respostas = list(respostas or [])
        self.chamadas: list[tuple[str, dict]] = []

    def run(self, query: str, **params) -> list[dict]:
        self.chamadas.append((query, params))
        if self.respostas:
            return self.respostas.pop(0)
        return []

    def ensure_constraints(self) -> None:
        self.chamadas.append(("ensure_constraints", {}))

    def verificar_conexao(self) -> bool:
        return True

    def close(self) -> None:
        pass
