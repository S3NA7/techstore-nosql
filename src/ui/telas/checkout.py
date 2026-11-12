"""Checkout: grava o pedido no MongoDB, cria as arestas COMPROU no Neo4j e limpa o carrinho no Redis."""
import pandas as pd
import streamlit as st

from src.services.checkout import CarrinhoVazioError, EstoqueInsuficienteError
from src.ui.components import PAGAMENTO_LABEL, badge_banco, brl, para_json
from src.ui.state import servicos


def _mostrar_confirmacao(confirmado: dict) -> None:
    pedido, operacoes = confirmado["pedido"], confirmado["operacoes"]
    st.success(f"Pedido **{pedido['_id']}** confirmado! Total {brl(pedido['total'])}.")
    if confirmado.pop("novo", False):  # balões só na primeira exibição
        st.balloons()
    col_doc, col_ops = st.columns(2)
    with col_doc:
        st.markdown("**Documento gravado no MongoDB** · coleção `pedidos`")
        st.json(para_json(pedido), expanded=2)
    with col_ops:
        st.markdown("**O que aconteceu em cada banco**")
        for op in reversed(operacoes):
            c1, c2 = st.columns([1, 4])
            with c1:
                badge_banco(op.banco)
            c2.markdown(f"`{op.operacao}` {op.detalhe.replace('$', chr(92) + '$')}")  # evita LaTeX no $param
    # A confirmação fica em session_state até o usuário sair dela: assim o clique nos botões
    # abaixo (que dispara um rerun) ainda encontra os botões renderizados.
    b1, b2 = st.columns(2)
    if b1.button("Ver meus pedidos", type="primary", width="stretch", icon=":material/receipt_long:"):
        st.session_state.pop("pedido_confirmado", None)
        st.switch_page(st.session_state["paginas"]["pedidos"])
    if b2.button("Voltar ao catálogo", width="stretch", icon=":material/storefront:"):
        st.session_state.pop("pedido_confirmado", None)
        st.switch_page(st.session_state["paginas"]["catalogo"])


def render() -> None:
    s = servicos()
    cliente = st.session_state["cliente"]
    st.title("💳 Checkout")

    resumo = s.checkout.resumo(cliente["_id"])
    confirmado = st.session_state.get("pedido_confirmado")
    if confirmado and not resumo["itens"]:
        _mostrar_confirmacao(confirmado)
        return
    st.session_state.pop("pedido_confirmado", None)  # carrinho voltou a ter itens: confirmação antiga sai

    if not resumo["itens"]:
        st.info("Seu carrinho está vazio. Adicione produtos antes de finalizar.")
        st.page_link(st.session_state["paginas"]["catalogo"], label="Ir para o catálogo", icon=":material/storefront:")
        return

    col_itens, col_form = st.columns([3, 2])
    with col_itens:
        st.subheader("Itens do pedido")
        df = pd.DataFrame(resumo["itens"])[["nome", "quantidade", "preco_unitario", "subtotal", "estoque"]]
        df.columns = ["Produto", "Qtd", "Preço unitário", "Subtotal", "Estoque"]
        st.dataframe(df, hide_index=True, width="stretch", column_config={
            "Preço unitário": st.column_config.NumberColumn(format="R$ %.2f"),
            "Subtotal": st.column_config.NumberColumn(format="R$ %.2f"),
        })
        st.markdown(f"### Total: {brl(resumo['total'])}")
        sem_estoque = [i for i in resumo["itens"] if i["quantidade"] > i["estoque"]]
        for i in sem_estoque:
            st.warning(f"{i['nome']}: pedido {i['quantidade']}, disponível {i['estoque']}. Ajuste no carrinho.")

    with col_form:
        st.subheader("Entrega e pagamento")
        endereco = cliente.get("endereco", {})
        with st.form("form_checkout"):
            rua = st.text_input("Endereço", value=endereco.get("rua", ""), placeholder="Rua, número")
            c1, c2 = st.columns([3, 1])
            cidade = c1.text_input("Cidade", value=endereco.get("cidade", ""))
            uf = c2.text_input("UF", value=endereco.get("uf", ""), max_chars=2)
            cep = st.text_input("CEP", value=endereco.get("cep", ""))
            forma = st.radio("Forma de pagamento", list(PAGAMENTO_LABEL), format_func=PAGAMENTO_LABEL.get,
                             horizontal=True)
            confirmar = st.form_submit_button("Confirmar pedido", type="primary", width="stretch",
                                              icon=":material/check_circle:", disabled=bool(sem_estoque))

    if confirmar:
        if not rua.strip() or not cidade.strip():
            st.error("Informe o endereço de entrega (rua e cidade).")
            return
        antes = s.oplog.total  # contador monotônico: funciona mesmo com a janela do log cheia
        try:
            pedido = s.checkout.finalizar(cliente, forma, {"rua": rua, "cidade": cidade, "uf": uf.upper(), "cep": cep})
        except CarrinhoVazioError:
            st.error("O carrinho está vazio.")
        except EstoqueInsuficienteError as exc:
            st.error(str(exc))
        else:
            novas = s.oplog.total - antes
            st.session_state["pedido_confirmado"] = {"pedido": pedido, "operacoes": s.oplog.recentes(300)[:novas],
                                                     "novo": True}
            st.rerun()
