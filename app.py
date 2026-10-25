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
            "atualizado_em": "SIMULADO " + str(progresso),
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
        "atualizado_em": "SIMULADO " + str(progresso),
        "url": "",
    }
    status = "aguardando" if progresso <= 0 else ("concluido" if progresso >= 100 else "apurando")
    return {
        "status": status,
        "eleicao": None,
        "nacional": nacional,
        "unidades": unidades,
        "erros": [],
        "r1": {},
    }


# ==========================================================
# MOTOR DE ANÁLISE E PROJEÇÃO (ativo, estado a estado)
# ==========================================================
# Ideia central:
#  1) Cada estado tem uma BASE (previsão/1º turno): total esperado T0 e % de Lula s0.
#  2) Conforme as urnas abrem, mede-se o DESVIO de cada estado em relação à base
#     (em escala logit, para não estourar 0%/100%) e a razão de COMPARECIMENTO
#     (votos apurados / % de seções, comparado a T0).
#  3) Esses desvios viram um "clima" (swing) NACIONAL e REGIONAL, ponderados pelos
#     votos já apurados e pela abertura de cada estado (estado com mais urnas abertas
#     pesa mais). O próprio estado é excluído do clima que o afeta.
#  4) Para cada estado, o que falta apurar recebe: o desvio do próprio estado (peso w,
#     que cresce com a abertura das urnas) + o clima regional/nacional (peso 1 - w).
#     Assim, estado com 0% apurado já se move pelo que os outros mostram.
#  5) Com 100% apurado, vale só o voto real.
#  O parâmetro m (confiança na previsão) controla a velocidade: w = p / (p + m(1-p)).
def motor(unidades, bases, m):
    info = {}
    for uf in UNIDADES:
        d = unidades.get(uf)
        base = bases.get(uf)
        p = max(0.0, min(1.0, d["pct_secoes"] / 100)) if d else 0.0
        a = max(0, d["lula_real"]) if d else 0
        b = max(0, d["flavio_real"]) if d else 0
        v = a + b
        i = {"uf": uf, "base": base, "p": p, "a": a, "b": b, "v": v, "usavel": False, "w": 0.0}
        if base and d and p >= MIN_PROGRESSO and v > 0:
            w = p / (p + m * (1 - p)) if p < 1 else 1.0
            s_obs = min(max(a / v, 1e-3), 1 - 1e-3)
            i.update(
                usavel=True,
                w=w,
                s_obs=s_obs,
                dev=logit(s_obs) - logit(base["s0"]),
                lr=math.log(min(max((v / p) / base["T0"], 0.5), 1.6)),
                cw=v * w,
            )
        info[uf] = i

    def somar(ufs):
        S = {"cw": 0.0, "cwd": 0.0, "cwlr": 0.0, "v": 0.0, "T0": 0.0}
        for uf in ufs:
            i = info[uf]
            if i["base"]:
                S["T0"] += i["base"]["T0"]
            if i["usavel"]:
                S["cw"] += i["cw"]
                S["cwd"] += i["cw"] * i["dev"]
                S["cwlr"] += i["cw"] * i["lr"]
                S["v"] += i["v"]
        return S

    def sem(S, i):
        R = dict(S)
        if i["base"]:
            R["T0"] -= i["base"]["T0"]
        if i["usavel"]:
            R["cw"] -= i["cw"]
            R["cwd"] -= i["cw"] * i["dev"]
            R["cwlr"] -= i["cw"] * i["lr"]
            R["v"] -= i["v"]
        return R

    def clima(S):
        if S["cw"] <= 1e-9 or S["T0"] <= 0:
            return 0.0, 0.0, 0.0
        P = min(1.0, max(0.0, S["v"] / S["T0"]))
        kappa = P / (P + m * (1 - P)) if P < 1 else 1.0
        return S["cwd"] / S["cw"], S["cwlr"] / S["cw"], kappa

    TOT = somar(UNIDADES)
    REG = {r: somar(ufs) for r, ufs in REGIOES.items()}

    linhas = []
    for uf in UNIDADES:
        i = info[uf]
        base, p, a, b, v = i["base"], i["p"], i["a"], i["b"], i["v"]

        Dn, Ln, kn = clima(sem(TOT, i))
        Dn, Ln = Dn * kn, Ln * kn
        Dr, Lr, kr = clima(sem(REG[REGIAO_DE[uf]], i))
        D_ctx = kr * Dr + (1 - kr) * Dn
        L_ctx = kr * Lr + (1 - kr) * Ln

        s_rest = None
        if base is None:
            # Sem previsão: só extrapola os votos reais (se houver).
            if v > 0 and p > 0:
                total = max(v / p, v)
                s_rest = a / v
                pa, pb = a + (total - v) * s_rest, b + (total - v) * (1 - s_rest)
                metodo = "Extrapolação dos votos reais (sem previsão)"
            else:
                pa = pb = 0.0
                metodo = "Sem dados e sem previsão"
            t0, s0, w_uso, ajuste = 0.0, None, 0.0, None
        elif v > 0 and p >= 0.9999:
            pa, pb = float(a), float(b)
            metodo = "Resultado real (totalização concluída)"
            t0, s0, w_uso, ajuste = base["T0"], base["s0"], 1.0, None
        else:
            t0, s0 = base["T0"], base["s0"]
            if i["usavel"]:
                w = i["w"]
                swing = w * i["dev"] + (1 - w) * D_ctx
                lrf = w * i["lr"] + (1 - w) * L_ctx
                metodo = "Real do estado + clima regional/nacional"
            else:
                w = 0.0
                swing, lrf = D_ctx, L_ctx
                if D_ctx == 0.0 and L_ctx == 0.0:
                    metodo = "Previsão-base (ainda sem urnas no país)"
                else:
                    metodo = "Previsão-base corrigida pelo clima regional/nacional"
            s_rest = inv_logit(logit(s0) + swing)
            total = t0 * math.exp(lrf)
            if p < 0.9:
                total = min(max(total, 0.7 * t0), 1.3 * t0)
            total = max(total, v)
            resto = total - v
            pa = a + resto * s_rest
            pb = b + resto * (1 - s_rest)
            w_uso = w
            ajuste = (s_rest - s0) * 100

        tot_proj = pa + pb
        pct_a = pa / tot_proj * 100 if tot_proj else 0.0
        pct_b = pb / tot_proj * 100 if tot_proj else 0.0
        lider_base = None
        if s0 is not None:
            lider_base = "Lula" if s0 > 0.5 else "Flávio"
        lider_proj = "Lula" if pa > pb else ("Flávio" if pb > pa else "Empate")
        d = unidades.get(uf)
        linhas.append(
            {
                "UF": "ZZ (Exterior)" if uf == "ZZ" else uf,
                "uf": uf,
                "regiao": REGIAO_DE[uf],
                "votos_previstos": t0,
                "pct_secoes": d["pct_secoes"] if d else 0.0,
                "secoes_apuradas": d["secoes_apuradas"] if d else 0,
                "secoes_total": d["secoes_total"] if d else 0,
                "lula_real": a,
                "flavio_real": b,
                "pct_a_base": s0 * 100 if s0 is not None else None,
                "proj_lula": pa,
                "proj_flavio": pb,
                "pct_proj_lula": pct_a,
                "pct_proj_flavio": pct_b,
                "desvio_lula_pp": (pct_a - s0 * 100) if (s0 is not None and tot_proj) else None,
                "ajuste_resto_pp": ajuste,
                "peso_real": w_uso * 100,
                "lider_base": lider_base,
                "lider_proj": lider_proj,
                "virou": bool(lider_base and tot_proj and lider_proj not in (lider_base, "Empate")),
                "metodo": metodo,
                "sem_dado": d is None,
                "obsoleto": bool(d and d.get("obsoleto")),
            }
        )

    # ---- resumo do clima (para o painel) ----
    def resumo(ufs):
        S = somar(ufs)
        if S["cw"] <= 1e-9:
            return None
        dev_pp = sum(
            info[u]["cw"] * (info[u]["s_obs"] - info[u]["base"]["s0"]) * 100
            for u in ufs
            if info[u]["usavel"]
        ) / S["cw"]
        fator = math.exp(S["cwlr"] / S["cw"])
        return {
            "desvio_pp": dev_pp,
            "comparecimento": fator,
            "votos_apurados_pct": S["v"] / S["T0"] * 100 if S["T0"] else 0.0,
        }

    clima_resumo = {"Brasil": resumo(UNIDADES)}
    for r, ufs in REGIOES.items():
        clima_resumo[r] = resumo(ufs)
    return pd.DataFrame(linhas), clima_resumo


