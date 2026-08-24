# Estándar usando Pep8
# Librerías de Python
from __future__ import annotations
from typing import Optional
# Librerías de Terceros
import numpy as np
import pandas as pd
from pandera.typing import DataFrame
import streamlit as st
# Librerías Locales
from data.data_loader import load_app_config, load_cartera_backup, load_client_balances, load_headcount_negociacion, load_pab_ideal, load_masivas, load_addendums
from data.data_models import DeudasActivasSchema
from services.metabase import MetabaseService
from utils.helpers_general import getBDDaysDiffFloat, imputeNans, parsePercentage
from modules.bank_normalizer import normalizar_banco
from modules.constants import IVA, HOUR_WAIT, DEFAULT_DISCOUNT_PL, QUERY_ACTIVE_DEBTS, QUERY_DEBT_TO_REFERENCE, QUERY_LAST_UPDATE, QUERY_LAST_UPDATE

# Función Auxiliar para Obtener el Descuento Óptimo para una Referencia por pago Tradicional
def obtener_descuento_optimo_tradicional(*,referencia: str, pricing: float, pago_total_original: float, descuento_pl: float):
    # Paso 1: Obtener el Ahorro y el Por Cobrar de la Referencia
    saldosDict = load_client_balances()
    ahorro = saldosDict['Saldos'][referencia]
    por_cobrar = saldosDict['PorCobrar'][referencia]

    # Paso 2: Calcular el Descuento Óptimo
    descuento_optimo = (ahorro - por_cobrar - pago_total_original) / (pago_total_original * (pricing * IVA - 1) )

    # Paso 3: Devolver el Descuento Óptimo con Piso descuento_pl y techo 1
    return min(max(descuento_optimo, descuento_pl), 1)

# Función Auxiliar para Obtener el Descuento Óptimo para una Referencia por Pago Crédito
def obtener_descuento_optimo_credito(*,referencia: str, deudas: list[str], pago_total_original: float):
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
    descuento_optimo = (pago_total_original - montoIdeal - (ahorro - por_cobrar)) / (pago_total_original )

    # Paso 4: Devolver el Descuento Óptimo con Techo 1
    return max(min(descuento_optimo, 1),0.15)

# Función para Obtener el Descuento Óptimo General para una Referencia, según el Tipo de Liquidación
def obtener_descuento_optimo(*,referencia: str, deudas: list[str], pricing: float, pago_total_original: float, descuento_pl: float) -> tuple[float, str]:
    descuento_trad = obtener_descuento_optimo_tradicional(referencia=referencia, pricing=pricing, pago_total_original=pago_total_original, descuento_pl=descuento_pl)
    descuento_cred = obtener_descuento_optimo_credito(referencia=referencia, deudas=deudas, pago_total_original=pago_total_original)
    return min(descuento_trad, descuento_cred), "Tradicional" if descuento_trad <= descuento_cred else "Crédito - PaB Ideal"

# Función para Definir si ya cumple la Condición de Actualización de Deudas
def cumple_condicion_actualizacion_deudas(*,ultima_actualizacion: pd.Timestamp) -> tuple[bool, float]:
    # Obtenemos la Fecha Actual Normalizada a Hoy (Sin Hora)
    fecha_actual = pd.Timestamp.now('America/Bogota').normalize().tz_localize(None)
    # Obtenemos la Diferencia en Días Hábiles entre Hoy y la Última Actualización
    dias_habiles_diff = getBDDaysDiffFloat(firstDate=ultima_actualizacion, secondDate=fecha_actual)
    # Traemos la Configuracion de la Aplicacion
    appConfig = load_app_config()
    # Veriticamos que satisface la Condición de Mínimo de Días Hábiles para Actualización
    return dias_habiles_diff <= float(appConfig['MIN_NECESSARY_DAYS_FOR_DEBT_UPDATE']), dias_habiles_diff

