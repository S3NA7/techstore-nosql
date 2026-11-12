# Roteiro da Defesa Oral (10 minutos)

## Checklist antes de começar

1. `docker compose up -d` e conferir `docker compose ps` (os três `healthy`).
2. `python scripts/seed.py --reset` (deixa os dados no estado inicial, carrinhos e sessões limpos).
3. `streamlit run app.py` aberto em http://localhost:8501, logado como **ana@techstore.com / 123456**.
4. Em outra aba do navegador: Neo4j Browser em http://localhost:7474 com a consulta
   `MATCH (c:Cliente {id: 'cli_46685257'})-[r]->(p) RETURN c, r, p` pronta (o id da Ana aparece nos Bastidores).
5. Um terminal com `docker exec -it techstore-redis redis-cli` aberto.
6. Cada integrante sabe qual parte explica e qual arquivo abre se perguntarem.
7. **Não rodar `pytest -m integration` durante a apresentação**: ele recarrega os bancos e apaga sessões, carrinhos e pedidos feitos na tela. O `pytest` simples é seguro (não toca nos bancos).

## Estrutura e tempos

| Bloco | Tempo | Quem | Conteúdo |
|---|---|---|---|
| 1. Problema e cenário | 1 min | — | Loja de eletrônicos e games; por que um e-commerce precisa de três bancos diferentes |
| 2. Arquitetura e modelagem | 3 min | — | Tabela "dado → banco → por quê"; documento de produto; chaves do Redis; modelo do grafo |
| 3. Demonstração ao vivo | 4 min | — | Roteiro abaixo, com a tela **Bastidores** mostrando as chamadas |
| 4. Perguntas | 2 min | todos | Respostas curtas (seção 4) |

## 1. Problema (1 min)

- "Um e-commerce tem três tipos de dado com necessidades opostas: o **catálogo** muda de forma e é lido
  muito; o **carrinho e a sessão** mudam a cada clique e devem expirar; a **recomendação** é uma pergunta
  sobre conexões entre pessoas e produtos."
- "Persistência poliglota: cada dado no banco que o atende melhor. MongoDB para documentos, Redis para
  estado em memória, Neo4j para o grafo."

## 2. Arquitetura (3 min) — abrir `docs/arquitetura.md`

- Mostrar a tabela da seção 1 (dado → banco → por quê).
- **MongoDB:** abrir Bastidores → aba MongoDB → "Esquema flexível": um notebook e um jogo lado a lado,
  mesma coleção, `especificacoes` diferentes. Falar do SKU como `_id` e do snapshot de itens no pedido.
- **Redis:** tabela de chaves (sessão com TTL deslizante, carrinho em Hash, cache com TTL + invalidação,
  ranking em Sorted Set).
- **Neo4j:** desenho do modelo `(:Cliente)-[:COMPROU]->(:Produto)-[:PERTENCE_A]->(:Categoria)` e a
  consulta "quem comprou também comprou". Citar index-free adjacency.

## 3. Demonstração (4 min)

| Passo | Ação na tela | O que dizer / mostrar |
|---|---|---|
| 1 | **Catálogo**: buscar "mouse" duas vezes | 1ª vez badge "MongoDB · lido do banco", 2ª vez "Redis · cache HIT". Faixa "Mais acessados" vem do Sorted Set. |
| 2 | Clicar **Detalhes** de um produto | Especificações = documento flexível. "Quem comprou este também comprou" vem do Neo4j. Fechar e abrir de novo: agora é cache HIT. |
| 3 | **Adicionar** ao carrinho 2 produtos; ir ao **Carrinho**; alterar quantidade | Badge da sidebar atualiza; expandir "Como está no Redis agora": `HGETALL carrinho:cli_…` e o TTL. No terminal: `HGETALL carrinho:<id>` mostra o mesmo. |
| 4 | **Recomendações** → aba "Quem comprou, também comprou" → clicar **Por quê?** | Cadeia `Ana —COMPROU→ … ←COMPROU— Outro —COMPROU→ Produto` = `shortestPath`. Expander "Cypher executado". Aba "Meu grafo": vizinhança desenhada. |
| 5 | **Checkout** → Confirmar pedido | Tela de confirmação lista as operações nos três bancos na ordem: Mongo `insert_one` + `$inc estoque`, Neo4j `MERGE COMPROU`, Redis `DEL carrinho` + `DEL cache`. Carrinho zera. |
| 6 | **Meus pedidos** → dar 5 estrelas ao item | Toast "gravada no Neo4j (MERGE [:AVALIOU])". No Neo4j Browser, rodar a consulta pronta: a aresta nova aparece. |
| 7 | **Bastidores** → Administração → alterar preço → "Ler produto" 2× | 1ª leitura MongoDB (cache foi invalidado), 2ª Redis HIT. Aba "Log de operações" mostra tudo que aconteceu na sessão. |

Se faltar tempo, cortar os passos 6 e 7 (o 5 já mostra os três bancos juntos).

## 4. Perguntas prováveis e respostas curtas

**Por que o carrinho está no Redis e não no MongoDB?**
Porque é estado de sessão: muda a cada clique, precisa de resposta em microssegundos e deve expirar sozinho (TTL de 7 dias). `HINCRBY` soma quantidades de forma atômica. Quando vira pedido, aí sim é gravado no Mongo, que é o histórico.

