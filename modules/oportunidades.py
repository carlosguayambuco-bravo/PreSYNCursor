# Estándar usando Pep8
# Librerías de Python
from typing import Optional
# Librerías de Terceros
import pandas as pd
import streamlit as st
# Librerías Locales
from data.data_loader import load_actualizacines_negos, load_asignacion_cartera, load_headcount_negociacion, load_liquidaciones, load_pipeline_credito, load_prospectos_credito, load_prospectos_tradicional
from utils.helpers_general import replaceNaN

# Función Auxiliar para Obtener las Referencias habilitadas para calcular de forma individual
def obtener_referencias_habilitadas() -> list[str]:
    """
    Obtiene las Referencias que el usuario puede analizar en la calculadora.

    Reglas:
    - Admin: todas las Referencias de la Asignación.
    - Líder: sus Referencias y las de los negociadores de su equipo (columna ``Lider`` del Headcount).
    - Negociador: solo sus Referencias asignadas.
    - Si ``PERMITIR_CALCULO_NO_ASIGNADO`` está activo, se habilitan todas para cualquier rol.

    Returns:
        list[str]: Lista ordenada de Referencias habilitadas.
    """
    # Cargamos la Asignación de Cartera
    asignacion_df = load_asignacion_cartera()
    if asignacion_df.empty:
        st.warning("No se encontró la Asignación de Cartera. Contacta al administrador.", icon="⚠️")
        return []

    # Verificamos si está completamente habilitado desde los secretos
    try:
        permitir_no_asignado = st.secrets.get("PERMITIR_CALCULO_NO_ASIGNADO", False)
    except Exception:
        permitir_no_asignado = False

    if permitir_no_asignado:
        return sorted(asignacion_df["Referencia"].dropna().unique().tolist())

    # Paso 1: Obtener el Rol y el Correo del Usuario Actual
    user_obj = st.session_state.get("user_obj", None)
    user_role = getattr(user_obj, "role", None) or st.session_state.get("user_role", None)
    correo_usuario_actual = st.session_state.get("user_email", None)

    # Paso 2: El Admin puede ver todas las Referencias
    if user_role == "admin":
        return sorted(asignacion_df["Referencia"].dropna().unique().tolist())

    if not correo_usuario_actual:
        st.warning("No se encontró el correo del usuario en la sesión.", icon="⚠️")
        return []

    # Paso 3: Obtener el Nombre del Usuario según el HC
    hc_df = load_headcount_negociacion()
    nombre_usuario_actual = hc_df.loc[hc_df["Correo"] == correo_usuario_actual, "Nombre"].values
    if len(nombre_usuario_actual) == 0:
        st.warning("No se encontró el nombre del usuario en el Headcount de Negociación.", icon="⚠️")
        return []
    nombre_usuario_actual = nombre_usuario_actual[0]

    # Paso 4: Definir los Nombres Visibles (propio + equipo si es líder)
    nombres_visibles = [nombre_usuario_actual]
    if user_role == "leader":
        nombre_lider = str(nombre_usuario_actual).strip().casefold()
        equipo_df = hc_df[
            hc_df["Lider"].astype(str).str.strip().str.casefold() == nombre_lider
        ]
        nombres_visibles.extend(equipo_df["Nombre"].dropna().unique().tolist())

    # Paso 5: Normalizar y Filtrar la Asignación por Negociador
    nombres_normalizados = {
        str(nombre).strip().casefold()
        for nombre in nombres_visibles
        if pd.notna(nombre)
    }
    mask_negociador = (
        asignacion_df["Negociador"].astype(str).str.strip().str.casefold().isin(nombres_normalizados)
    )
    referencias_habilitadas = asignacion_df.loc[mask_negociador, "Referencia"].dropna().unique().tolist()

    # Paso 6: Devolver las Referencias Habilitadas
    return sorted(referencias_habilitadas)

# Función Auxiliar para Obtener el DF de Asignación para una Referencia específica
def obtener_asignacion_para_referencia(referencia: str) -> pd.DataFrame:
    asignacion_df = load_asignacion_cartera()
    asignacion_referencia_df = asignacion_df.loc[asignacion_df["Referencia"] == referencia]
    return asignacion_referencia_df

