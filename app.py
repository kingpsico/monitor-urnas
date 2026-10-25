
import random
import time
from datetime import datetime

import pandas as pd
import requests
import streamlit as st

# ============================================================
# MONITOR DE URNAS — FLÁVIO BOLSONARO x LULA
# Instalação: pip install -U streamlit pandas requests
# Execução: streamlit run app.py
# ============================================================

st.set_page_config(
    page_title="Monitor de Urnas | Painel Nacional",
    page_icon="🗳️",
    layout="wide",
)

INTERVALO = 20
TSE_BASE = "https://resultados.tse.jus.br"
TSE_CONFIG = f"{TSE_BASE}/oficial/comum/config/ele-c.json"

CANDIDATOS = {
    "A": "Flávio Bolsonaro (PL)",
    "B": "Luiz Inácio Lula da Silva (PT)",
}

ESTADOS = {
    "SP": (28_200_000, 43.0, 52.0),
    "MG": (12_000_000, 49.0, 50.0),
    "RJ": (9_500_000, 42.0, 53.0),
    "BA": (9_000_000, 66.5, 33.0),
    "RS": (7_500_000, 42.0, 55.6),
    "PR": (7_500_000, 37.0, 63.0),
    "PE": (5_500_000, 65.0, 35.0),
    "CE": (5_450_000, 66.0, 34.0),
    "PA": (5_050_000, 54.0, 46.0),
    "MA": (4_000_000, 67.0, 33.0),
    "SC": (4_900_000, 31.0, 69.0),
    "GO": (4_350_000, 41.0, 59.0),
    "PB": (2_672_000, 64.0, 36.0),
    "RN": (2_248_000, 63.0, 37.0),
    "AL": (1_940_000, 58.0, 42.0),
    "PI": (2_180_000, 74.0, 26.0),
    "MT": (2_410_000, 33.0, 66.5),
    "DF": (1_921_000, 38.0, 57.0),
    "ES": (2_520_000, 42.0, 57.0),
    "AM": (2_190_000, 51.0, 48.5),
    "MS": (1_730_000, 38.0, 62.0),
    "SE": (1_360_000, 64.0, 36.0),
    "RO": (1_112_000, 27.0, 72.0),
    "TO": (970_000, 48.0, 51.0),
    "AC": (545_000, 27.5, 65.0),
    "AP": (535_000, 49.0, 48.5),
    "RR": (333_000, 26.0, 73.0),
}

SESSAO = requests.Session()
SESSAO.headers.update({"User-Agent": "MonitorUrnas/1.0"})


def fmt(n):
    return f"{int(n):,}".replace(",", ".")


def pct(n, total):
    return 100 * n / total if total else 0.0


def buscar_json(url):
    r = SESSAO.get(url, timeout=10)
    r.raise_for_status()
    return r.json()


def simulador(progresso, semente):
    """Simulação determinística para permitir testes reproduzíveis."""
    rng = random.Random(semente)
    linhas = []

    for uf, (esperados, base_a, base_b) in ESTADOS.items():
        ajuste = 1.3 if uf in ("SP", "PR", "SC", "RS") else 1.0

        if uf in ("BA", "PE", "MA", "PI"):
            p = max(0, min(100, (progresso - 10) * 1.1))
        else:
            p = min(100, progresso * ajuste)

        total = round(esperados * p / 100)

        variacao = rng.uniform(-1, 1) * (1 - p / 100)
        a = max(0, base_a + 0.5 + variacao)
        b = max(0, base_b - 0.5 - variacao)
        soma = a + b or 1

        votos_a = round(total * a / soma)
        votos_b = total - votos_a

        # A base original contém votos esperados, não o número oficial
        # de seções eleitorais. A quantidade de seções abaixo é apenas
        # uma escala de simulação e não representa dados do TSE.
        secoes_estimadas = max(1, round(esperados / 300))
        secoes_totalizadas = round(secoes_estimadas * p / 100)

        linhas.append({
            "UF": uf,
            "Votos esperados (base)": esperados,
            "Seções estimadas (simulação)": secoes_estimadas,
            "Seções totalizadas (simulação)": secoes_totalizadas,
            "Progresso (%)": p,
            "Votos apurados A": votos_a,
            "Votos apurados B": votos_b,
            "Projeção A (votos)": round(
                votos_a + max(0, esperados - total) * a / soma
            ),
            "Projeção B (votos)": round(
                votos_b + max(0, esperados - total) * b / soma
            ),
        })

    return pd.DataFrame(linhas)


