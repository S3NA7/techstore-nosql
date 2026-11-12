"""Tela de login e cadastro (MongoDB para o cadastro, Redis para o token de sessão)."""
import streamlit as st

from src.services.auth import EmailJaCadastradoError
from src.ui.state import servicos, verificar_conexoes


def render() -> None:
    s = servicos()
    st.title("🛒 TechStore")
    st.caption("E-commerce com persistência poliglota: MongoDB (catálogo e pedidos) · "
               "Redis (sessão, carrinho e cache) · Neo4j (recomendações em grafo)")

    if aviso := st.session_state.pop("aviso_sessao", None):
        st.warning(aviso)

    status = verificar_conexoes()
    colunas = st.columns(3)
    for col, (nome, (ok, detalhe)) in zip(colunas, status.items()):
        col.metric(nome, "online" if ok else "offline", detalhe, delta_color="normal" if ok else "inverse")
    indisponiveis = [nome for nome, (ok, _) in status.items() if not ok]
    if indisponiveis:
        st.error(f"Banco(s) indisponível(is): {', '.join(indisponiveis)}. "
                 "Rode `docker compose up -d` e recarregue a página.")

    aba_login, aba_cadastro = st.tabs(["Entrar", "Criar conta"])

    with aba_login:
        with st.form("form_login"):
            email = st.text_input("E-mail", value="ana@techstore.com")
            senha = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar", type="primary", width="stretch", icon=":material/login:"):
                try:
                    token = s.auth.login(email, senha)
                except Exception as exc:  # banco fora do ar
                    st.error(f"Não foi possível autenticar: {exc}")
                    return
                if token:
                    st.session_state["token"] = token
                    st.rerun()
                st.error("E-mail ou senha inválidos.")
        st.info("Usuário de demonstração: **ana@techstore.com** · senha **123456** "
                "(todos os clientes gerados pela carga inicial usam a senha 123456).")

    with aba_cadastro:
        with st.form("form_cadastro"):
            nome = st.text_input("Nome completo")
            email_novo = st.text_input("E-mail")
            senha_nova = st.text_input("Senha", type="password")
            confirmacao = st.text_input("Confirme a senha", type="password")
            if st.form_submit_button("Criar conta", width="stretch", icon=":material/person_add:"):
                if not nome.strip() or not email_novo.strip() or not senha_nova:
                    st.error("Preencha nome, e-mail e senha.")
                elif len(senha_nova) < 6:
                    st.error("A senha precisa ter pelo menos 6 caracteres.")
                elif senha_nova != confirmacao:
                    st.error("As senhas não conferem.")
                else:
                    try:
                        s.auth.registrar(nome, email_novo, senha_nova)
                    except EmailJaCadastradoError:
                        st.error("Já existe uma conta com esse e-mail.")
                    else:
                        st.session_state["token"] = s.auth.login(email_novo, senha_nova)
                        st.session_state["toast"] = f"Bem-vindo(a), {nome.split()[0]}!"
                        st.rerun()
