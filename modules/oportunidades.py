# Estándar usando Pep8
# Librerías de Python
from typing import Any, Optional
# Librerías de Terceros
import numpy as np
import pandas as pd
import streamlit as st
# Librerías Locales
from data.data_loader import (
    load_actualizacines_negos,
    load_asignacion_cartera,
    load_client_balances,
    load_headcount_negociacion,
    load_liquidaciones,
    load_masivas,
    load_pab_ideal,
    load_pipeline_credito,
    load_prospectos_credito,
    load_prospectos_tradicional,
    load_solicitudes_mec,
    obtener_fecha_expiracion_acuerdo,
)
from modules.constants import (
    ETIQUETAS_ACT_CONFIABLES,
    IVA,
    MARGEN_DESCUENTO_ESPERADO,
    MONTO_ADICIONAL_DEPOSITO,
    OPORTUNIDADES,
    UMBRAL_CONTRACOFERTA_MAXIMA,
    UMBRAL_DEPOSITO_EXTRA_APARTADOS,
    UMBRAL_DEPOSITO_EXTRA_MONTO,
    UMBRAL_PROB_LIQ_IA,
)
from utils.helpers_general import replaceNaN

# Función Auxiliar para Normalizar un Id de Deuda
def _normalizar_id_deuda(valor: Any) -> str:
    """Normaliza un Id de Deuda a String, sin espacios y sin el sufijo ``.0``.

    Args:
        valor (Any): Valor a normalizar.

    Returns:
        str: Id de Deuda normalizado.
    """
    if valor is None:
        return ""
    try:
        if pd.isna(valor):
            return ""
    except (TypeError, ValueError):
        pass
    id_deuda = str(valor).strip()
    if id_deuda.endswith(".0"):
        id_deuda = id_deuda[:-2]
    return id_deuda

# Función Auxiliar para Convertir un Valor a Float
def _a_float(valor: Any, default: float = 0.0) -> float:
    """Convierte un valor a Float, devolviendo ``default`` si no es numérico."""
    try:
        numero = pd.to_numeric(valor, errors="coerce")
    except (TypeError, ValueError):
        return default
    if pd.isna(numero):
        return default
    return float(numero)

# Función Auxiliar para Convertir un Valor a Timestamp sin Zona Horaria
def _a_timestamp(valor: Any) -> Optional[pd.Timestamp]:
    """Convierte un valor a Timestamp de Bogotá sin zona horaria."""
    if valor is None:
        return None
    try:
        if pd.isna(valor):
            return None
    except (TypeError, ValueError):
        pass
    try:
        fecha = pd.Timestamp(valor)
    except (TypeError, ValueError):
        return None
    if pd.isna(fecha):
        return None
    # Quitamos la zona horaria para comparar con las fechas de Sheets
    if fecha.tzinfo is not None:
        fecha = fecha.tz_convert("America/Bogota").tz_localize(None)
    return fecha

# Función Auxiliar para Normalizar una Columna de Fechas
def _normalizar_columna_fechas(serie: pd.Series) -> pd.Series:
    """Convierte una columna a Timestamp sin zona horaria de Bogotá."""
    serie = pd.to_datetime(serie, errors="coerce")
    if getattr(serie.dt, "tz", None) is not None:
        serie = serie.dt.tz_convert("America/Bogota").dt.tz_localize(None)
    return serie

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

# --- Funciones Auxiliares de Datos para las Oportunidades ---
def _obtener_solicitudes_mec_calculo() -> pd.DataFrame:
    """Obtiene las solicitudes del MEC evitando recargar el caché desde un cálculo."""
    try:
        solicitudes_df = st.session_state.get("solicitudes_mec_df")
    except Exception:
        solicitudes_df = None
    if isinstance(solicitudes_df, pd.DataFrame):
        return solicitudes_df
    return load_solicitudes_mec()

def _obtener_pab_ideal_deuda(deuda: str) -> float:
    """Obtiene el PaB Ideal de Crédito de una deuda."""
    pab_ideal_dict = load_pab_ideal()
    return max(_a_float(pab_ideal_dict.get(_normalizar_id_deuda(deuda), 0.0)), 0.0)

def _obtener_pab_origen_deuda(deuda: str) -> float:
    """Obtiene el PaB_Origen de una deuda desde la Asignación de Cartera."""
    asignacion_df = load_asignacion_cartera()
    if asignacion_df.empty:
        return 0.0
    deuda_norm = _normalizar_id_deuda(deuda)
    fila = asignacion_df[
        asignacion_df["Id_Deuda"].apply(_normalizar_id_deuda) == deuda_norm
    ]
    if fila.empty:
        return 0.0
    return max(_a_float(fila.iloc[0]["PaB_Origen"]), 0.0)

def _obtener_df_deudas_seleccionadas(*, referencia: str, deudas: list[str]) -> pd.DataFrame:
    """Filtra la Asignación de Cartera por las deudas seleccionadas."""
    asignacion_df = obtener_asignacion_para_referencia(referencia).copy()
    if asignacion_df.empty:
        return asignacion_df
    asignacion_df["Id_Deuda"] = asignacion_df["Id_Deuda"].apply(_normalizar_id_deuda)
    deudas_normalizadas = {_normalizar_id_deuda(d) for d in deudas}
    return asignacion_df[asignacion_df["Id_Deuda"].isin(deudas_normalizadas)].copy()

def _etiqueta_es_confiable(etiqueta: Any) -> bool:
    """Valida si una etiqueta de actualización es confiable para el Descuento Actual."""
    return str(etiqueta).strip().upper() in ETIQUETAS_ACT_CONFIABLES

def _fecha_limite_uso_masiva(metadata: Any) -> Optional[pd.Timestamp]:
    """Obtiene la fecha de la metadata de un descuento en base."""
    if not isinstance(metadata, dict):
        return None
    return _a_timestamp(metadata.get("Fecha_Limite_Uso"))

