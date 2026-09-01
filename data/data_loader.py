# Archivo para Inicializar los Servicios de la Aplicación
# Usando estándar Pep8
# Librerías de Python
from collections import defaultdict
import json
# Librerías de Terceros
from gspread_dataframe import get_as_dataframe
from pandas import notna
from pandera.typing import DataFrame
import gspread
import numpy as np
import pandas as pd
import streamlit as st
# Librerías Locales
from core.permissions import PERMISSIONS_DICT
from data.data_models import AddendumsSchema, AhorroSchema, AliadosSchema, CarteraActivaSchema, ConfigsSchema, DeudasActivasSchema, DeudasPosiblesCruce, HeadCountSchema, InputCruceSchema, LiquidationsSchema, LogsSchema, MasivasMetadata, MasivasSchema, MetadataPendienteCruce, PaBIdealSchema, PagosCuotasCruce, PendienteCruceSchema, PorCobrarSchema, SolicitudesSchema, UserPermissionsSchema
from data.data_uploader import get_solicitud_id_to_row_mapping
from modules.bank_normalizer import normalizar_banco, normalizar_bancos_vectorizado
from modules.constants import ALIADOS_SHEET_ID, CARTERA_ACTIVA_SHEET_ID, CONFIGS_SHEET_ID, DEFAULT_DISCOUNT_PL, ESTADOS_LIQUIDACION, HCNEGO_SHEET_ID, HOUR_WAIT, DAY_WAIT, LIQUIDACIONES_SHEET_ID, MASIVAS_SHEET_ID, PABIDEAL_SHEET_ID, QUERY_ACTIVE_DEBTS, QUERY_DEBT_TO_REFERENCE, QUERY_DEUDAS, QUERY_LAST_UPDATE, QUERY_PLANES, QUERY_TOTAL_REPARADORAS, REFCHANGES_SHEET_ID, SALDOS_SHEET_ID, SUB_ESTADOS_LIQUIDACION, WEEK_WAIT, MIN_10_WAIT, SOLICITUDES_SHEET_ID
from services.google_sheets import GoogleSheetsService
from services.metabase import MetabaseService
from utils.helpers_general import cleanNumber, imputeNans, getMesOperativo, mesesDict, parsePercentage
from utils.helpers_sheets import _retry

#--> Carga de Solicitudes del Mes en Curso
@st.cache_data(show_spinner="Cargando Solicitudes del Mes en Curso desde Google Sheets...", ttl=MIN_10_WAIT)
def load_solicitudes_mec() -> DataFrame[SolicitudesSchema]:

    # Primero Obtenemos la Spreadsheet de Solicitudes desde Google Sheets
    google_sheets_service: GoogleSheetsService = st.session_state["google_sheets_service"]

    # Obtenemos el DF de la Hoja "Solicitudes_MEC"
    solicitudes_df = google_sheets_service.get_sheet_as_dataframe(SOLICITUDES_SHEET_ID, 'Solicitudes_MEC')

    # Guardamos los Headers en el Session State
    st.session_state["solicitudes_headers"] = list(solicitudes_df.columns)

    # Volvemos las Columnas Necesarias a Timestamp
    for col in ['Timestamp', 'Fecha_Esperada_Pago', 'Fecha_Respuesta', 'Fecha_Limite_Pago']:
        solicitudes_df[col] = pd.to_datetime(solicitudes_df[col], errors='coerce', dayfirst=False)

    # Volvemos las Columnas Referencia, ID_Solicitud y Cedula a String
    for col in ['Referencia', 'ID_Solicitud', 'Cedula', 'Ids_Deuda']:
        solicitudes_df[col] = solicitudes_df[col].apply(lambda s: str(s).replace('.0','').strip() if pd.notna(s) else '')

    # Cargamos los Cambios de Referencia y los Aplicamos
    changeRefDict = load_reference_changes()
    solicitudes_df['Referencia'] = solicitudes_df['Referencia'].apply(lambda s: changeRefDict.get(s,s))

    # Guardamos el Primer ID_Solicitud
    st.session_state["first_id_solicitud"] = solicitudes_df['ID_Solicitud'].iloc[0] if not solicitudes_df.empty else None

    # Imputamos Ejecutivo con 'Sin Asignar'
    imputeNans(solicitudes_df, 'Ejecutivo', 'Sin Asignar')

    # Corregimos los IDs de Solicitud Duplicados (si existen) antes de validar el esquema
    solicitudes_df = fix_duplicated_solicitud_ids(solicitudes_df)

    # Validamos el DataFrame con el esquema (Si no esta vacio)
    if not solicitudes_df.empty:
        solicitudes_df = SolicitudesSchema.validate(solicitudes_df) 
    else:
        solicitudes_df = SolicitudesSchema.empty()

    # Hacemos Parsing de la Columna Datos_Solicitud y Metadata_Solicitud a JSON
    for col in ['Datos_Solicitud', 'Metadata_Solicitud','JSON_Respuesta']:
        solicitudes_df[col] = solicitudes_df[col].apply(lambda s: json.loads(s) if pd.notna(s) else {})
    

    # Por último, reiniciamos los cambios locales
    st.session_state['local_solicitudes_changes'] = []

    # Devolvemos el DataFrame
    return solicitudes_df

# Función Auxiliar para Corregir los IDs de Solicitud Duplicados en la Worksheet y en el DF
def fix_duplicated_solicitud_ids(solicitudes_df: pd.DataFrame) -> pd.DataFrame:
    # Verificamos si existen IDs Duplicados en las Solicitudes (dejando el primero de cada grupo)
    duplicated_mask = solicitudes_df['ID_Solicitud'].duplicated(keep='first')

    # Si no hay duplicados, devolvemos el DF tal cual
    if not duplicated_mask.any():
        return solicitudes_df

    # Obtenemos la Worksheet de Solicitudes para corregir los IDs directamente en Sheets
    google_sheets_service: GoogleSheetsService = st.session_state["google_sheets_service"]
    solicitudes_ws = google_sheets_service.get_worksheet(SOLICITUDES_SHEET_ID, 'Solicitudes_MEC')

    # Calculamos el último ID de la secuencia (el más alto) para mantener el orden
    numeric_ids = pd.to_numeric(solicitudes_df['ID_Solicitud'], errors='coerce')
    last_id = int(numeric_ids.max()) if numeric_ids.notna().any() else 0

    # Corregimos cada ID duplicado (siempre el último de cada grupo) con last_id + 1
    for idx in solicitudes_df.loc[duplicated_mask].index:
        last_id += 1
        new_id = str(last_id)

        # Actualizamos el ID en el DF
        solicitudes_df.loc[idx, 'ID_Solicitud'] = new_id

        # Actualizamos el ID en Sheets (la fila es index + 2 y la columna del ID siempre es A)
        sheet_row = idx + 2
        _retry(lambda nid=new_id, row=sheet_row: solicitudes_ws.update(range_name=f"A{row}", values=[[nid]]), label=f"Fix duplicated ID row {sheet_row}")

    # Reiniciamos el cache del mapeo de IDs a Filas para evitar errores de mapeo
    get_solicitud_id_to_row_mapping.clear()

    # Devolvemos el DF corregido
    return solicitudes_df

# --> Carga de Solicitudes del Mes en Curso (Aplicando los Cambios locales)
def load_current_month_solicitudes() -> pd.DataFrame:
    # 1: Cargamos las Solicitudes del Mes en Curso desde Google Sheets
    solicitudes_df = load_solicitudes_mec()

    st.session_state["solicitudes_headers"] = list(solicitudes_df.columns)

    sols_ajustadas = solicitudes_df.copy()

    # 2: Aplicamos los Cambios Locales
    if ('local_solicitudes_changes' in st.session_state) and len(st.session_state['local_solicitudes_changes']) > 0:

        # Paso 1: Creamos un DF con todas las Series
        local_changes_df = pd.DataFrame(st.session_state['local_solicitudes_changes'])
        # Quitamos Duplicados dejando el último
        local_changes_df = local_changes_df.drop_duplicates(subset='ID_Solicitud', keep='last')
        # Limpiamos Fechas
        for col in ['Timestamp', 'Fecha_Esperada_Pago', 'Fecha_Respuesta', 'Fecha_Limite_Pago']:
            if col in local_changes_df.columns:
                local_changes_df[col] = pd.to_datetime(local_changes_df[col], errors='coerce', dayfirst=False)

        # Paso 2: Preparamos Operaciones por Índices dejando ID_Solicitud
        local_changes_df = local_changes_df.set_index('ID_Solicitud', drop=False)
        sols_ajustadas = sols_ajustadas.set_index('ID_Solicitud', drop=False)

        # Paso 3: Diferenciar nuevos de Existentes
        indices_existentes = sols_ajustadas.index.intersection(local_changes_df.index)
        indices_nuevos = local_changes_df.index.difference(sols_ajustadas.index)

        # A) Actualizar los que ya existen
        if not indices_existentes.empty:
            sols_ajustadas.update(local_changes_df.loc[indices_existentes])
        
        # B) Añadir los Nuevos
        if not indices_nuevos.empty:
            sols_ajustadas = pd.concat([sols_ajustadas, local_changes_df.loc[indices_nuevos]], axis=0)

        # Restauramos el Indice
        sols_ajustadas = sols_ajustadas.reset_index(drop=True)

    # 3: Devolver el Nuevo DF
    return sols_ajustadas

