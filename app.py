import random
from datetime import datetime
from typing import Any, Dict, List, Tuple

import pandas as pd
import requests
import streamlit as st

# =============================================================================
# MONITOR DE URNAS — TSE + SIMULADOR
# Instalação: pip install -U streamlit pandas requests
# Execução: streamlit run app.py
# =============================================================================

st.set_page_config(
    page_title="Monitor de Urnas — TSE",
    page_icon="🔮",
    layout="wide",
)

TSE_BASE = "https://resultados.tse.jus.br"
TSE_CONFIG_URL = f"{TSE_BASE}/oficial/comum/config/ele-c.json"
POLL_SECONDS = 20
TIMEOUT_SECONDS = 12

# =============================================================================
# PARÂMETROS ORIGINAIS — PRESERVADOS DO CÓDIGO ENVIADO
# Valores de referência para o simulador, não resultados oficiais.
# =============================================================================

DADOS_ESTADOS_1_TURNO = {
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

UFS = list(DADOS_ESTADOS_1_TURNO.keys())

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; MonitorEstatisticoUrnas/1.0)",
    "Accept": "application/json,text/plain,*/*",
})


# =============================================================================
# FUNÇÕES AUXILIARES
# =============================================================================

def numero_tse(valor: Any) -> int:
    if valor is None:
        return 0

    if isinstance(valor, (int, float)):
        return max(0, int(valor))

    texto = str(valor).strip().replace(" ", "")

    if not texto:
        return 0

    try:
        if "," in texto:
            texto = texto.replace(".", "").replace(",", ".")
            return max(0, int(float(texto)))

        if "." in texto:
            texto = texto.replace(".", "")

        return max(0, int(float(texto)))

    except (ValueError, TypeError, OverflowError):
        return 0


def numero_percentual(valor: Any) -> float:
    try:
        resultado = float(str(valor or "0").replace(",", "."))
        return max(0.0, min(100.0, resultado))
    except (TypeError, ValueError):
        return 0.0


def limitar(valor: float, minimo: float, maximo: float) -> float:
    return max(minimo, min(maximo, valor))


def fmt_num(valor: Any) -> str:
    return f"{int(valor):,}".replace(",", ".")


def get_json(url: str) -> dict:
    resposta = SESSION.get(url, timeout=TIMEOUT_SECONDS)
    resposta.raise_for_status()

    dados = resposta.json()

    if not isinstance(dados, dict):
        raise ValueError("A resposta recebida não é um objeto JSON.")

    return dados


@st.cache_data(ttl=300, show_spinner=False)
def obter_configuracao_tse() -> dict:
    return get_json(TSE_CONFIG_URL)


# =============================================================================
# DESCOBERTA DA ELEIÇÃO NA CONFIGURAÇÃO DO TSE
# =============================================================================

def descobrir_eleicoes(config: dict) -> Dict[str, dict]:
    encontradas = {}

    for pleito in config.get("pl", []):
        ciclo = pleito.get("c", "ele2026")

        for eleicao in pleito.get("e", []):
            codigo = str(eleicao.get("cd", ""))
            nome = str(eleicao.get("nm", ""))
            turno = str(eleicao.get("t", ""))

            texto_busca = nome.lower()
            cargos = []

            for abrangencia in eleicao.get("abr", []):
                cargos.extend(abrangencia.get("cp", []))

            presidente = any(
                str(cargo.get("cd", "")) == "1"
                or str(cargo.get("ds", "")).lower() == "presidente"
                for cargo in cargos
            )

            parece_eleicao_geral = (
                "federal" in texto_busca
                or "geral" in texto_busca
                or presidente
            )

            if turno in ("1", "2") and codigo and parece_eleicao_geral:
                encontradas[turno] = {
                    "ciclo": ciclo,
                    "codigo": codigo,
                    "nome": nome or f"Eleição presidencial — {turno}º turno",
                    "turno": turno,
                }

    return encontradas


