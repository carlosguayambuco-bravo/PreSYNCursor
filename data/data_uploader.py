# Estándar usando Pep8
# Librerías de Python
from typing import Any, Optional
import json
from time import sleep
from urllib import response
# Librerías de Terceros
import gspread
from pandera.typing import DataFrame
import numpy as np
import pandas as pd
import streamlit as st
# Librerías Locales
from data.data_loader import get_solicitud_row_in_google_sheets, normalizeMetadata, parse_metadata_cruce
from data.data_models import MetadataSolicitud, SolicitudesSchema, PendienteCruceSchema
from modules.constants import COL_ID_CRUCE, MASIVAS_BASE_MES_COLUMNS, MASIVAS_BASE_MES_SHEET, MASIVAS_EXISTENTES_COLUMNS, MASIVAS_MAX_ROWS_PER_BATCH, SOLICITUDES_ID_DELAY, SOLICITUDES_SHEET_ID, CONFIGS_SHEET_ID, MASIVAS_SHEET_ID
from modules.id_aut_deud.helpers import preparar_datos_base_mes
from utils.helpers_sheets import _retry, appendDataFrameToEnd, applyChanges, build_column_batch_updates, col_to_letter, convert_data_to_string, get_column_letter, getWorksheet, uploadToSheets, update_sheet_data_batch
from services.google_sheets import GoogleSheetsService

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
        # Volvemos la Metadata_Solicitud a su respectivo TypedDict
        response_df['Metadata_Solicitud'] = response_df['Metadata_Solicitud'].apply(lambda d: MetadataSolicitud(**normalizeMetadata(d)))
        # Devolvemos Timestamp a Datetime
        response_df['Timestamp'] = pd.to_datetime(response_df['Timestamp'], format='%Y-%m-%d %H:%M:%S')
        # Si Fecha_Esperada_Pago no es nula, la convertimos a Datetime
        if 'Fecha_Esperada_Pago' in response_df.columns:
            response_df['Fecha_Esperada_Pago'] = pd.to_datetime(response_df['Fecha_Esperada_Pago'], errors='coerce', format='%Y-%m-%d %H:%M:%S')
        response_df['Tipo_Pago'] = response_df["Tipo_Pago"].replace(r'^\s*$', np.nan, regex=True)
        # Agregamos que no es Histórico
        response_df['Es_Historico'] = False
        # Agregamos el JSON_Respuesta como NaN
        response_df['JSON_Respuesta'] = pd.NA
        # Agregamos Estado_Liquidacion como "N/A"
        response_df['Estado_Liquidacion'] = "N/A"
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

# =====================================================================
# Subida a la Base del Mes (Hoja 'Bases mes actual 2024' de Masivas)
# Las Funciones de Transformación/Preparación de los Datos viven en
# modules/id_aut_deud/helpers.py (preparar_datos_base_mes)
# =====================================================================

# Función para Obtener el Mapeo Id_Cruce -> Fila de Sheets de la Base del Mes (SIN Cache)
def get_masivas_rows_by_id_cruce(*, ws: gspread.Worksheet, headers: list[str]) -> tuple[dict[str, int], int]:
    """Obtiene el mapeo Id_Cruce -> fila de Sheets de la hoja de la Base del Mes.

    No se debe cachear: dos subidas seguidas necesitan leer el estado real de la hoja.
    Devuelve el mapeo y la última fila con datos de la hoja, calculada como el máximo
    entre TODAS las columnas que se actualizan (no solo Metadata), ya que puede haber
    registros agregados manualmente sin la Metadata.
    """
    if 'Metadata' not in headers:
        return {}, 0
    # Paso 1: Armar los Rangos a Revisar (Metadata + Todas las Columnas que se Actualizan)
    columnas_revisar = ['Metadata'] + [
        columna for columna in MASIVAS_BASE_MES_COLUMNS
        if (columna != 'Metadata') and (columna in headers)
    ]
    rangos = [
        "{letra}:{letra}".format(letra=col_to_letter(headers.index(columna) + 1))
        for columna in columnas_revisar
    ]
    # Paso 2: Traer los Valores de Todos los Rangos en Una Sola Llamada
    valores_rangos = _retry(lambda: ws.batch_get(rangos), label="Get Base Mes Columns")
    valores_por_columna = dict(zip(columnas_revisar, valores_rangos))

    # Paso 3: Calcular la Última Fila con Datos (el Máximo entre las Columnas Revisadas)
    ultima_fila = 1
    for columna in columnas_revisar:
        valores = valores_por_columna.get(columna) or []
        for idx in range(len(valores) - 1, -1, -1):
            celda = valores[idx][0] if valores[idx] else None
            if (celda is not None) and (str(celda).strip() != ''):
                ultima_fila = max(ultima_fila, idx + 1)
                break

    # Paso 4: Construir el Mapeo Id_Cruce -> Fila con la Columna Metadata
    filas_id_cruce: dict[str, int] = {}
    for fila_sheets, fila in enumerate((valores_por_columna.get('Metadata') or [])[1:], start=2):
        valor = fila[0] if fila else None
        if (valor is None) or (valor == ''):
            continue
        try:
            mtdt = json.loads(valor)
        except (TypeError, ValueError):
            continue
        if not isinstance(mtdt, dict):
            continue
        id_cruce = mtdt.get('Id_Cruce')
        if id_cruce in (None, ''):
            continue
        # En Caso de Duplicados nos Quedamos con la Última Fila (la Más Reciente)
        filas_id_cruce[str(id_cruce)] = fila_sheets
    return filas_id_cruce, ultima_fila