@st.cache_resource
def _historico():
    return {"series": {}, "lock": threading.Lock()}


def registrar_historico(chave, nacional, total_a, total_b):
    h = _historico()
    pct_a = total_a / (total_a + total_b) * 100 if (total_a + total_b) else 0
    ponto = {
        "carimbo": nacional.get("atualizado_em", ""),
        "Hora": datetime.now(TZ).strftime("%H:%M:%S"),
        "Seções apuradas %": round(nacional["pct_secoes"], 2),
        "Lula projeção %": pct_a,
        "Flávio projeção %": 100 - pct_a,
        "Diferença projetada (Lula − Flávio)": total_a - total_b,
    }
    with h["lock"]:
        serie = h["series"].setdefault(chave, [])
        k = "Diferença projetada (Lula − Flávio)"
        if not serie or serie[-1]["carimbo"] != ponto["carimbo"] or abs(serie[-1][k] - ponto[k]) > 1:
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


CORES_REGIAO = {
    "Sul": "#1f77b4",  # azul
    "Sudeste": "#ff7f0e",  # laranja
    "Norte": "#2ca02c",  # verde
    "Nordeste": "#d62728",  # vermelho
    "Centro-Oeste": "#9467bd",  # roxo
    "Exterior": "#17becf",  # turquesa
}


