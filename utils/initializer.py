# Archivo para Inicializar los Servicios de la Aplicación
# Usando estándar Pep8
# Librerías de Python
import json
# Librerías de Terceros
import streamlit as st
# Librerías Locales
from data.data_loader import load_addendums, load_aliados_dataframe, load_app_config, load_cartera_activa, load_client_balances, load_current_month_solicitudes, load_headcount_negociacion, load_liquidaciones, load_masivas, load_pab_ideal, load_reference_changes, load_special_user_permissions
from modules.classes import crear_diccionario_aliados
from services.metabase import MetabaseService
from services.google_sheets import GoogleSheetsService

# Creamos el Servicio de Metabase y de GoogleSheets
def initialize_services(debugging_mode: bool = False):
    if "metabase_service" in st.session_state and "google_sheets_service" in st.session_state:
        return  # Los servicios ya están inicializados

    # Inicializamos el Servicio de Metabase
    metabase_username = st.secrets["metabase"]["username"]
    metabase_password = st.secrets["metabase"]["password"]
    metabase_mainDB_id = st.secrets["metabase"]["mainDB_id"]
    metabase_service = MetabaseService(metabase_username, metabase_password, metabase_mainDB_id)

    if debugging_mode:
        st.success("Metabase Service Initialized")

    # Inicializamos el Servicio de GoogleSheets
    google_sheets_credentials = json.loads(st.secrets["google_credentials"]['json'])
    google_sheets_service = GoogleSheetsService(google_sheets_credentials)

    if debugging_mode:
        st.success("Google Sheets Service Initialized")

    # Guardamos los servicios en el estado de la aplicación para que estén disponibles globalmente
    st.session_state["metabase_service"] = metabase_service
    st.session_state["google_sheets_service"] = google_sheets_service

# Función Auxiliar para Inicializar los Datos
def initialize_data(debugging_mode: bool = False):
    if not ("solicitudes_mec_df" in st.session_state):
        st.session_state["solicitudes_mec_df"] = load_current_month_solicitudes()
        if debugging_mode:
            st.success("Current Month Solicitudes Loaded")
    if not ("changes_references_dict" in st.session_state):
        st.session_state["changes_references_dict"] = load_reference_changes()
        if debugging_mode:
            st.success("Reference Changes Loaded")
    if not ("saldos_dict" in st.session_state):
        st.session_state["saldos_dict"] = load_client_balances()
        if debugging_mode:
            st.success("Client Balances Loaded")
    if not ("pab_ideal_dict" in st.session_state):
        st.session_state["pab_ideal_dict"] = load_pab_ideal()
        if debugging_mode:
            st.success("PaB Ideal Loaded")
    if not ("masivas_df" in st.session_state):
        st.session_state["masivas_df"] = load_masivas()
        if debugging_mode:
            st.success("Masivas Loaded")
    if not ("addendums_df" in st.session_state):
        st.session_state["addendums_df"] = load_addendums()
        if debugging_mode:
            st.success("Addendums Loaded")
    if not ("liquidations_set" in st.session_state):
        st.session_state["liquidations_set"] = load_liquidaciones()
        if debugging_mode:
            st.success("Liquidations Set Initialized")
    if not ("headcount_df" in st.session_state):
        st.session_state["headcount_df"] = load_headcount_negociacion()
        if debugging_mode:
            st.success("Headcount Data Loaded")
    if not ("app_config_dict" in st.session_state):
        st.session_state["app_config_dict"] = load_app_config()
        if debugging_mode:
            st.success("App Config Loaded")
    if not ("special_user_permissions_dict" in st.session_state):
        st.session_state["special_user_permissions_dict"] = load_special_user_permissions()
        if debugging_mode:
            st.success("Special User Permissions Loaded")
    if not ("cartera_activa_df" in st.session_state):
        st.session_state["cartera_activa_df"] = load_cartera_activa()
        if debugging_mode:
            st.success("Cartera Activa Loaded")
    if not ("aliados_dict" in st.session_state):
            aliados_df = load_aliados_dataframe()
            st.session_state["aliados_dict"] = crear_diccionario_aliados(aliados_df)
            if debugging_mode:
                st.success("Aliados Loaded")

# Función Auxiliar para Inicializar Estados de prueba
def initialize_test_states():
    if "user_email" not in st.session_state:
        st.session_state["user_email"] = "maurcio.valencia@gobravo.com.co"