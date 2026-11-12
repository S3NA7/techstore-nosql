"""Catálogo e busca: MongoDB com cache e ranking no Redis; relacionados via Neo4j."""
import streamlit as st

from src.ui.components import (
    ORDENS_LABEL, arte_produto, badge_origem, brl, card_produto, para_json, tabela_especificacoes,
)
from src.ui.state import servicos


def _adicionar(sku: str) -> None:
    s = servicos()
    cliente = st.session_state["cliente"]
    qtd = s.cart.adicionar(cliente["_id"], sku)
    st.session_state["toast"] = f"{sku} adicionado ao carrinho (quantidade: {qtd})"


@st.dialog("Detalhes do produto", width="large")
def mostrar_detalhes(produto: dict, origem: str) -> None:
    s = servicos()
    cliente = st.session_state["cliente"]
    badge_origem(origem)
    col_arte, col_info = st.columns([1, 2])
    with col_arte:
        arte_produto(produto, altura=160)
        st.markdown(f"### {brl(produto['preco'])}")
        estoque = int(produto.get("estoque", 0))
        st.caption(f"{estoque} em estoque" if estoque > 0 else "Sem estoque")
        if st.button("Adicionar ao carrinho", type="primary", width="stretch", disabled=estoque <= 0,
                     icon=":material/add_shopping_cart:", key="dlg_add"):
            qtd = s.cart.adicionar(cliente["_id"], produto["_id"])
            st.success(f"Adicionado! Quantidade no carrinho: {qtd}")
    with col_info:
        st.subheader(produto["nome"])
        st.caption(f"{produto['marca']} · {produto['categoria']} · SKU `{produto['_id']}`")
        st.write(produto.get("descricao", ""))
        st.markdown("**Especificações** · documento flexível no MongoDB (campos variam por categoria)")
        tabela_especificacoes(produto.get("especificacoes", {}))

    st.divider()
    st.markdown("**Quem comprou este produto também comprou** · Neo4j")
    relacionados = s.recs.relacionados_ao_produto(produto["_id"])
    if relacionados:
        for r in relacionados:
            st.markdown(f"- **{r['nome']}** · {brl(r['preco'])} · {r['forca']} cliente(s) em comum")
    else:
        st.caption("Ainda não há compras em comum no grafo para este produto.")
    with st.expander("Ver documento JSON completo (MongoDB)"):
        st.json(para_json(produto))


def render() -> None:
    s = servicos()
    st.title("🛍️ Catálogo")

    f1, f2, f3, f4 = st.columns([3, 2, 2, 2])
    texto = f1.text_input("Buscar", placeholder="ex.: notebook gamer, mouse, PlayStation", key="busca_texto")
    categoria = f2.selectbox("Categoria", ["Todas"] + s.catalog.categorias())
    marca = f3.selectbox("Marca", ["Todas"] + s.catalog.marcas())
    ordem = f4.selectbox("Ordenar por", list(ORDENS_LABEL), format_func=ORDENS_LABEL.get)

    produtos, origem = s.catalog.buscar_com_origem(
        texto, None if categoria == "Todas" else categoria, None if marca == "Todas" else marca, ordem)

    # Mais acessados (Redis ZSET) em uma faixa no topo
    ranking = s.catalog.mais_acessados(5)
    if ranking:
        nomes = s.catalog.obter_varios([sku for sku, _ in ranking])
        st.markdown("**🔥 Mais acessados** · Redis `ZREVRANGE ranking:produtos_acessados`")
        for col, (sku, score) in zip(st.columns(5), ranking):
            nome = nomes.get(sku, {}).get("nome", sku)
            col.metric(nome, int(score), help=f"{nome}: {int(score)} acessos (ZSCORE)")

    c1, c2 = st.columns([4, 1])
    c1.caption(f"{len(produtos)} produto(s) encontrado(s)")
    with c2:
        badge_origem(origem)

    if not produtos:
        st.info("Nenhum produto encontrado. Tente outro termo ou limpe os filtros.")
        return

    colunas = st.columns(3)
    for i, p in enumerate(produtos):
        with colunas[i % 3]:
            if card_produto(p, ao_adicionar=_adicionar):
                produto, origem_produto = s.catalog.obter_produto(p["_id"])  # registra o acesso no ranking
                mostrar_detalhes(produto, origem_produto)
