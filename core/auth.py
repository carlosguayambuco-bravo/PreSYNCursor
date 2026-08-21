# Estándar usando Pep8
# Librerías de Python
import base64
import datetime
import hashlib
import json
import os
import secrets
import tempfile
import threading
import time
from pathlib import Path

# Librerías de Terceros
import jwt
import streamlit as st
from cryptography.fernet import Fernet
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

try:
    import extra_streamlit_components as stx
except ImportError:  # Sin el paquete, la persistencia queda solo en archivo local.
    stx = None

# Librerías Locales
from core.users import User
from data.data_loader import load_headcount_negociacion
from views.error_page import error_page_view

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/drive.file",  # Grants access to read and write files created or opened by the app
    "https://www.googleapis.com/auth/gmail.send",  # Grants access to send emails on behalf of the user
]

# --- Configuración de la persistencia de credenciales ---
# Las credenciales de Google se persisten en dos capas redundantes:
#   1. Cookies del navegador: sobreviven a recargas de página y reinicios de
#      la app (el filesystem no es persistente en Streamlit Cloud).
#   2. Archivo local cifrado con Fernet: sobrevive incluso si el navegador
#      bloquea o no envía las cookies.
CREDENTIALS_COOKIE_PREFIX = "google_oauth"
CREDENTIALS_COOKIE_FIELDS = (
    "token",
    "refresh_token",
    "token_uri",
    "client_id",
    "client_secret",
    "scopes",
    "expiry",
)
# Tiempo de vida de las cookies de autenticación (días).
CREDENTIALS_COOKIE_MAX_AGE_DAYS = 30

# Ubicación del archivo local encriptado con las credenciales.
CREDENTIALS_FILE_DIRNAME = ".presyncursor"
CREDENTIALS_FILE_NAME = "google_credentials.enc"

# Claves (keys) de los componentes de cookies. Deben ser únicas por ejecución
# del script: Streamlit rechaza instancias duplicadas con la misma clave.
_COOKIE_KEY_READ = "auth_cookies_read"
_COOKIE_KEY_WRITE = "auth_cookies_write"
_COOKIE_KEY_DELETE = "auth_cookies_delete"

# Memoria por ejecución del script. Cada rerun de Streamlit corre en un hilo
# nuevo, así que threading.local() aísla correctamente estos valores por corrida.
_run_state = threading.local()


# ---------------------------------------------------------------------------
# Almacén privado de la sesión (st.cache_resource con scope="session")
# ---------------------------------------------------------------------------
@st.cache_resource(scope="session", show_spinner=False)
def _session_store() -> dict:
    """Almacén privado de la sesión con las credenciales de respaldo y la marca
    de sesión autenticada.

    Con scope="session", sobrevive a st.session_state.clear() (se usa para
    detectar el cierre de sesión) y se descarta automáticamente cuando la
    sesión de Streamlit se desconecta.
    """
    return {}


def _cache_credentials(credentials_data: dict) -> None:
    """Guarda las credenciales en el almacén privado de la sesión."""
    _session_store()["credentials"] = dict(credentials_data)


def load_cached_credentials() -> dict | None:
    """Devuelve las credenciales del almacén privado de la sesión, si existen.

    Es el último recurso para restaurar las credenciales cuando no están ni en
    el session_state, ni en las cookies, ni en el archivo local.
    """
    cached = _session_store().get("credentials")
    return dict(cached) if cached else None


def clear_cached_credentials() -> None:
    """Elimina las credenciales del almacén privado de la sesión."""
    _session_store().clear()


# ---------------------------------------------------------------------------
# Serialización de credenciales de Google
# ---------------------------------------------------------------------------
def _normalize_expiry(expiry) -> str | None:
    """Normaliza una fecha de expiración al formato esperado por google-auth.

    google-auth solo entiende "YYYY-MM-DDTHH:MM:SS.ffffffZ" en
    from_authorized_user_info; aquí se tolera cualquier formato ISO 8601.
    """
    if not expiry:
        return None
    if isinstance(expiry, datetime.datetime):
        return expiry.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    try:
        parsed = datetime.datetime.fromisoformat(str(expiry).replace("Z", "+00:00"))
        return parsed.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        return None


def _normalized_credentials_data(credentials_data: dict) -> dict:
    """Copia del diccionario de credenciales con la expiración en formato google-auth."""
    return {**credentials_data, "expiry": _normalize_expiry(credentials_data.get("expiry"))}


