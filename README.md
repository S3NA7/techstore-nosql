# TechStore — E-commerce Inteligente com Persistência Poliglota

Projeto final da disciplina **Implementação de Bancos de Dados NoSQL** (Prof. Ricardo Roberto de Lima).
Estudo de Caso 01: *E-Commerce Inteligente & Motor de Recomendação*.

Uma loja de eletrônicos e games em **Python + Streamlit** que integra três bancos, cada um fazendo o que faz melhor:

| Banco | Modelo | O que guarda aqui |
|---|---|---|
| **MongoDB** | Documentos | Catálogo de produtos com especificações flexíveis por categoria, cadastro de clientes e pedidos finalizados (histórico) |
| **Redis** | Chave-valor em memória | Token de login com TTL, carrinho em tempo real (Hash), cache de produtos e buscas com invalidação, ranking de produtos mais acessados (Sorted Set) |
| **Neo4j** | Grafo | `(:Cliente)-[:COMPROU]->(:Produto)`, `(:Cliente)-[:AVALIOU]->(:Produto)`, `(:Produto)-[:PERTENCE_A]->(:Categoria)` e as consultas Cypher de recomendação |

```
                  +-----------------------------------+
                  |   Interface Streamlit (app.py)    |
                  +-----------------------------------+
                    /               |               \
    +-----------------+    +-----------------+    +------------------+
    | pymongo         |    |  redis-py       |    |  neo4j-driver    |
    +-----------------+    +-----------------+    +------------------+
            |                       |                      |
    +-----------------+    +-----------------+    +------------------+
    |    MongoDB      |    |      Redis      |    |      Neo4j       |
    | catálogo/pedidos|    | sessão/carrinho |    | grafo/recomend.  |
    +-----------------+    +-----------------+    +------------------+
```

Documentação complementar:

- [docs/arquitetura.md](docs/arquitetura.md) — modelagem de cada banco, chaves, Cypher e as decisões "por que esse dado foi para esse banco"
- [docs/roteiro_defesa.md](docs/roteiro_defesa.md) — roteiro da apresentação de 10 min e perguntas prováveis
- [docs/enunciado.md](docs/enunciado.md) — transcrição do enunciado do professor

## Como rodar

### Pré-requisitos

- Docker Desktop (para MongoDB, Redis e Neo4j)
- Python 3.11 ou superior
- Git

### 0. Clonar o repositório (no PC da faculdade)

```bash
git clone https://github.com/S3NA7/techstore-nosql.git
cd techstore-nosql
```

### 1. Subir os bancos

```bash
docker compose up -d
```

Sobe `mongo:7` (porta 27017), `redis:7` (6379) e `neo4j:5` (7474 e 7687, usuário `neo4j`, senha `techstore123`).
Aguarde os três ficarem `healthy` em `docker compose ps`.

