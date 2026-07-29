# Estándar usando Pep8
# Librerías de Python
from __future__ import annotations
from typing import Literal, Optional
# Librerías de Terceros
import numpy as np
import pandas as pd
import streamlit as st
# Librerías Locales
from data.data_loader import load_app_config, load_client_balances, load_pab_ideal, load_masivas, load_addendums, load_reference_changes
from utils.helpers_general import getBDDaysDiffFloat
from utils.helpers_sheets import appendDataFrameToEnd
from modules.constants import SOLICITUDES_SHEETS_ID, SOLICITUDES_WORKSHEET_NAME, IVA

# Función Auxiliar para Obtener el Descuento Óptimo para una Referencia por pago Tradicional
def obtener_descuento_optimo_tradicional(*,referencia: str, pricing: float, pago_total_original: float, descuento_pl: float):
    # Paso 1: Obtener el Ahorro y el Por Cobrar de la Referencia
    saldosDict = load_client_balances()
    ahorro = saldosDict['Saldos'][referencia]
    por_cobrar = saldosDict['PorCobrar'][referencia]

    # Paso 2: Calcular el Descuento Óptimo
    descuento_optimo = (ahorro - por_cobrar - pago_total_original) / (pago_total_original * (pricing * IVA) - 1)

    # Paso 3: Devolver el Descuento Óptimo con Piso descuento_pl y techo 1
    return min(max(descuento_optimo, descuento_pl), 1)

# Función Auxiliar para Obtener el Descuento Óptimo para una Referencia por Pago Crédito
def obtener_descuento_optimo_credito(*,referencia: str, deudas: list[str], pricing: float, pago_total_original: float):
    # Paso 1: Obtener el Ahorro y el Por Cobrar de la Referencia
    saldosDict = load_client_balances()
    ahorro = saldosDict['Saldos'][referencia]
    por_cobrar = saldosDict['PorCobrar'][referencia]

    # Paso 2: Obtener el PaB Ideal de las Deudas Seleccionadas
    pabIdealDict = load_pab_ideal()
    montoIdeal = 0
    for deuda in deudas:
        if deuda in pabIdealDict:
            montoIdeal += pabIdealDict[deuda]
        else:
            return 1 # Si no está alguna no se puede realizar el cálculo

    # Paso 3: Calcular el Descuento Óptimo
    descuento_optimo = (ahorro - por_cobrar - pago_total_original) / (pago_total_original * (pricing * IVA) - 1)

    # Paso 4: Devolver el Descuento Óptimo con Techo 1
    return min(descuento_optimo, 1)

# Función para Obtener el Descuento Óptimo General para una Referencia, según el Tipo de Liquidación
def obtener_descuento_optimo(*,referencia: str, deudas: list[str], pricing: float, pago_total_original: float, descuento_pl: float, tipo_pago: Literal['Tradicional','Estructurado','Refi','Crédito','Verificar']):
    if tipo_pago in ['Tradicional','Estructurado','Refi']:
        return obtener_descuento_optimo_tradicional(referencia=referencia, pricing=pricing, pago_total_original=pago_total_original, descuento_pl=descuento_pl)
    elif tipo_pago == 'Crédito':
        return obtener_descuento_optimo_credito(referencia=referencia, deudas=deudas, pricing=pricing, pago_total_original=pago_total_original)
    elif tipo_pago == 'Verificar':
        descuento_tradicional = obtener_descuento_optimo_tradicional(referencia=referencia, pricing=pricing, pago_total_original=pago_total_original, descuento_pl=descuento_pl)
        descuento_credito = obtener_descuento_optimo_credito(referencia=referencia, deudas=deudas, pricing=pricing, pago_total_original=pago_total_original)
        return min(descuento_tradicional, descuento_credito)
    else:
        return 1

# Función para Definir si ya cumple la Condición de Actualización de Deudas
def cumple_condicion_actualizacion_deudas(*,ultima_actualizacion: pd.Timestamp) -> tuple[bool, float]:
    # Obtenemos la Fecha Actual Normalizada a Hoy (Sin Hora)
    fecha_actual = pd.Timestamp.now('America/Bogota').normalize()
    # Obtenemos la Diferencia en Días Hábiles entre Hoy y la Última Actualización
    dias_habiles_diff = getBDDaysDiffFloat(firstDate=ultima_actualizacion, secondDate=fecha_actual)
    # Traemos la Configuracion de la Aplicacion
    appConfig = load_app_config()
    # Veriticamos que satisface la Condición de Mínimo de Días Hábiles para Actualización
    return dias_habiles_diff <= int(appConfig['MIN_NECESSARY_DAYS_FOR_DEBT_UPDATE']), dias_habiles_diff