def _extraer_monto_deuda_solicitud(*, solicitud: pd.Series, id_deuda: str) -> Optional[float]:
    """Extrae el Monto_Propuesto de una deuda dentro de una solicitud."""
    for campo in ("JSON_Respuesta", "Datos_Solicitud"):
        deudas = solicitud.get(campo)
        if deudas is None:
            continue
        if isinstance(deudas, float) and pd.isna(deudas):
            continue
        if not isinstance(deudas, (list, tuple)):
            continue
        for deuda in deudas:
            if not isinstance(deuda, dict):
                continue
            if _normalizar_id_deuda(deuda.get("Id_Deuda")) != id_deuda:
                continue
            monto = deuda.get("Monto_Propuesto")
            if monto is None:
                continue
            monto_float = _a_float(monto, default=np.nan)
            if not pd.isna(monto_float):
                return monto_float
    return None

def _resolver_pab_actualizado_alianzas(
    *,
    id_deuda: str,
    pab_origen: float,
    fecha_actualizacion: Optional[pd.Timestamp],
    pab_actualizado_fila: float,
) -> float:
    """Resuelve el PaB_Actualizado de una actualización ACTUALIZADO_ALIANZAS.

    Se compara el último descuento en base (masivas) contra la última solicitud
    exitosa. Si ambas fuentes tienen fecha, prevalece la más reciente. Si no hay
    fechas comparables, se usa el valor de la fila de actualización.
    """
    candidatos = []

    # Paso 1: Último descuento en base (masivas)
    try:
        masivas_df = load_masivas()
    except Exception:
        masivas_df = pd.DataFrame()
    if not masivas_df.empty and "Id_Deuda" in masivas_df.columns:
        masivas_deuda = masivas_df[
            masivas_df["Id_Deuda"].apply(_normalizar_id_deuda) == id_deuda
        ]
        if not masivas_deuda.empty:
            # El orden del DF es la recencia: el último registro es el más reciente
            ultima_masiva = masivas_deuda.iloc[-1]
            candidatos.append({
                "fuente": "masivas",
                "pab": _a_float(ultima_masiva.get("PaB_Propuesta"), default=pab_actualizado_fila),
                "fecha": _fecha_limite_uso_masiva(ultima_masiva.get("Metadata")),
            })

    # Paso 2: Última solicitud exitosa que incluya la deuda
    try:
        solicitudes_df = _obtener_solicitudes_mec_calculo()
    except Exception:
        solicitudes_df = pd.DataFrame()
    if not solicitudes_df.empty and "Estado_Solicitud" in solicitudes_df.columns:
        solicitudes_exitosas = solicitudes_df[
            solicitudes_df["Estado_Solicitud"] == "Exitosa"
        ].copy()
        if "Fecha_Respuesta" in solicitudes_exitosas.columns:
            solicitudes_exitosas = solicitudes_exitosas.sort_values(
                by="Fecha_Respuesta", ascending=False, na_position="last"
            )
        for _, solicitud in solicitudes_exitosas.iterrows():
            monto = _extraer_monto_deuda_solicitud(
                solicitud=solicitud,
                id_deuda=id_deuda,
            )
            if monto is None:
                continue
            fecha_solicitud = _a_timestamp(solicitud.get("Fecha_Respuesta"))
            if fecha_solicitud is None:
                fecha_solicitud = _a_timestamp(solicitud.get("Timestamp"))
            candidatos.append({
                "fuente": "solicitud",
                "pab": monto,
                "fecha": fecha_solicitud,
            })
            break

    # Paso 3: Elegir el candidato más reciente
    if not candidatos:
        return max(pab_actualizado_fila, 0.0)

    candidatos_con_fecha = [c for c in candidatos if c["fecha"] is not None]
    if candidatos_con_fecha:
        candidatos_con_fecha.sort(key=lambda c: c["fecha"], reverse=True)
        return max(candidatos_con_fecha[0]["pab"], 0.0)

    # Sin fechas comparables, usamos el valor de la fila de actualización
    return max(pab_actualizado_fila, 0.0)

def obtener_pab_actualizado_deuda(id_deuda: str, pab_origen: Optional[float] = None) -> float:
    """Obtiene el PaB_Actualizado confiable de una deuda.

    Reglas:
    - Se toma la actualización más reciente.
    - Si su etiqueta no es confiable (CAMBIO DE PAB, ACUERDO, DEPOSITO o
      ACTUALIZADO_ALIANZAS), se usa ``PaB_Origen`` (Descuento Actual = 0).
    - Para ACTUALIZADO_ALIANZAS se cruza el último descuento en base y la última
      solicitud exitosa, prevaleciendo la fuente más reciente por fecha.

    Args:
        id_deuda (str): Id de la deuda.
        pab_origen (Optional[float]): PaB_Origen de la deuda. Si es None se busca
            en la Asignación de Cartera.

    Returns:
        float: PaB_Actualizado de la deuda.
    """
    deuda_norm = _normalizar_id_deuda(id_deuda)
    if pab_origen is None:
        pab_origen = _obtener_pab_origen_deuda(deuda_norm)
    pab_origen = max(_a_float(pab_origen), 0.0)

    # Paso 1: Traer las actualizaciones de la deuda
    try:
        acts_df = load_actualizacines_negos()
    except Exception:
        return pab_origen
    if acts_df.empty or "Id_Deuda" not in acts_df.columns:
        return pab_origen
    acts_deuda = acts_df[
        acts_df["Id_Deuda"].apply(_normalizar_id_deuda) == deuda_norm
    ].copy()
    if acts_deuda.empty:
        return pab_origen
    acts_deuda["Fecha_Act"] = _normalizar_columna_fechas(acts_deuda["Fecha_Act"])

    # Paso 2: Tomar la actualización más reciente
    acts_deuda = acts_deuda.sort_values(by="Fecha_Act", ascending=False)
    ultima_act = acts_deuda.iloc[0]
    if not _etiqueta_es_confiable(ultima_act.get("Etiqueta_Act")):
        return pab_origen

    # Paso 3: Resolver el valor de la actualización
    pab_fila = _a_float(ultima_act.get("PaB_Actualizado"), default=pab_origen)
    if str(ultima_act.get("Etiqueta_Act", "")).strip().upper() == "ACTUALIZADO_ALIANZAS":
        pab_fila = _resolver_pab_actualizado_alianzas(
            id_deuda=deuda_norm,
            pab_origen=pab_origen,
            fecha_actualizacion=_a_timestamp(ultima_act.get("Fecha_Act")),
            pab_actualizado_fila=pab_fila,
        )

    # Paso 4: Acotar el valor al rango válido
    if pab_origen > 0:
        return max(0.0, min(pab_fila, pab_origen))
    return max(pab_fila, 0.0)

