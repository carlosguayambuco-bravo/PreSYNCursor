# Estándar usando Pep8
# Librerías de Python
# Librerías de Terceros
import pandas as pd
import streamlit as st
# Librerías Locales
from data.data_loader import SOLICITUDES_SHEET_ID
from modules.constants import SOLICITUDES_ID_DELAY
from utils.helpers_sheets import _retry, appendDataFrameToEnd, convert_data_to_string, get_column_letter
from services.google_sheets import GoogleSheetsService

# Función para subir una respuesta de Formulario a Google Sheets
def upload_form_response_to_google_sheets(response_info: dict) -> tuple[bool, int]:
    # Volvemos la Respuesta a un DataFrame para poder subirla a Google Sheets
    response_df = pd.DataFrame([response_info])

    # Obtenemos el Servicio de Google Sheets desde el Session State de Streamlit
    sheets_service: GoogleSheetsService = st.session_state['google_sheets_service']

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
        new_id = SOLICITUDES_ID_DELAY

    # Agregamos el nuevo ID a la respuesta
    response_df['ID_Solicitud'] = new_id

    # Subimos la respuesta a Google Sheets
    try:
        appendDataFrameToEnd(responses_ws, response_df)
        return True, new_id
    except Exception as e:
        st.error(f"Error al subir la respuesta a Google Sheets: {e}")
        return False, -1

# Función Auxiliar para Actualizar una Solicitud en Google Sheets
def update_solicitud_in_google_sheets(solicitud: pd.Series) -> bool:
    # Obtenemos el Servicio de Google Sheets desde el Session State de Streamlit
    sheets_service: GoogleSheetsService = st.session_state['google_sheets_service']

    # Abrimos la Worksheet 'Solicitudes_MEC' usando el servicio de Sheets
    solicitudes_ws = sheets_service.get_worksheet(SOLICITUDES_SHEET_ID, 'Solicitudes_MEC')

    # Buscamos la fila correspondiente a la solicitud por su ID
    solicitud_id = solicitud['ID_Solicitud']
    solicitud_sheets_row = solicitud_id - SOLICITUDES_ID_DELAY + 2  # +2 porque la primera fila es el header y la segunda fila es el primer ID (1)
    try:
        # Obtenemos los Headers de la Worksheet guardados en el Session State
        headers = st.session_state.get("solicitudes_headers", [])
        # Organizamos los datos de la solicitud en el orden de los headers
        solicitud_data = [convert_data_to_string(solicitud.get(header, "")) for header in headers]

        # Definimos el Rango de celdas a actualizar en la Worksheet
        cell_range = f"A{solicitud_sheets_row}:{get_column_letter(len(headers))}{solicitud_sheets_row}"

        # Aplicamos la Actualización a la Worksheet (usando _retry para manejar posibles errores de red)
        _retry(lambda: solicitudes_ws.update(range_name=cell_range, values=[solicitud_data]), label="Update Solicitud")

        return True
    except Exception as e:
        st.error(f"Error al actualizar la solicitud en Google Sheets: {e}")
        return False