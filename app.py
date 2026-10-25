import streamlit as st
import random
import requests

# ==============================================================================
# DATABASES: MATRIZ DE PESOS DOS ESTADOS (BASEADO NO 1º TURNO)
# ==============================================================================
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
    "TO": {"votos_esperados": 970_000,  "pct_a": 48.0, "pct_b": 51.0},
    "AC": {"votos_esperados": 545_000,  "pct_a": 27.5, "pct_b": 65.0},
    "AP": {"votos_esperados": 535_000,  "pct_a": 49.0, "pct_b": 48.5},
    "RR": {"votos_esperados": 333_000,  "pct_a": 26.0, "pct_b": 73.0}
}

# ==============================================================================
# 1. COLETORES DE DADOS (SIMULADO E AO VIVO)
# ==============================================================================
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
        desvio_real_cenario = 1.2 
        
        if 0 < progresso_uf < 100:
            fator_variacao = random.uniform(-1.5, 1.5) * (1 - (progresso_uf / 100))
            pct_ajustado_a = max(0, min(100, info["pct_a"] + desvio_real_cenario + fator_variacao))
        else:
            pct_ajustado_a = info["pct_a"] + (desvio_real_cenario if progresso_uf == 100 else 0)
            
        votos_a = int(votos_apurados * (pct_ajustado_a / 100))
        dados_apuracao_estados[uf] = {
            "progresso_uf": progresso_uf,
            "votos_total_esperados": info["votos_esperados"],
            "votos_apurados": votos_apurados,
            "votos_a": votos_a,
            "votos_b": votos_apurados - votos_a
        }
    return dados_apuracao_estados

def buscar_dados_reais_tse():
    dados_apuracao_estados = {}
    url_base = "https://tse.jus.br{uf}/{uf}-c0001-e002026-v.json"
    
    for uf, info in DADOS_ESTADOS_1_TURNO.items():
        try:
            url_estado = url_base.format(uf=uf.lower())
            resposta = requests.get(url_estado, timeout=3)
            json_tse = response.json()
            
            progresso_uf = float(json_tse["psi"].replace(",", "."))
            votos_apurados = int(json_tse["v"])
            
            votos_cand_a = 0
            votos_cand_b = 0
            for cand in json_tse["cand"]:
                # Mapeamento dinâmico baseado na ordem de envio das variáveis
                if cand["seq"] == "1": votos_cand_a = int(cand["vap"])
                elif cand["seq"] == "2": votos_cand_b = int(cand["vap"])
                
            dados_apuracao_estados[uf] = {
                "progresso_uf": progresso_uf,
                "votos_total_esperados": info["votos_esperados"],
                "votos_apurados": votos_apurados,
                "votos_a": votos_cand_a,
                "votos_b": votos_cand_b
            }
        except Exception:
            # Fallback limpo caso o sinal do TSE ainda esteja fechado
            dados_apuracao_estados[uf] = {
                "progresso_uf": 0.0,
                "votos_total_esperados": info["votos_esperados"],
                "votos_apurados": 0,
                "votos_a": 0,
                "votos_b": 0
            }
    return dados_apuracao_estados

# ==============================================================================
# 2. MOTOR DE AJUSTE DINÂMICO E APRENDIZADO EM TEMPO REAL
# ==============================================================================
def processar_modelos_eleitorais(dados_estados, modo_ao_vivo):
    dados_consolidados_estados = {}
    total_projetado_nacional_a = 0
    total_projetado_nacional_b = 0
    
    urnas_totais_br_computadas = sum(d["votos_apurados"] for d in dados_estados.values())
    
    for uf, dados in dados_estados.items():
        votos_ja_apurados_a = dados["votos_a"]
        votos_ja_apurados_b = dados["votos_b"]
        votos_restantes = dados["votos_total_esperados"] - dados["votos_apurados"]
        
        if urnas_totais_br_computadas == 0:
            proj_estado_a = dados["votos_total_esperados"] * 0.5
            proj_estado_b = dados["votos_total_esperados"] * 0.5
            desvio_identificado = 0.0
        else:
            total_parcial = votos_ja_apurados_a + votos_ja_apurados_b
            pct_real_atual_a = (votos_ja_apurados_a / total_parcial) if total_parcial > 0 else (DADOS_ESTADOS_1_TURNO[uf]["pct_a"] / 100)
            
            pct_previsto_1_turno_a = DADOS_ESTADOS_1_TURNO[uf]["pct_a"] / 100
            desvio_identificado = pct_real_atual_a - pct_previsto_1_turno_a
            
            fator_estabilidade = dados["progresso_uf"] / 100.0
            desvio_calibrado = desvio_identificado * fator_estabilidade
            
            pct_dinamico_futuro_a = max(0.0, min(1.0, pct_previsto_1_turno_a + desvio_calibrado))
            pct_dinamico_futuro_b = 1.0 - pct_dinamico_futuro_a
            
            proj_estado_a = votos_ja_apurados_a + (votos_restantes * pct_dinamico_futuro_a)
            proj_estado_b = votos_ja_apurados_b + (votos_restantes * pct_dinamico_futuro_b)
            
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
            "pct_projetado_b": pct_proj_estado_b,
            "desvio_real": desvio_identificado * 100
        }
        
    soma_nacional = total_projetado_nacional_a + total_projetado_nacional_b
    if soma_nacional == 0 or urnas_totais_br_computadas == 0:
        pct_nacional_proj_a, pct_nacional_proj_b = 50.0, 50.0
    else:
        pct_nacional_proj_a = (total_projetado_nacional_a / soma_nacional) * 100
        pct_nacional_proj_b = (total_projetado_nacional_b / soma_nacional) * 100
        
    return dados_consolidados_estados, pct_nacional_proj_a, pct_nacional_proj_b

# ==============================================================================
# 3. INTERFACE VISUAL DO AGENTE
# ==============================================================================
st.set_page_config(page_title="Monitor Estatístico de Urnas", page_icon="🔮", layout="wide")

# CRONÔMETRO ATIVO EM 20 SEGUNDOS
st.fragment(run_every=20)

st.title("🔮 Monitor de Urnas com Projeção Dinâmica por Estado")
st.subheader("Algoritmo adaptativo com Motor de Ajuste e Aprendizado em Tempo Real")

st.sidebar.header("🕹️ Configuração do Sistema")
modo_sistema = st.sidebar.radio("Selecione o modo de operação:", ["Simulador (Ambiente de Testes)", "AO VIVO (Dados Reais do TSE)"])

if modo_sistema == "AO VIVO (Dados Reais do TSE)":
    dados_processados = buscar_dados_reais_tse()
    votos_totais_esperados_br = sum(d["votos_total_esperados"] for d in dados_processados.values())
    votos_totais_apurados_br = sum(d["votos_apurados"] for d in dados_processados.values())
    progresso_visual = int((votos_totais_apurados_br / votos_totais_esperados_br * 100)) if votos_totais_esperados_br > 0 else 0
    st.sidebar.caption("📡 Motor adaptativo operando ao vivo a cada 20 segundos.")
else:
    progresso_visual = st.sidebar.slider("Porcentagem geral de urnas abertas:", 0, 100, 0, step=5)
    dados_processados = buscar_dados_simulados(progresso_visual)

dados_finais, proj_lula, proj_flavio = processar_modelos_eleitorais(dados_processados, progresso_visual)

