# Archivo para Inicializar los Servicios de la Aplicación
# Usando estándar Pep8
# Librerías de Python
from collections import defaultdict
# Librerías de Terceros
from gspread_dataframe import get_as_dataframe
from pandera.typing import DataFrame
import gspread
import pandas as pd
import streamlit as st
# Librerías Locales
from core.permissions import PERMISSIONS_DICT
from data.data_models import AddendumsSchema, AhorroSchema, AliadosSchema, CarteraActivaSchema, ConfigsSchema, DeudasActivasSchema, HeadCountSchema, LiquidationsSchema, MasivasSchema, PaBIdealSchema, PorCobrarSchema, UserPermissionsSchema
from modules.constants import DEFAULT_DISCOUNT_PL, QUERY_DEBT_TO_REFERENCE, QUERY_ACTIVE_DEBTS, QUERY_LAST_UPDATE, HOUR_WAIT, DAY_WAIT, WEEK_WAIT
from modules.forms import crear_diccionario_aliados
from services.google_sheets import GoogleSheetsService
from services.metabase import MetabaseService
from utils.helpers_general import cleanNumber, imputeNans, getMesOperativo, mesesDict, parsePercentage
from utils.helpers_sheets import _retry

# ----- Funciones de Carga de Información ---
SALDOS_SHEET_ID = '1mvxPdnyp5ip_0Lqyf6qy09BAtX323PF2Yc5-qGoukeU'
REFCHANGES_SHEET_ID = '1jcPPhtF2YK3Kr7P_A0Mgh2OqhOfnVWB2to3UPoSH5tE'
PABIDEAL_SHEET_ID = '1Obm0O5hfIIzCMy5RvdX5b1JBf3pmzIrYdYa1vPOB83M'
ALIADOS_SHEET_ID = '1px7MX8zMKPe-PeCTvpNkX4kFMp1XL5IuBUrP1oGftiw'
MASIVAS_SHEET_ID = '1sOIk9BAa2VE-P-wnMPDJh8_hYLGgO5WaJL7m9LIM2is'
LIQUIDACIONES_SHEET_ID = '1H3sYEtkeu47POnu8xZMaMtID1Vj53YIcWblWeZ8d0rc'
HCNEGO_SHEET_ID = '1KO4ImvhNZB_jtgpvs9DU-6_0FskFmxC9Xo4Rz5Yt6dM'
CONFIGS_SHEET_ID = '1_8M4GQf-n4_0gCWFfPCpUSebdmuSrVbiyQBdNzry6io'
CARTERA_ACTIVA_SHEET_ID = '1NRM51v9ENd4IOShbstNa8nNohiFWDsmx18RxsD4LB-8'

# --> Carga de Cambios de Referencias
@st.cache_data(show_spinner="Cargando Cambios de Referencias desde Google Sheets...", ttl=HOUR_WAIT)
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

    # Validamos el DF con el esquema
    df = AhorroSchema.validate(df)

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
    xcobrarDF = xcobrarDF.groupby('Referencia')['Por_Cobrar'].sum().reset_index()

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
    saldosDict = defaultdict(lambda: 0, saldosDict)
    porCobrarDict = defaultdict(lambda: 0, porCobrarDict)

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

    # Validamos el DF
    pab_ideal_df = PaBIdealSchema.validate(pab_ideal_df)

    # Creamos el Diccionario de Búsqueda para Id_Deuda -> PaB_Ideal_Credito
    pabIdealDict = pab_ideal_df.set_index('Id_Deuda')['PaB_Ideal_Credito'].to_dict()
    # Volvemos el Diccionario a defaultdict con valor por defecto 0
    pabIdealDict = defaultdict(lambda: 0, pabIdealDict)

    # Devolvemos el Diccionario de PaB Ideal de Crédito
    return pabIdealDict

# --> Carga de Datos de Aliados
@st.cache_data(show_spinner="Cargando Datos de Aliados desde Google Sheets...", ttl=HOUR_WAIT)
def load_aliados() -> dict:

    # Primero Obtenemos la Spreadsheet de Aliados desde Google Sheets
    google_sheets_service: GoogleSheetsService = st.session_state["google_sheets_service"]

    # Obtenemos el DF de la Hoja "AlianzasVigentes"
    aliadosDF = google_sheets_service.get_sheet_as_dataframe(ALIADOS_SHEET_ID, 'AlianzasVigentes')

    # Validamos el DF con el esquema
    aliadosDF = AliadosSchema.validate(aliadosDF)

    # Creamos el Diccionario de Aliados usando la función auxiliar
    aliados_dict = crear_diccionario_aliados(aliadosDF)

    # Devolvemos el Diccionario de Aliados
    return aliados_dict

# --> Carga de Datos de Masivas
@st.cache_data(show_spinner="Cargando Datos de Masivas desde Google Sheets...", ttl=HOUR_WAIT)
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

    # Validamos el DF
    masivasDF = MasivasSchema.validate(masivasDF)

    # Creamos el Diccionario de Masivas
    masivas_dict = masivasDF.set_index('Id_Deuda').to_dict(orient='index')

    # Devolvemos el Diccionario de Masivas
    return masivas_dict

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

    # Validamos el DF con el esquema
    addendumsDF = AddendumsSchema.validate(addendumsDF)

    # Devolvemos el Diccionario de Addendums
    return addendumsDF