def _fecha_limite_pago_alianza(
    *,
    solicitudes_df: pd.DataFrame,
    id_deuda: str,
) -> Optional[pd.Timestamp]:
    """Busca la Fecha_Limite_Pago de un acuerdo exitoso de Alianzas para una deuda."""
    if solicitudes_df.empty:
        return None
    columnas_requeridas = {"Estado_Solicitud", "Tipo_Solicitud", "Fecha_Limite_Pago"}
    if not columnas_requeridas.issubset(set(solicitudes_df.columns)):
        return None

    solicitudes_acuerdo = solicitudes_df[
        (solicitudes_df["Estado_Solicitud"] == "Exitosa")
        & (solicitudes_df["Tipo_Solicitud"].isin(["Acuerdo de Pago", "Oferta de Acuerdo"]))
        & (solicitudes_df["Fecha_Limite_Pago"].notna())
    ].copy()
    # Solo aplican acuerdos del MEC, no históricos
    if "Es_Historico" in solicitudes_acuerdo.columns:
        solicitudes_acuerdo = solicitudes_acuerdo[~solicitudes_acuerdo["Es_Historico"]]
    if solicitudes_acuerdo.empty:
        return None

    # Filtramos por la deuda, ya sea en Ids_Deuda o en los JSON de deudas
    def _contiene_deuda(row: pd.Series) -> bool:
        ids_deuda = str(row.get("Ids_Deuda", ""))
        if id_deuda in [x.strip() for x in ids_deuda.split("-")]:
            return True
        for campo in ("Datos_Solicitud", "JSON_Respuesta"):
            deudas = row.get(campo)
            if deudas is None:
                continue
            if isinstance(deudas, float) and pd.isna(deudas):
                continue
            if not isinstance(deudas, (list, tuple)):
                continue
            for deuda in deudas:
                if isinstance(deuda, dict) and _normalizar_id_deuda(deuda.get("Id_Deuda")) == id_deuda:
                    return True
        return False

    solicitudes_acuerdo = solicitudes_acuerdo[
        solicitudes_acuerdo.apply(_contiene_deuda, axis=1)
    ]
    if solicitudes_acuerdo.empty:
        return None

    # Ordenamos por la respuesta más reciente y tomamos la primera fecha válida
    columnas_orden = [c for c in ("Fecha_Respuesta", "Timestamp") if c in solicitudes_acuerdo.columns]
    if columnas_orden:
        solicitudes_acuerdo = solicitudes_acuerdo.sort_values(
            by=columnas_orden, ascending=False, na_position="last"
        )
    for _, solicitud in solicitudes_acuerdo.iterrows():
        fecha_limite = _a_timestamp(solicitud.get("Fecha_Limite_Pago"))
        if fecha_limite is not None:
            return fecha_limite
    return None

def obtener_acuerdos_robo(*, deudas: list[str]) -> dict[str, str]:
    """Obtiene los Acuerdos para Robo de un conjunto de deudas.

    Un acuerdo es oportunidad de robo si:
    1. La deuda tiene una actualización ACUERDO en el MEC.
    2. No tiene actualizaciones posteriores a esa fila ACUERDO.
    3. No está liquidada.
    4. Su fecha límite de pago ya venció (Alianzas o Metabase).

    Returns:
        dict[str, str]: Diccionario Id_Deuda -> fecha de vencimiento (o "Sin fecha").
    """
    try:
        acts_df = load_actualizacines_negos()
        liquidaciones_set = load_liquidaciones()
        solicitudes_df = _obtener_solicitudes_mec_calculo()
    except Exception:
        # Ante un error de datos, no se reportan acuerdos para robo
        return {}
    hoy = pd.Timestamp.now(tz="America/Bogota").tz_localize(None).normalize()
    acuerdos_robo = {}

    for deuda in deudas:
        deuda_norm = _normalizar_id_deuda(deuda)
        if not deuda_norm or deuda_norm in liquidaciones_set:
            continue
        if acts_df.empty or "Id_Deuda" not in acts_df.columns:
            continue

        acts_deuda = acts_df[
            acts_df["Id_Deuda"].apply(_normalizar_id_deuda) == deuda_norm
        ].copy()
        if acts_deuda.empty:
            continue
        acts_deuda["Fecha_Act"] = _normalizar_columna_fechas(acts_deuda["Fecha_Act"])

        # Paso 1: Buscar la actualización ACUERDO más reciente
        acts_acuerdo = acts_deuda[
            acts_deuda["Etiqueta_Act"].astype(str).str.upper().str.strip() == "ACUERDO"
        ]
        if acts_acuerdo.empty:
            continue
        acts_acuerdo = acts_acuerdo.sort_values(by="Fecha_Act", ascending=False)
        act_acuerdo = acts_acuerdo.iloc[0]
        fecha_acuerdo = _a_timestamp(act_acuerdo.get("Fecha_Act"))
        if fecha_acuerdo is None:
            continue

        # Paso 2: Descartar si hay gestión posterior a la actualización ACUERDO
        posteriores = acts_deuda[acts_deuda["Fecha_Act"] > fecha_acuerdo]
        if not posteriores.empty:
            continue

        # Paso 3: Buscar la fecha en Alianzas
        fecha_alianza = _fecha_limite_pago_alianza(
            solicitudes_df=solicitudes_df,
            id_deuda=deuda_norm,
        )
        if fecha_alianza is not None:
            if fecha_alianza.normalize() < hoy:
                acuerdos_robo[deuda_norm] = fecha_alianza.strftime("%d/%m/%Y")
            continue

        # Paso 4: Buscar la fecha en Metabase
        correo = str(act_acuerdo.get("Correo", "")).strip()
        if not correo or correo.lower() == "nan":
            continue
        fecha_meta = obtener_fecha_expiracion_acuerdo(debt_ids=[deuda_norm], end=correo)
        if fecha_meta is None:
            # Ante un error de Metabase no se considera oportunidad
            continue
        if pd.isna(fecha_meta):
            # Sin fecha, pero con datos: se considera para robo
            acuerdos_robo[deuda_norm] = "Sin fecha"
            continue
        fecha_meta = _a_timestamp(fecha_meta)
        if fecha_meta is not None and fecha_meta.normalize() < hoy:
            acuerdos_robo[deuda_norm] = fecha_meta.strftime("%d/%m/%Y")

    return acuerdos_robo