def descobrir_eleicao(config, turno):
    """Procura o código do turno na configuração pública do TSE."""
    for pleito in config.get("pl", []):
        ciclo = pleito.get("c", "ele2026")

        for eleicao in pleito.get("e", []):
            codigo = str(eleicao.get("cd", ""))
            nome = str(eleicao.get("nm", "")).lower()
            t = str(eleicao.get("t", ""))

            cargos = []
            for abrangencia in eleicao.get("abr", []):
                cargos.extend(abrangencia.get("cp", []))

            presidencial = any(
                str(c.get("cd", "")) == "1"
                or "presidente" in str(c.get("ds", "")).lower()
                for c in cargos
            )

            geral = (
                "geral" in nome
                or "federal" in nome
                or presidencial
            )

            if t == turno and codigo and geral:
                return ciclo, codigo, eleicao

    raise ValueError(
        f"O código do {turno}º turno não foi encontrado "
        "na configuração consultada do TSE."
    )


def buscar_tse(turno):
    """
    Consulta a configuração oficial e tenta ler os arquivos nacionais
    e estaduais. O formato e os caminhos devem corresponder à eleição
    publicada pelo TSE.
    """
    config = buscar_json(TSE_CONFIG)
    ciclo, codigo, eleicao = descobrir_eleicao(config, turno)

    # Estrutura usual dos arquivos de divulgação de resultados.
    # Se o TSE alterar o caminho ou o formato, o erro será apresentado.
    base = f"{TSE_BASE}/oficial/{ciclo}/dados"
    abrangencias = ["br"] + [uf.lower() for uf in ESTADOS]
    registros = []
    falhas = []

    for uf in abrangencias:
        url = f"{base}/{uf}/{uf}-c0001-e{codigo.zfill(6)}-v.json"

        try:
            dados = buscar_json(url)
            candidatos = dados.get("cand", [])

            if not isinstance(candidatos, list):
                raise ValueError("Lista de candidatos inválida.")

            mapa = {}
            for c in candidatos:
                nome = str(c.get("nm", "")).strip()
                numero = str(c.get("n", "")).strip()
                votos = int(float(str(c.get("vap", "0")).replace(",", ".")))

                if not nome:
                    continue

                mapa[nome] = {
                    "numero": numero,
                    "votos": max(0, votos),
                }

            if not mapa:
                raise ValueError("O arquivo não contém votos de candidatos.")

            # Identificação por nome, evitando assumir que a ordem
            # ou a numeração interna será sempre a mesma.
            for nome_alvo in CANDIDATOS.values():
                encontrados = [
                    (nome, info)
                    for nome, info in mapa.items()
                    if nome_alvo.split(" (")[0].lower() in nome.lower()
                ]

                votos = encontrados[0][1]["votos"] if encontrados else 0

                registros.append({
                    "UF": uf.upper(),
                    "Candidato": nome_alvo,
                    "Votos apurados": votos,
                    "Fonte": "TSE",
                })

        except Exception as exc:
            falhas.append(f"{uf.upper()}: {exc}")

    if not registros:
        raise RuntimeError(
            "Não foi possível obter arquivos de resultados. "
            "Confira o caminho e a disponibilidade dos dados do TSE. "
            + " | ".join(falhas[:3])
        )

    return pd.DataFrame(registros), eleicao, falhas


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.title("⚙️ Configuração")

modo = st.sidebar.radio(
    "Modo de operação",
    [
        "Simulador",
        "TSE — 2º turno",
        "TSE — 1º turno",
    ],
)

auto = st.sidebar.checkbox(
    "Atualização automática a cada 20 segundos",
    value=True,
)

progresso_simulado = st.sidebar.slider(
    "Progresso da simulação (%)",
    min_value=0,
    max_value=100,
    value=50,
    step=5,
)