# Función Auxiliar para Obtener el Pricing de una Referencia
def obtener_pricing_para_referencia(referencia: str) -> float:
    asignacion_df = load_asignacion_cartera()
    pricing_values = asignacion_df.loc[asignacion_df["Referencia"] == referencia, "Pricing"].values
    if len(pricing_values) == 0:
        return 0.15
    return float(pricing_values[0])

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
def obtener_ultima_actualizacion_deuda(id_deuda: str, fecha_min: Optional[pd.Timestamp] = None) -> str:
    """Función para Obtener la Última Actualización de una Deuda en el Mec

    Args:
        id_deuda (str): El Id de la Deuda que se desea consultar
        fecha_min (Optional[pd.Timestamp]): La Fecha Mínima para considerar la Última Actualización.
            Si la Última Actualización es menor a esta Fecha, se devuelve N/A. Si es None, no se filtra por fecha.

    Returns:
        str: La Última Actualización de la Deuda si es mayor a fecha_min, de lo contrario devuelve N/A.
        Para formatear los datos, se usa el siguiente formato:
        `**{Etiqueta_Act}** - **{Fecha_Act:%d/%m/%Y %X}** - **{Nombre}**`
    """
    # Paso 1: Traer el DF de las Actualizaciones
    actsDF = load_actualizacines_negos()
    # Si no se recibe fecha mínima, mostramos la última actualización disponible
    if fecha_min is None:
        fecha_min = pd.Timestamp.min
    # Paso 2: Filtrar por la Deuda y Ordenar por Fecha_Act Descendente
    deuda_acts = actsDF.loc[
        (actsDF["Id_Deuda"] == id_deuda) & (actsDF["Fecha_Act"] >= fecha_min)
    ].sort_values(by="Fecha_Act", ascending=False)
    # Paso 3: Verificar si hay Actualizaciones
    if deuda_acts.empty:
        return "N/A"
    # Paso 4: Crear el String formateado de la Última Actualización
    ultima_act = deuda_acts.iloc[0]
    string_ultima_act = "**{Etiqueta_Act}** - **{Fecha_Act:%d/%m/%Y %X}** - **{Nombre}**".format(
        Etiqueta_Act=ultima_act["Etiqueta_Act"],
        Fecha_Act=ultima_act["Fecha_Act"],
        Nombre=ultima_act["Nombre"],
    )
    return string_ultima_act

# Función Auxiliar para obtener el estado actual de un cliente en Crédito
def obtener_estado_actual_credito(*,referencia: str) -> tuple[str,bool,bool]:
    """Función para obtener el Estado actual del cliente en el Pipeline de Crédito

    Args:
        referencia (str): La Referencia a Analizar

    Returns:
        tuple[
        str,: Estado actual de Crédito
        bool,: Booleano para definir si ya rechazó el crédito
        bool: Booleano para definir si no Opta a Crédito
    ]
    """    
    # Paso 1: Obtener el DF del Pipeline de Crédito
    pipecredDF = load_pipeline_credito()
    # Paso 2: Filtrar por la Referencia
    pipecred_ref = pipecredDF[pipecredDF['Referencia'] == referencia]
    # Paso 3: Devolver los Estados
    if pipecred_ref.empty:
        return "🫠No se ha convertido en Opp de Crédito", False, False
    else:
        ref_row = pipecred_ref.iloc[0]
        return ref_row['Status_Credito'], ref_row['Rechazo_Credito'], ref_row['No_Opta_Credito']

# Función Auxiliar para Obtener los Estados de Liquidación de las Deudas
def obtener_estado_liquidacion_deudas(*, deudas: list[str]) -> dict[str,bool]:
    """Función para obtener el estado de liquidación a modo de booleano para deudas

    Args:
        deudas (list[str]): Lista de los Id de Deuda

    Returns:
        dict[str,bool]: Diccionario con Llave el Id de Deuda y valor si esta liquidada
    """    
    # Paso 1: Cargar las Liquidaciones
    liqsSet = load_liquidaciones()
    # Paso 2: Devolver el estado para cada deuda
    return {d: d in liqsSet for d in deudas}

# --- Cálculo de Oportunidades (Funciones para calcular Oportunidades) ---
# NOTA: Estas funciones son el esquema de cálculo. Aún no están implementadas.
# Las definiciones de negocio están en docs/OPORTUNIDADES_DETALLADO.md.
## -- Opps por Referencia
### - Depósito Extra

