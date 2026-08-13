# Estándar usando Pep8
# Librerías de Python
from typing import Literal
# Librerías de Terceros
import streamlit as st
# Librerías Locales

class Permit:
    """
    Clase para manejar un permiso específico de un usuario.
    """
    def __init__(self,*,name: str, description: str, user_roles_allowed: list[Literal['admin', 'leader','nego', 'executive']]):
        self.name = name
        self.description = description
        self.user_roles_allowed = user_roles_allowed

    def __eq__(self, other):
        if isinstance(other, Permit):
            return self.name == other.name
        return False

    def is_allowed(self, user_role: Literal['admin', 'leader','nego', 'executive']) -> bool:
        """
        Método para verificar si un usuario con un rol específico tiene permitido este permiso.
        """
        return user_role in self.user_roles_allowed

# Definimos todos los permisos disponibles en el sistema
SUBIDA_FORMULARIO = Permit(
    name="subida_formulario",
    description="Permite subir formularios a Alianzas.",
    user_roles_allowed=['admin', 'leader','nego'],
)
AGREGAR_CARTERA = Permit(
    name="agregar_cartera",
    description="Permite agregar carteras a Alianzas.",
    user_roles_allowed=['admin', 'executive'],
)
GESTIONAR_SOLICITUDES = Permit(
    name="gestionar_solicitudes",
    description="Permite gestionar solicitudes de Alianzas dando Respuestas.",
    user_roles_allowed=['admin', 'executive'],
)
VER_MIS_SOLICITUDES = Permit(
    name="ver_mis_solicitudes",
    description="Permite ver las solicitudes del usuario y del equipo si es necesario.",
    user_roles_allowed=['admin', 'leader','nego', 'executive'],
)
VER_CARTERA_TOTAL = Permit(
    name="ver_cartera_total",
    description="Permite ver la cartera total bien sea individual o por equipos",
    user_roles_allowed=['admin', 'leader','nego', 'executive'],
)
VER_LOGS = Permit(
    name="ver_logs",
    description="Permite ver los logs de actividad del sistema.",
    user_roles_allowed=['admin'],
)

# Creamos un Diccionario de Permisos para facilitar la búsqueda y gestión de permisos
PERMISSIONS_DICT = {
    "subida_formulario": SUBIDA_FORMULARIO,
    "agregar_cartera": AGREGAR_CARTERA,
    "gestionar_solicitudes": GESTIONAR_SOLICITUDES,
    "ver_mis_solicitudes": VER_MIS_SOLICITUDES,
    "ver_cartera_total": VER_CARTERA_TOTAL,
    "ver_logs": VER_LOGS,
}

# Definimos los permisos por defecto para cada rol de usuario
DEFAULT_PERMISSIONS = {
    'admin': list(PERMISSIONS_DICT.values()),  # Todos los permisos para admin
    'leader': [p for p in PERMISSIONS_DICT.values() if p.is_allowed('leader')],  # Permisos específicos para leader
    'nego': [p for p in PERMISSIONS_DICT.values() if p.is_allowed('nego')],  # Permisos específicos para nego
    'executive': [p for p in PERMISSIONS_DICT.values() if p.is_allowed('executive')],  # Permisos específicos para executive
}

PAGES_ROUTE_MAPPING = {
    "subida_formulario": {"page": "views/rellenar_forms.py", "title": "Formulario Alianzas", "icon": "📝"},
    "agregar_cartera": {"page": "views/agregar_cartera.py", "title": "Agregar Cartera", "icon": "💼"},
    "gestionar_solicitudes": {"page": "views/gestionar_solicitudes.py", "title": "Gestionar Solicitudes", "icon": "🛠️"},
    "ver_mis_solicitudes": {"page": "views/ver_solicitudes.py", "title": "Ver Mis Solicitudes", "icon": "📋"},
    "ver_cartera_total": {"page": "views/ver_cartera_total.py", "title": "Ver Cartera Total", "icon": "💸"},
    "ver_logs": {"page": "views/ver_logs.py", "title": "Ver Logs", "icon": "🤔"},
}

def get_permit_pages(user_role: Literal['admin', 'leader', 'nego', 'executive']) -> list[st.Page]:
    """
    Función para obtener las páginas permitidas e instanciar st.Page dinámicamente.
    """
    allowed_permits = DEFAULT_PERMISSIONS.get(user_role, [])
    
    # Eliminamos duplicados si los hubiera
    seen_permits = set()
    allowed_pages = []

    for permit in allowed_permits:
        if permit.name in PAGES_ROUTE_MAPPING and permit.name not in seen_permits:
            seen_permits.add(permit.name)
            config = PAGES_ROUTE_MAPPING[permit.name]
            
            # Instanciamos la página de forma fresca
            # Establecemos default=True únicamente en la primera página de la lista
            is_default = (len(allowed_pages) == 0)
            
            page_obj = st.Page(
                page=config["page"],
                title=config["title"],
                icon=config["icon"],
                default=is_default
            )
            allowed_pages.append(page_obj)

    # Opcional: Página por defecto si el usuario no tiene ninguna página permitida
    if not allowed_pages:
        allowed_pages = [st.Page("views/no_access.py", title="Sin Acceso", icon="🚫", default=True)]

    return allowed_pages