def _credentials_to_dict(credentials: Credentials) -> dict:
    """Convierte un objeto Credentials de Google en un diccionario serializable."""
    return {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": list(credentials.scopes or []),
        "expiry": _normalize_expiry(credentials.expiry),
    }


def _credentials_from_dict(credentials_data: dict) -> Credentials:
    """Reconstruye un objeto Credentials de Google desde el diccionario guardado."""
    info = {
        "token": credentials_data.get("token"),
        "refresh_token": credentials_data.get("refresh_token"),
        "token_uri": credentials_data.get("token_uri"),
        "client_id": credentials_data.get("client_id"),
        "client_secret": credentials_data.get("client_secret"),
        "scopes": credentials_data.get("scopes") or [],
        "expiry": _normalize_expiry(credentials_data.get("expiry")),
    }
    return Credentials.from_authorized_user_info(info, scopes=SCOPES)


def _set_session_credentials(credentials_data: dict) -> None:
    """Carga las credenciales en el session_state de Streamlit.

    La expiración se normaliza al formato de google-auth porque core/users.py
    reconstruye las credenciales desde este diccionario.
    """
    normalized = _normalized_credentials_data(credentials_data)
    st.session_state["credentials"] = normalized
    st.session_state["creds_google"] = _credentials_from_dict(normalized)


def _refresh_credentials(credentials_data: dict) -> dict | None:
    """Renueva el access token si expiró.

    Devuelve el diccionario actualizado o el original si el token aún es
    válido. Devuelve None cuando las credenciales ya no sirven (refresh token
    revocado o inexistente). Los fallos transitorios (red, etc.) se propagan
    como excepción para no borrar las credenciales guardadas.
    """
    try:
        credentials = _credentials_from_dict(credentials_data)
    except Exception:
        return None

    if not credentials.expired:
        return _normalized_credentials_data(credentials_data)

    if not credentials.refresh_token:
        return None

    try:
        credentials.refresh(Request())
    except RefreshError as error:
        message = str(error).lower()
        if "invalid_grant" in message or "invalid_client" in message:
            return None  # El refresh token fue revocado: hay que volver a iniciar sesión.
        raise

    return _credentials_to_dict(credentials)


def _refresh_session_in_place() -> None:
    """Renueva el token de la sesión activa si ya expiró (muta el objeto en
    sitio, por lo que los servicios que ya lo referencian también se actualizan).
    """
    credentials = st.session_state.get("creds_google")
    if credentials is None or not credentials.expired or not credentials.refresh_token:
        return
    try:
        credentials.refresh(Request())
    except Exception:
        return
    credentials_data = _credentials_to_dict(credentials)
    st.session_state["credentials"] = credentials_data
    save_credentials(credentials_data, email=st.session_state.get("user_email"))


# ---------------------------------------------------------------------------
# Guardado local encriptado (Fernet + archivo en disco)
# ---------------------------------------------------------------------------
def _fernet() -> Fernet:
    """Instancia de Fernet con una clave derivada de los secretos de la app.

    La clave se deriva de secretos ya existentes (jwt_auth y client_secret),
    de modo que el descifrado funciona entre reinicios de la aplicación sin
    necesidad de configurar nada nuevo.
    """
    if getattr(_run_state, "fernet", None) is None:
        jwt_secret = st.secrets.get("google_oauth", {}).get("jwt_auth", "")
        client_secret = st.secrets.get("google_oauth", {}).get("client_secret", "")
        material = f"{jwt_secret}:{client_secret}".encode("utf-8")
        key = base64.urlsafe_b64encode(hashlib.sha256(material).digest())
        _run_state.fernet = Fernet(key)
    return _run_state.fernet


def _credentials_file_path() -> Path:
    """Ruta del archivo local encriptado (directorio del usuario o temp como respaldo)."""
    if getattr(_run_state, "credentials_file_path", None) is None:
        base_dir = Path.home() / CREDENTIALS_FILE_DIRNAME
        try:
            base_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            base_dir = Path(tempfile.gettempdir()) / CREDENTIALS_FILE_DIRNAME
            base_dir.mkdir(parents=True, exist_ok=True)
        _run_state.credentials_file_path = base_dir / CREDENTIALS_FILE_NAME
    return _run_state.credentials_file_path


