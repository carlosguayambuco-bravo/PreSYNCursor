# Estandar usando Pep8
# Librerías de Python
from typing import Optional, Any
from collections import defaultdict
import re
import io
# Librerías de Terceros
from thefuzz import fuzz
from pandera.typing import DataFrame
import numpy as np
import pandas as pd
import streamlit as st
# Librerías Locales
from data.data_loader import obtener_datos_deuda_cedula, parse_metadata_cruce
from data.data_models import InputFullScehma, InputCruceSchema, DeudasPosiblesCruce, PagosCuotasCruce, MetadataPendienteCruce, PendienteCruceSchema
from modules.constants import (
    COL_BANCO,
    COL_CEDULA,
    COL_CREDITO,
    COL_ID_CRUCE,
    COL_ID_DEUDA,
    COL_MONTO_ACTUAL,
    COL_MONTO_PROPUESTO,
    COL_NOMBRE,
    COLUMNAS_MAPEABLES,
    ETIQUETA_EXACTO,
    ETIQUETA_NULO,
    MIN_LEN_TEXTO
)
from services import GoogleDriveService
from utils.helpers_general import cleanNumber
from utils.helpers_sheets import convert_data_to_string

# Función Auxiliar para Buscar Cortes
def is_generalized_crop(original, target):
    """
    Returns True if 'target' can be formed by joining two non-overlapping
    substrings of 'original' in their original relative order.
    """
    # A crop cannot be longer than the original source
    if len(target) > len(original):
        return False

    # Check every possible split point in the target string
    for i in range(len(target) + 1):
        part1 = target[:i]
        part2 = target[i:]

        # 1. Find the earliest possible occurrence of part1
        idx1 = original.find(part1)

        # If part1 isn't in there at all, this split point won't work
        if idx1 == -1:
            continue

        # 2. Look for part2 only in the remaining part of the string
        # We start searching from (idx1 + length of part1)
        remaining_original = original[idx1 + len(part1):]

        if part2 in remaining_original:
            return True

    return False

# Función Auxiliar para obtener el valor más cercano dado una lista
def getClosestValue(value, values, minScore = 80, verbose=True):
    if pd.isna(value) or len(values) == 0: # Si es Nan lo devolvemos
        return value
    # Convertimos values a valores unicos
    values = list(set(values))
    currMax = 0
    currBest = values[0]
    for v in values:
        # Obtenemos la Score
        score = fuzz.ratio(value.lower(), v.lower())
        # Actualizamos la mejor coincidencia
        if score >= currMax:
            currMax = score
            currBest = v
    # Si cumple con el umbral se devuelve
    if currMax >= minScore:
        return True, currBest
    # Si no se devuelve el valor y se imprime una alerta
    if verbose:
        print('🚧No se encontraron valores para {}'.format(value))
    return False, value

# --- Funciones de Limpieza y Preparación ---

# Función Auxiliar para limpiar una Serie aplicando una función de limpieza por elemento
def _limpiar_serie(serie: pd.Series, funcion_limpieza) -> np.ndarray:
    serie_str = serie.astype(str).mask(serie.isna(), '')
    return serie_str.map(funcion_limpieza).to_numpy(dtype=object)

# Función Auxiliar para limpiar la Serie de Monto usando cleanNumber
def _limpiar_serie_monto(serie: pd.Series) -> np.ndarray:
    return serie.map(lambda v: cleanNumber(v, default_nan=np.nan)).to_numpy(dtype=float)

# Función Auxiliar para obtener la Serie de Número de Crédito sin modificarla
def _serie_credito(serie: pd.Series) -> np.ndarray:
    return serie.apply(cleanNumeroCredito).to_numpy(dtype=object)

# Función Auxiliar para construir los índices por texto de una columna
def _construir_indices_texto(valores: np.ndarray):
    char_index = defaultdict(set)    # carácter -> posiciones que lo contienen
    start2_index = defaultdict(set)  # par de letras iniciales -> posiciones que inician con él
    gram_index = defaultdict(set)    # 4-grama -> posiciones que lo contienen
    for i in range(len(valores)):
        v = valores[i]
        if len(v) >= MIN_LEN_TEXTO:
            for c in set(v):
                char_index[c].add(i)
            start2_index[v[:2]].add(i)
            for pos in range(len(v) - 3):
                gram_index[v[pos:pos + 4]].add(i)
    # Se convierten los conjuntos a arreglos de NumPy para acelerar las rutas bloqueadas
    char_index = {k: np.asarray(list(v), dtype=np.int64) for k, v in char_index.items()}
    start2_index = {k: np.asarray(list(v), dtype=np.int64) for k, v in start2_index.items()}
    gram_index = {k: np.asarray(list(v), dtype=np.int64) for k, v in gram_index.items()}
    return char_index, start2_index, gram_index

