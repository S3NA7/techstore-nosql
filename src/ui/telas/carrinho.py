"""Carrinho ativo: cada alteração é um comando no Redis (HINCRBY/HSET/HDEL/DEL)."""
import json

import streamlit as st

from src.ui.components import brl
from src.ui.state import servicos


def _cliente_id() -> str:
    return st.session_state["cliente"]["_id"]


def _alterar_quantidade(sku: str, chave_widget: str) -> None:
    s = servicos()
    s.cart.definir_quantidade(_cliente_id(), sku, int(st.session_state[chave_widget]))


def _remover(sku: str) -> None:
    servicos().cart.remover(_cliente_id(), sku)
    st.session_state["toast"] = f"{sku} removido do carrinho"


def _limpar() -> None:
    servicos().cart.limpar(_cliente_id())
    st.session_state["toast"] = "Carrinho esvaziado"


def _mostrar_redis(s, cliente_id: str) -> None:
    chave = s.cart.chave(cliente_id)
    with st.expander("Como está no Redis agora"):
        conteudo = s.redis.hgetall(chave)
        ttl = s.redis.ttl(chave)
        st.code(
            f"TYPE {chave}      → {s.redis.type(chave)}\n"
            f"HGETALL {chave}\n{json.dumps(conteudo, indent=2, ensure_ascii=False)}\n"
            f"TTL {chave}       → {ttl} s"
            + (f" (~{ttl // 86400} dias)" if ttl > 0 else "  (−2 = a chave não existe)" if ttl == -2 else ""),
            language="text",
        )
        st.caption("Chave = `carrinho:{cliente_id}`, tipo Hash (campo = SKU, valor = quantidade). "
                   "O TTL descarta carrinhos abandonados; o checkout apaga a chave.")


def render() -> None:
    s = servicos()
    cliente_id = _cliente_id()
    st.title("🛒 Carrinho")

    resumo = s.checkout.resumo(cliente_id)
    if not resumo["itens"]:
        st.info("Seu carrinho está vazio.")
        st.page_link(st.session_state["paginas"]["catalogo"], label="Ir para o catálogo", icon=":material/storefront:")
        _mostrar_redis(s, cliente_id)
        return

    cab = st.columns([4, 2, 2, 2, 1])
    for col, titulo in zip(cab, ["Produto", "Preço", "Quantidade", "Subtotal", ""]):
        col.markdown(f"**{titulo}**")

    for item in resumo["itens"]:
        c = st.columns([4, 2, 2, 2, 1])
        c[0].markdown(f"**{item['nome']}**  \n`{item['sku']}`")
        c[1].markdown(brl(item["preco_unitario"]))
        # a chave inclui a quantidade: quando o Redis muda, o widget nasce de novo com o valor fresco
        chave_widget = f"qtd_{item['sku']}_{item['quantidade']}"
        c[2].number_input("Quantidade", min_value=0, max_value=max(item["estoque"], item["quantidade"]),
                          value=item["quantidade"], step=1, key=chave_widget, label_visibility="collapsed",
                          on_change=_alterar_quantidade, args=(item["sku"], chave_widget))
        c[3].markdown(brl(item["subtotal"]))
        c[4].button("Remover", key=f"rm_{item['sku']}", icon=":material/delete:", type="tertiary",
                    on_click=_remover, args=(item["sku"],))
        if item["quantidade"] > item["estoque"]:
            st.warning(f"Só há {item['estoque']} unidade(s) de {item['nome']} em estoque.")

    st.divider()
    t1, t2 = st.columns([3, 1])
    t1.markdown(f"### Total: {brl(resumo['total'])}")
    t1.caption(f"{resumo['quantidade_itens']} item(ns) · preços lidos do MongoDB, quantidades do Redis")
    t2.button("Limpar carrinho", on_click=_limpar, width="stretch", icon=":material/remove_shopping_cart:")
    if t2.button("Finalizar compra", type="primary", width="stretch", icon=":material/payments:"):
        st.switch_page(st.session_state["paginas"]["checkout"])

    _mostrar_redis(s, cliente_id)
