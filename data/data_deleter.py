# Estándar usando PEP8
# Librerías de Python
from typing import Optional
# Librerías de Terceros
import streamlit as st
# Librerías Locales
from data.data_loader import parse_metadata_cruce
from modules.constants import CONFIGS_SHEET_ID
from utils.helpers_sheets import _retry, deleteRows

# Función Auxiliar para Obtener la Metadata de Cada Fila de la Hoja de Pendientes
def _obtener_metadata_filas(*, worksheet) -> list[tuple[int, dict]]:
    # Paso 1: Cargar la Fila 1 para Obtener los Headers
    headers = _retry(lambda: worksheet.row_values(1), label="Get Pendientes Cruce Headers")
    if 'Metadata' not in headers:
        return []
    # Paso 2: Obtener los Datos de la Columna 'Metadata'
    metadata_col = headers.index('Metadata') + 1
    metadata_values = _retry(lambda: worksheet.col_values(metadata_col), label="Get Pendientes Cruce Metadata")
    # Paso 3: Parsear la Metadata de Cada Fila (Row Number de Sheets = Índice + 2)
    return [
        (row_num, parse_metadata_cruce(mtdt))
        for row_num, mtdt in enumerate(metadata_values[1:], start=2)
    ] # type: ignore

# Función Auxiliar para Verificar si una Fila de Metadata Corresponde a la Base Indicada
def _fila_es_de_base(*, mtdt: dict, casa_cobro: str, alias: str, nombre_archivo: str) -> bool:
    return (
        str(mtdt.get('Casa_Cobro') or '') == str(casa_cobro or '')
        and str(mtdt.get('Alias_Casa') or '') == str(alias or '')
        and str(mtdt.get('Archivo_Origen') or '') == str(nombre_archivo or '')
    )

# Función para Eliminar los Datos de una Base Subida Anteriormente
def eliminar_base_cruce(*, casa_cobro: str, alias: Optional[str] = None, nombre_archivo: str) -> bool:
    # Paso 1: Obtener el Servicio de Google Sheets y la Worksheet
    sheets_service = st.session_state['google_sheets_service']
    cruce_ws = sheets_service.get_worksheet(CONFIGS_SHEET_ID, 'Pendientes_IdAutDeud')
    # Paso 2: Obtener la Metadata de Todas las Filas de la Hoja
    filas_metadata = _obtener_metadata_filas(worksheet=cruce_ws)
    # Paso 3: Identificar las Filas que Corresponden a la Base Seleccionada
    filas_a_eliminar = [
        row_num
        for row_num, mtdt in filas_metadata
        if _fila_es_de_base(
            mtdt=mtdt,
            casa_cobro=str(casa_cobro or ''),
            alias=str(alias or ''),
            nombre_archivo=str(nombre_archivo or ''),
        )
    ]
    # Paso 4: Eliminar las Filas Identificadas usando deleteRows
    if not filas_a_eliminar:
        return True
    return deleteRows(worksheet=cruce_ws, rows_to_delete=filas_a_eliminar)
