# Estándar usando Pep8
# Librerías de Python
from typing import Optional
import json
# Librerías de Terceros
from pandera.typing import DataFrame
import pandas as pd
import streamlit as st
# Librerías Locales
from data.data_models import SolicitudesSchema, PendienteCruceSchema
from modules.constants import SOLICITUDES_ID_DELAY, SOLICITUDES_SHEET_ID, CONFIGS_SHEET_ID, MASIVAS_SHEET_ID
from utils.helpers_sheets import _retry, appendDataFrameToEnd, applyChanges, convert_data_to_string, get_column_letter, getWorksheet, uploadToSheets, update_sheet_data_batch
from services.google_sheets import GoogleSheetsService

# Función Auxiliar para Obtener el Mapeo de IDs de Solicitud a Filas de Google Sheets
@st.cache_data(ttl=180, show_spinner="Cargando mapeo de IDs de Solicitud desde Google Sheets...")
def get_solicitud_id_to_row_mapping() -> dict[str, int]:
    """
    Obtiene un diccionario que mapea ID_Solicitud -> Fila en Google Sheets
    Se cachea por 3 minutos (180 segundos) para evitar lecturas constantes
    
    Returns:
        dict[str, int]: Diccionario con ID_Solicitud como clave y fila de sheets como valor
    """
    sheets_service: GoogleSheetsService = st.session_state['google_sheets_service']
    solicitudes_ws = sheets_service.get_worksheet(SOLICITUDES_SHEET_ID, 'Solicitudes_MEC')
    
    # Obtener todos los valores de la primera columna (ID_Solicitud)
    id_column = _retry(lambda: solicitudes_ws.col_values(1), label="Get ID_Solicitud column")
    
    # Crear el mapeo: ID_Solicitud (desde fila 2) -> número de fila
    # Fila 1 es el header, así que empezamos desde fila 2
    mapping = {}
    for row_num, solicitud_id in enumerate(id_column[1:], start=2):
        id_cleaned = str(solicitud_id).replace('.0','').strip()
        if solicitud_id and not (id_cleaned in mapping):  # Si no está vacío y no esta ya presente
            mapping[id_cleaned] = row_num
    
    return mapping

# Función Auxiliar para Obtener la Fila de Sheets basado en el ID de Solicitud
def get_solicitud_row_in_google_sheets(solicitud_id: str) -> int:
    """
    Obtiene la fila de Google Sheets para una solicitud específica
    usando el mapeo de IDs cacheado. Si el ID no se encuentra,
    resetea el cache y reintenta una vez.
    
    Args:
        solicitud_id (str): ID de la solicitud
        
    Returns:
        int: Número de fila en Google Sheets
        
    Raises:
        ValueError: Si el ID no es string o no se encuentra en Google Sheets
    """
    if not isinstance(solicitud_id, str):
        raise ValueError("El ID de Solicitud debe ser una cadena de texto (str)., se encontro: {} ({})".format(
            type(solicitud_id), solicitud_id
        ))
    
    solicitud_id_clean = str(solicitud_id).replace('.0','').strip()
    
    # Obtener el mapeo cacheado
    mapping = get_solicitud_id_to_row_mapping()
    
    # Si el ID no está en el mapeo, resetear cache y recargar
    if solicitud_id_clean not in mapping:
        st.cache_data.clear()
        mapping = get_solicitud_id_to_row_mapping()
    
    # Si aún no está, lanzar error
    if solicitud_id_clean not in mapping:
        raise ValueError(f"No se encontró ID de Solicitud '{solicitud_id}' en Google Sheets")
    
    return mapping[solicitud_id_clean]

