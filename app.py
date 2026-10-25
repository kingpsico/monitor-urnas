"""
==========================================================
MOTOR ELEITORAL 2026 — 2º TURNO PRESIDENCIAL (25/10/2026)
A = Lula (13, PT)  |  B = Flávio Bolsonaro (22, PL)
Fonte oficial: arquivos JSON públicos do TSE (resultados.tse.jus.br)

O app:
  1. Fica consultando o TSE sozinho (a cada 20 s). Antes da apuração
     mostra "aguardando"; quando os arquivos aparecem, começa sozinho.
  2. Lê os 27 estados + Exterior (ZZ) em paralelo.
  3. Compara a PREVISÃO-BASE de cada estado com os votos reais e
     recalcula a projeção final continuamente.
==========================================================
"""

import json
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Motor Eleitoral 2026", page_icon="🗳️", layout="wide")

# ==========================================================
# CONFIGURAÇÃO
# ==========================================================
TZ = ZoneInfo("America/Sao_Paulo")
BASE_TSE = "https://resultados.tse.jus.br/oficial"
CICLO = "ele2026"
URL_CONFIG = f"{BASE_TSE}/comum/config/ele-c.json"

ELEICAO_2T = 6258  # 2º turno (confirmado no ele-c.json do TSE)
ELEICAO_1T = 6257  # 1º turno (usado no modo ensaio e como base do Exterior)
COD_CARGO = "0001"  # Presidente

INTERVALO_ATUALIZACAO = 20  # segundos
TTL_CACHE = 12  # segundos (cache compartilhado entre visitantes)
INICIO_DIVULGACAO = datetime(2026, 10, 25, 17, 0, tzinfo=TZ)

NUM_A, NUM_B = "13", "22"

MODO_OFICIAL = "Oficial — 2º turno (TSE)"
MODO_ENSAIO = "Ensaio — 1º turno real (teste do app)"
MODO_SIM = "Simulador (números fictícios)"

HEADERS = {"User-Agent": "Mozilla/5.0 MotorEleitoral/2026", "Accept": "application/json"}

# ==========================================================
# PREVISÃO-BASE (informada pelo usuário) — A = Lula | B = Flávio
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
UNIDADES = list(PREVISAO_ESTADOS) + ["ZZ"]  # 27 UFs + Exterior


# ==========================================================
# UTILITÁRIOS
# ==========================================================
def numero_inteiro(valor):
    try:
        return int(float(str(valor if valor is not None else "0").replace(",", ".")))
    except (ValueError, TypeError):
        return 0


def numero_decimal(valor):
    try:
        return float(str(valor if valor is not None else "0").replace(",", "."))
    except (ValueError, TypeError):
        return 0.0


def fmt_num(valor):
    return f"{int(round(valor)):,}".replace(",", ".")


def fmt_pct(valor):
    return f"{valor:.2f}%".replace(".", ",")


def sem_acento(texto):
    return "".join(
        c for c in unicodedata.normalize("NFKD", str(texto)) if not unicodedata.combining(c)
    ).upper()


def normalizar(pa, pb):
    total = pa + pb
    if total <= 0:
        return 50.0, 50.0
    return pa / total * 100, pb / total * 100


# ==========================================================
# DOWNLOAD (cache compartilhado + último dado bom + paralelo)
# ==========================================================
class SemArquivo(Exception):
    """Arquivo ainda não publicado pelo TSE (HTTP 403/404)."""


@st.cache_resource
def _cache_http():
    return {"dados": {}, "ultimo_bom": {}, "lock": threading.Lock()}


