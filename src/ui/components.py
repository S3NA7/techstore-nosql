"""Componentes visuais reutilizáveis (cards, badges, tabelas, grafo)."""
from __future__ import annotations

import json
from typing import Callable

import pandas as pd
import streamlit as st
from pyvis.network import Network

ICONES_CATEGORIA = {
    "Notebooks": "💻", "Smartphones": "📱", "Periféricos": "🖱️", "Consoles": "🎮",
    "Jogos": "🕹️", "Áudio": "🎧", "Acessórios": "🔌",
}
CORES_CATEGORIA = {
    "Notebooks": "#7C5CFF", "Smartphones": "#2DD4BF", "Periféricos": "#F59E0B", "Consoles": "#EF4444",
    "Jogos": "#22C55E", "Áudio": "#3B82F6", "Acessórios": "#EC4899",
}
CORES_BANCO = {"MongoDB": "green", "Redis": "red", "Neo4j": "blue"}
ORDENS_LABEL = {
    "relevancia": "Relevância (mais acessados)",
    "menor_preco": "Menor preço",
    "maior_preco": "Maior preço",
    "nome": "Nome (A-Z)",
}
PAGAMENTO_LABEL = {"pix": "Pix", "cartao": "Cartão de crédito", "boleto": "Boleto"}


def brl(valor: float) -> str:
    return "R$ " + f"{float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def para_json(doc) -> dict:
    """Converte ObjectId/datetime em texto para exibir com st.json."""
    return json.loads(json.dumps(doc, default=str, ensure_ascii=False))


def badge_origem(origem: str) -> None:
    if origem == "cache":
        st.badge("Redis · cache HIT", color="red", icon=":material/bolt:")
    else:
        st.badge("MongoDB · lido do banco", color="green", icon=":material/database:")


def badge_banco(banco: str) -> None:
    st.badge(banco, color=CORES_BANCO.get(banco, "gray"))


def _formatar_valor(v) -> str:
    if isinstance(v, bool):
        return "Sim" if v else "Não"
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    return str(v)


def tabela_especificacoes(especificacoes: dict) -> None:
    if not especificacoes:
        st.caption("Sem especificações cadastradas.")
        return
    linhas = [{"Especificação": k.replace("_", " ").capitalize(), "Valor": _formatar_valor(v)}
              for k, v in especificacoes.items()]
    st.dataframe(pd.DataFrame(linhas), hide_index=True, width="stretch")


def arte_produto(produto: dict, altura: int = 110) -> None:
    categoria = produto.get("categoria", "")
    icone = ICONES_CATEGORIA.get(categoria, "📦")
    cor = CORES_CATEGORIA.get(categoria, "#64748B")
    st.markdown(
        f'<div style="background:linear-gradient(135deg,{cor}33,{cor}11);border:1px solid {cor}66;'
        f'border-radius:12px;height:{altura}px;display:flex;align-items:center;justify-content:center;'
        f'font-size:{altura // 2}px">{icone}</div>',
        unsafe_allow_html=True,
    )


def card_produto(produto: dict, ao_adicionar: Callable[[str], None], prefixo: str = "cat") -> bool:
    """Desenha o card. Devolve True quando o botão "Detalhes" foi clicado nesta execução."""
    sku = produto["_id"]
    estoque = int(produto.get("estoque", 0))
    with st.container(border=True):
        arte_produto(produto)
        st.markdown(f"**{produto['nome']}**")
        st.caption(f"{produto['marca']} · {produto['categoria']} · `{sku}`")
        st.markdown(f"#### {brl(produto['preco'])}")
        st.caption(f"{estoque} em estoque" if estoque > 0 else "Sem estoque")
        c1, c2 = st.columns(2)
        c1.button("Adicionar", key=f"{prefixo}_add_{sku}", on_click=ao_adicionar, args=(sku,),
                  disabled=estoque <= 0, type="primary", width="stretch", icon=":material/add_shopping_cart:")
        return c2.button("Detalhes", key=f"{prefixo}_det_{sku}", width="stretch", icon=":material/info:")


def cadeia_caminho(caminho: list[dict]) -> str:
    """Formata o shortestPath como texto: Ana —COMPROU→ PS5 ←COMPROU— Bruno —COMPROU→ FC 25."""
    if not caminho:
        return "_Nenhum caminho encontrado no grafo._"
    partes = []
    for i, no in enumerate(caminho):
        icone = "🧑" if no["rotulo"] == "Cliente" else "📦"
        if i > 0:
            anterior = caminho[i - 1]
            seta = f" —{no['via']}→ " if anterior["rotulo"] == "Cliente" else f" ←{no['via']}— "
            partes.append(seta)
        partes.append(f"{icone} **{no['nome']}**")
    return "".join(partes)


def grafo_html(nos: list[dict], arestas: list[dict], destaque_id: str | None = None,
               altura_px: int = 540) -> str:
    """Gera o HTML (vis.js embutido, funciona offline) da vizinhança do cliente no grafo."""
    net = Network(height=f"{altura_px}px", width="100%", bgcolor="#0e1117", font_color="#fafafa",
                  directed=True, cdn_resources="in_line")
    net.barnes_hut(gravity=-6000, central_gravity=0.3, spring_length=140, spring_strength=0.02)
    for no in nos:
        if no["id"] == destaque_id:
            cor, tamanho = "#F59E0B", 34
        elif no["rotulo"] == "Cliente":
            cor, tamanho = "#7C5CFF", 22
        else:
            cor, tamanho = "#2DD4BF", 18
        net.add_node(no["id"], label=no["nome"], title=f"{no['rotulo']}: {no['nome']}", color=cor,
                     size=tamanho, shape="dot" if no["rotulo"] == "Produto" else "ellipse")
    for a in arestas:
        cor = "#22C55E" if a["tipo"] == "COMPROU" else "#F59E0B"
        net.add_edge(a["origem"], a["destino"], label=a["tipo"], color=cor,
                     font={"size": 9, "color": "#9CA3AF", "strokeWidth": 0})
    return net.generate_html()