# Función Auxiliar para preparar la Cartera de Datos (universo) con sus índices
def preparar_universo(df_datos: pd.DataFrame) -> dict:
    n = len(df_datos)

    id_deuda_arr = df_datos[COL_ID_DEUDA].to_numpy(dtype=object)
    cedula_arr = _limpiar_serie(df_datos[COL_CEDULA], cleanCedula)
    nombre_arr = _limpiar_serie(df_datos[COL_NOMBRE], cleanNombreCliente)
    banco_arr = _limpiar_serie(df_datos[COL_BANCO], cleanText)
    monto_arr = _limpiar_serie_monto(df_datos[COL_MONTO_ACTUAL])
    credito_arr = _serie_credito(df_datos[COL_CREDITO])

    # Índice de Cédula
    cedula_index = defaultdict(list)
    for i in range(n):
        if cedula_arr[i]:
            cedula_index[cedula_arr[i]].append(i)

    # Índices de Nombre (exacto y por palabra)
    nombre_exact_index = defaultdict(list)
    nombre_word_index = defaultdict(set)
    for i in range(n):
        if nombre_arr[i]:
            nombre_exact_index[nombre_arr[i]].append(i)
            for palabra in nombre_arr[i].split():
                nombre_word_index[palabra].add(i)

    # Índices de Banco
    banco_exact_index = defaultdict(list)
    for i in range(n):
        if banco_arr[i]:
            banco_exact_index[banco_arr[i]].append(i)
    banco_char_index, banco_start2_index, banco_gram_index = _construir_indices_texto(banco_arr)

    # Índices de Número de Crédito
    credito_exact_index = defaultdict(list)
    for i in range(n):
        if credito_arr[i]:
            credito_exact_index[credito_arr[i]].append(i)
    credito_char_index, credito_start2_index, credito_gram_index = _construir_indices_texto(credito_arr)

    # Se convierten los índices exactos a arreglos de NumPy para acelerar las rutas bloqueadas
    cedula_index = {k: np.asarray(v, dtype=np.int64) for k, v in cedula_index.items()}
    nombre_exact_index = {k: np.asarray(v, dtype=np.int64) for k, v in nombre_exact_index.items()}
    banco_exact_index = {k: np.asarray(v, dtype=np.int64) for k, v in banco_exact_index.items()}
    credito_exact_index = {k: np.asarray(v, dtype=np.int64) for k, v in credito_exact_index.items()}

    # Arreglos Ordenados de Monto para búsqueda por rangos
    monto_sorted_idx = np.argsort(monto_arr, kind='stable')
    monto_sorted = monto_arr[monto_sorted_idx]

    return {
        'n': n,
        'id_deuda_arr': id_deuda_arr,
        'cedula_arr': cedula_arr,
        'nombre_arr': nombre_arr,
        'banco_arr': banco_arr,
        'monto_arr': monto_arr,
        'credito_arr': credito_arr,
        'cedula_index': cedula_index,
        'nombre_exact_index': nombre_exact_index,
        'nombre_word_index': nombre_word_index,
        'banco_exact_index': banco_exact_index,
        'banco_char_index': banco_char_index,
        'banco_start2_index': banco_start2_index,
        'banco_gram_index': banco_gram_index,
        'credito_exact_index': credito_exact_index,
        'credito_char_index': credito_char_index,
        'credito_start2_index': credito_start2_index,
        'credito_gram_index': credito_gram_index,
        'monto_sorted_idx': monto_sorted_idx,
        'monto_sorted': monto_sorted,
    }

# Función Auxiliar para preparar la Cartera a Buscar (solo las columnas existentes)
def limpiar_busqueda(df_buscar: pd.DataFrame):
    id_registro_arr = df_buscar[COL_ID_CRUCE].tolist()
    columnas = {}
    if COL_CEDULA in df_buscar.columns:
        columnas[COL_CEDULA] = _limpiar_serie(df_buscar[COL_CEDULA], cleanCedula)
    if COL_NOMBRE in df_buscar.columns:
        columnas[COL_NOMBRE] = _limpiar_serie(df_buscar[COL_NOMBRE], cleanNombreCliente)
    if COL_BANCO in df_buscar.columns:
        columnas[COL_BANCO] = _limpiar_serie(df_buscar[COL_BANCO], cleanText)
    if COL_MONTO_ACTUAL in df_buscar.columns:
        columnas[COL_MONTO_ACTUAL] = _limpiar_serie_monto(df_buscar[COL_MONTO_ACTUAL])
    if COL_CREDITO in df_buscar.columns:
        columnas[COL_CREDITO] = _serie_credito(df_buscar[COL_CREDITO])
    if COL_MONTO_PROPUESTO in df_buscar.columns:
        columnas[COL_MONTO_PROPUESTO] = _limpiar_serie_monto(df_buscar[COL_MONTO_PROPUESTO])
    return id_registro_arr, columnas

