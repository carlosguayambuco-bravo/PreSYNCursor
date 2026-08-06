# Estándar usando Pep8
# Librerías de Python
from io import BytesIO
# Librerías de Terceros
import plotly.express as px
import streamlit as st
from st_copy_to_clipboard import st_copy_to_clipboard
# Librerías Locales
from data.data_loader import load_current_month_solicitudes
from data.data_uploader import upload_log_to_sheets
from modules.gest_sols import generar_descarga_masiva_solicitudes, get_massive_solicitudes_txt, obtener_df_bancos_sin_responder, obtener_mascara_sin_responder, obtener_promedio_respuestas_dia, obtener_promedio_tiempos_respuesta, reiniciar_filtros_solicitudes, subir_masivo_plantilla_solicitudes
from ui.solicitudes_components import mostrar_filtros_generales_solicitud, mostrar_datos_solicitud_ejecutivo

# Paso 1: Inicializar el State Session de Cantidad_Solicitudes_Ver
if not ('Cantidad_Solicitudes_Ver' in st.session_state):
    st.session_state['Cantidad_Solicitudes_Ver'] = 10  # Valor por defecto
# Paso 2: Cargar las Solicitudes MEC
solicitudes_df = load_current_month_solicitudes()
# Paso 3: Mostrar los Filtros Generales de Solicitud
solicitudes_filtered = mostrar_filtros_generales_solicitud(solicitudes_df=solicitudes_df)

