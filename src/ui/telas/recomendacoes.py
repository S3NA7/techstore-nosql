"""Painel de recomendação: consultas Cypher no Neo4j e visualização do grafo."""
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from src.services.recommendations import (
    PERFIL_SIMILAR_POR_AVALIACAO, POPULARES_NA_CATEGORIA, QUEM_COMPROU_TAMBEM_COMPROU,
)
from src.ui.components import brl, cadeia_caminho, grafo_html
from src.ui.state import servicos


def _adicionar(sku: str) -> None:
    s = servicos()
    qtd = s.cart.adicionar(st.session_state["cliente"]["_id"], sku)
    st.session_state["toast"] = f"{sku} adicionado ao carrinho (quantidade: {qtd})"


def render() -> None:
    s = servicos()
    cliente = st.session_state["cliente"]
    cid = cliente["_id"]
    st.title("✨ Recomendações para você")
    st.caption("Geradas em tempo real no Neo4j a partir do grafo (:Cliente)-[:COMPROU|AVALIOU]->(:Produto)")

    aba1, aba2, aba3, aba4 = st.tabs([
        "Quem comprou, também comprou", "Perfil similar (avaliações)", "Populares por categoria", "Meu grafo",
    ])

    with aba1:
        recs = s.recs.quem_comprou_tambem_comprou(cid, limite=9)
        if not recs:
            st.info("Faça uma compra para o grafo começar a recomendar!")
        colunas = st.columns(3)
        for i, r in enumerate(recs):
            with colunas[i % 3], st.container(border=True):
                st.markdown(f"**{r['nome']}**")
                st.caption(f"{r['categoria']} · `{r['sku']}`")
                st.markdown(f"#### {brl(r['preco'])}")
                st.caption(f"{r['forca']} cliente(s) com compras em comum com você")
                b1, b2 = st.columns(2)
                b1.button("Adicionar", key=f"rec_add_{r['sku']}", on_click=_adicionar, args=(r["sku"],),
                          type="primary", width="stretch", icon=":material/add_shopping_cart:")
                if b2.button("Por quê?", key=f"rec_why_{r['sku']}", width="stretch", icon=":material/route:"):
                    st.markdown(cadeia_caminho(s.recs.caminho_recomendacao(cid, r["sku"])))
                    st.caption("Cypher: `shortestPath((c:Cliente)-[:COMPROU|AVALIOU*..6]-(p:Produto))`")
        with st.expander("Cypher executado"):
            st.code(QUEM_COMPROU_TAMBEM_COMPROU.strip(), language="cypher")

    with aba2:
        similares = s.recs.perfil_similar_por_avaliacao(cid, limite=10)
        st.markdown("Clientes que deram **notas parecidas às suas** (diferença < 1) nos mesmos produtos "
                    "e avaliaram bem (nota ≥ 4) algo que você ainda não comprou. Adaptado do exemplo do enunciado.")
        if similares:
            df = pd.DataFrame(similares)[["nome", "categoria", "preco", "origem", "nota"]]
            df.columns = ["Produto", "Categoria", "Preço", "Recomendado por", "Nota dada"]
            st.dataframe(df, hide_index=True, width="stretch",
                         column_config={"Preço": st.column_config.NumberColumn(format="R$ %.2f")})
        else:
            st.info("Avalie alguns produtos em **Meus pedidos** para habilitar este tipo de recomendação.")
        with st.expander("Cypher executado"):
            st.code(PERFIL_SIMILAR_POR_AVALIACAO.strip(), language="cypher")

    with aba3:
        categoria = st.selectbox("Categoria", s.catalog.categorias(), key="rec_categoria")
        populares = s.recs.populares_na_categoria(categoria, limite=10)
        if populares:
            df = pd.DataFrame(populares)
            st.bar_chart(df, x="nome", y="compras", horizontal=True, height=320)
            for p in populares[:3]:
                st.markdown(f"- **{p['nome']}** · {brl(p['preco'])} · {p['compras']} compra(s) no grafo")
        else:
            st.info("Nenhum produto nessa categoria.")
        with st.expander("Cypher executado"):
            st.code(POPULARES_NA_CATEGORIA.strip(), language="cypher")

    with aba4:
        nos, arestas = s.recs.subgrafo_cliente(cid, limite=40)
        st.caption(f"{len(nos)} nós · {len(arestas)} relacionamentos · "
                   "🟠 você · 🟣 outros clientes · 🟢 produtos · arestas verdes = COMPROU, laranja = AVALIOU")
        if nos:
            components.html(grafo_html(nos, arestas, destaque_id=cid), height=560, scrolling=False)
        else:
            st.info("Seu grafo ainda está vazio: faça a primeira compra.")
