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
        return str(obj)