def on_change_tab_gest_sols():
    # Si el cambio de pestaña fue a la pestaña de Dashboard, reiniciamos los filtros de solicitudes
    if st.session_state['tabs_gestionar_solicitudes'] == "😎 Resumen de Solicitudes":
        reiniciar_filtros_solicitudes(method='reset')

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

    # Paso 4: Mostrar los Primeros N Registros de Solicitudes según la Cantidad_Solicitudes_Ver
    principal_sol = True
    for _, solicitud in solicitudes_filtered.head(st.session_state['Cantidad_Solicitudes_Ver']).iterrows():
        mostrar_datos_solicitud_ejecutivo(solicitud=solicitud, is_main = principal_sol)
        principal_sol = False  # Solo la primera solicitud es la principal, las demás son secundarias

    # Creamos 4 Botones: Cargar Más Solicitudes, Descargar Solicitudes, Subir Solicitudes a Sheets y Copiar Datos de Solicitudes
    colMas, colDescargar, colSubir, colCopiar = st.columns([2, 2, 2, 1], gap = "large")

    with colMas:
        mas_solicitudes =  st.button("Cargar Más Solicitudes",
            key="cargar_mas_solicitudes_button",
            help="Haz clic para cargar más solicitudes",
            disabled = len(solicitudes_df) <= st.session_state['Cantidad_Solicitudes_Ver'],
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
        if st_copy_to_clipboard(
            get_massive_solicitudes_txt(solicitudes_df=solicitudes_filtered),
            key="copiar_solicitudes_masivas_button",
        ):
            st.toast("Datos de solicitudes copiados al portapapeles", icon="✅")

    if subido_sheets:
        success = subir_masivo_plantilla_solicitudes(solicitudes_df=solicitudes_filtered)
        if success:
            st.toast("Las solicitudes filtradas se han subido correctamente a Google Sheets.", icon="✅")

    if mas_solicitudes:
        st.session_state['Cantidad_Solicitudes_Ver'] += 10  # Incrementamos en 10 la cantidad de solicitudes a mostrar

# Ahora Creamos el Dashboard
with tabResumenSolicitudes:
    st.title("😎 Resumen de Solicitudes")
    # Siguiente: Definición del Dashboard de Resumen de Solicitudes
    st.divider()
    # Creamos 2 Columnas: 1 para Pie Graph de Estados de Solicitudes y otra para KPIs
    colPieEstados, colKPIs = st.columns([4, 2], gap = "small", vertical_alignment="center", border=True,)

    with colPieEstados:
        st.subheader("📊 Distribución de Estados de Solicitudes")
        # Creamos el Gráfico de Pie de Estados de Solicitudes
        fig_pie_estados = px.pie(
            solicitudes_filtered,
            names='estado_solicitud',
            title='Distribución de Estados de Solicitudes',
            hole=0.4,
            color_discrete_sequence=px.colors.qualitative.Set3
        )
        st.plotly_chart(fig_pie_estados, use_container_width=True)

    with colKPIs:
        tiempos_respuesta = obtener_promedio_tiempos_respuesta(solicitudes_filtered)
        respuestas_por_dia = obtener_promedio_respuestas_dia(solicitudes_filtered)
        mascara_sin_responder = obtener_mascara_sin_responder(solicitudes_filtered)
        solicitudes_sin_responder = mascara_sin_responder.sum()

        st.subheader("📈 KPIs de Respuesta")
        st.metric(
            "**Solicitudes Sin Responder**", 
            f"{solicitudes_sin_responder} Solicitudes", 
            delta_color= "green" if solicitudes_sin_responder <= 20 else "red"
        )
        st.metric(
            "**Promedio de Tiempo de Respuesta (días)**", 
            f"{tiempos_respuesta['promedio_general']:.2f}",
            delta_color= "green" if tiempos_respuesta['promedio_general'] <= 3 else "red" # type: ignore
        )
        st.metric(
            "**Respuestas por Día**",
            f"{respuestas_por_dia['promedio_general']:.2f}",
            delta_color= "green" if respuestas_por_dia['promedio_general'] >= 10 else "red" # type: ignore
        )
        # Ahora Creamos 2 Popovers para mostrar los detalles de los KPIs
        with st.popover("Respuestas por Día", icon="ℹ️"):
            st.write("**Promedio de Respuestas por Día:**")
            for dia, respuestas in respuestas_por_dia['promedio_por_dia'].items(): # type: ignore
                st.write(f"- {dia}: {respuestas:.2f} respuestas")

        with st.popover("Tiempos por Tipo", icon="ℹ️"):
            st.write("**Promedio de Tiempo de Respuesta por Tipo de Solicitud:**")
            for tipo, tiempo in tiempos_respuesta['promedio_por_tipo'].items(): # type: ignore
                st.write(f"- {tipo}: {tiempo:.2f} días")

    # Añadimos un Divisor
    st.divider()
    # Siguientes Gráficos: Solicitudes sin Responder por Casa de Cobro, Bancos y Ejecutivos
    st.subheader("📊 Solicitudes Sin Responder")

    if solicitudes_sin_responder > 0:
        # La Estructura será: 3 Columnas: Casa de Cobro, Banco y Ejecutivo
        colCasaCobro, colBanco, colEjecutivo = st.columns([3,1,2], gap = "small", vertical_alignment="center", border=True,)

        with colCasaCobro: # La única con gráfico de Barras, además este debe ser vertical
            st.subheader("🥸 Por Casa de Cobro")
            fig_casa_cobro = px.bar(
                mascara_sin_responder.groupby('casa_cobro').size().reset_index(name='count'),
                x='casa_cobro',
                y='count',
                title='Solicitudes Sin Responder por Casa de Cobro',
                color='count',
                orientation='v',
                color_continuous_scale=px.colors.sequential.Viridis
            )
            st.plotly_chart(fig_casa_cobro, use_container_width=True)

        with colBanco: # Mostramos un DF 
            st.subheader("🏦 Por Banco")
            bancos_sin_responder_df = obtener_df_bancos_sin_responder(solicitudes_filtered)
            # Estilizamos el DF para que se vea mejor en Streamlit
            st.dataframe(
                bancos_sin_responder_df.style.format({"Solicitudes Sin Responder": "{:,.0f}"}).background_gradient(cmap='YlGnBu', subset=["Solicitudes Sin Responder"]),
                use_container_width=True,
                hide_index=True
            )

        with colEjecutivo: # Mostramos un Pie
            st.subheader("👨‍💼 Por Ejecutivo")
            fig_ejecutivo = px.pie(
                mascara_sin_responder.groupby('Ejecutivo').size().reset_index(name='count'),
                names='Ejecutivo',
                values='count',
                title='Solicitudes Sin Responder por Ejecutivo',
                hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Set3
            )
            st.plotly_chart(fig_ejecutivo, use_container_width=True)
    else:
        st.success("No hay solicitudes sin responder en este momento.", icon="✅")