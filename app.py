import streamlit as st
import random

# ==============================================================================
# DATABASES: MATRIZ DE PESOS DOS ESTADOS (BASEADO NO 1º TURNO DE 2026)
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
# 1. SIMULADOR COM RUIDO E OSCILAÇÃO REALISTA
# ==============================================================================
def buscar_dados_urnas_por_estado(progresso_geral):
    dados_apuracao_estados = {}
    
    # Fixamos uma semente baseada no progresso para manter consistência ao mover o slider
    random.seed(progresso_geral)
    
    for uf, info in DADOS_ESTADOS_1_TURNO.items():
        # Velocidades diferentes por região
        if uf in ["SP", "PR", "SC", "RS"]:
            progresso_uf = min(100, progresso_geral * 1.3)
        elif uf in ["BA", "PE", "MA", "PI"]:
            progresso_uf = max(0, min(100, (progresso_geral - 10) * 1.1))
        else:
            progresso_uf = progresso_geral
            
        votos_apurados = int(info["votos_esperados"] * (progresso_uf / 100))
        
        # INJEÇÃO DE OSCILAÇÃO: Se a apuração está no começo, o resultado local varia mais.
        # Conforme chega perto de 100%, a variação cai para zero.
        if 0 < progresso_uf < 100:
            fator_variacao = random.uniform(-3.5, 3.5) * (1 - (progresso_uf / 100))
            pct_ajustado_a = max(0, min(100, info["pct_a"] + fator_variacao))
        else:
            pct_ajustado_a = info["pct_a"]
            
        votos_a = int(votos_apurados * (pct_ajustado_a / 100))
        votos_b = votos_apurados - votos_a
        
        dados_apuracao_estados[uf] = {
            "progresso_uf": progresso_uf,
            "votos_total_esperados": info["votos_esperados"],
            "votos_apurados": votos_apurados,
            "votos_a": votos_a,
            "votos_b": votos_b
        }
    return dados_apuracao_estados

# ==============================================================================
# 2. ALGORITMO DE PROJEÇÃO PONDERADA ESTADUAL
# ==============================================================================
def calcular_projecao_ponderada(dados_estados):
    projecao_votos_totais_a = 0
    projecao_votos_totais_b = 0
    
    for uf, dados in dados_estados.items():
        votos_ja_apurados_a = dados["votos_a"]
        votos_ja_apurados_b = dados["votos_b"]
        votos_restantes = dados["votos_total_esperados"] - dados["votos_apurados"]
        
        # Preditor projeta os votos que faltam com base na linha de base histórica
        pct_historico_a = DADOS_ESTADOS_1_TURNO[uf]["pct_a"] / 100
        pct_historico_b = DADOS_ESTADOS_1_TURNO[uf]["pct_b"] / 100
        
        votos_projetados_a = votos_ja_apurados_a + (votos_restantes * pct_historico_a)
        votos_projetados_b = votos_ja_apurados_b + (votos_restantes * pct_historico_b)
        
        projecao_votos_totais_a += votos_projetados_a
        projecao_votos_totais_b += votos_projetados_b
        
    soma_total = projecao_votos_totais_a + projecao_votos_totais_b
    if soma_total == 0:
        return 50.0, 50.0
        
    return (projecao_votos_totais_a / soma_total) * 100, (projecao_votos_totais_b / soma_total) * 100

# ==============================================================================
# 3. INTERFACE VISUAL DO SISTEMA
# ==============================================================================
st.set_page_config(page_title="Monitor Estatístico de Urnas", page_icon="🔮", layout="wide")

st.title("🔮 Monitor de Urnas com Projeção Ponderada por Estado")
st.subheader("Algoritmo com ajuste fino de oscilação estatística local")

st.sidebar.header("🕹️ Painel de Controle")
progresso = st.sidebar.slider("Porcentagem geral de urnas abertas:", 0, 100, 0, step=5)

# Processamento dos Modelos
dados_atuais = buscar_dados_urnas_por_estado(progresso)
proj_a, proj_b = calcular_projecao_ponderada(dados_atuais)

# Consolidação Nacional Atual
votos_totais_a = sum(d["votos_a"] for d in dados_atuais.values())
votos_totais_b = sum(d["votos_b"] for d in dados_atuais.values())
votos_totais_geral = votos_totais_a + votos_totais_b

pct_nacional_a = (votos_totais_a / votos_totais_geral * 100) if votos_totais_geral > 0 else 0
pct_nacional_b = (votos_totais_b / votos_totais_geral * 100) if votos_totais_geral > 0 else 0

# Exibição dos Blocos Principais
col1, col2 = st.columns(2)

with col1:
    st.markdown("### 🗳️ Placar Parcial Geral (Sem Filtro Regional)")
    st.progress(progresso / 100, text=f"Urnas Brasileiras Apuradas: {progresso}%")
    st.metric(label="🟢 Candidato A (Votos Reais Computados)", value=f"{votos_totais_a:,}", delta=f"{pct_nacional_a:.2f}%")
    st.metric(label="🔵 Candidato B (Votos Reais Computados)", value=f"{votos_totais_b:,}", delta=f"{pct_nacional_b:.2f}%")

with col2:
    st.markdown("### 🧠 Projeção Ponderada por Estado (Previsão Final)")
    if progresso < 10:
        st.warning("⚠️ Aguarde pelo menos 10% das urnas para estabilizar o cálculo regional.")
    else:
        st.success("✅ Modelo matemático calculando pesos com estabilidade dinâmica.")
    st.metric(label="🔮 Candidato A (Resultado Final Projetado)", value=f"{proj_a:.2f}%")
    st.metric(label="🔮 Candidato B (Resultado Final Projetado)", value=f"{proj_b:.2f}%")

st.write("---")
st.markdown("### 🗺️ Status da Apuração por Estado")
lista_estados = []
for uf, d in dados_atuais.items():
    lista_estados.append({
        "Estado": uf,
        "Progresso": f"{d['progresso_uf']:.1f}%",
        "Votos Apurados": f"{d['votos_apurados']:,}",
        "Votos Cand. A": f"{d['votos_a']:,}",
        "Votos Cand. B": f"{d['votos_b']:,}"
    })
st.table(lista_estados)

