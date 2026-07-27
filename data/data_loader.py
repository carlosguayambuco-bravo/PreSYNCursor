# Archivo para Inicializar los Servicios de la Aplicación
# Usando estándar Pep8
# Librerías de Python
from collections import defaultdict
# Librerías de Terceros
from gspread_dataframe import get_as_dataframe
import gspread
import pandas as pd
import streamlit as st
# Librerías Locales
from modules.constants import DEFAULT_DISCOUNT_PL, QUERY_DEBT_TO_REFERENCE, QUERY_ACTIVE_DEBTS, QUERY_LAST_UPDATE
from modules.forms import crear_diccionario_aliados
from services.metabase import MetabaseService
from services.google_sheets import GoogleSheetsService
from utils.helpers_sheets import _retry
from utils.helpers_general import cleanNumber, imputeNans, getMesOperativo, mesesDict, parsePercentage

# ----- Funciones de Carga de Información ---
SALDOS_SHEET_ID = '1mvxPdnyp5ip_0Lqyf6qy09BAtX323PF2Yc5-qGoukeU'
REFCHANGES_SHEET_ID = '1jcPPhtF2YK3Kr7P_A0Mgh2OqhOfnVWB2to3UPoSH5tE'
PABIDEAL_SHEET_ID = '1Obm0O5hfIIzCMy5RvdX5b1JBf3pmzIrYdYa1vPOB83M'
ALIADOS_SHEET_ID = '1px7MX8zMKPe-PeCTvpNkX4kFMp1XL5IuBUrP1oGftiw'
MASIVAS_SHEET_ID = '1sOIk9BAa2VE-P-wnMPDJh8_hYLGgO5WaJL7m9LIM2is'

# --> Carga de Cambios de Referencias
@st.cache_data(show_spinner="Cargando Cambios de Referencias desde Google Sheets...", ttl=3600)
def load_reference_changes() -> dict[str,str]:

    # Primero Obtenemos la Spreadsheet de Cambios de Referencias desde Google Sheets
    google_sheets_service: GoogleSheetsService = st.session_state["google_sheets_service"]

    # Abrimos la Hoja llamada 'Cambios de Referencia'
    ref_changes_ws = google_sheets_service.get_worksheet(REFCHANGES_SHEET_ID, 'Cambios de Referencia')

    # Obtenemos los Valores como records
    ref_values = _retry(lambda: ref_changes_ws.get_all_records())

    ## La llave sera la referencia vieja y el valor la referencia nueva
    if len(ref_values)>0 and len(ref_values[0])>1:
        refChangesDict = {str(row[0]).replace('.0','').strip():str(row[1]).replace('.0','').strip() for row in ref_values} # type: ignore
    else:
        refChangesDict = {}

    # Devolvemos el Diccionario de Cambios de Referencias
    return refChangesDict

# Función Auxiliar de Procesamiento de Información de DF de Saldos
def processDF(ws: gspread.Worksheet, refChangesDict: dict) -> pd.DataFrame:
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

    # Devolvemos el DF
    return df

# --> Carga de Saldos de Clientes (saldosDF)
@st.cache_data(show_spinner="Cargando Saldos de Clientes desde Google Sheets...", ttl=3600)
def load_client_balances() -> dict[str, dict[str, float]]:

    # -- Paso 1: Traer Datos de Ahorros
    # Primero Obtenemos la Spreadsheet de Saldos desde Google Sheets
    google_sheets_service: GoogleSheetsService = st.session_state["google_sheets_service"]

    saldos_sheet = google_sheets_service.get_spreadsheet(SALDOS_SHEET_ID)

    # Traemos el Diccionario de Cambios de Referencias
    refChangesDict = load_reference_changes()

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
    xcobrarDF = xcobrarDF.groupby('Referencia', as_index=False)['Por_Cobrar'].sum()

    # Concatenamos ambos DFs en uno solo
    finalDF = pd.merge(saldosDF, xcobrarDF, on='Referencia', how='outer')
    # Imputamos Por_Cobrar y Ahorro_Total con 0 en caso de NaN
    imputeNans(finalDF, 'Ahorro_Total', 0)
    imputeNans(finalDF, 'Por_Cobrar', 0)

    # Ahora Creamos Diccionarios de Búsqueda para Referencia -> Ahorro_Total y Referencia -> Por_Cobrar
    saldosDict = finalDF.set_index('Referencia')['Ahorro_Total'].to_dict()
    porCobrarDict = finalDF.set_index('Referencia')['Por_Cobrar'].to_dict()
    # Volvemos los Diccionarios a defaultdict con valor por defecto 0
    saldosDict = defaultdict(lambda: 0, saldosDict)
    porCobrarDict = defaultdict(lambda: 0, porCobrarDict)

    # Creamos un Diccionario General
    generalDict = {
        'Saldos': saldosDict,
        'PorCobrar': porCobrarDict
    }

    return generalDict # type: ignore

