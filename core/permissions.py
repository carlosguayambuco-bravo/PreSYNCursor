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
    "subida_formulario": st.Page("views/rellenar_forms.py",title="Formulario Alianzas",icon="📝",default=False),
    "agregar_cartera": st.Page("views/agregar_cartera.py",title="Agregar Cartera",icon="💼",default=False),
    "gestionar_solicitudes": st.Page("views/gestionar_solicitudes.py",title="Gestionar Solicitudes",icon="🛠️",default=False),
    "ver_mis_solicitudes": st.Page("views/ver_solicitudes.py",title="Ver Mis Solicitudes",icon="📋",default=False),
    "ver_cartera_total": st.Page("views/ver_cartera_total.py",title="Ver Cartera Total",icon="💸",default=False),
    "ver_logs": st.Page("views/ver_logs.py",title="Ver Logs",icon="🤔",default=False),
}

def get_permit_pages(user_role: Literal['admin', 'leader','nego', 'executive']) -> list[st.Page]: # type: ignore
    """
    Función para obtener las páginas permitidas para un rol de usuario específico.
    """
    allowed_permits = DEFAULT_PERMISSIONS.get(user_role, [])
    allowed_pages = [PAGES_ROUTE_MAPPING[permit.name] for permit in allowed_permits if permit.name in PAGES_ROUTE_MAPPING]
    return allowed_pages