### 2. Preparar o ambiente Python

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows   (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env          # Windows   (Linux/macOS: cp .env.example .env)
```

> **Windows:** mantenha `127.0.0.1` no `.env` em vez de `localhost`. O nome `localhost` resolve primeiro
> para IPv6 (`::1`) e o Docker Desktop aceita a conexão mas não a encaminha, o que causa timeouts no Redis e no Neo4j.

### 3. Carga inicial dos três bancos

```bash
python scripts/seed.py --reset
```

Cria índices (Mongo), constraints (Neo4j) e carrega 42 produtos, 30 clientes, 160 pedidos históricos,
~300 relacionamentos `COMPROU`, ~190 `AVALIOU` e o ranking de acessos no Redis. Os dados são determinísticos (seed 42).

### 4. Rodar a aplicação

```bash
streamlit run app.py
```

Abra http://localhost:8501 e entre com **ana@techstore.com** / **123456**
(todos os clientes gerados usam a senha `123456`).

### Alternativa: tudo no Docker

```bash
docker compose --profile app up -d --build
docker compose exec app python scripts/seed.py --reset
```

A aplicação fica em http://localhost:8501 e usa `.env.docker` (hosts = nomes dos serviços).

## Telas

| Tela | O que faz | Bancos envolvidos |
|---|---|---|
| **Entrar / Criar conta** | Cadastro e login; mostra a saúde dos três bancos | Mongo (`clientes`, hash PBKDF2) · Redis (`sessao:{token}` com TTL) |
| **Catálogo** | Busca por texto, categoria, marca e ordenação; cards; detalhes com especificações | Mongo (`produtos`) · Redis (`cache:produto:*`, `cache:busca:*`, `ranking:produtos_acessados`) · Neo4j ("quem comprou também comprou") |
| **Carrinho** | Adicionar, alterar quantidade, remover, limpar | Redis (`carrinho:{cliente_id}` Hash com TTL) · Mongo (preço e estoque atuais) |
| **Recomendações** | Compras cruzadas, perfil similar por avaliação, populares por categoria, grafo interativo e explicação por `shortestPath` | Neo4j |
| **Checkout** | Persiste o pedido, baixa o estoque, cria as arestas `COMPROU`, limpa o carrinho e invalida o cache | Mongo · Neo4j · Redis (nesta ordem) |
| **Meus pedidos** | Histórico do cliente e avaliação dos itens com estrelas | Mongo (`pedidos`) · Neo4j (`AVALIOU`) |
| **Bastidores** | Saúde dos bancos, chaves do Redis com TTL, contagens e documentos do Mongo, estatísticas do grafo, alteração de preço (demonstra invalidação de cache) e log de todas as operações da sessão | os três |

## Testes

```bash
pip install -r requirements-dev.txt
pytest                     # 54 testes unitários: não precisam de Docker e não tocam nos bancos
pytest -m integration      # fluxo completo contra os containers (pulado se não estiverem no ar)
```

> **Atenção:** `pytest -m integration` **recarrega os três bancos** (`seed --reset`): apaga carrinhos, sessões e pedidos
> feitos na interface. Não rode durante a apresentação.

## Estrutura do repositório

```
app.py                      ponto de entrada do Streamlit (navegação, sidebar, tratamento de erros de conexão)
src/config.py               Settings lidas do .env (nomes conforme o enunciado: NEO4J_URI, NEO4J_USERNAME, ...)
src/db/                     conexões: mongo.py (índices), redis_client.py, neo4j_client.py (constraints)
src/services/               regras de negócio, independentes do Streamlit
  auth.py                   cadastro/login, hash de senha, token de sessão no Redis
  cart.py                   carrinho (Hash no Redis)
  catalog.py                busca e leitura com cache-aside, ranking e invalidação
  recommendations.py        consultas Cypher de recomendação
  orders.py                 histórico de pedidos e avaliações
  checkout.py               orquestra os três bancos ao finalizar a compra
src/observability.py        OpLog: registro das operações de cada banco, exibido nos Bastidores
src/ui/                     telas Streamlit (state.py, components.py, telas/*.py)
scripts/seed.py             carga inicial; scripts/data/produtos.json tem o catálogo
tests/                      unitários (sem Docker) e tests/integration (com Docker)
docker-compose.yml          mongo + redis + neo4j (+ app com --profile app)
```

## Usando o Neo4j AuraDB do professor

Basta trocar no `.env`:

```
NEO4J_URI=neo4j+s://<id>.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=<senha>
NEO4J_DATABASE=neo4j
```

e rodar `python scripts/seed.py --reset` de novo. O código é o mesmo.

## Ferramentas úteis durante a demonstração

- Neo4j Browser: http://localhost:7474 (`neo4j` / `techstore123`), por exemplo `MATCH (c:Cliente)-[r:COMPROU]->(p) RETURN c, r, p LIMIT 50`
- Redis: `docker exec -it techstore-redis redis-cli` → `KEYS carrinho:*`, `HGETALL carrinho:<id>`, `TTL sessao:<token>`, `ZREVRANGE ranking:produtos_acessados 0 9 WITHSCORES`
- MongoDB: `docker exec -it techstore-mongo mongosh techstore` → `db.pedidos.find().sort({criado_em: -1}).limit(3)`

## Equipe

| Nome | Matrícula | Responsabilidade principal |
|---|---|---|
| _preencher_ | | |