# --> Carga de PaB Ideal de Crédito
@st.cache_data(show_spinner="Cargando PaB Ideal de Crédito desde Google Sheets...", ttl=3600)
def load_pab_ideal() -> dict:

    # Primero Obtenemos la Spreadsheet de PaB Ideal desde Google Sheets
    google_sheets_service: GoogleSheetsService = st.session_state["google_sheets_service"]
    # Definimos el Nombre de la Hoja según el mes operativo
    fecha_operativa = getMesOperativo()
    nombre_hoja = f'{mesesDict[fecha_operativa.month].title()}-{fecha_operativa.year%100}'

    pab_ideal_df = google_sheets_service.get_sheet_as_dataframe(PABIDEAL_SHEET_ID, nombre_hoja)

    # Renombramos Columna PB Ideal a PaB_Ideal_Credito
    pabIdealDF = pabIdealDF.rename(columns={'PB Ideal':'PaB_Ideal_Credito','Id deuda':'Id_Deuda'}) # type: ignore

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

    # Creamos el Diccionario de Búsqueda para Id_Deuda -> PaB_Ideal_Credito
    pabIdealDict = pab_ideal_df.set_index('Id_Deuda')['PaB_Ideal_Credito'].to_dict()
    # Volvemos el Diccionario a defaultdict con valor por defecto 0
    pabIdealDict = defaultdict(lambda: 0, pabIdealDict)

    # Devolvemos el Diccionario de PaB Ideal de Crédito
    return pabIdealDict

# --> Carga de Datos de Aliados
@st.cache_data(show_spinner="Cargando Datos de Aliados desde Google Sheets...", ttl=3600)
def load_aliados() -> dict:

    # Primero Obtenemos la Spreadsheet de Aliados desde Google Sheets
    google_sheets_service: GoogleSheetsService = st.session_state["google_sheets_service"]

    # Obtenemos el DF de la Hoja "AlianzasVigentes"
    aliadosDF = google_sheets_service.get_sheet_as_dataframe(ALIADOS_SHEET_ID, 'AlianzasVigentes')

    # Creamos el Diccionario de Aliados usando la función auxiliar
    aliados_dict = crear_diccionario_aliados(aliadosDF)

    # Devolvemos el Diccionario de Aliados
    return aliados_dict

