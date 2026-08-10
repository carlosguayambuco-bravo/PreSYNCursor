# Estándar usando Pep8
# Librerías de Python
from io import BytesIO
# Librerías de Terceros
import plotly.express as px
from st_copy import copy_button
import streamlit as st
# Librerías Locales
from data.data_loader import load_current_month_solicitudes
from data.data_uploader import upload_log_to_sheets
from modules.gest_sols import generar_descarga_masiva_solicitudes, get_massive_solicitudes_txt, obtener_df_bancos_sin_responder, obtener_mascara_sin_responder, obtener_promedio_respuestas_dia, obtener_promedio_tiempos_respuesta, reiniciar_filtros_solicitudes_ejecutivo, subir_masivo_plantilla_solicitudes
from ui.solicitudes_components import mostrar_filtros_generales_solicitud_ejecutivo, mostrar_datos_solicitud_ejecutivo, mostrar_resumen_solicitudes_ejecutivo

# Paso 1: Inicializar el State Session de Cantidad_Solicitudes_Ver_Ejecutivo
if not ('Cantidad_Solicitudes_Ver_Ejecutivo' in st.session_state):
    st.session_state['Cantidad_Solicitudes_Ver_Ejecutivo'] = 10  # Valor por defecto
# Paso 2: Cargar las Solicitudes MEC
solicitudes_df = load_current_month_solicitudes()
# Paso 3: Mostrar los Filtros Generales de Solicitud
solicitudes_filtered = mostrar_filtros_generales_solicitud_ejecutivo(solicitudes_df=solicitudes_df)

def on_change_tab_gest_sols():
    # Si el cambio de pestaña fue a la pestaña de Dashboard, reiniciamos los filtros de solicitudes
    if st.session_state['tabs_gestionar_solicitudes'] == "😎 Resumen de Solicitudes":
        reiniciar_filtros_solicitudes_ejecutivo(method='reset')

# Vamos a Crear 2 Sub-Páginas: Una para mostrar las Soliciutdes y otra para mostrar un Dashboard
tabSolicitudes, tabResumenSolicitudes = st.tabs(
    ["🗒️ Solicitudes", "😎 Resumen de Solicitudes"],
    key = "tabs_gestionar_solicitudes",
    width="stretch",
    on_change=on_change_tab_gest_sols
)

with tabSolicitudes:
    st.title("🗒️ Gestión de Solicitudes")

    st.divider()
    st.space("small")

    if solicitudes_filtered.empty:
        st.warning("No se encontraron solicitudes que coincidan con los filtros aplicados.", icon="⚠️")
        st.stop()  # Detenemos la ejecución del script si no hay solicitudes que mostrar

    # Paso 4: Mostrar los Primeros N Registros de Solicitudes según la Cantidad_Solicitudes_Ver_Ejecutivo
    principal_sol = True
    for _, solicitud in solicitudes_filtered.head(st.session_state['Cantidad_Solicitudes_Ver_Ejecutivo']).iterrows():
        mostrar_datos_solicitud_ejecutivo(solicitud=solicitud, is_main = principal_sol)
        principal_sol = False  # Solo la primera solicitud es la principal, las demás son secundarias

    # Creamos 4 Botones: Cargar Más Solicitudes, Descargar Solicitudes, Subir Solicitudes a Sheets y Copiar Datos de Solicitudes
    colMas, colDescargar, colSubir, colCopiar = st.columns([2, 2, 2, 1], gap = "large")

    with colMas:
        mas_solicitudes =  st.button("Cargar Más Solicitudes",
            key="cargar_mas_solicitudes_button",
            help="Haz clic para cargar más solicitudes",
            disabled = len(solicitudes_df) <= st.session_state['Cantidad_Solicitudes_Ver_Ejecutivo'],
            type="secondary"
        )
    with colDescargar:
        st.download_button("Descargar Solicitudes",
            generar_descarga_masiva_solicitudes(solicitudes_df=solicitudes_filtered),
            file_name="solicitudes.csv",
            mime="text/csv",
            type="primary",
            key="descargar_solicitudes_button",
            help="Haz clic para descargar las solicitudes filtradas completas",
            on_click=upload_log_to_sheets,
            kwargs={"info": "Descarga de Solicitudes", "detail": f"{st.session_state['user_email']} descargó {len(solicitudes_filtered)} solicitudes filtradas."},
        )

    with colSubir:
        subido_sheets = st.button("Subir Solicitudes a Sheets",
            key="subir_solicitudes_button",
            help="Haz clic para subir las solicitudes filtradas a Google Sheets",
            type="primary",
            disabled = len(solicitudes_filtered) == 0,
            )

    with colCopiar:
        if copy_button(
            get_massive_solicitudes_txt(solicitudes_df=solicitudes_filtered),
            key="copiar_solicitudes_masivas_button",
        ):
            st.toast("Datos de solicitudes copiados al portapapeles", icon="✅")

    if subido_sheets:
        success = subir_masivo_plantilla_solicitudes(solicitudes_df=solicitudes_filtered)
        if success:
            st.toast("Las solicitudes filtradas se han subido correctamente a Google Sheets.", icon="✅")

    if mas_solicitudes:
        st.session_state['Cantidad_Solicitudes_Ver_Ejecutivo'] += 10  # Incrementamos en 10 la cantidad de solicitudes a mostrar

# Ahora Creamos el Dashboard
with tabResumenSolicitudes:
    mostrar_resumen_solicitudes_ejecutivo(solicitudes=solicitudes_filtered)