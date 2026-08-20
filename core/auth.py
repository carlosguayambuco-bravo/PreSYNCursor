# Estándar usando Pep8
# Librerías de Python
import datetime
import json
import secrets
import threading
import time
# Librerías de Terceros
import extra_streamlit_components as stx
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
import jwt
import streamlit as st
from streamlit.runtime.scriptrunner import get_script_run_ctx
# Librerías Locales
from core.users import User
from data.data_loader import load_headcount_negociacion
from views.error_page import error_page_view

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/drive.file",  # Grants access to read and write files created or opened by the app
    "https://www.googleapis.com/auth/gmail.send", # Grants access to send emails on behalf of the user
]

# --- Persistencia de credenciales en cookies (extra-streamlit-components) ---
# Las credenciales de Google se guardan ahora en cookies del navegador en lugar
# de un archivo local: el filesystem no es persistente en Streamlit Cloud, así
# que la sesión solo puede sobrevivir a los reinicios de la app vía cookies.
CREDENTIALS_COOKIE_PREFIX = "google_oauth"
CREDENTIALS_COOKIE_FIELDS = (
    "token",
    "refresh_token",
    "token_uri",
    "client_id",
    "client_secret",
    "scopes",
)
# Tiempo de vida de las cookies de autenticación (días).
CREDENTIALS_COOKIE_MAX_AGE_DAYS = 30

# Claves (keys) de los componentes. Deben ser únicas por ejecución del script:
# Streamlit rechaza instancias duplicadas con la misma clave en una misma corrida.
_COOKIE_KEY_READ = "auth_cookies_read"
_COOKIE_KEY_WRITE = "auth_cookies_write"
_COOKIE_KEY_DELETE = "auth_cookies_delete"

# Memoria por ejecución del script: evita instanciar dos veces el componente de
# lectura cuando initialize_services() y authenticate_user() se ejecutan en la
# misma corrida. threading.local() aísla la memoria por sesión (cada sesión de
# Streamlit corre en su propio hilo).
_read_state = threading.local()


def _cookie_name(field: str) -> str:
    """Nombre de la cookie para un campo de las credenciales."""
    return f"{CREDENTIALS_COOKIE_PREFIX}_{field}"


def _cookie_expiration() -> datetime.datetime:
    """Fecha de expiración de las cookies de autenticación."""
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        days=CREDENTIALS_COOKIE_MAX_AGE_DAYS
    )


def _cookie_secure() -> bool | None:
    """True cuando la app se sirve por HTTPS, para marcar las cookies como Secure."""
    try:
        app_url = st.context.url or ""
        return app_url.startswith("https://")
    except Exception:
        return None


def _cookie_options() -> dict:
    """Opciones comunes para escribir las cookies de autenticación."""
    return {
        "path": "/",
        "expires_at": _cookie_expiration(),
        "secure": _cookie_secure(),
        "same_site": "strict",
    }


def _reader_registered_this_run() -> bool:
    """True si el componente de lectura de cookies ya se instanció en esta corrida."""
    ctx = get_script_run_ctx()
    if ctx is None:
        return False
    return _COOKIE_KEY_READ in ctx.shared.widget_user_keys_this_run


def load_saved_credentials() -> dict | None:
    """Loads the Google OAuth credentials persisted in browser cookies, if available.

    The CookieManager component can only be instantiated once per script run
    (Streamlit rejects duplicate element keys), so the result is memoized for
    the rest of the current run.
    """
    if _reader_registered_this_run():
        return getattr(_read_state, "result", None)

    credentials = None
    try:
        cookie_manager = stx.CookieManager(key=_COOKIE_KEY_READ)
        raw_values = {
            field: cookie_manager.get(_cookie_name(field))
            for field in CREDENTIALS_COOKIE_FIELDS
        }
        if raw_values.get("token"):
            credentials = {
                "token": raw_values["token"],
                "refresh_token": raw_values.get("refresh_token"),
                "token_uri": raw_values.get("token_uri"),
                "client_id": raw_values.get("client_id"),
                "client_secret": raw_values.get("client_secret"),
                "scopes": json.loads(raw_values.get("scopes") or "[]"),
            }
    except Exception:
        credentials = None

    _read_state.result = credentials
    return credentials


def save_credentials(credentials: Credentials) -> dict:
    """Persists the OAuth credentials as browser cookies for Streamlit reruns.

    Se guarda un campo por cookie para respetar el límite de ~4KB por cookie
    (los tokens de acceso de Google pueden ser largos).
    """
    credentials_data = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes,
    }
    cookies = {
        _cookie_name(field): (
            json.dumps(value or []) if field == "scopes" else (value or "")
        )
        for field, value in credentials_data.items()
    }
    cookie_manager = stx.CookieManager(key=_COOKIE_KEY_WRITE)
    cookie_manager.batch_set(cookies, **_cookie_options())
    return credentials_data