# Función Auxiliar para Obtener las Deudas del Portafolio de Masivas
def obtener_deudas_portafolio_masivas(*,deuda: str) -> list[str]:
    # Paso 1: Cargamos las Masivas y los Cambios de Referencia
    masivas_df = load_masivas()

    # Paso 2: Buscamos la Deuda en las Masivas
    masiva_row = masivas_df[(masivas_df['Id_Deuda'] == deuda) & (masivas_df['PaB_Portafolio'].notna())]
    if not masiva_row.empty:
        # Obtenemos la Referencia y la Casa de Cobro
        ref_deuda = masiva_row['Referencia'].iloc[0] # type: ignore
        casa_cobro = masiva_row['Casa_Cobro'].iloc[0] # type: ignore
        # Ahora buscamos todas las Deudas con la misma Referencia y la misma Casa de Cobro que tengan PaB_Portafolio no nulo
        deudas_portafolio = masivas_df[(masivas_df['Referencia'] == ref_deuda) & (masivas_df['Casa_Cobro'] == casa_cobro) & (masivas_df['PaB_Portafolio'].notna())]['Id_Deuda'].tolist() # type: ignore
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
def validar_descuento_base(*, deuda: str, deudas_info: dict[str, float]) -> tuple[bool, str]:
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
        if deudas_info[deuda] > descuento_base:
            return False, "El monto propuesto para la deuda {} es mayor al Pago Base actual de ${:,.0f}.".format(deuda, descuento_base)

    return True, "La deuda cumple con la restriccion de ofertas menores a base."

# Función para Obtener el Nombre del Negociador dado el Email
def obtener_nombre_negociador(*, email: str, full_name: bool = True) -> str:
    # Paso 1: Obtener los Datos del Headcount
    headcount_df = load_headcount_negociacion()
    # Paso 2: Filtrar el DataFrame por el Email
    negociador_row = headcount_df[headcount_df['Correo'] == email]

    # Paso 3: Devolver el Nombre del Negociador si Existe, de lo Contrario Devolver 'No Encontrado'
    if not negociador_row.empty:
        nombre_completo = negociador_row['Nombre'].values[0] # type: ignore

        if full_name:
            return nombre_completo # type: ignore

        # Ahora Vamos a dejar solo el Primer Nombre y el Primer Apellido
        nombre_partes = nombre_completo.split() # type: ignore
        if len(nombre_partes) >= 4:
            return "{} {}".format(nombre_partes[0], nombre_partes[2])
        else:
            return nombre_completo # type: ignore

    return "No Encontrado"

def obtener_correo_lider_negociador(*, email: str) -> Optional[str]:
    # Paso 1: Obtener los Datos del Headcount
    headcount_df = load_headcount_negociacion()
    # Paso 2: Filtrar el DataFrame por el Email
    negociador_row = headcount_df[headcount_df['Correo'] == email]
    if negociador_row.empty:
        return None

    # Obtenemos el nombre del líder
    lider_name = negociador_row['Lider'].values[0]
    # Buscamos el Lider ahora
    lider_row = headcount_df[headcount_df['Nombre'] == lider_name]
    if lider_row.empty:
        return None
    # Si existe la Fila entonces devolvemos el Correo
    return str(lider_row['Correo'].values[0])

# Función para Obtener el Aliado en Base dado un Conjunto de Deudas y Aliados Posibles
def obtener_aliado_en_base(*, deudas: list[str], aliados_posibles: list[str]) -> str:
    # Paso 1: Cargamos las Masivas
    masivas_df = load_masivas()
    # Paso 2: Buscamos las Deudas en las Masivas
    masivas_locales = masivas_df[masivas_df['Id_Deuda'].isin(deudas)]
    # Paso 3: Filtramos por los Aliados Posibles
    masivas_filtradas = masivas_locales[masivas_locales['Casa_Cobro'].isin(aliados_posibles)]
    # Paso 4: Hacemos un Agrupamiento por Casa de Cobro para dejar el Minimo PaB_Propuesta
    aliado_en_base = masivas_filtradas.groupby('Casa_Cobro')['PaB_Propuesta'].min().idxmin() # type: ignore
    return str(aliado_en_base)

# Función Auxiliar para Mostrar como subir la Solicitud de Aliados Diferentes
def mostrar_como_subir_solicitud_aliados_diferentes(*, ml: pd.DataFrame, es_admin: bool = False) -> None:
    # ml es Masivas Locales
    # Primero vamos a crear el Body de la Información
    body_info = [
        "{}: Deudas {}".format(
            casa if es_admin else "Aliado {}".format(i+1),
            '-'.join(ml[ml['Casa_Cobro'] == casa]['Id_Deuda'].tolist())
        ) for i, casa in enumerate(ml['Casa_Cobro'].unique())
    ]
    # Ahora Mostramos la Información en un st.info
    st.info(
        title="Información de Subida de Solicitud con Aliados Diferentes",
        body="Para subir la solicitud, debes crear una solicitud por cada aliado diferente. La información de las deudas por aliado es la siguiente:\n\n{}".format(
            "\n\n".join(body_info)
        ),
        icon="ℹ️"
    )

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

