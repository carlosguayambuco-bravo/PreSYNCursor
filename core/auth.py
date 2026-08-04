# Estándar usando Pep8
# Librerías de Python
# Librerías de Terceros
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import streamlit as st
# Librerías Locales
from core.users import User
from data.data_loader import load_headcount_negociacion
from views.error_page import error_page_view

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/drive.file"  # Grants access to files created/opened by this app
]

def create_flow():
    """Initializes the OAuth 2.0 Flow using secrets."""
    return Flow.from_client_config(
        {
            "web": {
                "client_id": st.secrets["google_oauth"]["client_id"],
                "client_secret": st.secrets["google_oauth"]["client_secret"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
        redirect_uri=st.secrets["google_oauth"]["redirect_uri"],
    )

def get_auth_url():
    """Generates Google login URL with access_type=offline to get refresh tokens."""
    flow = create_flow()
    auth_url, _ = flow.authorization_url(
        prompt="consent",
        access_type="offline",
        include_granted_scopes="true"
    )
    return auth_url

def get_user_info_from_credentials():
    """Fetches user info (email, name) from Google using the credentials stored in session state."""

    service = build("oauth2", "v2", credentials=st.session_state["creds_google"])
    user_info = service.userinfo().get().execute()
    return user_info

def get_user_role(email: str) -> str:

    # Si el Email es Desconocido, entonces mostramos error
    if email == "Unknown":
        error_page_view("No se pudo obtener el correo del usuario. Por favor, contacte al administrador.")
        st.stop()

    # Primero Cargamos los Datos del headcount
    headcount_data = load_headcount_negociacion()
    # Ahora Obtenemos la Fila para dicho Email
    user_row = headcount_data[headcount_data['Correo'] == email]
    # Si esta vacio, entonces devolvemos 'nego'
    if user_row.empty:
        # Mostramos un Mensaje de Error en la Aplicación
        error_page_view(f"El correo {email} no está registrado en el headcount de negociación. Por favor, contacte al administrador.")
        st.stop()
    # Obtenemos la Fila
    user_row = user_row.iloc[0]
    # Ahora, si 'Es_Negociador' es True, entonces devolvemos 'nego'
    if user_row['Es_Negociador']:
        return 'nego'
    # Caso 2: Si Nombre_Empleo == 'Encargado de Negociación', entonces devolvemos 'leader'
    if user_row['Nombre_Empleo'] == 'Encargado de Negociación':
        return 'leader'
    # Caso 3: Si Nombre_Empleo contiene gerente o analista, entonces devolvemos 'admin'
    if 'gerente' in user_row['Nombre_Empleo'].lower() or 'analista' in user_row['Nombre_Empleo'].lower():
        return 'admin'
    # Caso 4: Si Nombre_Empleo == 'Ejecutivo Jr', entonces devolvemos 'executive'
    if user_row['Nombre_Empleo'] == 'Ejecutivo Jr':
        return 'executive'

    # Mostramos un Mensaje de Error en la Aplicación
    error_page_view(f"El correo {email} no tiene un rol definido en el headcount de negociación. Por favor, contacte al administrador.")
    st.stop()

def create_user_from_session():
    """Creates a User object from session state credentials."""
    if "credentials" in st.session_state:
        creds = st.session_state["credentials"]
        user_info = get_user_info_from_credentials()
        # Guardamos el Email en el Session_State
        st.session_state["user_email"] = user_info.get("email", "Unknown")

        user_role = get_user_role(user_info.get("email", "Unknown"))
        return User(
            name=user_info.get("name", "Unknown"),
            email=user_info.get("email", "Unknown"),
            creds=creds,
            role=user_role  # Ajusta esto según la lógica de tu aplicación # type: ignore
        )

def authenticate_user():
    """Handles query params after Google redirects back to Streamlit."""
    # Read query params
    params = st.query_params

    # 1. Check if returning from Google Auth with code
    if "code" in params and "credentials" not in st.session_state:
        code = params["code"]
        flow = create_flow()
        flow.fetch_token(code=code)
        
        # Save OAuth credentials (Access token, Refresh token, Scopes) into Session State
        creds = flow.credentials
        st.session_state["credentials"] = {
            "token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_uri": creds.token_uri, # type: ignore
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "scopes": creds.scopes
        }

        # Guardamos el Session State de las Credenciales
        st.session_state["creds_google"] = Credentials.from_authorized_user_info(st.session_state["credentials"])
        
        # Clear URL parameters to keep address bar clean
        st.query_params.clear()

        # Guardamos el Usuario
        st.session_state["user_obj"] = create_user_from_session()

        st.rerun()