# --> Carga de Cambios de Referencias
@st.cache_data(show_spinner="Cargando Cambios de Referencias desde Google Sheets...", ttl=HOUR_WAIT)
def load_reference_changes() -> dict[str,str]:

    # Primero Obtenemos la Spreadsheet de Cambios de Referencias desde Google Sheets
    google_sheets_service: GoogleSheetsService = st.session_state["google_sheets_service"]

    # Abrimos la Hoja llamada 'Cambios de Referencia'
    ref_changes_ws = google_sheets_service.get_worksheet(REFCHANGES_SHEET_ID, 'Cambios de Referencia')

    # Obtenemos los Valores como records
    ref_values = _retry(lambda: ref_changes_ws.get_all_values())

    ## La llave sera la referencia vieja y el valor la referencia nueva
    if len(ref_values)>0 and len(ref_values[0])>1:
        refChangesDict = {str(row[0]).replace('.0','').strip():str(row[1]).replace('.0','').strip() for row in ref_values} # type: ignore
    else:
        refChangesDict = {}

    # Devolvemos el Diccionario de Cambios de Referencias
    return refChangesDict

# Función Auxiliar de Procesamiento de Información de DF de Saldos
def processDF(ws: gspread.Worksheet, refChangesDict: dict) -> DataFrame[AhorroSchema]:
    # Obtenemos los Datos como un DF
    df = _retry(lambda: get_as_dataframe(ws, evaluate_formulas=True, skiprows=3))

    # Renombramos Columnas REFERENCIA a Referencia y SALDO a Ahorro_Total
    df = df.rename(columns={'REFERENCIA':'Referencia','SALDO':'Ahorro_Total'}) # type: ignore

    # Dejamos solo dichas Columnas
    df = df[['Referencia','Ahorro_Total']]

    # Volvemos la Columna Referencia a String
    df['Referencia'] = df['Referencia'].apply(lambda s: str(s).replace('.0','').strip())
    # Aplicamos el Cambio de Referencia
    df['Referencia'] = df['Referencia'].apply(lambda s: refChangesDict.get(s,s))

    # Volvemos el Saldo a Número
    df['Ahorro_Total'] = df['Ahorro_Total'].apply(cleanNumber)
    df['Ahorro_Total'] = pd.to_numeric(df['Ahorro_Total'], errors='coerce')

    # Validamos el DF con el esquema (Si no esta vacío)
    if not df.empty:
        df = AhorroSchema.validate(df)
    else:
        df = AhorroSchema.empty()

    # Devolvemos el DF
    return df

# --> Carga de Saldos de Clientes (saldosDF)
@st.cache_data(show_spinner="Cargando Saldos de Clientes desde Google Sheets...", ttl=HOUR_WAIT)
def load_client_balances() -> dict[str, dict[str, float]]:

    # -- Paso 1: Traer Datos de Ahorros
    # Primero Obtenemos la Spreadsheet de Saldos desde Google Sheets
    google_sheets_service: GoogleSheetsService = st.session_state["google_sheets_service"]

    saldos_sheet = google_sheets_service.get_spreadsheet(SALDOS_SHEET_ID)

    # Traemos el Diccionario de Cambios de Referencias
    refChangesDict = st.session_state["changes_references_dict"]

    # Ahora Iteramos sobre cada Worksheet y obtenemos los datos como DataFrames
    saldosDFList = []

    for ws in saldos_sheet.worksheets():
        # Si el Nombre de la Hoja tiene "SALDO" se procesa, sino se ignora
        if ("SALDO" in ws.title.upper()) and not ("DING" in ws.title.upper()): # Quitamos DING por Lógica de Negocio
            df = processDF(ws, refChangesDict)
            saldosDFList.append(df)

    # Concatenamos todos los DataFrames en uno solo
    if saldosDFList:
        saldosDF = pd.concat(saldosDFList, ignore_index=True)
    else:
        saldosDF = pd.DataFrame(columns=['Referencia', 'Ahorro_Total'])

    # Agrupamos una Agrupación por Referencia y dejamos el Ahorro Máximo
    saldosDF = saldosDF.groupby('Referencia', as_index=False)['Ahorro_Total'].max()

    # Paso 2: Traer Datos de la hoja "TOTAL" de la misma Spreadsheet
    xcobrarDF = google_sheets_service.get_sheet_as_dataframe(SALDOS_SHEET_ID, 'TOTAL')

    # Renombramos Columnas
    xcobrarDF.rename(columns={
        'REFERENCIA': 'Referencia',
        'TOTAL': 'Por_Cobrar'
    }, inplace=True)

    # Volvemos la Referencia a String
    xcobrarDF['Referencia'] = xcobrarDF['Referencia'].apply(lambda s: str(s).replace('.0','').strip())
    # Aplicamos el Cambio de Referencia
    xcobrarDF['Referencia'] = xcobrarDF['Referencia'].apply(lambda s: refChangesDict.get(s,s))

    # Volvemos el Por_Cobrar a Número
    xcobrarDF['Por_Cobrar'] = xcobrarDF['Por_Cobrar'].apply(cleanNumber)
    xcobrarDF['Por_Cobrar'] = pd.to_numeric(xcobrarDF['Por_Cobrar'], errors='coerce')

    # Dejamos solo las Columnas de Referencia y Por_Cobrar
    xcobrarDF = xcobrarDF[['Referencia', 'Por_Cobrar']]

    # Realizamos una Agrupación por Referencia y dejamos la suma de Por_Cobrar
    xcobrarDF = xcobrarDF.groupby('Referencia')['Por_Cobrar'].sum().reset_index()

    # Si el DF está vacío, lo validamos con el esquema vacío
    if xcobrarDF.empty:
        xcobrarDF = PorCobrarSchema.empty()
    else:
        # Validamos el DF con el esquema
        xcobrarDF = PorCobrarSchema.validate(xcobrarDF)

    # Concatenamos ambos DFs en uno solo
    finalDF = pd.merge(saldosDF, xcobrarDF, on='Referencia', how='outer')
    # Imputamos Por_Cobrar y Ahorro_Total con 0 en caso de NaN
    imputeNans(finalDF, 'Ahorro_Total', 0)
    imputeNans(finalDF, 'Por_Cobrar', 0)

    # Ahora Creamos Diccionarios de Búsqueda para Referencia -> Ahorro_Total y Referencia -> Por_Cobrar
    saldosDict = finalDF.set_index('Referencia')['Ahorro_Total'].to_dict()
    porCobrarDict = finalDF.set_index('Referencia')['Por_Cobrar'].to_dict()
    # Volvemos los Diccionarios a defaultdict con valor por defecto 0
    saldosDict = defaultdict(int, saldosDict)
    porCobrarDict = defaultdict(int, porCobrarDict)

    # Creamos un Diccionario General
    generalDict = {
        'Saldos': saldosDict,
        'PorCobrar': porCobrarDict
    }

    return generalDict # type: ignore