# Función Auxiliar para Añadir cambios locales
def add_cambios_locales_to_session_state(cambios_locales: list[pd.Series] | pd.DataFrame, cambios_key: str = 'local_solicitudes_changes'):
    # Paso 1: Inicializar el Session State si no esta inicializado
    if not (cambios_key in st.session_state):
        st.session_state[cambios_key] = []

    # Paso 2: Extender la lista
    if isinstance(cambios_locales, pd.DataFrame):
        st.session_state[cambios_key].extend([cambios_locales.iloc[i] for i in range(len(cambios_locales))])
    else:
        st.session_state[cambios_key].extend(cambios_locales)

    print('✅Añadidos Cambios Locales: {}'.format(len(cambios_locales)))

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
    response_df['ID_Solicitud'] = str(new_id)

    # Subimos la respuesta a Google Sheets
    try:
        appendDataFrameToEnd(responses_ws, response_df)
        # Añadimos los Cambios a local
        # A response_df le volvemos Datos_Solicitud y Metadata_Solicitud como diccionarios para que sean más fáciles de manejar en local
        response_df['Datos_Solicitud'] = response_df['Datos_Solicitud'].apply(lambda x: x if isinstance(x, dict) else json.loads(x) if isinstance(x, str) else {})
        response_df['Metadata_Solicitud'] = response_df['Metadata_Solicitud'].apply(lambda x: x if isinstance(x, dict) else json.loads(x) if isinstance(x, str) else {})
        # Devolvemos Timestamp a Datetime
        response_df['Timestamp'] = pd.to_datetime(response_df['Timestamp'], format='%Y-%m-%d %H:%M:%S')
        # Si Fecha_Esperada_Pago no es nula, la convertimos a Datetime
        if 'Fecha_Esperada_Pago' in response_df.columns:
            response_df['Fecha_Esperada_Pago'] = pd.to_datetime(response_df['Fecha_Esperada_Pago'], errors='coerce', format='%Y-%m-%d %H:%M:%S')
        add_cambios_locales_to_session_state(response_df)
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
    solicitud_id = float(solicitud['ID_Solicitud'])
    solicitud_sheets_row = get_solicitud_row_in_google_sheets(str(int(solicitud_id)))
    try:
        # Obtenemos los Headers de la Worksheet guardados en el Session State
        headers = st.session_state.get("solicitudes_headers", [])
        # Organizamos los datos de la solicitud en el orden de los headers
        solicitud_data = [convert_data_to_string(solicitud.get(header, "")) for header in headers]

        # Definimos el Rango de celdas a actualizar en la Worksheet
        cell_range = f"A{solicitud_sheets_row}:{get_column_letter(len(headers))}{solicitud_sheets_row}"

        # Aplicamos la Actualización a la Worksheet (usando _retry para manejar posibles errores de red)
        _retry(lambda: solicitudes_ws.update(range_name=cell_range, values=[solicitud_data]), label="Update Solicitud")

        # Agregamos la serie a los cambios locales
        add_cambios_locales_to_session_state([solicitud])

        return True
    except Exception as e:
        st.error(f"Error al actualizar la solicitud en Google Sheets: {e}")
        return False

def update_massive_solicitudes_in_google_sheets(solicitudes_df: pd.DataFrame) -> bool:
    # Obtenemos el Servicio de Google Sheets desde el Session State de Streamlit
    sheets_service: GoogleSheetsService = st.session_state['google_sheets_service']

    # Abrimos la Worksheet 'Solicitudes_MEC' usando el servicio de Sheets
    solicitudes_ws = sheets_service.get_worksheet(SOLICITUDES_SHEET_ID, 'Solicitudes_MEC')

    # Obtenemos los Headers de la Worksheet guardados en el Session State
    headers = st.session_state.get("solicitudes_headers", [])
    
    # Validación: verificar que headers no esté vacío
    if not headers:
        st.error("No se encontraron headers de Solicitudes. Intente recargar la página.")
        return False
    
    # Validación: verificar que el DataFrame no esté vacío
    if solicitudes_df.empty:
        st.error("No hay solicitudes para actualizar.")
        return False
    
    # Seleccionar solo las columnas que existen en el DataFrame
    headers_disponibles = [h for h in headers if h in solicitudes_df.columns]
    if not headers_disponibles:
        st.error(f"No se encontraron columnas válidas para actualizar. Esperado: {headers}. Recibido: {list(solicitudes_df.columns)}")
        return False

    # Organizamos los datos de las solicitudes en el orden de los headers
    solicitudes_matrix = solicitudes_df[headers_disponibles].values

    # Convertimos el array a una lista de listas
    solicitudes_matrix = solicitudes_matrix.tolist()

    # 2. Construimos la nueva lista asegurando que row es una lista y que row[0] existe
    solicitudes_data = []
    for row in solicitudes_matrix:
        if row: # Verifica que la fila no esté vacía
            id_solicitud = row[0]
            sheet_row = get_solicitud_row_in_google_sheets(id_solicitud)
            row_cleaned = [convert_data_to_string(cell) for cell in row]
            solicitudes_data.append([sheet_row] + row_cleaned)

    # Usamos la función de actualización masiva
    succeded = update_sheet_data_batch(
        ws=solicitudes_ws,
        data=solicitudes_data,
        start_col_letter="A",
        cell_threshold=10000
    )

    if succeded:
        # Añadimos los Cambios a local
        add_cambios_locales_to_session_state(solicitudes_df)
    
    return succeded