def baixar_json(url, cache):
    """Retorna (json, obsoleto). Obsoleto=True se usou o último dado bom."""
    agora = time.time()
    with cache["lock"]:
        item = cache["dados"].get(url)
    if item and agora - item[0] < TTL_CACHE:
        if isinstance(item[1], Exception):
            raise item[1]
        return item[1], item[2]

    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code in (403, 404):
            raise SemArquivo(f"HTTP {resp.status_code}")
        resp.raise_for_status()
        dados = json.loads(resp.content.decode("utf-8-sig"))
    except SemArquivo as erro:
        with cache["lock"]:
            cache["dados"][url] = (agora, erro, False)
        raise
    except Exception as erro:
        # Falha transitória: se já houve leitura boa, mantém ela.
        with cache["lock"]:
            bom = cache["ultimo_bom"].get(url)
            if bom is not None:
                cache["dados"][url] = (agora, bom, True)
                return bom, True
            cache["dados"][url] = (agora, erro, False)
        raise

    with cache["lock"]:
        cache["ultimo_bom"][url] = dados
        cache["dados"][url] = (agora, dados, False)
    return dados, False


# ==========================================================
# LEITURA TOLERANTE DO JSON DO TSE
# ==========================================================
def url_resultado(abrangencia, eleicao):
    uf = abrangencia.lower()
    return f"{BASE_TSE}/{CICLO}/{eleicao}/dados/{uf}/{uf}-c{COD_CARGO}-e{int(eleicao):06d}-u.json"


def achar_chave(obj, chaves, prof_max=3):
    """Procura a 1ª chave (do nível mais raso para o mais fundo) com valor simples."""
    fila = [(obj, 0)]
    while fila:
        no, prof = fila.pop(0)
        if not isinstance(no, dict):
            continue
        for k in chaves:
            v = no.get(k)
            if v is not None and not isinstance(v, (dict, list)):
                return v
        if prof < prof_max:
            fila.extend((v, prof + 1) for v in no.values() if isinstance(v, dict))
    return None


def achar_todos(obj, chave):
    pilha = [obj]
    while pilha:
        no = pilha.pop()
        if isinstance(no, dict):
            if chave in no and not isinstance(no[chave], (dict, list)):
                yield no[chave]
            pilha.extend(v for v in no.values() if isinstance(v, (dict, list)))
        elif isinstance(no, list):
            pilha.extend(v for v in no if isinstance(v, (dict, list)))


def extrair_candidatos(obj):
    """Acha os candidatos 13 e 22 em qualquer nível do JSON."""
    achados = {NUM_A: [], NUM_B: []}
    pilha = [obj]
    while pilha:
        no = pilha.pop()
        if isinstance(no, dict):
            n = str(no.get("n", "")).strip()
            if n in achados and "vap" in no:
                achados[n].append(no)
            pilha.extend(v for v in no.values() if isinstance(v, (dict, list)))
        elif isinstance(no, list):
            pilha.extend(v for v in no if isinstance(v, (dict, list)))

    def escolher(lista, nomes):
        if not lista:
            return None
        preferidos = [
            c
            for c in lista
            if any(x in sem_acento(f"{c.get('nm', '')} {c.get('nmu', '')}") for x in nomes)
        ]
        return max(preferidos or lista, key=lambda c: numero_inteiro(c.get("vap")))

    a = escolher(achados[NUM_A], ("LULA",))
    b = escolher(achados[NUM_B], ("FLAVIO", "BOLSONARO"))
    return a, b


def consultar(uf, eleicao, cache):
    url = url_resultado(uf, eleicao)
    obj, obsoleto = baixar_json(url, cache)
    a, b = extrair_candidatos(obj)
    if a is None or b is None:
        raise ValueError("candidatos 13 e 22 não encontrados no arquivo")

    pst = achar_chave(obj, ["pst"])
    ts = numero_inteiro(achar_chave(obj, ["ts"]))
    st_ = numero_inteiro(achar_chave(obj, ["st"]))
    if pst is not None:
        pct_secoes = numero_decimal(pst)
    elif ts > 0:
        pct_secoes = st_ / ts * 100
    else:
        pct_secoes = 0.0

    dg = achar_chave(obj, ["dg"]) or ""
    hg = achar_chave(obj, ["hg"]) or ""
    return {
        "uf": uf.upper(),
        "lula_real": numero_inteiro(a.get("vap")),
        "flavio_real": numero_inteiro(b.get("vap")),
        "pct_secoes": max(0.0, min(100.0, pct_secoes)),
        "secoes_total": ts,
        "secoes_apuradas": st_,
        "atualizado_em": f"{dg} {hg}".strip(),
        "obsoleto": obsoleto,
        "url": url,
    }