# --> Carga de PaB Ideal de Crédito
@st.cache_data(show_spinner="Cargando PaB Ideal de Crédito desde Google Sheets...", ttl=HOUR_WAIT)
def load_pab_ideal() -> dict:

    # Primero Obtenemos la Spreadsheet de PaB Ideal desde Google Sheets
    google_sheets_service: GoogleSheetsService = st.session_state["google_sheets_service"]
    # Definimos el Nombre de la Hoja según el mes operativo
    fecha_operativa = getMesOperativo()
    nombre_hoja = f'{mesesDict[fecha_operativa.month].title()}-{fecha_operativa.year%100}'

    pab_ideal_df = google_sheets_service.get_sheet_as_dataframe(PABIDEAL_SHEET_ID, nombre_hoja)

    # Renombramos Columna PB Ideal a PaB_Ideal_Credito
    pab_ideal_df = pab_ideal_df.rename(columns={'PB Ideal':'PaB_Ideal_Credito','Id deuda':'Id_Deuda'}) # type: ignore

    # Volvemos la Id_Deuda a String
    pab_ideal_df['Id_Deuda'] = pab_ideal_df['Id_Deuda'].apply(lambda s: str(s).replace('.0','').strip())

    # Volvemos el PaB_Ideal a Número
    pab_ideal_df['PaB_Ideal_Credito'] = pab_ideal_df['PaB_Ideal_Credito'].apply(cleanNumber)
    pab_ideal_df['PaB_Ideal_Credito'] = pd.to_numeric(pab_ideal_df['PaB_Ideal_Credito'], errors='coerce')

    # Dejamos solo las Columnas de Id_Deuda y PaB_Ideal_Credito
    pab_ideal_df = pab_ideal_df[['Id_Deuda', 'PaB_Ideal_Credito']]

    # Quitamos Datos con nans
    pab_ideal_df = pab_ideal_df.dropna(subset=['Id_Deuda', 'PaB_Ideal_Credito'])

    # Dejamos Datos donde el PaB_Ideal_Credito sea mayor a 0
    pab_ideal_df = pab_ideal_df[pab_ideal_df['PaB_Ideal_Credito'] > 0]

    # Eliminamos Duplicados por Id_Deuda, dejando el último registro (el más reciente)
    pab_ideal_df = pab_ideal_df.drop_duplicates(subset=['Id_Deuda'], keep='last')

    # Validamos el DF (Si no esta vacío)
    if not pab_ideal_df.empty:
        pab_ideal_df = PaBIdealSchema.validate(pab_ideal_df)
    else:
        pab_ideal_df = PaBIdealSchema.empty()

    # Creamos el Diccionario de Búsqueda para Id_Deuda -> PaB_Ideal_Credito
    pabIdealDict = pab_ideal_df.set_index('Id_Deuda')['PaB_Ideal_Credito'].to_dict()
    # Volvemos el Diccionario a defaultdict con valor por defecto 0
    pabIdealDict = defaultdict(int, pabIdealDict)

    # Devolvemos el Diccionario de PaB Ideal de Crédito
    return pabIdealDict

# --> Carga de Datos de Aliados
@st.cache_data(show_spinner="Cargando Datos de Aliados desde Google Sheets...", ttl=HOUR_WAIT)
def load_aliados_dataframe() -> DataFrame[AliadosSchema]:

    # Primero Obtenemos la Spreadsheet de Aliados desde Google Sheets
    google_sheets_service: GoogleSheetsService = st.session_state["google_sheets_service"]

    # Obtenemos el DF de la Hoja "AlianzasVigentes"
    aliados_df = google_sheets_service.get_sheet_as_dataframe(ALIADOS_SHEET_ID, 'AlianzasVigentes')

    # Dejamos solo las Columnas Necesarias según el esquema
    aliados_df = aliados_df[AliadosSchema.__fields__.keys()]

    # Convertimos las Columnas de 'SI|NO' a Booleano
    boolean_columns = ['Permite Contacto', 'Cruza Base', 'SYNC', 'Negociación en Bloque', 'Contraofertas de Pago Obligatorio', 'Brindan Máx. Descuento', 'Pago a Cuotas']

    for col in boolean_columns:
        aliados_df[col] = aliados_df[col].astype(str)  # Aseguramos que sean strings
        aliados_df[col] = aliados_df[col].str.contains('SI', case=False, na=False)

    # Validamos el DF con el esquema (Si no esta vacío)
    if not aliados_df.empty:
        aliados_df = AliadosSchema.validate(aliados_df)
    else:
        aliados_df = AliadosSchema.empty()

    # Devolvemos el DataFrame de Aliados
    return aliados_df

def process_masivas_metadata(mtdt: str):
    if pd.isna(mtdt) or (mtdt == '') or (mtdt == 'nan'):
        return MasivasMetadata()
    try:
        return MasivasMetadata(**json.loads(mtdt))
    except:
        return MasivasMetadata()

# --> Carga de Datos de Masivas
@st.cache_data(show_spinner="Cargando Datos de Masivas desde Google Sheets...", ttl=HOUR_WAIT)
def load_masivas() -> DataFrame[MasivasSchema]:
    # Primero Obtenemos la Spreadsheet de Masivas desde Google Sheets
    google_sheets_service: GoogleSheetsService = st.session_state["google_sheets_service"]

    # Obtenemos el DF de la Hoja "Bases mes actual 2024" (PORQUE ESE NOMBRE ;_( Carita Triste )
    masivasDF = google_sheets_service.get_sheet_as_dataframe(MASIVAS_SHEET_ID, 'Bases mes actual 2024')

    # Renombramos las Columnas
    masivasDF = masivasDF.rename(columns={
        'ID': 'Id_Deuda',
        'Propuesta Pago': 'PaB_Propuesta',
        'Monto Pago Estructurado': 'PaB_Estructurado',
        'Plazo Estructurado': 'Plazo_Estructurado',
        'Referencia': 'Referencia',
        'Casa': 'Casa_Cobro',
        'Metadata': 'Metadata',
    })

    # Quitamos los Datos donde Id_Deuda o Casa_Cobro sea NaN
    masivasDF = masivasDF.dropna(subset=['Id_Deuda', 'Casa_Cobro'])

    # Dejamos solo las Columnas Necesarias
    masivasDF = masivasDF[
        [
            'Id_Deuda', 'PaB_Propuesta', 'PaB_Estructurado', 'Plazo_Estructurado',
            'Referencia','Casa_Cobro','Metadata'
        ]
    ]

    # Volvemos la Id_Deuda Y Referencia a String
    masivasDF['Id_Deuda'] = masivasDF['Id_Deuda'].apply(lambda s: str(s).replace('.0','').strip())
    masivasDF['Referencia'] = masivasDF['Referencia'].apply(lambda s: str(s).replace('.0','').strip())

    # Aplicamos la inicialización de la Metadata
    masivasDF['Metadata'] = masivasDF['Metadata'].apply(process_masivas_metadata)

    # Extraemos el PaB_Portafolio a Número 
    masivasDF['PaB_Portafolio'] = masivasDF['Metadata'].apply(
        lambda mtdt: mtdt['PaB_Portafolio'] if 'PaB_Portafolio' in mtdt else np.nan
    )

    # Aplicamos a Casa_Cobro .upper y strip
    masivasDF['Casa_Cobro'] = masivasDF['Casa_Cobro'].apply(lambda s: str(s).upper().strip() if pd.notnull(s) else '')

    # Cargamos los Cambios de Referencia y los Aplicamos
    refChangesDict = st.session_state["changes_references_dict"]
    masivasDF['Referencia'] = masivasDF['Referencia'].apply(lambda s: refChangesDict.get(s,s))

    # Volvemos los PaB a Número
    masivasDF['PaB_Propuesta'] = masivasDF['PaB_Propuesta'].apply(cleanNumber)
    masivasDF['PaB_Propuesta'] = pd.to_numeric(masivasDF['PaB_Propuesta'], errors='coerce')
    masivasDF['PaB_Estructurado'] = masivasDF['PaB_Estructurado'].apply(cleanNumber)
    masivasDF['PaB_Estructurado'] = pd.to_numeric(masivasDF['PaB_Estructurado'], errors='coerce')
    masivasDF['PaB_Portafolio'] = masivasDF['PaB_Portafolio'].apply(cleanNumber)
    masivasDF['PaB_Portafolio'] = pd.to_numeric(masivasDF['PaB_Portafolio'], errors='coerce')
    # Volvemos el Plazo a Número 
    masivasDF['Plazo_Estructurado'] = masivasDF['Plazo_Estructurado'].apply(cleanNumber)
    masivasDF['Plazo_Estructurado'] = pd.to_numeric(masivasDF['Plazo_Estructurado'], errors='coerce')

    # Quitamos Datos donde PaB_Propuesta sea Nulo
    masivasDF = masivasDF[masivasDF['PaB_Propuesta'].notna()]

    # Nota: Mantenemos todos los Registros por Id_Deuda (pueden existir varios descuentos por Deuda)
    # El orden del DF nunca cambia, por lo que el último registro de cada Deuda es el más reciente

    # Validamos el DF (Si no esta vacío)
    if not masivasDF.empty:
        masivasDF = MasivasSchema.validate(masivasDF)
    else:
        masivasDF = MasivasSchema.empty()

    # Devolvemos el DataFrame
    return masivasDF

