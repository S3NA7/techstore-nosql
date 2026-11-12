# Arquitetura e Modelagem de Dados — TechStore

Este documento responde às três perguntas da defesa oral: **por que determinado dado foi para o MongoDB**,
**por que determinado dado ficou no Redis** e **como o grafo foi modelado no Neo4j**.

## 1. Visão geral

O Streamlit é o orquestrador: cada tela chama serviços Python (`src/services`) que conversam diretamente
com os três bancos por meio dos drivers oficiais (`pymongo`, `redis-py`, `neo4j`). Não há servidor
intermediário. Os serviços não conhecem o Streamlit, o que permite testá-los sem interface.

| Dado | Banco | Por quê |
|---|---|---|
| Produto (nome, preço, estoque, `especificacoes` que mudam por categoria) | MongoDB | Esquema flexível: um notebook tem `memoria_ram_gb` e `placa_video`; um jogo tem `plataforma` e `classificacao_etaria`. Em SQL seriam dezenas de colunas nulas ou tabelas EAV. |
| Cliente (nome, e-mail, hash da senha, endereço) | MongoDB | Documento durável com subdocumento de endereço; índice único em `email`. |
| Pedido finalizado (snapshot dos itens, total, endereço, pagamento) | MongoDB | Histórico imutável. Os itens são **copiados** para dentro do pedido (preço no momento da compra), então o pedido não muda se o produto mudar. |
| Token de login | Redis | Volátil, precisa **expirar sozinho** (TTL 30 min) e ser lido a cada requisição em microssegundos. |
| Carrinho ativo | Redis | Estado de sessão que muda a cada clique; `HINCRBY` é atômico; TTL de 7 dias descarta carrinhos abandonados. |
| Cache de produto e de busca | Redis | Leituras repetidas do catálogo sem bater no Mongo; TTL curto + invalidação explícita quando o produto muda. |
| Ranking de produtos mais acessados | Redis | Sorted Set: `ZINCRBY` a cada visualização, `ZREVRANGE` para o top N. Contador em tempo real sem agregação pesada. |
| Quem comprou / avaliou o quê | Neo4j | A pergunta é sobre **conexões** ("quem comprou o que você comprou também comprou…"). Travessias de 3 saltos são naturais em grafo e caras em junções. |

## 2. MongoDB (banco `techstore`)

### 2.1 Coleção `produtos` — `_id` = SKU

```json
{
  "_id": "NB-001",
  "sku": "NB-001",
  "nome": "Notebook Acer Nitro 5",
  "marca": "Acer",
  "categoria": "Notebooks",
  "preco": 5499.0,
  "estoque": 12,
  "descricao": "Notebook gamer com RTX 3050 e tela de 144 Hz para jogos em Full HD.",
  "tags": ["gamer", "notebook", "rtx", "144hz"],
  "imagem": "https://placehold.co/400x300?text=Acer+Nitro+5",
  "especificacoes": {
    "processador": "Intel Core i5-12450H",
    "memoria_ram_gb": 16,
    "armazenamento_gb": 512,
    "placa_video": "NVIDIA GeForce RTX 3050 4GB",
    "tela_polegadas": 15.6,
    "taxa_atualizacao_hz": 144
  },
  "criado_em": "2026-11-12T16:00:00"
}
```

Um jogo na mesma coleção tem `especificacoes` completamente diferentes:

```json
{ "_id": "JG-001", "nome": "God of War Ragnarök", "categoria": "Jogos",
  "especificacoes": { "plataforma": "PS5", "genero": "Ação / Aventura", "classificacao_etaria": 18,
                      "modo_online": false, "midia": "física", "dublagem_pt_br": true } }
```

Decisões:

- **SKU como `_id`** (chave natural): evita um índice extra, e o mesmo valor é usado como `sku` no Neo4j e nas chaves do Redis.
- **Busca** por `$regex` (case-insensitive, texto escapado com `re.escape`) em `nome`, `marca`, `descricao` e `tags` via `$or`; filtros de igualdade em `categoria` e `marca`; ordenação com `sort`.
- Índices: `categoria`, `marca`, `preco`.

### 2.2 Coleção `clientes`