# Función Auxiliar para Limpiar la Cédula
def cleanCedula(cedula) -> str:
    if pd.isna(cedula):
        return ''
    cedula = str(cedula).strip()
    # Caso 1: Si tiene más de un punto, se quitan todos los puntos
    if cedula.count('.') > 1:
        cedula = cedula.replace('.', '')
    # Caso 2: Si tiene un solo punto, se elimina el punto y todo lo que venga después
    elif cedula.count('.') == 1:
        cedula = cedula.split('.')[0]
    return cedula.strip()

# Función Auxiliar para Limpiar el Nombre del Cliente
def cleanNombreCliente(nombre) -> str:
    if pd.isna(nombre):
        return ''
    txt = str(nombre)
    # Quitamos Tildes
    tildes = {
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U',
    }
    for original, limpio in tildes.items():
        txt = txt.replace(original, limpio)
    # Dejamos en Mayúsculas y Ordenamos las Palabras alfabéticamente
    txt = txt.upper().strip()
    return ' '.join(sorted(txt.split()))

# Función Auxiliar para Limpiar el Número de Crédito
def cleanNumeroCredito(nc: Any) -> str:
    # Si es Nulo se deja así
    if pd.isna(nc):
        return ''
    # Convertimos el Número de Credito a String
    if isinstance(nc, (int,float)):
        nc_cleaned = str(int(nc)) if nc%1 == 0 else str(nc)
    else:
        nc_cleaned = str(nc)
    
    # Quitamos Signos de Puntuación y X
    nc_cleaned = nc_cleaned.replace('X','')
    for p in '\'!"#$%&()*+,-./:;<=>?@[\\]^_`{|}~´-':
        nc_cleaned = nc_cleaned.replace(p,'')

    # Devolvemos el Resultado
    return nc_cleaned

def cleanText(txt):
    # Verificamos que no sea NaN
    if pd.isna(txt) or not (isinstance(txt,str)):
        return 'NAN'
    # Primero Quitamos tildes y dejamos Upper
    txt = txt.lower().replace("ó", "o").replace("á", "a").replace("í", "i").replace("é", "e").replace("ú", "u").upper().strip()
    # Ahora Reemplazamos #N/A con NO_HAY_INFORMACION
    txt = txt.replace('#N/A','NO_HAY_INFORMACION')
    # Ahora Iteramos por cada uno de los signos de puntuación y los quitamos
    for p in '\'!"#$%&()*+,-./:;<=>?@[\\]^_`{|}~´-':
        txt = txt.replace(p,'')
    # Ahora Reemplazamos (\d+) con '' para evitar numeros y parentesis
    txt = re.sub(r'\(\d+\)', '', txt)
    # Remplazamos Bco. por BANCO y AV VILLAS POR AVVILLAS
    txt = txt.replace('BCO.','BANCO').replace('AV VILLAS','AVVILLAS')
    # Reemplazams JEFFERSON_CAPITAL por JCAP
    txt = txt.replace('JEFFERSON_CAPITAL','JCAP')
    # Quitamos Números Romanos por cada uno de los Splits por espacio
    romanRegex = r'\b(?=[MDCLXVI])M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})\b'
    txt = ' '.join(re.sub(romanRegex, '', t) for t in txt.split())
    # Ahora realizamos split por espacio y ordenamos
    txt = ' '.join(sorted(txt.split()))
    # Quitamos Valores de Banco\s
    txt = ' '.join(t for t in txt.split() if not t == 'BANCO')
    # Quitamos Nombres Comunes de Casas de Cobro
    commonNames = r'\b(' \
            r'grupo|juridico|jurídico|sas|sa|s a|ltda|suma|financiera|'\
            r'contactosol|contacto|solucion|soluciones|citisumma|'\
            r'cobrando|cobranzas|adcore|logros|factoring|origen|origem|'\
            r'gestiones|gestion|profesionales|bpo|inversionistas|'\
            r'estrategicos|estratégicos|casa|de|cobro|servicios|'\
            r'creditos|credito|abogados|asociados|'\
            r'outsourcing|risk|patrimonio|autonomo|autónomo|central|'\
            r'inversiones|valora|punto|com|puntocom|activos|'\
            r'recuperacion|recuperación|financiera|financiero|'\
            r'asesores|asociados|gest|prof|eyc|gca|summa'\
            r')\b'
    # Volvemos los Nombres Comunes a Upper
    commnNames = commonNames.upper()
    # Quitamos los nombres comunes
    txt = re.sub(commnNames, '', txt)

    # Reemplazamos NUBANK POR NU
    txt = txt.replace('NUBANK','NU')

    # Regla de Negocio: Si tiene COLPATRIA se devuelve DAVI BANK
    if 'COLPATRIA' in txt:
        txt = 'DAVI BANK'
    if 'BBVA' in txt:
        txt = 'BBVA'

    # Se devuelve el valor
    return txt.strip()

