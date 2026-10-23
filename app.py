import streamlit as st
import random
import requests

# ==============================================================================
# DATABASES: MATRIZ DE PESOS DOS ESTADOS (BASEADO NO 1º TURNO)
# ==============================================================================
DADOS_ESTADOS_1_TURNO = {
    "SP": {"votos_esperados": 27_000_000, "pct_a": 48.0, "pct_b": 52.0},
    "MG": {"votos_esperados": 12_000_000, "pct_a": 51.0, "pct_b": 49.0},
    "RJ": {"votos_esperados": 10_000_000, "pct_a": 45.0, "pct_b": 55.0},
    "BA": {"votos_esperados": 9_000_000, "pct_a": 68.0, "pct_b": 32.0},
    "RS": {"votos_esperados": 7_000_000, "pct_a": 42.0, "pct_b": 58.0},
    "PR": {"votos_esperados": 7_000_000, "pct_a": 40.0, "pct_b": 60.0},
    "PE": {"votos_esperados": 5_500_000, "pct_a": 65.0, "pct_b": 35.0},
    "CE": {"votos_esperados": 5_300_000, "pct_a": 66.0, "pct_b": 34.0},
    "PA": {"votos_esperados": 4_800_000, "pct_a": 54.0, "pct_b": 46.0},
    "MA": {"votos_esperados": 4_000_000, "pct_a": 67.0, "pct_b": 33.0},
    "SC": {"votos_esperados": 4_500_000, "pct_a": 31.0, "pct_b": 69.0},
    "GO": {"votos_esperados": 4_000_000, "pct_a": 41.0, "pct_b": 59.0},
    "PB": {"votos_esperados": 2_600_000, "pct_a": 64.0, "pct_b": 36.0},
    "RN": {"votos_esperados": 2_200_000, "pct_a": 63.0, "pct_b": 37.0},
    "AL": {"votos_esperados": 1_900_000, "pct_a": 58.0, "pct_b": 42.0},
    "PI": {"votos_esperados": 2_100_000, "pct_a": 74.0, "pct_b": 26.0},
    "MT": {"votos_esperados": 2_200_000, "pct_a": 35.0, "pct_b": 65.0},
    "DF": {"votos_esperados": 1_800_000, "pct_a": 39.0, "pct_b": 61.0},
    "ES": {"votos_esperados": 2_300_000, "pct_a": 43.0, "pct_b": 57.0},
    "AM": {"votos_esperados": 2_100_000, "pct_a": 50.0, "pct_b": 50.0},
    "MS": {"votos_esperados": 1_600_000, "pct_a": 38.0, "pct_b": 62.0},
    "SE": {"votos_esperados": 1_300_000, "pct_a": 62.0, "pct_b": 38.0},
    "RO": {"votos_esperados": 1_000_000, "pct_a": 30.0, "pct_b": 70.0},
    "TO": {"votos_esperados": 900_000,  "pct_a": 52.0, "pct_b": 48.0},
    "AC": {"votos_esperados": 500_000,  "pct_a": 28.0, "pct_b": 72.0},
    "AP": {"votos_esperados": 500_000,  "pct_a": 46.0, "pct_b": 54.0},
    "RR": {"votos_esperados": 300_000,  "pct_a": 25.0, "pct_b": 75.0}
}

# ==============================================================================
# 1. FUNÇÃO COLETORA DE DADOS REAIS DO TSE
# ==============================================================================
def buscar_dados_reais_tse():
    dados_apuracao_estados = {}
    
    # URL Base oficial da CDN de divulgação de resultados do TSE
    # c0001 representa o cargo de presidente. e002026 representa o ano eleitoral.
    url_base = "https://tse.jus.br{uf}/{uf}-c0001-e002026-v.json"
    
    for uf, info in DADOS_ESTADOS_1_TURNO.items():
        try:
            url_estado = url_base.format(uf=uf.lower())
            resposta = requests.get(url_estado, timeout=3)
            json_tse = resposta.json()
            
            # Mapeamento padrão dos nós do arquivo oficial do TSE (psi = % apurado, v = votos válidos)
            progresso_uf = float(json_tse["psi"].replace(",", "."))
            votos_apurados = int(json_tse["v"])
            
            # Identificação dos candidatos pelo nó de candidaturas (consulte o TSE para mapear os números oficiais corretos)
            votos_cand_a = 0
            votos_cand_b = 0
            for cand in json_tse["cand"]:
                if cand["n"] == "NUMERO_CANDIDATO_A": 
                    votos_cand_a = int(cand["vap"])
                elif cand["n"] == "NUMERO_CANDIDATO_B": 
                    votos_cand_b = int(cand["vap"])
            
            dados_apuracao_estados[uf] = {
                "progresso_uf": progresso_uf,
                "votos_total_esperados": info["votos_esperados"],
                "votos_apurados": votos_apurados,
                "votos_a": votos_cand_a,
                "votos_b": votos_cand_b
            }
        except Exception:
            # Fallback de segurança se o servidor de algum estado oscilar
            dados_apuracao_estados[uf] = {"progresso_uf": 0.0, "votos_total_esperados": info["votos_esperados"], "votos_apurados": 0, "votos_a": 0, "votos_b": 0}
            
    return dados_apuracao_estados

