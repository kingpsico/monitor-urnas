import streamlit as st
import time
import random

# ==========================================
# 1. COLETA E SIMULAÇÃO DE DADOS
# ==========================================
def buscar_dados_urnas(progresso_atual):
    total_votos_validos = 100_000_000
    votos_apurados_ate_agora = int(total_votos_validos * (progresso_atual / 100))
    
    if progresso_atual < 50:
        percentual_a = 0.54 - (progresso_atual * 0.001)
    else:
        percentual_a = 0.49 + ((100 - progresso_atual) * 0.001)
        
    percentual_b = 1.0 - percentual_a
    votos_a = int(votos_apurados_ate_agora * percentual_a)
    votos_b = int(votos_apurados_ate_agora * percentual_b)
    
    return {
        "urnas_apuradas_percentual": progresso_atual,
        "votos_total_apurados": votos_apurados_ate_agora,
        "candidato_a_votos": votos_a,
        "candidato_b_votos": votos_b
    }

# ==========================================
# 2. INTELIGÊNCIA E PROJEÇÃO ESTATÍSTICA
# ==========================================
def calcular_projecao_final(dados_parciais):
    porcentagem_aberta = dados_parciais["urnas_apuradas_percentual"]
    votos_a = dados_parciais["candidato_a_votos"]
    votos_b = dados_parciais["candidato_b_votos"]
    
    if porcentagem_aberta == 0:
        return 50.0, 50.0
        
    fator_confianca = porcentagem_aberta / 100.0
    total_votos_parcial = votos_a + votos_b
    pct_atual_a = votos_a / total_votos_parcial if total_votos_parcial > 0 else 0.5
    pct_atual_b = votos_b / total_votos_parcial if total_votos_parcial > 0 else 0.5
    
    projecao_a = (pct_atual_a * fator_confianca) + (0.50 * (1 - fator_confianca))
    projecao_b = (pct_atual_b * fator_confianca) + (0.50 * (1 - fator_confianca))
    
    soma = projecao_a + projecao_b
    return (projecao_a / soma) * 100, (projecao_b / soma) * 100

# ==========================================
# 3. INTERFACE VISUAL DO AGENTE
# ==========================================
st.set_page_config(page_title="Monitor de Urnas em Tempo Real", page_icon="📊", layout="wide")

st.title("📊 Monitor de Urnas & Projeção Estatística")
st.subheader("Acompanhe a apuração e a previsão do resultado final em tempo real")

st.sidebar.header("🕹️ Controle de Fluxo")
progresso = st.sidebar.slider("Porcentagem de urnas abertas:", 0, 100, 0, step=5)

dados = buscar_dados_urnas(progresso)
proj_a, proj_b = calcular_projecao_final(dados)

col1, col2 = st.columns(2)

with col1:
    st.markdown("### 🗳️ Resultado Parcial Atual")
    st.progress(progresso / 100, text=f"Urnas Apuradas: {progresso}%")
    
    total_votos_atual = dados["votos_total_apurados"]
    pct_atual_a = (dados["candidato_a_votos"] / total_votos_atual * 100) if total_votos_atual > 0 else 0
    pct_atual_b = (dados["candidato_b_votos"] / total_votos_atual * 100) if total_votos_atual > 0 else 0
    
    st.metric(label="🟢 Candidato A (Votos Atuais)", value=f"{dados['candidato_a_votos']:,}", delta=f"{pct_atual_a:.2f}%")
    st.metric(label="🔵 Candidato B (Votos Atuais)", value=f"{dados['candidato_b_votos']:,}", delta=f"{pct_atual_b:.2f}%")

with col2:
    st.markdown("### 🔮 Projeção Matemático-Estatística")
    if progresso < 15:
        st.warning("⚠️ Dados insuficientes para uma projeção confiável. Aguarde mais urnas.")
    else:
        st.success("✅ Tendência estatística calculada com sucesso!")
        
    st.metric(label="🔮 Candidato A (Resultado Final Estimado)", value=f"{proj_a:.2f}%")
    st.metric(label="🔮 Candidato B (Resultado Final Estimado)", value=f"{proj_b:.2f}%")

st.info("💡 Este sistema está rodando em modo simulação. Para usar com dados reais de eleições, basta integrar a URL da API oficial à função de busca de dados.")
