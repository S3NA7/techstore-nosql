# Enunciado do Projeto Final (transcrição do .docx do professor)

PROJETO FINAL E GUIA DA DISCIPLINA
Disciplina: Implementação de Bancos de Dados NoSQLTecnologias Envolvidas: MongoDB, Redis, Neo4j, Python e StreamlitFormato de Trabalho: Grupos de 04 a 06 alunosAvaliação: Entrega de Código/Repositório + Defesa Oral Técnica
Prof. Ricardo Roberto de Lima

1. APRESENTAÇÃO E OBJETIVO DO PROJETO
O objetivo deste projeto prático final é proporcionar uma experiência real de arquitetura e desenvolvimento poliglota em bancos de dados NoSQL (Polyglot Persistence). Cada equipe desenvolverá uma aplicação funcional utilizando Python e a biblioteca Streamlit para gerenciar e integrar três soluções distintas e complementares de armazenamento de dados:
- MongoDB (Modelo Orientado a Documentos): Responsável pela persistência de dados estruturados e semi-estruturados flexíveis, catálogos e históricos.
- Redis (Modelo Chave-Valor / In-Memory): Responsável por tarefas de altíssima performance, tais como gerenciamento de sessões, controle de estados em tempo real e cache de leituras.
- Neo4j (Modelo de Grafos): Responsável por modelar e consultar conexões complexas, rotas, relacionamentos e algoritmos de recomendação baseados na técnica de Index-Free Adjacency.

2. REGRAS GERAIS E FORMATO DO TRABALHO
- Composição dos Grupos: Mínimo de 02 e máximo de 06 alunos por equipe.
- Componentes Solicitados:
- Repositório de Código: Código-fonte completo em Python/Streamlit devidamente organizado, comentado e com arquivo requirements.txt ou Docker Compose.
- Scripts de Carga e Inicialização: Scripts para criação dos schemas/coleções, índices e carga inicial de dados nos três bancos de dados.
- Defesa Oral e Apresentação: Todos os membros da equipe devem estar presentes e aptos a responder perguntas conceituais e práticas durante a arguição técnica final.