@st.cache_data(ttl=HOUR_WAIT, show_spinner="Buscando Deudas Activas de esa Referencia", max_entries = 100,)
def obtener_deudas_activas_con_retry(*, referencia: str) -> DataFrame[DeudasActivasSchema]:
    """
    Función principal que intenta obtener las Deudas Activas desde Metabase.
    Si la consulta falla, se cargan las Deudas Activas desde la Cartera Backup.
    """
    try:
        # Intentamos obtener los datos desde Metabase
        return obtener_deudas_activas(referencia=referencia)
    except LookupError:
        # Si la consulta a Metabase falla, cargamos la Cartera Backup
        st.warning('Berex no se encuentra disponible, cargando la Cartera Backup', icon="⚠️")

        # Paso 1: Cargamos la Cartera Backup (Contiene la info de todos los clientes)
        backup_df = load_cartera_backup()

        # Paso 2: Filtramos la Cartera Backup por la Referencia dada
        deudas_backup_df = backup_df[backup_df['Referencia'] == referencia]

        # Paso 3: Devolvemos el DataFrame con las Deudas Activas desde la Cartera Backup
        return deudas_backup_df

# Función Auxiliar para Obtener las Deudas Activas de una Referencia
def obtener_deudas_activas(*,referencia: str) -> DataFrame[DeudasActivasSchema]:
    # Paso 1: Obtener El Servicio de Metabase
    metabase_service: MetabaseService = st.session_state["metabase_service"]
    # Paso 2: Obtener los Datos de la Consulta SQL para Obtener las Deudas Activas
    query = QUERY_ACTIVE_DEBTS.format(referencia=referencia)
    # Paso 3: Obtener las Deudas Activas desde Metabase
    deudas_df = metabase_service.execute_query(query)

    if deudas_df.empty:
        # Si el DataFrame está vacío, devolvemos un DataFrame vacío con el esquema
        return DeudasActivasSchema.empty()

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
    # Volvemos Numero_Credito a String usando astype
    deudas_df['Numero_Credito'] = deudas_df['Numero_Credito'].astype(str)

    # Importante: Normalizamos los Bancos
    deudas_df['Banco'] = deudas_df['Banco'].apply(normalizar_banco)

    # Validamos el DF con el esquema
    deudas_df = DeudasActivasSchema.validate(deudas_df)

    # Paso 5: Devolver el DataFrame de Deudas Activas
    return deudas_df

# Función Auxiliar para Obtener la Última Actualización entre todas las deudas dadas
@st.cache_data(ttl=HOUR_WAIT, show_spinner="Buscando Última Actualización de esas Deudas", max_entries = 500,)
def obtener_ultima_actualizacion_deudas(*,debt_ids: list[str], user_email: str) -> pd.Timestamp:
    # Paso 1: Obtener El Servicio de Metabase
    metabase_service: MetabaseService = st.session_state["metabase_service"]

    # Paso 2: Obtener los Datos de la Consulta SQL para Obtener la Última Actualización
    query = QUERY_LAST_UPDATE.format(debt_ids=','.join(debt_ids), email=user_email)

    # Paso 3: Obtener las Últimas Actualizaciones desde Metabase
    ultima_actualizacion_df = metabase_service.execute_query(query)

    if ultima_actualizacion_df.empty:
        return pd.Timestamp.now('America/Bogota').normalize() - pd.Timedelta(days=100) # Devolvemos una Fecha de 100 Días Atrás si No Hay Actualizaciones

    # Paso 4: -- Limpieza de Datos --
    # Volvemos la Columna Id_Deuda a String y Eliminamos los Valores Nulos
    ultima_actualizacion_df.dropna(subset=['Id_Deuda'], inplace=True)
    ultima_actualizacion_df['Id_Deuda'] = ultima_actualizacion_df['Id_Deuda'].apply(lambda x: str(x).replace(".0", "").strip())
    # Volvemos la Columna Ultima_Actualizacion a Timestamp (Quitando Zona Horaria)
    ultima_actualizacion_df['Ultima_Actualizacion'] = pd.to_datetime(ultima_actualizacion_df['Ultima_Actualizacion'], errors='coerce', utc=True ).dt.tz_convert('America/Bogota').dt.tz_localize(None)

    # Paso 5: Devolver la Última Actualización como el Máximo de la Columna Ultima_Actualizacion
    if not ultima_actualizacion_df.empty:
        return ultima_actualizacion_df['Ultima_Actualizacion'].max()
    return pd.Timestamp.now('America/Bogota').normalize() - pd.Timedelta(days=100) # Devolvemos una Fecha de 30 Días Atrás si No Hay Actualizaciones