# Función Auxiliar para Leer la Base Subida por el Usuario (xlsx o csv)
def leer_base_subida(uploaded_file: io.BytesIO) -> pd.DataFrame:
    buffer_bytes = uploaded_file.getvalue()
    ext = uploaded_file.name.split('.')[-1].lower()

    # Caso 1: Excel
    if ext == 'xlsx':
        return pd.read_excel(io.BytesIO(buffer_bytes), dtype=str)

    # Caso 2: CSV (intentamos la lectura y si falla pedimos el separador)
    try:
        return pd.read_csv(io.BytesIO(buffer_bytes), dtype=str)
    except Exception:
        pass
    try:
        return pd.read_csv(io.BytesIO(buffer_bytes), dtype=str, encoding='latin-1')
    except Exception:
        pass

    separador = st.text_input(
        label="**🚧 No se pudo leer el CSV automáticamente. Indica el separador**",
        value=";",
        key="cruce_separador_csv_input",
        help="Escribe el separador usado en el archivo (Ej: ';', '|', '\\t').",
    )
    if separador:
        try:
            sep = '\t' if separador == '\\t' else separador
            return pd.read_csv(io.BytesIO(buffer_bytes), sep=sep, dtype=str)
        except Exception as e:
            st.error("No se pudo leer el CSV con el separador '{}': {}".format(separador, e), icon="❌")
            return pd.DataFrame()
    st.error("No se pudo leer el archivo CSV. Indica el separador para continuar.", icon="🚧")
    return pd.DataFrame()

# Función Auxiliar para Adivinar la Columna que corresponde a un dato del esquema
def adivinar_columna(columnas: list, candidatos: list) -> str:
    columnas_lower = [str(c).strip().lower() for c in columnas]
    for candidato in candidatos:
        for i, col_lower in enumerate(columnas_lower):
            if candidato in col_lower:
                return columnas[i]
    return 'Sin Columna'

# Función Auxiliar para Limpiar las Keys de los Widgets de Columnas (al subir un archivo nuevo)
def resetear_widgets_columnas(base_key: str) -> None:
    for key in list(st.session_state.keys()):
        if key.endswith(base_key): # type: ignore
            del st.session_state[key]

def mostrar_seleccion_columnas(*,label: str, start_idx: int, end_idx: int, opciones_columnas: list[str], column_mapper: dict[str,str], columnas_df: list[str]):
    st.markdown(f"#### **{label}**")
    for (col_std, label, candidatos) in COLUMNAS_MAPEABLES[start_idx:end_idx]:
        adivinada = adivinar_columna(columnas_df, candidatos)
        index_default = opciones_columnas.index(adivinada) if adivinada in opciones_columnas else 0
        column_mapper[col_std] = st.selectbox(
            label="**{}**".format(label),
            options=opciones_columnas,
            index=index_default,
            key="cruce_col_{}".format(col_std),
        )

