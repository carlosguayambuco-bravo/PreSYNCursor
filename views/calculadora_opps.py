# Estándar usando Pep8
# Librerías de Python
# Librerías de Terceros
import streamlit as st
# Librerías Locales
from ui.calculadora_components import mostrar_calculadora_individual

# Calculadora con 2 Componentes Principales:
# - Calculadora Individual por Referencia
# - Calculadora Grande de Referencias Asignadas

st.header("🧮 Calculadora de Oportunidades" )

# Agregamos en Detalle la documentación de las Oportunidades
with st.expander("📖 Documentación de Oportunidades"):
    with open("docs/OPORTUNIDADES.md", "r", encoding="utf-8") as f:
        st.markdown(f.read())

st.divider()

# Creamos 2 Tabs: Cálculadora Individual y Calculadora de Referencias Asignadas
tabIndividual, tabMasivas = st.tabs(["😁 Calculadora por Referencia", "🛠️ Oportunidades Masivas"], on_change="rerun")

if tabIndividual.open:
    mostrar_calculadora_individual()

if tabMasivas.open:
    pass