def _read_local_store() -> dict:
    """Lee y descifra el archivo local. Devuelve un almacén vacío si falla."""
    try:
        path = _credentials_file_path()
        if not path.exists():
            return {"users": {}, "last": None}
        payload = path.read_bytes()
        if not payload:
            return {"users": {}, "last": None}
        store = json.loads(_fernet().decrypt(payload).decode("utf-8"))
        if not isinstance(store, dict) or not isinstance(store.get("users"), dict):
            return {"users": {}, "last": None}
        return store
    except Exception:
        return {"users": {}, "last": None}


def _write_local_store(store: dict) -> None:
    """Cifra y escribe el almacén de forma atómica (escritura temporal + reemplazo)."""
    path = _credentials_file_path()
    payload = _fernet().encrypt(json.dumps(store).encode("utf-8"))
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with open(temp_path, "wb") as handle:
        handle.write(payload)
    os.replace(temp_path, path)
    try:
        os.chmod(path, 0o600)  # Solo el dueño del proceso puede leerlo.
    except OSError:
        pass


def _save_local_credentials(email: str, credentials_data: dict) -> None:
    """Guarda (cifradas) las credenciales del usuario en el archivo local."""
    try:
        store = _read_local_store()
        store.setdefault("users", {})[email] = credentials_data
        store["last"] = email
        _write_local_store(store)
    except Exception:
        pass  # La persistencia local es un respaldo: nunca debe romper el flujo.


def _load_local_credentials() -> tuple[str, dict] | None:
    """Devuelve (email, credenciales) del último usuario guardado en el archivo."""
    try:
        store = _read_local_store()
        email = store.get("last")
        credentials_data = (store.get("users") or {}).get(email)
        if not email or not credentials_data or not credentials_data.get("token"):
            return None
        return email, dict(credentials_data)
    except Exception:
        return None


def _delete_local_credentials(email: str | None = None) -> None:
    """Borra las credenciales del archivo local (solo las del email dado, o todas)."""
    try:
        store = _read_local_store()
        if email and email in store.get("users", {}):
            del store["users"][email]
            if store.get("last") == email:
                store["last"] = next(iter(store["users"]), None)
            _write_local_store(store)
        else:
            _write_local_store({"users": {}, "last": None})
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Persistencia en cookies del navegador
# ---------------------------------------------------------------------------
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
        "same_site": "lax",
    }


def _encode_scopes(scopes) -> str:
    """Codifica la lista de scopes en base64url (evita caracteres no válidos en cookies)."""
    payload = json.dumps(list(scopes or [])).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii")


def _decode_scopes(raw: str) -> list:
    """Decodifica la lista de scopes guardada en una cookie."""
    if not raw:
        return []
    try:
        return list(json.loads(raw))  # Compatibilidad con cookies antiguas (JSON plano).
    except (TypeError, ValueError):
        pass
    try:
        payload = base64.urlsafe_b64decode(raw.encode("ascii"))
        return list(json.loads(payload.decode("utf-8")))
    except Exception:
        return []


def _credentials_from_raw_values(raw_values: dict) -> dict | None:
    """Construye el diccionario de credenciales desde los valores crudos (cookies).

    Solo se aceptan cadenas de texto no vacías: cualquier valor corrupto o
    inesperado invalida la lectura para evitar credenciales basura.
    """
    def _str(value):
        return value if isinstance(value, str) and value else None

    token = _str(raw_values.get("token"))
    if not token:
        return None
    return {
        "token": token,
        "refresh_token": _str(raw_values.get("refresh_token")),
        "token_uri": _str(raw_values.get("token_uri")),
        "client_id": _str(raw_values.get("client_id")),
        "client_secret": _str(raw_values.get("client_secret")),
        "scopes": _decode_scopes(raw_values.get("scopes") or ""),
        "expiry": _str(raw_values.get("expiry")),
    }


def _read_request_cookies() -> dict | None:
    """Lee las cookies de la petición HTTP inicial (lectura síncrona del servidor).

    Al recargar la página, el navegador envía las cookies en la primera
    petición, por lo que están disponibles desde la primera ejecución del
    script, sin el desfase asíncrono del componente de cookies. Esto también
    funciona en Streamlit Cloud.
    """
    try:
        request_cookies = st.context.cookies
        raw_values = {
            field: request_cookies.get(_cookie_name(field))
            for field in CREDENTIALS_COOKIE_FIELDS
        }
        return _credentials_from_raw_values(raw_values)
    except Exception:
        return None