def obtener_probabilidades_ia_liquidadora(*, deudas: list[str]) -> dict[str, float]:
    """Obtiene las probabilidades de liquidación de los Prospectos de Tradicional."""
    try:
        prosp_df = load_prospectos_tradicional()
    except Exception:
        return {}
    if prosp_df.empty or "Id_Deuda" not in prosp_df.columns:
        return {}
    deudas_normalizadas = {_normalizar_id_deuda(d) for d in deudas}
    prosp_df = prosp_df.copy()
    prosp_df["Id_Deuda"] = prosp_df["Id_Deuda"].apply(_normalizar_id_deuda)
    prosp_df = prosp_df[prosp_df["Id_Deuda"].isin(deudas_normalizadas)]
    return {
        row["Id_Deuda"]: _a_float(row.get("Prob_Liq"))
        for _, row in prosp_df.iterrows()
    }

# --- Cálculo de Oportunidades (Funciones Puras) ---
def calcular_descuento_actual(
    *,
    pab_origen_total: float,
    pab_actualizado_total: float,
) -> float:
    """Calcula el Descuento Actual del conjunto de deudas.

    ``Descuento Actual = 1 - SUM(PaB_Actualizado) / SUM(PaB_Origen)``.

    Returns:
        float: Descuento entre 0 y 1. Si el PaB_Origen es 0, retorna 0.
    """
    pab_origen_total = max(_a_float(pab_origen_total), 0.0)
    if pab_origen_total <= 0:
        return 0.0
    pab_actualizado_total = max(_a_float(pab_actualizado_total), 0.0)
    descuento = 1 - (pab_actualizado_total / pab_origen_total)
    return min(max(descuento, 0.0), 1.0)

def calcular_descuento_esperado_ponderado(
    *,
    descuentos: list[float],
    pab_origen: list[float],
) -> float:
    """Calcula el Descuento_Esperado ponderado por PaB_Origen."""
    if not descuentos or not pab_origen:
        return 0.0
    pesos = [max(_a_float(p), 0.0) for p in pab_origen]
    total_pesos = sum(pesos)
    if total_pesos <= 0:
        return 0.0
    ponderado = sum(
        max(_a_float(d), 0.0) * peso
        for d, peso in zip(descuentos, pesos)
    )
    return ponderado / total_pesos

def calcular_apartado_neto_cliente(asignacion_df: pd.DataFrame) -> float:
    """Obtiene el Apartado_Neto del cliente como un único valor.

    ``Apartado_Neto`` es un dato del cliente que se repite por deuda en la
    Asignación. Para no sobrecontarlo, se toma el máximo de las filas.
    """
    if asignacion_df.empty or "Apartado_Neto" not in asignacion_df.columns:
        return 0.0
    valores = pd.to_numeric(asignacion_df["Apartado_Neto"], errors="coerce").dropna()
    if valores.empty:
        return 0.0
    return max(_a_float(valores.max()), 0.0)

def calcular_deposito_extra_credito(
    *,
    pab_ideal_total: float,
    pab_actualizado_total: float,
) -> float:
    """Calcula el Depósito Extra necesario para Crédito."""
    return (
        _a_float(pab_ideal_total)
        + MONTO_ADICIONAL_DEPOSITO
        - _a_float(pab_actualizado_total)
    )

def calcular_deposito_extra_tradicional(
    *,
    pab_origen_total: float,
    pab_actualizado_total: float,
    pricing: float,
    ahorro: float,
    por_cobrar: float,
) -> float:
    """Calcula el Depósito Extra necesario para Tradicional."""
    pab_origen_total = _a_float(pab_origen_total)
    pab_actualizado_total = _a_float(pab_actualizado_total)
    comision = max(
        (pab_origen_total - pab_actualizado_total) * _a_float(pricing) * IVA,
        0.0,
    )
    return (
        pab_actualizado_total
        + comision
        + MONTO_ADICIONAL_DEPOSITO
        - (_a_float(ahorro) - _a_float(por_cobrar))
    )

def calcular_contraoferta_credito(
    *,
    pab_ideal_total: float,
    pab_origen_total: float,
    deposito_extra: float = 0.0,
) -> float:
    """Calcula el descuento necesario para que el pago entre en el cupo de Crédito."""
    pab_origen_total = _a_float(pab_origen_total)
    if pab_origen_total <= 0:
        return 0.0
    return 1 - (
        (
            _a_float(pab_ideal_total)
            + MONTO_ADICIONAL_DEPOSITO
            + max(_a_float(deposito_extra), 0.0)
        )
        / pab_origen_total
    )