def descobrir_codigos(cache):
    """2º turno = 6258 (confirmado). Também lê o ele-c.json do TSE como segurança."""
    codigos = [ELEICAO_2T]
    try:
        cfg, _ = baixar_json(URL_CONFIG, cache)
        for v in achar_todos(cfg, "cdt2"):
            cod = numero_inteiro(v)
            if cod and cod not in codigos:
                codigos.append(cod)
    except Exception:
        pass
    return codigos[:5]


def prior_exterior(cache):
    """Exterior não tem previsão do usuário: usa o resultado REAL do 1º turno como base."""
    try:
        d = consultar("zz", ELEICAO_1T, cache)
        total = d["lula_real"] + d["flavio_real"]
        if total > 0:
            pa, pb = normalizar(d["lula_real"], d["flavio_real"])
            return {"votos_esperados": total, "pct_a": pa, "pct_b": pb}
    except Exception:
        pass
    return None


# ==========================================================
# CARREGAMENTO (oficial / ensaio / simulador)
# ==========================================================
def carregar_oficial(eleicao_fixa=None):
    cache = _cache_http()
    codigos = [eleicao_fixa] if eleicao_fixa else descobrir_codigos(cache)

    nacional, eleicao, motivos = None, None, []
    for cod in codigos:
        try:
            nacional = consultar("br", cod, cache)
            eleicao = cod
            break
        except SemArquivo as e:
            motivos.append(f"Eleição {cod}: arquivo nacional ainda não publicado ({e})")
        except Exception as e:
            motivos.append(f"Eleição {cod}: {e}")

    prior_zz = prior_exterior(cache)

    if nacional is None:
        return {
            "status": "aguardando",
            "eleicao": codigos[0],
            "nacional": None,
            "unidades": {u: None for u in UNIDADES},
            "erros": motivos,
            "prior_zz": prior_zz,
        }

    def tarefa(uf):
        try:
            return uf, consultar(uf, eleicao, cache), None
        except Exception as e:
            return uf, None, f"{uf}: {e}"

    with ThreadPoolExecutor(max_workers=8) as ex:
        resultados = list(ex.map(tarefa, UNIDADES))

    unidades = {uf: d for uf, d, _ in resultados}
    erros = [e for _, _, e in resultados if e]
    tem_voto = (nacional["lula_real"] + nacional["flavio_real"]) > 0
    status = "aguardando" if (nacional["pct_secoes"] <= 0 and not tem_voto) else (
        "concluido" if nacional["pct_secoes"] >= 99.99 else "apurando"
    )
    return {
        "status": status,
        "eleicao": eleicao,
        "nacional": nacional,
        "unidades": unidades,
        "erros": erros,
        "prior_zz": prior_zz,
    }


def carregar_simulado(progresso, desvio_pp):
    unidades = {}
    for uf, base in PREVISAO_ESTADOS.items():
        pa, _ = normalizar(base["pct_a"], base["pct_b"])
        sa_real = min(max(pa + desvio_pp, 1.0), 99.0) / 100
        total = base["votos_esperados"] * progresso / 100
        unidades[uf] = {
            "uf": uf,
            "lula_real": int(total * sa_real),
            "flavio_real": int(total * (1 - sa_real)),
            "pct_secoes": float(progresso),
            "secoes_total": 1000,
            "secoes_apuradas": int(10 * progresso),
            "atualizado_em": "SIMULADO",
            "obsoleto": False,
            "url": "",
        }
    unidades["ZZ"] = None
    soma_a = sum(u["lula_real"] for u in unidades.values() if u)
    soma_b = sum(u["flavio_real"] for u in unidades.values() if u)
    nacional = {
        "lula_real": soma_a,
        "flavio_real": soma_b,
        "pct_secoes": float(progresso),
        "secoes_total": 27_000,
        "secoes_apuradas": int(270 * progresso),
        "atualizado_em": "SIMULADO",
        "url": "",
    }
    status = "aguardando" if progresso <= 0 else ("concluido" if progresso >= 100 else "apurando")
    return {
        "status": status,
        "eleicao": None,
        "nacional": nacional,
        "unidades": unidades,
        "erros": [],
        "prior_zz": None,
    }


