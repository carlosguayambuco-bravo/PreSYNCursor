# Estándar usando Pep8
# Librerías de Python
# Librerías de Terceros
import pandas as pd
import streamlit as st
# Librerías Locales
from data.data_loader import SOLICITUDES_SHEET_ID
from utils.helpers_sheets import _retry, appendDataFrameToEnd
from services.google_sheets import GoogleSheetsService

# Función para subir una respuesta de Formulario a Google Sheets
def upload_form_response_to_google_sheets(response_info: dict) -> tuple[bool, int]:
    # Volvemos la Respuesta a un DataFrame para poder subirla a Google Sheets
    response_df = pd.DataFrame([response_info])

    # Obtenemos el Servicio de Google Sheets desde el Session State de Streamlit
    sheets_service: GoogleSheetsService = st.session_state['sheets_service']

    # Abrimos la Worksheet 'Solicitudes_MEC' usando el servicio de Sheets
    responses_ws = sheets_service.get_worksheet(SOLICITUDES_SHEET_ID, 'Solicitudes_MEC')

    # Siguiente: Agregamos el Timestamp y Correo a la respuesta antes de subirla
    response_df['Timestamp'] = pd.Timestamp.now(tz='America/Bogota').strftime('%Y-%m-%d %H:%M:%S')
    response_df['Correo'] = st.session_state['user_email']

    # Ahora: Agregamos el ID
    # 1. Obtenemos el último ID de Solicitud en la Worksheet
    last_id_cell = _retry(lambda: responses_ws.col_values(1))  # Suponemos que la columna A tiene los IDs de Solicitud
    # 2. Calculamos el nuevo ID sumando 1 al último ID
    if len(last_id_cell) > 1:  # Si hay más de una fila
        last_id = int(last_id_cell[-1])  # type: ignore # Tomamos el último ID
        new_id = last_id + 1
    else:
        new_id = 1

    # Agregamos el nuevo ID a la respuesta
    response_df['ID'] = new_id

    # Subimos la respuesta a Google Sheets
    try:
        appendDataFrameToEnd(responses_ws, response_df)
        return True, new_id
    except Exception as e:
        st.error(f"Error al subir la respuesta a Google Sheets: {e}")
        return False, -1