# =============================================================================
# LEITURA DOS RESULTADOS DO TSE
# =============================================================================

def parse_candidatos(dados: dict) -> List[dict]:
    candidatos = dados.get("cand", [])

    if not isinstance(candidatos, list):
        return []

    resultado = []

    for candidato in candidatos:
        if not isinstance(candidato, dict):
            continue

        nome = str(
            candidato.get(
                "nm",
                candidato.get("nome", candidato.get("nmu", "")),
            )
        ).strip()

        numero = str(
            candidato.get("n", candidato.get("seq", ""))
        ).strip()

        partido = str(
            candidato.get("sgp", candidato.get("partido", ""))
        ).strip()

        votos = numero_tse(
            candidato.get(
                "vap",
                candidato.get("votos", candidato.get("v", 0)),
            )
        )

        if nome or numero:
            resultado.append({
                "nome": nome or f"Candidato {numero}",
                "numero": numero,
                "partido": partido,
                "votos": votos,
            })

    resultado.sort(key=lambda item: item["votos"], reverse=True)

    return resultado


def montar_url_resultado(ciclo: str, codigo_eleicao: str, uf: str) -> str:
    codigo6 = str(codigo_eleicao).zfill(6)
    uf_lower = uf.lower()

    return (
        f"{TSE_BASE}/oficial/{ciclo}/{codigo_eleicao}/dados/"
        f"{uf_lower}/{uf_lower}-c0001-e{codigo6}-u.json"
    )


def buscar_resultados_tse(
    turno: str,
) -> Tuple[Dict[str, dict], dict, List[str], str]:

    config = obter_configuracao_tse()
    eleicoes = descobrir_eleicoes(config)

    if turno not in eleicoes:
        raise RuntimeError(
            f"A configuração do TSE não retornou uma eleição compatível "
            f"com o {turno}º turno. Verifique a configuração oficial."
        )

    eleicao = eleicoes[turno]
    ciclo = eleicao["ciclo"]
    codigo = eleicao["codigo"]

    resultados = {}
    falhas = []

    atualizado_em = datetime.now().astimezone().strftime(
        "%d/%m/%Y %H:%M:%S %Z"
    )

    # Consulta nacional e estadual.
    # A disponibilidade dos arquivos pode variar conforme a eleição.
    for uf in ["BR"] + UFS:
        url = montar_url_resultado(ciclo, codigo, uf)

        try:
            dados = get_json(url)
            candidatos = parse_candidatos(dados)

            if not candidatos:
                falhas.append(
                    f"{uf}: arquivo sem lista de candidatos ou votos."
                )
                continue

            progresso = numero_percentual(
                dados.get("psi", dados.get("progresso", 0))
            )

            resultados[uf] = {
                "uf": uf,
                "nome_eleicao": eleicao["nome"],
                "codigo_eleicao": codigo,
                "ciclo": ciclo,
                "progresso": progresso,
                "votos_apurados_candidatos": sum(
                    candidato["votos"] for candidato in candidatos
                ),
                "candidatos": candidatos,
                "url": url,
            }

        except Exception as exc:
            falhas.append(
                f"{uf}: {type(exc).__name__}: {exc}"
            )

    if not resultados:
        detalhe = " | ".join(falhas[:5])

        raise RuntimeError(
            "Não foi possível recuperar arquivos de resultado do TSE. "
            "Confira o endereço, a disponibilidade dos arquivos e o formato "
            f"dos dados. Detalhes: {detalhe}"
        )

    return resultados, eleicao, falhas, atualizado_em


# =============================================================================
# SIMULADOR ORIGINAL
# =============================================================================

