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
from data.data_loader import get_solicitud_row_in_google_sheets, normalizeMetadata
from data.data_models import MasivasMetadata, MetadataSolicitud, SolicitudesSchema, PendienteCruceSchema
from modules.constants import COL_CREDITO, COL_ID_CRUCE, COL_MONTO_ACTUAL, ETIQUETA_ADDENDUM, SOLICITUDES_ID_DELAY, SOLICITUDES_SHEET_ID, CONFIGS_SHEET_ID, MASIVAS_SHEET_ID
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
# =====================================================================

# Configuraciones de la Subida a la Base del Mes
MASIVAS_BASE_MES_SHEET = 'Bases mes actual 2024'
MASIVAS_BASE_MES_COLUMNS = [
    'Metadata',
    'Fecha',
    'Hora',
    'ID',
    'Casa',
    'Número de producto',
    'Propuesta Pago',
    'Monto Pago Estructurado',
    'Plazo Estructurado',
    'Portafolio',
    'Monto Portafolio',
]
MASIVAS_PORTFOLIO_COLUMNS = ['Portafolio', 'Monto Portafolio']
MASIVAS_EXISTENTES_COLUMNS = ['Metadata'] + MASIVAS_PORTFOLIO_COLUMNS
MASIVAS_MAX_ROWS_PER_BATCH = 3000

# Función Auxiliar para Obtener el Número de Cuotas de un Pago
def _int_cuotas_pago(pago: dict) -> int:
    try:
        return int(float(pago.get('Cuotas', 1) or 1))
    except (TypeError, ValueError):
        return 1

# Función Auxiliar para Calcular la 'Propuesta Pago' de un Registro
def _calcular_propuesta_pago(*, mtdt: dict, monto_actual_fila: Optional[float] = None) -> float:
    # Paso 1: Pago con el Mínimo de Plazos (el Monto_Propuesto quedó guardado como Pago a 1 Cuota)
    pagos = mtdt.get('Pagos_Cuotas') or []
    if pagos:
        pago_min = min(pagos, key=_int_cuotas_pago)
        monto_pago = pago_min.get('Monto')
        if (monto_pago is not None) and pd.notna(monto_pago):
            return float(monto_pago)
    # Paso 2: Si tampoco hay, se usa el Monto_Actual de la Deuda Identificada
    monto_original = mtdt.get('Monto_Actual_Original')
    if (monto_original is not None) and pd.notna(monto_original):
        return float(monto_original)
    id_definitivo = str(mtdt.get('Id_Definitivo') or '')
    for deuda in (mtdt.get('Deudas_Posibles') or []):
        if str(deuda.get('Id_Deuda') or '') == id_definitivo:
            monto_deuda = deuda.get('Monto_Actual')
            if (monto_deuda is not None) and pd.notna(monto_deuda):
                return float(monto_deuda)
    # Paso 3: Último caso, el Monto_Actual de la fila del cruce
    if (monto_actual_fila is not None) and pd.notna(monto_actual_fila):
        return float(monto_actual_fila)
    return np.nan

# Función Auxiliar para Calcular el Pago y Plazo Estructurado (Mayor Plazo)
def _calcular_pago_estructurado(mtdt: dict) -> tuple[float, int]:
    pagos = mtdt.get('Pagos_Cuotas') or []
    pagos_estructurados = [pago for pago in pagos if _int_cuotas_pago(pago) > 1]
    if not pagos_estructurados:
        return np.nan, np.nan # type: ignore
    pago_mayor = max(pagos_estructurados, key=_int_cuotas_pago)
    monto_mayor = pago_mayor.get('Monto')
    monto_mayor = float(monto_mayor) if (monto_mayor is not None) and pd.notna(monto_mayor) else np.nan
    return monto_mayor, _int_cuotas_pago(pago_mayor)

