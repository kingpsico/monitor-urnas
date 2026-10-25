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
import math
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

REGIOES = {
    "Norte": ["AC", "AP", "AM", "PA", "RO", "RR", "TO"],
    "Nordeste": ["AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"],
    "Centro-Oeste": ["DF", "GO", "MT", "MS"],
    "Sudeste": ["ES", "MG", "RJ", "SP"],
    "Sul": ["PR", "RS", "SC"],
    "Exterior": ["ZZ"],
}
REGIAO_DE = {uf: r for r, ufs in REGIOES.items() for uf in ufs}
MIN_PROGRESSO = 0.01  # estado só entra no cálculo de "desvio" com >= 1% das seções
CONFIANCA = {"Baixa (dados reais pesam mais)": 0.3, "Média": 0.6, "Alta (previsão pesa mais)": 1.2}
BASES = ["Minha previsão", "Resultado real do 1º turno", "Média das duas"]


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


def carregar_r1(cache):
    """Resultado REAL do 1º turno por unidade (dois finalistas). Guardado em memória."""
    with cache["lock"]:
        r1 = cache.setdefault("r1", {})
        faltam = [u for u in UNIDADES if u not in r1]
        ultima = cache.get("r1_tentativa", 0)
        if faltam and time.time() - ultima < 120:
            return dict(r1)
        if faltam:
            cache["r1_tentativa"] = time.time()

    if faltam:
        def tarefa(uf):
            try:
                d = consultar(uf, ELEICAO_1T, cache)
                if d["lula_real"] + d["flavio_real"] > 0:
                    return uf, {"a": d["lula_real"], "b": d["flavio_real"]}
            except Exception:
                pass
            return uf, None

        with ThreadPoolExecutor(max_workers=8) as ex:
            for uf, val in ex.map(tarefa, faltam):
                if val:
                    with cache["lock"]:
                        r1[uf] = val
    with cache["lock"]:
        return dict(r1)


# ==========================================================
# BASES DE PREVISÃO (previsão do usuário + 1º turno real)
# ==========================================================
def logit(p):
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def inv_logit(x):
    return 1 / (1 + math.exp(-x))


def construir_bases(escala, r1, modo_base):
    """
    Para cada unidade: T0 = total de votos esperado, s0 = % esperado de Lula
    entre os dois candidatos (fração 0-1).
    """
    bases = {}
    for uf, prev in PREVISAO_ESTADOS.items():
        s_user = normalizar(prev["pct_a"], prev["pct_b"])[0] / 100
        s_r1 = None
        if uf in r1:
            s_r1 = r1[uf]["a"] / (r1[uf]["a"] + r1[uf]["b"])
        if modo_base == "Resultado real do 1º turno" and s_r1 is not None:
            s0 = s_r1
        elif modo_base == "Média das duas" and s_r1 is not None:
            s0 = (s_user + s_r1) / 2
        else:
            s0 = s_user
        bases[uf] = {
            "T0": prev["votos_esperados"] * escala,
            "s0": s0,
            "s_user": s_user,
            "s_r1": s_r1,
        }
    if "ZZ" in r1:
        tot = r1["ZZ"]["a"] + r1["ZZ"]["b"]
        s = r1["ZZ"]["a"] / tot
        bases["ZZ"] = {"T0": float(tot), "s0": s, "s_user": None, "s_r1": s}
    return bases


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

    r1 = carregar_r1(cache)

    if nacional is None:
        return {
            "status": "aguardando",
            "eleicao": codigos[0],
            "nacional": None,
            "unidades": {u: None for u in UNIDADES},
            "erros": motivos,
            "r1": r1,
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
    if nacional["pct_secoes"] <= 0 and not tem_voto:
        status = "aguardando"
    elif nacional["pct_secoes"] >= 99.99:
        status = "concluido"
    else:
        status = "apurando"
    return {
        "status": status,
        "eleicao": eleicao,
        "nacional": nacional,
        "unidades": unidades,
        "erros": erros,
        "r1": r1,
    }


def _hash_uf(uf):
    return (sum(ord(c) for c in uf) * 37 % 100) / 100  # 0..1 determinístico


def carregar_simulado(progresso, desvio_pp):
    """Cada estado abre num ritmo diferente e tem um desvio próprio (fictício)."""
    unidades = {}
    for uf, base in PREVISAO_ESTADOS.items():
        pa = normalizar(base["pct_a"], base["pct_b"])[0]
        h = _hash_uf(uf)
        ruido = (h - 0.5) * 3.0  # ±1,5 p.p.
        sa_real = min(max(pa + desvio_pp + ruido, 1.0), 99.0) / 100
        prog_uf = 100.0 if progresso >= 100 else min(99.9, max(0.0, progresso * (0.5 + h)))
        total = base["votos_esperados"] * 0.93 * prog_uf / 100  # comparecimento 7% menor
        unidades[uf] = {
            "uf": uf,
            "lula_real": int(total * sa_real),
            "flavio_real": int(total * (1 - sa_real)),
            "pct_secoes": prog_uf,
            "secoes_total": 1000,
            "secoes_apuradas": int(10 * prog_uf),
            "atualizado_em": f"SIMULADO {progresso}",
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
        "atualizado_em": f"SIMULADO