3. MÓDULO DE REFERÊNCIA TÉCNICA (NEO4J & CYPHER)
Para a correta integração com o banco de dados em grafo Neo4j (local via Neo4j Desktop ou em nuvem via Neo4j AuraDB), a equipe deverá seguir o modelo de conexão e consultas de referência abaixo:
3.1. Parâmetros de Conexão (Variáveis de Ambiente / AuraDB)
vNEO4J_URI=neo4j+s://cb70a3bc.databases.neo4j.ioNEO4J_USERNAME=neo4jNEO4J_PASSWORD=<SUA_SENHA>NEO4J_DATABASE=neo4j
### 3.2. Exemplo de Conexão com Python (`neo4j-driver`)
```python

from neo4j import GraphDatabase

class Neo4jService:

    def __init__(self, uri, user, password):

        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):

        self.driver.close()

    def get_recommendations(self, user_name):

        query = """
        MATCH (p1:Pessoa {nome: $nome})-[r1:ASSISTIU]->(f:Filme)<-[r2:ASSISTIU]-(p2:Pessoa)
        WHERE p1 <> p2 AND abs(r1.nota - r2.nota) < 1
        RETURN DISTINCT f.titulo AS recomendacao, p2.nome AS origem LIMIT 10;
        """

        with self.driver.session() as session:

            result = session.run(query, nome=user_name)

            return [record["recomendacao"] for record in result]


4. ARQUITETURA OBRIGATÓRIA DA APLICAÇÃO
A aplicação Streamlit atuará como orquestradora central, conectando-se diretamente às três instâncias de banco de dados conforme o fluxo arquitetural:                  +-----------------------------------+
                  |   Interface Streamlit (Python)    |
|---|
                    /               |               \
                   /                |                \
    +-----------------+    +-----------------+    +------------------+
    | MongoDB Driver  |    |  Redis Client   |    |  Neo4j Driver    |
    +-----------------+    +-----------------+    +------------------+
            |                       |                      |
            v                       v                      v
    +-----------------+    +-----------------+    +------------------+
    |    MongoDB      |    |      Redis      |    |      Neo4j       |
    | (Catálogo/Logs) |    | (Cache/Sessão)  |    | (Grafo/Conexões) |
    +-----------------+    +-----------------+    +------------------+

5. ESTUDOS DE CASO DISPONÍVEIS (ESCOLHER 01)
Cada grupo deverá selecionar obrigatoriamente UM dos dois cenários propostos a seguir para projetar e implementar na disciplina:
Estudo de Caso 01: E-Commerce Inteligente & Motor de Recomendação
Responsabilidade dos Bancos:
- MongoDB: Armazena o catálogo de produtos com esquemas flexíveis (especificações em JSON, imagens, marca, categorias) e grava os pedidos finalizados com histórico do comprador e valores.
- Redis: Mantém o carrinho de compras dinâmico da sessão ativa do cliente, controla tokens de login e aplica Cache Invalidation (TTL) para consultas de produtos mais acessados.
- Neo4j: Armazena o grafo contendo Nós (:Cliente), (:Produto) e (:Categoria) com os relacionamentos [:COMPROU] e [:AVALIOU], executando algoritmos Cypher de recomendação cruzada ("Clientes com perfil similar também compraram...").
Telas Mínimas no Streamlit:
- Catálogo & Busca de Produtos: Interface de navegação consultando o MongoDB e aproveitando respostas do Redis em cache.
- Carrinho Ativo: Adição, alteração e exclusão rápida de itens no Redis em tempo real.
- Painel de Recomendação (Grafo): Bloco interativo exibindo recomendações personalizadas geradas no Neo4j.
- Checkout: Persistência do pedido no MongoDB e limpeza do carrinho no Redis.

Estudo de Caso 02: Rede Social Profissional & Plataforma de Talentos/Mentoria
Responsabilidade dos Bancos:
- MongoDB: Armazena o perfil estendido dos usuários (experiências em JSON, formação, certificações), posts da linha do tempo e anexos multimídia.
- Redis: Controla os estados de presença online/offline dos profissionais, gerenciamento de sessões ativas e contador em tempo real de notificações não lidas.
- Neo4j: Mantém a rede de conexões profissionais ((:Pessoa)-[:CONECTADO_COM]->(:Pessoa)), mapa de habilidades ((:Pessoa)-[:POSSUI_HABILIDADE]->(:Habilidade)) e histórico profissional ((:Pessoa)-[:TRABALHA_EM]->(:Empresa)), permitindo consultas de menor caminho (shortestPath).
Telas Mínimas no Streamlit:
- Feed & Perfil do Usuário: Perfil rico e postagens alimentadas pelo MongoDB.
- Dashboard de Presença & Notificações: Indicadores em tempo real utilizando Redis.
- Rede de Conexões & Busca de Mentores: Exibição gráfica ou em lista dos graus de separação entre profissionais e recomendações de mentores baseadas em grafos Neo4j.
Estudo de Caso 03: Plataforma de Telemedicina & Gestão de Prontuários Médicos
Responsabilidade dos Bancos:
- MongoDB: Armazena os prontuários eletrônicos detalhados dos pacientes em formato JSON flexível (histórico de consultas, prescrições, exames anexados e laudos), além do cadastro completo de profissionais de saúde e especialidades.
- Redis: Controla a fila de espera em tempo real da recepção virtual (com ordenação via Sorted Sets), mantém tokens de sessão das consultas ativas e faz cache temporário das agendas do dia para consultas rápidas.
- Neo4j: Mantém o grafo de histórico epidemiológico e interações clínicas, estruturado com (:Paciente), (:Diagnostico), (:Medicamento) e (:Medico). Executa consultas em Cypher para identificar interações medicamentosas (ex: medicamentos prescritos que possuem contraindicação cruzada) e mapeamento de diagnósticos correlacionados em cadeia.
Telas Mínimas no Streamlit:
- Prontuário & Atendimento Médico: Interface de navegação para consulta de históricos, edição flexível de diagnósticos e upload/anexo de laudos direto no MongoDB.
- Painel da Recepção Virtual & Fila: Visualização dinâmica dos pacientes aguardando atendimento e agendamentos do dia atualizados via Redis.
- Mapeamento Clínico & Alertas de Segurança (Grafo): Painel interativo exibindo a teia de diagnósticos e alertas automáticos gerados pelo Neo4j sobre prescrições incompatíveis ou histórico do paciente.
- Finalização da Consulta: Emissão do laudo/receita com persistência no MongoDB e atualização imediata do status da fila no Redis.
Estudo de Caso 04: Sistema Logístico & Rastreamento de Cadeia de Suprimentos (Supply Chain)
Responsabilidade dos Bancos:
- MongoDB: Armazena o registro detalhado das mercadorias, lotes, especificações fiscais/técnicas, histórico de auditoria e manifestos de transporte em documentos JSON.
- Redis: Mantém a telemetria em tempo real das frotas (coordenadas GPS atualizadas frequentemente, velocidade e temperatura de baús refrigerados) e controle de pub/sub para alertas instantâneos de desvio de rota ou acidentes.
- Neo4j: Armazena a malha logística de distribuição contendo os nós (:CentroDistribuição), (:PontoTransbordo), (:Cliente) e (:Rota). Executa algoritmos Cypher como shortestPath (menor caminho) e rotas de menor custo para otimização de entregas e análise de impacto caso algum nó da rede fique inoperante.

Telas Mínimas no Streamlit:
- Gestão de Lotes & Inventário: Consulta e cadastro de produtos, lotes e documentação de carga armazenados no MongoDB.
- Torre de Controle (Telemetria em Tempo Real): Dashboard dinâmico exibindo a posição atual e métricas de sensores dos veículos em trânsito lidos do Redis.
- Otimizador de Rotas Logísticas (Grafo): Bloco visual com o mapa/grafo de transporte permitindo simular bloqueios de trechos e calcular a rota ideal via Neo4j.
- Despacho & Recebimento de Cargas: Interface para confirmar a entrega, salvar o histórico de recebimento no MongoDB e atualizar a disponibilidade do veículo no Redis.

6. GUIA E ESTRUTURA PARA A APRESENTAÇÃO E DEFESA ORAL
A avaliação final ocorrerá na forma de uma Defesa Oral Técnica com duração de até 10 minutos por grupo.
6.1. Estrutura Recomendada da Apresentação
- Introdução e Problema de Negócio (3 a 5 min): Apresentação da equipe, justificativa do Estudo de Caso escolhido e escopo da solução.
- Arquitetura & Modelagem de Dados (7 a 10 min): Apresentação das decisões arquiteturais:
- Por que determinado dado foi para o MongoDB (Documento).
- Por que determinado dado foi mantido no Redis (Chave-Valor/In-Memory).
- Como o grafo foi modelado no Neo4j (Nós, Relacionamentos, Propriedades e Cypher).
- Demonstração Prática na Interface Streamlit (10 min): Execução do sistema ao vivo. O grupo deverá simular um fluxo de uso completo mostrando as chamadas e atualizações acontecendo nos três bancos simultaneamente.
- Arguição Técnica e Pergunta dos Avaliadores (5 a 7 min): Perguntas direcionadas individualmente aos integrantes do grupo sobre o código, comandos Cypher, estratégias de cache e consultas NoSQL.

7. CRITÉRIOS E MATRIZ DE AVALIAÇÃO
A nota final da equipe será atribuída com base na seguinte matriz de avaliação (0 a 10 pontos):
<w:tblPr><w:tblStyle w:val="a"/><w:tblW w:w="10500" w:type="dxa"/><w:tblInd w:w="0" w:type="dxa"/><w:tblBorders><w:top w:val="single" w:sz="8" w:space="0" w:color="E2E8F0"/><w:left w:val="nil"/><w:bottom w:val="single" w:sz="8" w:space="0" w:color="E2E8F0"/><w:right w:val="nil"/><w:insideH w:val="single" w:sz="8" w:space="0" w:color="EDF2F7"/><w:insideV w:val="nil"/></w:tblBorders><w:tblLayout w:type="fixed"/><w:tblLook w:val="0620" w:firstRow="1" w:lastRow="0" w:firstColumn="0" w:lastColumn="0" w:noHBand="1" w:noVBand="1"/></w:tblPr><w:tblGrid><w:gridCol w:w="3500"/><w:gridCol w:w="3500"/><w:gridCol w:w="3500"/></w:tblGrid><w:tr w:rsidR="004D4C7D" w14:paraId="08ABF7AC" w14:textId="77777777" w:rsidTr="004D4C7D"><w:trPr><w:cnfStyle w:val="100000000000" w:firstRow="1" w:lastRow="0" w:firstColumn="0" w:lastColumn="0" w:oddVBand="0" w:evenVBand="0" w:oddHBand="0" w:evenHBand="0" w:firstRowFirstColumn="0" w:firstRowLastColumn="0" w:lastRowFirstColumn="0" w:lastRowLastColumn="0"/><w:tblHeader/></w:trPr><w:tc><w:tcPr><w:tcW w:w="3500" w:type="dxa"/></w:tcPr><w:p w14:paraId="23DB88C9" w14:textId="77777777" w:rsidR="004D4C7D" w:rsidRDefault="00000000"><w:r><w:t>Critério
Descrição
Peso
Integração Arquitetural NoSQL
Adequação do uso de cada um dos 3 bancos (MongoDB, Redis e Neo4j) de acordo com suas fortalezas específicas (Polyglot Persistence).
25%
Modelagem de Dados & Cypher
Qualidade do design do documento JSON, estruturação de chaves no Redis e consultas em grafo/Cypher no Neo4j.
20%
Aplicação Streamlit & Python
Funcionamento e usabilidade da interface gráfica em Streamlit, organização do código-fonte e tratamento de erros.
25%
Defesa Oral e Domínio Técnico
Desempenho individual e coletivo da equipe durante a explicação e respostas às perguntas dos avaliadores.
30%
