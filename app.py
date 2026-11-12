"""TechStore — e-commerce poliglota (MongoDB + Redis + Neo4j) em Streamlit.

Execute com:  streamlit run app.py
"""
import streamlit as st

from src.ui.state import cliente_logado, servicos
from src.ui.telas import bastidores, carrinho, catalogo, checkout, login, pedidos, recomendacoes

st.set_page_config(page_title="TechStore", page_icon="🛒", layout="wide", initial_sidebar_state="expanded")

ERROS_DE_CONEXAO = (ConnectionError, TimeoutError, OSError)
try:  # exceções específicas dos drivers, quando disponíveis
    import redis.exceptions as _rx
    from neo4j.exceptions import ServiceUnavailable as _Neo4jIndisponivel
    from pymongo.errors import PyMongoError as _MongoErro

    ERROS_DE_CONEXAO += (_rx.ConnectionError, _rx.TimeoutError, _Neo4jIndisponivel, _MongoErro)
except ImportError:  # pragma: no cover
    pass


def _sidebar(s, cliente: dict) -> None:
    with st.sidebar:
        st.markdown(f"**{cliente['nome']}**  \n{cliente['email']}")
        total = s.cart.total_itens(cliente["_id"])
        st.badge(f"{total} item(ns) no carrinho", icon=":material/shopping_cart:", color="violet")
        if st.button("Sair", icon=":material/logout:", width="stretch"):
            s.auth.logout(st.session_state["token"])
            for chave in ("token", "cliente", "oplog"):
                st.session_state.pop(chave, None)
            st.rerun()
        st.divider()
        st.caption("Últimas operações nos bancos")
        for op in s.oplog.recentes(5):
            st.caption(f"`{op.banco}` {op.operacao}")


def main() -> None:
    try:
        s = servicos()
        cliente = cliente_logado(s)
    except ERROS_DE_CONEXAO as exc:
        st.error("Não foi possível conectar aos bancos de dados. Verifique se os containers estão rodando "
                 "(`docker compose up -d`) e recarregue a página.")
        st.exception(exc)
        st.stop()

    if cliente is None:
        st.session_state.pop("cliente", None)
        st.navigation([st.Page(login.render, title="Entrar", icon=":material/login:")], position="hidden").run()
        return

    st.session_state["cliente"] = cliente
    paginas = {
        "catalogo": st.Page(catalogo.render, title="Catálogo", icon=":material/storefront:", url_path="catalogo",
                            default=True),
        "carrinho": st.Page(carrinho.render, title="Carrinho", icon=":material/shopping_cart:", url_path="carrinho"),
        "recomendacoes": st.Page(recomendacoes.render, title="Recomendações", icon=":material/hub:",
                                 url_path="recomendacoes"),
        "checkout": st.Page(checkout.render, title="Checkout", icon=":material/payments:", url_path="checkout"),
        "pedidos": st.Page(pedidos.render, title="Meus pedidos", icon=":material/receipt_long:", url_path="pedidos"),
        "bastidores": st.Page(bastidores.render, title="Bastidores", icon=":material/monitoring:",
                              url_path="bastidores"),
    }
    st.session_state["paginas"] = paginas
    pagina = st.navigation({
        "Loja": [paginas["catalogo"], paginas["carrinho"], paginas["recomendacoes"], paginas["checkout"],
                 paginas["pedidos"]],
        "Técnico": [paginas["bastidores"]],
    })
    _sidebar(s, cliente)

    if mensagem := st.session_state.pop("toast", None):
        st.toast(mensagem, icon="✅")

    try:
        pagina.run()
    except ERROS_DE_CONEXAO as exc:
        st.error("Um dos bancos de dados parou de responder durante a operação. "
                 "Verifique os containers (`docker compose ps`) e tente novamente.")
        st.exception(exc)


main()
