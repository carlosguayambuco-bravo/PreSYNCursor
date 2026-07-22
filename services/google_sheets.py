# Usando Pip8
# Librerías de Python
import json
import os
# Librerías de Terceros
import gspread
from gspread.exceptions import APIError, SpreadsheetNotFound, WorksheetNotFound
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from google.oauth2.service_account import Credentials
import pandas as pd
# Librerías Locales
from utils.helpers_sheets import _retry

# Clase de GoogleSheetsService para interactuar con la API de Google Sheets (usando gspread)
class GoogleSheetsService:
    def __init__(self, credentials: dict):
        self._init_client(credentials)

    # Inicializa el cliente de gspread con las credenciales proporcionadas
    def _init_client(self, credentials: dict):
        creds = Credentials.from_service_account_info(credentials)
        self.client = gspread.authorize(creds)

    # Método para obtener los Datos de una hoja de cálculo como un DataFrame de pandas
    def get_sheet_as_dataframe(self, spreadsheet_id: str, worksheet_name: str) -> pd.DataFrame:
        try:
            spreadsheet = _retry(lambda: self.client.open_by_key(spreadsheet_id))
            worksheet = _retry(lambda: spreadsheet.worksheet(worksheet_name))
            df = _retry(lambda: get_as_dataframe(worksheet, evaluate_formulas=True))
            return df # type: ignore
        except SpreadsheetNotFound:
            raise ValueError(f"Spreadsheet with ID '{spreadsheet_id}' not found.")
        except WorksheetNotFound:
            raise ValueError(f"Worksheet '{worksheet_name}' not found in spreadsheet '{spreadsheet_id}'.")
        except APIError as e:
            raise RuntimeError(f"API error occurred: {e}")