# ==========================================================
# MOTOR DE PROJEÇÃO
# ==========================================================
def projetar(uf, dados, prior, escala=1.0):
    """
    Mistura previsão-base (prior) e votos reais.
      - sem votos apurados  -> previsão pura
      - 100% apurado        -> votos reais
      - entre os dois       -> total final = mistura entre o total previsto e o total
                               extrapolado dos votos reais (votos/progresso);
                               votos restantes divididos por uma média ponderada entre a
                               previsão e o desempenho real, com peso do real = progresso
                               (máx. 95%).
    """
    real_a = max(0, dados["lula_real"]) if dados else 0
    real_b = max(0, dados["flavio_real"]) if dados else 0
    real_total = real_a + real_b
    p = max(0.0, min(1.0, dados["pct_secoes"] / 100)) if dados else 0.0

    if prior:
        t0 = prior["votos_esperados"] * escala
        sa0n, sb0n = normalizar(prior["pct_a"], prior["pct_b"])
        sa0 = sa0n / 100
    else:
        t0, sa0 = 0.0, 0.5

    if real_total > 0 and p >= 0.9999:
        pa, pb = float(real_a), float(real_b)
        metodo = "Resultado real (totalização concluída)"
    elif p <= 0 or real_total <= 0:
        if prior:
            pa, pb = t0 * sa0, t0 * (1 - sa0)
            metodo = "Previsão-base (sem votos apurados)"
        else:
            pa = pb = 0.0
            metodo = "Sem dados e sem previsão"
    else:
        total_extrap = real_total / p
        sa_obs = real_a / real_total
        if prior:
            w = 0.0 if p < 0.02 else min(0.95, p)
            total_final = (1 - w) * t0 + w * total_extrap
            if p < 0.5:  # trava de segurança no início da apuração
                total_final = min(max(total_final, 0.75 * t0), 1.25 * t0)
            sa_resto = (1 - w) * sa0 + w * sa_obs
            metodo = "Votos reais + previsão ajustada"
        else:
            total_final = total_extrap
            sa_resto = sa_obs
            metodo = "Extrapolação dos votos reais (sem previsão)"
        total_final = max(total_final, real_total)
        resto = total_final - real_total
        pa = real_a + resto * sa_resto
        pb = real_b + resto * (1 - sa_resto)

    total_proj = pa + pb
    pct_a = pa / total_proj * 100 if total_proj else 0.0
    pct_b = pb / total_proj * 100 if total_proj else 0.0
    base_a = normalizar(prior["pct_a"], prior["pct_b"])[0] if prior else None
    lider_base = None
    if prior:
        lider_base = "Lula" if prior["pct_a"] > prior["pct_b"] else "Flávio"
    lider_proj = "Lula" if pa > pb else ("Flávio" if pb > pa else "Empate")

    return {
        "UF": "ZZ (Exterior)" if uf == "ZZ" else uf,
        "uf": uf,
        "votos_previstos": t0,
        "pct_secoes": dados["pct_secoes"] if dados else 0.0,
        "secoes_apuradas": dados["secoes_apuradas"] if dados else 0,
        "secoes_total": dados["secoes_total"] if dados else 0,
        "lula_real": real_a,
        "flavio_real": real_b,
        "pct_a_base": base_a,
        "proj_lula": pa,
        "proj_flavio": pb,
        "pct_proj_lula": pct_a,
        "pct_proj_flavio": pct_b,
        "desvio_lula_pp": (pct_a - base_a) if base_a is not None and total_proj else None,
        "lider_base": lider_base,
        "lider_proj": lider_proj,
        "virou": bool(lider_base and total_proj and lider_proj not in (lider_base, "Empate")),
        "metodo": metodo,
        "sem_dado": dados is None,
        "obsoleto": bool(dados and dados.get("obsoleto")),
    }


@st.cache_resource
def _historico():
    return {"series": {}, "lock": threading.Lock()}