def buscar_dados_simulados(progresso_geral: int) -> Dict[str, dict]:
    rng = random.Random(int(progresso_geral))
    saida = {}

    for uf, base in DADOS_ESTADOS_1_TURNO.items():

        if uf in ["SP", "PR", "SC", "RS"]:
            progresso = min(100.0, progresso_geral * 1.3)

        elif uf in ["BA", "PE", "MA", "PI"]:
            progresso = limitar(
                (progresso_geral - 10) * 1.1,
                0.0,
                100.0,
            )

        else:
            progresso = float(progresso_geral)

        esperados = base["votos_esperados"]
        apurados = int(esperados * progresso / 100)

        pct_a = base["pct_a"]
        pct_b = base["pct_b"]

        if 0 < progresso < 100:
            variacao = rng.uniform(-1.0, 1.0) * (
                1 - progresso / 100
            )

            pct_a = limitar(pct_a + 0.5 + variacao, 0, 100)
            pct_b = limitar(pct_b - 0.5 - variacao, 0, 100)

        soma = pct_a + pct_b or 1

        votos_a = int(apurados * pct_a / soma)
        votos_b = apurados - votos_a

        saida[uf] = {
            "progresso": progresso,
            "votos_esperados": esperados,
            "votos_apurados": apurados,
            "candidatos": [
                {
                    "nome": "Candidato A (simulado)",
                    "numero": "A",
                    "partido": "",
                    "votos": votos_a,
                },
                {
                    "nome": "Candidato B (simulado)",
                    "numero": "B",
                    "partido": "",
                    "votos": votos_b,
                },
            ],
        }

    return saida


# =============================================================================
# MOTOR DE PROJEÇÃO
# =============================================================================

def projetar_estado_real(dado: dict, uf: str) -> List[dict]:
    candidatos = dado["candidatos"]
    soma_votos = sum(candidato["votos"] for candidato in candidatos)

    if soma_votos <= 0:
        return []

    if uf == "BR":
        base_esperada = sum(
            item["votos_esperados"]
            for item in DADOS_ESTADOS_1_TURNO.values()
        )
    else:
        base_esperada = DADOS_ESTADOS_1_TURNO.get(
            uf, {}
        ).get("votos_esperados", 0)

    progresso = dado.get("progresso", 0.0)

    # O percentual de seções totalizadas não equivale exatamente ao percentual
    # dos votos. Por isso, esta estimativa é apenas uma aproximação operacional.
    if 0 < progresso < 100 and base_esperada > soma_votos:
        restantes_estimados = int(
            base_esperada * (1 - progresso / 100)
        )
    else:
        restantes_estimados = 0

    linhas = []

    for candidato in candidatos:
        participacao = candidato["votos"] / soma_votos

        # Distribuição dos votos restantes pela participação atual.
        # É uma projeção simples, não uma previsão estatística validada.
        votos_projetados = (
            candidato["votos"]
            + restantes_estimados * participacao
        )

        linhas.append({
            "UF": uf,
            "Candidato": candidato["nome"],
            "Número": candidato["numero"],
            "Partido": candidato["partido"],
            "Votos apurados": candidato["votos"],
            "Percentual apurado (%)": round(
                participacao * 100, 3
            ),
            "Votos projetados (estimativa)": int(
                round(votos_projetados)
            ),
            "Percentual projetado (%)": round(
                participacao * 100, 3
            ),
            "Progresso TSE (%)": progresso,
        })

    return linhas


def projetar_simulacao(dados: Dict[str, dict]) -> pd.DataFrame:
    linhas = []

    for uf, dado in dados.items():
        candidatos = dado["candidatos"]
        total = sum(c["votos"] for c in candidatos)

        for candidato in candidatos:
            percentual = (
                candidato["votos"] / total * 100
                if total > 0
                else 0
            )

            linhas.append({
                "UF": uf,
                "Candidato": candidato["nome"],
                "Número": candidato["numero"],
                "Partido": candidato["partido"],
                "Votos apurados": candidato["votos"],
                "Percentual apurado (%)": round(percentual, 3),
                "Votos projetados (estimativa)": int(
                    round(
                        dado["votos_esperados"]
                        * candidato["votos"] / total
                    )
                ) if total else 0,
                "Percentual projetado (%)": round(percentual, 3),
                "Progresso TSE (%)": dado["progresso"],
            })

    return pd.DataFrame(linhas)


