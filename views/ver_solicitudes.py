# Estándar usando Pep8
# Librerías de Python
# Librerías de Terceros
import streamlit as st
# Librerías Locales
from data.data_loader import load_current_month_solicitudes
from modules.gest_sols import filtrar_solicitudes_por_usuario_actual, reiniciar_filtros_solicitudes_negociadores
from ui.solicitudes_components import mostrar_filtros_generales_solicitud_negociador

# Paso 1: Cargar el DataFrame de Solicitudes
solicitudes_df = load_current_month_solicitudes()
# Paso 2: Filtar las Solicitudes segun el Usuario
solicitudes_df = filtrar_solicitudes_por_usuario_actual(solicitudes_df=solicitudes_df)

# Creamos la Función de Cambio de Pestaña
def on_change_tab_gest_sols():
    # Si el cambio de pestaña fue a la pestaña de Dashboard, reiniciamos los filtros de solicitudes
    if st.session_state['tabs_ver_solicitudes'] == "😎 Resumen de Solicitudes":
        reiniciar_filtros_solicitudes_negociadores()


# --- Elementos de la Interfaz de Usuario ---
solicitudes_filtered = mostrar_filtros_generales_solicitud_negociador(solicitudes_df=solicitudes_df)

# Si no hay solicitudes, mostramos un mensaje
if solicitudes_filtered.empty:
    st.info("No hay solicitudes para mostrar. Si quieres reinicia los filtros.", icon="ℹ️")
    st.stop()

# Añadimos un Divisor
st.divider()

# Creamos las 2 Pestañas: Ver Solicitudes y Resumen de Solicitudes
tabVer, tabResumen = st.tabs(
    ["📄 Ver Solicitudes", "😎 Resumen de Solicitudes"], 
    on_change=on_change_tab_gest_sols,
    key="tabs_ver_solicitudes",
    width="stretch",
)