# --> Carga de Addendums de Aliados
@st.cache_data(show_spinner="Cargando Addendums de Aliados desde Google Sheets...", ttl=HOUR_WAIT)
def load_addendums() -> DataFrame[AddendumsSchema]:
    # Primero Obtenemos la Spreadsheet de Addendums desde Google Sheets
    google_sheets_service: GoogleSheetsService = st.session_state["google_sheets_service"]

    # Obtenemos el DF de la Hoja "ADD"
    addendumsDF = google_sheets_service.get_sheet_as_dataframe(MASIVAS_SHEET_ID, 'ADD')

    # Renombramos las Columnas
    addendumsDF = addendumsDF.rename(columns={
        'ID_Addendum': 'Id_Deuda',
        'Cédula': 'Cedula',
        'Banco': 'Banco',
        'Deuda Bravo': 'PaB_Origen',
        'Propuesta de pago': 'PaB_Propuesta',
        'Referencia': 'Referencia',
    })
    # Dejamos solo las Columnas Necesarias
    addendumsDF = addendumsDF[['Id_Deuda', 'Cedula', 'Banco', 'PaB_Origen', 'PaB_Propuesta','Referencia']]

    # Quitamos Datos donde el Id_Deuda sea NaN
    addendumsDF = addendumsDF.dropna(subset=['Id_Deuda'])

    # Volvemos la Id_Deuda, Referencia y Cedula a String
    addendumsDF['Id_Deuda'] = addendumsDF['Id_Deuda'].apply(lambda s: str(s).replace('.0','').strip())
    addendumsDF['Referencia'] = addendumsDF['Referencia'].apply(lambda s: str(s).replace('.0','').strip())
    addendumsDF['Cedula'] = addendumsDF['Cedula'].apply(lambda s: str(s).replace('.0','').strip() if pd.notnull(s) else '')

    # Cargamos los Cambios de Referencia y los Aplicamos
    refChangesDict = st.session_state["changes_references_dict"]
    addendumsDF['Referencia'] = addendumsDF['Referencia'].apply(lambda s: refChangesDict.get(s,s))

    # Volvemos los PaB a Número
    addendumsDF['PaB_Origen'] = addendumsDF['PaB_Origen'].apply(cleanNumber)
    addendumsDF['PaB_Origen'] = pd.to_numeric(addendumsDF['PaB_Origen'], errors='coerce')
    addendumsDF['PaB_Propuesta'] = addendumsDF['PaB_Propuesta'].apply(cleanNumber)
    addendumsDF['PaB_Propuesta'] = pd.to_numeric(addendumsDF['PaB_Propuesta'], errors='coerce')

    # Quitamos Datos donde algún PaB sea menor a 2
    addendumsDF = addendumsDF[(addendumsDF['PaB_Origen'] >= 2) & (addendumsDF['PaB_Propuesta'] >= 2)]

    # Creamos la Columna PaB_PL como PaB_Origen * (1 - DEFAULT_DISCOUNT_PL)
    addendumsDF['PaB_PL'] = addendumsDF['PaB_Origen'] * (1 - DEFAULT_DISCOUNT_PL)

    # Si el DF está vacío, lo validamos con el esquema vacío
    if addendumsDF.empty:
        addendumsDF = AddendumsSchema.empty()
    else:
        # Validamos el DF con el esquema
        addendumsDF = AddendumsSchema.validate(addendumsDF)

    # Devolvemos el Diccionario de Addendums
    return addendumsDF

# Función Auxiliar para Obtener las Deudas Liquidadas del MEC
@st.cache_data(show_spinner="Cargando Deudas Liquidadas desde Google Sheets...", ttl=HOUR_WAIT)
def load_liquidaciones() -> set[str]:
    # Primero Obtenemos la Spreadsheet de Liquidaciones desde Google Sheets
    google_sheets_service: GoogleSheetsService = st.session_state["google_sheets_service"]

    # Obtenemos el DF de la Hoja "BD del mes"
    liquidacionesDF = google_sheets_service.get_sheet_as_dataframe(LIQUIDACIONES_SHEET_ID, 'BD del mes')

    # Renombramos la Columna ID a Id_Deuda
    liquidacionesDF = liquidacionesDF.rename(columns={'Deuda Berex':'Id_Deuda'})

    # Quitamos Datos donde Id_Deuda sea NaN
    liquidacionesDF = liquidacionesDF.dropna(subset=['Id_Deuda'])

    # Dejamos solo la Columna Id_Deuda
    liquidacionesDF = liquidacionesDF[['Id_Deuda']].drop_duplicates()

    # Volvemos la Id_Deuda a String
    liquidacionesDF['Id_Deuda'] = liquidacionesDF['Id_Deuda'].apply(lambda s: str(s).replace('.0','').strip())

    # Si el DF está vacío, lo validamos con el esquema vacío
    if liquidacionesDF.empty:
        liquidacionesDF = LiquidationsSchema.empty()
    else:
        # Validad el DF con el esquema
        liquidacionesDF = LiquidationsSchema.validate(liquidacionesDF)

    # Creamos un Set con las Deudas Liquidadas
    liquidaciones_set = set(liquidacionesDF['Id_Deuda'].tolist())

    # Devolvemos el Set de Deudas Liquidadas
    return liquidaciones_set


# Función Auxiliar para Cargar el HeadCount de Negociación
@st.cache_data(show_spinner="Cargando HeadCount de Negociación desde Google Sheets...", ttl=HOUR_WAIT)
def load_headcount_negociacion() -> DataFrame[HeadCountSchema]:
    # Primero Obtenemos la Spreadsheet de HeadCount desde Google Sheets
    google_sheets_service: GoogleSheetsService = st.session_state["google_sheets_service"]

    # Obtenemos el DF de la Hoja "HC"
    hc_negociacion_df = google_sheets_service.get_sheet_as_dataframe(HCNEGO_SHEET_ID, 'HC')

    # Renombramos las Columnas
    hc_negociacion_df = hc_negociacion_df.rename(columns={
        'email': 'Correo',
        'employee_id': 'ID_Empleado',
        'name': 'Nombre',
        'job_title': 'Nombre_Empleo',
        'status': 'Estado',
        'cedula': 'Cedula',
        'leader': 'Lider'
    })

    # Dejamos solo las Columnas Necesarias
    hc_negociacion_df = hc_negociacion_df[['Correo', 'ID_Empleado', 'Nombre', 'Nombre_Empleo', 'Estado', 'Cedula','Lider']]

    # Quitamos Datos con NaN
    hc_negociacion_df = hc_negociacion_df.dropna(subset=['Correo', 'ID_Empleado', 'Nombre', 'Nombre_Empleo', 'Estado'])

    # Volvemos la Columna ID_Empleado y Cedula a String
    hc_negociacion_df['ID_Empleado'] = hc_negociacion_df['ID_Empleado'].apply(lambda s: str(s).replace('.0','').strip())
    hc_negociacion_df['Cedula'] = hc_negociacion_df['Cedula'].apply(lambda s: str(s).replace('.0','').strip() if pd.notnull(s) else '')

    # Creamos Columna Es_Negociador como True si el Nombre Empleo contiene negociador o sena o back (ignorando mayúsculas/minúsculas), de lo contrario False
    hc_negociacion_df['Es_Negociador'] = hc_negociacion_df['Nombre_Empleo'].str.contains('negociador|sena|back', case=False, na=False, regex=True)

    # Quitamos Datos donde Cedula sea NaN o vacía
    hc_negociacion_df = hc_negociacion_df[hc_negociacion_df['Cedula'].notna() & (hc_negociacion_df['Cedula'] != '')]

    # Si el DF está vacío, lo validamos con el esquema vacío
    if hc_negociacion_df.empty:
        hc_negociacion_df = HeadCountSchema.empty()
    else:
        # Validamos el DF con el esquema
        hc_negociacion_df = HeadCountSchema.validate(hc_negociacion_df)

    # Devolvemos el DataFrame de HeadCount de Negociación
    return hc_negociacion_df