# Función Auxiliar para ajustar el portafolio
def adjust_portafolio_value(
        cruce_df: DataFrame[InputFullScehma],
        cartera_df: Optional[DataFrame[InputCruceSchema]],
        colsAdjust: list[str] = [COL_MONTO_PROPUESTO]
    ) -> tuple[DataFrame[InputFullScehma],str]:
    # Paso 1: Asegurarnos que Cedula o Nombre_Cliente esten en la base de cruce como primera condición
    if not (COL_CEDULA in cruce_df.columns) and not (COL_NOMBRE in cruce_df.columns):
        return InputFullScehma.empty(), "Faltan las Columnas Principales (Cedula o Nombre del Cliente)"
    # Paso 2: Verificación de que exista un Monto_Propuesto
    elif not (COL_MONTO_PROPUESTO in cruce_df.columns):
        return InputFullScehma.empty(), "Hace falta el Monto Propuesto a Dividir el Portafolio"
    # Paso 3: Verificación de Monto_Actual en base de cruce o que se haya entregado la cartera
    elif not (COL_MONTO_ACTUAL in cruce_df.columns) and cartera_df is None:
        return InputFullScehma.empty(), "Se Necesita el Monto Actual para realizar la división del Portafolio"

    # Siguiente: Definir que Columna de Cliente se utiliza
    if not COL_CEDULA in cruce_df.columns:
        columna_cliente = COL_NOMBRE
    else:
        columna_cliente = COL_CEDULA
    # Verificación 2: Dejamos la Columna con menos NaNs
    if (COL_CEDULA in cruce_df.columns) and (COL_NOMBRE in cruce_df.columns) and cruce_df[COL_CEDULA].isna().sum() < cruce_df[COL_NOMBRE].isna().sum():
        columna_cliente = COL_NOMBRE

    # Siguiente Verificación: Inserción de monto actual (si es necesario)
    if not (COL_MONTO_ACTUAL in cruce_df.columns) and cartera_df is not None:
        # Paso 1: Verificar que exista el Id Definitivo en el cruce para almenos un dato
        if not any((mtdt.get('Id_Definitivo',None) != None for mtdt in cruce_df['Metadata'].values)):
            return InputFullScehma.empty(), "Se Necesita que las Deudas esten cruzadas para la Subida del Portafolio"
        # Paso 2: Añadir el Monto_Actual y definir la Máscara de uso
        monto_actual_mapper = dict(zip(cartera_df['Id_Deuda'], cartera_df['Monto_Actual']))
        maskUse = cruce_df['Metadata'].apply(
            lambda mtdt: (mtdt.get('Id_Definitivo',None) != None) and (mtdt.get('Id_Definitivo',None) in monto_actual_mapper)
        )
        # Paso 3: Aplicar el Mappeado de Monto Actual
        cruce_df[COL_MONTO_ACTUAL] = np.nan
        cruce_df.loc[maskUse, COL_MONTO_ACTUAL] = cruce_df.loc[maskUse, 'Metadata'].apply(
            lambda mtdt: monto_actual_mapper[mtdt['Id_Definitivo']]
        )
    else:
        # De lo Contrario la máscara de uso es los datos sin NaN de la Columna del Cliente
        maskUse = cruce_df[columna_cliente].notna()

    # Ajuste: Dejamos solo los Datos con Monto_Actual (asegurando integridad por cliente)
    maskUse = maskUse & cruce_df[COL_MONTO_ACTUAL].notna()
    maskUse = maskUse.groupby(cruce_df[columna_cliente]).transform('all')

    if not maskUse.sum():
        return cruce_df, "No hubieron datos suficientes por cliente para aplicar la división"

    # Siguiente: Creamos la Serie que servirá como distribuidora dependiendo si hay Portafolio_Ids o no en la Metadata
    if any((mtdt.get('Portafolio_Ids',None) != None for mtdt in cruce_df['Metadata'].values)):
        serieDist = cruce_df.loc[maskUse].apply(
            lambda r: r['Metadata'].get('Portafolio_Ids') if 'Portafolio_Ids' in r['Metadata'] else str(r['Metadata']['Id_Registro'])
        )
    else:
        serieDist = cruce_df.loc[maskUse,columna_cliente] + '_' + cruce_df.loc[maskUse,COL_MONTO_ACTUAL].astype(str)

    # Verificación: Deben haber 2 elementos iguales por lo menos
    if maskUse.sum() == serieDist.nunique():
        return cruce_df, "No hubieron coincidencias de portafolios por monto"

    # Ahora Creamos los Fraccionadores
    fracSerie = cruce_df.loc[maskUse, COL_MONTO_ACTUAL] / cruce_df.loc[maskUse, COL_MONTO_ACTUAL].groupby(serieDist).transform('sum')
    # Por último aplicamos el Cambio a las columnas necesarias de ajuste
    for col in colsAdjust:
        # Verificamos que el dtype sea Número
        if not pd.api.types.is_numeric_dtype(cruce_df[col].dtype):
            continue
        cruce_df.loc[maskUse, col] = cruce_df.loc[maskUse, col] * fracSerie

    return cruce_df, "Todo Correcto {} cambios Aplicados".format(maskUse.sum())