def load_saved_credentials() -> dict | None:
    """Recupera las credenciales persistidas en cookies del navegador, si existen.

    Primero intenta la lectura síncrona de las cookies de la petición inicial
    (st.context.cookies) y, como respaldo, el componente CookieManager de
    extra-streamlit-components. El componente solo puede instanciarse una vez
    por ejecución, por lo que el resultado se memoiza para el resto de la corrida.
    """
    if getattr(_run_state, "cookies_read_done", False):
        return getattr(_run_state, "cookies_result", None)

    credentials = _read_request_cookies()

    if credentials is None and stx is not None:
        try:
            cookie_manager = stx.CookieManager(key=_COOKIE_KEY_READ)
            raw_values = {
                field: cookie_manager.get(_cookie_name(field))
                for field in CREDENTIALS_COOKIE_FIELDS
            }
            credentials = _credentials_from_raw_values(raw_values)
        except Exception:
            credentials = None

    _run_state.cookies_read_done = True
    _run_state.cookies_result = credentials
    return credentials


def save_credentials(credentials_data: dict, email: str | None = None) -> None:
    """Persiste las credenciales de Google en dos capas redundantes:

    1. Cookies del navegador (sobreviven recargas de página y reinicios).
    2. Archivo local cifrado con Fernet (respaldo si el navegador no coopera).

    Se guarda un campo por cookie para respetar el límite de ~4KB por cookie
    (los tokens de acceso de Google pueden ser largos).
    """
    credentials_data = _normalized_credentials_data(credentials_data)

    if stx is not None:
        try:
            cookies = {
                _cookie_name(field): (
                    _encode_scopes(value) if field == "scopes" else (value or "")
                )
                for field, value in credentials_data.items()
            }
            cookie_manager = stx.CookieManager(key=_COOKIE_KEY_WRITE)
            cookie_manager.batch_set(cookies, **_cookie_options())
        except Exception:
            pass  # Las cookies son un respaldo: el archivo local queda como garantía.

    if email:
        _save_local_credentials(email, credentials_data)

    # Capa adicional de respaldo dentro de la propia sesión.
    _cache_credentials(credentials_data)


def delete_saved_credentials() -> None:
    """Borra las credenciales persistidas durante el cierre de sesión."""
    store = _session_store()
    email = store.get("email")

    if stx is not None:
        try:
            cookie_manager = stx.CookieManager(key=_COOKIE_KEY_DELETE)
            for index, field in enumerate(CREDENTIALS_COOKIE_FIELDS):
                try:
                    cookie_manager.delete(_cookie_name(field), key=f"delete_{index}")
                except Exception:
                    pass  # La cookie no existe en el snapshot: nada que borrar.
        except Exception:
            pass

    _delete_local_credentials(email)
    store.clear()


# ---------------------------------------------------------------------------
# Flujo de OAuth 2.0 con Google
# ---------------------------------------------------------------------------
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

    # Primero Cargamos los Datos del headcount
    headcount_data = load_headcount_negociacion()
    # Ahora Obtenemos la Fila para dicho Email
    user_row = headcount_data[headcount_data['Correo'] == email]
    # Si esta vacio, entonces devolvemos 'nego'
    if user_row.empty:
        # Mostramos un Mensaje de Error en la Aplicación
        error_page_view(f"El correo {email} no está registrado en el headcount de negociación. Por favor, contacte al administrador.")

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

def create_user_from_session():
    """Creates a User object from session state credentials."""
    if "credentials" not in st.session_state:
        return None

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


