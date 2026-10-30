# Usando Pep8
# Librerías de Python
from io import BytesIO
from typing import Optional
# Librerías de Terceros
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload
import streamlit as st

# Clase de GoogleDriveService para interactuar con la API de Google Drive (usando googleapiclient)
class GoogleDriveService:
    def __init__(self, credentials_json: dict):
        """
        Inicializa la instancia de GoogleDriveService con las credenciales proporcionadas.

        Args:
            credentials_json (dict): Diccionario con las credenciales de Google Service Account.
        """
        self.credentials = Credentials.from_service_account_info(credentials_json, scopes=['https://www.googleapis.com/auth/drive'])
        self.service = build('drive', 'v3', credentials=self.credentials)

    def upload_file(self, file_bytes: bytes, file_name: str, mime_type: str, folder_id: str) -> str:
        """
        Sube un archivo a Google Drive.

        Args:
            file_bytes (bytes): Contenido del archivo en bytes.
            file_name (str): Nombre del archivo a subir.
            mime_type (str): Tipo MIME del archivo.
            folder_id (str): ID de la carpeta en Google Drive donde se subirá el archivo.

        Returns:
            str: ID del archivo subido en Google Drive.
        """
        try:
            file_io = BytesIO(file_bytes)
            media = MediaIoBaseUpload(file_io, mimetype=mime_type, resumable=True)
            file_metadata = {
                'name': file_name,
                'parents': [folder_id],
                'mimeType': mime_type
            }
            file = self.service.files().create(body=file_metadata, media_body=media, fields='id',supportsAllDrives=True).execute()
            st.success(f"Archivo subido exitosamente a Google Drive.", icon="✅")
            return file.get('id')
        except Exception as e:
            print(f"Error al subir el archivo a Google Drive: {e}")
            st.error(f"Error al subir el archivo a Google Drive: {e}", icon="❌")
            return ''

    @staticmethod
    def _escape_query_value(value: str) -> str:
        """Escapa un valor para usarlo dentro de una consulta de Google Drive."""
        return str(value).replace("\\", "\\\\").replace("'", "\\'")

    def find_folder(self, *, folder_name: str, parent_id: str) -> Optional[str]:
        """
        Busca una carpeta por nombre dentro de un padre específico.

        Args:
            folder_name (str): Nombre de la carpeta.
            parent_id (str): ID de la carpeta padre.

        Returns:
            Optional[str]: ID de la carpeta encontrada, cadena vacía si no existe,
            o None si ocurrió un error.
        """
        try:
            safe_name = self._escape_query_value(folder_name)
            safe_parent = self._escape_query_value(parent_id)
            query = (
                "name = '{}' and '{}' in parents and "
                "mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            ).format(safe_name, safe_parent)
            response = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id,name,createdTime)',
                pageSize=100,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                corpora='allDrives',
            ).execute()
            folders = response.get('files', [])
            if not folders:
                return ''
            # Si hay varias carpetas con el mismo nombre, usamos la más reciente
            folders.sort(key=lambda folder: folder.get('createdTime', ''))
            return folders[-1].get('id', '')
        except Exception as e:
            print(f"Error al buscar la carpeta en Google Drive: {e}")
            st.error(f"Error al buscar la carpeta en Google Drive: {e}", icon="❌")
            return None

    def create_folder(self, *, folder_name: str, parent_id: str) -> str:
        """
        Crea una carpeta en Google Drive.

        Args:
            folder_name (str): Nombre de la carpeta.
            parent_id (str): ID de la carpeta padre.

        Returns:
            str: ID de la carpeta creada, o cadena vacía si falló.
        """
        try:
            folder_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [parent_id],
            }
            folder = self.service.files().create(
                body=folder_metadata,
                fields='id',
                supportsAllDrives=True,
            ).execute()
            return folder.get('id', '')
        except Exception as e:
            print(f"Error al crear la carpeta en Google Drive: {e}")
            st.error(f"Error al crear la carpeta en Google Drive: {e}", icon="❌")
            return ''

    def list_folder_contents(self, folder_id: str) -> Optional[list[dict]]:
        """
        Lista los elementos contenidos en una carpeta de Google Drive.

        Args:
            folder_id (str): ID de la carpeta.

        Returns:
            Optional[list[dict]]: Lista de archivos/carpetas, o None si ocurrió un error.
        """
        try:
            safe_folder_id = self._escape_query_value(folder_id)
            query = "'{}' in parents and trashed = false".format(safe_folder_id)
            files = []
            page_token = None
            while True:
                response = self.service.files().list(
                    q=query,
                    spaces='drive',
                    fields='nextPageToken, files(id,name,mimeType,shortcutDetails)',
                    pageSize=1000,
                    pageToken=page_token,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                    corpora='allDrives',
                ).execute()
                files.extend(response.get('files', []))
                page_token = response.get('nextPageToken')
                if not page_token:
                    break
            return files
        except Exception as e:
            print(f"Error al listar el contenido de la carpeta en Google Drive: {e}")
            st.error(f"Error al listar el contenido de la carpeta en Google Drive: {e}", icon="❌")
            return None

    def delete_folder_contents(self, folder_id: str) -> bool:
        """
        Elimina todos los elementos contenidos en una carpeta de Google Drive.

        Args:
            folder_id (str): ID de la carpeta.

        Returns:
            bool: True si se eliminaron todos los elementos, False en caso contrario.
        """
        files = self.list_folder_contents(folder_id)
        if files is None:
            return False
        for file in files:
            if not self.delete_file(file_id=file.get('id', '')):
                return False
        return True

    def create_shortcut(self, *, target_file_id: str, folder_id: str, shortcut_name: str) -> str:
        """
        Crea un acceso directo a un archivo dentro de una carpeta de Google Drive.

        Args:
            target_file_id (str): ID del archivo destino.
            folder_id (str): ID de la carpeta donde se creará el acceso directo.
            shortcut_name (str): Nombre visible del acceso directo.

        Returns:
            str: ID del acceso directo creado, o cadena vacía si falló.
        """
        try:
            shortcut_metadata = {
                'name': shortcut_name,
                'mimeType': 'application/vnd.google-apps.shortcut',
                'parents': [folder_id],
                'shortcutDetails': {
                    'targetId': target_file_id,
                },
            }
            shortcut = self.service.files().create(
                body=shortcut_metadata,
                fields='id',
                supportsAllDrives=True,
            ).execute()
            return shortcut.get('id', '')
        except Exception as e:
            print(f"Error al crear el acceso directo en Google Drive: {e}")
            st.error(f"Error al crear el acceso directo en Google Drive: {e}", icon="❌")
            return ''

    def delete_file(self, file_id: str) -> bool:
        """
        Elimina un archivo de Google Drive.

        Args:
            file_id (str): ID del archivo en Google Drive a eliminar.

        Returns:
            bool: True si la eliminación fue exitosa, False en caso contrario.
        """
        try:
            self.service.files().delete(fileId=file_id, supportsAllDrives=True).execute()
            return True
        except HttpError as e:
            # Si el archivo ya no existe (404), consideramos que la eliminación fue exitosa
            if e.resp.status == 404:
                return True
            print(f"Error al eliminar el archivo de Google Drive: {e}")
            st.error(f"Error al eliminar el archivo de Google Drive: {e}", icon="❌")
            return False
        except Exception as e:
            print(f"Error al eliminar el archivo de Google Drive: {e}")
            st.error(f"Error al eliminar el archivo de Google Drive: {e}", icon="❌")
            return False