def tema_escuro():
    """Detecta o tema do Streamlit; se não der, assume escuro."""
    try:
        return st.context.theme.type != "light"
    except Exception:
        pass
    try:
        return st.get_option("theme.base") != "light"
    except Exception:
        return True


def grafico_urnas(df):
    """Barras: maiores colégios eleitorais à esquerda; altura = % de urnas apuradas."""
    d = df[["uf", "regiao", "pct_secoes", "votos_previstos"]].copy()
    d = d.sort_values("votos_previstos", ascending=False)
    d["pct"] = d["pct_secoes"].round(1)
    d["previstos"] = d["votos_previstos"].round(0).astype("int64")
    ordem = d["uf"].tolist()
    cor_rotulo = "#FFFFFF" if tema_escuro() else "#000000"  # oposta ao fundo
    try:
        import altair as alt

        escala_cor = alt.Scale(
            domain=list(CORES_REGIAO), range=list(CORES_REGIAO.values())
        )
        base = alt.Chart(d).encode(
            x=alt.X("uf:N", sort=ordem, title="Estado (maior eleitorado à esquerda)"),
            y=alt.Y("pct:Q", scale=alt.Scale(domain=[0, 105]), title="% de urnas apuradas"),
            tooltip=[
                alt.Tooltip("uf:N", title="Estado"),
                alt.Tooltip("regiao:N", title="Região"),
                alt.Tooltip("pct:Q", title="% apuradas"),
                alt.Tooltip("previstos:Q", title="Votos previstos", format=","),
            ],
        )
        barras = base.mark_bar().encode(
            color=alt.Color(
                "regiao:N",
                scale=escala_cor,
                sort=list(CORES_REGIAO),
                title="Região",
            )
        )
        rotulos = base.mark_text(
            dy=-8, fontSize=13, fontWeight="bold", color=cor_rotulo
        ).encode(text=alt.Text("pct:Q", format=".0f"))
        grafico = (barras + rotulos).properties(height=340)
        try:
            st.altair_chart(grafico, width="stretch")
        except Exception:
            st.altair_chart(grafico, use_container_width=True)
    except Exception:
        st.bar_chart(d.set_index("uf")["pct"])


