# Estándar usando Pep8
# Librerías de Python
from typing import Literal, Optional
# Librerías de Terceros
import pandas as pd
import streamlit as st
# Librerías Locales
from utils.initializer import load_client_balances, IVA
from utils.helpers_sheets import appendDataFrameToEnd
from .constants import QUERY_DEBT_TO_REFERENCE, QUERY_ACTIVE_DEBTS, SOLICITUDES_SHEETS_ID, SOLICITUDES_WORKSHEET_NAME

# Creamos la Clase Aliado para guardar la información de cada aliado de forma estructurada
class Aliado:
    def __init__(self,*,
                nombre: str, 
                bancos: list,
                permite_contacto: bool,
                aliado_formal: bool,
                negociacion_bloque: bool,
                pago_co_obligatorio: bool,
                brinda_descuento_max: bool,
                ):
        self.nombre = nombre
        self.bancos = bancos
        self.permite_contacto = permite_contacto
        self.aliado_formal = aliado_formal
        self.negociacion_bloque = negociacion_bloque
        self.pago_co_obligatorio = pago_co_obligatorio
        self.brinda_descuento_max = brinda_descuento_max

    def brinda_maximo_descuento(self) -> bool:
        return self.brinda_descuento_max

    def es_formal(self) -> bool:
        return self.aliado_formal

    def permite_contactar(self) -> bool:
        return self.permite_contacto

    def validar_banco(self, banco: str) -> bool:
        return banco in self.bancos

    def pagar_co_obligatorio(self) -> bool:
        return self.pago_co_obligatorio

    def negocia_en_bloque(self) -> bool:
        return self.negociacion_bloque

# Función Auxiliar para Crear un Diccionario de Aliados a partir de un DataFrame
def crear_diccionario_aliados(df: pd.DataFrame) -> dict:
    # Paso 1: Definir un Diccionario Vacío para Guardar los Aliados
    aliados_dict = {}

    # Paso 2: Iterar sobre cada Fila del DataFrame y Crear un Objeto Aliado
    for _, row in df.iterrows():
        current_aliado = Aliado(
            nombre=row['Casa de Cobro'],
            bancos=[banco.strip() for banco in row['Bancos'].split(',')],
            permite_contacto=row['Permite Contacto'] == 'SI',
            aliado_formal=row['Tipo Aliado'] == 'Formal',
            negociacion_bloque=row['Negociación en Bloque'] == 'SI',
            pago_co_obligatorio=row['Pago CO Obligatorio'] == 'SI',
            brinda_descuento_max=row['Brinda Descuento Máximo'] == 'SI'
        )
        aliados_dict[current_aliado.nombre] = current_aliado

    # Paso 3: Devolver el Diccionario de Aliados
    return aliados_dict

# Función Auxiliar para Obtener el Descuento Óptimo para una Referencia
def obtener_descuento_optimo(*,referencia: str, pricing: float, pago_total_original: float, descuento_pl: float):
    # Paso 1: Obtener el Ahorro y el Por Cobrar de la Referencia
    saldosDict = load_client_balances()
    ahorro = saldosDict['Saldos'][referencia]
    por_cobrar = saldosDict['PorCobrar'][referencia]

    # Paso 2: Calcular el Descuento Óptimo
    descuento_optimo = (ahorro - por_cobrar - pago_total_original) / (pago_total_original * (pricing * IVA) - 1)

    # Paso 3: Devolver el Descuento Óptimo con Piso descuento_pl y techo 1
    return min(max(descuento_optimo, descuento_pl), 1)

# Función Auxiliar para obtener la referencia dada una deuda
def obtener_referencia_por_deuda(*,deuda: str) -> str:
    # Paso 1: Obtener El Servicio de Metabase
    metabase_service = st.session_state["metabase_service"]
    # Paso 2: Obtener los Datos de la Consulta SQL para Obtener la Referencia
    query = QUERY_DEBT_TO_REFERENCE.format(debt_id=deuda)
    # Paso 3: Obtener la Referencia desde Metabase
    referencia_df = metabase_service.execute_query(query)
    # Paso 4: Devolver la Referencia si Existe, de lo Contrario Devolver None
    if not referencia_df.empty:
        return str(referencia_df.iloc[0]['Referencia']).replace(".0", "").strip()
    return ""

# Función Auxiliar para Obtener las Deudas Activas de una Referencia
def obtener_deudas_activas(*,referencia: str) -> pd.DataFrame:
    # Paso 1: Obtener El Servicio de Metabase
    metabase_service = st.session_state["metabase_service"]
    # Paso 2: Obtener los Datos de la Consulta SQL para Obtener las Deudas Activas
    query = QUERY_ACTIVE_DEBTS.format(referencia=referencia)
    # Paso 3: Obtener las Deudas Activas desde Metabase
    deudas_df = metabase_service.execute_query(query)
    # Paso 4: Devolver el DataFrame de Deudas Activas
    return deudas_df