**Por que o pedido está no MongoDB e não no Redis?**
Pedido é histórico durável e precisa de consultas (por cliente, por data). O Redis é memória; se expirar ou reiniciar sem persistência, o pedido some.

**Como funciona o cache e a invalidação?**
Cache-aside: o serviço tenta `GET cache:produto:{sku}`; se não existe, lê do Mongo e faz `SET … EX 300`. Quando o produto muda (preço ou estoque), fazemos `DEL` da chave e das buscas em cache. O TTL garante que nada fica velho por mais de 5 min mesmo se a invalidação falhar.

**O que é sessão deslizante?**
A cada acesso o app faz `EXPIRE sessao:{token} 1800`. Enquanto o usuário usa o sistema, a sessão não cai; 30 min parado, o Redis apaga o token e o app volta para o login.

**Por que Hash e não uma String JSON para o carrinho?**
Com Hash alteramos um item (`HSET`/`HINCRBY`/`HDEL`) sem reler e reescrever o carrinho inteiro, sem condição de corrida entre duas abas.

**Por que `_id` = SKU no Mongo?**
Chave natural única do negócio: evita um índice extra e é o mesmo valor que identifica o produto no Neo4j (`Produto.sku`) e nas chaves do Redis.

**Por que recomendação em grafo e não em SQL?**
"Clientes que compraram o que você comprou também compraram" são 3 saltos: Cliente → Produto ← Cliente → Produto. No Neo4j cada nó aponta direto para suas arestas (index-free adjacency), então o custo depende da vizinhança, não do tamanho do banco. Em SQL seriam três junções na tabela de compras.

**O que o `MERGE` faz diferente do `CREATE`?**
`MERGE` só cria se não existir. Usamos `MERGE (c)-[r:COMPROU {pedido_id}]->(p)`: repetir o checkout do mesmo pedido não duplica a aresta; `MERGE (c)-[r:AVALIOU]->(p)` + `SET r.nota` atualiza a nota em vez de criar outra.

**E se o Neo4j cair no meio do checkout?**
Não existe transação distribuída entre três bancos diferentes, e não fingimos que existe. O pedido e a baixa de estoque já estão no Mongo (fonte da verdade); o grafo fica sem a aresta e o usuário vê o erro. Se ele confirmar de novo, nasce um segundo pedido, porque cada checkout gera um `pedido_id` novo. A solução de produção é o padrão *outbox*: gravar junto com o pedido um evento "pedido criado" e reaplicá-lo no Neo4j/Redis até dar certo; como o evento carrega o `pedido_id`, o `MERGE (c)-[:COMPROU {pedido_id}]->(p)` torna a repetição segura. É por isso que a aresta tem `pedido_id` na identidade.

**E se dois clientes comprarem a última unidade ao mesmo tempo?**
Hoje a checagem é "ler estoque, comparar, decrementar", então os dois passariam. A correção é uma única operação atômica no Mongo: `update_one({_id: sku, estoque: {$gte: qtd}}, {$inc: {estoque: -qtd}})` e verificar `matched_count`; se for 0, o produto acabou. Documentado como limitação conhecida em `docs/arquitetura.md`.

**Por que guardar o token no Redis se o Streamlit já tem `session_state`?**
O `session_state` vive na memória de uma aba e some num F5 ou se o servidor reiniciar. O Redis dá expiração automática (TTL), sessão deslizante, é compartilhado por qualquer processo do app e pode ser inspecionado (`TTL sessao:<token>`), ou seja, é um gerenciador de sessão de verdade, como o enunciado pede.

**Onde está a senha do usuário?**
Só o hash PBKDF2-HMAC-SHA256 (200 000 iterações) com salt por usuário, no Mongo. O token de sessão é aleatório e vive só no Redis.

**Como vocês garantem que a busca com `$regex` não quebra com `C++`?**
`re.escape` no texto antes de montar o filtro; há um teste unitário para isso.

**Como testaram sem os bancos?**
`pytest` roda 54 testes unitários com `fakeredis`, `mongomock` e um stub do Neo4j que grava os Cypher enviados, sem tocar nos bancos. `pytest -m integration` roda o fluxo completo (carga, login, busca com cache, checkout, avaliação, recomendação) contra os containers reais, e por isso recarrega os dados.

**O preço no grafo pode ficar diferente do Mongo?**
O Mongo é a fonte da verdade; o grafo guarda uma cópia do preço para exibir recomendações sem consultar o Mongo. `atualizar_preco` grava nos dois e invalida o cache do Redis na mesma operação (dá para ver nos Bastidores → Administração).

**Por que `127.0.0.1` em vez de `localhost` no `.env`?**
No Windows `localhost` resolve primeiro para IPv6 (`::1`); o Docker Desktop aceita a conexão nessa interface mas não a encaminha para o container, e o Redis/Neo4j ficam em timeout. Com `127.0.0.1` vai direto por IPv4.

## 5. Quem explica o quê (preencher)

| Integrante | Explica | Arquivos que abre se perguntarem |
|---|---|---|
| | MongoDB: documentos, índices, checkout | `src/services/checkout.py`, `src/db/mongo.py` |
| | Redis: sessão, carrinho, cache, ranking | `src/services/auth.py`, `src/services/cart.py`, `src/services/catalog.py` |
| | Neo4j: modelo e Cypher | `src/services/recommendations.py`, `scripts/seed.py` (`seed_neo4j`) |
| | Streamlit e demonstração | `app.py`, `src/ui/telas/*.py` |