# --> Carga de Datos de Masivas
@st.cache_data(show_spinner="Cargando Datos de Masivas desde Google Sheets...", ttl=3600)
def load_masivas() -> dict:
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
        'Portafolio': 'Es_Portafolio',
    })

    # Quitamos los Datos donde Id_Deuda sea NaN
    masivasDF = masivasDF.dropna(subset=['Id_Deuda'])

    # Dejamos solo las Columnas Necesarias
    masivasDF = masivasDF[['Id_Deuda', 'PaB_Propuesta', 'PaB_Estructurado', 'Plazo_Estructurado', 'Es_Portafolio']]
    # Volvemos la Id_Deuda a String
    masivasDF['Id_Deuda'] = masivasDF['Id_Deuda'].apply(lambda s: str(s).replace('.0','').strip())
    # Volvemos los PaB a Número
    masivasDF['PaB_Propuesta'] = masivasDF['PaB_Propuesta'].apply(cleanNumber)
    masivasDF['PaB_Propuesta'] = pd.to_numeric(masivasDF['PaB_Propuesta'], errors='coerce')
    masivasDF['PaB_Estructurado'] = masivasDF['PaB_Estructurado'].apply(cleanNumber)
    masivasDF['PaB_Estructurado'] = pd.to_numeric(masivasDF['PaB_Estructurado'], errors='coerce')
    # Volvemos el Plazo a Número 
    masivasDF['Plazo_Estructurado'] = masivasDF['Plazo_Estructurado'].apply(cleanNumber)
    masivasDF['Plazo_Estructurado'] = pd.to_numeric(masivasDF['Plazo_Estructurado'], errors='coerce')
    # Volvemos el Portafolio a Booleano
    masivasDF['Es_Portafolio'] = masivasDF['Es_Portafolio'].apply(lambda x: x == 'SI' if isinstance(x, str) else False)

    # Eliminamos Duplicados por Id_Deuda, dejando el último registro (el más reciente)
    masivasDF = masivasDF.drop_duplicates(subset=['Id_Deuda'], keep='last')

    # Creamos el Diccionario de Masivas
    masivas_dict = masivasDF.set_index('Id_Deuda').to_dict(orient='index')

    # Devolvemos el Diccionario de Masivas
    return masivas_dict

# --> Carga de Addendums de Aliados
@st.cache_data(show_spinner="Cargando Addendums de Aliados desde Google Sheets...", ttl=3600)
def load_addendums() -> pd.DataFrame:
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
    })
    # Dejamos solo las Columnas Necesarias
    addendumsDF = addendumsDF[['Id_Deuda', 'Cedula', 'Banco', 'PaB_Origen', 'PaB_Propuesta']]
    # Quitamos Datos donde el Id_Deuda sea NaN
    addendumsDF = addendumsDF.dropna(subset=['Id_Deuda'])
    # Volvemos la Id_Deuda y Cedula a String
    addendumsDF['Id_Deuda'] = addendumsDF['Id_Deuda'].apply(lambda s: str(s).replace('.0','').strip())
    addendumsDF['Cedula'] = addendumsDF['Cedula'].apply(lambda s: str(s).replace('.0','').strip() if pd.notnull(s) else '')
    # Volvemos los PaB a Número
    addendumsDF['PaB_Origen'] = addendumsDF['PaB_Origen'].apply(cleanNumber)
    addendumsDF['PaB_Origen'] = pd.to_numeric(addendumsDF['PaB_Origen'], errors='coerce')
    addendumsDF['PaB_Propuesta'] = addendumsDF['PaB_Propuesta'].apply(cleanNumber)
    addendumsDF['PaB_Propuesta'] = pd.to_numeric(addendumsDF['PaB_Propuesta'], errors='coerce')

    # Quitamos Datos donde algún PaB sea menor a 2
    addendumsDF = addendumsDF[(addendumsDF['PaB_Origen'] >= 2) & (addendumsDF['PaB_Propuesta'] >= 2)]

    # Creamos la Columna PaB_PL como PaB_Origen * (1 - DEFAULT_DISCOUNT_PL)
    addendumsDF['PaB_PL'] = addendumsDF['PaB_Origen'] * (1 - DEFAULT_DISCOUNT_PL)

    # Devolvemos el Diccionario de Addendums
    return addendumsDF


# Función Auxiliar para obtener la referencia dada una deuda
st.cache_data(ttl=3600, show_spinner="Buscando Referencia de esa Deuda", max_entries = 100,)
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

