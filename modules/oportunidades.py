# Estándar usando Pep8
# Librerías de Python
# Librerías de Terceros
import pandas as pd
import streamlit as st
# Librerías Locales
from data.data_loader import load_actualizacines_negos, load_asignacion_cartera, load_headcount_negociacion, load_prospectos_credito, load_prospectos_tradicional
from utils.helpers_general import replaceNaN

# Función Auxiliar para Obtener las Referencias habilitadas para calcular de forma individual
def obtener_referencias_habilitadas() -> list[str]:
    # Cargamos la Asignación de Cartera
    asignacion_df = load_asignacion_cartera()
    # Verificamos si esta completamente habilitado desde los secretos
    if st.secrets.get("PERMITIR_CALCULO_NO_ASIGNADO",False):
        # Devolvemos todas las Referencias Habilitadas
        return list(asignacion_df["Referencia"].unique())

    # Paso 1: Obtener el Correo del Usuario Actual
    correo_usuario_actual = st.session_state.get("user_email", None)
    # Paso 2: Obtener el Nombre del Usuario según el HC
    hc_df = load_headcount_negociacion()
    nombre_usuario_actual = hc_df.loc[hc_df["Correo"] == correo_usuario_actual, "Nombre"].values
    if len(nombre_usuario_actual) == 0:
        st.warning("No se encontró el nombre del usuario en el Headcount de Negociación.")
        return []
    nombre_usuario_actual = nombre_usuario_actual[0]
    # Paso 3: Traer la Asignación de Cartera y Obtener las Referencias Habilitadas
    referencias_habilitadas = asignacion_df.loc[
        asignacion_df["Negociador"] == nombre_usuario_actual,
        "Referencia"
    ].unique()
    # Paso 4: Devolver las Referencias Habilitadas
    return list(referencias_habilitadas)

# Función Auxiliar para Obtener el DF de Asignación para una Referencia específica
def obtener_asignacion_para_referencia(referencia: str) -> pd.DataFrame:
    asignacion_df = load_asignacion_cartera()
    asignacion_referencia_df = asignacion_df.loc[asignacion_df["Referencia"] == referencia]
    return asignacion_referencia_df

# Función Auxiliar para Obtener el Pricing de una Referencia
def obtener_pricing_para_referencia(referencia: str) -> float:
    asignacion_df = load_asignacion_cartera()
    pricing_ref = asignacion_df.loc[asignacion_df["Referencia"] == referencia,"Pricing"].values[0]
    return pricing_ref

# Función Auxiliar para Obtener el Prospecto de Crédito de la Referencia
def obtener_prospecto_credito_para_referencia(referencia: str) -> str:
    # Primero cargamos los Prospectos de Crédito
    prospCredDict = load_prospectos_credito()
    # Devolvemos el Prospecto
    return prospCredDict[referencia]

# Función Auxiliar para Obtener el Máximo Prospecto Tradicional para una Referencia
def obtener_prospecto_tradicional_para_referencia(referencia: str) -> str:
    # Primero cargamos el DF de los Prospectos de Tradicional
    prosp_df = load_prospectos_tradicional()
    # Ahora filtramos por la Referencia y que exista el Prospecto
    prosp_ref = prosp_df[(prosp_df['Referencia'] == referencia) & (prosp_df['Prospecto'].notna())]
    # Si el DF esta vacío se devuelve ""
    if prosp_ref.empty:
        return "N/A"
    # Ordenamos los Datos por Prospecto
    prosp_ref = prosp_ref.sort_values(by='Prospecto',ascending=True)
    # Devolvemos el Primer Prospecto
    return prosp_ref['Prospecto'].values[0]

# Función Auxiliar para Obtener el Máximo Prospecto Tradicional para una Referencia
def obtener_prospecto_tradicional_para_deuda(deuda: str) -> str:
    # Primero cargamos el DF de los Prospectos de Tradicional
    prosp_df = load_prospectos_tradicional()
    # Ahora filtramos por la Id_Deuda
    prosp_debt = prosp_df[prosp_df['Id_Deuda'] == deuda]
    # Si no hay datos se devuelve ""
    if prosp_debt.empty:
        return "N/A"
    # Obtenemos el Primer Registro
    prosp_debt = prosp_debt.iloc[0]
    # Devolvemos el Prospecto reemplazando NaNs por ""
    return replaceNaN(value = prosp_debt['Prospecto'], nan_replace="")