# Función Auxiliar para Obtener las Deudas Liquidadas del MEC
@st.cache_data(show_spinner="Cargando Deudas Liquidadas desde Google Sheets...", ttl=HOUR_WAIT)
def load_liquidaciones() -> set:
    # Primero Obtenemos la Spreadsheet de Liquidaciones desde Google Sheets
    google_sheets_service: GoogleSheetsService = st.session_state["google_sheets_service"]

    # Obtenemos el DF de la Hoja "BD del mes"
    liquidacionesDF = google_sheets_service.get_sheet_as_dataframe(LIQUIDACIONES_SHEET_ID, 'BD del mes')

    # Renombramos la Columna ID a Id_Deuda
    liquidacionesDF = liquidacionesDF.rename(columns={'Deuda Berex':'Id_Deuda'})

    # Dejamos solo la Columna Id_Deuda
    liquidacionesDF = liquidacionesDF[['Id_Deuda']]

    # Volvemos la Id_Deuda a String
    liquidacionesDF['Id_Deuda'] = liquidacionesDF['Id_Deuda'].apply(lambda s: str(s).replace('.0','').strip())

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

    # Obtenemos el DF de la Hoja "HC Negociación"
    hc_negociacion_df = google_sheets_service.get_sheet_as_dataframe(HCNEGO_SHEET_ID, 'HC Negociación')

    # Renombramos las Columnas
    hc_negociacion_df = hc_negociacion_df.rename(columns={
        'email': 'Correo',
        'employee_id': 'ID_Empleado',
        'name': 'Nombre',
        'job_title': 'Nombre_Empleo',
        'status': 'Estado',
        'cedula': 'Cedula',
    })

    # Dejamos solo las Columnas Necesarias
    hc_negociacion_df = hc_negociacion_df[['Correo', 'ID_Empleado', 'Nombre', 'Nombre_Empleo', 'Estado', 'Cedula']]

    # Volvemos la Columna ID_Empleado y Cedula a String
    hc_negociacion_df['ID_Empleado'] = hc_negociacion_df['ID_Empleado'].apply(lambda s: str(s).replace('.0','').strip())
    hc_negociacion_df['Cedula'] = hc_negociacion_df['Cedula'].apply(lambda s: str(s).replace('.0','').strip() if pd.notnull(s) else '')

    # Creamos Columna Es_Negociador como True si el Nombre Empleo contiene negociador (ignorando mayúsculas/minúsculas), de lo contrario False
    hc_negociacion_df['Es_Negociador'] = hc_negociacion_df['Nombre_Empleo'].str.contains('negociador', case=False, na=False, regex=False)

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

    # Validamos el DF con el esquema
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

    # Validamos el DF con el esquema
    special_users_df = UserPermissionsSchema.validate(special_users_df)

    # Convertimos el DataFrame a un Diccionario
    return special_users_df.set_index('Correo')['Permisos'].to_dict()

# Función Auxiliar para Cargar la Cartera Activa (Para Modelo de Búsqueda)
@st.cache_data(show_spinner="Cargando Cartera Activa desde Google Sheets...", ttl=WEEK_WAIT)
def load_cartera_activa() -> DataFrame[CarteraActivaSchema]:
    # Primero Obtenemos la Spreadsheet de Cartera Activa desde Google Sheets
    google_sheets_service: GoogleSheetsService = st.session_state["google_sheets_service"]

    # Obtenemos el DF de la Hoja "Cartera"
    cartera_activa_df = google_sheets_service.get_sheet_as_dataframe(CARTERA_ACTIVA_SHEET_ID, 'Cartera')

    # Renombramos las Columnas
    cartera_activa_df = cartera_activa_df.rename(columns={
        'id_deuda': 'Id_Deuda',
        'Referencia': 'Referencia',
        'cedula': 'Cedula',
        'deuda bravo': 'PaB_Origen',
        'numero_credito': 'Numero_Credito',
        'Banco Normalizado': 'Banco',
    })

    # Volvemos las Columnas Referencia, Cedula y Id_Deuda a String
    cartera_activa_df['Referencia'] = cartera_activa_df['Referencia'].apply(lambda s: str(s).replace('.0','').strip())
    cartera_activa_df['Cedula'] = cartera_activa_df['Cedula'].apply(lambda s: str(s).replace('.0','').strip() if pd.notnull(s) else '')
    cartera_activa_df['Id_Deuda'] = cartera_activa_df['Id_Deuda'].apply(lambda s: str(s).replace('.0','').strip())

    # Volvemos la Columna Numero_Credito a String usando astype(str)
    cartera_activa_df['Numero_Credito'] = cartera_activa_df['Numero_Credito'].astype(str)

    # Volvemos la Columna PaB_Origen a Número
    cartera_activa_df['PaB_Origen'] = pd.to_numeric(cartera_activa_df['PaB_Origen'], errors='coerce')

    # Dejamos solo las Columnas Necesarias
    cartera_activa_df = cartera_activa_df[['Id_Deuda', 'Referencia', 'Cedula', 'PaB_Origen', 'Numero_Credito', 'Banco']]

    # Validamos el DF con el esquema
    cartera_activa_df = CarteraActivaSchema.validate(cartera_activa_df)

    # Devolvemos el DataFrame de Cartera Activa
    return cartera_activa_df

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

# Función Auxiliar para Obtener las Deudas Activas de una Referencia
@st.cache_data(ttl=HOUR_WAIT, show_spinner="Buscando Deudas Activas de esa Referencia", max_entries = 100,)
def obtener_deudas_activas(*,referencia: str) -> DataFrame[DeudasActivasSchema]:
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

    # Validamos el DF con el esquema
    deudas_df = DeudasActivasSchema.validate(deudas_df)

    # Paso 5: Devolver el DataFrame de Deudas Activas
    return deudas_df

# Función Auxiliar para Obtener la Última Actualización entre todas las deudas dadas
@st.cache_data(ttl=HOUR_WAIT, show_spinner="Buscando Última Actualización de esas Deudas", max_entries = 100,)
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