# Función Auxiliar para Cargar la Configuración de la Aplicación
@st.cache_data(show_spinner="Cargando Configuración de la Aplicación desde Google Sheets...", ttl=HOUR_WAIT)
def load_app_config() -> dict:
    # Primero Obtenemos la Spreadsheet de Configuración desde Google Sheets
    google_sheets_service: GoogleSheetsService = st.session_state["google_sheets_service"]

    # Obtenemos el DF de la Hoja "Configs"
    configs_df = google_sheets_service.get_sheet_as_dataframe(CONFIGS_SHEET_ID, 'Configs')

    # Dejamos solo las Columnas Necesarias
    configs_df = configs_df[['Config_Name', 'Value']]

    # Validamos el DF con el esquema (Si no esta vacío)
    if configs_df.empty:
        configs_df = ConfigsSchema.empty()
    else:
        configs_df = ConfigsSchema.validate(configs_df)

    # Creamos un Diccionario de Configuración
    config_dict = configs_df.set_index('Config_Name')['Value'].to_dict()

    # Devolvemos el Diccionario de Configuración
    return config_dict

# Función Auxiliar para Cargar los Permisos de Usuarios Especiales
@st.cache_data(show_spinner="Cargando Permisos de Usuarios Especiales desde Google Sheets...", ttl=DAY_WAIT)
def load_special_user_permissions() -> dict:
    # Primero Obtenemos la Spreadsheet de Configuración desde Google Sheets
    google_sheets_service: GoogleSheetsService = st.session_state["google_sheets_service"]

    # Ahora Abrimos la Hoja "Usuarios" de las Configuraciones de la Aplicación
    special_users_df = google_sheets_service.get_sheet_as_dataframe(CONFIGS_SHEET_ID, 'Usuarios')

    # A la Columna Permisos la Convertimos a Lista de Permisos
    special_users_df['Permisos'] = special_users_df['Permisos'].apply(lambda s: [p.strip() for p in str(s).split(',')] if pd.notnull(s) else [])

    # Ahora cambiamos la Búsqueda de Permisos según el Nombre y el Diccionario
    special_users_df['Permisos'] = special_users_df['Permisos'].apply(lambda perms: [PERMISSIONS_DICT[p] for p in perms if p in PERMISSIONS_DICT])

    # Validamos el DF con el esquema (Si no esta vacío)
    if special_users_df.empty:
        special_users_df = UserPermissionsSchema.empty()
    else:
        special_users_df = UserPermissionsSchema.validate(special_users_df)

    # Convertimos el DataFrame a un Diccionario
    return special_users_df.set_index('Correo')['Permisos'].to_dict()

# Función Auxiliar para Cargar la Cartera Activa (Para Modelo de Búsqueda)
@st.cache_data(show_spinner="Cargando Cartera Activa desde Google Sheets...", ttl=WEEK_WAIT)
def load_cartera_activa() -> DataFrame[CarteraActivaSchema]:
    # Primero Obtenemos el Servicio de Google Sheets desde el Session State
    google_sheets_service: GoogleSheetsService = st.session_state["google_sheets_service"]

    # Obtenemos el DF de la Hoja "Cartera"
    cartera_activa_df = google_sheets_service.get_sheet_as_dataframe(CARTERA_ACTIVA_SHEET_ID, 'Cartera')

    # Renombramos las Columnas
    cartera_activa_df = cartera_activa_df.rename(columns={
        'Id deuda': 'Id_Deuda',
        'Referencia': 'Referencia',
        'cedula': 'Cedula',
        'deuda bravo': 'Monto_Actual',
        'numero_credito': 'Numero_Credito',
        'Banco Normalizado': 'Banco',
        'Nombre Cliente': 'Nombre_Cliente',
    })

    # Volvemos las Columnas Referencia, Cedula y Id_Deuda a String
    cartera_activa_df['Referencia'] = cartera_activa_df['Referencia'].apply(lambda s: str(s).replace('.0','').strip())
    cartera_activa_df['Cedula'] = cartera_activa_df['Cedula'].apply(lambda s: str(s).replace('.0','').strip() if pd.notnull(s) else '')
    cartera_activa_df['Id_Deuda'] = cartera_activa_df['Id_Deuda'].apply(lambda s: str(s).replace('.0','').strip())

    # Cargamos los Cambios de Referencia y los Aplicamos
    refChangesDict = st.session_state["changes_references_dict"]
    cartera_activa_df['Referencia'] = cartera_activa_df['Referencia'].apply(lambda s: refChangesDict.get(s,s))

    # Volvemos las Columnas Numero_Credito y Nombre_Cliente a String usando astype(str)
    cartera_activa_df['Numero_Credito'] = cartera_activa_df['Numero_Credito'].astype(str)
    cartera_activa_df['Nombre_Cliente'] = cartera_activa_df['Nombre_Cliente'].astype(str)

    # Volvemos la Columna Monto_Actual a Número
    cartera_activa_df['Monto_Actual'] = pd.to_numeric(cartera_activa_df['Monto_Actual'], errors='coerce')

    # Dejamos solo las Columnas Necesarias
    cartera_activa_df = cartera_activa_df[['Id_Deuda', 'Referencia', 'Cedula', 'Monto_Actual', 'Numero_Credito', 'Banco','Nombre_Cliente']]

    # Eliminamos Duplicados por Id_Deuda, dejando el Primer registro
    cartera_activa_df = cartera_activa_df.drop_duplicates(subset=['Id_Deuda'], keep='first')

    # Validamos el DF con el esquema (Si no esta vacío)
    if cartera_activa_df.empty:
        cartera_activa_df = CarteraActivaSchema.empty()
    else:
        cartera_activa_df = CarteraActivaSchema.validate(cartera_activa_df)

    # Devolvemos el DataFrame de Cartera Activa
    return cartera_activa_df

# Función Auxiliar para Cargar los Logs
@st.cache_data(show_spinner="Cargando Logs de la Aplicación desde Google Sheets...", ttl=HOUR_WAIT)
def load_logs() -> DataFrame[LogsSchema]:
    # Primero obtenemos el Servicio de Google Sheets desde el Session State
    google_sheets_service: GoogleSheetsService = st.session_state["google_sheets_service"]

    # Obtenemos el DF de la Hoja "Logs"
    logs_df = google_sheets_service.get_sheet_as_dataframe(CONFIGS_SHEET_ID, 'Logs')

    # Renombramos las Columnas
    logs_df = logs_df.rename(columns={
        'Timestamp': 'Timestamp',
        'Usuario': 'Usuario',
        'Motivo': 'Motivo',
        'Detalle': 'Detalle'
    })

    # Volvemos Timestamp a Datetime
    logs_df['Timestamp'] = pd.to_datetime(logs_df['Timestamp'], errors='coerce', dayfirst=False)

    # Validamos el DF con el esquema (Si no esta vacío)
    if logs_df.empty:
        logs_df = LogsSchema.empty()
    else:
        logs_df = LogsSchema.validate(logs_df)

    # Devolvemos el DataFrame de Logs
    return logs_df