# Función Auxiliar para Subir una plantilla masiva de Solicitudes a Sheets
def upload_massive_solicitudes_filtered_plantilla(plantilla_df: pd.DataFrame) -> bool:
    # Obtenemos el Servicio de Google Sheets desde el Session State de Streamlit
    sheets_service: GoogleSheetsService = st.session_state['google_sheets_service']

    # Definimos el Nombre de la Hoja segun el user_email
    user_email = st.session_state['user_email']
    sheet_name = f"Plantilla_{user_email.split('@')[0]}"

    # Abrimos Primero la Spreadsheet
    spreadsheet = sheets_service.get_spreadsheet(SOLICITUDES_SHEET_ID)
    # Ahora Obtenemos la Hoja de la Plantilla masiva (si no existe, la creamos)
    _, plantilla_ws = getWorksheet(spreadsheet, sheet_name, plantilla_df)

    try:
        # Subimos la plantilla masiva a Google Sheets
        uploadToSheets(plantilla_ws, plantilla_df, resizing=True, retry_label="Upload Plantilla Masiva")
        return True
    except Exception as e:
        st.error(f"Error al subir la plantilla masiva a Google Sheets: {e}")
        return False

def upload_log_to_sheets(*,info: str, detail: str):
    # Paso 1: Crear la Lista de Datos del Log
    # Timestamp, Correo del Usuario, Información, Detalle
    log_data = [pd.Timestamp.now(tz='America/Bogota').tz_localize(None), st.session_state['user_email'], info, detail]
    log_data[0] = log_data[0].strftime('%Y-%m-%d %H:%M:%S')  # Convertimos el Timestamp a String para Google Sheets

    # Paso 2: Obtener el Servicio de Google Sheets desde el Session State
    sheets_service: GoogleSheetsService = st.session_state['google_sheets_service']

    # Paso 3 Abrir la Hoja "Logs" en la Worksheet de Configs
    logs_ws = sheets_service.get_worksheet(CONFIGS_SHEET_ID, 'Logs')

    # Paso 4: Agregar la Fila del Log al Final de la Hoja
    _retry(lambda: logs_ws.append_row(log_data), label="Append Log Row")

    # Paso 5: Mostrar un Toast
    st.toast(f"{info}: {detail}", icon="✅")

