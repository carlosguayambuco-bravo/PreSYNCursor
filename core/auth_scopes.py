# Estándar usando Pep8
# Librerías de Python
import os

# Variable de oauthlib que relaja la validación de igualdad estricta de scopes.
RELAX_TOKEN_SCOPE_ENV = "OAUTHLIB_RELAX_TOKEN_SCOPE"


def configure_oauthlib_for_shared_client() -> None:
    """Permite tokens con scopes adicionales a los solicitados por el App.

    El App comparte el client_id con el MCP de Google Workspace. Cuando el MCP
    ya concedió permisos adicionales, Google devuelve el conjunto completo de
    scopes en el token y oauthlib lo rechaza con:
        Warning: Scope has changed from "..." to "..."

    Esta variable desactiva únicamente esa validación de igualdad estricta. La
    seguridad no se relaja: auth.py verifica que los scopes requeridos por el
    App estén presentes antes de aceptar la sesión.
    """
    if not os.environ.get(RELAX_TOKEN_SCOPE_ENV):
        os.environ[RELAX_TOKEN_SCOPE_ENV] = "1"


def normalize_scope_list(raw_scopes) -> list[str]:
    """Convierte el campo `scope` de un token OAuth en una lista de strings.

    Google devuelve el campo como una cadena separada por espacios, pero
    oauthlib lo normaliza a lista. Se aceptan ambos formatos y valores nulos.
    """
    if not raw_scopes:
        return []
    if isinstance(raw_scopes, str):
        return raw_scopes.split()
    return [str(scope) for scope in raw_scopes]


def missing_scopes(granted_scopes, required_scopes) -> list[str]:
    """Devuelve los scopes requeridos que no fueron concedidos.

    Si `granted_scopes` viene vacío se asume que Google no incluyó el campo
    `scope` porque coincide con lo solicitado; en ese caso no se reportan
    faltantes.
    """
    granted = set(normalize_scope_list(granted_scopes))
    if not granted:
        return []
    return [scope for scope in required_scopes if scope not in granted]