# Función Auxiliar para Cargar la Cartera Activa Backup
@st.cache_data(show_spinner="Cargando Cartera Activa de Respaldo (berex malo :( )", ttl=WEEK_WAIT)
def load_cartera_backup() -> DataFrame[DeudasActivasSchema]:
    # Primero obtenemos el Servicio de Google Sheets desde el Session State
    google_sheets_service: GoogleSheetsService = st.session_state["google_sheets_service"]

    # Obtenemos el DF de la Hoja Backup_DB de la Hoja de Configuraciones
    backup_df = google_sheets_service.get_sheet_as_dataframe(CONFIGS_SHEET_ID, 'Backup_DB')

    # Aplicamos la Limpieza a la Base
    # Volvemos la Columna Id_Deuda a String y Eliminamos los Valores Nulos
    backup_df.dropna(subset=['Id_Deuda'], inplace=True)
    backup_df['Id_Deuda'] = backup_df['Id_Deuda'].apply(lambda x: str(x).replace(".0", "").strip())
    # Volvemos la Columna Referencia y Cedula a String
    backup_df['Referencia'] = backup_df['Referencia'].apply(lambda x: str(x).replace(".0", "").strip())
    backup_df['Cedula'] = backup_df['Cedula'].apply(lambda x: str(x).replace(".0", "").strip())
    # Volvemos las Columnas PaB_Origen y PaB_PL a Números
    backup_df['PaB_Origen'] = pd.to_numeric(backup_df['PaB_Origen'], errors='coerce')
    backup_df['PaB_PL'] = pd.to_numeric(backup_df['PaB_PL'], errors='coerce')
    # Imputamos los Valores Nulos de PaB_Origen con 0
    imputeNans(backup_df, col='PaB_Origen', value=0)
    # Imputamos los Valores Nulos de PaB_PL como: PaB_Origen * (1 - DEFAULT_DISCOUNT_PL)
    maskPLNaN = backup_df['PaB_PL'].isna()
    backup_df.loc[maskPLNaN, 'PaB_PL'] = backup_df.loc[maskPLNaN, 'PaB_Origen'] * (1 - DEFAULT_DISCOUNT_PL)
    # Por Último, aplicamos la Limpieza a la Columna Pricing usando parsePercentage
    backup_df['Pricing'] = backup_df['Pricing'].apply(parsePercentage)
    # Volvemos Numero_Credito a String usando astype
    backup_df['Numero_Credito'] = backup_df['Numero_Credito'].astype(str)

    # Importante: Normalizamos los Bancos
    backup_df['Banco'] = backup_df['Banco'].apply(normalizar_banco)

    # Cargamos los Cambios de Referencia y los Aplicamos
    refChangesDict = load_reference_changes()
    backup_df['Referencia'] = backup_df['Referencia'].apply(lambda s: refChangesDict.get(s,s))

    # Validamos el Esquema
    if backup_df.empty:
        return DeudasActivasSchema.empty()
    else:
        backup_df = DeudasActivasSchema.validate(backup_df)

    return backup_df

# Función Auxiliar para la Carga de las Deudas a Identificar
@st.cache_data(show_spinner="Cargando Datos de Deudas a Identificar", ttl=HOUR_WAIT)
def load_pendiente_cruce() -> DataFrame[PendienteCruceSchema]:
    # Paso 1: Obtenemos el Servicio de Google Sheets
    google_sheets_service: GoogleSheetsService = st.session_state["google_sheets_service"]

    # Paso 2: Obtenemos el DF de la Hoja 'Pendientes_IdAutDeud'
    cruce_df = google_sheets_service.get_sheet_as_dataframe(CONFIGS_SHEET_ID, 'Pendientes_IdAutDeud')

    # Si el DF está vacío, devolvemos el Esquema Vacío
    if cruce_df.empty:
        st.session_state['local_cruce_changes'] = []
        return PendienteCruceSchema.empty()

    # Paso 3: Limpieza de Columnas
    # Dejamos solo las Columnas del Esquema
    cols_esquema = [c for c in PendienteCruceSchema.__fields__.keys() if c in cruce_df.columns]
    cruce_df = cruce_df[cols_esquema]
    # Quitamos las Filas Vacías (sin Id_Cruce)
    cruce_df = cruce_df.dropna(subset=['Id_Cruce'])
    # Volvemos las Columnas Id_Cruce y Cedula a String
    cruce_df['Id_Cruce'] = cruce_df['Id_Cruce'].apply(lambda s: str(s).replace('.0','').strip() if pd.notna(s) else '')
    if 'Cedula' in cruce_df.columns:
        cruce_df['Cedula'] = cruce_df['Cedula'].apply(lambda s: str(s).replace('.0','').strip() if pd.notna(s) else '')
    # Volvemos Nombre_Cliente y Banco a String (vacíos a NaN)
    for col in ['Nombre_Cliente', 'Banco']:
        if col in cruce_df.columns:
            cruce_df[col] = cruce_df[col].astype(str).replace(['', 'nan', 'None', '<NA>'], np.nan)
    # Volvemos Monto_Actual a Número
    if 'Monto_Actual' in cruce_df.columns:
        cruce_df['Monto_Actual'] = cruce_df['Monto_Actual'].apply(cleanNumber)
        cruce_df['Monto_Actual'] = pd.to_numeric(cruce_df['Monto_Actual'], errors='coerce')
    # Volvemos Numero_Credito a String (vacíos a NaN)
    if 'Numero_Credito' in cruce_df.columns:
        cruce_df['Numero_Credito'] = cruce_df['Numero_Credito'].apply(lambda s: str(s).replace('.0','').strip() if pd.notna(s) else '')
        cruce_df['Numero_Credito'] = cruce_df['Numero_Credito'].replace('', np.nan)

    # Paso 4: Conversión de la Metadata a los Tipados Necesarios
    if 'Metadata' in cruce_df.columns:
        cruce_df['Metadata'] = cruce_df['Metadata'].apply(_parse_metadata_cruce)

    # Paso 5: Dejamos la Última Versión de cada Id_Cruce (las actualizaciones se anexan al final)
    cruce_df = cruce_df.drop_duplicates(subset=['Id_Cruce'], keep='last').reset_index(drop=True)

    # Paso 6: Validamos el DF con el Esquema (Si no esta vacio)
    if not cruce_df.empty:
        cruce_df = PendienteCruceSchema.validate(cruce_df, lazy=True)
    else:
        cruce_df = PendienteCruceSchema.empty()

    # Por último, reiniciamos los cambios locales
    st.session_state['local_cruce_changes'] = []

    # Devolvemos el DataFrame
    return cruce_df

# Función Auxiliar para Parsear la Metadata de un Registro de Cruce desde Sheets
def _parse_metadata_cruce(mtdt_val) -> MetadataPendienteCruce:
    # Si ya es un Diccionario (Cambios Locales) lo devolvemos tal cual
    if isinstance(mtdt_val, dict):
        return MetadataPendienteCruce(**mtdt_val)
    # Si es Vacío o no es texto devolvemos un Diccionario Vacío
    if pd.isna(mtdt_val) or not isinstance(mtdt_val, str) or not mtdt_val.strip():
        return {} # type: ignore
    try:
        mtdt = json.loads(mtdt_val)
    except json.JSONDecodeError:
        return {} # type: ignore
    if not isinstance(mtdt, dict):
        return {} # type: ignore

    # Sub-Listas que quedaron serializadas como texto dentro del JSON
    for key in ['Pagos_Cuotas', 'Deudas_Posibles']:
        valor = mtdt.get(key)
        if isinstance(valor, str):
            try:
                mtdt[key] = json.loads(valor) if valor else []
            except json.JSONDecodeError:
                mtdt[key] = []
        elif valor is None:
            mtdt[key] = []

    # Tipados de las Claves Obligatorias
    try:
        mtdt['Id_Registro'] = str(int(float(mtdt.get('Id_Registro', 0))))
    except (TypeError, ValueError):
        mtdt['Id_Registro'] = str(mtdt.get('Id_Registro') or 0)
    for key in ['Fecha_Identificacion', 'Fecha_Limite_Pago']:
        mtdt[key] = pd.to_datetime(mtdt.get(key,''), errors='coerce')
    ultima_upd = mtdt.get('Ultima_Actualizacion')
    mtdt['Ultima_Actualizacion'] = pd.to_datetime(ultima_upd, errors='coerce') if (ultima_upd not in (None, '')) else None

    # Tipado de los Pagos a Cuotas
    for pago in (mtdt.get('Pagos_Cuotas') or []):
        if not isinstance(pago, dict):
            continue
        try:
            pago['Cuotas'] = int(float(pago.get('Cuotas', 1)))
        except (TypeError, ValueError):
            pago['Cuotas'] = 1
        try:
            pago['Monto'] = float(pago.get('Monto', 0) or 0)
        except (TypeError, ValueError):
            pago['Monto'] = 0.0

    # Tipado de las Deudas Posibles
    for deuda in (mtdt.get('Deudas_Posibles') or []):
        if not isinstance(deuda, dict):
            continue
        deuda['Banco'] = str(deuda.get('Banco') or '')
        try:
            deuda['Monto_Actual'] = float(deuda.get('Monto_Actual','nan')) if (deuda.get('Monto_Actual') not in (None, '')) else float('nan')
        except (TypeError, ValueError):
            deuda['Monto_Actual'] = float('nan')
        deuda['Numero_Credito'] = str(deuda.get('Numero_Credito') or '')
        deuda['Id_Deuda'] = str(deuda.get('Id_Deuda') or '')
        deuda['Es_Liquidada'] = deuda.get('Es_Liquidada',False)

    # Quitamos las Claves NotRequired que estén Vacías
    for key in ['Alias_Casa', 'Id_Definitivo', 'Portafolio_Ids']:
        if (key in mtdt) and (mtdt[key] in ('', None)):
            mtdt.pop(key)
    if ('Monto_Actual_Original' in mtdt) and (mtdt['Monto_Actual_Original'] in ('', None)):
        mtdt.pop('Monto_Actual_Original')

    # Aseguramos las Claves Obligatorias Faltantes
    mtdt.setdefault('Archivo_Origen', '')
    mtdt.setdefault('Pagos_Cuotas', [])
    mtdt.setdefault('Deudas_Posibles', [])
    mtdt.setdefault('Fecha_Identificacion', pd.NaT)
    mtdt.setdefault('Fecha_Limite_Pago', pd.NaT)
    mtdt.setdefault('Maximo_Descuento', False)
    mtdt.setdefault('Etiqueta', 'NULO')
    mtdt.setdefault('Motivos_Cruce', [])
    mtdt.setdefault('Cruce_Status', 'Sin Reconocer')
    mtdt.setdefault('Casa_Cobro', '')
    mtdt.setdefault('Ejecutivo_Subida', '')
    mtdt.setdefault('Ultima_Actualizacion', None)

    # Filtramos las Claves no Declaradas en los TypedDicts (la Validación las Rechaza)
    top_keys = set(MetadataPendienteCruce.__annotations__)
    mtdt = {k: v for k, v in mtdt.items() if k in top_keys}
    pago_keys = set(PagosCuotasCruce.__annotations__)
    mtdt['Pagos_Cuotas'] = [
        {k: v for k, v in pago.items() if k in pago_keys}
        for pago in mtdt['Pagos_Cuotas'] if isinstance(pago, dict)
    ]
    deuda_keys = set(DeudasPosiblesCruce.__annotations__)
    mtdt['Deudas_Posibles'] = [
        DeudasPosiblesCruce(**{k: v for k, v in deuda.items() if k in deuda_keys})
        for deuda in mtdt['Deudas_Posibles'] if isinstance(deuda, dict)
    ]

    # Lo Convertimos en el TypedDict
    mtdt = MetadataPendienteCruce(**mtdt)

    return mtdt