# Función Auxiliar para Obtener la Última Actualización de una Deuda
def obtener_ultima_actualizacion_deuda(id_deuda: str, fecha_min: pd.TimedeltaIndex) -> str:
    """Función para Obtener la Última Actualización de una Deuda en el Mec

    Args:
        id_deuda (str): El Id de la Deuda que se desea consultar
        fecha_min (pd.TimedeltaIndex): La Fecha Mínima para considerar la Última Actualización. Si la Última Actualización es menor a esta Fecha, se devuelve None.

    Returns:
        str: La Última Actualización de la Deuda si es mayor a fecha_min, de lo contrario devuelve N/A.
        Para formatear los datos, se usa el siguiente formato:
        `**{Etiqueta_Act}** - **{Fecha_Act:%d/%m/%Y %X}** - **{Origen_Act}**`
    """    
    # Paso 1: Traer el DF de las Actualizaciones
    actsDF = load_actualizacines_negos()
    # Paso 2: Filtrar por la Deuda y Ordenar por Fecha_Act Descendente
    deuda_acts = actsDF.loc[(actsDF["Id_Deuda"] == id_deuda) & (actsDF["Fecha_Act"] >= fecha_min)].sort_values(by="Fecha_Act", ascending=False)
    # Paso 3: Verificar si hay Actualizaciones
    if deuda_acts.empty:
        return "N/A"
    # Paso 4: Crear el String formateado de la Última Actualización
    ultima_act = deuda_acts.iloc[0]
    string_ultima_act = "**{Etiqueta_Act}** - **{Fecha_Act:%d/%m/%Y %X}** - **{Origen_Act}**".format(
        Etiqueta_Act=ultima_act["Etiqueta_Act"],
        Fecha_Act=ultima_act["Fecha_Act"],
        Origen_Act=ultima_act["Origen_Act"]
    )
    return string_ultima_act

# --- Cálculo de Oportunidades (Funciones para calcular Oportunidades) ---
## -- Opps por Referencia
### - Depósito Extra

# Función Auxiliar para Obtener el Depósito Extra Necesario para Crédito
def oportunidad_dep_extra_credito(*,referencia: str, deudas: list[str]) -> float:
    pass

# Función Auxiliar para Obtener el Depósito Extra Necesario para Tradicional
def oportunidad_dep_extra_tradicional(*,referencia: str, deudas: list[str]) -> float:
    pass

# Función Auxiliar para Obtener el Depósito Extra Necesario según el Tipo de Análisis
def oportunidad_dep_extra_tradicional(*,referencia: str, deudas: list[str], es_opp_cred: bool):
    if es_opp_cred:
        return oportunidad_dep_extra_credito(referencia=referencia, deudas=deudas)
    else:
        return oportunidad_dep_extra_tradicional(referencia=referencia, deudas=deudas)

### - ContraOfertas Viables

# Función Auxiliar para Obtener el Depósito Extra Necesario para Crédito
def oportunidad_contraofertas_credito(*,referencia: str, deudas: list[str]) -> float:
    pass

# Función Auxiliar para Obtener el Depósito Extra Necesario para Tradicional
def oportunidad_contraofertas_tradicional(*,referencia: str, deudas: list[str]) -> float:
    pass

# Función Auxiliar para Obtener el Depósito Extra Necesario según el Tipo de Análisis
def oportunidad_contraofertas_tradicional(*,referencia: str, deudas: list[str], es_opp_cred: bool):
    if es_opp_cred:
        return oportunidad_contraofertas_credito(referencia=referencia, deudas=deudas)
    else:
        return oportunidad_contraofertas_tradicional(referencia=referencia, deudas=deudas)

### - Acuerdos para Robo

# Función Auxiliar para Obtener el Depósito Extra Necesario para Crédito
def oportunidad_acuerdos_robo_credito(*,referencia: str, deudas: list[str]) -> float:
    pass

# Función Auxiliar para Obtener el Depósito Extra Necesario para Tradicional
def oportunidad_acuerdos_robo_tradicional(*,referencia: str, deudas: list[str]) -> float:
    pass

# Función Auxiliar para Obtener el Depósito Extra Necesario según el Tipo de Análisis
def oportunidad_acuerdos_robo_tradicional(*,referencia: str, deudas: list[str], es_opp_cred: bool):
    if es_opp_cred:
        return oportunidad_acuerdos_robo_credito(referencia=referencia, deudas=deudas)
    else:
        return oportunidad_acuerdos_robo_tradicional(referencia=referencia, deudas=deudas)

### - Liquidaciones Instantáneas

# Función Auxiliar para Obtener el Depósito Extra Necesario para Crédito
def oportunidad_liq_insta_credito(*,referencia: str, deudas: list[str]) -> float:
    pass

# Función Auxiliar para Obtener el Depósito Extra Necesario para Tradicional
def oportunidad_liq_insta_tradicional(*,referencia: str, deudas: list[str]) -> float:
    pass

# Función Auxiliar para Obtener el Depósito Extra Necesario según el Tipo de Análisis
def oportunidad_liq_insta_tradicional(*,referencia: str, deudas: list[str], es_opp_cred: bool):
    if es_opp_cred:
        return oportunidad_liq_insta_credito(referencia=referencia, deudas=deudas)
    else:
        return oportunidad_liq_insta_tradicional(referencia=referencia, deudas=deudas)

### - IA Liquidadora
# Función Auxiliar para Obtener el Depósito Extra Necesario según el Tipo de Análisis
def oportunidad_liq_insta_tradicional(*,referencia: str, deudas: list[str], es_opp_cred: bool):
    pass