def registrar_historico(chave, nacional, total_a, total_b):
    h = _historico()
    pct_a = total_a / (total_a + total_b) * 100 if (total_a + total_b) else 0
    ponto = {
        "carimbo": nacional.get("atualizado_em", ""),
        "Hora": datetime.now(TZ).strftime("%H:%M:%S"),
        "Seções apuradas %": nacional["pct_secoes"],
        "Lula projeção %": pct_a,
        "Flávio projeção %": 100 - pct_a,
        "Diferença projetada (Lula − Flávio)": total_a - total_b,
    }
    with h["lock"]:
        serie = h["series"].setdefault(chave, [])
        if not serie or serie[-1]["carimbo"] != ponto["carimbo"] or abs(
            serie[-1]["Diferença projetada (Lula − Flávio)"] - ponto["Diferença projetada (Lula − Flávio)"]
        ) > 1:
            serie.append(ponto)
            del serie[:-3000]
        return list(serie)


# ==========================================================
# INTERFACE
# ==========================================================
def mostrar_df(df):
    try:
        st.dataframe(df, width="stretch", hide_index=True)
    except Exception:
        st.dataframe(df, use_container_width=True, hide_index=True)


def painel(modo, escala, prog_sim, desvio_sim):
    agora = datetime.now(TZ)
    st.caption(f"Última atualização do painel: {agora.strftime('%d/%m/%Y %H:%M:%S')} (Brasília)")

    # ---------- carga ----------
    if modo == MODO_SIM:
        dados = carregar_simulado(prog_sim, desvio_sim)
        st.warning("MODO SIMULADOR: números fictícios, sem relação com a apuração oficial.")
    elif modo == MODO_ENSAIO:
        dados = carregar_oficial(ELEICAO_1T)
        st.warning(
            "MODO ENSAIO: usando os dados REAIS (já encerrados) do 1º turno, apenas para "
            "testar o app. Os números NÃO são do 2º turno."
        )
    else:
        dados = carregar_oficial()

    status = dados["status"]
    nacional = dados["nacional"]

    # ---------- faixa de status ----------
    if status == "aguardando":
        if modo == MODO_OFICIAL and agora < INICIO_DIVULGACAO:
            falta = INICIO_DIVULGACAO - agora
            h, resto = divmod(int(falta.total_seconds()), 3600)
            m, s = divmod(resto, 60)
            st.info(
                f"⏳ Aguardando o início da divulgação do TSE (a partir das 17h de 25/10). "
                f"Faltam {h:02d}h{m:02d}min{s:02d}s. O app consulta o TSE sozinho a cada "
                f"{INTERVALO_ATUALIZACAO}s e começa a apuração automaticamente. "
                "Enquanto isso, a projeção abaixo mostra apenas a previsão-base."
            )
        else:
            st.info(
                "⏳ Os arquivos de apuração ainda não foram publicados pelo TSE (ou ainda "
                "sem votos). O app continua tentando automaticamente. A projeção abaixo é "
                "apenas a previsão-base."
            )
    elif status == "apurando":
        st.success("🟢 Apuração em andamento — projeção sendo recalculada em tempo real.")
    else:
        st.success("🏁 Totalização concluída — valores finais baseados nos votos reais.")

    # ---------- projeção por unidade ----------
    linhas = []
    for uf in UNIDADES:
        if uf == "ZZ":
            prior, esc = dados["prior_zz"], 1.0
        else:
            prior, esc = PREVISAO_ESTADOS[uf], escala
        linhas.append(projetar(uf, dados["unidades"].get(uf), prior, esc))
    df = pd.DataFrame(linhas)

    total_a = float(df["proj_lula"].sum())
    total_b = float(df["proj_flavio"].sum())
    total_proj = total_a + total_b
    pct_a = total_a / total_proj * 100 if total_proj else 0
    pct_b = total_b / total_proj * 100 if total_proj else 0
    diferenca = abs(total_a - total_b)

    # ---------- 1. consolidado nacional ----------
    st.subheader("1. Consolidado nacional (votos reais apurados)")
    if nacional:
        real_a, real_b = nacional["lula_real"], nacional["flavio_real"]
        pct_sec = nacional["pct_secoes"]
        sec_ap, sec_tot = nacional["secoes_apuradas"], nacional["secoes_total"]
    else:
        real_a = real_b = 0
        pct_sec, sec_ap, sec_tot = 0.0, 0, 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Seções apuradas",
        fmt_pct(pct_sec),
        f"{fmt_num(sec_ap)} de {fmt_num(sec_tot)}" if sec_tot else None,
    )
    c2.metric("Lula — votos reais", fmt_num(real_a))
    c3.metric("Flávio — votos reais", fmt_num(real_b))
    lidos = int((~df["sem_dado"]).sum())
    c4.metric("Unidades com dados", f"{lidos} de {len(UNIDADES)}")

    if nacional and modo != MODO_SIM:
        soma_real = int(df["lula_real"].sum() + df["flavio_real"].sum())
        nac_total = real_a + real_b
        if nac_total > 0 and abs(soma_real - nac_total) / nac_total > 0.005:
            st.warning(
                f"Atenção: a soma das 28 unidades ({fmt_num(soma_real)} votos) difere do total "
                f"nacional do TSE ({fmt_num(nac_total)}). Pode ser atraso entre arquivos; "
                "se persistir, confira a seção de diagnóstico."
            )

    # ---------- 2. projeção ----------
    st.subheader("2. Projeção final do motor")
    p1, p2, p3 = st.columns(3)
    p1.metric("Lula — projeção", fmt_num(total_a), fmt_pct(pct_a))
    p2.metric("Flávio Bolsonaro — projeção", fmt_num(total_b), fmt_pct(pct_b))
    if total_a > total_b:
        lider = "Lula à frente na projeção"
    elif total_b > total_a:
        lider = "Flávio à frente na projeção"
    else:
        lider = "Empate na projeção"
    p3.metric("Diferença projetada", fmt_num(diferenca), lider)

    a_apurar = max(0.0, total_proj - (real_a + real_b)) if nacional else total_proj
    q1, q2, q3 = st.columns(3)
    q1.metric("Votos a apurar (estimado)", fmt_num(a_apurar))
    q2.metric("Total projetado de votos", fmt_num(total_proj))
    virou = df[df["virou"]]["uf"].tolist()
    q3.metric(
        "Estados que virariam vs. previsão-base",
        str(len(virou)),
        ", ".join(virou) if virou else "nenhum",
        delta_color="off",
    )

    if total_proj and diferenca / total_proj < 0.005:
        st.warning(
            "⚠️ Disputa muito apertada: a diferença projetada é menor que 0,5% dos votos, "
            "dentro da margem de erro do modelo. Não trate como resultado."
        )

    st.caption(
        "Percentuais calculados sobre a soma dos votos dos dois candidatos (27 UFs + Exterior). "
        "Não são percentuais oficiais do TSE. Projeção = estimativa, não resultado oficial."
    )

    # ---------- 3. evolução ----------
    if status != "aguardando" and nacional:
        chave = f"{modo}|{dados['eleicao']}"
        serie = registrar_historico(chave, nacional, total_a, total_b)
        if len(serie) >= 2:
            st.subheader("3. Evolução da projeção")
            dh = pd.DataFrame(serie).set_index("Hora")
            g1, g2 = st.columns(2)
            g1.caption("Projeção % de cada candidato")
            g1.line_chart(dh[["Lula projeção %", "Flávio projeção %"]])
            g2.caption("Diferença projetada em votos (Lula − Flávio)")
            g2.line_chart(dh[["Diferença projetada (Lula − Flávio)"]])

    # ---------- 4. tabela ----------
    st.subheader("4. Acompanhamento por estado")
    tabela = pd.DataFrame(
        {
            "UF": df["UF"],
            "Votos previstos base": df["votos_previstos"].round(0).astype("int64"),
            "Seções apuradas %": df["pct_secoes"].round(2),
            "Seções apuradas": df["secoes_apuradas"],
            "Total de seções": df["secoes_total"],
            "Lula votos reais": df["lula_real"],
            "Flávio votos reais": df["flavio_real"],
            "Lula previsão % (norm.)": df["pct_a_base"].round(2),
            "Lula projeção votos": df["proj_lula"].round(0).astype("int64"),
            "Lula projeção %": df["pct_proj_lula"].round(2),
            "Flávio projeção votos": df["proj_flavio"].round(0).astype("int64"),
            "Flávio projeção %": df["pct_proj_flavio"].round(2),
            "Desvio Lula vs previsão (p.p.)": df["desvio_lula_pp"].astype(float).round(2),
            "Líder previsão": df["lider_base"],
            "Líder projeção": df["lider_proj"],
            "Método": df["metodo"],
        }
    ).sort_values("UF")
    mostrar_df(tabela)

    st.download_button(
        "📥 Baixar tabela em CSV",
        data=tabela.to_csv(index=False).encode("utf-8-sig"),
        file_name="motor_eleitoral_2026.csv",
        mime="text/csv",
    )

    # ---------- diagnóstico ----------
    with st.expander("Diagnóstico técnico"):
        st.write(f"Eleição TSE consultada: **{dados['eleicao']}**")
        if nacional and nacional.get("url"):
            st.write(f"Arquivo nacional: {nacional['url']}")
            st.write(f"Carimbo do TSE: {nacional.get('atualizado_em') or 'n/d'}")
        st.write(f"Unidades com dado desatualizado (usando última leitura boa): "
                 f"{int(df['obsoleto'].sum())}")
        if dados["prior_zz"]:
            st.write("Exterior (ZZ): previsão-base derivada do resultado real do 1º turno.")
        else:
            st.write("Exterior (ZZ): sem previsão-base; projetado só pelos votos reais.")
        if dados["erros"]:
            st.write("Falhas/avisos:")
            st.code("\n".join(dados["erros"][:40]))
        st.write(
            "Unidades sem dado usam a previsão-base na projeção, para que o total nacional "
            "nunca fique incompleto."
        )
    st.caption(
        "Fonte dos resultados oficiais: TSE (resultados.tse.jus.br). Aplicativo independente; "
        "não substitui a divulgação oficial."
    )