# Función Auxiliar para Obtener las Deudas Activas de una Referencia
@st.cache_data(ttl=3600, show_spinner="Buscando Deudas Activas de esa Referencia", max_entries = 100,)
def obtener_deudas_activas(*,referencia: str) -> pd.DataFrame:
    # Paso 1: Obtener El Servicio de Metabase
    metabase_service: MetabaseService = st.session_state["metabase_service"]
    # Paso 2: Obtener los Datos de la Consulta SQL para Obtener las Deudas Activas
    query = QUERY_ACTIVE_DEBTS.format(referencia=referencia)
    # Paso 3: Obtener las Deudas Activas desde Metabase
    deudas_df = metabase_service.execute_query(query)

    # Paso 4: -- Limpieza de Datos --
    # Volvemos la Columna Id_Deuda a String y Eliminamos los Valores Nulos
    deudas_df.dropna(subset=['Id_Deuda'], inplace=True)
    deudas_df['Id_Deuda'] = deudas_df['Id_Deuda'].apply(lambda x: str(x).replace(".0", "").strip())
    # Volvemos la Columna Referencia y Cedula a String
    deudas_df['Referencia'] = deudas_df['Referencia'].apply(lambda x: str(x).replace(".0", "").strip())
    deudas_df['Cedula'] = deudas_df['Cedula'].apply(lambda x: str(x).replace(".0", "").strip())
    # Volvemos las Columnas PaB_Origen y PaB_PL a Números
    deudas_df['PaB_Origen'] = pd.to_numeric(deudas_df['PaB_Origen'], errors='coerce')
    deudas_df['PaB_PL'] = pd.to_numeric(deudas_df['PaB_PL'], errors='coerce')
    # Imputamos los Valores Nulos de PaB_Origen con 0
    imputeNans(deudas_df, col='PaB_Origen', value=0)
    # Imputamos los Valores Nulos de PaB_PL como: PaB_Origen * (1 - DEFAULT_DISCOUNT_PL)
    maskPLNaN = deudas_df['PaB_PL'].isna()
    deudas_df.loc[maskPLNaN, 'PaB_PL'] = deudas_df.loc[maskPLNaN, 'PaB_Origen'] * (1 - DEFAULT_DISCOUNT_PL)
    # Por Último, aplicamos la Limpieza a la Columna Pricing usando parsePercentage
    deudas_df['Pricing'] = deudas_df['Pricing'].apply(parsePercentage)

    # Paso 5: Devolver el DataFrame de Deudas Activas
    return deudas_df

# Función Auxiliar para Obtener la Última Actualización entre todas las deudas dadas
@st.cache_data(ttl=3600, show_spinner="Buscando Última Actualización de esas Deudas", max_entries = 100,)
def obtener_ultima_actualizacion_deudas(*,debt_ids: list[str], user_email: str) -> pd.Timestamp:
    # Paso 1: Obtener El Servicio de Metabase
    metabase_service: MetabaseService = st.session_state["metabase_service"]
    # Paso 2: Obtener los Datos de la Consulta SQL para Obtener la Última Actualización
    query = QUERY_LAST_UPDATE.format(debt_ids=','.join(debt_ids), email=user_email)
    # Paso 3: Obtener las Últimas Actualizaciones desde Metabase
    ultima_actualizacion_df = metabase_service.execute_query(query)
    # Paso 4: -- Limpieza de Datos --
    # Volvemos la Columna Id_Deuda a String y Eliminamos los Valores Nulos
    ultima_actualizacion_df.dropna(subset=['Id_Deuda'], inplace=True)
    ultima_actualizacion_df['Id_Deuda'] = ultima_actualizacion_df['Id_Deuda'].apply(lambda x: str(x).replace(".0", "").strip())
    # Volvemos la Columna Ultima_Actualizacion a Timestamp (Quitando Zona Horaria)
    ultima_actualizacion_df['Ultima_Actualizacion'] = pd.to_datetime(ultima_actualizacion_df['Ultima_Actualizacion'], errors='coerce', utc=True ).dt.tz_convert('America/Bogota').dt.tz_localize(None)
    # Paso 5: Devolver la Última Actualización como el Máximo de la Columna Ultima_Actualizacion
    if not ultima_actualizacion_df.empty:
        return ultima_actualizacion_df['Ultima_Actualizacion'].max()
    return pd.Timestamp.now('America/Bogota').normalize() - pd.Timedelta(days=30) # Devolvemos una Fecha de 30 Días Atrás si No Hay Actualizaciones