def calcular_contraoferta_tradicional(
    *,
    pab_origen_total: float,
    pricing: float,
    ahorro: float,
    por_cobrar: float,
    deposito_extra: float = 0.0,
) -> float:
    """Calcula el descuento necesario para pagar con el ahorro del cliente."""
    pab_origen_total = _a_float(pab_origen_total)
    denominador = pab_origen_total * (_a_float(pricing) * IVA - 1)
    if denominador == 0:
        return 0.0
    numerador = (
        _a_float(ahorro)
        + max(_a_float(deposito_extra), 0.0)
        - _a_float(por_cobrar)
        - pab_origen_total
        - MONTO_ADICIONAL_DEPOSITO
    )
    return numerador / denominador

def evaluar_deposito_extra(
    *,
    deposito_extra: float,
    apartado_neto: float,
) -> bool:
    """Evalúa si el Depósito Extra calculado es una oportunidad."""
    deposito_extra = _a_float(deposito_extra, default=np.nan)
    if pd.isna(deposito_extra) or deposito_extra < 0:
        return False
    apartado_neto = max(_a_float(apartado_neto), 0.0)
    if deposito_extra <= UMBRAL_DEPOSITO_EXTRA_MONTO:
        return True
    if apartado_neto <= 0:
        return False
    return (deposito_extra / apartado_neto) <= UMBRAL_DEPOSITO_EXTRA_APARTADOS

def evaluar_contraoferta(
    *,
    contraoferta: float,
    descuento_actual: float,
    descuento_esperado: float,
) -> bool:
    """Evalúa si la ContraOferta calculada es una oportunidad."""
    contraoferta = _a_float(contraoferta, default=np.nan)
    if pd.isna(contraoferta):
        return False
    return (
        contraoferta > _a_float(descuento_actual)
        and contraoferta <= UMBRAL_CONTRACOFERTA_MAXIMA
        and contraoferta <= _a_float(descuento_esperado) + MARGEN_DESCUENTO_ESPERADO
    )

def evaluar_liq_insta(
    *,
    descuento_actual: float,
    contraoferta: float,
    deposito_extra: float,
) -> bool:
    """Evalúa si el cliente ya puede liquidar de forma instantánea.

    Se cumple cuando el Descuento Actual es igual o mejor que la ContraOferta
    necesaria y existe un descuento, o cuando el Depósito Extra calculado es
    negativo (no se necesita depósito).
    """
    descuento_actual = _a_float(descuento_actual)
    if _a_float(deposito_extra) < 0:
        return True
    contraoferta = _a_float(contraoferta, default=np.nan)
    if pd.isna(contraoferta):
        return False
    return descuento_actual >= contraoferta and descuento_actual != 0

def evaluar_ia_liquidadora(*, probabilidades: list[float]) -> bool:
    """Evalúa si al menos una deuda supera el umbral de IA Liquidadora."""
    return any(_a_float(p) >= UMBRAL_PROB_LIQ_IA for p in probabilidades)

def evaluar_viabilidad_cliente(
    *,
    pab_total: float,
    pab_ideal_total: float,
    ingreso_total: float,
    ahorro: float,
    por_cobrar: float,
    deposito_extra: float = 0.0,
    es_opp_cred: bool = False,
) -> dict[str, Any]:
    """Evalúa la viabilidad del pago con el ahorro y/o el cupo de Crédito.

    - Tradicional: Pago Total (PaB + comisión con IVA + 20k) <= Ahorro + Depósito Extra - Por Cobrar.
    - Crédito: el PaB total debe caber en el PaB Ideal más los 20k restrictivos.
    """
    pab_total = _a_float(pab_total)
    pago_total = pab_total + (_a_float(ingreso_total) * IVA) + MONTO_ADICIONAL_DEPOSITO
    disponible_tradicional = (
        _a_float(ahorro)
        + max(_a_float(deposito_extra), 0.0)
        - _a_float(por_cobrar)
    )
    viable_tradicional = pago_total <= disponible_tradicional
    viable_credito = False
    if es_opp_cred and _a_float(pab_ideal_total) > 0:
        viable_credito = pab_total <= (_a_float(pab_ideal_total) + MONTO_ADICIONAL_DEPOSITO)
    return {
        "pago_total": pago_total,
        "disponible_tradicional": disponible_tradicional,
        "viable_tradicional": viable_tradicional,
        "viable_credito": viable_credito,
        "viable": viable_tradicional or viable_credito,
    }

# --- Cálculo de Oportunidades (Funciones de Datos) ---
def _resolver_saldos_cliente(
    *,
    referencia: str,
    ahorro: Optional[float],
    porcobrar: Optional[float],
) -> tuple[float, float]:
    """Resuelve el Ahorro y el Por Cobrar, usando los saldos oficiales si faltan."""
    if ahorro is None or porcobrar is None:
        saldos_dict = load_client_balances()
        if ahorro is None:
            ahorro = saldos_dict["Saldos"][referencia]
        if porcobrar is None:
            porcobrar = saldos_dict["PorCobrar"][referencia]
    return max(_a_float(ahorro), 0.0), max(_a_float(porcobrar), 0.0)

