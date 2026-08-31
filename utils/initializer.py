# Archivo para Inicializar los Servicios de la Aplicación
# Usando estándar Pep8
# Librerías de Python
import json
# Librerías de Terceros
from google.oauth2.credentials import Credentials
import streamlit as st
# Librerías Locales
from core.auth import SCOPES, load_saved_credentials
from data.data_loader import load_addendums, load_aliados_dataframe, load_app_config, load_client_balances, load_current_month_solicitudes, load_headcount_negociacion, load_liquidaciones, load_masivas, load_pab_ideal, load_reference_changes, load_special_user_permissions # type: ignore
from modules.classes import crear_diccionario_aliados
from services import MetabaseService, GoogleSheetsService, GoogleMailService, GoogleDriveService

# Creamos el Servicio de Metabase y de GoogleSheets
def initialize_services(debugging_mode: bool = False):
    if "credentials" not in st.session_state:
        saved_credentials = load_saved_credentials()
        if saved_credentials is not None:
            st.session_state["credentials"] = saved_credentials
            st.session_state["creds_google"] = Credentials.from_authorized_user_info(
                saved_credentials,
                scopes=SCOPES,
            )

    if ("metabase_service" in st.session_state) and ("google_sheets_service" in st.session_state) and ("google_mail_service" in st.session_state) and ("google_drive_service" in st.session_state):
        return  # Los servicios ya están inicializados

    # Inicializamos el Servicio de Metabase
    if not ("metabase_service" in st.session_state):
        metabase_username = st.secrets["metabase"]["username"]
        metabase_password = st.secrets["metabase"]["password"]
        metabase_mainDB_id = st.secrets["metabase"]["mainDB_id"]
        st.session_state["metabase_service"] = MetabaseService(metabase_username, metabase_password, metabase_mainDB_id)

        if debugging_mode:
            st.success("Metabase Service Initialized")

    # Cargamos las credenciales de la cuenta de servicio de Google desde los secretos
    google_credentials = json.loads(st.secrets["google_credentials"]['json'])

    # Inicializamos el Servicio de GoogleSheets
    if not ("google_sheets_service" in st.session_state):
        st.session_state["google_sheets_service"] = GoogleSheetsService(google_credentials)
        if debugging_mode:
            st.success("Google Sheets Service Initialized")

    # Inicializamos el Servicio de GoogleMail (usando creds_google)
    if "creds_google" in st.session_state and not ("google_mail_service" in st.session_state):
        google_mail_service = GoogleMailService(st.session_state["creds_google"])
        st.session_state["google_mail_service"] = google_mail_service
        if debugging_mode:
            st.success("Google Mail Service Initialized")

    # Inicializamos el Servicio de GoogleDrive (usando google_credentials si no hay creds_google)
    if not ("google_drive_service" in st.session_state):
        st.session_state["google_drive_service"] = GoogleDriveService(google_credentials)

        if debugging_mode:
            st.success("Google Drive Service Initialized")

# Función Auxiliar para Inicializar los Datos
def initialize_data(debugging_mode: bool = False):
    anyChange = False
    if not ("solicitudes_mec_df" in st.session_state):
        st.session_state["solicitudes_mec_df"] = load_current_month_solicitudes()
        anyChange = True
        if debugging_mode:
            st.success("Current Month Solicitudes Loaded")
    if not ("changes_references_dict" in st.session_state):
        st.session_state["changes_references_dict"] = load_reference_changes()
        anyChange = True
        if debugging_mode:
            st.success("Reference Changes Loaded")
    if not ("saldos_dict" in st.session_state):
        st.session_state["saldos_dict"] = load_client_balances()
        anyChange = True
        if debugging_mode:
            st.success("Client Balances Loaded")
    if not ("pab_ideal_dict" in st.session_state):
        st.session_state["pab_ideal_dict"] = load_pab_ideal()
        anyChange = True
        if debugging_mode:
            st.success("PaB Ideal Loaded")
    if not ("masivas_df" in st.session_state):
        st.session_state["masivas_df"] = load_masivas()
        anyChange = True
        if debugging_mode:
            st.success("Masivas Loaded")
    if not ("addendums_df" in st.session_state):
        st.session_state["addendums_df"] = load_addendums()
        anyChange = True
        if debugging_mode:
            st.success("Addendums Loaded")
    if not ("liquidations_set" in st.session_state):
        st.session_state["liquidations_set"] = load_liquidaciones()
        anyChange = True
        if debugging_mode:
            st.success("Liquidations Set Initialized")
    if not ("headcount_df" in st.session_state):
        st.session_state["headcount_df"] = load_headcount_negociacion()
        anyChange = True
        if debugging_mode:
            st.success("Headcount Data Loaded")
    if not ("app_config_dict" in st.session_state):
        st.session_state["app_config_dict"] = load_app_config()
        anyChange = True
        if debugging_mode:
            st.success("App Config Loaded")
    if not ("special_user_permissions_dict" in st.session_state):
        anyChange = True
        st.session_state["special_user_permissions_dict"] = load_special_user_permissions()
        if debugging_mode:
            st.success("Special User Permissions Loaded")
    if not ("aliados_dict" in st.session_state):
        anyChange = True
        aliados_df = load_aliados_dataframe()
        st.session_state["aliados_dict"] = crear_diccionario_aliados(aliados_df)
        if debugging_mode:
            st.success("Aliados Loaded")

    if anyChange:
        st.toast("✅Datos Inicializados con Éxito", icon="⏳")
        st.rerun()

# Función Auxiliar para Inicializar Estados de prueba
def initialize_test_states():
    if "user_email" not in st.session_state:
        st.session_state["user_email"] = "maurcio.valencia@gobravo.com.co"