def upload_addendum_debt(*,
        reference: str,
        cedula: str,
        bank: str,
        number_credit: str,
        aliado: str,
        monto_inicial: float,
        monto_propuesto: Optional[float] = None,
    ):
    # Paso 1: Crear la Lista de Datos del Addendum
    addendum_data = [
        reference,cedula,number_credit,bank,aliado,monto_inicial,(monto_propuesto if monto_propuesto is not None else monto_inicial)
    ]

    # Paso 2: Obtener el Servicio de Google Sheets desde el Session State
    sheets_service: GoogleSheetsService = st.session_state['google_sheets_service']
    # Paso 3: Abrir la Worksheet de Masivas la Hoja 'ADD'
    masivas_ws = sheets_service.get_worksheet(MASIVAS_SHEET_ID, 'ADD')
    # Paso 4: Obtener Valores de Rango B y C
    exisiting_Adds = _retry(lambda: masivas_ws.get_values('B:C'), label="Get Existing Data")[1:]  # Ignoramos el header
    # Paso 5: Verificar si el Addendum ya existe (por cedula y numero de crédito)
    # 5.1 Limpiar las Cedulas y Números de Crédito existentes para compararlos
    exisiting_cedulas_cleaned = [str(row[0]).strip() for row in exisiting_Adds if len(row) > 0]
    existing_numbers_cleaned = [str(row[1]).strip().replace("'","").lstrip("0") for row in exisiting_Adds if len(row) > 1]
    # 5.2 Limpiar la Cedula y Número de Crédito del Addendum a subir
    cedula_cleaned = str(cedula).strip()
    number_credit_cleaned = str(number_credit).strip().replace("'","").lstrip("0")
    # 5.3 Verificar si ya existe
    tuplas_existentes = list(zip(exisiting_cedulas_cleaned, existing_numbers_cleaned))
    if (cedula_cleaned, number_credit_cleaned) in tuplas_existentes:
        st.warning(f"El Addendum con Cédula {cedula_cleaned} y Número de Crédito {number_credit_cleaned} ya existe en la hoja de Masivas. No se puede subir duplicado.")
        return True  # Retornamos True porque no es un error, simplemente no se sube duplicado

    # Paso 6: Agregar la Fila del Addendum al Final de la Hoja 
    # 6.1 Definir el Rango de Celdas a Actualizar
    cell_range = f"A{len(exisiting_Adds)+2}:{get_column_letter(len(addendum_data))}{len(exisiting_Adds)+2}"  # +2 porque la primera fila es el header y la segunda fila es la primera fila de datos
    # 6.2 Aplicar la Actualización a la Worksheet (usando _retry para manejar posibles errores de red)
    try:
        _retry(lambda: masivas_ws.update(range_name=cell_range, values=[addendum_data]), label="Upload Addendum")
        st.toast(f"Addendum subido exitosamente: Cédula {cedula_cleaned}, Número de Crédito {number_credit_cleaned}", icon="ℹ️")
        return True
    except Exception as e:
        st.error(f"Error al subir el Addendum a Google Sheets: {e}")
        return False

def update_base_cruce_info(*, cruce_df: DataFrame[PendienteCruceSchema]) -> bool:
    # Paso 1: Obtener el Servicio de Google Sheets
    sheets_service: GoogleSheetsService = st.session_state['google_sheets_service']
    # Paso 2: Abrir la Hoja 'Pendientes_IdAutDeud' de las Configuraciones
    cruceWS = sheets_service.get_worksheet(CONFIGS_SHEET_ID, 'Pendientes_IdAutDeud')
    original_cruce = cruce_df.copy()
    # Paso 4: Volvemos la Metadata a String
    cruce_df['Metadata'] = cruce_df['Metadata'].apply(lambda m: convert_data_to_string(m))
    # Paso 5: Intentar realizar la Actualización usando applyChanges
    try:
        result = applyChanges(
            ws = cruceWS,
            df = cruce_df,
            identifierCol='Id_Cruce',
            numericCols=['Monto_Actual'],
            semiStrCols=['Cedula'],
            pureStrCols=['Numero_Credito','Banco','Nombre_Cliente'],
        )[0]
        # Añadimos los Cambios Locales
        add_cambios_locales_to_session_state(
            cambios_locales=original_cruce,
            cambios_key='local_cruce_changes'
        )
        return result
    except Exception as e:
        st.error("Error al Subir los Datos del Cruce ```{}```".format(
            e
        ), title="Error de Subida")
        return False

def upload_base_cruce_info(*,cruce_df: DataFrame[PendienteCruceSchema]) -> bool:
    # Paso 1: Obtener el Servicio de Google Sheets
    sheets_service: GoogleSheetsService = st.session_state['google_sheets_service']
    # Paso 2: Abrir la Hoja 'Pendientes_IdAutDeud' de las Configuraciones
    cruceWS = sheets_service.get_worksheet(CONFIGS_SHEET_ID, 'Pendientes_IdAutDeud')
    original_cruce = cruce_df.copy()
    # Paso 3: Volvemos la Metadata a String
    cruce_df['Metadata'] = cruce_df['Metadata'].apply(lambda m: convert_data_to_string(m))
    # Paso 4: Subir la Información
    try:
        appendDataFrameToEnd(cruceWS, cruce_df)
        # Añadimos los cambios locales
        add_cambios_locales_to_session_state(
            cambios_locales=original_cruce,
            cambios_key='local_cruce_changes'
        )
        return True
    except Exception as e:
        st.error("Error al Subir los Datos del Cruce ```{}```".format(
            e
        ), title="Error de Subida")
        return False