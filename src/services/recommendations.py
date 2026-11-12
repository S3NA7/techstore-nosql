"""Motor de recomendação sobre o grafo do Neo4j.

Por que grafo? "Quem comprou X também comprou Y" é uma travessia de 3 saltos
(Cliente -> Produto <- Cliente -> Produto). Em SQL seriam auto-joins caros; no
Neo4j cada nó guarda ponteiros diretos para seus relacionamentos
(index-free adjacency), então a travessia custa proporcional ao tamanho da
vizinhança e não ao tamanho do banco.
"""
from __future__ import annotations

QUEM_COMPROU_TAMBEM_COMPROU = """
MATCH (c:Cliente {id: $cliente_id})-[:COMPROU]->(p:Produto)<-[:COMPROU]-(outro:Cliente)
WHERE outro <> c
MATCH (outro)-[:COMPROU]->(rec:Produto)
WHERE NOT (c)-[:COMPROU]->(rec)
RETURN rec.sku AS sku, rec.nome AS nome, rec.preco AS preco, rec.categoria AS categoria,
       count(DISTINCT outro) AS forca
ORDER BY forca DESC, rec.nome
LIMIT $limite
"""

# Adaptado do exemplo do enunciado (seção 3.2): clientes com notas parecidas
# (diferença < 1) nos mesmos produtos têm "perfil similar".
PERFIL_SIMILAR_POR_AVALIACAO = """
MATCH (c1:Cliente {id: $cliente_id})-[a1:AVALIOU]->(p:Produto)<-[a2:AVALIOU]-(c2:Cliente)
WHERE c1 <> c2 AND abs(a1.nota - a2.nota) < 1
MATCH (c2)-[a3:AVALIOU]->(rec:Produto)
WHERE a3.nota >= 4 AND NOT (c1)-[:COMPROU]->(rec)
RETURN DISTINCT rec.sku AS sku, rec.nome AS nome, rec.preco AS preco, rec.categoria AS categoria,
       c2.nome AS origem, a3.nota AS nota
ORDER BY nota DESC, nome
LIMIT $limite
"""

RELACIONADOS_AO_PRODUTO = """
MATCH (p:Produto {sku: $sku})<-[:COMPROU]-(c:Cliente)-[:COMPROU]->(rec:Produto)
WHERE rec <> p
RETURN rec.sku AS sku, rec.nome AS nome, rec.preco AS preco, rec.categoria AS categoria,
       count(DISTINCT c) AS forca
ORDER BY forca DESC, rec.nome
LIMIT $limite
"""

POPULARES_NA_CATEGORIA = """
MATCH (p:Produto)-[:PERTENCE_A]->(:Categoria {nome: $categoria})
OPTIONAL MATCH (p)<-[r:COMPROU]-(:Cliente)
RETURN p.sku AS sku, p.nome AS nome, p.preco AS preco, count(r) AS compras
ORDER BY compras DESC, p.nome
LIMIT $limite
"""

CAMINHO_RECOMENDACAO = """
MATCH (c:Cliente {id: $cliente_id}), (p:Produto {sku: $sku})
MATCH caminho = shortestPath((c)-[:COMPROU|AVALIOU*..6]-(p))
RETURN [n IN nodes(caminho) | {rotulo: labels(n)[0], id: coalesce(n.id, n.sku),
                               nome: coalesce(n.nome, n.sku)}] AS nos,
       [r IN relationships(caminho) | type(r)] AS tipos
"""

SUBGRAFO_CLIENTE = """
MATCH (c:Cliente {id: $cliente_id})-[r:COMPROU|AVALIOU]->(p:Produto)
RETURN c.id AS origem_id, 'Cliente' AS origem_rotulo, c.nome AS origem_nome, type(r) AS tipo,
       p.sku AS destino_id, 'Produto' AS destino_rotulo, p.nome AS destino_nome
UNION
MATCH (c:Cliente {id: $cliente_id})-[:COMPROU]->(p:Produto)<-[r:COMPROU]-(outro:Cliente)
WHERE outro <> c
WITH p, outro, r ORDER BY outro.nome LIMIT $limite
RETURN outro.id AS origem_id, 'Cliente' AS origem_rotulo, outro.nome AS origem_nome, type(r) AS tipo,
       p.sku AS destino_id, 'Produto' AS destino_rotulo, p.nome AS destino_nome
UNION
MATCH (c:Cliente {id: $cliente_id})-[:COMPROU]->(:Produto)<-[:COMPROU]-(outro:Cliente)-[r:COMPROU]->(rec:Produto)
WHERE outro <> c AND NOT (c)-[:COMPROU]->(rec)
WITH outro, r, rec ORDER BY outro.nome LIMIT $limite
RETURN outro.id AS origem_id, 'Cliente' AS origem_rotulo, outro.nome AS origem_nome, type(r) AS tipo,
       rec.sku AS destino_id, 'Produto' AS destino_rotulo, rec.nome AS destino_nome
"""


class RecommendationService:
    def __init__(self, neo4j):
        self.neo4j = neo4j

    def quem_comprou_tambem_comprou(self, cliente_id: str, limite: int = 8) -> list[dict]:
        return self.neo4j.run(QUEM_COMPROU_TAMBEM_COMPROU, cliente_id=cliente_id, limite=limite)

    def perfil_similar_por_avaliacao(self, cliente_id: str, limite: int = 8) -> list[dict]:
        return self.neo4j.run(PERFIL_SIMILAR_POR_AVALIACAO, cliente_id=cliente_id, limite=limite)

    def relacionados_ao_produto(self, sku: str, limite: int = 6) -> list[dict]:
        return self.neo4j.run(RELACIONADOS_AO_PRODUTO, sku=sku, limite=limite)

    def populares_na_categoria(self, categoria: str, limite: int = 6) -> list[dict]:
        return self.neo4j.run(POPULARES_NA_CATEGORIA, categoria=categoria, limite=limite)

    def caminho_recomendacao(self, cliente_id: str, sku: str) -> list[dict]:
        """Nós do menor caminho cliente -> produto; cada nó traz `via` (tipo da aresta anterior)."""
        linhas = self.neo4j.run(CAMINHO_RECOMENDACAO, cliente_id=cliente_id, sku=sku)
        if not linhas:
            return []
        nos, tipos = linhas[0]["nos"], linhas[0]["tipos"]
        return [dict(no, via=(tipos[i - 1] if i > 0 else None)) for i, no in enumerate(nos)]

    def subgrafo_cliente(self, cliente_id: str, limite: int = 40) -> tuple[list[dict], list[dict]]:
        """Devolve (nós, arestas) para desenhar a vizinhança do cliente."""
        linhas = self.neo4j.run(SUBGRAFO_CLIENTE, cliente_id=cliente_id, limite=limite)
        nos: dict[str, dict] = {}
        arestas: list[dict] = []
        vistas: set[tuple] = set()
        for linha in linhas:
            nos.setdefault(linha["origem_id"], {"id": linha["origem_id"], "rotulo": linha["origem_rotulo"],
                                                "nome": linha["origem_nome"]})
            nos.setdefault(linha["destino_id"], {"id": linha["destino_id"], "rotulo": linha["destino_rotulo"],
                                                 "nome": linha["destino_nome"]})
            aresta = (linha["origem_id"], linha["destino_id"], linha["tipo"])
            if aresta not in vistas:
                vistas.add(aresta)
                arestas.append({"origem": aresta[0], "destino": aresta[1], "tipo": aresta[2]})
        return list(nos.values()), arestas
