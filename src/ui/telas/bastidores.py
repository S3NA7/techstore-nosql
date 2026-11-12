"""Bastidores: o que está acontecendo em cada banco agora. Pensado para a defesa oral."""
import json

import pandas as pd
import streamlit as st

from src.ui.components import badge_origem, brl
from src.ui.state import servicos, verificar_conexoes


def _saude() -> None:
    status = verificar_conexoes()
    colunas = st.columns([1, 1, 1, 1])
    for col, (nome, (ok, detalhe)) in zip(colunas, status.items()):
        col.metric(nome, "online" if ok else "offline", detalhe, delta_color="normal" if ok else "inverse")
    if colunas[3].button("Atualizar", icon=":material/refresh:", width="stretch"):
        verificar_conexoes.clear()
        st.rerun()


def _aba_redis(s, cliente_id: str, token: str) -> None:
    r = s.redis
    st.subheader("Sessão (STRING com TTL)")
    chave_sessao = f"sessao:{token}"
    st.code(f"GET {chave_sessao[:28]}…   → {r.get(chave_sessao)}\nTTL {chave_sessao[:28]}…   → {r.ttl(chave_sessao)} s "
            f"(renovado a cada acesso: sessão deslizante)", language="text")

    st.subheader("Carrinho (HASH com TTL)")
    chave_carrinho = s.cart.chave(cliente_id)
    ttl_carrinho = r.ttl(chave_carrinho)
    st.code(f"HGETALL {chave_carrinho}\n{json.dumps(r.hgetall(chave_carrinho), indent=2)}\n"
            f"TTL → {ttl_carrinho} s" + ("  (−2 = a chave não existe: carrinho vazio ou já finalizado)"
                                        if ttl_carrinho == -2 else ""), language="text")

    st.subheader("Cache (STRING JSON com TTL)")
    chaves = sorted(r.scan_iter(match="cache:*"))
    if chaves:
        linhas = [{"chave": k, "TTL (s)": r.ttl(k), "bytes": r.strlen(k)} for k in chaves]
        st.dataframe(pd.DataFrame(linhas), hide_index=True, width="stretch")
        st.caption("`cache:produto:{sku}` expira em 300 s; `cache:busca:{hash}` em 60 s. "
                   "Alterar um produto apaga as chaves (invalidação explícita).")
    else:
        st.info("Nenhuma chave de cache no momento: expiraram pelo TTL ou foram invalidadas.")

    st.subheader("Ranking de acessos (ZSET)")
    ranking = s.catalog.mais_acessados(10)
    if ranking:
        nomes = s.catalog.obter_varios([sku for sku, _ in ranking])
        df = pd.DataFrame([{"produto": nomes.get(sku, {}).get("nome", sku), "acessos": int(sc)} for sku, sc in ranking])
        st.bar_chart(df, x="produto", y="acessos", horizontal=True, height=300)
    st.code("ZINCRBY ranking:produtos_acessados 1 <sku>      # a cada visualização\n"
            "ZREVRANGE ranking:produtos_acessados 0 9 WITHSCORES", language="text")


def _aba_mongo(s) -> None:
    colunas = st.columns(3)
    for col, nome in zip(colunas, ("produtos", "clientes", "pedidos")):
        col.metric(f"coleção `{nome}`", s.db[nome].estimated_document_count())

    st.subheader("Últimos pedidos gravados")
    ultimos = list(s.db.pedidos.find({}, {"cliente.nome": 1, "total": 1, "status": 1, "criado_em": 1, "itens": 1})
                   .sort("criado_em", -1).limit(5))
    if ultimos:
        df = pd.DataFrame([{"pedido": p["_id"], "cliente": p["cliente"]["nome"], "itens": len(p["itens"]),
                            "total": p["total"], "status": p["status"], "quando": p["criado_em"]} for p in ultimos])
        st.dataframe(df, hide_index=True, width="stretch",
                     column_config={"total": st.column_config.NumberColumn(format="R$ %.2f")})

    st.subheader("Esquema flexível: mesma coleção, estruturas diferentes")
    p1 = s.db.produtos.find_one({"categoria": "Notebooks"}, {"nome": 1, "especificacoes": 1})
    p2 = s.db.produtos.find_one({"categoria": "Jogos"}, {"nome": 1, "especificacoes": 1})
    c1, c2 = st.columns(2)
    for col, p in ((c1, p1), (c2, p2)):
        if p:
            col.markdown(f"**{p['nome']}**")
            col.json(p["especificacoes"])

    st.subheader("Índices")
    st.json({col: list(s.db[col].index_information().keys()) for col in ("produtos", "clientes", "pedidos")})