semente = st.sidebar.number_input(
    "Semente da simulação",
    min_value=0,
    value=2026,
    step=1,
)

st.sidebar.caption(
    "No simulador, os dados são artificiais. "
    "A contagem de seções é ilustrativa."
)

st.sidebar.markdown(
    "[Abrir portal oficial de resultados do TSE]"
    "(https://resultados.tse.jus.br/oficial/app/index.html)"
)

# ============================================================
# CABEÇALHO
# ============================================================

st.title("🗳️ Monitor de Urnas — Painel Nacional")
st.caption(
    "Flávio Bolsonaro (PL) × Luiz Inácio Lula da Silva (PT)"
)

if modo == "Simulador":
    df = simulador(progresso_simulado, int(semente))
    df["Fonte"] = "SIMULAÇÃO"

    total_esperado = int(df["Votos esperados (base)"].sum())
    total_apurado = int(
        df["Votos apurados A"].sum() + df["Votos apurados B"].sum()
    )
    total_a = int(df["Votos apurados A"].sum())
    total_b = int(df["Votos apurados B"].sum())

    proj_a = int(df["Projeção A (votos)"].sum())
    proj_b = int(df["Projeção B (votos)"].sum())

    progresso_nacional = pct(
        df["Seções totalizadas (simulação)"].sum(),
        df["Seções estimadas (simulação)"].sum(),
    )

    urnas_texto = "Seções totalizadas (simulação)"

else:
    turno = "2" if "2º" in modo else "1"

    try:
        with st.spinner("Consultando dados do TSE..."):
            dados_tse, eleicao, falhas = buscar_tse(turno)

        st.success(f"Eleição identificada: {eleicao.get('nm', 'TSE')}")

        pivot = dados_tse.pivot_table(
            index="UF",
            columns="Candidato",
            values="Votos apurados",
            aggfunc="sum",
            fill_value=0,
        ).reset_index()

        nome_a = CANDIDATOS["A"]
        nome_b = CANDIDATOS["B"]

        if nome_a not in pivot.columns:
            pivot[nome_a] = 0
        if nome_b not in pivot.columns:
            pivot[nome_b] = 0

        pivot = pivot.rename(columns={
            nome_a: "Votos apurados A",
            nome_b: "Votos apurados B",
        })

        df = pivot.copy()
        df["Fonte"] = "TSE"

        df["Votos esperados (base)"] = df["UF"].map(
            lambda uf: ESTADOS.get(uf, (0, 0, 0))[0]
        )

        # Não inventamos quantidade de seções nem percentual de urnas
        # totalizadas quando esses campos não foram validados na fonte.
        df["Seções estimadas (simulação)"] = 0
        df["Seções totalizadas (simulação)"] = 0
        df["Progresso (%)"] = 0.0
        df["Projeção A (votos)"] = df["Votos apurados A"]
        df["Projeção B (votos)"] = df["Votos apurados B"]

        total_esperado = int(df["Votos esperados (base)"].sum())
        total_apurado = int(
            df["Votos apurados A"].sum() + df["Votos apurados B"].sum()
        )
        total_a = int(df["Votos apurados A"].sum())
        total_b = int(df["Votos apurados B"].sum())

        # Sem o campo oficial validado de seções totalizadas,
        # não exibimos uma porcentagem inventada.
        progresso_nacional = None
        proj_a = total_a
        proj_b = total_b
        urnas_texto = "Seções totalizadas: campo a validar"

        if falhas:
            with st.expander(f"Consultas sem sucesso: {len(falhas)}"):
                for falha in falhas:
                    st.write(f"- {falha}")

    except Exception as exc:
        st.error(f"Falha na consulta ao TSE: {exc}")
        st.info(
            "Você pode selecionar Simulador para testar a interface. "
            "Não foram substituídos dados oficiais indisponíveis "
            "por números simulados."
        )
        st.stop()

# ============================================================
# PAINEL NACIONAL EM DESTAQUE
# ============================================================

st.divider()
st.header("🇧🇷 Consolidado nacional")

