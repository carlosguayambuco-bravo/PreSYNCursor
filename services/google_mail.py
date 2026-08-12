# Usando Pep8
# Librerías de Python
import base64
from typing import Optional
from io import BytesIO
# Librerías de Terceros
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import streamlit as st

# Clase de GoogleMailService para interactuar con la API de Google Mail (usando googleapiclient)
class GoogleMailService:
    def __init__(self, credentials_obj):
        """
        Inicializa la instancia de GoogleMailService con las credenciales proporcionadas.

        Args:
            credentials_obj (Credentials): Objeto de credenciales de Google Service Account.
        """
        self.credentials = credentials_obj
        self.service = build('gmail', 'v1', credentials=credentials_obj)

    def send_email(self, to: str, subject: str, body: str, cc_emails: Optional[list] = None, pdf_bytes: Optional[bytes] = None, pdf_name: Optional[str] = None) -> bool:
        """
        Envía un correo electrónico utilizando la API de Gmail.

        Args:
            to (str): Dirección de correo electrónico del destinatario.
            subject (str): Asunto del correo electrónico.
            body (str): Cuerpo del correo electrónico.
            cc_emails (Optional[list]): Lista de correos electrónicos para copia (opcional).
            pdf_bytes (Optional[bytes]): Contenido del archivo PDF en bytes (opcional).
            pdf_name (Optional[str]): Nombre del archivo PDF adjunto (opcional).

        Returns:
            bool: True si el correo se envió correctamente, False en caso contrario.
        """
        try:
            message = {
                'raw': self._create_message(to, subject, body, cc_emails, pdf_bytes, pdf_name)
            }
            self.service.users().messages().send(userId='me', body=message).execute()
            st.success("Correo enviado exitosamente a {}".format(to), icon="✅")
            return True
        except Exception as e:
            st.error(f"Error al enviar el correo: {e}", icon="❌")
            return False

    def _create_message(self, to: str, subject: str, body: str, cc_emails: Optional[list[str]] = None, pdf_bytes: Optional[bytes] = None, pdf_name: Optional[str] = None) -> str:
        """
        Crea un mensaje codificado en base64 para enviar a través de la API de Gmail.

        Args:
            to (str): Dirección de correo electrónico del destinatario.
            subject (str): Asunto del correo electrónico.
            body (str): Cuerpo del correo electrónico.

        Returns:
            str: Mensaje codificado en base64.
        """
        message = MIMEMultipart()
        message.attach(MIMEText(body, 'plain'))
        message['to'] = to
        message['subject'] = subject

        if cc_emails:
            message['Cc'] = ', '.join(cc_emails)

        if pdf_bytes and pdf_name:
            if isinstance(pdf_bytes, BytesIO):
                pdf_bytes = pdf_bytes.getvalue()
            # Agregar el archivo PDF como adjunto
            attachment = MIMEApplication(pdf_bytes, _subtype='pdf')
            attachment.add_header('Content-Disposition', 'attachment', filename=pdf_name)
            message.attach(attachment)

        return base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
