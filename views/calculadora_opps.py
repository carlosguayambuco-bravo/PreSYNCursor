# Estándar usando Pep8
# Librerías de Python
from pathlib import Path
# Librerías de Terceros
import streamlit as st
# Librerías Locales
from modules.constants import (
    ETIQUETA_TAB_CALCULADORA_INDIVIDUAL,
    ETIQUETA_TAB_CALCULADORA_MASIVA,
    ETIQUETA_TAB_CALCULADORA_RESUMEN,
    LLAVE_REDIRECCION_CALCULADORA,
    LLAVE_TAB_CALCULADORA,
)
from ui.calculadora_components import mostrar_calculadora_individual
from ui.calculadora_masiva_components import mostrar_calculadora_masiva
from ui.calculadora_resumen_components import mostrar_calculadora_resumen

# Calculadora con 3 Componentes Principales:
# - Calculadora Individual por Referencia
# - Calculadora Grande de Referencias Asignadas
# - Resumen Agregado de Oportunidades

st.header("🧮 Calculadora de Oportunidades" )

# Agregamos en Detalle la documentación de las Oportunidades
ruta_documentacion = Path(__file__).resolve().parents[1] / "docs" / "OPORTUNIDADES.md"
with st.expander("📖 Documentación de Oportunidades"):
    with open(ruta_documentacion, "r", encoding="utf-8") as f:
        st.markdown(f.read())

st.divider()

# Si venimos de un redireccionamiento de la vista masiva, cambiamos la pestaña
# antes de instanciar el widget de tabs (no se puede modificar después).
if st.session_state.pop(LLAVE_REDIRECCION_CALCULADORA, False):
    st.session_state[LLAVE_TAB_CALCULADORA] = ETIQUETA_TAB_CALCULADORA_INDIVIDUAL

# Creamos 3 Tabs: Cálculadora Individual, Masiva y Resumen Agregado
tabIndividual, tabMasivas, tabResumen = st.tabs(
    [
        ETIQUETA_TAB_CALCULADORA_INDIVIDUAL,
        ETIQUETA_TAB_CALCULADORA_MASIVA,
        ETIQUETA_TAB_CALCULADORA_RESUMEN,
    ],
    key=LLAVE_TAB_CALCULADORA,
    on_change="rerun",
)

if tabIndividual.open:
    mostrar_calculadora_individual()

if tabMasivas.open:
    mostrar_calculadora_masiva()

if tabResumen.open:
    mostrar_calculadora_resumen()