# Función Auxiliar para Construir la Metadata de Masivas (MasivasMetadata)
def _construir_metadata_masivas(*, id_cruce: str, mtdt_cruce: dict, id_portafolio: str = '', pab_portafolio: Optional[float] = None) -> MasivasMetadata:
    # Se incluyen TODAS las Claves del Esquema (las Opcionales quedan en None si no aplican)
    # El Tipo_Contraoferta reemplaza a Es_Maximo_Descuento (ya indica si es 'Descuento Máximo')
    fecha_limite = mtdt_cruce.get('Fecha_Limite_Pago')
    mtdt = MasivasMetadata(
        Id_Cruce=str(id_cruce),
        Tipo_Contraoferta=(mtdt_cruce.get('Tipo_Contraoferta') or 'Descuento Máximo'), # type: ignore
        Fecha_Limite_Uso=(fecha_limite if (fecha_limite is not None) and pd.notna(fecha_limite) else None), # type: ignore
        Alias=(str(mtdt_cruce.get('Alias_Casa')) if mtdt_cruce.get('Alias_Casa') else None),
        Id_Portafolio=str(id_portafolio or ''),
        PaB_Portafolio=(float(pab_portafolio) if (pab_portafolio is not None) and pd.notna(pab_portafolio) else None),
    )
    return mtdt

# Función para Preparar los Datos Cruzados con las Columnas de la Base del Mes
def preparar_datos_base_mes(
        *,
        cruce_df: pd.DataFrame,
        distribucion_df: Optional[pd.DataFrame] = None,
        columnas_portafolio: Optional[list[str]] = None,
    ) -> pd.DataFrame:
    columnas_salida = [COL_ID_CRUCE] + MASIVAS_BASE_MES_COLUMNS
    df = cruce_df.copy()
    if df.empty:
        return pd.DataFrame(columns=columnas_salida)

    # Paso 1: Filtrar únicamente los Registros Cruzados (Id_Definitivo real, sin ADDENDUM)
    df['_Id_Definitivo'] = df['Metadata'].apply(lambda m: str(m.get('Id_Definitivo') or '').strip())
    mask_cruzados = df['_Id_Definitivo'].ne('') & df['_Id_Definitivo'].str.upper().ne(ETIQUETA_ADDENDUM)
    df = df.loc[mask_cruzados].copy()
    # Paso 1.1: Descartar los Registros sin Fecha Límite de Pago (la Metadata de Masivas la Exige)
    mask_fecha = df['Metadata'].apply(lambda m: pd.notna(m.get('Fecha_Limite_Pago')))
    if not mask_fecha.all():
        st.warning(
            "Se omitieron **{:,}** registro(s) sin Fecha Límite de Pago válida (no cumplen el esquema de Masivas).".format(
                int((~mask_fecha).sum())
            ),
            icon="⚠️",
        )
        df = df.loc[mask_fecha].copy()
    if df.empty:
        return pd.DataFrame(columns=columnas_salida)

    # Paso 2: Calcular 'Propuesta Pago' y el Pago/Plazo Estructurado (Mayor Plazo)
    df['_Propuesta_Pago'] = df.apply(
        lambda fila: _calcular_propuesta_pago(
            mtdt=fila['Metadata'],
            monto_actual_fila=fila.get(COL_MONTO_ACTUAL),
        ),
        axis=1,
    )
    pagos_estructurados = df['Metadata'].apply(_calcular_pago_estructurado)
    df['_Monto_Estructurado'] = [pago[0] for pago in pagos_estructurados]
    df['_Plazo_Estructurado'] = [pago[1] for pago in pagos_estructurados]

    # Paso 3: Determinar los Portafolios según la Distribución del tab Control
    df['_Portafolio'] = ''
    df['_Monto_Portafolio'] = np.nan
    df['_Id_Portafolio'] = ''
    columnas_grupo = [col for col in (columnas_portafolio or []) if col in df.columns]
    if (distribucion_df is not None) and (not distribucion_df.empty) and columnas_grupo:
        # 3.1: Mapear si el Registro quedó Dentro de un Grupo Distribuido
        flags_distribucion = (
            distribucion_df
            .drop_duplicates(subset=COL_ID_CRUCE, keep='last')
            .set_index(COL_ID_CRUCE)['Portafolio_Distribuido']
        )
        df['_Distribuido'] = df[COL_ID_CRUCE].map(flags_distribucion).fillna(False).astype(bool)
        # 3.2: Calcular el Tamaño, el Monto y los Ids de cada Grupo de Portafolio
        grupos = df.groupby(columnas_grupo, dropna=False)
        tamano_grupo = grupos[COL_ID_CRUCE].transform('size')
        monto_grupo = grupos['_Propuesta_Pago'].transform('sum')
        ids_grupo = grupos[COL_ID_CRUCE].transform(lambda ids: '-'.join(str(i) for i in ids))
        # 3.3: Solo los Grupos Distribuidos con más de una Deuda se marcan como Portafolio
        mask_portafolio = df['_Distribuido'] & (tamano_grupo > 1)
        df.loc[mask_portafolio, '_Portafolio'] = 'SI'
        df.loc[mask_portafolio, '_Monto_Portafolio'] = monto_grupo[mask_portafolio].round(2)
        df.loc[mask_portafolio, '_Id_Portafolio'] = ids_grupo[mask_portafolio]

    # Paso 4: Fecha y Hora Actual en la Zona Horaria de Bogotá
    ahora = pd.Timestamp.now(tz='America/Bogota')
    fecha_actual = ahora.strftime('%d/%m/%Y')
    hora_actual = ahora.strftime('%X')

    # Paso 5: Construir el DataFrame con las Columnas de la Base del Mes
    numero_producto = (
        df[COL_CREDITO].apply(lambda v: str(v).replace('.0', '').strip() if pd.notna(v) else '')
        if COL_CREDITO in df.columns else pd.Series('', index=df.index)
    )
    metadata_masivas = df.apply(
        lambda fila: convert_data_to_string(
            _construir_metadata_masivas(
                id_cruce=str(fila[COL_ID_CRUCE]),
                mtdt_cruce=fila['Metadata'],
                id_portafolio=str(fila.get('_Id_Portafolio') or ''),
                pab_portafolio=(fila.get('_Monto_Portafolio') if fila.get('_Portafolio') == 'SI' else None),
            )
        ),
        axis=1,
    )
    df_salida = pd.DataFrame({
        COL_ID_CRUCE: df[COL_ID_CRUCE].astype(str),
        'Metadata': metadata_masivas,
        'Fecha': fecha_actual,
        'Hora': hora_actual,
        'ID': df['_Id_Definitivo'],
        'Casa': df['Metadata'].apply(lambda m: str(m.get('Casa_Cobro') or '')),
        'Número de producto': numero_producto,
        'Propuesta Pago': df['_Propuesta_Pago'].apply(lambda v: round(float(v), 2) if pd.notna(v) else ''),
        'Monto Pago Estructurado': df['_Monto_Estructurado'].apply(lambda v: round(float(v), 2) if pd.notna(v) else ''),
        'Plazo Estructurado': df['_Plazo_Estructurado'].apply(lambda v: int(v) if pd.notna(v) else ''),
        'Portafolio': df['_Portafolio'],
        'Monto Portafolio': df['_Monto_Portafolio'].apply(lambda v: round(float(v), 2) if pd.notna(v) else ''),
    })
    return df_salida.reset_index(drop=True)