# --> Carga de Deudas a Identificar (Aplicando los Cambios Locales)
def load_pendiente_cruce_con_cambios() -> pd.DataFrame:
    # 1: Cargamos los Datos desde Google Sheets
    cruce_df = load_pendiente_cruce()

    cruce_ajustado = cruce_df.copy()

    # 2: Aplicamos los Cambios Locales
    if ('local_cruce_changes' in st.session_state) and len(st.session_state['local_cruce_changes']) > 0:

        # Paso 1: Creamos un DF con todas las Series
        local_changes_df = pd.DataFrame(st.session_state['local_cruce_changes'])
        # Quitamos Duplicados dejando el último
        local_changes_df = local_changes_df.drop_duplicates(subset='Id_Cruce', keep='last')

        # Paso 2: Preparamos Operaciones por Índices dejando Id_Cruce
        local_changes_df = local_changes_df.set_index('Id_Cruce', drop=False)
        cruce_ajustado = cruce_ajustado.set_index('Id_Cruce', drop=False)

        # Paso 3: Diferenciar nuevos de Existentes
        indices_existentes = cruce_ajustado.index.intersection(local_changes_df.index)
        indices_nuevos = local_changes_df.index.difference(cruce_ajustado.index)

        # A) Actualizar los que ya existen
        if not indices_existentes.empty:
            cruce_ajustado.update(local_changes_df.loc[indices_existentes])

        # B) Añadir los Nuevos
        if not indices_nuevos.empty:
            cruce_ajustado = pd.concat([cruce_ajustado, local_changes_df.loc[indices_nuevos]], axis=0)

        # Restauramos el Indice
        cruce_ajustado = cruce_ajustado.reset_index(drop=True)

    # 3: Devolver el Nuevo DF
    return cruce_ajustado

# --- Queries a MetaBase ---

# Función Auxiliar para obtener la referencia dada una deuda
@st.cache_data(ttl=HOUR_WAIT, show_spinner="Buscando Referencia de esa Deuda", max_entries = 100,)
def obtener_referencia_por_deuda(*,deuda: str) -> str:
    # Paso 1: Obtener El Servicio de Metabase
    metabase_service: MetabaseService = st.session_state["metabase_service"]
    # Paso 2: Obtener los Datos de la Consulta SQL para Obtener la Referencia
    query = QUERY_DEBT_TO_REFERENCE.format(debt_id=deuda)
    # Paso 3: Obtener la Referencia desde Metabase
    referencia_df = metabase_service.execute_query(query)
    # Paso 4: Devolver la Referencia si Existe, de lo Contrario Devolver None
    if not referencia_df.empty:
        return str(referencia_df.iloc[0]['Referencia']).replace(".0", "").strip()
    return ""

@st.cache_data(ttl=HOUR_WAIT, show_spinner="Buscando Deudas Activas de esa Referencia", max_entries = 100,)
def obtener_deudas_activas_con_retry(*, referencia: str, todas: bool) -> DataFrame[DeudasActivasSchema]:
    """
    Función principal que intenta obtener las Deudas Activas desde Metabase.
    Si la consulta falla, se cargan las Deudas Activas desde la Cartera Backup.
    """
    try:
        # Intentamos obtener los datos desde Metabase
        return obtener_deudas_activas(referencia=referencia, usar_todas=todas)
    except LookupError:
        # Si la consulta a Metabase falla, cargamos la Cartera Backup
        st.warning('Berex no se encuentra disponible, cargando la Cartera Backup', icon="⚠️")

        # Paso 1: Cargamos la Cartera Backup (Contiene la info de todos los clientes)
        backup_df = load_cartera_backup()

        # Paso 2: Aplicamos el Cambio de Referencia
        refChanges = load_reference_changes()
        referencia = refChanges.get(referencia,referencia)

        # Paso 3: Filtramos la Cartera Backup por la Referencia dada
        deudas_backup_df = backup_df[backup_df['Referencia'] == referencia]

        # Paso 4: Devolvemos el DataFrame con las Deudas Activas desde la Cartera Backup
        return deudas_backup_df

# Función Auxiliar para Parsear los Planes de Liquidación
def parsear_plan_items(planes: pd.DataFrame) -> pd.DataFrame:
    """Convierte el JSON 'debts' de cada plan winner en filas con Pricing + PB_PL."""
    items = []
    for row in planes.itertuples():
        try:
            debts_json = json.loads(row.debts) if isinstance(row.debts, str) else row.debts
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(debts_json, list):
            continue
        for item in debts_json:
            try:
                items.append({
                    "Pricing": row.pricing,
                    "Banco": item.get("financial_entity"),
                    "PaB_Origen": float(item.get("updated_amount")),
                    "PaB_PL": float(item.get("payment_to_bank"))
                    + float(item.get("reduction_commission")),
                })
            except (TypeError, ValueError):
                continue
    return pd.DataFrame(items)