def painel(modo, escala, m, modo_base, prog_sim, desvio_sim):
    agora = datetime.now(TZ)
    st.caption(f"Última atualização do painel: {agora.strftime('%d/%m/%Y %H:%M:%S')} (Brasília)")

    # ---------- carga ----------
    if modo == MODO_SIM:
        dados = carregar_simulado(prog_sim, desvio_sim)
        st.warning(
            "MODO SIMULADOR: números fictícios (cada estado abre num ritmo diferente, com "
            "comparecimento 7% menor que o previsto e o desvio escolhido). Mexa nos controles "
            "laterais para ver o motor reagir."
        )
    elif modo == MODO_ENSAIO:
        dados = carregar_oficial(ELEICAO_1T)
        st.warning(
            "MODO ENSAIO: dados REAIS e já encerrados do 1º turno, só para testar a leitura do "
            "TSE. Como estão 100% apurados, a projeção não se move aqui; para ver o motor "
            "reagindo use o Simulador. Os números NÃO são do 2º turno."
        )
    else:
        dados = carregar_oficial()

    status = dados["status"]
    nacional = dados["nacional"]
    bases = construir_bases(escala, dados["r1"], modo_base)
    df, clima_resumo = motor(dados["unidades"], bases, m)

    # ---------- faixa de status ----------
    if status == "aguardando":
        if modo == MODO_OFICIAL and agora < INICIO_DIVULGACAO:
            falta = INICIO_DIVULGACAO - agora
            h, resto = divmod(int(falta.total_seconds()), 3600)
            mi, s = divmod(resto, 60)
            st.info(
                f"⏳ Aguardando o início da divulgação do TSE (a partir das 17h de 25/10). "
                f"Faltam {h:02d}h{mi:02d}min{s:02d}s. O app consulta o TSE sozinho a cada "
                f"{INTERVALO_ATUALIZACAO}s e começa a apuração automaticamente. Até lá, a "
                "projeção mostrada é só a previsão-base."
            )
        else:
            st.info(
                "⏳ Arquivos de apuração ainda não publicados pelo TSE (ou ainda sem votos). "
                "O app continua tentando sozinho. A projeção é só a previsão-base."
            )
    elif status == "apurando":
        st.success("🟢 Apuração em andamento — projeção recalculada a cada atualização.")
    else:
        st.success("🏁 Totalização concluída — valores finais baseados nos votos reais.")

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
                f"nacional do TSE ({fmt_num(nac_total)}). Pode ser atraso entre arquivos."
            )

    # ---------- 2. projeção ----------
    st.subheader("2. Projeção final do motor (ativa)")
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

    base_a = sum(b["T0"] * b["s0"] for b in bases.values())
    base_b = sum(b["T0"] * (1 - b["s0"]) for b in bases.values())
    b1, b2, b3 = st.columns(3)
    b1.metric("Previsão-base (sem urnas) — Lula", fmt_pct(base_a / (base_a + base_b) * 100))
    b2.metric(
        "Contagem real até agora — Lula",
        fmt_pct(real_a / (real_a + real_b) * 100) if (real_a + real_b) > 0 else "—",
    )
    b3.metric("Projeção do motor — Lula", fmt_pct(pct_a))
    st.caption(
        "A contagem real pode ficar muito diferente da projeção no início, porque as urnas "
        "que abrem primeiro vêm de estados específicos. O motor compara cada estado com a "
        "sua própria base, por isso não confunde 'quem abriu primeiro' com 'quem está ganhando'."
    )

    a_apurar = max(0.0, total_proj - (real_a + real_b)) if nacional else total_proj
    q1, q2, q3 = st.columns(3)
    q1.metric("Votos a apurar (estimado)", fmt_num(a_apurar))
    q2.metric("Total projetado de votos", fmt_num(total_proj))
    virou = df[df["virou"]]["uf"].tolist()
    q3.metric(
        "Estados que virariam vs. base",
        str(len(virou)),
        ", ".join(virou) if virou else "nenhum",
        delta_color="off",
    )

    # clima nacional
    cn = clima_resumo.get("Brasil")
    if cn:
        k1, k2, k3 = st.columns(3)
        k1.metric(
            "Desvio de Lula vs. base (nas urnas abertas)",
            f"{cn['desvio_pp']:+.2f}".replace(".", ",") + " p.p.",
        )
        k2.metric(
            "Comparecimento vs. previsto",
            fmt_pct(cn["comparecimento"] * 100),
        )
        k3.metric("Votos previstos já apurados", fmt_pct(cn["votos_apurados_pct"]))

    if total_proj and diferenca / total_proj < 0.005:
        st.warning(
            "⚠️ Disputa muito apertada: diferença projetada menor que 0,5% dos votos, dentro "
            "da margem de erro do modelo. Não trate como resultado."
        )
    st.caption(
        "Percentuais calculados sobre a soma dos votos dos dois candidatos (27 UFs + Exterior). "
        "Não são percentuais oficiais do TSE. Projeção = estimativa, não resultado oficial."
    )

    # ---------- 3. urnas por estado ----------
    st.subheader("3. Urnas apuradas por estado (maiores colégios eleitorais primeiro)")
    grafico_urnas(df)

    # ---------- 4. evolução ----------
    if status != "aguardando" and nacional:
        chave = f"{modo}|{dados['eleicao']}"
        serie = registrar_historico(chave, nacional, total_a, total_b)
        if len(serie) >= 2:
            st.subheader("4. Evolução da projeção")
            dh = pd.DataFrame(serie).sort_values("Seções apuradas %", kind="stable")
            g1, g2 = st.columns(2)
            g1.caption("Projeção % de cada candidato (eixo: % de seções apuradas)")
            g1.line_chart(
                dh, x="Seções apuradas %", y=["Lula projeção %", "Flávio projeção %"]
            )
            g2.caption("Diferença projetada em votos, Lula − Flávio (eixo: % de seções apuradas)")
            g2.line_chart(
                dh, x="Seções apuradas %", y=["Diferença projetada (Lula − Flávio)"]
            )

    # ---------- 4. motor: clima por região ----------
    st.subheader("5. Motor de análise — o que as urnas estão dizendo")
    linhas_reg = []
    for r in ["Brasil"] + list(REGIOES):
        c = clima_resumo.get(r)
        if c:
            linhas_reg.append(
                {
                    "Região": r,
                    "Votos previstos já apurados %": round(c["votos_apurados_pct"], 2),
                    "Desvio de Lula vs. base (p.p.)": round(c["desvio_pp"], 2),
                    "Comparecimento vs. previsto (%)": round(c["comparecimento"] * 100, 2),
                }
            )
    if linhas_reg:
        mostrar_df(pd.DataFrame(linhas_reg))
    else:
        st.write("Sem urnas apuradas ainda — o motor entra em ação assim que os primeiros dados chegarem.")
    st.caption(
        "Como funciona: cada estado é comparado com a sua base (previsão / 1º turno). O desvio "
        "observado vira um 'clima' regional e nacional, ponderado pelos votos apurados e pela "
        "abertura das urnas de cada estado. Esse clima corrige o que ainda falta apurar em todos "
        "os estados, inclusive os que ainda não abriram. Quanto mais urnas abertas num estado, "
        "mais o resultado real dele pesa sobre a própria projeção."
    )

    # ---------- 5. tabela ----------
    st.subheader("6. Acompanhamento por estado")
    tabela = pd.DataFrame(
        {
            "UF": df["UF"],
            "Região": df["regiao"],
            "Votos previstos base": df["votos_previstos"].round(0).astype("int64"),
            "Seções apuradas %": df["pct_secoes"].round(2),
            "Seções apuradas": df["secoes_apuradas"],
            "Total de seções": df["secoes_total"],
            "Lula votos reais": df["lula_real"],
            "Flávio votos reais": df["flavio_real"],
            "Lula base %": df["pct_a_base"].astype(float).round(2),
            "Peso dos dados reais %": df["peso_real"].round(1),
            "Ajuste no que falta (p.p. Lula)": df["ajuste_resto_pp"].astype(float).round(2),
            "Lula projeção votos": df["proj_lula"].round(0).astype("int64"),
            "Lula projeção %": df["pct_proj_lula"].round(2),
            "Flávio projeção votos": df["proj_flavio"].round(0).astype("int64"),
            "Flávio projeção %": df["pct_proj_flavio"].round(2),
            "Desvio Lula vs base (p.p.)": df["desvio_lula_pp"].astype(float).round(2),
            "Líder base": df["lider_base"],
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
        st.write(f"Base de previsão em uso: **{modo_base}**")
        st.write(f"1º turno real carregado para {len(dados['r1'])} de {len(UNIDADES)} unidades.")
        st.write(
            "Unidades com dado desatualizado (usando última leitura boa): "
            f"{int(df['obsoleto'].sum())}"
        )
        if "ZZ" not in bases:
            st.write("Exterior (ZZ): sem base (1º turno indisponível); projetado só pelos votos reais.")
        if dados["erros"]:
            st.write("Falhas/avisos:")
            st.code("\n".join(dados["erros"][:40]))
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
        modo_base = st.selectbox(
            "Base da previsão",
            BASES,
            index=0,
            help="'Minha previsão' usa os percentuais que você informou. As outras opções "
            "usam (ou misturam) o resultado real do 1º turno lido do TSE.",
        )
        conf = st.select_slider(
            "Confiança na previsão-base",
            options=list(CONFIANCA),
            value="Média",
            help="Quanto menor, mais rápido os dados reais assumem o controle da projeção.",
        )
        escala_pct = st.slider(
            "Ajuste dos totais previstos (%)",
            min_value=80,
            max_value=110,
            value=100,
            step=1,
            help="100% = exatamente os totais informados. O motor já corrige o comparecimento "
            "sozinho conforme as urnas abrem; use só para testar cenários.",
        )
        prog_sim, desvio_sim = 35, 0.0
        if modo == MODO_SIM:
            prog_sim = st.slider("Progresso fictício da apuração (%)", 0, 100, 35, 5)
            desvio_sim = st.slider(
                "Desvio fictício a favor de Lula (p.p.)", -10.0, 10.0, 3.0, 0.5
            )
        st.write(f"Atualização automática: {INTERVALO_ATUALIZACAO} s")
        st.write("Abrangência: 27 UFs + Exterior")
        st.markdown("[Portal oficial do TSE](https://resultados.tse.jus.br/)")

    escala = escala_pct / 100
    m = CONFIANCA[conf]

    def corpo():
        try:
            painel(modo, escala, m, modo_base, prog_sim, desvio_sim)
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


if __name__ == "__main__":
    main()