# Función Auxiliar para Obtener el Depósito Extra Necesario para Crédito
def oportunidad_dep_extra_credito(*, referencia: str, deudas: list[str]) -> float:
    raise NotImplementedError("Cálculo de Depósito Extra por Crédito pendiente de implementación.")

# Función Auxiliar para Obtener el Depósito Extra Necesario para Tradicional
def oportunidad_dep_extra_tradicional(*, referencia: str, deudas: list[str]) -> float:
    raise NotImplementedError("Cálculo de Depósito Extra por Tradicional pendiente de implementación.")

# Función Auxiliar para Obtener el Depósito Extra Necesario según el Tipo de Análisis
def oportunidad_dep_extra(*, referencia: str, deudas: list[str], es_opp_cred: bool) -> float:
    if es_opp_cred:
        return oportunidad_dep_extra_credito(referencia=referencia, deudas=deudas)
    return oportunidad_dep_extra_tradicional(referencia=referencia, deudas=deudas)

### - ContraOfertas Viables

# Función Auxiliar para Obtener la ContraOferta Viable para Crédito
def oportunidad_contraofertas_credito(*, referencia: str, deudas: list[str]) -> float:
    raise NotImplementedError("Cálculo de ContraOferta Viable por Crédito pendiente de implementación.")

# Función Auxiliar para Obtener la ContraOferta Viable para Tradicional
def oportunidad_contraofertas_tradicional(*, referencia: str, deudas: list[str]) -> float:
    raise NotImplementedError("Cálculo de ContraOferta Viable por Tradicional pendiente de implementación.")

# Función Auxiliar para Obtener la ContraOferta Viable según el Tipo de Análisis
def oportunidad_contraofertas(*, referencia: str, deudas: list[str], es_opp_cred: bool) -> float:
    if es_opp_cred:
        return oportunidad_contraofertas_credito(referencia=referencia, deudas=deudas)
    return oportunidad_contraofertas_tradicional(referencia=referencia, deudas=deudas)

### - Acuerdos para Robo

# Función Auxiliar para Obtener los Acuerdos para Robo por Crédito
def oportunidad_acuerdos_robo_credito(*, referencia: str, deudas: list[str]) -> float:
    raise NotImplementedError("Cálculo de Acuerdos para Robo por Crédito pendiente de implementación.")

# Función Auxiliar para Obtener los Acuerdos para Robo por Tradicional
def oportunidad_acuerdos_robo_tradicional(*, referencia: str, deudas: list[str]) -> float:
    raise NotImplementedError("Cálculo de Acuerdos para Robo por Tradicional pendiente de implementación.")

# Función Auxiliar para Obtener los Acuerdos para Robo según el Tipo de Análisis
def oportunidad_acuerdos_robo(*, referencia: str, deudas: list[str], es_opp_cred: bool) -> float:
    if es_opp_cred:
        return oportunidad_acuerdos_robo_credito(referencia=referencia, deudas=deudas)
    return oportunidad_acuerdos_robo_tradicional(referencia=referencia, deudas=deudas)

### - Liquidaciones Instantáneas

# Función Auxiliar para Obtener la Liquidación Instantánea por Crédito
def oportunidad_liq_insta_credito(*, referencia: str, deudas: list[str]) -> float:
    raise NotImplementedError("Cálculo de Liquidación Instantánea por Crédito pendiente de implementación.")

# Función Auxiliar para Obtener la Liquidación Instantánea por Tradicional
def oportunidad_liq_insta_tradicional(*, referencia: str, deudas: list[str]) -> float:
    raise NotImplementedError("Cálculo de Liquidación Instantánea por Tradicional pendiente de implementación.")

# Función Auxiliar para Obtener la Liquidación Instantánea según el Tipo de Análisis
def oportunidad_liq_insta(*, referencia: str, deudas: list[str], es_opp_cred: bool) -> float:
    if es_opp_cred:
        return oportunidad_liq_insta_credito(referencia=referencia, deudas=deudas)
    return oportunidad_liq_insta_tradicional(referencia=referencia, deudas=deudas)

### - IA Liquidadora
def oportunidad_ia_liquidadora(*, referencia: str, deudas: list[str]) -> float:
    """Oportunidad basada en la probabilidad de liquidación de Prospectos de Tradicional."""
    raise NotImplementedError("Cálculo de IA Liquidadora pendiente de implementación.")