# Usando Pep8
# Librerías de Python
from io import BytesIO
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