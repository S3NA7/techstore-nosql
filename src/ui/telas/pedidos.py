"""Histórico de pedidos (MongoDB) com avaliação dos itens (aresta AVALIOU no Neo4j)."""
import streamlit as st

from src.ui.components import PAGAMENTO_LABEL, brl, para_json
from src.ui.state import servicos


def _avaliar(sku: str, chave_widget: str) -> None:
    indice = st.session_state.get(chave_widget)
    if indice is None:
        return
    s = servicos()
    nota = int(indice) + 1
    s.orders.avaliar(st.session_state["cliente"]["_id"], sku, nota)
    st.session_state["toast"] = f"Nota {nota}★ para {sku} gravada no Neo4j (MERGE [:AVALIOU])"


def render() -> None:
    s = servicos()
    cliente = st.session_state["cliente"]
    cid = cliente["_id"]
    st.title("📦 Meus pedidos")

    pedidos = s.orders.pedidos_do_cliente(cid)
    if not pedidos:
        st.info("Você ainda não fez nenhum pedido.")
        st.page_link(st.session_state["paginas"]["catalogo"], label="Ir para o catálogo", icon=":material/storefront:")
        return

    notas = s.orders.notas_do_cliente(cid)
    st.caption(f"{len(pedidos)} pedido(s) · MongoDB `find({{'cliente.id': ...}}).sort('criado_em', -1)` · "
               "avalie os itens para alimentar o grafo de recomendação (Neo4j)")

    for ped in pedidos:
        titulo = (f"{ped['criado_em']:%d/%m/%Y %H:%M} · {brl(ped['total'])} · {ped.get('status', '')} · "
                  f"{len(ped['itens'])} item(ns) · {ped['_id']}")
        with st.expander(titulo, expanded=False):
            cab = st.columns([4, 1, 2, 3])
            for col, t in zip(cab, ["Produto", "Qtd", "Subtotal", "Sua avaliação"]):
                col.markdown(f"**{t}**")
            for item in ped["itens"]:
                c = st.columns([4, 1, 2, 3])
                c[0].markdown(f"{item['nome']}  \n`{item['sku']}`")
                c[1].markdown(f"x{item['quantidade']}")
                c[2].markdown(brl(item["subtotal"]))
                chave_widget = f"nota_{ped['_id']}_{item['sku']}"
                if chave_widget not in st.session_state and item["sku"] in notas:
                    st.session_state[chave_widget] = notas[item["sku"]] - 1  # st.feedback usa índice 0..4
                c[3].feedback("stars", key=chave_widget, on_change=_avaliar, args=(item["sku"], chave_widget))
            endereco = ped.get("endereco_entrega", {})
            st.caption(f"Pagamento: {PAGAMENTO_LABEL.get(ped.get('forma_pagamento'), ped.get('forma_pagamento'))} · "
                       f"Entrega: {endereco.get('rua', '')}, {endereco.get('cidade', '')} - {endereco.get('uf', '')}")
            with st.popover("Ver documento no MongoDB", icon=":material/data_object:"):
                st.json(para_json(ped), expanded=2)