# --- Respuestas de Formulario ---

# Clase Respuesta Formulario
class RespuestaFormulario:
    def __init__(self, *,
                correo: str,
                Referencia: str,
                Ids_Deuda: list[str],
                aliado_solicitud: Aliado,
                tipo_solicitud: Literal['Validación','Acuerdo de pago'],
                monto_solicitado: float,
                observaciones: Optional[str] = None,
                fecha_esperada_pago: Optional[pd.Timestamp] = None,
                tipo_pago: Optional[Literal['Tradicional','Estructurado','Refi','Crédito']] = None,
                plazos_pago: Optional[int] = None,
                monto_promesa_deposito: Optional[float] = None,
                fecha_promesa_deposito: Optional[pd.Timestamp] = None,
                ):
        self.correo = correo
        self.Referencia = Referencia
        self.Ids_Deuda = Ids_Deuda
        self.aliado_solicitud = aliado_solicitud
        self.tipo_solicitud = tipo_solicitud
        self.monto_solicitado = monto_solicitado
        self.observaciones = observaciones
        self.fecha_esperada_pago = fecha_esperada_pago
        self.tipo_pago = tipo_pago
        self.plazos_pago = plazos_pago
        self.monto_promesa_deposito = monto_promesa_deposito
        self.fecha_promesa_deposito = fecha_promesa_deposito

    def obtener_df_subida(self) -> pd.DataFrame:
        # Creamos un Diccionario con los Datos de la Respuesta
        data = {
            'Timestamp': pd.Timestamp.now('America/Bogota').strftime('%Y-%m-%d %H:%M:%S'),
            'Correo': self.correo,
            'Referencia': self.Referencia,
            'Ids_Deuda': '-'.join(self.Ids_Deuda),
            'Casa de Cobro': self.aliado_solicitud.nombre,
            'Tipo de Solicitud': self.tipo_solicitud,
            'Monto Solicitado': self.monto_solicitado,
            'Observaciones': self.observaciones,
            'Fecha Esperada de Pago': self.fecha_esperada_pago,
            'Tipo de Pago': self.tipo_pago,
            'Plazos de Pago': self.plazos_pago,
            'Promesa de Depósito': self.monto_promesa_deposito,
            'Fecha Promesada': self.fecha_promesa_deposito,
            'Estado Solicitud': 'Sin Tocar',
        }
        # Devolvemos un DataFrame con un Solo Registro
        return pd.DataFrame([data])

    def validar_respuesta(self) -> bool:
        # Validamos que los Campos Obligatorios Estén Completos
        if not self.correo or not self.Referencia or not self.Ids_Deuda or not self.aliado_solicitud or not self.tipo_solicitud or not self.monto_solicitado:
            return False
        # Validamos que el Monto Solicitado sea Mayor a 0
        if self.monto_solicitado <= 0:
            return False
        # Validamos que la Fecha Esperada de Pago sea Mayor o Igual a Hoy si Existe
        if self.fecha_esperada_pago and self.fecha_esperada_pago <= pd.Timestamp.now('America/Bogota').normalize():
            return False
        # Validamos que la Fecha Promesada de Depósito sea Mayor o Igual a Hoy si Existe
        if self.fecha_promesa_deposito and self.fecha_promesa_deposito <= pd.Timestamp.now('America/Bogota').normalize():
            return False
        # Si Todas las Validaciones Pasan, Devolvemos True
        return True

    def subir_respuesta(self) -> bool:
        # Paso 1: Obtener el Servicio de Google Sheets
        google_sheets_service = st.session_state["google_sheets_service"]
        # Paso 2: Validar la Respuesta antes de Subirla
        if not self.validar_respuesta():
            st.error("La respuesta del formulario no es válida. Por favor, revise los campos obligatorios y las fechas.")
            return False
        # Paso 3: Obtener el DataFrame de la Respuesta
        df_respuesta = self.obtener_df_subida()
        # Paso 4: Obtener la Worksheet de Respuestas desde Google Sheets
        worksheet = google_sheets_service.get_worksheet(
            spreadsheet_id=SOLICITUDES_SHEETS_ID,
            worksheet_name=SOLICITUDES_WORKSHEET_NAME
        )
        # Paso 5: Añadir la Respuesta al Final de la Worksheet
        try:
            appendDataFrameToEnd(worksheet, df_respuesta)
            return True
        except Exception as e:
            st.error(f"Error al subir la respuesta del formulario: {e}")
            return False

    def actualizar_campos_respuesta(self, **kwargs):
        # Actualizamos los Campos de la Respuesta con los Valores Proporcionados
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)