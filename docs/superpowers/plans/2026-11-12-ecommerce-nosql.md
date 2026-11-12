# TechStore – E-commerce Poliglota (MongoDB + Redis + Neo4j) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar o Estudo de Caso 01 do enunciado: um e-commerce de eletrônicos e games em Python + Streamlit que usa MongoDB (catálogo, clientes e pedidos), Redis (sessão, carrinho, cache, ranking) e Neo4j (grafo de compras/avaliações e recomendação), com Docker Compose, scripts de carga e documentação para a defesa oral.

**Architecture:** Streamlit é o orquestrador. Uma camada `src/db` cria as conexões; uma camada `src/services` contém a lógica de negócio, independente de Streamlit, uma classe por responsabilidade (auth, carrinho, catálogo, recomendação, pedidos, checkout). Cada serviço recebe um `OpLog` opcional e registra nele o que fez em cada banco, e a tela "Bastidores" exibe esse log para a defesa oral. Os três bancos sobem localmente via Docker Compose; o app roda local (venv) ou via perfil `app` do compose.

**Tech Stack:** Python 3.11, Streamlit ≥1.40 (`st.navigation`), pymongo 4, redis-py 5, neo4j-driver 5, python-dotenv, Faker (pt_BR), pyvis (grafo), pytest + fakeredis + mongomock (testes unitários), Docker Compose (mongo:7, redis:7-alpine, neo4j:5).

**Spec:** `docs/enunciado.md` (transcrição do .docx do professor, Estudo de Caso 01 e seção 4) + decisões registradas neste plano. O documento de arquitetura para a defesa (`docs/arquitetura.md`) é produzido na Task 10.

## Global Constraints