# Función Auxiliar para Enviar los Datos Agrupados por Columnas usando batch_update
def _enviar_batches_base_mes(*, ws: gspread.Worksheet, values_by_column: dict[str, dict[int, Any]], label: str) -> bool:
    batches = build_column_batch_updates(
        values_by_column=values_by_column,
        row_chunk_size=MASIVAS_MAX_ROWS_PER_BATCH,
    )
    try:
        for idx, batch in enumerate(batches, start=1):
            _retry(
                lambda batch=batch: ws.batch_update(batch, value_input_option="USER_ENTERED"),
                label="{} (Lote {}/{})".format(label, idx, len(batches)),
            )
            if idx < len(batches):
                sleep(0.5)
        return True
    except Exception as e:
        st.error("Error al actualizar la Base del Mes en Google Sheets: ```{}```".format(e), title="Error de Subida")
        return False

# Función Auxiliar para Actualizar los Portafolios Ya Presentes en la Base del Mes
def _actualizar_portafolios_base_mes(*, ws: gspread.Worksheet, headers: list[str], df_existentes: pd.DataFrame) -> bool:
    # Se actualiza también la Metadata para que el PaB_Portafolio de los nuevos Portafolios
    # quede sincronizado (y se limpie cuando un registro deja de ser Portafolio)
    values_by_column: dict[str, dict[int, Any]] = {}
    for columna in MASIVAS_EXISTENTES_COLUMNS:
        col_letter = col_to_letter(headers.index(columna) + 1)
        values_by_column[col_letter] = {
            int(fila['_Fila_Sheets']): fila[columna]
            for _, fila in df_existentes.iterrows()
        }
    return _enviar_batches_base_mes(ws=ws, values_by_column=values_by_column, label="Update Portafolios Base Mes")

# Función Auxiliar para Agregar los Registros Nuevos a la Base del Mes por Columna
def _agregar_registros_base_mes(*, ws: gspread.Worksheet, headers: list[str], df_nuevos: pd.DataFrame, start_row: int) -> bool:
    values_by_column: dict[str, dict[int, Any]] = {}
    for columna in MASIVAS_BASE_MES_COLUMNS:
        col_letter = col_to_letter(headers.index(columna) + 1)
        values_by_column[col_letter] = {
            start_row + offset: fila[columna]
            for offset, (_, fila) in enumerate(df_nuevos.iterrows())
        }
    return _enviar_batches_base_mes(ws=ws, values_by_column=values_by_column, label="Append Base Mes")

# Función Auxiliar para Marcar como 'Subido Alianzas' los Registros Subidos a la Base del Mes
def _marcar_cruce_subido_alianzas(*, cruce_df: pd.DataFrame, ids_subidos: set[str]) -> bool:
    # Paso 1: Filtrar únicamente los Registros que se Subieron a la Base del Mes
    ids_subidos = {str(id_cruce) for id_cruce in ids_subidos}
    mask_subidos = cruce_df[COL_ID_CRUCE].astype(str).isin(ids_subidos)
    df_actualizar = cruce_df.loc[mask_subidos].copy()
    if df_actualizar.empty:
        return True

    # Paso 2: Actualizar la Metadata (Etiqueta de Estado del Cruce y Última Actualización)
    ahora = pd.Timestamp.now(tz='America/Bogota').tz_localize(None)

    def actualizar_mtdt(mtdt: dict) -> dict:
        mtdt = dict(mtdt)
        mtdt['Cruce_Status'] = 'Subido Alianzas'
        mtdt['Ultima_Actualizacion'] = ahora
        return parse_metadata_cruce(mtdt)

    df_actualizar['Metadata'] = df_actualizar['Metadata'].apply(actualizar_mtdt)

    # Paso 3: Dejar únicamente las Columnas del Esquema y Actualizar Sheets (Guardando los Cambios Locales)
    cols_esquema = [col for col in PendienteCruceSchema.__fields__.keys() if col in df_actualizar.columns]
    df_actualizar = df_actualizar[cols_esquema]
    return update_base_cruce_info(cruce_df=df_actualizar)

