"""Log de operações executadas nos bancos, exibido na tela "Bastidores".

Cada serviço recebe um OpLog opcional e registra o que fez em cada banco
(MongoDB, Redis ou Neo4j). O log vive na sessão do usuário, não em banco.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Operacao:
    banco: str          # "MongoDB" | "Redis" | "Neo4j"
    operacao: str       # ex.: "find", "HINCRBY", "CYPHER"
    detalhe: str        # texto livre: chave, filtro, query...
    quando: datetime = field(default_factory=datetime.now)


class OpLog:
    def __init__(self, limite: int = 50):
        self._itens: deque[Operacao] = deque(maxlen=limite)
        self.total = 0  # contador monotônico: continua subindo quando a janela (deque) já está cheia

    def registrar(self, banco: str, operacao: str, detalhe: str) -> None:
        self._itens.append(Operacao(banco=banco, operacao=operacao, detalhe=detalhe))
        self.total += 1

    def recentes(self, n: int = 20) -> list[Operacao]:
        """Devolve as últimas operações, da mais recente para a mais antiga."""
        return list(reversed(self._itens))[:n]

    def limpar(self) -> None:
        self._itens.clear()
        self.total = 0