def main():
    st.title("🗳️ Motor Eleitoral 2026 — 2º turno")
    st.caption("A = Lula (13, PT)  |  B = Flávio Bolsonaro (22, PL)")

    with st.sidebar:
        st.header("Painel de controle")
        modo = st.radio("Modo", [MODO_OFICIAL, MODO_ENSAIO, MODO_SIM], index=0)
        escala_pct = st.slider(
            "Ajuste dos totais previstos (%)",
            min_value=80,
            max_value=110,
            value=100,
            step=1,
            help="100% = exatamente os totais informados. Mexa só se quiser testar "
            "um cenário de comparecimento menor/maior.",
        )
        prog_sim, desvio_sim = 35, 0.0
        if modo == MODO_SIM:
            prog_sim = st.slider("Progresso fictício da apuração (%)", 0, 100, 35, 5)
            desvio_sim = st.slider(
                "Desvio fictício a favor de Lula (p.p.)", -10.0, 10.0, 0.0, 0.5
            )
        st.write(f"Atualização automática: {INTERVALO_ATUALIZACAO} s")
        st.write("Abrangência: 27 UFs + Exterior")
        st.markdown("[Portal oficial do TSE](https://resultados.tse.jus.br/)")

    escala = escala_pct / 100

    def corpo():
        try:
            painel(modo, escala, prog_sim, desvio_sim)
        except Exception as erro:  # nunca derrubar o painel
            st.error(f"Erro ao atualizar o painel (nova tentativa automática): {erro}")

    fragmento = getattr(st, "fragment", None) or getattr(st, "experimental_fragment", None)
    if fragmento is not None:
        try:
            fragmento(run_every=INTERVALO_ATUALIZACAO)(corpo)()
            return
        except TypeError:
            pass
    # Fallback para versões antigas do Streamlit
    corpo()
    time.sleep(INTERVALO_ATUALIZACAO)
    st.rerun()


main()