- Texto da interface, nomes de coleções, chaves e nós em **português** (ex.: `produtos`, `carrinho:{cliente_id}`, `:Cliente`).
- Variáveis de ambiente seguem o enunciado: `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`; mais `MONGO_URI`, `MONGO_DB`, `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `SESSION_TTL_SECONDS`, `CACHE_TTL_SECONDS`, `CART_TTL_SECONDS`.
- Nenhuma credencial real no repositório: `.env` está no `.gitignore`; `.env.example` traz os valores do Docker local (`neo4j/techstore123`).
- `src/services` e `src/db` **não importam streamlit**. Só `app.py` e `src/ui/` conhecem Streamlit.
- Identificadores: `produtos._id` = SKU (string, ex. `NB-001`); `clientes._id` = `cli_<8 hex>`; `pedidos._id` = `ped_<12 hex>`. Os mesmos valores são usados em Redis e Neo4j (`Cliente.id`, `Produto.sku`).
- Chaves Redis: `sessao:{token}`, `carrinho:{cliente_id}`, `cache:produto:{sku}`, `cache:busca:{sha1}`, `ranking:produtos_acessados`.
- TTLs padrão: sessão 1800 s, cache de produto 300 s, cache de busca 60 s, carrinho 604800 s (7 dias).
- Senhas: PBKDF2-HMAC-SHA256, 200 000 iterações, salt de 16 bytes, via `hashlib` (sem dependência extra).
- Testes unitários rodam **sem** Docker (fakeredis + mongomock + stub de Neo4j). Testes de integração ficam em `tests/integration/` e são pulados quando os bancos não respondem.
- Comandos de execução: `.venv/Scripts/python -m pytest` (Windows) para testes; `streamlit run app.py` para o app.

## Review Focus

1. Login com e-mail inexistente ou senha errada → mensagem amigável, `login` devolve `None`, nenhuma exceção (Task 3).
2. Token expirado/removido do Redis → `cliente_do_token` devolve `None` e o app volta para a tela de login sem erro (Task 3 e Task 9).
3. Checkout com estoque insuficiente → `EstoqueInsuficienteError` nomeando o produto; nada é gravado em Mongo, Neo4j ou Redis (Task 7).
4. SKU no carrinho que não existe mais no catálogo → ignorado no resumo e removido do carrinho, sem quebrar a tela (Task 7).
5. Busca com caracteres especiais de regex (`C++`, `(`, `*`) → resultado vazio ou correto, nunca `re.error` (Task 5).

---

### Task 1: Infraestrutura (Docker Compose, env, Settings)

**Files:**
- Create: `docker-compose.yml`, `Dockerfile`, `.env.example`, `.env`, `.env.docker`, `.gitignore`, `.streamlit/config.toml`
- Create: `src/__init__.py`, `src/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `Settings` (dataclass frozen) com campos `mongo_uri, mongo_db, redis_host, redis_port, redis_db, neo4j_uri, neo4j_user, neo4j_password, neo4j_database, session_ttl, cache_ttl, cart_ttl` e `Settings.from_env(dotenv_path: str | None = ".env") -> Settings`.

- [ ] **Step 1: Write the failing test**

```python
def test_from_env_reads_variables(monkeypatch):
    monkeypatch.setenv("MONGO_URI", "mongodb://x:1")
    monkeypatch.setenv("REDIS_PORT", "6390")
    monkeypatch.setenv("NEO4J_USERNAME", "u")
    s = Settings.from_env(dotenv_path=None)
    assert s.mongo_uri == "mongodb://x:1" and s.redis_port == 6390 and s.neo4j_user == "u"

def test_defaults_match_docker_compose():
    s = Settings()
    assert s.mongo_db == "techstore" and s.neo4j_password == "techstore123" and s.session_ttl == 1800
```

- [ ] **Step 2: Run** `pytest tests/test_config.py -v` → FAIL (`ModuleNotFoundError: src.config`)
- [ ] **Step 3: Implement `src/config.py`** – `from_env` chama `load_dotenv(dotenv_path)` quando não `None`, depois lê `os.environ` com os defaults do dataclass; ints convertidos.
- [ ] **Step 4: Write `docker-compose.yml`** – serviços `mongo` (mongo:7, 27017, volume `mongo_data`, healthcheck `mongosh --eval "db.adminCommand('ping')"`), `redis` (redis:7-alpine, 6379, `--appendonly yes`, volume `redis_data`), `neo4j` (neo4j:5, 7474/7687, `NEO4J_AUTH=neo4j/techstore123`, volume `neo4j_data`), `app` (build `.`, 8501, `env_file: .env.docker`, `profiles: ["app"]`, depends_on os três).
- [ ] **Step 5: Write `Dockerfile`** – `python:3.11-slim`, copia `requirements.txt`, `pip install`, copia o projeto, `CMD streamlit run app.py --server.address=0.0.0.0`.
- [ ] **Step 6: Write `.env.example` (= `.env`) com hosts `localhost` e `.env.docker` com hosts `mongo`, `redis`, `bolt://neo4j:7687`.** `.gitignore`: `.venv/`, `.env`, `__pycache__/`, `.pytest_cache/`, `*.pyc`.
- [ ] **Step 7: Run** `pytest tests/test_config.py -v` → PASS; `docker compose config` → sem erro.

### Task 2: Clientes de banco e OpLog

**Files:**
- Create: `src/observability.py`, `src/db/__init__.py`, `src/db/mongo.py`, `src/db/redis_client.py`, `src/db/neo4j_client.py`
- Test: `tests/test_observability.py`, `tests/test_mongo_indexes.py`, `tests/fakes.py`

**Interfaces:**
- Produces: `Operacao(banco: str, operacao: str, detalhe: str, quando: datetime)`; `OpLog(limite: int = 50)` com `registrar(banco, operacao, detalhe) -> None`, `recentes(n: int = 20) -> list[Operacao]` (mais recente primeiro), `limpar()`.
- Produces: `get_mongo_db(settings) -> Database`; `ensure_indexes(db) -> None` (produtos: `categoria`, `marca`, `preco`; clientes: `email` unique; pedidos: `(cliente.id, criado_em desc)`); `get_redis(settings) -> redis.Redis` com `decode_responses=True`; `Neo4jService(uri, user, password, database="neo4j", oplog=None)` com `run(query: str, **params) -> list[dict]`, `ensure_constraints()`, `verificar_conexao() -> bool`, `close()`.
- Produces (tests): `tests/fakes.py::FakeNeo4j` com `run(query, **params)` que grava `(query, params)` em `self.chamadas` e devolve `self.respostas.pop(0)` se houver, senão `[]`.

- [ ] **Step 1: Tests** – `test_oplog_keeps_newest_first_and_respects_limit` (limite 3, registra 4, `recentes()` tem 3 e o primeiro é o último registrado); `test_ensure_indexes_creates_unique_email` com `mongomock.MongoClient().techstore` → `db.clientes.index_information()` contém índice em `email` com `unique: True`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** `Neo4jService.run` usa `self.driver.session(database=...)` e `[r.data() for r in result]`; registra no oplog `("Neo4j", "CYPHER", query.strip()[:300])`. `ensure_constraints` cria `CREATE CONSTRAINT ... IF NOT EXISTS` para `Cliente.id`, `Produto.sku`, `Categoria.nome`.
- [ ] **Step 4: Run** `pytest tests/test_observability.py tests/test_mongo_indexes.py -v` → PASS.

### Task 3: AuthService (Mongo + Redis)

**Files:**
- Create: `src/services/__init__.py`, `src/services/auth.py`
- Test: `tests/test_auth.py`

**Interfaces:**
- Produces: `hash_senha(senha: str, salt: bytes | None = None) -> tuple[str, str]` (hash_hex, salt_hex); `verificar_senha(senha, hash_hex, salt_hex) -> bool`; `EmailJaCadastradoError`; `AuthService(db, redis, session_ttl: int, oplog=None)` com `registrar(nome, email, senha) -> dict` (cliente sem `senha_hash`), `login(email, senha) -> str | None`, `logout(token) -> None`, `cliente_do_token(token) -> dict | None` (renova TTL), `novo_token() -> str` (`secrets.token_urlsafe(32)`).

- [ ] **Step 1: Tests** (mongomock + `fakeredis.FakeRedis(decode_responses=True)`):
  - `test_registrar_e_login_devolve_token` → token não vazio; `redis.get(f"sessao:{token}") == cliente["_id"]`; `redis.ttl(...)` entre 1700 e 1800.
  - `test_login_senha_errada_e_email_inexistente_devolvem_none`.
  - `test_registrar_email_duplicado_lanca_erro` (case-insensitive: e-mail normalizado para minúsculas).
  - `test_cliente_do_token_expirado_devolve_none` (token que não está no Redis).
  - `test_logout_remove_token`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** Cliente doc: `{_id: "cli_"+uuid4().hex[:8], nome, email, senha_hash, salt, criado_em}`. **Step 4: Run** → PASS.

### Task 4: CartService (Redis Hash)

**Files:**
- Create: `src/services/cart.py`
- Test: `tests/test_cart.py`

**Interfaces:**
- Produces: `CartService(redis, ttl: int, oplog=None)` com `chave(cliente_id) -> str` (`carrinho:{cliente_id}`), `adicionar(cliente_id, sku, quantidade=1) -> int` (quantidade resultante), `definir_quantidade(cliente_id, sku, quantidade) -> None` (≤0 remove), `remover(cliente_id, sku)`, `limpar(cliente_id)`, `itens(cliente_id) -> dict[str, int]`, `total_itens(cliente_id) -> int`.

- [ ] **Step 1: Tests** – `test_adicionar_acumula_quantidade` (2 + 3 → 5), `test_definir_zero_remove_item`, `test_limpar_apaga_chave`, `test_carrinho_tem_ttl` (`ttl(chave) > 0` após adicionar), `test_itens_devolve_ints`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** com `HINCRBY`, `HSET`, `HDEL`, `HGETALL`, `EXPIRE` após cada escrita. **Step 4: Run** → PASS.

### Task 5: CatalogService (Mongo + cache/ranking Redis)

**Files:**
- Create: `src/services/catalog.py`
- Test: `tests/test_catalog.py`

**Interfaces:**
- Produces: `CatalogService(db, redis, cache_ttl: int, oplog=None)` com `buscar(texto="", categoria=None, marca=None, ordem="relevancia", limite=60) -> list[dict]`, `obter_produto(sku, registrar_acesso=True) -> tuple[dict | None, str]` (origem `"cache"` ou `"mongo"`), `obter_varios(skus) -> dict[str, dict]`, `categorias() -> list[str]`, `marcas() -> list[str]`, `mais_acessados(n=10) -> list[tuple[str, float]]`, `atualizar_preco(sku, novo_preco: float) -> None`, `invalidar_cache(sku) -> None`.
- `ordem` ∈ {`"relevancia"`, `"menor_preco"`, `"maior_preco"`, `"nome"`}.

- [ ] **Step 1: Tests** (mongomock + fakeredis; fixture insere 3 produtos):
  - `test_obter_produto_segunda_chamada_vem_do_cache` → origens `("mongo", "cache")` e `redis.exists("cache:produto:NB-001")`.
  - `test_obter_produto_incrementa_ranking` → `redis.zscore("ranking:produtos_acessados", "NB-001") == 2.0` após 2 chamadas.
  - `test_atualizar_preco_invalida_cache` → após `atualizar_preco`, chave de cache não existe e `obter_produto` devolve o novo preço com origem `"mongo"`.
  - `test_buscar_por_texto_categoria_e_ordem` → `buscar("mouse")` encontra por nome e por tag; `buscar(categoria="Notebooks", ordem="menor_preco")` vem ordenado.
  - `test_buscar_com_caracteres_de_regex_nao_quebra` → `buscar("C++ (")` devolve lista (vazia) sem exceção.
  - `test_buscar_usa_cache_de_consulta` → segunda chamada igual lê `cache:busca:*` (verificar que a chave existe após a primeira).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** Busca: `re.escape(texto)` em `$regex` case-insensitive sobre `nome`, `marca`, `descricao`, `tags` via `$or`; filtros `categoria`/`marca` por igualdade; ordenação via `sort`. Documentos serializados em JSON no Redis (`default=str`). **Step 4: Run** → PASS.

### Task 6: RecommendationService e OrderService (Neo4j)

**Files:**
- Create: `src/services/recommendations.py`, `src/services/orders.py`
- Test: `tests/test_recommendations.py`, `tests/test_orders.py`

**Interfaces:**
- Produces: `RecommendationService(neo4j)` com `quem_comprou_tambem_comprou(cliente_id, limite=8) -> list[dict]` (`sku, nome, preco, forca`), `perfil_similar_por_avaliacao(cliente_id, limite=8) -> list[dict]` (`sku, nome, preco, origem, nota`), `relacionados_ao_produto(sku, limite=6) -> list[dict]`, `populares_na_categoria(categoria, limite=6) -> list[dict]` (`sku, nome, compras`), `caminho_recomendacao(cliente_id, sku) -> list[dict]` (nós do `shortestPath`, cada um `{rotulo, nome}`), `subgrafo_cliente(cliente_id, limite=40) -> tuple[list[dict], list[dict]]` (nós `{id, rotulo, nome}`, arestas `{origem, destino, tipo}`).
- Produces: `OrderService(db, neo4j, oplog=None)` com `pedidos_do_cliente(cliente_id) -> list[dict]` (mais recente primeiro), `avaliar(cliente_id, sku, nota: int) -> None` (1..5, `MERGE` em `[:AVALIOU]` e `SET r.nota, r.data`), `nota_dada(cliente_id, sku) -> int | None`.
- Cypher de referência (adaptado do enunciado, seção 3.2) para `perfil_similar_por_avaliacao`:

```cypher
MATCH (c1:Cliente {id: $cliente_id})-[a1:AVALIOU]->(p:Produto)<-[a2:AVALIOU]-(c2:Cliente)
WHERE c1 <> c2 AND abs(a1.nota - a2.nota) < 1
MATCH (c2)-[a3:AVALIOU]->(rec:Produto)
WHERE a3.nota >= 4 AND NOT (c1)-[:COMPROU]->(rec)
RETURN DISTINCT rec.sku AS sku, rec.nome AS nome, rec.preco AS preco, c2.nome AS origem, a3.nota AS nota
LIMIT $limite
```

- [ ] **Step 1: Tests** com `FakeNeo4j`: `test_quem_comprou_passa_parametros_e_devolve_linhas` (respostas pré-carregadas; `chamadas[0][1] == {"cliente_id": "cli_1", "limite": 8}`; query contém `COMPROU` e `NOT (c)-[:COMPROU]->(rec)`); `test_avaliar_rejeita_nota_fora_de_1_a_5` (`ValueError`); `test_avaliar_envia_merge_avaliou`; `test_pedidos_do_cliente_ordena_por_data_desc` (mongomock).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.

### Task 7: CheckoutService (orquestra os três bancos)

**Files:**
- Create: `src/services/checkout.py`
- Test: `tests/test_checkout.py`

**Interfaces:**
- Consumes: `CartService`, `CatalogService`, `Neo4jService.run`.
- Produces: `CarrinhoVazioError`, `EstoqueInsuficienteError(sku, nome, disponivel)`; `CheckoutService(db, redis, neo4j, cart, catalog, oplog=None)` com `resumo(cliente_id) -> dict` (`itens: [{sku, nome, preco_unitario, quantidade, subtotal, estoque}], total: float, quantidade_itens: int`) e `finalizar(cliente: dict, forma_pagamento: str, endereco: dict) -> dict` (pedido gravado).
- Pedido: `{_id: "ped_"+uuid4().hex[:12], cliente: {id, nome, email}, itens: [...], total, forma_pagamento, endereco_entrega, status: "confirmado", criado_em}`.
- Ordem em `finalizar`: valida carrinho e estoque → `insert_one(pedido)` → `update_one({_id: sku}, {$inc: {estoque: -q}})` por item → Cypher `MERGE (c:Cliente {id}) SET c.nome` + `UNWIND $itens ... MATCH (p:Produto {sku}) MERGE (c)-[r:COMPROU {pedido_id}]->(p) SET r.data, r.quantidade` → `cart.limpar` → `catalog.invalidar_cache(sku)` por item.

- [ ] **Step 1: Tests** (mongomock + fakeredis + FakeNeo4j): `test_finalizar_grava_pedido_decrementa_estoque_cria_grafo_e_limpa_carrinho`; `test_finalizar_carrinho_vazio_lanca_erro`; `test_estoque_insuficiente_nao_grava_nada` (`pedidos.count_documents({}) == 0`, carrinho intacto, `FakeNeo4j.chamadas == []`); `test_sku_inexistente_no_carrinho_e_ignorado_e_removido`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.

### Task 8: Dados de exemplo e scripts de carga

**Files:**
- Create: `scripts/__init__.py`, `scripts/data/produtos.json`, `scripts/seed.py`
- Test: `tests/test_seed_data.py`, `tests/integration/test_smoke.py`, `tests/integration/conftest.py`

**Interfaces:**
- `produtos.json`: lista de ~42 produtos em 7 categorias (`Notebooks`, `Smartphones`, `Periféricos`, `Consoles`, `Jogos`, `Áudio`, `Acessórios`), cada um `{sku, nome, marca, categoria, preco, estoque, descricao, tags, imagem, especificacoes}`; `especificacoes` tem campos diferentes por categoria (ex. notebook: `processador, memoria_ram_gb, armazenamento_gb, tela_polegadas, sistema_operacional`; jogo: `plataforma, genero, classificacao, modo_online`).
- `scripts/seed.py` (executável: `python scripts/seed.py [--reset]`): `carregar_produtos() -> list[dict]`; `gerar_clientes(n=30, seed=42) -> list[dict]` (Faker pt_BR, senha `123456`, inclui `ana@techstore.com`, cada cliente com `persona` ∈ {`gamer`, `profissional`, `mobile`}); `gerar_pedidos(clientes, produtos, n=160, seed=42) -> list[dict]` (80 % dos itens vêm das categorias da persona); `gerar_avaliacoes(pedidos, seed=42) -> list[dict]` (`cliente_id, sku, nota, data`; ~70 % dos itens comprados, notas 3-5 com viés da persona); `seed_mongo(db, produtos, clientes, pedidos)`; `seed_neo4j(svc, produtos, clientes, pedidos, avaliacoes)`; `seed_redis(r, produtos, seed=42)` (apaga `cache:*`, `carrinho:*`, `sessao:*` e popula `ranking:produtos_acessados` com acessos aleatórios); `main(argv)`.
- Personas → categorias: `gamer: Consoles, Jogos, Periféricos`; `profissional: Notebooks, Periféricos, Áudio`; `mobile: Smartphones, Áudio, Acessórios`.

- [ ] **Step 1: Tests** – `test_produtos_json_tem_skus_unicos_e_campos_obrigatorios`; `test_gerar_clientes_inclui_demo_e_e_deterministico` (duas chamadas com seed 42 iguais; `ana@techstore.com` presente, persona `gamer`); `test_gerar_pedidos_respeita_persona` (≥70 % dos itens em categorias da persona); `test_seed_mongo_em_mongomock_popula_tres_colecoes`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Write `produtos.json` e `seed.py`.** **Step 4: Run** → PASS.
- [ ] **Step 5: Integration** – `tests/integration/conftest.py` pula tudo (`pytest.skip(allow_module_level=True)`) se Mongo, Redis ou Neo4j não responderem em 2 s. `test_smoke.py`: roda `main(["--reset"])`, depois `RecommendationService.quem_comprou_tambem_comprou(id da Ana)` devolve ≥1 item e `CatalogService.buscar("PlayStation")` devolve ≥1.
- [ ] **Step 6: Run** `docker compose up -d` e `python scripts/seed.py --reset` → saída com contagens; `pytest tests/integration -v` → PASS.

### Task 9: Interface Streamlit

**Files:**
- Create: `app.py`, `src/ui/__init__.py`, `src/ui/state.py`, `src/ui/components.py`, `src/ui/pages/__init__.py`, `src/ui/pages/login.py`, `catalogo.py`, `carrinho.py`, `recomendacoes.py`, `checkout.py`, `pedidos.py`, `bastidores.py`

**Interfaces:**
- `src/ui/state.py`: `@st.cache_resource def conexoes() -> Conexoes` (`settings, db, redis, neo4j`); `def servicos() -> Servicos` (dataclass `auth, catalog, cart, recs, orders, checkout, oplog`), com `oplog` guardado em `st.session_state["oplog"]`; `cliente_logado() -> dict | None` (lê `st.session_state["token"]` e consulta `auth.cliente_do_token`; limpa o token se `None`); `verificar_conexoes() -> dict[str, tuple[bool, str]]`.
- `app.py`: carrega `servicos()`; se não logado → `st.navigation([Page(login)])`; se logado → páginas `Catálogo`, `Carrinho`, `Recomendações`, `Checkout`, `Meus Pedidos`, `Bastidores`; sidebar mostra nome do cliente, badge com `cart.total_itens`, botão Sair, e os 5 últimos registros do `oplog`.
- Páginas (comportamento mínimo):
  - **login**: abas "Entrar" e "Criar conta"; dica com o usuário de demonstração `ana@techstore.com / 123456`.
  - **catalogo**: busca por texto, filtros categoria/marca, ordenação; grid de cards (`st.columns(3)`) com imagem, preço, estoque, botão "Adicionar ao carrinho" e "Detalhes"; detalhes em `st.dialog` mostram `especificacoes` como tabela e a origem (cache/Mongo) e "quem comprou também comprou" (Neo4j); barra lateral direita com "Mais acessados" (ZSET).
  - **carrinho**: tabela com `number_input` por item, botão remover, botão limpar, total; cada alteração reflete no Redis na mesma execução.
  - **recomendacoes**: três blocos (compras cruzadas, perfil similar por avaliação, populares na categoria escolhida) + grafo pyvis de `subgrafo_cliente` em `components.html`; ao clicar em um item, mostra `caminho_recomendacao`.
  - **checkout**: resumo, formulário (endereço com defaults, forma de pagamento), botão "Confirmar pedido" → `finalizar`; sucesso mostra o JSON do pedido gravado e o aviso de carrinho limpo.
  - **pedidos**: lista de pedidos do Mongo com expanders; `st.feedback("stars")`/`selectbox` para avaliar cada item → `orders.avaliar`.
  - **bastidores**: saúde dos três bancos; chaves Redis da sessão atual (`sessao:*` do token, carrinho, `cache:*` com TTL via `SCAN`), últimos 5 pedidos do Mongo, contagens de nós/relacionamentos no Neo4j, log completo do `oplog`; seção "Administração" com `atualizar_preco` para demonstrar invalidação de cache.
- `components.py`: `card_produto(produto, on_add)`, `badge_origem(origem)`, `tabela_especificacoes(especificacoes)`, `grafo_html(nos, arestas) -> str` (pyvis, altura 500).

- [ ] **Step 1: Implement `state.py` e `app.py`** com a página de login; rodar `streamlit run app.py` e confirmar login/logout com a Ana.
- [ ] **Step 2: Implement catálogo + carrinho**; verificar no browser: adicionar item, badge da sidebar atualiza, `redis-cli HGETALL carrinho:<id>` (via bastidores) mostra o item.
- [ ] **Step 3: Implement recomendações + checkout + pedidos**; verificar fluxo completo: checkout zera carrinho, pedido aparece em "Meus Pedidos", recomendações mudam.
- [ ] **Step 4: Implement bastidores**; verificar invalidação de cache (alterar preço → próxima leitura vem do Mongo).
- [ ] **Step 5: Run** `pytest` (todos) → PASS; app sem exceções no console com os três bancos; app com Redis parado mostra erro amigável na tela de login.

### Task 10: Documentação e repositório

**Files:**
- Create: `README.md`, `docs/arquitetura.md`, `docs/roteiro_defesa.md`

- [ ] **Step 1: `README.md`** – o que é, pré-requisitos, `docker compose up -d`, criar venv e `pip install -r requirements.txt`, `python scripts/seed.py --reset`, `streamlit run app.py`, usuário demo, alternativa `docker compose --profile app up`, como rodar os testes, estrutura de pastas, mapeamento de cada tela para os bancos, equipe (placeholders).
- [ ] **Step 2: `docs/arquitetura.md`** – diagrama (ASCII, seção 4 do enunciado), modelagem: documentos JSON de exemplo (produto, cliente, pedido), índices; tabela de chaves Redis (chave, tipo, TTL, por quê); modelo do grafo (nós, relacionamentos, propriedades, constraints) e cada Cypher com explicação; justificativa "por que esse dado foi para esse banco".
- [ ] **Step 3: `docs/roteiro_defesa.md`** – roteiro de 10 min: introdução, arquitetura, demo passo a passo (com o que observar em Bastidores), perguntas prováveis e respostas curtas (TTL, cache invalidation, Hash vs String, index-free adjacency, por que não SQL).
- [ ] **Step 4: `git init`**, conferir `git status` sem `.env`/`.venv`.