def generateFileName(casa_cobro: str, alias: Optional[str]) -> str:
    return "{casa} {alias} - {dt}".format(
        casa = casa_cobro,
        alias = '' if not alias else "({})".format(alias),
        dt = pd.Timestamp.now('America/Bogota').strftime('%Y-%m-%d')
    )

# Función para subir la base a Drive
def uploadDBtoDrive(base_bytes: bytes, mimetype: str, file_name: str) -> str:
    # Paso 1: Obtener el Servicio de Google Sheets
    google_drive_service: GoogleDriveService = st.session_state['google_drive_service']
    # Paso 2: Obtener el ID de la Carpeta
    folder_id = st.secrets['google_drive']["folder_id_bases_cruce"]
    # Paso 3: Subir el archivo a Google Drive
    file_id = google_drive_service.upload_file(
        file_bytes=base_bytes,
        file_name=file_name,
        mime_type=mimetype,
        folder_id=folder_id
    )
    # Paso 4: Devolver el File ID
    return file_id

# --- Funciones de Metadata y Formateo del Cruce ---

# Función Auxiliar para Crear la Metadata de un Registro de Cruce
def create_metadata_cruce(*,
        id_registro: str,
        nombre_archivo: str,
        pagos_cuotas: list[PagosCuotasCruce],
        fecha_identificacion: pd.Timestamp,
        fecha_limite_pago: pd.Timestamp,
        descuento_maximo: bool,
        etiqueta: str,
        motivos_cruce: list[str],
        deudas_posibles: list[DeudasPosiblesCruce],
        cruce_status: str = 'Sin Reconocer',
        casa_cobro: str,
        ejecutivo_subida: str,
        alias_casa: Optional[str] = None,
        id_definitivo: Optional[str] = None,
        portafolio_ids: Optional[str] = None,
        monto_actual_original: Optional[float] = None,
        ultima_actualizacion: Optional[pd.Timestamp] = None,
        monto_propuesto: Optional[float] = None,
    ) -> MetadataPendienteCruce:
    # Paso 1: Crear la Metadata con las Claves Obligatorias
    mtdt = MetadataPendienteCruce(
        Id_Registro=str(id_registro),
        Archivo_Origen = nombre_archivo,
        Pagos_Cuotas=pagos_cuotas, # type: ignore
        Fecha_Identificacion=fecha_identificacion,
        Fecha_Limite_Pago=(fecha_limite_pago if pd.notna(fecha_limite_pago) else pd.NaT),
        Maximo_Descuento=descuento_maximo,
        Etiqueta=etiqueta, # type: ignore
        Motivos_Cruce=motivos_cruce,
        Deudas_Posibles=deudas_posibles, # type: ignore
        Cruce_Status=cruce_status, # type: ignore
        Casa_Cobro=casa_cobro,
        Ejecutivo_Subida=ejecutivo_subida,
        Ultima_Actualizacion=ultima_actualizacion,
    )
    # Paso 2: Agregar las Claves Opcionales (solo si tienen valor)
    if alias_casa:
        mtdt['Alias_Casa'] = alias_casa
    if id_definitivo:
        mtdt['Id_Definitivo'] = id_definitivo
    if portafolio_ids:
        mtdt['Portafolio_Ids'] = portafolio_ids
    if monto_actual_original is not None:
        mtdt['Monto_Actual_Original'] = monto_actual_original
    if pd.notna(monto_propuesto) and monto_propuesto>0:
        mtdt['Monto_Propuesto'] = monto_propuesto
    # Paso 3: Devolver la Metadata
    return mtdt