# Simulador legado para testes rápidos
def buscar_dados_simulados(progresso_geral):
    dados_apuracao_estados = {}
    random.seed(progresso_geral)
    for uf, info in DADOS_ESTADOS_1_TURNO.items():
        if uf in ["SP", "PR", "SC", "RS"]:
            progresso_uf = min(100, progresso_geral * 1.3)
        elif uf in ["BA", "PE", "MA", "PI"]:
            progresso_uf = max(0, min(100, (progresso_geral - 10) * 1.1))
        else:
            progresso_uf = progresso_geral
        votos_apurados = int(info["votos_esperados"] * (progresso_uf / 100))
        if 0 < progresso_uf < 100:
            fator = random.uniform(-3.5, 3.5) * (1 - (progresso_uf / 100))
            pct = max(0, min(100, info["pct_a"] + fator))
        else:
            pct = info["pct_a"]
        votos_a = int(votos_apurados * (pct / 100))
        dados_apuracao_estados[uf] = {"progresso_uf": progresso_uf, "votos_total_esperados": info["votos_esperados"], "votos_apurados": votos_apurados, "votos_a": votos_a, "votos_b": votos_apurados - votos_a}
    return dados_apuracao_estados

# ==============================================================================
# 2. PROCESSADOR DE PROJEÇÃO ESTADUAL E NACIONAL
# ==============================================================================
def processar_modelos_eleitorais(dados_estados, modo_ao_vivo):
    dados_consolidados_estados = {}
    total_projetado_nacional_a = 0
    total_projetado_nacional_b = 0
    
    # Calcula a soma geral de urnas para saber se o país começou a apurar
    urnas_totais_abertas = sum(d["votos_apurados"] for d in dados_estados.values())
    
    for uf, dados in dados_estados.items():
        votos_ja_apurados_a = dados["votos_a"]
        votos_ja_apurados_b = dados["votos_b"]
        votos_restantes = dados["votos_total_esperados"] - dados["votos_apurados"]
        
        if urnas_totais_abertas == 0:
            proj_estado_a = dados["votos_total_esperados"] * 0.5
            proj_estado_b = dados["votos_total_esperados"] * 0.5
        else:
            pct_historico_a = DADOS_ESTADOS_1_TURNO[uf]["pct_a"] / 100
            pct_historico_b = 1.0 - pct_historico_a
            
            proj_estado_a = votos_ja_apurados_a + (votos_restantes * pct_historico_a)
            proj_estado_b = votos_ja_apurados_b + (votos_restantes * pct_historico_b)
            
        total_projetado_nacional_a += proj_estado_a
        total_projetado_nacional_b += proj_estado_b
        
        soma_estado = proj_estado_a + proj_estado_b
        pct_proj_estado_a = (proj_estado_a / soma_estado * 100) if soma_estado > 0 else 50.0
        pct_proj_estado_b = (proj_estado_b / soma_estado * 100) if soma_estado > 0 else 50.0
        
        dados_consolidados_estados[uf] = {
            "progresso_uf": dados["progresso_uf"],
            "votos_total_esperados": dados["votos_total_esperados"],
            "votos_apurados": dados["votos_apurados"],
            "votos_a": dados["votos_a"],
            "votos_b": dados["votos_b"],
            "votos_projetados_total": int(soma_estado),
            "pct_projetado_a": pct_proj_estado_a,
            "pct_projetado_b": pct_proj_estado_b
        }
        
    soma_nacional = total_projetado_nacional_a + total_projetado_nacional_b
    if soma_nacional == 0 or urnas_totais_abertas == 0:
        pct_nacional_proj_a, pct_nacional_proj_b = 50.0, 50.0
    else:
        pct_nacional_proj_a = (total_projetado_nacional_a / soma_nacional) * 100
        pct_nacional_proj_b = (total_projetado_nacional_b / soma_nacional) * 100
        
    return dados_consolidados_estados, pct_nacional_proj_a, pct_nacional_proj_b

# ==============================================================================
# 3. INTERFACE VISUAL DO AGENTE (Adapte os rótulos conforme os candidatos oficiais)
# ==============================================================================
st.set_page_config(page_title="Monitor Estatístico de Urnas", page_icon="🔮", layout="wide")

st.title("🔮 Monitor de Urnas com Projeção por Estado")
st.subheader("Visualização geopolítica e eliminação de viés de apuração em tempo real")

# CONTROLE DE CHAVEAMENTO DE MODO EM TEMPO REAL NA SIDEBAR
st.sidebar.header("🕹️ Configuração do Sistema")
modo_sistema = st.sidebar.radio("Selecione o modo de operação:", ["Simulador (Ambiente de Testes)", "AO VIVO (Dados Reais do TSE)"])

if modo_sistema == "AO VIVO (Dados Reais do TSE)":
    st.sidebar.success("📡 Modo Tempo Real Ativo! O painel tentará ler a CDN do TSE.")
    progresso_geral_calculado = 0
    dados_processados = buscar_dados_reais_tse()
    votos_totais_esperados_br = sum(d["votos_total_esperados"] for d in dados_processados.values())
    votos_totais_apurados_br = sum(d["votos_apurados"] for d in dados_processados.values())
    progresso_visual = int((votos_totais_apurados_br / votos_totais_esperados_br * 100)) if votos_totais_esperados_br > 0 else 0
else:
    progresso_visual = st.sidebar.slider("Porcentagem geral de urnas abertas:", 0, 100, 0, step=5)
    dados_processados = buscar_dados_simulados(progresso_visual)

dados_finais, proj_a, proj_b = processar_modelos_eleitorais(dados_processados, modo_sistema == "AO VIVO (Dados Reais do TSE)")

votos_totais_a = sum(d["votos_a"] for d in dados_finais.values())
votos_totais_b = sum(d["votos_b"] for d in dados_finais.values())
votos_totais_geral = votos_totais_a + votos_totais_b

pct_nacional_a = (votos_totais_a / votos_totais_geral * 100) if votos_totais_geral > 0 else 50.0
pct_nacional_b = (votos_totais_b / votos_totais_geral * 100) if votos_totais_geral > 0 else 50.0

col1, col2 = st.columns(2)