# Función Auxiliar para Obtener las Deudas del Portafolio de Masivas
def obtener_deudas_portafolio_masivas(*,deuda: str) -> list[str]:
    # Paso 1: Cargamos las Masivas y los Cambios de Referencia
    masivas_df = load_masivas()

    # Paso 2: Buscamos la Deuda en las Masivas
    masiva_row = masivas_df[(masivas_df['Id_Deuda'] == deuda) & (masivas_df['PaB_Portafolio'].notna())]
    if not masiva_row.empty:
        # Obtenemos la Referencia
        ref_deuda = masiva_row['Referencia'].iloc[0] # type: ignore
        # Ahora buscamos todas las Deudas con la misma Referencia y que tengan PaB_Portafolio no nulo
        deudas_portafolio = masivas_df[(masivas_df['Referencia'] == ref_deuda) & (masivas_df['PaB_Portafolio'].notna())]['Id_Deuda'].tolist() # type: ignore
        return deudas_portafolio

    # Paso 3: Si no se encuentra, devolvemos una Lista Vacía
    return []

# Función Auxiliar para Obtener el Descuento por Base si Hay
def obtener_descuento_base(*, deuda: str, portafolio: bool = False) -> float:
    # Paso 1: Cargamos las Masivas y los Addendums
    masivas_df = load_masivas()
    addendums_df = load_addendums()

    # Paso 2: Buscamos la Deuda en las Masivas
    masiva_row = masivas_df[masivas_df['Id_Deuda'] == deuda]
    if not masiva_row.empty:
        if portafolio:
            valor_portafolio = masiva_row['PaB_Portafolio'].iloc[0] # type: ignore
            # Si es NaN lo volvemos 0
            if pd.isna(valor_portafolio):
                valor_portafolio = 0
        else:
            valor_portafolio = 0
        return max(masiva_row['PaB_Propuesta'].iloc[0], valor_portafolio) # type: ignore

    # Paso 3: Buscamos la Deuda en los Addendums
    addendum_row = addendums_df[addendums_df['Id_Deuda'] == deuda]
    if not addendum_row.empty:
        return float(addendum_row['PaB_Propuesta'].values[0]) # type: ignore

    # Paso 4: Si no se encuentra, devolvemos NaN
    return np.nan

# Función Auxiliar para Validar si se cumple la Restricción de Ofertas Menores a Base
def validar_descuento_base(*, deuda: str, deudas_info: dict[str, float], monto_prop: float) -> tuple[bool, str]:
    # Obtenemos el Descuento Base para la Deuda
    descuento_base = obtener_descuento_base(deuda=deuda, portafolio=False)
    descuento_portafolio = obtener_descuento_base(deuda=deuda, portafolio=True)

    if pd.notna(descuento_portafolio): # Si no es NaN comparamos
        # Obtenemos las Deudas del Portafolio
        deudas_portafolio = obtener_deudas_portafolio_masivas(deuda=deuda)
        # Ahora Verificamos si todas las deudas del portafolio estan en la lista de deudas seleccionadas
        if all(d in deudas_info.keys() for d in deudas_portafolio):
            # Obtenemos el Valor Propuesto para dichas deudas
            valor_propuesto_portafolio = sum(deudas_info[d] for d in deudas_portafolio)
            # Comparamos con el Descuento Portafolio con el Valor Propuesto
            if valor_propuesto_portafolio > descuento_portafolio:
                return False, "El monto propuesto para las deudas {} es mayor al Pago en Portafolio actual de ${:,.0f}.".format(', '.join(deudas_portafolio), descuento_portafolio)

    # Siguiente: Comparación Individual de la Deuda con el Descuento Base
    if pd.notna(descuento_base): # Si no es NaN comparamos
        if monto_prop > descuento_base:
            return False, "El monto propuesto para la deuda {} es mayor al Pago Base actual de ${:,.0f}.".format(deuda, descuento_base)

    return True, "La deuda cumple con la restricción de ofertas menores a base."

# --- Respuestas de Formulario ---

# Clase Respuesta Formulario
class RespuestaFormulario:
    def __init__(self, *,
                correo: str,
                Referencia: str,
                Ids_Deuda: list[str],
                aliado_solicitud: 'Aliado',
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
        # Validamos que el Monto de Promesa de Depósito sea Mayor a 0 si Existe
        if self.monto_promesa_deposito and self.monto_promesa_deposito <= 0:
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