```json
{ "_id": "cli_46685257", "nome": "Ana Souza", "email": "ana@techstore.com",
  "senha_hash": "<pbkdf2-sha256 hex>", "salt": "<16 bytes hex>", "persona": "gamer",
  "endereco": { "rua": "Alameda Sousa, 43", "cidade": "Sousa", "uf": "AM", "cep": "96001338" },
  "criado_em": "2026-03-10T00:00:00" }
```

- Índice **único** em `email` (e-mail sempre normalizado para minúsculas).
- Senha com **PBKDF2-HMAC-SHA256, 200 000 iterações e salt por usuário**; nunca em texto puro.

### 2.3 Coleção `pedidos`

```json
{ "_id": "ped_5e73d5635e0a",
  "cliente": { "id": "cli_46685257", "nome": "Ana Souza", "email": "ana@techstore.com" },
  "itens": [ { "sku": "PF-001", "nome": "Mouse Logitech G Pro X Superlight",
               "preco_unitario": 699.0, "quantidade": 2, "subtotal": 1398.0 } ],
  "total": 1398.0, "forma_pagamento": "pix",
  "endereco_entrega": { "rua": "Alameda Sousa, 43", "cidade": "Sousa", "uf": "AM", "cep": "96001338" },
  "status": "confirmado", "criado_em": "2026-11-12T16:18:54" }
```

- **Desnormalização proposital**: nome e preço do item e dados do cliente são copiados para o pedido.
- Índice composto `(cliente.id, criado_em desc)` para "meus pedidos" ordenado por data.
- O estoque é baixado com `update_one({_id: sku}, {$inc: {estoque: -quantidade}})` (operação atômica no documento).

## 3. Redis

| Chave | Tipo | Conteúdo | TTL | Operações | Por quê |
|---|---|---|---|---|---|
| `sessao:{token}` | STRING | `cliente_id` | 1800 s, renovado a cada acesso (`EXPIRE`) | `SET EX`, `GET`, `EXPIRE`, `DEL` | Sessão deslizante: inativo por 30 min = deslogado. O token é `secrets.token_urlsafe(32)`. |
| `carrinho:{cliente_id}` | HASH | `sku -> quantidade` | 7 dias, renovado ao adicionar ou alterar quantidade | `HINCRBY`, `HSET`, `HDEL`, `HGETALL`, `DEL` | Hash permite alterar um item sem reescrever o carrinho inteiro; `HINCRBY` é atômico. |
| `cache:produto:{sku}` | STRING (JSON) | documento do produto | 300 s | `GET`, `SET EX`, `DEL` | Cache-aside: lê do Redis; se não existe (MISS) lê do Mongo e grava. |
| `cache:busca:{sha1(parâmetros)}` | STRING (JSON) | lista de resultados | 60 s | `GET`, `SET EX`, `DEL` | A mesma busca repetida não toca o Mongo. A chave é o hash dos parâmetros (texto, categoria, marca, ordem, limite). |
| `ranking:produtos_acessados` | ZSET | `sku -> nº de acessos` | sem TTL | `ZINCRBY`, `ZREVRANGE WITHSCORES` | Top N em O(log N) por incremento; alimenta a faixa "Mais acessados" e a ordenação por relevância. |

**Invalidação de cache (Cache Invalidation).** Quando um produto muda (alteração de preço nos Bastidores
ou baixa de estoque no checkout), o serviço executa `DEL cache:produto:{sku}` e apaga todas as
`cache:busca:*` (porque resultados de busca contêm preço e estoque). A próxima leitura vem do Mongo
(badge "MongoDB · lido do banco") e repovoa o cache (badge "Redis · cache HIT" na leitura seguinte).
O TTL é a segunda linha de defesa: mesmo sem invalidação explícita, nada fica mais de 5 min desatualizado.

## 4. Neo4j

### 4.1 Modelo

```
(:Cliente {id, nome, persona})
(:Produto {sku, nome, preco, categoria, marca})
(:Categoria {nome})

(:Cliente)-[:COMPROU {pedido_id, data, quantidade}]->(:Produto)
(:Cliente)-[:AVALIOU {nota, data}]->(:Produto)
(:Produto)-[:PERTENCE_A]->(:Categoria)
```

Constraints de unicidade: `Cliente.id`, `Produto.sku`, `Categoria.nome` (também criam índices).

Decisões:

- O grafo guarda **só o que é relação**: ids, nomes e preço (para exibir a recomendação sem consultar o Mongo). Descrição, estoque e especificações ficam no Mongo. Os mesmos ids (`cli_…`, SKU) ligam os três bancos.
- `Produto.preco` no grafo é uma **cópia desnormalizada**: o Mongo é a fonte da verdade e `CatalogService.atualizar_preco` atualiza os dois (`SET p.preco`) e invalida o cache do Redis na mesma operação.
- `COMPROU` carrega `pedido_id` como parte da identidade (`MERGE (c)-[r:COMPROU {pedido_id}]->(p)`): dois pedidos do mesmo produto geram duas arestas, e repetir o checkout do mesmo pedido não duplica.
- `AVALIOU` é única por par cliente-produto (`MERGE` sem propriedades na identidade) e o `SET` atualiza a nota.

### 4.2 Consultas Cypher

**Quem comprou o que você comprou também comprou** (filtragem colaborativa por compras):

```cypher
MATCH (c:Cliente {id: $cliente_id})-[:COMPROU]->(p:Produto)<-[:COMPROU]-(outro:Cliente)
WHERE outro <> c
MATCH (outro)-[:COMPROU]->(rec:Produto)
WHERE NOT (c)-[:COMPROU]->(rec)
RETURN rec.sku AS sku, rec.nome AS nome, rec.preco AS preco, rec.categoria AS categoria,
       count(DISTINCT outro) AS forca
ORDER BY forca DESC, rec.nome
LIMIT $limite
```

`forca` = quantos clientes "parecidos" compraram o produto recomendado. O `NOT (c)-[:COMPROU]->(rec)` evita recomendar o que o cliente já tem.

**Perfil similar por avaliação** (adaptado do exemplo do enunciado, seção 3.2):

```cypher
MATCH (c1:Cliente {id: $cliente_id})-[a1:AVALIOU]->(p:Produto)<-[a2:AVALIOU]-(c2:Cliente)
WHERE c1 <> c2 AND abs(a1.nota - a2.nota) < 1
MATCH (c2)-[a3:AVALIOU]->(rec:Produto)
WHERE a3.nota >= 4 AND NOT (c1)-[:COMPROU]->(rec)
RETURN DISTINCT rec.sku AS sku, rec.nome AS nome, rec.preco AS preco, rec.categoria AS categoria,
       c2.nome AS origem, a3.nota AS nota
ORDER BY nota DESC, nome
LIMIT $limite
```

Dois clientes têm "perfil similar" quando deram notas que diferem em menos de 1 ponto para o mesmo produto.

**Quem comprou este produto também comprou** (tela de detalhes):

```cypher
MATCH (p:Produto {sku: $sku})<-[:COMPROU]-(c:Cliente)-[:COMPROU]->(rec:Produto)
WHERE rec <> p
RETURN rec.sku AS sku, rec.nome AS nome, rec.preco AS preco, rec.categoria AS categoria,
       count(DISTINCT c) AS forca
ORDER BY forca DESC, rec.nome
LIMIT $limite
```

**Populares na categoria**:

```cypher
MATCH (p:Produto)-[:PERTENCE_A]->(:Categoria {nome: $categoria})
OPTIONAL MATCH (p)<-[r:COMPROU]-(:Cliente)
RETURN p.sku AS sku, p.nome AS nome, p.preco AS preco, count(r) AS compras
ORDER BY compras DESC, p.nome
LIMIT $limite
```

**Por que me recomendou isso?** (`shortestPath`):

```cypher
MATCH (c:Cliente {id: $cliente_id}), (p:Produto {sku: $sku})
MATCH caminho = shortestPath((c)-[:COMPROU|AVALIOU*..6]-(p))
RETURN [n IN nodes(caminho) | {rotulo: labels(n)[0], id: coalesce(n.id, n.sku),
                               nome: coalesce(n.nome, n.sku)}] AS nos,
       [r IN relationships(caminho) | type(r)] AS tipos
```

(As consultas acima são exatamente as de `src/services/recommendations.py`; a tela "Recomendações" mostra cada uma no expander "Cypher executado".)

Devolve a cadeia `Ana —COMPROU→ PS5 ←COMPROU— Bruno —COMPROU→ EA FC 25`, mostrada ao clicar em "Por quê?".

**Registrar a compra** (chamado pelo checkout):

