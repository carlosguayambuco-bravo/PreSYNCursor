# Usando Pip8
# Librerías de Python
from time import sleep
from unittest import result
# Librerías de Terceros
from gspread.exceptions import APIError
from gspread_dataframe import get_as_dataframe, set_with_dataframe
import gspread
import numpy as np
import pandas as pd

# Párametros de Configuración
MAX_RETRIES = 10

# Función Auxiliar para reintentar cualquier llamda al API de sheets
def _retry(fn, label="", tries=MAX_RETRIES, base_sleep=1.5, jitter=0.6, max_sleep=45):
    RETRIABLE_CODES = ["[500]", "[502]", "[503]", "[504]", "[429]"]
    last_err = ValueError("No se ejecutó la función")
    for i in range(tries):
        try:
            return fn()
        except APIError as e:
            last_err = e
            msg = str(e)
            # Si el error fue del servidor
            if any(c in msg for c in RETRIABLE_CODES):
                sleep_s = min((base_sleep) * (2 ** i) + np.random.uniform(0, jitter), max_sleep)
                print(f"[RETRY {i+1}/{tries}] {label} -> {msg[:120]}... sleep {sleep_s:.1f}s")
                # Esperamos para no saturar al API
                sleep(sleep_s)
                continue
            raise e
    raise last_err

# Función Auxiliar para Obtener un Diccionario con las Variables de Entorno
def getEnvVarsFromSheet(ws: gspread.Worksheet, cellRange: str) -> dict:
    # Get values using your retry logic
    values = _retry(lambda: ws.get(cellRange, pad_values=True), label=f"get {cellRange} for {ws.title}")

    if not values:
        raise ValueError('No hay Datos Suficientes')

    result = {}
    for row in values:
        key = row[0] if len(row) > 0 else None
        # If the row is shorter than 2 elements, the second value is 'missing'
        # We assign None (Python's version of NaN) or ""
        val = row[1] if len(row) > 1 else None
        if key:
            result[key] = val

    return result

# Funcion Auxiliar para obtener worksheet con objeto sheet
def getWorksheet(sh: gspread.Spreadsheet, wsName: str, df: pd.DataFrame):
    try:
        return _retry(lambda: (True, sh.worksheet(wsName)))
    except:
        return _retry(lambda: (False, sh.add_worksheet(wsName, df.shape[0], df.shape[1])))

# Función Auxiliar para obtener un DF a partir de la hoja y el rango
def gettingAsDF(ws: gspread.Worksheet, cellRange: str) -> pd.DataFrame:
    # Obtenemos los valores del rango propuesto
    values = _retry(lambda: ws.get(cellRange, pad_values=True))
    # Definimos los headers y las filas
    headers = values[0]
    rows = values[1:]
    # Creamos el DF
    df = pd.DataFrame(rows, columns=headers)
    return df

def appendDataFrameToEnd(ws: gspread.Worksheet, df: pd.DataFrame, retry_label="Append Data"):
    """
    Appends a DataFrame to the end of a Google Sheet, ensuring column alignment
    and cleaning up unnecessary columns.
    """
    # 1. Obtener los Headers
    # We use index 1 to get the first row (headers)
    sheet_headers = _retry(lambda: ws.row_values(1))
    if not sheet_headers:
        raise ValueError("The target sheet is empty. Please add headers first.")

    # 2. Eliminar Columnas Unnamed
    df_clean = df.loc[:, ~df.columns.str.contains('^Unnamed')].copy()

    # 3. Organizar las Columnas
    # - Solo se dejan columnas existentes en el sheets
    # - Si una columna falta, se agrega y se deja vacia
    # - Se ordenan las columnas del mismo modo en el que estan en sheets
    df_final = pd.DataFrame(columns=sheet_headers)
    for col in sheet_headers:
        if col in df_clean.columns:
            df_final[col] = df_clean[col]
        else:
            df_final[col] = "" # Fill missing columns with empty strings

    # 4. Data Preparation: Convert to list of lists and handle NaNs/Dates
    # We reuse the logic from your previous preparation steps
    df_final = df_final.replace([np.inf, -np.inf], None)

    # Format dates to string to avoid JSON serializing errors
    for c in df_final.columns:
        if pd.api.types.is_datetime64_any_dtype(df_final[c]):
            df_final[c] = df_final[c].dt.strftime("%Y-%m-%d %H:%M:%S")

    # Fill NaNs with empty string
    values_to_append = df_final.fillna("").values.tolist()

    # 5. Execute Append with Retry Logic
    if values_to_append:
        # We use value_input_option="USER_ENTERED" so dates/numbers are parsed by Sheets
        _retry(
            lambda: ws.append_rows(values_to_append, value_input_option="USER_ENTERED"), # type: ignore
            label=f"{retry_label} ({len(values_to_append)} rows)"
        )

    return True