# Función Auxiliar para Limpiar la Base Estandarizada del Cruce (misma lógica de
# limpiar_busqueda, incluyendo el cleanNumber para las Columnas de Montos a Cuotas)
def limpiar_base_subida(cruce_df: pd.DataFrame, montos_cuotas_cols: Optional[list[str]] = None) -> pd.DataFrame:
    df = cruce_df.copy()
    # Limpieza de Textos del Cliente
    if COL_CEDULA in df.columns:
        df[COL_CEDULA] = df[COL_CEDULA].map(cleanCedula)
    if COL_NOMBRE in df.columns:
        df[COL_NOMBRE] = df[COL_NOMBRE].map(cleanNombreCliente)
    # Limpieza de Banco
    if COL_BANCO in df.columns:
        df[COL_BANCO] = df[COL_BANCO].map(cleanText)
    # Limpieza de Montos (incluyendo los Montos a Cuotas)
    for col in [COL_MONTO_ACTUAL, COL_MONTO_PROPUESTO] + (montos_cuotas_cols or []):
        if col in df.columns:
            df[col] = df[col].map(lambda v: cleanNumber(v, default_nan=np.nan))
    # Limpieza de Número de Crédito (se deja como texto sin modificar)
    if COL_CREDITO in df.columns:
        df[COL_CREDITO] = df[COL_CREDITO].apply(lambda s: str(s).replace('.0','').strip() if pd.notna(s) else np.nan)
    # Limpieza de Id_Deuda (si la base lo trae)
    if COL_ID_DEUDA in df.columns:
        df[COL_ID_DEUDA] = df[COL_ID_DEUDA].apply(lambda s: str(s).replace('.0','').strip() if pd.notna(s) else '')
    # Columnas Nullables: Volvemos los vacíos a NaN
    for col in [COL_NOMBRE, COL_BANCO, COL_MONTO_ACTUAL, COL_CREDITO, COL_MONTO_PROPUESTO]:
        if col in df.columns:
            df[col] = df[col].replace('', np.nan)
    # Devolvemos el DF Limpio
    return df

# Función Auxiliar para Construir el DataFrame Formateado según PendienteCruceSchema
def build_pendiente_cruce_df(*,
        cruce_df: pd.DataFrame,
        match_result: Optional[pd.DataFrame],
        cartera_df: pd.DataFrame,
        pagos_cuotas_dict: dict[str,list],
        fecha_limite_serie: pd.Series,
        casa_cobro: str,
        ejecutivo_subida: str,
        descuento_maximo: bool,
        nombre_archivo: str,
        alias_casa: Optional[str] = None,
        id_deuda_col: Optional[str] = None,
    ) -> DataFrame[PendienteCruceSchema]:
    # Paso 1: Dejar la Cartera (Universo) sin Duplicados de Id_Deuda
    cartera_unico = cartera_df.drop_duplicates(subset=COL_ID_DEUDA, keep='first').copy()
    cartera_unico[COL_ID_DEUDA] = cartera_unico[COL_ID_DEUDA].astype(str)

    # Paso 2: Crear el Diccionario de Información de Deudas por Id_Deuda
    cartera_info = {}
    for _, fila in cartera_unico.iterrows():
        id_deuda = str(fila[COL_ID_DEUDA])
        cartera_info[id_deuda] = {
            COL_BANCO: (str(fila[COL_BANCO]) if (COL_BANCO in fila.index) and pd.notna(fila[COL_BANCO]) else ''),
            COL_MONTO_ACTUAL: (float(fila[COL_MONTO_ACTUAL]) if (COL_MONTO_ACTUAL in fila.index) and pd.notna(fila[COL_MONTO_ACTUAL]) else float('nan')),
            COL_CREDITO: (str(fila[COL_CREDITO]).replace('.0','').strip() if (COL_CREDITO in fila.index) and pd.notna(fila[COL_CREDITO]) else ''),
            COL_ID_DEUDA: id_deuda,
            "Es_Liquidada": fila.get("Liquidada",False),
        }

    # Paso 3: Indexar el Resultado del Modelo por Id_Cruce
    match_by_id = {}
    if (match_result is not None) and (not match_result.empty):
        match_by_id = {
            str(fila['Id_Registro']): fila for _, fila in match_result.iterrows()
        }

    # Paso 4: Construir las Filas del DataFrame de Salida
    fecha_identificacion = pd.Timestamp.now(tz='America/Bogota').tz_localize(None)
    filas_salida = []
    for i, fila in cruce_df.iterrows():
        id_cruce = str(fila[COL_ID_CRUCE])
        match_fila = match_by_id.get(id_cruce)
        if match_fila is not None:
            # Registro Procesado por el Modelo de Identificación
            etiqueta = str(match_fila['Etiqueta_Registro'])
            ids_candidatos = [str(id_d) for id_d in (match_fila['Ids_Candidatos'] or [])]
            motivos_cruce = match_fila['Motivos_Etiqueta'].split('|')
        else:
            id_pre = ''
            if (id_deuda_col is not None) and pd.notna(fila.get(id_deuda_col)):
                id_pre = str(fila[id_deuda_col]).replace('.0','').strip()
            # Registro que ya traía Id_Deuda en la base (se asume identificado)
            etiqueta = ETIQUETA_EXACTO if id_pre else ETIQUETA_NULO
            ids_candidatos = [id_pre] if id_pre else []
            motivos_cruce = ["Id_Deuda Input"] if id_pre else []

        # Id Definitivo (los EXACTO se guardan directamente con el Id_Deuda del cruce)
        id_definitivo = None
        if (etiqueta == ETIQUETA_EXACTO) and (len(ids_candidatos) == 1):
            id_definitivo = ids_candidatos[0]

        # Deudas Posibles: solo los Ids que devolvió el Modelo, cruzados con la Cartera
        deudas_posibles = []
        for id_deuda in ids_candidatos:
            info = cartera_info.get(id_deuda)
            if info is None:
                info = {COL_BANCO: '', COL_MONTO_ACTUAL: float('nan'), COL_CREDITO: '', COL_ID_DEUDA: id_deuda}
            deudas_posibles.append(DeudasPosiblesCruce(**info))

        # Pagos a Cuotas, Fecha Límite de Pago y Portafolio
        pagos_cuotas = [PagosCuotasCruce(**info) for info in pagos_cuotas_dict.get(fila[COL_ID_CRUCE],[])]
        fecha_limite = fecha_limite_serie.iloc[i] if i < len(fecha_limite_serie) else pd.NaT # type: ignore
        monto_propuesto = fila.get(COL_MONTO_PROPUESTO)

        # Creación de la Metadata del Registro
        mtdt = create_metadata_cruce(
            id_registro=(i + 1), # type: ignore
            pagos_cuotas=pagos_cuotas,
            fecha_identificacion=fecha_identificacion,
            fecha_limite_pago=fecha_limite, # type: ignore
            etiqueta=etiqueta,
            motivos_cruce = motivos_cruce,
            deudas_posibles=deudas_posibles,
            casa_cobro=casa_cobro,
            ejecutivo_subida=ejecutivo_subida,
            alias_casa=alias_casa,
            id_definitivo=id_definitivo,
            descuento_maximo = descuento_maximo,
            nombre_archivo = nombre_archivo,
            monto_propuesto=monto_propuesto
        )

        # Agregar la Fila de Salida
        filas_salida.append({
            COL_ID_CRUCE: id_cruce,
            COL_CEDULA: fila.get(COL_CEDULA),
            COL_NOMBRE: fila.get(COL_NOMBRE),
            COL_BANCO: fila.get(COL_BANCO),
            COL_MONTO_ACTUAL: fila.get(COL_MONTO_ACTUAL),
            COL_CREDITO: fila.get(COL_CREDITO),
            'Metadata': mtdt,
        })

    # Paso 5: Validar y Devolver el DataFrame de Pendientes de Cruce
    if not filas_salida:
        return PendienteCruceSchema.empty()
    df_salida = pd.DataFrame(filas_salida)
    df_salida = PendienteCruceSchema.validate(df_salida, lazy=True)
    return df_salida