def _aba_neo4j(s, cliente_id: str) -> None:
    rotulos = s.neo4j.run("MATCH (n) RETURN labels(n)[0] AS rotulo, count(*) AS total ORDER BY total DESC")
    rels = s.neo4j.run("MATCH ()-[r]->() RETURN type(r) AS tipo, count(*) AS total ORDER BY total DESC")
    c1, c2 = st.columns(2)
    c1.markdown("**Nós por rótulo**")
    c1.dataframe(pd.DataFrame(rotulos), hide_index=True, width="stretch")
    c2.markdown("**Relacionamentos por tipo**")
    c2.dataframe(pd.DataFrame(rels), hide_index=True, width="stretch")

    st.subheader("Suas compras no grafo")
    minhas = s.neo4j.run(
        """
        MATCH (c:Cliente {id: $id})-[r:COMPROU]->(p:Produto)-[:PERTENCE_A]->(cat:Categoria)
        RETURN p.nome AS produto, cat.nome AS categoria, r.quantidade AS quantidade,
               toString(date(r.data)) AS data, r.pedido_id AS pedido
        ORDER BY r.data DESC LIMIT 15
        """, id=cliente_id)
    if minhas:
        st.dataframe(pd.DataFrame(minhas), hide_index=True, width="stretch")
    else:
        st.info("Você ainda não tem compras no grafo.")
    st.code("(:Cliente {id, nome})-[:COMPROU {pedido_id, data, quantidade}]->(:Produto {sku, nome, preco, categoria})\n"
            "(:Cliente)-[:AVALIOU {nota, data}]->(:Produto)\n"
            "(:Produto)-[:PERTENCE_A]->(:Categoria {nome})", language="text")
    st.caption("Neo4j Browser: http://localhost:7474 (usuário neo4j · senha techstore123)")


def _aba_admin(s) -> None:
    st.subheader("Alterar preço de um produto")
    st.markdown("Demonstra **Cache Invalidation**: o `update_one` no MongoDB é seguido de `DEL cache:produto:<sku>` "
                "e `DEL cache:busca:*` no Redis. A próxima leitura vem do Mongo e repovoa o cache.")
    produtos = s.catalog.buscar(limite=100, ordem="nome")
    por_nome = {f"{p['nome']} ({p['_id']})": p for p in produtos}
    escolha = st.selectbox("Produto", list(por_nome))
    produto = por_nome[escolha]
    c1, c2, c3 = st.columns([2, 2, 2])
    c1.metric("Preço atual (MongoDB)", brl(produto["preco"]))
    novo = c2.number_input("Novo preço", min_value=1.0, value=float(produto["preco"]), step=10.0, format="%.2f")
    if c3.button("Atualizar preço", type="primary", width="stretch", icon=":material/save:"):
        s.catalog.atualizar_preco(produto["_id"], novo)
        st.success(f"MongoDB atualizado e cache invalidado: `DEL cache:produto:{produto['_id']}`, `DEL cache:busca:*`.")
        st.rerun()

    st.subheader("Ler o produto agora")
    st.caption("Clique duas vezes: a primeira leitura após uma alteração vem do MongoDB (MISS), a segunda do Redis (HIT).")
    if st.button("Ler produto", icon=":material/search:"):
        lido, origem = s.catalog.obter_produto(produto["_id"], registrar_acesso=False)
        badge_origem(origem)
        st.write(f"**{lido['nome']}** · {brl(lido['preco'])} · TTL do cache: "
                 f"{s.redis.ttl(s.catalog.chave_produto(produto['_id']))} s")


def _aba_log(s) -> None:
    operacoes = s.oplog.recentes(300)
    c1, c2 = st.columns([4, 1])
    filtro = c1.multiselect("Bancos", ["MongoDB", "Redis", "Neo4j"], default=["MongoDB", "Redis", "Neo4j"])
    if c2.button("Limpar log", icon=":material/delete_sweep:", width="stretch"):
        s.oplog.limpar()
        st.rerun()
    linhas = [{"quando": op.quando.strftime("%H:%M:%S"), "banco": op.banco, "operação": op.operacao,
               "detalhe": op.detalhe} for op in operacoes if op.banco in filtro]
    st.caption(f"{len(linhas)} operação(ões) desta sessão, da mais recente para a mais antiga")
    st.dataframe(pd.DataFrame(linhas), hide_index=True, width="stretch", height=520)


def render() -> None:
    s = servicos()
    cliente = st.session_state["cliente"]
    st.title("🔬 Bastidores")
    st.caption("O que cada banco está fazendo agora. Use esta tela durante a demonstração para mostrar "
               "as chamadas acontecendo nos três bancos.")
    _saude()
    abas = st.tabs(["Redis", "MongoDB", "Neo4j", "Administração", "Log de operações"])
    with abas[0]:
        _aba_redis(s, cliente["_id"], st.session_state.get("token", ""))
    with abas[1]:
        _aba_mongo(s)
    with abas[2]:
        _aba_neo4j(s, cliente["_id"])
    with abas[3]:
        _aba_admin(s)
    with abas[4]:
        _aba_log(s)
