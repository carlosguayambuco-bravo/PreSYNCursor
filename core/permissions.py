# Estándar usando Pep8
# Librerías de Python
from typing import Literal
# Librerías de Terceros
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
VER_CARTERA_EQUIPO = Permit(
    name="ver_cartera_equipo",
    description="Permite ver la cartera de todo el equipo.",
    user_roles_allowed=['admin', 'leader'],
)
VER_CARTERA_TOTAL = Permit(
    name="ver_cartera_total",
    description="Permite ver la cartera total de todos los equipos.",
    user_roles_allowed=['admin','executive'],
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
    "ver_cartera_equipo": VER_CARTERA_EQUIPO,
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