# Función Auxiliar para Obtener las Deudas Activas de una Referencia (Usando Progreso)
def obtener_deudas_activas(*,referencia: str, usar_todas: bool) -> DataFrame[DeudasActivasSchema]:
    # Paso 1: Obtener El Servicio de Metabase
    metabase_service: MetabaseService = st.session_state["metabase_service"]
    # Paso 2: Obtener los Datos de la Consulta SQL para Obtener las Deudas Activas
    query_deudas = QUERY_DEUDAS.format(reference=referencia)

    progreso_busqueda = st.progress(1/5,"Buscando Deudas para la Referencia")

    # 2.1 Ejecutamos la Query de las Deudas
    deudas_df = metabase_service.execute_query(query_deudas)
    # 2.2 Obtenemos el lead_id
    lead_id = deudas_df['Lead_Id'].iloc[0]
    if pd.notna(lead_id):
        progreso_busqueda.progress(2/5,"Buscando Datos del Plan de Liquidación")
        # Creamos la Query
        query_plan_liq = QUERY_PLANES.format(lead_id=str(lead_id).replace('.0','').strip())
        # Ejecutamos la Query
        pl_df = metabase_service.execute_query(query_plan_liq)
        # Limpiamos los Datos
        pl_df = parsear_plan_items(pl_df)
    else:
        pl_df = pd.DataFrame(columns=['Pricing','Banco','PaB_Origen','PaB_PL'])

    # Si esta Vacío
    if deudas_df.empty:
        # Si el DataFrame está vacío, devolvemos un DataFrame vacío con el esquema
        return DeudasActivasSchema.empty()

    progreso_busqueda.progress(3/5, "Limpiando Datos")
    # Paso 3: -- Limpieza de Datos --
    # Volvemos la Columna Id_Deuda a String y Eliminamos los Valores Nulos
    deudas_df.dropna(subset=['Id_Deuda'], inplace=True)
    deudas_df['Id_Deuda'] = deudas_df['Id_Deuda'].apply(lambda x: str(x).replace(".0", "").strip())
    # Volvemos la Columna Referencia y Cedula a String
    deudas_df['Referencia'] = deudas_df['Referencia'].apply(lambda x: str(x).replace(".0", "").strip())
    deudas_df['Cedula'] = deudas_df['Cedula'].apply(lambda x: str(x).replace(".0", "").strip())
    # Volvemos las Columnas PaB_Origen y PaB_PL a Números
    deudas_df['PaB_Origen'] = pd.to_numeric(deudas_df['PaB_Origen'], errors='coerce')

    # Paso 4: Unimos los Datos con los del Plan de Liquidación
    deudas_df = pd.merge(
        deudas_df,
        pl_df,
        on=['PaB_Origen','Banco'],
    )

    # Paso 5: Filtramos si es necesario las liquidaciones
    if not usar_todas:
        maskEstados = deudas_df['Estado_Deuda'].isin(ESTADOS_LIQUIDACION)
        maskSubEstados = deudas_df['Sub_Estado_Deuda'].isin(SUB_ESTADOS_LIQUIDACION)
        deudas_df = deudas_df[~(maskEstados|maskSubEstados)]

    # Quitamos las Columnas Lead_Id, Estado_Deuda y Sub_Estado_Deuda
    deudas_df = deudas_df.drop(columns=['Estado_Deuda','Sub_Estado_Deuda','Lead_Id'])

    deudas_df['PaB_PL'] = pd.to_numeric(deudas_df['PaB_PL'], errors='coerce')
    # Imputamos los Valores Nulos de PaB_Origen con 0
    imputeNans(deudas_df, col='PaB_Origen', value=0)
    # Imputamos los Valores Nulos de PaB_PL como: PaB_Origen * (1 - DEFAULT_DISCOUNT_PL)
    maskPLNaN = deudas_df['PaB_PL'].isna()
    deudas_df.loc[maskPLNaN, 'PaB_PL'] = deudas_df.loc[maskPLNaN, 'PaB_Origen'] * (1 - DEFAULT_DISCOUNT_PL)
    # Por Último, aplicamos la Limpieza a la Columna Pricing usando parsePercentage
    deudas_df['Pricing'] = deudas_df['Pricing'].apply(parsePercentage)
    # Volvemos Numero_Credito a String usando astype
    deudas_df['Numero_Credito'] = deudas_df['Numero_Credito'].astype(str)

    progreso_busqueda.progress(3/5, "Aplicando Normalización de Bancos")
    # Importante: Normalizamos los Bancos
    deudas_df['Banco'] = deudas_df['Banco'].apply(normalizar_banco)

    # Validamos el DF con el esquema
    deudas_df = DeudasActivasSchema.validate(deudas_df, lazy=True)

    progreso_busqueda.progress(5/5, "Búsqueda Completada")

    # Paso 5: Devolver el DataFrame de Deudas Activas
    return deudas_df

# Función Auxiliar para Obtener la Última Actualización entre todas las deudas dadas
@st.cache_data(ttl=HOUR_WAIT, show_spinner="Buscando Última Actualización de esas Deudas", max_entries = 500,)
def obtener_ultima_actualizacion_deudas(*,debt_ids: list[str], user_email: str) -> pd.Timestamp:
    # Paso 1: Obtener El Servicio de Metabase
    metabase_service: MetabaseService = st.session_state["metabase_service"]

    # Paso 2: Obtener los Datos de la Consulta SQL para Obtener la Última Actualización
    try:
        query = QUERY_LAST_UPDATE.format(debt_ids=','.join(debt_ids), email=user_email)

        # Paso 3: Obtener las Últimas Actualizaciones desde Metabase
        ultima_actualizacion_df = metabase_service.execute_query(query)

        if ultima_actualizacion_df.empty:
            return pd.Timestamp.now('America/Bogota').normalize() - pd.Timedelta(days=100) # Devolvemos una Fecha de 100 Días Atrás si No Hay Actualizaciones

        # Paso 4: -- Limpieza de Datos --
        # Volvemos la Columna Id_Deuda a String y Eliminamos los Valores Nulos
        ultima_actualizacion_df.dropna(subset=['Id_Deuda'], inplace=True)
        ultima_actualizacion_df['Id_Deuda'] = ultima_actualizacion_df['Id_Deuda'].apply(lambda x: str(x).replace(".0", "").strip())
        # Volvemos la Columna Ultima_Actualizacion a Timestamp (Quitando Zona Horaria)
        ultima_actualizacion_df['Ultima_Actualizacion'] = pd.to_datetime(ultima_actualizacion_df['Ultima_Actualizacion'], errors='coerce', utc=True ).dt.tz_convert('America/Bogota').dt.tz_localize(None)

        # Paso 5: Devolver la Última Actualización como el Máximo de la Columna Ultima_Actualizacion
        if not ultima_actualizacion_df.empty:
            return ultima_actualizacion_df['Ultima_Actualizacion'].max()
        return pd.Timestamp.now('America/Bogota').normalize() - pd.Timedelta(days=100) # Devolvemos una Fecha de 30 Días Atrás si No Hay Actualizaciones
    except:
        return pd.Timestamp.now('America/Bogota').normalize() - pd.Timedelta(days=100) # Devolvemos una Fecha de 100 Días Atrás si No Hay Actualizaciones

# Función Auxiliar para obtener todos los datos necesarios de las deudas de reparadoras activas
@st.cache_data(ttl=WEEK_WAIT, show_spinner="Buscando los Datos de las Reparadoras Activas")
def obtener_datos_completos_deudas() -> DataFrame[InputCruceSchema]:
    # Paso 1: Obtener El Servicio de Metabase
    metabase_service: MetabaseService = st.session_state["metabase_service"]
    # Paso 2: Ejecutar la Query QUERY_TOTAL_REPARADORAS
    completo_df = metabase_service.execute_query(QUERY_TOTAL_REPARADORAS)

    if completo_df.empty:
        return InputCruceSchema.empty()

    # Paso 3: Limpieza de Datos
    # Volvemos la Columna Id_Deuda a String y Eliminamos los Valores Nulos
    completo_df.dropna(subset=['Id_Deuda'], inplace=True)
    completo_df['Id_Deuda'] = completo_df['Id_Deuda'].apply(lambda x: str(x).replace(".0", "").strip())
    # Volvemos la Columna Referencia y Cedula a String
    completo_df['Cedula'] = completo_df['Cedula'].apply(lambda x: str(x).replace(".0", "").strip())
    # Volvemos la Columna Monto_Actual a Números
    completo_df['Monto_Actual'] = pd.to_numeric(completo_df['Monto_Actual'], errors='coerce')
    # Volvemos Numero_Credito, Nombre_Cliente y Banco a String usando astype
    completo_df['Numero_Credito'] = completo_df['Numero_Credito'].astype(str)
    completo_df['Nombre_Cliente'] = completo_df['Nombre_Cliente'].astype(str)
    completo_df['Banco'] = completo_df['Banco'].astype(str)

    # Estandarizamos el Banco
    completo_df['Banco'] = normalizar_bancos_vectorizado(completo_df['Banco'])

    # Siguiente: Calcular Columna Liquidada según los Estados y los Sub-Estados
    maskEstado = completo_df['Estado_Deuda'].isin(ESTADOS_LIQUIDACION)
    maskSubEstado = completo_df['Sub_Estado_Deuda'].isin(SUB_ESTADOS_LIQUIDACION)

    completo_df['Liquidada'] = maskEstado | maskSubEstado

    # Quitamos las Columnas de Estados
    completo_df = completo_df.drop(columns=['Estado_Deuda','Sub_Estado_Deuda'])

    # Validamos el Esquema
    completo_df = InputCruceSchema.validate(completo_df)
    # Devolvemos el DF
    return completo_df