def _obtener_totales_deudas(*, referencia: str, deudas: list[str]) -> dict[str, Any]:
    """Calcula los totales y datos base de las deudas seleccionadas."""
    asignacion_df = _obtener_df_deudas_seleccionadas(referencia=referencia, deudas=deudas)
    pricing = obtener_pricing_para_referencia(referencia)
    if asignacion_df.empty:
        return {
            "asignacion": asignacion_df,
            "pab_origen_total": 0.0,
            "pab_actualizado_total": 0.0,
            "pab_ideal_total": 0.0,
            "descuento_esperado": 0.0,
            "apartado_neto": 0.0,
            "pricing": pricing,
            "deudas": [],
            "pab_origen_por_deuda": {},
            "pab_actualizado_por_deuda": {},
        }

    pab_origen_por_deuda = {}
    pab_actualizado_por_deuda = {}
    descuentos_esperados = []
    pab_origen_lista = []
    pab_ideal_total = 0.0

    for _, fila in asignacion_df.iterrows():
        deuda = _normalizar_id_deuda(fila["Id_Deuda"])
        pab_origen = max(_a_float(fila.get("PaB_Origen")), 0.0)
        pab_actualizado = obtener_pab_actualizado_deuda(deuda, pab_origen=pab_origen)
        pab_origen_por_deuda[deuda] = pab_origen
        pab_actualizado_por_deuda[deuda] = pab_actualizado
        pab_origen_lista.append(pab_origen)
        descuentos_esperados.append(_a_float(fila.get("Descuento_Esperado")))
        pab_ideal_total += _obtener_pab_ideal_deuda(deuda)

    return {
        "asignacion": asignacion_df,
        "pab_origen_total": sum(pab_origen_lista),
        "pab_actualizado_total": sum(pab_actualizado_por_deuda.values()),
        "pab_ideal_total": pab_ideal_total,
        "descuento_esperado": calcular_descuento_esperado_ponderado(
            descuentos=descuentos_esperados,
            pab_origen=pab_origen_lista,
        ),
        "apartado_neto": calcular_apartado_neto_cliente(asignacion_df),
        "pricing": pricing,
        "deudas": [_normalizar_id_deuda(d) for d in deudas],
        "pab_origen_por_deuda": pab_origen_por_deuda,
        "pab_actualizado_por_deuda": pab_actualizado_por_deuda,
    }

# --- Oportunidades por Referencia ---
### - Depósito Extra
def oportunidad_dep_extra_credito(
    *,
    referencia: str,
    deudas: list[str],
    ahorro: Optional[float] = None,
    porcobrar: Optional[float] = None,
    deposito_extra: float = 0.0,
) -> float:
    """Obtiene el Depósito Extra necesario para Crédito."""
    totales = _obtener_totales_deudas(referencia=referencia, deudas=deudas)
    if totales["pab_ideal_total"] <= 0:
        return 0.0
    return calcular_deposito_extra_credito(
        pab_ideal_total=totales["pab_ideal_total"],
        pab_actualizado_total=totales["pab_actualizado_total"],
    )

def oportunidad_dep_extra_tradicional(
    *,
    referencia: str,
    deudas: list[str],
    ahorro: Optional[float] = None,
    porcobrar: Optional[float] = None,
    deposito_extra: float = 0.0,
) -> float:
    """Obtiene el Depósito Extra necesario para Tradicional."""
    totales = _obtener_totales_deudas(referencia=referencia, deudas=deudas)
    ahorro, porcobrar = _resolver_saldos_cliente(
        referencia=referencia,
        ahorro=ahorro,
        porcobrar=porcobrar,
    )
    return calcular_deposito_extra_tradicional(
        pab_origen_total=totales["pab_origen_total"],
        pab_actualizado_total=totales["pab_actualizado_total"],
        pricing=totales["pricing"],
        ahorro=ahorro,
        por_cobrar=porcobrar,
    )

def oportunidad_dep_extra(
    *,
    referencia: str,
    deudas: list[str],
    es_opp_cred: bool,
    ahorro: Optional[float] = None,
    porcobrar: Optional[float] = None,
    deposito_extra: float = 0.0,
) -> float:
    """Obtiene el Depósito Extra necesario según el tipo de análisis."""
    if es_opp_cred:
        return oportunidad_dep_extra_credito(
            referencia=referencia,
            deudas=deudas,
            ahorro=ahorro,
            porcobrar=porcobrar,
            deposito_extra=deposito_extra,
        )
    return oportunidad_dep_extra_tradicional(
        referencia=referencia,
        deudas=deudas,
        ahorro=ahorro,
        porcobrar=porcobrar,
        deposito_extra=deposito_extra,
    )

### - ContraOfertas Viables
def oportunidad_contraofertas_credito(
    *,
    referencia: str,
    deudas: list[str],
    ahorro: Optional[float] = None,
    porcobrar: Optional[float] = None,
    deposito_extra: float = 0.0,
) -> float:
    """Obtiene la ContraOferta Viable para Crédito."""
    totales = _obtener_totales_deudas(referencia=referencia, deudas=deudas)
    if totales["pab_ideal_total"] <= 0 or totales["pab_origen_total"] <= 0:
        return 0.0
    return calcular_contraoferta_credito(
        pab_ideal_total=totales["pab_ideal_total"],
        pab_origen_total=totales["pab_origen_total"],
        deposito_extra=deposito_extra,
    )

def oportunidad_contraofertas_tradicional(
    *,
    referencia: str,
    deudas: list[str],
    ahorro: Optional[float] = None,
    porcobrar: Optional[float] = None,
    deposito_extra: float = 0.0,
) -> float:
    """Obtiene la ContraOferta Viable para Tradicional."""
    totales = _obtener_totales_deudas(referencia=referencia, deudas=deudas)
    ahorro, porcobrar = _resolver_saldos_cliente(
        referencia=referencia,
        ahorro=ahorro,
        porcobrar=porcobrar,
    )
    return calcular_contraoferta_tradicional(
        pab_origen_total=totales["pab_origen_total"],
        pricing=totales["pricing"],
        ahorro=ahorro,
        por_cobrar=porcobrar,
        deposito_extra=deposito_extra,
    )

def oportunidad_contraofertas(
    *,
    referencia: str,
    deudas: list[str],
    es_opp_cred: bool,
    ahorro: Optional[float] = None,
    porcobrar: Optional[float] = None,
    deposito_extra: float = 0.0,
) -> float:
    """Obtiene la ContraOferta Viable según el tipo de análisis."""
    if es_opp_cred:
        return oportunidad_contraofertas_credito(
            referencia=referencia,
            deudas=deudas,
            ahorro=ahorro,
            porcobrar=porcobrar,
            deposito_extra=deposito_extra,
        )
    return oportunidad_contraofertas_tradicional(
        referencia=referencia,
        deudas=deudas,
        ahorro=ahorro,
        porcobrar=porcobrar,
        deposito_extra=deposito_extra,
    )

