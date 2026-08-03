# Estándar usando Pep8
# Librerías de Python
from typing import Literal
# Librerías de Terceros
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
# Librerías Locales
from core.permissions import Permit, DEFAULT_PERMISSIONS
from data.data_loader import load_special_user_permissions
from services import GoogleDriveService, GoogleSheetsService

# Clase para manejar la información de los usuarios
class User:
    def __init__(self, name: str, email: str, creds: dict, role: Literal['admin', 'leader','nego', 'executive']):
        self.name = name
        self.email = email
        self.creds = creds
        self.role = role
        self.permits: list[Permit] = []  # Lista de permisos del usuario, se puede llenar según el rol

        self.build_credentials()
        self.build_permits()

    def build_credentials(self):
        # Construimos las credenciales de Google a partir del diccionario de credenciales
        self.credentials = Credentials.from_authorized_user_info(self.creds)

    def build_permits(self):
        # Cargamos los permisos especiales desde Google Sheets
        special_user_permissions = load_special_user_permissions()

        # Si el usuario tiene permisos especiales, los asignamos
        if self.email in special_user_permissions:
            self.permits = special_user_permissions[self.email]
        else:
            # Si no tiene permisos especiales, asignamos los permisos por defecto según el rol
            self.permits = DEFAULT_PERMISSIONS.get(self.role, [])

    def is_admin(self) -> bool:
        return self.role == 'admin'

    def is_executive(self) -> bool:
        return self.role == 'executive'
    
    def is_leader(self) -> bool:
        return self.role == 'leader'

    def is_nego(self) -> bool:
        return self.role == 'nego'

    def has_permission(self, permit: Permit) -> bool:
        """
        Método para verificar si el usuario tiene un permiso específico.
        """
        return permit.is_allowed(self.role) # type: ignore