# Archivo para Inicializar los Servicios de la Aplicación
# Usando estándar Pep8
# Librerías de Python
# Librerías de Terceros
import streamlit as st
# Librerías Locales
from services.metabase import MetabaseService
from services.google_sheets import GoogleSheetsService

# Creamos el Servicio de Metabase y de GoogleSheets
def initialize_services():
    if "metabase_service" in st.session_state and "google_sheets_service" in st.session_state:
        return  # Los servicios ya están inicializados

    # Inicializamos el Servicio de Metabase
    metabase_username = st.secrets["metabase"]["username"]
    metabase_password = st.secrets["metabase"]["password"]
    metabase_mainDB_id = st.secrets["metabase"]["mainDB_id"]
    metabase_service = MetabaseService(metabase_username, metabase_password, metabase_mainDB_id)

    # Inicializamos el Servicio de GoogleSheets
    google_sheets_credentials = st.secrets["google_sheets"]["credentials"]
    google_sheets_service = GoogleSheetsService(google_sheets_credentials)

    # Guardamos los servicios en el estado de la aplicación para que estén disponibles globalmente
    st.session_state["metabase_service"] = metabase_service
    st.session_state["google_sheets_service"] = google_sheets_service