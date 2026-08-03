# Estándar usando Pep8
# Librerías de Python
from io import BytesIO
# Librerías de Terceros
import streamlit as st
# Librerías Locales
from data.data_loader import load_current_month_solicitudes
from data.data_uploader import upload_log_to_sheets
from modules.gest_sols import generar_descarga_masiva_solicitudes
from ui.solicitudes_components import mostrar_filtros_generales_solicitud, mostrar_datos_solicitud_ejecutivo

# Aquí consta de 3 vistas:
# Solicitudes Pendientes por Gestionar
# Solicitudes ya Gestionadas
# Descarga de Solicitudes

def gestionar_solicitudes():
    """
    Función principal para gestionar las solicitudes.
    Esta función maneja la visualización y gestión de solicitudes pendientes y ya gestionadas.
    """
    # Paso 1: Inicializar el State Session de Cantidad_Solicitudes_Ver
    if not ('Cantidad_Solicitudes_Ver' in st.session_state):
        st.session_state['Cantidad_Solicitudes_Ver'] = 10  # Valor por defecto
    # Paso 2: Cargar las Solicitudes MEC
    solicitudes_df = load_current_month_solicitudes()
    # Paso 3: Mostrar los Filtros Generales de Solicitud
    solicitudes_df = mostrar_filtros_generales_solicitud(solicitudes_df=solicitudes_df)

    if solicitudes_df.empty:
        st.warning("No se encontraron solicitudes que coincidan con los filtros aplicados.", icon="⚠️")
        return

    # Paso 4: Mostrar los Primeros N Registros de Solicitudes según la Cantidad_Solicitudes_Ver
    principal_sol = True
    for _, solicitud in solicitudes_df.head(st.session_state['Cantidad_Solicitudes_Ver']).iterrows():
        mostrar_datos_solicitud_ejecutivo(solicitud=solicitud, is_main = principal_sol)
        principal_sol = False  # Solo la primera solicitud es la principal, las demás son secundarias

    # Creamos 2 Botonos: 1 Añadir Más Solicitudes y el otro para Descargar las Solicitudes Dados dichos Filtros
    colMas, colDescargar = st.columns([1, 1], gap = "large")

    with colMas:
        mas_solicitudes =  st.button("Cargar Más Solicitudes",
                    key="cargar_mas_solicitudes_button",
                    help="Haz clic para cargar más solicitudes"
                    )
    with colDescargar:
        st.download_button("Descargar Solicitudes",
                    generar_descarga_masiva_solicitudes(solicitudes_df=solicitudes_df),
                    file_name="solicitudes.csv",
                    mime="text/csv",
                    key="descargar_solicitudes_button",
                    help="Haz clic para descargar las solicitudes filtradas completas",
                    on_click=upload_log_to_sheets,
                    kwargs={"info": "Descarga de Solicitudes", "detail": f"Se descargaron {len(solicitudes_df)} solicitudes filtradas."},
                    )

    if mas_solicitudes:
        st.session_state['Cantidad_Solicitudes_Ver'] += 10  # Incrementamos en 10 la cantidad de solicitudes a mostrar