### - Acuerdos para Robo
def oportunidad_acuerdos_robo_credito(*, referencia: str, deudas: list[str]) -> float:
    """Obtiene el número de Acuerdos para Robo por Crédito."""
    return float(len(obtener_acuerdos_robo(deudas=deudas)))

def oportunidad_acuerdos_robo_tradicional(*, referencia: str, deudas: list[str]) -> float:
    """Obtiene el número de Acuerdos para Robo por Tradicional."""
    return float(len(obtener_acuerdos_robo(deudas=deudas)))

def oportunidad_acuerdos_robo(
    *,
    referencia: str,
    deudas: list[str],
    es_opp_cred: bool,
) -> float:
    """Obtiene los Acuerdos para Robo según el tipo de análisis."""
    return float(len(obtener_acuerdos_robo(deudas=deudas)))

### - Liquidaciones Instantáneas
def oportunidad_liq_insta_credito(
    *,
    referencia: str,
    deudas: list[str],
    ahorro: Optional[float] = None,
    porcobrar: Optional[float] = None,
    deposito_extra: float = 0.0,
) -> float:
    """Obtiene el Descuento Actual para evaluar la Liquidación Instantánea por Crédito."""
    totales = _obtener_totales_deudas(referencia=referencia, deudas=deudas)
    return calcular_descuento_actual(
        pab_origen_total=totales["pab_origen_total"],
        pab_actualizado_total=totales["pab_actualizado_total"],
    )

def oportunidad_liq_insta_tradicional(
    *,
    referencia: str,
    deudas: list[str],
    ahorro: Optional[float] = None,
    porcobrar: Optional[float] = None,
    deposito_extra: float = 0.0,
) -> float:
    """Obtiene el Descuento Actual para evaluar la Liquidación Instantánea por Tradicional."""
    totales = _obtener_totales_deudas(referencia=referencia, deudas=deudas)
    return calcular_descuento_actual(
        pab_origen_total=totales["pab_origen_total"],
        pab_actualizado_total=totales["pab_actualizado_total"],
    )

def oportunidad_liq_insta(
    *,
    referencia: str,
    deudas: list[str],
    es_opp_cred: bool,
    ahorro: Optional[float] = None,
    porcobrar: Optional[float] = None,
    deposito_extra: float = 0.0,
) -> float:
    """Obtiene la Liquidación Instantánea según el tipo de análisis."""
    if es_opp_cred:
        return oportunidad_liq_insta_credito(
            referencia=referencia,
            deudas=deudas,
            ahorro=ahorro,
            porcobrar=porcobrar,
            deposito_extra=deposito_extra,
        )
    return oportunidad_liq_insta_tradicional(
        referencia=referencia,
        deudas=deudas,
        ahorro=ahorro,
        porcobrar=porcobrar,
        deposito_extra=deposito_extra,
    )

### - IA Liquidadora
def oportunidad_ia_liquidadora(*, referencia: str, deudas: list[str]) -> float:
    """Obtiene la máxima probabilidad de liquidación de las deudas seleccionadas."""
    probabilidades = obtener_probabilidades_ia_liquidadora(deudas=deudas)
    if not probabilidades:
        return 0.0
    return max(probabilidades.values())

# --- Agregador de Oportunidades por Referencia ---
def _resultado_oportunidad(
    *,
    aplica: bool,
    valor: Any,
    detalle: str,
    tipo_valor: str,
) -> dict[str, Any]:
    """Construye el resultado homogéneo de una oportunidad."""
    return {
        "aplica": bool(aplica),
        "valor": valor,
        "detalle": detalle,
        "tipo_valor": tipo_valor,
    }