# Función para Obtener el Mapeo Id_Cruce -> Fila de Sheets de la Base del Mes (SIN Cache)
def get_masivas_rows_by_id_cruce(*, ws: gspread.Worksheet, headers: list[str]) -> tuple[dict[str, int], int]:
    """Obtiene el mapeo Id_Cruce -> fila de Sheets de la hoja de la Base del Mes.

    No se debe cachear: dos subidas seguidas necesitan leer el estado real de la hoja.
    Devuelve el mapeo y la última fila con datos de la hoja (según la columna Metadata).
    """
    if 'Metadata' not in headers:
        return {}, 0
    metadata_col = headers.index('Metadata') + 1
    valores = _retry(lambda: ws.col_values(metadata_col), label="Get Base Mes Metadata Column")
    filas_id_cruce: dict[str, int] = {}
    for fila_sheets, valor in enumerate(valores[1:], start=2):
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
    return filas_id_cruce, len(valores)

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

# Función para Subir/Actualizar los Datos Cruzados en la Base del Mes (Masivas)
def upload_base_mes_info(
        *,
        cruce_df: pd.DataFrame,
        distribucion_df: Optional[pd.DataFrame] = None,
        columnas_portafolio: Optional[list[str]] = None,
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

    # Paso 7: Mostrar el Resumen de la Subida
    if exito:
        st.toast(
            "✅ Base del Mes actualizada: {} nuevo(s) / {} existente(s)".format(len(df_nuevos), len(df_existentes)),
            icon="✅",
        )
        st.success(
            "✅ **Base del Mes actualizada**: **{:,}** registro(s) nuevo(s) y **{:,}** registro(s) existente(s) "
            "con Metadata y Portafolio actualizados.".format(len(df_nuevos), len(df_existentes)),
        )
    return exito