# ---------------------------------------------------------------------------
# Orquestación de la autenticación
# ---------------------------------------------------------------------------
def _handle_oauth_callback(params) -> None:
    """Completa el flujo de OAuth cuando Google redirige de vuelta a la app."""
    try:
        code = params["code"]
        flow = create_flow()

        # Obtenemos el code_verifier de PKCE desde el parámetro state (JWT firmado).
        state = params.get("state", "")
        payload = jwt.decode(state, st.secrets["google_oauth"]["jwt_auth"], algorithms=["HS256"])
        code_verifier = payload.get("cv")

        # Validamos la Expiración del Token
        if time.time() > payload.get("exp", 0):
            st.query_params.clear()
            error_page_view("El token de autenticación ha expirado. Por favor, intenta iniciar sesión nuevamente.")

        flow.code_verifier = code_verifier  # Set the code_verifier for PKCE
        flow.fetch_token(code=code)

        # Guardamos las credenciales de OAuth en el session state.
        credentials_data = _credentials_to_dict(flow.credentials)
        _set_session_credentials(credentials_data)

        # Clear URL parameters to keep address bar clean
        st.query_params.clear()

        # Guardamos el Usuario
        st.session_state["user_obj"] = create_user_from_session()
        email = st.session_state.get("user_email", "Unknown")

        store = _session_store()
        store["authenticated"] = True
        store["email"] = email

        # Persistimos las credenciales (cookies + archivo local encriptado)
        # para que la sesión sobreviva a recargas de página y reinicios.
        save_credentials(credentials_data, email=email)

        st.rerun()
    except Exception as e:
        st.query_params.clear()
        st.error(f"Error durante la autenticación: {e}", icon="🚨")
        st.info("Por favor, intenta iniciar sesión nuevamente.", icon="ℹ️")
        # Volvemos a generar la URL guardandola en auth_url
        st.session_state["auth_url"] = get_auth_url()


def _restore_credentials() -> dict | None:
    """Busca credenciales persistidas en este orden:
    cookies del navegador -> archivo local encriptado -> almacén de sesión.
    """
    credentials = load_saved_credentials()
    if credentials:
        return credentials

    restored = _load_local_credentials()
    if restored is not None:
        return restored[1]

    return load_cached_credentials()


def authenticate_user():
    """Handles query params after Google redirects back to Streamlit.

    Además de completar el callback de OAuth, restaura la sesión desde las
    credenciales persistidas (cookies o archivo local encriptado) cuando se
    recarga la página o la sesión de Streamlit expiró, y detecta el cierre de
    sesión para borrar lo guardado.
    """
    # Read query params
    params = st.query_params

    # 1. Check if returning from Google Auth with code
    if "code" in params and "credentials" not in st.session_state:
        _handle_oauth_callback(params)
        return

    store = _session_store()

    # 2. Detección del cierre de sesión: la sesión estaba autenticada en una
    #    ejecución anterior y ahora el session_state está vacío (el usuario
    #    pulsó "Cerrar Sesión", que hace st.session_state.clear()).
    if (
        store.get("authenticated")
        and "credentials" not in st.session_state
        and "user_obj" not in st.session_state
    ):
        delete_saved_credentials()
        store["authenticated"] = False
        return

    # 3. La sesión ya tiene credenciales en memoria: solo falta crear el usuario.
    if "credentials" in st.session_state:
        if "code" in params:
            st.query_params.clear()

        if "user_obj" not in st.session_state:
            credentials_data = st.session_state["credentials"]
            try:
                refreshed = _refresh_credentials(credentials_data)
            except Exception:
                refreshed = credentials_data  # Fallo transitorio: seguimos con lo que hay.
            if refreshed is None:
                # Refresh revocado: limpiamos todo y forzamos un nuevo login.
                st.session_state.clear()
                delete_saved_credentials()
                return

            _set_session_credentials(refreshed)
            st.session_state["user_obj"] = create_user_from_session()
            email = st.session_state.get("user_email")
            store["authenticated"] = True
            store["email"] = email
            save_credentials(refreshed, email=email)
            st.rerun()

        # Sesión activa: renovamos el token en sitio si expiró.
        _refresh_session_in_place()
        store["authenticated"] = True
        return

    # 4. Recarga de página / sesión nueva: intentamos restaurar credenciales.
    credentials_data = _restore_credentials()
    if credentials_data is None:
        return  # Se muestra la página de login.

    try:
        refreshed = _refresh_credentials(credentials_data)
    except Exception:
        return  # Fallo transitorio: conservamos lo guardado y mostramos login.

    if refreshed is None:
        # Credenciales revocadas: limpiamos lo guardado y forzamos re-login.
        delete_saved_credentials()
        return

    _set_session_credentials(refreshed)
    st.session_state["user_obj"] = create_user_from_session()
    email = st.session_state.get("user_email")
    store["authenticated"] = True
    store["email"] = email
    save_credentials(refreshed, email=email)

    # Rerun para que initialize_services() vea creds_google y arranque el
    # servicio de correo con las credenciales del usuario.
    st.rerun()
