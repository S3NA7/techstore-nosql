from src.services.recommendations import RecommendationService
from tests.fakes import FakeNeo4j


def test_quem_comprou_passa_parametros_e_devolve_linhas():
    neo = FakeNeo4j(respostas=[[{"sku": "JG-001", "nome": "Jogo", "preco": 299.0, "forca": 3}]])
    recs = RecommendationService(neo)
    res = recs.quem_comprou_tambem_comprou("cli_1")
    assert res == [{"sku": "JG-001", "nome": "Jogo", "preco": 299.0, "forca": 3}]
    query, params = neo.chamadas[0]
    assert params == {"cliente_id": "cli_1", "limite": 8}
    assert "COMPROU" in query and "NOT (c)-[:COMPROU]->(rec)" in query


def test_perfil_similar_usa_avaliou_com_diferenca_menor_que_1():
    neo = FakeNeo4j()
    RecommendationService(neo).perfil_similar_por_avaliacao("cli_1", limite=5)
    query, params = neo.chamadas[0]
    assert params == {"cliente_id": "cli_1", "limite": 5}
    assert "AVALIOU" in query and "abs(a1.nota - a2.nota) < 1" in query


def test_relacionados_populares_e_caminho():
    neo = FakeNeo4j()
    recs = RecommendationService(neo)
    recs.relacionados_ao_produto("NB-001")
    recs.populares_na_categoria("Jogos", limite=3)
    recs.caminho_recomendacao("cli_1", "NB-001")
    assert neo.chamadas[0][1] == {"sku": "NB-001", "limite": 6}
    assert neo.chamadas[1][1] == {"categoria": "Jogos", "limite": 3}
    assert "shortestPath" in neo.chamadas[2][0]
    assert neo.chamadas[2][1] == {"cliente_id": "cli_1", "sku": "NB-001"}


def test_subgrafo_devolve_nos_e_arestas_unicos():
    neo = FakeNeo4j(respostas=[[
        {"origem_id": "cli_1", "origem_rotulo": "Cliente", "origem_nome": "Ana",
         "tipo": "COMPROU", "destino_id": "NB-001", "destino_rotulo": "Produto", "destino_nome": "Notebook"},
        {"origem_id": "cli_2", "origem_rotulo": "Cliente", "origem_nome": "Bia",
         "tipo": "COMPROU", "destino_id": "NB-001", "destino_rotulo": "Produto", "destino_nome": "Notebook"},
    ]])
    nos, arestas = RecommendationService(neo).subgrafo_cliente("cli_1")
    assert {n["id"] for n in nos} == {"cli_1", "cli_2", "NB-001"}
    assert len(arestas) == 2 and arestas[0] == {"origem": "cli_1", "destino": "NB-001", "tipo": "COMPROU"}