# =============================================================================
# INTERFACE — INDICADORES, TABELA, GRÁFICOS E EXPORTAÇÃO
# =============================================================================

def renderizar_tabela_e_graficos(
    df: pd.DataFrame,
    subtitulo: str,
):
    st.caption(subtitulo)

    if df.empty:
        st.warning("Ainda não há dados para exibir.")
        return

    total_votos = int(
        df.groupby("UF")["Votos apurados"].sum().sum()
    )

    ufs_carregadas = int(df["UF"].nunique())

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "Abrangências carregadas",
        str(ufs_carregadas),
    )

    c2.metric(
        "Votos de candidatos recuperados",
        fmt_num(total_votos),
    )

    c3.metric(
        "Candidaturas listadas",
        str(len(df)),
    )

    nacional = df[df["UF"] == "BR"]

    if not nacional.empty:
        st.subheader("🇧🇷 Indicadores nacionais")

        ranking_nacional = nacional.sort_values(
            "Votos apurados",
            ascending=False,
        )

        colunas = st.columns(4)

        for indice in range(min(4, len(ranking_nacional))):
            candidato = ranking_nacional.iloc[indice]

            colunas[indice].metric(
                str(candidato["Candidato"]),
                fmt_num(candidato["Votos apurados"]),
                f"{candidato['Percentual apurado (%)']:.2f}%",
            )

    st.subheader("📋 Resultados por estado e candidato")

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        label="⬇️ Baixar resultados em CSV",
        data=df.to_csv(index=False).encode("utf-8-sig"),
        file_name="monitor_urnas_resultados.csv",
        mime="text/csv",
    )

    st.subheader("📊 Comparação de percentuais por candidato")

    ufs_disponiveis = sorted(df["UF"].unique().tolist())

    uf_escolhida = st.selectbox(
        "Selecione a abrangência",
        options=ufs_disponiveis,
        index=0,
        key="uf_grafico",
    )

    recorte = df[df["UF"] == uf_escolhida].copy()

    if not recorte.empty:
        recorte = recorte.sort_values(
            "Votos apurados",
            ascending=False,
        )

        grafico = recorte.set_index("Candidato")[
            ["Percentual apurado (%)"]
        ]

        st.bar_chart(grafico)

    st.subheader("🏆 Ranking nacional consolidado")

    if not nacional.empty:
        nacional = nacional.sort_values(
            "Votos apurados",
            ascending=False,
        )

        st.dataframe(
            nacional[
                [
                    "Candidato",
                    "Número",
                    "Partido",
                    "Votos apurados",
                    "Percentual apurado (%)",
                    "Votos projetados (estimativa)",
                    "Percentual projetado (%)",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info(
            "O arquivo nacional BR não foi recuperado nesta consulta. "
            "Os dados estaduais disponíveis continuam sendo apresentados."
        )


# =============================================================================
# CONFIGURAÇÃO DO PAINEL
# =============================================================================

st.title("🔮 Monitor de Urnas — Apuração e Projeção")
st.caption(
    "Consulta de arquivos públicos do TSE com atualização automática. "
    "A consulta a cada 20 segundos não significa que o TSE publicará "
    "novos números em todas as consultas."
)

st.sidebar.header("⚙️ Configuração")

modo = st.sidebar.radio(
    "Modo de operação",
    [
        "TSE oficial — 2º turno",
        "TSE oficial — 1º turno",
        "Simulador de testes",
    ],
    index=0,
)

progresso_simulado = st.sidebar.slider(
    "Progresso do simulador (%)",
    min_value=0,
    max_value=100,
    value=50,
    step=5,
)

auto_refresh = st.sidebar.checkbox(
    "Atualizar automaticamente a cada 20 segundos",
    value=True,
)

st.sidebar.caption(
    "Os parâmetros estaduais originais foram mantidos no simulador. "
    "Eles não substituem os resultados oficiais."
)

st.sidebar.markdown(
    f"[Portal oficial do TSE]({TSE_BASE}/oficial/app/index.html)"
)

st.sidebar.markdown(
    f"[Configuração eleitoral oficial]({TSE_CONFIG_URL})"
)


# =============================================================================
# EXECUÇÃO DO PAINEL
# =============================================================================

def painel():
    if modo == "Simulador de testes":
        dados_simulados = buscar_dados_simulados(
            progresso_simulado
        )

        df = projetar_simulacao(dados_simulados)

        renderizar_tabela_e_graficos(
            df,
            "Modo de simulação artificial. Os números não são dados oficiais.",
        )

        st.info(
            "O simulador utiliza os parâmetros cadastrados manualmente "
            "no código original."
        )

        return

    turno = "1" if modo.endswith("1º turno") else "2"

    st.subheader(
        f"Apuração oficial — {turno}º turno"
    )

    with st.spinner(
        "Consultando a configuração e os arquivos de resultados do TSE..."
    ):
        try:
            resultados, eleicao, falhas, atualizado_em = (
                buscar_resultados_tse(turno)
            )

            st.success(
                f"Consulta realizada. Eleição identificada: "
                f"{eleicao['nome']}"
            )

            st.caption(
                f"Última consulta: {atualizado_em}"
            )

            st.caption(
                f"Código da eleição: {eleicao['codigo']} | "
                f"Ciclo: {eleicao['ciclo']}"
            )

            st.caption(
                "Os dados são atualizados pelo TSE conforme a totalização. "
                "O aplicativo consulta novamente a fonte a cada 20 segundos "
                "quando a atualização automática está ativada."
            )

            linhas = []

            for uf, dado in resultados.items():
                linhas.extend(
                    projetar_estado_real(dado, uf)
                )

            df = pd.DataFrame(linhas)

            if not df.empty:
                renderizar_tabela_e_graficos(
                    df,
                    "Dados recuperados da fonte consultada. "
                    "As projeções são estimativas do aplicativo, "
                    "não resultados oficiais.",
                )
            else:
                st.warning(
                    "A consulta foi realizada, mas não foram encontrados "
                    "votos de candidatos para exibir."
                )

            if falhas:
                with st.expander(
                    f"⚠️ Arquivos sem dados nesta consulta ({len(falhas)})"
                ):
                    st.write(
                        "Alguns arquivos podem ainda não estar publicados, "
                        "estar indisponíveis ou possuir estrutura diferente."
                    )

                    for falha in falhas:
                        st.write(f"- {falha}")

            st.warning(
                "O percentual de seções totalizadas não é necessariamente "
                "igual ao percentual de votos apurados. A projeção de votos "
                "restantes utiliza uma aproximação baseada nos parâmetros "
                "de referência e não deve ser interpretada como previsão "
                "eleitoral validada."
            )

        except Exception as exc:
            st.error(
                f"Não foi possível consultar os resultados oficiais: {exc}"
            )

            st.info(
                "O aplicativo não substitui dados oficiais ausentes por "
                "resultados simulados. Você pode selecionar o simulador "
                "no menu lateral para testar a interface."
            )


# =============================================================================
# ATUALIZAÇÃO AUTOMÁTICA
# =============================================================================

if hasattr(st, "fragment"):

    @st.fragment(
        run_every=(
            POLL_SECONDS
            if auto_refresh and modo != "Simulador de testes"
            else None
        )
    )
    def painel_atualizavel():
        painel()

    painel_atualizavel()

else:
    st.warning(
        "Sua versão do Streamlit não oferece st.fragment. "
        "Atualize com: pip install -U streamlit"
    )
    painel()


# =============================================================================
# RODAPÉ
# =============================================================================

st.divider()

st.caption(
    "Monitor Estatístico de Urnas | Fonte pretendida: TSE | "
    "Ferramenta experimental de análise. "
    "A disponibilidade dos arquivos oficiais deve ser confirmada durante "
    "a execução."
)