# Función Auxiliar para Aplicar los Cambios Manuales de Id_Definitivo a la Metadata
def aplicar_cambios_id_definitivo(*, cruce_df: pd.DataFrame, cambios: dict) -> pd.DataFrame:
    # Paso 1: Filtramos los Registros con Cambios Pendientes
    cambios_keys = [str(k) for k in cambios.keys()]
    mask = cruce_df[COL_ID_CRUCE].astype(str).isin(cambios_keys)
    df_actualizar = cruce_df.loc[mask].copy()
    if df_actualizar.empty:
        return df_actualizar

    # Paso 2: Definimos la Fecha de Última Actualización
    ahora = pd.Timestamp.now(tz='America/Bogota').tz_localize(None)

    # Paso 3: Aplicamos el Cambio a la Metadata de cada Registro
    def actualizar_mtdt(fila):
        mtdt = dict(fila['Metadata'])
        id_cruce = str(fila[COL_ID_CRUCE])
        mtdt['Id_Definitivo'] = cambios[id_cruce]
        mtdt['Ultima_Actualizacion'] = ahora
        # Actualizamos el Status de Cruce a Reconocido
        mtdt['Cruce_Status'] = 'Reconocido'
        return parse_metadata_cruce(mtdt)

    df_actualizar['Metadata'] = df_actualizar.apply(actualizar_mtdt, axis=1)

    # Paso 4: Devolver el DataFrame Actualizado
    return df_actualizar

# Función Auxiliar para Buscar los Datos de las Deudas
def search_data_deudas(*,cedula: str):
    # Ejecutar la Función de Obtención de Datos y Guardarla en el Session State
    key_deudas = 'cruce_deudas_posibles_{}'.format(cedula)
    st.session_state[key_deudas] = obtener_datos_deuda_cedula(cedula = cedula)