# Función Auxiliar para subir los datos a una hoja
def uploadToSheets(ws: gspread.Worksheet, df: pd.DataFrame, rezising: bool = False, retry_label="Upload Data"):
    """
    Uploads a DataFrame to a Google Sheet, ensuring column alignment
    and cleaning up unnecessary columns.
    """
    _retry(lambda: ws.clear(), label="clear sheet")
    _retry(lambda: set_with_dataframe(ws, df, resize=rezising), label=f"{retry_label} ({len(df)} rows)")

# Funcion Auxiliar para comparar DF y SheetRows cambiando columnas tipo DateTime
def _prepare_df_for_sheets(df: pd.DataFrame) -> pd.DataFrame:
    df_out = df.copy()
    df_out = df_out.replace([np.inf, -np.inf], np.nan)

    # Si alguna columna es DateTime la volvemos string
    for c in df_out.columns:
        if pd.api.types.is_datetime64_any_dtype(df_out[c]):
            # datetime64[ns] y datetime64[ns, tz]
            df_out[c] = pd.to_datetime(df_out[c], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S")

    # Cambiamos NaNs por valores vacios
    df_out = df_out.where(pd.notna(df_out), "")
    return df_out

# Función Auxiliar para compara DF y SheetRows convirtiendo las columnas en strings
def _df_to_str_matrix(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """
    Normaliza para comparar contra Sheets (que casi siempre devuelve strings).
    """
    out = df[cols].copy()
    for c in cols:
        # todo como string comparable; "" para vacíos
        out[c] = out[c].astype(str)
        out.loc[out[c].isin(["nan", "NaT", "<NA>", "None"]), c] = ""
    return out

def _batch_update_rows(ws: gspread.Worksheet, start_col_letter: str, end_col_letter: str, row_blocks: list[tuple[int,int,list[list[str]]]], cell_threshold: int = 10000):
    """
    Updates Google Sheets using batch_update to minimize API calls.
    Groups row_blocks into 'mega-batches' based on a cell_threshold.
    """

    current_batch_data = []
    current_cell_count = 0

    for (r1, r2, mat) in row_blocks:
        # Calculate cells in this specific block
        block_cells = len(mat) * len(mat[0]) if mat else 0
        rng = f"{start_col_letter}{r1}:{end_col_letter}{r2}"

        # Prepare the update object for this block
        update_item = {
            'range': rng,
            'values': mat
        }

        # Check if adding this block exceeds our threshold
        if current_cell_count + block_cells > cell_threshold and current_batch_data:
            # Execute the accumulated batch before starting a new one
            _execute_batch_retry(ws, current_batch_data)
            current_batch_data = []
            current_cell_count = 0
            sleep(0.5) # Slight breather between mega-batches

        current_batch_data.append(update_item)
        current_cell_count += block_cells

    # Final execution for any remaining data
    if current_batch_data:
        _execute_batch_retry(ws, current_batch_data)

def _execute_batch_retry(ws, data_list):
    """
    Helper to wrap the batch_update in your retry logic.
    """
    _retry(
        lambda: ws.batch_update(data_list, value_input_option="USER_ENTERED"),
        label=f"batch_update for {len(data_list)} ranges"
    )

# Funcion auxiliar para unir filas actualizadas en una sola y poder realizar cambios enteros por chunks
def _make_consecutive_blocks(rownums_sorted: list[int], values_by_rownum: dict[int, list[str]]):
    """
    Agrupa filas consecutivas para reducir llamadas a la API.
    Retorna [(start_row, end_row, matrix_values)]
    """
    blocks = []
    if not rownums_sorted:
        return blocks

    start = prev = rownums_sorted[0]
    mat = [values_by_rownum[start]]

    for r in rownums_sorted[1:]:
        # Si la fila es adyacente a la anterior se uno como un bloque
        if r == prev + 1:
            mat.append(values_by_rownum[r])
            prev = r
        else:
            # Si no, entonces se guarda el bloque y se crea uno nuevo
            blocks.append((start, prev, mat))
            start = prev = r
            mat = [values_by_rownum[r]]
    # Se guarda el último bloque en memoria
    blocks.append((start, prev, mat))
    return blocks

def applyChanges(ws: gspread.Worksheet, df: pd.DataFrame, identifierCol: str, numericCols = [], dateCols = [], semiStrCols = []) -> tuple[bool, str]:
    # Transformamos el DataFrame previo a la comparación
    dfOut = _prepare_df_for_sheets(df)

    # Construir DF de Sheets
    df_sheet = _retry(lambda: get_as_dataframe(ws, evaluate_formulas=True), label="fetch sheet data for comparison")
    sheet_header = df_sheet.columns.tolist()
    cols = dfOut.columns.tolist()

    # Ponemos los valores "" como NaNs
    df_sheet = df_sheet.replace("", np.nan)
    dfOut = dfOut.replace("", np.nan)

    # Si por cualquier razón Sheets no trae todas las columnas, nos quedamos con intersección
    missing_in_sheet = [c for c in cols if c not in df_sheet.columns]
    if missing_in_sheet:
        print("⚠️ En Sheets faltan estas columnas vs DF:", missing_in_sheet)
        print(sheet_header,cols)

        # Si son más de 10 Columnas, entonces se va a reescribir toda la información del Sheets
        if len(missing_in_sheet) > 10:
            print("⚠️ Más de 10 columnas faltantes, se va a reescribir toda la información del Sheets para evitar inconsistencias.")
            print('🆔Comenzando a Subir información a Sheets...')
            uploadToSheets(ws, dfOut, retry_label="Full Upload due to many missing columns")
            return True, f"✅ Completado: Se subió toda la información debido a la falta de {len(missing_in_sheet)} columnas en Sheets. Columnas faltantes: {missing_in_sheet}"

        # Igual seguimos, pero esas columnas las tratamos como "" al comparar
        for c in missing_in_sheet:
            df_sheet[c] = ""

    ##### Solución a Problema de comparar floats a int
    # La solucion consiste en convertir todas las variables numericas a float
    dfOut[identifierCol] = dfOut[identifierCol].apply(lambda s: str(s).replace('.0',''))
    df_sheet[identifierCol] = df_sheet[identifierCol].apply(lambda s: str(s).replace('.0',''))
    for c in numericCols:
        dfOut[c] = dfOut[c].astype(float).round(2)
        df_sheet[c] = df_sheet[c].astype(float).round(2)
        # Reemplazamos Infinitos con NaNs
        dfOut[c] = dfOut[c].replace([np.inf, -np.inf], np.nan)
        df_sheet[c] = df_sheet[c].replace([np.inf, -np.inf], np.nan)

    # Ahora se cambian tambien todas las variables tipo Datetime
    for c in dateCols:
        temp_py = pd.to_datetime(dfOut[c], errors='coerce')
        temp_sheet = pd.to_datetime(df_sheet[c], errors='coerce')
        # Se ponen las columnas como formato largo
        dfOut[c] = temp_py.dt.strftime("%Y-%m-%d %H:%M:%S").fillna("")
        df_sheet[c] = temp_sheet.dt.strftime("%Y-%m-%d %H:%M:%S").fillna("")

    # Ahora para las Columnas semiString, se vuelve todo a string y se quitan los .0 sobrantes
    for c in semiStrCols:
        dfOut[c] = dfOut[c].astype(str).apply(lambda s: str(s).replace('.0','').replace('nan','').replace('NaT','').replace('<NA>','').replace('None',''))
        df_sheet[c] = df_sheet[c].astype(str).apply(lambda s: str(s).replace('.0','').replace('nan','').replace('NaT','').replace('<NA>','').replace('None',''))

    # Volvemos a hacer fill de nans con ""
    dfOut = dfOut.fillna("")
    df_sheet = df_sheet.fillna("")

    # Map id -> row_number en Sheets (row 2 = primer dato)
    id_to_rownum = {}
    for i, v in enumerate(df_sheet[identifierCol].tolist(), start=2):
        if v != "":
            # si hay duplicados, nos quedamos con el primero (puedes cambiarlo si prefieres el último)
            if v not in id_to_rownum:
                id_to_rownum[v] = i

    # Convertimos el df local para comparar a solo strings
    df_py_cmp = _df_to_str_matrix(dfOut, cols)

    # Creamos sets para comparar la interseccion
    ids_sheet = set(id_to_rownum.keys())
    ids_py = set(df_py_cmp[identifierCol].tolist())

    # Diferenciamos Ids comunes de los ID que son nuevos en la SpreadSheet
    ids_common = ids_py.intersection(ids_sheet)
    ids_new = sorted(list(ids_py - ids_sheet))

    # Indexar para comparación rápida
    df_sheet_cmp = _df_to_str_matrix(df_sheet, cols) # type: ignore

    sheet_by_id = df_sheet_cmp.set_index(identifierCol, drop=False)
    py_by_id = df_py_cmp.set_index(identifierCol, drop=False)

    # Encontrar ids cambiados (comparando todas las columnas excepto Referencia)
    compare_cols = [c for c in cols if c != identifierCol]
    changed_ids = []
    for _id in ids_common:
        # si por algo no aparece, saltamos
        if _id not in sheet_by_id.index or _id not in py_by_id.index:
            continue
        a = sheet_by_id.loc[_id, compare_cols]
        b = py_by_id.loc[_id, compare_cols]
        # a y b son Series
        ##### Problema Fundamental: Cuando un valor cambia de int a float, se agrega como n.0 y se produce automaticamente un cambio

        if not a.equals(b):
            changed_ids.append(_id)
    # Preparar updates por row_number
    values_by_rownum = {}
    for _id in changed_ids:
        rownum = id_to_rownum.get(_id)
        if not rownum:
            continue
        row_values = py_by_id.loc[_id, cols].tolist() # type: ignore

        # Último Intento de Corregir Error JSON out of range
        # Convertimos NaNs inf o -inf en ''
        # 2. Convertimos y limpiamos de forma segura para JSON:
        sanitized_row = []
        for r in row_values:
            # Si es un valor nulo/nan/infinito de numpy o pandas, lo volvemos string vacío
            if pd.isna(r) or r in [np.inf, -np.inf]:
                sanitized_row.append('')
            # Si es un tipo entero/flotante de numpy, lo casteamos a primitivo de Python
            elif hasattr(r, 'item'):
                sanitized_row.append(r.item())
            else:
                sanitized_row.append(r)

        values_by_rownum[rownum] = sanitized_row

    rownums_sorted = sorted(values_by_rownum.keys())

    start_col_letter = "A"
    end_col_letter = gspread.utils.rowcol_to_a1(1, len(df.columns)).replace("1", "")
    blocks = _make_consecutive_blocks(rownums_sorted, values_by_rownum)

    # Aplicar updates (en bloques)
    if blocks:
        _batch_update_rows(ws, start_col_letter, end_col_letter, blocks)

    # Agregar los nuevos
    if ids_new:
        # Asegurar que todo se convierta a tipos nativos de Python (o string) antes de enviar
        rows_new = []
        for _id in ids_new:
            row_values = py_by_id.loc[_id, cols].tolist()
            # Convertir cada elemento a string si persiste el error, o usar .item()
            sanitized_row = ["" if pd.isna(x) or x in [np.inf, -np.inf] else (x.item() if hasattr(x, 'item') else x) for x in row_values]
            rows_new.append(sanitized_row)

        for i in range(0, len(rows_new), 1000):
            chunk = rows_new[i:i+1000]
            _retry(lambda ch=chunk: ws.append_rows(ch, value_input_option="USER_ENTERED"), label=f"append_rows new {i}-{i+len(chunk)-1}") # type: ignore
            sleep(1)

    return True, (
        f"✅ Completado: "
        f"👍{len(changed_ids):,} filas actualizadas, ℹ️{len(ids_new):,} nuevas {identifierCol}s. "
        f"Total DF={len(dfOut):,} / Total sheet aprox={len(df_sheet):,}"
    )