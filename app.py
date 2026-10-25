```python
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st

# ==========================================================
# MOTOR ELEITORAL 2026
# A = Lula | B = Flávio Bolsonaro
# Dados oficiais: arquivos JSON públicos do TSE
# ==========================================================

st.set_page_config(
    page_title="Motor Eleitoral 2026",
    page_icon="🗳️",
    layout="wide",
)

# Eleição presidencial do segundo turno de 2026.
BASE_TSE = "https://resultados.tse.jus.br/oficial/ele2026/6258/dados"
COD_ELEICAO = "006258"
COD_CARGO = "0001"
INTERVALO_ATUALIZACAO = 20

CANDIDATOS = {
    "A": {
        "numero": "13",
        "nome": "Luiz Inácio Lula da Silva",
        "curto": "Lula",
        "partido": "PT",
    },
    "B": {
        "numero": "22",
        "nome": "Flávio Bolsonaro",
        "curto": "Flávio Bolsonaro",
        "partido": "PL",
    },
}

# ==========================================================
# PREVISÃO INICIAL INFORMADA PELO USUÁRIO
# A = Lula | B = Flávio Bolsonaro
# ==========================================================

PREVISAO_ESTADOS = {
    "SP": {"votos_esperados": 28_200_000, "pct_a": 43.0, "pct_b": 52.0},
    "MG": {"votos_esperados": 12_000_000, "pct_a": 49.0, "pct_b": 50.0},
    "RJ": {"votos_esperados": 9_500_000, "pct_a": 42.0, "pct_b": 53.0},
    "BA": {"votos_esperados": 9_000_000, "pct_a": 66.5, "pct_b": 33.0},
    "RS": {"votos_esperados": 7_500_000, "pct_a": 42.0, "pct_b": 55.6},
    "PR": {"votos_esperados": 7_500_000, "pct_a": 37.0, "pct_b": 63.0},
    "PE": {"votos_esperados": 5_500_000, "pct_a": 65.0, "pct_b": 35.0},
    "CE": {"votos_esperados": 5_450_000, "pct_a": 66.0, "pct_b": 34.0},
    "PA": {"votos_esperados": 5_050_000, "pct_a": 54.0, "pct_b": 46.0},
    "MA": {"votos_esperados": 4_000_000, "pct_a": 67.0, "pct_b": 33.0},
    "SC": {"votos_esperados": 4_900_000, "pct_a": 31.0, "pct_b": 69.0},
    "GO": {"votos_esperados": 4_350_000, "pct_a": 41.0, "pct_b": 59.0},
    "PB": {"votos_esperados": 2_672_000, "pct_a": 64.0, "pct_b": 36.0},
    "RN": {"votos_esperados": 2_248_000, "pct_a": 63.0, "pct_b": 37.0},
    "AL": {"votos_esperados": 1_940_000, "pct_a": 58.0, "pct_b": 42.0},
    "PI": {"votos_esperados": 2_180_000, "pct_a": 74.0, "pct_b": 26.0},
    "MT": {"votos_esperados": 2_410_000, "pct_a": 33.0, "pct_b": 66.5},
    "DF": {"votos_esperados": 1_921_000, "pct_a": 38.0, "pct_b": 57.0},
    "ES": {"votos_esperados": 2_520_000, "pct_a": 42.0, "pct_b": 57.0},
    "AM": {"votos_esperados": 2_190_000, "pct_a": 51.0, "pct_b": 48.5},
    "MS": {"votos_esperados": 1_730_000, "pct_a": 38.0, "pct_b": 62.0},
    "SE": {"votos_esperados": 1_360_000, "pct_a": 64.0, "pct_b": 36.0},
    "RO": {"votos_esperados": 1_112_000, "pct_a": 27.0, "pct_b": 72.0},
    "TO": {"votos_esperados": 970_000, "pct_a": 48.0, "pct_b": 51.0},
    "AC": {"votos_esperados": 545_000, "pct_a": 27.5, "pct_b": 65.0},
    "AP": {"votos_esperados": 535_000, "pct_a": 49.0, "pct_b": 48.5},
    "RR": {"votos_esperados": 333_000, "pct_a": 26.0, "pct_b": 73.0},
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 MotorEleitoral/2026",
    "Accept": "application/json",
}


def numero_inteiro(valor):
    try:
        return int(float(str(valor or "0").replace(",", ".")))
    except (ValueError, TypeError):
        return 0


def numero_decimal(valor):
    try:
        return float(str(valor or "0").replace(",", "."))
    except (ValueError, TypeError):
        return 0.0


def formatar_numero(valor):
    return f"{int(round(valor)):,}".replace(",", ".")


def formatar_percentual(valor):
    return f"{valor:.2f}%".replace(".", ",")


def normalizar_percentuais(pct_a, pct_b):
    total = pct_a + pct_b
    if total <= 0:
        return 50.0, 50.0
    return pct_a / total * 100, pct_b / total * 100


# ==========================================================
# CONSULTA AOS ARQUIVOS PÚBLICOS DO TSE
# ==========================================================

def url_resultado(abrangencia):
    uf = abrangencia.lower()
    return (
        f"{BASE_TSE}/{uf}/"
        f"{uf}-c{COD_CARGO}-e{COD_ELEICAO}-u.json"
    )


@st.cache_data(ttl=15, show_spinner=False)
def baixar_json(url):
    resposta = requests.get(
        url,
        headers=HEADERS,
        timeout=15,
    )
    resposta.raise_for_status()
    return resposta.json()


def extrair_candidatos(objeto):
    """
    Os candidatos aparecem aninhados em estruturas de cargo,
    agrupamentos, partidos e listas 'cand'.
    Percorre o JSON e procura os números 13 e 22.
    """
    encontrados = {}

    def percorrer(no):
        if isinstance(no, dict):
            numero = str(no.get("n", "")).strip()
            nome = str(no.get("nm", "")).upper()
            nome_urna = str(no.get("nmu", "")).upper()

            if numero == "13" and (
                "LULA" in nome or "LULA" in nome_urna
            ):
                encontrados["A"] = {
                    "votos": numero_inteiro(no.get("vap")),
                    "percentual_tse": numero_decimal(no.get("pvap")),
                    "nome": no.get("nmu") or no.get("nm") or "Lula",
                }

            elif numero == "22" and (
                "FLAVIO" in nome
                or "FLÁVIO" in nome
                or "FLAVIO" in nome_urna
                or "FLÁVIO" in nome_urna
            ):
                encontrados["B"] = {
                    "votos": numero_inteiro(no.get("vap")),
                    "percentual_tse": numero_decimal(no.get("pvap")),
                    "nome": no.get("nmu") or no.get("nm") or "Flávio Bolsonaro",
                }

            for valor in no.values():
                percorrer(valor)

        elif isinstance(no, list):
            for item in no:
                percorrer(item)

    percorrer(objeto)
    return encontrados


def extrair_resumo(objeto):
    secoes = objeto.get("s", {}) or {}
    eleitorado = objeto.get("e", {}) or {}
    votos = objeto.get("v", {}) or {}

    return {
        "secoes_total": numero_inteiro(secoes.get("ts")),
        "secoes_apuradas": numero_inteiro(secoes.get("st")),
        "pct_secoes": numero_decimal(secoes.get("pst")),
        "eleitorado_total": numero_inteiro(eleitorado.get("te")),
        "votos_validos": numero_inteiro(votos.get("vvc")),
        "atualizado_em": (
            f"{objeto.get('dg', '')} {objeto.get('hg', '')}".strip()
        ),
        "status_dados": objeto.get("dv", ""),
    }


def consultar_abrangencia(uf):
    url = url_resultado(uf)
    objeto = baixar_json(url)
    candidatos = extrair_candidatos(objeto)
    resumo = extrair_resumo(objeto)

    if "A" not in candidatos or "B" not in candidatos:
        raise ValueError(
            f"Os candidatos 13 e 22 não foram reconhecidos no arquivo de {uf}."
        )

    return {
        "uf": uf,
        "lula_real": candidatos["A"]["votos"],
        "flavio_real": candidatos["B"]["votos"],
        "url": url,
        **resumo,
    }


# ==========================================================
# MOTOR DE PROJEÇÃO
# Compara a previsão-base com os dados reais disponíveis.
# ==========================================================

def projetar_estado(dados):
    uf = dados["uf"]
    base = PREVISAO_ESTADOS[uf]

    pct_a_base, pct_b_base = normalizar_percentuais(
        base["pct_a"],
        base["pct_b"],
    )

    total_previsto = base["votos_esperados"]
    previsao_a = total_previsto * pct_a_base / 100
    previsao_b = total_previsto * pct_b_base / 100

    real_a = max(0, dados["lula_real"])
    real_b = max(0, dados["flavio_real"])
    real_dois = real_a + real_b

    progresso = max(0.0, min(100.0, dados["pct_secoes"]))

    if progresso <= 0 or real_dois <= 0:
        proj_a = previsao_a
        proj_b = previsao_b
        metodo = "Previsão-base: apuração ainda sem dados úteis"

    elif progresso >= 99.99:
        # Seções praticamente totalizadas: usa a votação real.
        proj_a = float(real_a)
        proj_b = float(real_b)
        metodo = "Votação real: totalização praticamente concluída"

    else:
        # A previsão estadual é uma estimativa de escala, não um
        # total oficial de votos válidos. Usa-se o progresso das
        # seções como aproximação do avanço da apuração.
        total_final_estimado = max(total_previsto, real_dois)
        total_restante_estimado = max(
            0.0,
            total_final_estimado - real_dois,
        )

        share_a_real = real_a / real_dois
        share_b_real = real_b / real_dois

        # A influência dos dados reais cresce com a apuração.
        peso_real = min(0.95, max(0.10, progresso / 100))

        share_a = (
            (1 - peso_real) * pct_a_base / 100
            + peso_real * share_a_real
        )
        share_b = (
            (1 - peso_real) * pct_b_base / 100
            + peso_real * share_b_real
        )

        soma_shares = share_a + share_b
        if soma_shares > 0:
            share_a /= soma_shares
            share_b /= soma_shares

        proj_a = real_a + total_restante_estimado * share_a
        proj_b = real_b + total_restante_estimado * share_b
        metodo = "Votos reais + previsão ajustada"

    total_projetado = proj_a + proj_b

    pct_proj_a = proj_a / total_projetado * 100 if total_projetado else 0
    pct_proj_b = proj_b / total_projetado * 100 if total_projetado else 0

    return {
        **dados,
        "votos_esperados": total_previsto,
        "pct_a_inicial": base["pct_a"],
        "pct_b_inicial": base["pct_b"],
        "proj_lula": proj_a,
        "proj_flavio": proj_b,
        "pct_proj_lula": pct_proj_a,
        "pct_proj_flavio": pct_proj_b,
        "metodo_projecao": metodo,
    }


def coletar_estados():
    resultados = []
    erros = []

    for uf in PREVISAO_ESTADOS:
        try:
            resultados.append(
                projetar_estado(consultar_abrangencia(uf))
            )
        except Exception as erro:
            erros.append(f"{uf}: {erro}")

    return pd.DataFrame(resultados), erros


# ==========================================================
# INTERFACE
# ==========================================================

st.title("🗳️ Motor Eleitoral 2026")
st.caption(
    "A = Lula (PT) | B = Flávio Bolsonaro (PL)"
)

st.info(
    "O motor compara a previsão inicial de cada estado com os "
    "dados oficiais disponíveis e recalcula as projeções. "
    "As projeções são estimativas, não resultados oficiais."
)

with st.sidebar:
    st.header("Painel de controle")
    modo = st.radio(
        "Modo",
        ["Dados oficiais do TSE", "Simulador de teste"],
    )
    st.write("Intervalo de atualização: 20 segundos")
    st.write("Abrangência: 27 unidades da Federação")
    st.markdown(
        "[Consultar portal oficial do TSE](https://resultados.tse.jus.br/)"
    )


def exibir_painel():
    agora = datetime.now(
        ZoneInfo("America/Sao_Paulo")
    ).strftime("%d/%m/%Y %H:%M:%S")

    st.caption(f"Última atualização do painel: {agora}")

    if modo == "Simulador de teste":
        st.warning(
            "MODO SIMULADOR: os números abaixo são fictícios "
            "e não representam uma apuração oficial."
        )

        progresso = st.slider(
            "Progresso fictício da apuração",
            min_value=0,
            max_value=100,
            value=35,
            step=5,
        )

        linhas = []

        for uf, base in PREVISAO_ESTADOS.items():
            pct_a, pct_b = normalizar_percentuais(
                base["pct_a"], base["pct_b"]
            )

            # Valores sintéticos apenas para testar a interface.
            total_teste = base["votos_esperados"] * progresso / 100

            dados = {
                "uf": uf,
                "lula_real": int(total_teste * pct_a / 100),
                "flavio_real": int(total_teste * pct_b / 100),
                "pct_secoes": float(progresso),
                "secoes_total": 1000,
                "secoes_apuradas": int(1000 * progresso / 100),
                "eleitorado_total": base["votos_esperados"],
                "votos_validos": int(total_teste),
                "atualizado_em": "SIMULADO",
                "status_dados": "SIMULADO",
                "url": "",
            }

            linhas.append(projetar_estado(dados))

        df = pd.DataFrame(linhas)
        erros = []
        pct_nacional = float(progresso)
        lula_real_nacional = int(df["lula_real"].sum())
        flavio_real_nacional = int(df["flavio_real"].sum())
        secoes_total_nacional = int(df["secoes_total"].sum())
        secoes_apuradas_nacional = int(df["secoes_apuradas"].sum())
        url_nacional = ""

    else:
        # O resultado nacional é a fonte de referência para o
        # percentual oficial de seções e os totais nacionais.
        try:
            nacional = consultar_abrangencia("BR")
        except Exception as erro:
            st.error(
                "Não foi possível ler o arquivo nacional do TSE. "
                "Nenhum resultado simulado será apresentado como oficial."
            )
            st.code(str(erro))
            st.link_button(
                "Abrir resultados oficiais",
                "https://resultados.tse.jus.br/",
            )
            return

        df, erros = coletar_estados()

        if df.empty:
            st.error(
                "Nenhum arquivo estadual foi lido com sucesso. "
                "Confira os arquivos e a conectividade do TSE."
            )
            if erros:
                st.code("\n".join(erros[:10]))
            st.link_button(
                "Abrir resultados oficiais",
                "https://resultados.tse.jus.br/",
            )
            return

        pct_nacional = nacional["pct_secoes"]
        lula_real_nacional = nacional["lula_real"]
        flavio_real_nacional = nacional["flavio_real"]
        secoes_total_nacional = nacional["secoes_total"]
        secoes_apuradas_nacional = nacional["secoes_apuradas"]
        url_nacional = nacional["url"]

    # ------------------------------------------------------
    # INDICADORES NACIONAIS
    # ------------------------------------------------------

    st.subheader("1. Consolidado nacional")

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "Seções apuradas",
        formatar_percentual(pct_nacional),
        f"{formatar_numero(secoes_apuradas_nacional)} de "
        f"{formatar_numero(secoes_total_nacional)}",
    )

    c2.metric(
        "Lula — votos reais",
        formatar_numero(lula_real_nacional),
    )

    c3.metric(
        "Flávio — votos reais",
        formatar_numero(flavio_real_nacional),
    )

    c4.metric(
        "Estados com dados recebidos",
        f"{len(df)} de 27",
    )

    # ------------------------------------------------------
    # PROJEÇÃO NACIONAL
    # ------------------------------------------------------

    st.subheader("2. Projeção final do motor")

    total_a = float(df["proj_lula"].sum())
    total_b = float(df["proj_flavio"].sum())
    total_projetado = total_a + total_b

    pct_a = total_a / total_projetado * 100 if total_projetado else 0
    pct_b = total_b / total_projetado * 100 if total_projetado else 0
    diferenca = abs(total_a - total_b)

    p1, p2, p3 = st.columns(3)

    p1.metric(
        "Lula — projeção",
        formatar_numero(total_a),
        formatar_percentual(pct_a),
    )

    p2.metric(
        "Flávio Bolsonaro — projeção",
        formatar_numero(total_b),
        formatar_percentual(pct_b),
    )

    if total_a > total_b:
        lider = "Lula à frente na projeção"
    elif total_b > total_a:
        lider = "Flávio à frente na projeção"
    else:
        lider = "Empate na projeção"

    p3.metric(
        "Diferença projetada",
        formatar_numero(diferenca),
        lider,
    )

    st.caption(
        "Os percentuais da projeção são calculados sobre a soma "
        "projetada dos votos dos dois candidatos. Não são percentuais "
        "oficiais do TSE. A previsão inicial fornecida é usada como "
        "referência e é ajustada conforme os dados reais chegam."
    )

    # ------------------------------------------------------
    # TABELA ESTADUAL
    # ------------------------------------------------------

    st.subheader("3. Acompanhamento dos 27 estados")

    colunas = [
        "uf",
        "votos_esperados",
        "pct_secoes",
        "secoes_apuradas",
        "secoes_total",
        "lula_real",
        "flavio_real",
        "pct_a_inicial",
        "pct_b_inicial",
        "proj_lula",
        "pct_proj_lula",
        "proj_flavio",
        "pct_proj_flavio",
    ]

    tabela = df[colunas].copy()

    tabela.rename(
        columns={
            "uf": "UF",
            "votos_esperados": "Votos previstos base",
            "pct_secoes": "Seções apuradas %",
            "secoes_apuradas": "Seções apuradas",
            "secoes_total": "Total de seções",
            "lula_real": "Lula votos reais",
            "flavio_real": "Flávio votos reais",
            "pct_a_inicial": "Lula previsão inicial %",
            "pct_b_inicial": "Flávio previsão inicial %",
            "proj_lula": "Lula projeção votos",
            "pct_proj_lula": "Lula projeção %",
            "proj_flavio": "Flávio projeção votos",
            "pct_proj_flavio": "Flávio projeção %",
        },
        inplace=True,
    )

    colunas_inteiras = [
        "Votos previstos base",
        "Seções apuradas",
        "Total de seções",
        "Lula votos reais",
        "Flávio votos reais",
        "Lula projeção votos",
        "Flávio projeção votos",
    ]

    for coluna in colunas_inteiras:
        tabela[coluna] = (
            tabela[coluna].fillna(0).round(0).astype("int64")
        )

    tabela = tabela.sort_values("UF")

    st.dataframe(
        tabela,
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "📥 Baixar tabela em CSV",
        data=tabela.to_csv(index=False).encode("utf-8-sig"),
        file_name="motor_eleitoral_2026.csv",
        mime="text/csv",
    )

    if erros:
        with st.expander(
            f"Estados com falha na consulta ({len(erros)})"
        ):
            st.write("\n".join(erros))

    if url_nacional:
        st.caption(f"Arquivo nacional consultado: {url_nacional}")

    st.caption(
        "Fonte dos resultados oficiais: TSE. "
        "Este aplicativo é independente e não substitui a divulgação oficial."
    )


# Atualização automática enquanto a sessão do app estiver ativa.
if hasattr(st, "fragment"):
    @st.fragment(run_every=INTERVALO_ATUALIZACAO)
    def painel_automatico():
        exibir_painel()

    painel_automatico()
else:
    st.error(
        "A versão instalada do Streamlit não suporta atualização "
        "automática por fragmentos. Atualize a dependência Streamlit."
    )
    exibir_painel()
```
