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
from modules.forms import crear_diccionario_aliados
from services.metabase import MetabaseService
from services.google_sheets import GoogleSheetsService
from utils.helpers_sheets import _retry
from utils.helpers_general import cleanNumber, imputeNans, getMesOperativo, mesesDict

IVA = 1.19

# Creamos el Servicio de Metabase y de GoogleSheets
def initialize_services():
    if "metabase_service" in st.session_state and "google_sheets_service" in st.session_state:
        return  # Los servicios ya están inicializados

    # Inicializamos el Servicio de Metabase
    metabase_username = st.secrets["metabase"]["username"]
    metabase_password = st.secrets["metabase"]["password"]
    metabase_mainDB_id = st.secrets["metabase"]["mainDB_id"]
    metabase_service = MetabaseService(metabase_username, metabase_password, metabase_mainDB_id)

    # Inicializamos el Servicio de GoogleSheets
    google_sheets_credentials = st.secrets["google_sheets"]["credentials"]
    google_sheets_service = GoogleSheetsService(google_sheets_credentials)

    # Guardamos los servicios en el estado de la aplicación para que estén disponibles globalmente
    st.session_state["metabase_service"] = metabase_service
    st.session_state["google_sheets_service"] = google_sheets_service

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

    # Devolvemos el Diccionario de Addendums
    return addendumsDF