def calcular_oportunidades_referencia(
    *,
    referencia: str,
    deudas: list[str],
    es_opp_cred: bool,
    ahorro: Optional[float] = None,
    porcobrar: Optional[float] = None,
    deposito_extra: float = 0.0,
) -> dict[str, dict[str, Any]]:
    """Calcula todas las oportunidades de una Referencia para un conjunto de deudas.

    Args:
        referencia (str): Referencia analizada.
        deudas (list[str]): Deudas seleccionadas.
        es_opp_cred (bool): True si el análisis es por Crédito.
        ahorro (Optional[float]): Ahorro a usar. Si es None, se toma el oficial.
        porcobrar (Optional[float]): Por Cobrar a usar. Si es None, se toma el oficial.
        deposito_extra (float): Depósito Extra simulado en la calculadora.

    Returns:
        dict[str, dict[str, Any]]: Diccionario por oportunidad con
        ``aplica``, ``valor``, ``detalle`` y ``tipo_valor``.
    """
    deudas_normalizadas = [_normalizar_id_deuda(d) for d in deudas if _normalizar_id_deuda(d)]
    if not deudas_normalizadas:
        return {
            oportunidad: _resultado_oportunidad(
                aplica=False,
                valor=0,
                detalle="Sin deudas seleccionadas.",
                tipo_valor="texto",
            )
            for oportunidad in OPORTUNIDADES
        }

    totales = _obtener_totales_deudas(
        referencia=referencia,
        deudas=deudas_normalizadas,
    )
    if totales["pab_origen_total"] <= 0:
        return {
            oportunidad: _resultado_oportunidad(
                aplica=False,
                valor=0,
                detalle="Sin datos de Asignación para las deudas seleccionadas.",
                tipo_valor="texto",
            )
            for oportunidad in OPORTUNIDADES
        }
    ahorro, porcobrar = _resolver_saldos_cliente(
        referencia=referencia,
        ahorro=ahorro,
        porcobrar=porcobrar,
    )

    # Paso 1: Verificar que el Crédito esté habilitado
    credito_habilitado = True
    detalle_credito = ""
    if es_opp_cred:
        _, _, no_opp = obtener_estado_actual_credito(referencia)
        if no_opp:
            credito_habilitado = False
            detalle_credito = "El cliente no opta a Crédito."
        elif totales["pab_ideal_total"] <= 0 or any(
            _obtener_pab_ideal_deuda(deuda) <= 0 for deuda in deudas_normalizadas
        ):
            credito_habilitado = False
            detalle_credito = "Falta PaB Ideal en al menos una deuda."

    # Paso 2: Descuento Actual y Descuento Esperado
    descuento_actual = calcular_descuento_actual(
        pab_origen_total=totales["pab_origen_total"],
        pab_actualizado_total=totales["pab_actualizado_total"],
    )
    descuento_esperado = totales["descuento_esperado"]

    # Paso 3: Calcular Depósito Extra
    if es_opp_cred:
        deposito_extra_calculado = (
            calcular_deposito_extra_credito(
                pab_ideal_total=totales["pab_ideal_total"],
                pab_actualizado_total=totales["pab_actualizado_total"],
            )
            if credito_habilitado
            else 0.0
        )
    else:
        deposito_extra_calculado = calcular_deposito_extra_tradicional(
            pab_origen_total=totales["pab_origen_total"],
            pab_actualizado_total=totales["pab_actualizado_total"],
            pricing=totales["pricing"],
            ahorro=ahorro,
            por_cobrar=porcobrar,
        )
    deposito_extra_aplica = credito_habilitado and evaluar_deposito_extra(
        deposito_extra=deposito_extra_calculado,
        apartado_neto=totales["apartado_neto"],
    )

    # Paso 4: Calcular ContraOferta Viable
    if es_opp_cred:
        contraoferta = (
            calcular_contraoferta_credito(
                pab_ideal_total=totales["pab_ideal_total"],
                pab_origen_total=totales["pab_origen_total"],
                deposito_extra=deposito_extra,
            )
            if credito_habilitado
            else 0.0
        )
    else:
        contraoferta = calcular_contraoferta_tradicional(
            pab_origen_total=totales["pab_origen_total"],
            pricing=totales["pricing"],
            ahorro=ahorro,
            por_cobrar=porcobrar,
            deposito_extra=deposito_extra,
        )
    contraoferta_aplica = credito_habilitado and evaluar_contraoferta(
        contraoferta=contraoferta,
        descuento_actual=descuento_actual,
        descuento_esperado=descuento_esperado,
    )

    # Paso 5: Evaluar Liquidación Instantánea
    deposito_extra_neto = deposito_extra_calculado - max(_a_float(deposito_extra), 0.0)
    liq_insta_aplica = credito_habilitado and evaluar_liq_insta(
        descuento_actual=descuento_actual,
        contraoferta=contraoferta,
        deposito_extra=deposito_extra_neto,
    )

    # Paso 6: Acuerdos para Robo
    acuerdos_robo = obtener_acuerdos_robo(deudas=deudas_normalizadas)
    detalle_robo = (
        "; ".join("{}: {}".format(deuda, fecha) for deuda, fecha in acuerdos_robo.items())
        if acuerdos_robo
        else "Sin acuerdos vencidos sin gestión posterior."
    )

    # Paso 7: IA Liquidadora
    probabilidades = obtener_probabilidades_ia_liquidadora(deudas=deudas_normalizadas)
    probabilidades_cumplen = {
        deuda: prob
        for deuda, prob in probabilidades.items()
        if prob >= UMBRAL_PROB_LIQ_IA
    }
    detalle_ia = (
        "; ".join("{}: {:.0%}".format(deuda, prob) for deuda, prob in probabilidades_cumplen.items())
        if probabilidades_cumplen
        else "Sin deudas con probabilidad >= 50%."
    )

    # Paso 8: Construir los resultados
    detalle_deposito = "Depósito necesario: ${:,.0f}; {:.2f} apartados netos.".format(
        deposito_extra_calculado,
        (deposito_extra_calculado / totales["apartado_neto"]) if totales["apartado_neto"] > 0 else 0.0,
    )
    if es_opp_cred and not credito_habilitado:
        detalle_deposito = detalle_credito

    detalle_contraoferta = "Descuento requerido: {:.1%}; pago estimado: ${:,.0f}.".format(
        contraoferta,
        totales["pab_origen_total"] * (1 - contraoferta),
    )
    if es_opp_cred and not credito_habilitado:
        detalle_contraoferta = detalle_credito

    detalle_liq_insta = "Descuento actual: {:.1%}; descuento requerido: {:.1%}.".format(
        descuento_actual,
        contraoferta,
    )
    if es_opp_cred and not credito_habilitado:
        detalle_liq_insta = detalle_credito

    return {
        "Depósito Extra": _resultado_oportunidad(
            aplica=deposito_extra_aplica,
            valor=deposito_extra_calculado,
            detalle=detalle_deposito,
            tipo_valor="monto",
        ),
        "ContraOferta Viable": _resultado_oportunidad(
            aplica=contraoferta_aplica,
            valor=contraoferta,
            detalle=detalle_contraoferta,
            tipo_valor="porcentaje",
        ),
        "Liquidación Instantánea": _resultado_oportunidad(
            aplica=liq_insta_aplica,
            valor=descuento_actual,
            detalle=detalle_liq_insta,
            tipo_valor="porcentaje",
        ),
        "Acuerdo para Robo": _resultado_oportunidad(
            aplica=bool(acuerdos_robo),
            valor="{} deuda(s)".format(len(acuerdos_robo)),
            detalle=detalle_robo,
            tipo_valor="texto",
        ),
        "IA Liquidadora": _resultado_oportunidad(
            aplica=bool(probabilidades_cumplen),
            valor=max(probabilidades.values()) if probabilidades else 0.0,
            detalle=detalle_ia,
            tipo_valor="porcentaje",
        ),
    }