# Función para Subir/Actualizar los Datos Cruzados en la Base del Mes (Masivas)
def upload_base_mes_info(
        *,
        cruce_df: pd.DataFrame,
        distribucion_df: Optional[pd.DataFrame] = None,
        columnas_portafolio: Optional[list[str]] = None,
        tipo_portafolio: Optional[str] = None,
    ) -> bool:
    # Paso 1: Obtener el Servicio de Google Sheets y Abrir la Hoja de la Base del Mes
    sheets_service: GoogleSheetsService = st.session_state['google_sheets_service']
    try:
        base_mes_ws = sheets_service.get_worksheet(MASIVAS_SHEET_ID, MASIVAS_BASE_MES_SHEET)
        headers = _retry(lambda: base_mes_ws.row_values(1), label="Get Base Mes Headers")
    except Exception as e:
        st.error("No se pudo abrir la hoja '{}' de Masivas: ```{}```".format(MASIVAS_BASE_MES_SHEET, e), title="Error de Subida")
        return False

    # Paso 2: Validar que Todas las Columnas Requeridas Existan (Header por Header)
    columnas_faltantes = [col for col in MASIVAS_BASE_MES_COLUMNS if col not in headers]
    if columnas_faltantes:
        st.error(
            "No se puede realizar la actualización porque no se encontraron las siguientes columnas en la hoja '{}': **{}**".format(
                MASIVAS_BASE_MES_SHEET, ', '.join(columnas_faltantes)
            ),
            title="Error de Columnas",
        )
        return False

    # Paso 3: Preparar los Datos (Solo Registros Cruzados y sin ADDENDUM)
    df_subida = preparar_datos_base_mes(
        cruce_df=cruce_df,
        distribucion_df=distribucion_df,
        columnas_portafolio=columnas_portafolio,
        tipo_portafolio=tipo_portafolio,
    )
    if df_subida.empty:
        st.warning("No hay registros cruzados (con Id_Definitivo y sin ADDENDUM) para subir a la Base del Mes.", icon="⚠️")
        return False

    # Paso 4: Obtener el Mapeo Id_Cruce -> Fila (SIN Cache: la Hoja Pudo Cambiar entre Subidas)
    filas_id_cruce, ultima_fila = get_masivas_rows_by_id_cruce(ws=base_mes_ws, headers=headers)

    # Paso 5: Separar los Registros Nuevos de los Ya Presentes en la Hoja
    df_subida['_Fila_Sheets'] = df_subida[COL_ID_CRUCE].map(filas_id_cruce)
    df_existentes = df_subida[df_subida['_Fila_Sheets'].notna()].copy()
    df_nuevos = df_subida[df_subida['_Fila_Sheets'].isna()].copy()

    # Paso 6: Actualizar los Portafolios Ya Presentes y Agregar los Registros Nuevos
    exito = True
    if not df_existentes.empty:
        exito = _actualizar_portafolios_base_mes(ws=base_mes_ws, headers=headers, df_existentes=df_existentes)
    if exito and not df_nuevos.empty:
        exito = _agregar_registros_base_mes(ws=base_mes_ws, headers=headers, df_nuevos=df_nuevos, start_row=ultima_fila + 1)

    # Paso 7: Marcar los Registros Subidos con la Etiqueta de Estado 'Subido Alianzas' (Trazabilidad)
    if exito:
        try:
            exito = _marcar_cruce_subido_alianzas(
                cruce_df=cruce_df,
                ids_subidos=set(df_subida[COL_ID_CRUCE].astype(str)),
            )
        except Exception as e:
            st.error(
                "La Base del Mes se actualizó, pero no se pudo guardar la Etiqueta de Estado "
                "'Subido Alianzas' en los registros del cruce: ```{}```. Vuelve a intentar la subida.".format(e),
                title="Error de Trazabilidad",
            )
            exito = False
        else:
            if not exito:
                st.error(
                    "La Base del Mes se actualizó, pero no se pudo guardar la Etiqueta de Estado "
                    "'Subido Alianzas' en los registros del cruce. Vuelve a intentar la subida.",
                    title="Error de Trazabilidad",
                )

    # Paso 8: Mostrar el Resumen de la Subida
    if exito:
        st.toast(
            "✅ Base del Mes actualizada: {} nuevo(s) / {} existente(s)".format(len(df_nuevos), len(df_existentes)),
            icon="✅",
        )
        st.success(
            "✅ **Base del Mes actualizada**: **{:,}** registro(s) nuevo(s) y **{:,}** registro(s) existente(s) "
            "con Metadata y Portafolio actualizados. Los registros subidos quedaron marcados como "
            "**'Subido Alianzas'**.".format(len(df_nuevos), len(df_existentes)),
        )
    return exito