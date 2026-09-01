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
from modules.gest_sols import generar_descarga_masiva_solicitudes, get_massive_solicitudes_txt, obtener_mascara_sin_responder, reiniciar_filtros_solicitudes_ejecutivo, subir_masivo_plantilla_solicitudes
from ui.solicitudes_components import dialog_confirmar_actualizacion_solicitudes, dialog_confirmar_actualizacion_vencidas, mostrar_filtros_generales_solicitud_ejecutivo, mostrar_datos_solicitud_ejecutivo, mostrar_resumen_solicitudes_ejecutivo, mostrar_solicitudes_paginadas

# Paso 1: Cargar las Solicitudes MEC
solicitudes_df = load_current_month_solicitudes()
# Paso 2: Mostrar los Filtros Generales de Solicitud
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

if tabSolicitudes.open:
    with tabSolicitudes:
        st.title("🗒️ Gestión de Solicitudes")

        st.divider()
        st.space("small")

        if solicitudes_filtered.empty:
            st.warning("No se encontraron solicitudes que coincidan con los filtros aplicados.", icon="⚠️")
            st.stop()  # Detenemos la ejecución del script si no hay solicitudes que mostrar

        # Paso 4: Mostrar las Solicitudes Paginadas (10-20-30-40 por página)
        mostrar_solicitudes_paginadas(
            solicitudes_df=solicitudes_filtered,
            mostrar_funcion=mostrar_datos_solicitud_ejecutivo,
            key="ejecutivo",
        )

        st.divider()


        # Creamos 2 Columnas: Columna de Portafolio y Columna de Todas las Solicitudes
        colPortafolio, colTodas = st.columns(2)
        with colPortafolio:
            modo_plantilla = st.toggle(
                label="Plantilla en Portafolio",
                value=True,
                help="Generar Plantilla agrupando los Datos de Deudas",
                key="plantilla_en_portafolio_gestionar_solicitudes"
            )
        with colTodas:
            modo_total = st.toggle(
                label="Usar todas las Solicitudes",
                value=False,
                help="Generar Plantilla con todos los datos de solicitudes (inlcuyendo con respuesta)",
                key="plantilla_total_gestionar_solicitudes"
            )

        mask_sin_responder = obtener_mascara_sin_responder(solicitudes_df=solicitudes_filtered)

        # Creamos 5 Botones: Descargar Solicitudes, Subir Solicitudes, Marcar como Solicitado, Marcar como Vencida y Copiar Datos
        colDescargar, colSubir, colMarcar, colVencer, colCopiar = st.columns([2, 2, 2, 2, 1], gap = "small")
        with colDescargar:
            download_bytes = generar_descarga_masiva_solicitudes(
                solicitudes_df=solicitudes_filtered,
                en_portafolio=modo_plantilla,
                usar_total=modo_total,
            )
            st.download_button("Descargar Solicitudes",
                download_bytes,
                file_name="solicitudes.csv",
                mime="text/csv",
                type="primary",
                key="descargar_solicitudes_button",
                help="Haz clic para descargar las solicitudes filtradas completas",
                on_click=upload_log_to_sheets,
                disabled=len(download_bytes)<=0,
                width="stretch",
                kwargs={"info": "Descarga de Solicitudes", "detail": f"{st.session_state['user_email']} descargó {len(solicitudes_filtered)} solicitudes filtradas."},
            )

        with colSubir:
            subido_sheets = st.button("Subir Solicitudes a Sheets",
                key="subir_solicitudes_button",
                help="Haz clic para subir las solicitudes filtradas a Google Sheets",
                type="primary",
                width="stretch",
                disabled = ((mask_sin_responder).sum() == 0) and not modo_total,
                )

        with colCopiar:
            if copy_button(
                get_massive_solicitudes_txt(solicitudes_df=solicitudes_filtered),
                key="copiar_solicitudes_masivas_button",
            ):
                st.toast("Datos de solicitudes copiados al portapapeles", icon="✅")

        with colMarcar:
            if st.button("Marcar como Solicitado",
                key="marcar_solicitudes_button",
                help="Haz clic para marcar las solicitudes filtradas como 'Solicitado'",
                type="primary",
                width="stretch",
                disabled = (mask_sin_responder).sum() == 0,
            ):
                dialog_confirmar_actualizacion_solicitudes(solicitudes=solicitudes_filtered)

        with colVencer:
            if st.button("Marcar como Vencida",
                key="marcar_vencidas_solicitudes_button",
                help="Haz clic para marcar las solicitudes abiertas como 'Vencida' por el cierre del Mes en Curso",
                type="primary",
                width="stretch",
                disabled = (mask_sin_responder).sum() == 0,
            ):
                dialog_confirmar_actualizacion_vencidas(solicitudes=solicitudes_filtered)

        if subido_sheets:
            success = subir_masivo_plantilla_solicitudes(
                solicitudes_df=solicitudes_filtered,
                en_portafolio=modo_plantilla,
                usar_total=modo_plantilla,
                )
            if success:
                st.toast("Las solicitudes filtradas se han subido correctamente a Google Sheets.", icon="✅")
            else:
                st.toast("Ocurrió un error al subir las solicitudes a Google Sheets. Por favor, inténtalo de nuevo.", icon="❌")

# Ahora Creamos el Dashboard
if tabResumenSolicitudes.open:
    with tabResumenSolicitudes:
        try:
            mostrar_resumen_solicitudes_ejecutivo(solicitudes=solicitudes_filtered)
        except Exception as e:
            st.error("Ocurrió un error al generar el resumen de solicitudes: {}".format(str(e)), icon="❌")