def delete_saved_credentials() -> None:
    """Removes the credentials cookies during logout."""
    cookie_manager = stx.CookieManager(key=_COOKIE_KEY_DELETE)
    for index, field in enumerate(CREDENTIALS_COOKIE_FIELDS):
        try:
            cookie_manager.delete(_cookie_name(field), key=f"delete_{index}")
        except KeyError:
            # La cookie no existe en el snapshot del componente: nada que borrar.
            pass


def generate_jwt_token(cv: str) -> str:
    """Generates a JWT token with a short expiration time."""
    payload = {
        "cv": cv,
        "iat": time.time(),
        "exp": time.time() + 60000,  # Token expires in 10 minutes
        "nonce": secrets.token_urlsafe(16)  # Random nonce for added security
    }

    state = jwt.encode(payload, st.secrets["google_oauth"]["jwt_auth"], algorithm="HS256")
    return state

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
    # Create a code_verifier and generate a state token
    code_verifier = secrets.token_urlsafe(64)
    # Save it into the flow
    flow.code_verifier = code_verifier

    state = generate_jwt_token(code_verifier)
    auth_url, _ = flow.authorization_url(
        access_type="offline",  
        prompt="consent",
        include_granted_scopes="true",
        state=state,
    )

    return auth_url

def get_user_info_from_credentials():
    """Fetches user info (email, name) from Google using active credentials."""

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

    # Guardamos el Nombre del Usuario en el Session State
    st.session_state['user_name'] = user_row['Nombre']

    # Ahora, si 'Es_Negociador' es True, entonces devolvemos 'nego'
    if user_row['Es_Negociador']:
        return 'nego'
    # Caso 2: Si Nombre_Empleo == 'Encargado de Negociación', entonces devolvemos 'leader'
    if user_row['Nombre_Empleo'] == 'Encargado de Negociación' or user_row['Nombre_Empleo'] == 'Team Leader Negociación':
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
    """Creates a User object from the active OAuth credentials."""
    if "credentials" in st.session_state and "creds_google" in st.session_state:
        creds = st.session_state["credentials"]
        user_info = get_user_info_from_credentials()
        # Guardamos el Email en el Session_State
        st.session_state["user_email"] = user_info.get("email", "Unknown")

        user_role = get_user_role(user_info.get("email", "Unknown"))

        # Guardamos el user_role en el Session_State
        st.session_state["user_role"] = user_role

        return User(
            name=user_info.get("name", "Unknown"),
            email=user_info.get("email", "Unknown"),
            creds=creds,
            role=user_role  # Ajusta esto según la lógica de tu aplicación # type: ignore
        )

def authenticate_user():
    """Restores saved credentials or handles the Google OAuth callback."""
    params = st.query_params

    if "credentials" not in st.session_state:
        saved_credentials = load_saved_credentials()
        if saved_credentials is not None:
            st.session_state["credentials"] = saved_credentials
            st.session_state["creds_google"] = Credentials.from_authorized_user_info(
                saved_credentials,
                scopes=SCOPES,
            )

    if "code" in params and "user_obj" not in st.session_state:
        try:
            code = params["code"]
            flow = create_flow()

            # Obtain the cv from the state parameter and decode it
            state = params.get("state",'')
            payload = jwt.decode(state, st.secrets["google_oauth"]["jwt_auth"], algorithms=["HS256"])
            code_verifier = payload.get("cv")

            # Validamos la Expiración del Token
            current_time = time.time()
            if current_time > payload.get("exp", 0):
                error_page_view("El token de autenticación ha expirado. Por favor, intenta iniciar sesión nuevamente.")

            flow.code_verifier = code_verifier  # Set the code_verifier for PKCE

            flow.fetch_token(code=code)
            
            creds = flow.credentials
            credentials_data = save_credentials(creds) # type: ignore
            st.session_state["credentials"] = credentials_data

            st.session_state["creds_google"] = Credentials.from_authorized_user_info(
                credentials_data,
                scopes=SCOPES,
            )
            
            st.query_params.clear()

            # Guardamos el Usuario
            st.session_state["user_obj"] = create_user_from_session()

            st.rerun()
        except Exception as e:
            st.error(f"Error durante la autenticación: {e}", icon="🚨")
            st.info("Por favor, intenta iniciar sesión nuevamente.", icon="ℹ️")
            # Volvemos a generar la URL guardandola en auth_url
            st.session_state["auth_url"] = get_auth_url()
    elif "credentials" in st.session_state and "user_obj" not in st.session_state:
        st.session_state["user_obj"] = create_user_from_session()