```cypher
MERGE (c:Cliente {id: $cliente_id}) ON CREATE SET c.nome = $nome
WITH c
UNWIND $itens AS item
MATCH (p:Produto {sku: item.sku})
MERGE (c)-[r:COMPROU {pedido_id: $pedido_id}]->(p)
SET r.data = datetime($data), r.quantidade = item.quantidade
```

### 4.3 Por que grafo e não junções

No Neo4j cada nó guarda ponteiros físicos para seus relacionamentos (**index-free adjacency**). Partir
de um cliente e chegar aos produtos de clientes parecidos custa proporcional ao tamanho da vizinhança
percorrida, não ao tamanho total do banco. A mesma pergunta em SQL exige três junções
(`compras ⋈ compras ⋈ compras`) cujo custo cresce com o número total de compras.

## 5. Fluxo do checkout (os três bancos na mesma operação)

```
Redis    HGETALL carrinho:{cliente}          -> itens e quantidades
MongoDB  find produtos {_id: {$in: skus}}    -> preço e estoque atuais (sem cache!)
         (valida: carrinho não vazio, estoque suficiente; se falhar, nada é gravado)
MongoDB  insert_one pedidos                  -> documento com snapshot
MongoDB  update_one produtos $inc estoque    -> por item
Neo4j    MERGE Cliente, UNWIND itens, MERGE COMPROU {pedido_id}
Redis    DEL carrinho:{cliente}
Redis    DEL cache:produto:{sku}, DEL cache:busca:*   -> invalidação
```

Não há transação distribuída entre os três bancos, e o sistema **não finge que há**. A ordem foi
escolhida para que uma falha no meio deixe um estado explicável:

- O pedido (fonte da verdade) e a baixa de estoque são gravados primeiro, no Mongo.
- Se o Neo4j falhar logo depois, o pedido existe, o estoque já baixou, mas o grafo não tem a aresta e o
  carrinho continua cheio. A tela mostra o erro. Se o cliente clicar em "Confirmar" de novo, a aplicação
  gera **outro** `pedido_id` e cria um **segundo pedido** (e baixa o estoque de novo): o `MERGE … {pedido_id}`
  protege apenas contra o *reenvio do mesmo evento* (mesmo `pedido_id`), não contra um novo checkout.
- Em produção isso se resolve com o padrão *outbox*: o checkout grava no Mongo o pedido **e** um evento
  "pedido criado"; um processo separado lê os eventos pendentes e aplica no Neo4j e no Redis, repetindo
  até conseguir. Como cada evento carrega o `pedido_id`, o `MERGE` torna a repetição segura. Esse é o
  motivo de a aresta `COMPROU` levar `pedido_id` na identidade.

Outra limitação deliberada, fácil de citar na defesa: a verificação de estoque é "ler, comparar, decrementar".
Dois clientes comprando a última unidade ao mesmo tempo passariam os dois. A correção é uma única
operação atômica por documento no Mongo:
`update_one({"_id": sku, "estoque": {"$gte": qtd}}, {"$inc": {"estoque": -qtd}})` e checar `matched_count`.

## 6. Segurança e configuração

- Credenciais apenas em variáveis de ambiente (`.env`, ignorado pelo git). Nomes conforme o enunciado (`NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`).
- Senhas com PBKDF2-HMAC-SHA256 + salt; comparação em tempo constante (`hmac.compare_digest`).
- Tokens de sessão aleatórios de 256 bits, nunca armazenados no Mongo; só existem no Redis enquanto o TTL durar.
- Busca escapa caracteres especiais de regex (`C++`, `(`, `*`) antes de montar o `$regex`.

## 7. Limitações e evoluções possíveis

- Sem transação entre bancos e sem reserva atômica de estoque (ver seção 5): um *outbox* no Mongo e o `update_one` condicional resolveriam.
- Um F5 no navegador perde o `token` guardado no `st.session_state` (o Streamlit não grava cookies), e o usuário entra de novo; a chave no Redis expira sozinha pelo TTL.
- O ranking do Redis não tem TTL nem janela de tempo; uma evolução seria um Sorted Set por dia (`ranking:2026-11-12`).
- A busca usa `$regex`; para catálogos grandes, um índice de texto do Mongo ou Atlas Search seria mais eficiente.
- Imagens são URLs de placeholder; os cards usam um ícone por categoria para funcionar offline na apresentação.
