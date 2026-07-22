# Estándar usando Pep8
# Librerías de Python
import os
import json
# Librerías de Terceros
import streamlit as st
import pandas as pd

mesesDict = {
    1: 'Enero',2: 'Febrero',3: 'Marzo',4: 'Abril',5: 'Mayo',6: 'Junio',
    7: 'Julio',8: 'Agosto',9: 'Septiembre',10: 'Octubre',11: 'Noviembre',12: 'Diciembre'
}

LIMITE_MEC = 4 # El Día límite para Considerar el Día como mes operativo

# Función Auxiliar para imputar NaNs
def imputeNans(df: pd.DataFrame, col: str, value):
    # Se define la mascara de valores nulos
    mask = df[col].isna()
    # A los valores nulos se aplica el valor
    df.loc[mask, col] = value

# Función Auxiliar para limpiar valores
def cleanText(txt) -> str:
    if pd.isna(txt):
        return "nan"
    return txt.lower().replace("ó", "o").replace("á", "a").replace("í", "i").replace("é", "e").replace("ú", "u").upper().strip()

# Función Auxiliar para Limpiar Números
def cleanNumber(value) -> float:
    if not isinstance(value, str):
        return value
    # Reemplazamos X por ''
    value = value.replace('X','')

    # Check if the string contains numbers and currency symbols/commas
    # This regex matches things like: "$ 1.234,56", "50,000", or "1.200.000,00"
    clean_val = value.replace('$', '').replace(' ', '')

    try:
        # Common in Latin America: 1,000.00 -> 1000.00
        if (',' in clean_val) and ('.' in clean_val) and (clean_val.index(',') > clean_val.index('.')):
            clean_val = clean_val.replace(',', '')
        elif (',' in clean_val) and ('.' in clean_val) and (clean_val.index(',') < clean_val.index('.')):
            # Reemplzamos . con nada y luego , con .
            clean_val = clean_val.replace('.', '').replace(',', '.')
        elif '.' in clean_val and clean_val.count('.') > 1:
            # Handle "666.666.666" as 666666666
            clean_val = clean_val.replace('.','')
        elif ',' in clean_val and clean_val.count(',') > 1:
            # Handle "666.666.666" as 666666666
            clean_val = clean_val.replace(',','')
        elif ',' in clean_val and clean_val.count(',') > 1:
            parts = clean_val.split(',')
            # The first part can be 1-3 digits; all following parts MUST be exactly 3 digits
            if 1 <= len(parts[0]) <= 3 and all(len(s) == 3 for s in parts[1:]):
                clean_val = clean_val.replace(',', '')
            else:
                # If it's a decimal separator used multiple times (e.g., European format typo or specific notation)
                # Note: A valid float can only have ONE decimal point.
                # If there are multiple commas acting as decimals, replacing them all with '.' will still error out.
                clean_val = clean_val.replace(',', '.')
        elif '.' in clean_val and clean_val.count('.') == 1:
            # 2 Possible Cases: Decimal Separator or Thousand Separator
            # Detecting case thousand by: splitting and Confirming len of all == 3
            if all([len(s) == 3 for s in clean_val.split('.')]):
                clean_val = clean_val.replace('.', '')
            # Else it's decimal so its ignored

        return float(clean_val)
    except ValueError:
        return pd.to_numeric(value, errors='coerce') # Not a number? Return original text

# Función Auxiliar para Obtener el Mes Operativo
def getMesOperativo() -> pd.Timestamp:
    # Primero Obtenemos el Día de hoy
    today = pd.Timestamp.now().normalize()

    # Si hoy es menor a el día límite, entonces el mes operativo es el mes anterior
    if today.day < LIMITE_MEC:
        mes_operativo = today - pd.DateOffset(months=1)
    else:
        mes_operativo = today

    return mes_operativo.replace(day=1)  # Retornamos el primer día del mes operativo