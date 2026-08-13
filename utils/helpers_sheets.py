# Usando Pip8
# Librerías de Python
from time import sleep
from typing import Any
from unittest import result
import json
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

def _batch_update_rows(ws, start_col_letter: str, end_col_letter: str, row_blocks: list[tuple[int,int,list[list[str]]]], cell_threshold: int = 10000):
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

def letter_to_col(col_str: str) -> int:
    """Convierte una letra de columna de Sheets (ej. 'A', 'Z', 'AA') a su número de índice 1-based."""
    num = 0
    for char in col_str.upper():
        num = num * 26 + (ord(char) - ord('A') + 1)
    return num


def col_to_letter(col_idx: int) -> str:
    """Convierte un índice numérico 1-based de columna a su letra correspondiente en Sheets."""
    result = ""
    while col_idx > 0:
        col_idx, remainder = divmod(col_idx - 1, 26)
        result = chr(65 + remainder) + result
    return result


def update_sheet_data_batch(
    ws,
    data: list[list],
    start_col_letter: str = "A",
    cell_threshold: int = 10000
) -> bool:
    """
    Actualiza Google Sheets de forma masiva y eficiente agrupando filas consecutivas
    y dividiendo los envíos en bloques según un umbral de celdas.

    :param ws: Objeto Worksheet de gspread.
    :param data: Lista de listas con estructura [Número_Fila_Sheets, col1, col2, ...].
    :param start_col_letter: Letra de la columna donde inicia el bloque de datos (por defecto 'A').
    :param cell_threshold: Umbral máximo de celdas por solicitud batch_update.
    :return: True si la actualización se completó con éxito, False de lo contrario.
    """
    if not data:
        return True

    try:
        # 1. Extraer los números de fila y mapear sus respectivos valores
        values_by_rownum = {}
        num_cols = None

        for item in data:
            if not item:
                continue
            
            row_num = item[0]
            row_values = item[1:]

            # Registrar la cantidad de columnas basada en la primera fila no vacía
            if num_cols is None:
                num_cols = len(row_values)

            values_by_rownum[row_num] = row_values

        if not values_by_rownum or num_cols == 0:
            return True

        # 2. Ordenar las filas para poder detectar la consecutividad
        rownums_sorted = sorted(values_by_rownum.keys())

        # 3. Calcular la letra de la columna final según la longitud de los headers/datos
        start_col_idx = letter_to_col(start_col_letter)
        end_col_idx = start_col_idx + num_cols - 1 # type: ignore
        end_col_letter = col_to_letter(end_col_idx)

        # 4. Crear bloques de filas consecutivas
        row_blocks = _make_consecutive_blocks(rownums_sorted, values_by_rownum)

        # 5. Ejecutar la actualización masiva utilizando los bloques generados
        _batch_update_rows(
            ws=ws,
            start_col_letter=start_col_letter.upper(),
            end_col_letter=end_col_letter,
            row_blocks=row_blocks,
            cell_threshold=cell_threshold
        )

        return True

    except Exception as e:
        print(f"[Error] No se pudo completar la actualización en lote: {e}")
        return False

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
def uploadToSheets(ws: gspread.Worksheet, df: pd.DataFrame, resizing: bool = False, retry_label="Upload Data"):
    """
    Uploads a DataFrame to a Google Sheet, ensuring column alignment
    and cleaning up unnecessary columns.
    """
    _retry(lambda: ws.clear(), label="clear sheet")
    _retry(lambda: set_with_dataframe(ws, df, resize=resizing), label=f"{retry_label} ({len(df)} rows)")

# Función para Obtener el Nombre de la Columna de Google Sheets a partir del Índice (1-based)
def get_column_letter(col_idx: int) -> str:
    """Convert a 1-based column index to a column letter (e.g., 1 -> 'A', 27 -> 'AA')."""
    if col_idx < 1:
        raise ValueError("Column index must be 1 or greater.")
    
    result = ""
    while col_idx > 0:
        col_idx, remainder = divmod(col_idx - 1, 26)
        result = chr(65 + remainder) + result
    return result

# Función Auxiliar para Convertir los Datos a String
def convert_data_to_string(obj: Any) -> str:
    """
    Converts various data types to a string representation.
    Handles None, NaN, and other types gracefully.
    """
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, pd.Timestamp) and pd.isna(obj):
        return ''
    if isinstance(obj, pd.Timestamp):
        return obj.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(obj, float) and np.isnan(obj):
        return ""
    if isinstance(obj, (int, float)):
        return str(obj)
    # For other types (like lists, dicts), we can use json.dumps for a readable format
    try:
        return json.dumps(obj, ensure_ascii=False)
    except TypeError:
        return str(obj).replace('\'','"')