if progresso_nacional is None:
    progresso_label = "Não disponível"
else:
    progresso_label = f"{progresso_nacional:.2f}%"

c1, c2, c3, c4 = st.columns(4)

c1.metric("Votos apurados", fmt(total_apurado))
c2.metric("Progresso da apuração", progresso_label)
c3.metric("Votos esperados (base)", fmt(total_esperado))
c4.metric("Última consulta", datetime.now().strftime("%H:%M:%S"))

st.subheader("Votos por candidato")

ca, cb = st.columns(2)

ca.metric(
    "Flávio Bolsonaro (PL)",
    fmt(total_a),
    f"{pct(total_a, total_a + total_b):.2f}% dos votos exibidos"
)

cb.metric(
    "Luiz Inácio Lula da Silva (PT)",
    fmt(total_b),
    f"{pct(total_b, total_a + total_b):.2f}% dos votos exibidos"
)

st.subheader("Projeção estimada — baseada nos parâmetros do modelo")

pa, pb = st.columns(2)

pa.metric("Flávio Bolsonaro — estimativa", fmt(proj_a))
pb.metric("Lula — estimativa", fmt(proj_b))

st.caption(
    "A estimativa do simulador usa os parâmetros cadastrados. "
    "No modo TSE, a projeção permanece igual aos votos recuperados "
    "até que a integração com os campos oficiais de totalização "
    "e votos restantes seja validada."
)

# ============================================================
# TABELA ESTADUAL
# ============================================================

st.divider()
st.header("📍 Acompanhamento por estado")

if modo == "Simulador":
    tabela = df[[
        "UF",
        "Votos esperados (base)",
        "Seções estimadas (simulação)",
        "Seções totalizadas (simulação)",
        "Progresso (%)",
        "Votos apurados A",
        "Votos apurados B",
        "Projeção A (votos)",
        "Projeção B (votos)",
    ]].copy()

    tabela = tabela.rename(columns={
        "Votos apurados A": "Flávio — votos simulados",
        "Votos apurados B": "Lula — votos simulados",
        "Projeção A (votos)": "Flávio — projeção simulada",
        "Projeção B (votos)": "Lula — projeção simulada",
    })

else:
    tabela = df.copy()

    tabela = tabela.rename(columns={
        "Votos apurados A": "Flávio — votos recuperados",
        "Votos apurados B": "Lula — votos recuperados",
        "Projeção A (votos)": "Flávio — projeção",
        "Projeção B (votos)": "Lula — projeção",
    })

st.dataframe(
    tabela,
    use_container_width=True,
    hide_index=True,
)

st.download_button(
    "⬇️ Exportar tabela para CSV",
    data=tabela.to_csv(index=False).encode("utf-8-sig"),
    file_name="monitor_urnas.csv",
    mime="text/csv",
)

# ============================================================
# HISTÓRICO DAS CONSULTAS DURANTE A SESSÃO
# ============================================================

if "historico" not in st.session_state:
    st.session_state.historico = []

st.session_state.historico.append({
    "Horário": datetime.now().strftime("%H:%M:%S"),
    "Modo": modo,
    "Votos apurados": total_apurado,
    "Flávio — votos": total_a,
    "Lula — votos": total_b,
    "Progresso (%)": (
        round(progresso_nacional, 2)
        if progresso_nacional is not None
        else None
    ),
})

st.session_state.historico = st.session_state.historico[-100:]

with st.expander("🕒 Histórico das atualizações nesta sessão"):
    st.dataframe(
        pd.DataFrame(st.session_state.historico),
        use_container_width=True,
        hide_index=True,
    )

st.caption(
    "Os parâmetros originais são referências do simulador. "
    "O número de seções totalizadas e o percentual oficial da apuração "
    "devem vir dos campos próprios publicados pelo TSE. "
    "A atualização automática depende de uma versão do Streamlit "
    "compatível com st.fragment."
)

# Atualização automática apenas para o modo TSE.
if auto and modo != "Simulador" and hasattr(st, "fragment"):
    st.info(
        "Atualização automática habilitada: o painel fará nova consulta "
        "a cada 20 segundos."
    )
