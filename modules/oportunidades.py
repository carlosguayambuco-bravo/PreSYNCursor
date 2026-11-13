# Estándar usando Pep8
# Librerías de Python
from typing import Any, Callable, Optional
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
    load_vencimientos_acuerdos,
    obtener_fecha_expiracion_acuerdo,
)
from data.data_uploader import register_opps_uploaded
from modules.constants import (
    BANCOS_PORTAFOLIO,
    ESTADOS_NO_OPP_CREDITO,
    ESTADOS_NO_QUIERE_CREDITO,
    ETIQUETAS_ACT_CONFIABLES,
    IVA,
    MARGEN_DESCUENTO_ESPERADO,
    MONTO_ADICIONAL_DEPOSITO,
    OPORTUNIDADES,
    UMBRAL_CONTRACOFERTA_MAXIMA,
    UMBRAL_DESCUENTO_MINIMO_LIQ_INSTA,
    UMBRAL_DEPOSITO_EXTRA_APARTADOS,
    UMBRAL_DEPOSITO_EXTRA_MONTO,
    UMBRAL_PROB_LIQ_IA,
    VENTANA_PORTAFOLIO_SEGUNDOS,
)
from utils.helpers_general import clean_tildes, replaceNaN

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
    # Camino rápido para los valores numéricos, que son la mayoría en los
    # bucles de detalle. Evita el costo de pd.to_numeric por cada celda.
    if isinstance(valor, (int, float, np.integer, np.floating)):
        numero = float(valor)
        return default if np.isnan(numero) else numero
    try:
        numero = pd.to_numeric(valor, errors="coerce")
    except (TypeError, ValueError):
        return default
    if pd.isna(numero):
        return default
    return float(numero)

# Función Auxiliar para Convertir un Valor a Booleano
def _a_bool(valor: Any, default: bool = False) -> bool:
    """Convierte un valor a booleano tratando NaN como False."""
    if valor is None:
        return default
    if isinstance(valor, (bool, np.bool_)):
        return bool(valor)
    try:
        if pd.isna(valor):
            return default
    except (TypeError, ValueError):
        pass
    return bool(valor)

# Función Auxiliar para Convertir un Valor a Lista
def _a_lista(valor: Any) -> list[Any]:
    """Devuelve una lista segura para valores que pueden venir como NaN."""
    if isinstance(valor, (list, tuple, set)):
        return list(valor)
    return []

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
    masivas_df: Optional[pd.DataFrame] = None,
    solicitudes_df: Optional[pd.DataFrame] = None,
) -> float:
    """Resuelve el PaB_Actualizado de una actualización ACTUALIZADO_ALIANZAS.

    Se compara el último descuento en base (masivas) contra la última solicitud
    exitosa. Si ambas fuentes tienen fecha, prevalece la más reciente. Si no hay
    fechas comparables, se usa el valor de la fila de actualización.

    Args:
        id_deuda (str): Id de la deuda.
        pab_origen (float): PaB_Origen de la deuda.
        fecha_actualizacion (Optional[pd.Timestamp]): Fecha de la actualización.
        pab_actualizado_fila (float): Valor reportado en la fila de actualización.
        masivas_df (Optional[pd.DataFrame]): Masivas ya cargadas. Si es None se
            usa ``load_masivas``.
        solicitudes_df (Optional[pd.DataFrame]): Solicitudes del MEC ya cargadas.
            Si es None se usa ``_obtener_solicitudes_mec_calculo``.
    """
    candidatos = []

    # Paso 1: Último descuento en base (masivas)
    if masivas_df is None:
        try:
            masivas_df = load_masivas()
        except Exception:
            masivas_df = pd.DataFrame()
    if (
        masivas_df is not None
        and not masivas_df.empty
        and "Id_Deuda" in masivas_df.columns
    ):
        masivas_deuda = masivas_df[
            masivas_df["Id_Deuda"].apply(_normalizar_id_deuda) == id_deuda
        ].copy()
        if not masivas_deuda.empty:
            # La masiva más reciente es la de mayor Fecha_Masiva y, en empate,
            # la de mayor Fila_Sheets. Si no hay esas columnas, se mantiene el
            # orden de la hoja (la última fila es la más reciente).
            columnas_orden = [
                columna for columna in ("Fecha_Masiva", "Fila_Sheets")
                if columna in masivas_deuda.columns
            ]
            if columnas_orden:
                masivas_deuda = masivas_deuda.sort_values(
                    by=columnas_orden, ascending=False, na_position="last"
                )
            ultima_masiva = masivas_deuda.iloc[0]
            candidatos.append({
                "fuente": "masivas",
                "pab": _a_float(ultima_masiva.get("PaB_Propuesta"), default=pab_actualizado_fila),
                "fecha": _fecha_limite_uso_masiva(ultima_masiva.get("Metadata")),
            })

    # Paso 2: Última solicitud exitosa que incluya la deuda
    if solicitudes_df is None:
        try:
            solicitudes_df = _obtener_solicitudes_mec_calculo()
        except Exception:
            solicitudes_df = pd.DataFrame()
    if (
        solicitudes_df is not None
        and not solicitudes_df.empty
        and "Estado_Solicitud" in solicitudes_df.columns
    ):
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
    - Si la actualización confiable deja el PaB en 0, se usa ``PaB_Origen``:
      un pago en 0 se interpreta como dato faltante, no como descuento total.
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

    # Paso 4: Si no hay un descuento real, el PaB vuelve al Origen.
    # Un PaB_Actualizado en 0 suele ser un dato faltante, no un descuento del 100%.
    if pab_origen > 0 and pab_fila <= 0:
        return pab_origen

    # Paso 5: Acotar el valor al rango válido
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
    deposito_extra: float = 0.0,
) -> float:
    """Calcula el Depósito Extra necesario para Crédito.

    El PaB Ideal es el cupo aprobado por Crédito. Si el pago actual
    (``PaB_Actualizado``) supera ese cupo, el cliente debe cubrir la
    diferencia para que el crédito quede aprobado. El ``deposito_extra``
    simulado hace parte de los recursos disponibles y reduce el depósito
    requerido:

    ``Depósito Extra = SUM(PaB_Actualizado) + 20k - SUM(PaB_Ideal) - Depósito_Extra``.
    """
    return (
        _a_float(pab_actualizado_total)
        + MONTO_ADICIONAL_DEPOSITO
        - _a_float(pab_ideal_total)
        - max(_a_float(deposito_extra), 0.0)
    )

def calcular_deposito_extra_tradicional(
    *,
    pab_origen_total: float,
    pab_actualizado_total: float,
    pricing: float,
    ahorro: float,
    por_cobrar: float,
    deposito_extra: float = 0.0,
) -> float:
    """Calcula el Depósito Extra necesario para Tradicional.

    El ``deposito_extra`` simulado se suma al Ahorro del cliente, porque
    representa el ahorro nuevo que se proyecta conseguir a futuro.
    """
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
        - (
            _a_float(ahorro)
            + max(_a_float(deposito_extra), 0.0)
            - _a_float(por_cobrar)
        )
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
    es_opp_cred: bool = False,
) -> bool:
    """Evalúa si el cliente ya puede liquidar de forma instantánea.

    Se cumple cuando el Descuento Actual es igual o mejor que la ContraOferta
    necesaria y existe un descuento, o cuando el Depósito Extra calculado es
    negativo (no se necesita depósito).

    Para Tradicional se exige además un Descuento Actual mínimo de
    ``UMBRAL_DESCUENTO_MINIMO_LIQ_INSTA`` (3% por defecto): tener el dinero no
    basta si no existe un descuento real. Crédito no aplica ese mínimo.
    """
    descuento_actual = _a_float(descuento_actual)
    if not es_opp_cred and descuento_actual < UMBRAL_DESCUENTO_MINIMO_LIQ_INSTA:
        return False
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
        viable_credito = pab_total <= (
            _a_float(pab_ideal_total)
            + MONTO_ADICIONAL_DEPOSITO
            + max(_a_float(deposito_extra), 0.0)
        )
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

def _resolver_pab_simulado_por_deuda(
    *,
    pab_por_deuda: Optional[dict[str, float]],
) -> dict[str, float]:
    """Normaliza el PaB simulado por deuda que llega desde la calculadora.

    Las llaves se normalizan igual que los ``Id_Deuda`` de la Asignación para
    que el cruce no falle por sufijos ``.0`` o espacios.
    """
    if not isinstance(pab_por_deuda, dict):
        return {}
    pab_normalizado = {}
    for deuda, pab in pab_por_deuda.items():
        deuda_norm = _normalizar_id_deuda(deuda)
        if not deuda_norm:
            continue
        pab_float = _a_float(pab, default=np.nan)
        if pd.isna(pab_float):
            continue
        pab_normalizado[deuda_norm] = max(pab_float, 0.0)
    return pab_normalizado

def _obtener_totales_deudas(
    *,
    referencia: str,
    deudas: list[str],
    pab_por_deuda: Optional[dict[str, float]] = None,
) -> dict[str, Any]:
    """Calcula los totales y datos base de las deudas seleccionadas.

    Si se recibe ``pab_por_deuda``, su valor se usa como PaB_Actualizado
    simulado para esa deuda. Las deudas que no vengan en el diccionario usan
    el PaB_Actualizado oficial de las Actualizaciones.
    """
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
    pab_simulado = _resolver_pab_simulado_por_deuda(pab_por_deuda=pab_por_deuda)

    for _, fila in asignacion_df.iterrows():
        deuda = _normalizar_id_deuda(fila["Id_Deuda"])
        pab_origen = max(_a_float(fila.get("PaB_Origen")), 0.0)
        if deuda in pab_simulado:
            # El PaB simulado puede superar el PaB_Origen cuando el usuario
            # distribuye un monto de portafolio mayor al DUM total.
            pab_actualizado = max(pab_simulado[deuda], 0.0)
        else:
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
    pab_por_deuda: Optional[dict[str, float]] = None,
) -> float:
    """Obtiene el Depósito Extra necesario para Crédito."""
    totales = _obtener_totales_deudas(
        referencia=referencia,
        deudas=deudas,
        pab_por_deuda=pab_por_deuda,
    )
    if totales["pab_ideal_total"] <= 0:
        return 0.0
    return calcular_deposito_extra_credito(
        pab_ideal_total=totales["pab_ideal_total"],
        pab_actualizado_total=totales["pab_actualizado_total"],
        deposito_extra=deposito_extra,
    )

def oportunidad_dep_extra_tradicional(
    *,
    referencia: str,
    deudas: list[str],
    ahorro: Optional[float] = None,
    porcobrar: Optional[float] = None,
    deposito_extra: float = 0.0,
    pab_por_deuda: Optional[dict[str, float]] = None,
) -> float:
    """Obtiene el Depósito Extra necesario para Tradicional."""
    totales = _obtener_totales_deudas(
        referencia=referencia,
        deudas=deudas,
        pab_por_deuda=pab_por_deuda,
    )
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
        deposito_extra=deposito_extra,
    )

def oportunidad_dep_extra(
    *,
    referencia: str,
    deudas: list[str],
    es_opp_cred: bool,
    ahorro: Optional[float] = None,
    porcobrar: Optional[float] = None,
    deposito_extra: float = 0.0,
    pab_por_deuda: Optional[dict[str, float]] = None,
) -> float:
    """Obtiene el Depósito Extra necesario según el tipo de análisis."""
    if es_opp_cred:
        return oportunidad_dep_extra_credito(
            referencia=referencia,
            deudas=deudas,
            ahorro=ahorro,
            porcobrar=porcobrar,
            deposito_extra=deposito_extra,
            pab_por_deuda=pab_por_deuda,
        )
    return oportunidad_dep_extra_tradicional(
        referencia=referencia,
        deudas=deudas,
        ahorro=ahorro,
        porcobrar=porcobrar,
        deposito_extra=deposito_extra,
        pab_por_deuda=pab_por_deuda,
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
    pab_por_deuda: Optional[dict[str, float]] = None,
) -> float:
    """Obtiene el Descuento Actual para evaluar la Liquidación Instantánea por Crédito."""
    totales = _obtener_totales_deudas(
        referencia=referencia,
        deudas=deudas,
        pab_por_deuda=pab_por_deuda,
    )
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
    pab_por_deuda: Optional[dict[str, float]] = None,
) -> float:
    """Obtiene el Descuento Actual para evaluar la Liquidación Instantánea por Tradicional."""
    totales = _obtener_totales_deudas(
        referencia=referencia,
        deudas=deudas,
        pab_por_deuda=pab_por_deuda,
    )
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
    pab_por_deuda: Optional[dict[str, float]] = None,
) -> float:
    """Obtiene la Liquidación Instantánea según el tipo de análisis."""
    if es_opp_cred:
        return oportunidad_liq_insta_credito(
            referencia=referencia,
            deudas=deudas,
            ahorro=ahorro,
            porcobrar=porcobrar,
            deposito_extra=deposito_extra,
            pab_por_deuda=pab_por_deuda,
        )
    return oportunidad_liq_insta_tradicional(
        referencia=referencia,
        deudas=deudas,
        ahorro=ahorro,
        porcobrar=porcobrar,
        deposito_extra=deposito_extra,
        pab_por_deuda=pab_por_deuda,
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
    pab_por_deuda: Optional[dict[str, float]] = None,
) -> dict[str, dict[str, Any]]:
    """Calcula todas las oportunidades de una Referencia para un conjunto de deudas.

    Args:
        referencia (str): Referencia analizada.
        deudas (list[str]): Deudas seleccionadas.
        es_opp_cred (bool): True si el análisis es por Crédito.
        ahorro (Optional[float]): Ahorro a usar. Si es None, se toma el oficial.
        porcobrar (Optional[float]): Por Cobrar a usar. Si es None, se toma el oficial.
        deposito_extra (float): Depósito Extra simulado en la calculadora. Hace
            parte de los recursos disponibles: reduce el depósito requerido y
            aumenta el disponible para la ContraOferta.
        pab_por_deuda (Optional[dict[str, float]]): PaB simulado por deuda desde
            los inputs de la calculadora. Reemplaza el PaB_Actualizado oficial
            para el Depósito Extra, el Descuento Actual y la evaluación de la
            ContraOferta. Puede superar el PaB_Origen cuando el monto de
            portafolio distribuido es mayor al DUM. Las deudas ausentes usan el
            PaB_Actualizado oficial.

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
        pab_por_deuda=pab_por_deuda,
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
        _, _, no_opp = obtener_estado_actual_credito(referencia=referencia)
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
                deposito_extra=deposito_extra,
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
            deposito_extra=deposito_extra,
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
    # El depósito calculado ya descuenta el depósito extra simulado.
    liq_insta_aplica = credito_habilitado and evaluar_liq_insta(
        descuento_actual=descuento_actual,
        contraoferta=contraoferta,
        deposito_extra=deposito_extra_calculado,
        es_opp_cred=es_opp_cred,
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
        "; ".join("ID_Deuda: {} - {:.0%} Prob Liq.".format(deuda, prob) for deuda, prob in probabilidades_cumplen.items())
        if probabilidades_cumplen
        else "Sin deudas con probabilidad >= 50%."
    )

    # Paso 8: Construir los resultados
    detalle_deposito = "Depósito necesario (neto de Depósito Extra): ${:,.0f}; {:.2f} apartados netos.".format(
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

# Función para registrar la oportunidad calculada (Solo aplica para cálculos individuales)
def registrar_opp_individual(*,referencia: str, deudas: list[str], tipo_analisis: str):
    # Paso 1: Crear la llave que manejará las Opps ya subidas
    if not ("registro_opps_ya_subidas" in st.session_state):
        st.session_state["registro_opps_ya_subidas"] = set()
    # Paso 2: Crear la llave que va a definir nuestra oportunidad
    llave_opp = '_'.join([
        referencia,
        '-'.join(sorted(deudas)),
        tipo_analisis
    ])
    # Paso 3: Verificamos si la Opp ya fue subida
    if llave_opp in st.session_state["registro_opps_ya_subidas"]:
        return

    # Paso 4: Registrar la Oportunidad
    if register_opps_uploaded(
        referencia=referencia,
        deudas=deudas,
        tipo_analisis=tipo_analisis
    ):
        st.session_state["registro_opps_ya_subidas"].add(llave_opp)

# =============================================================================
# Cálculo Masivo de Oportunidades (Vectorizado)
# =============================================================================
# La calculadora masiva NO usa Actualizaciones ni PaB simulado: el descuento
# sale exclusivamente de la Base del Mes de Masivas. Así las oportunidades
# tienen la misma certeza del 100% que el descuento reportado por el aliado.

# Función Auxiliar para Reportar el Progreso del Cálculo Masivo
def _reportar_progreso_masivo(
    progreso_callback: Optional[Callable[[float, str], None]],
    avance: float,
    mensaje: str,
) -> None:
    """Notifica el avance del cálculo masivo sin romper el cálculo si falla la UI."""
    if progreso_callback is None:
        return
    try:
        progreso_callback(float(min(max(avance, 0.0), 1.0)), str(mensaje))
    except Exception:
        pass

# Función Auxiliar para Definir las Columnas del Resultado Masivo
def _columnas_resultado_masivo() -> list[str]:
    """Devuelve las columnas del DataFrame de oportunidades masivas."""
    return [
        "Referencia",
        "Nombre_Cliente",
        "Negociador",
        "Prospecto_Credito",
        "Prospecto_Tradicional",
        "Pricing",
        "Ahorro",
        "Por_Cobrar",
        "Ahorro_Neto",
        "PaB_Origen_Total",
        "PaB_Actualizado_Total",
        "Descuento_Actual",
        "Pago_Actual",
        "Ingreso_Actual",
        "Ingreso_Estimado",
        "Ingreso_Estimado_Detalle",
        "Apartado_Neto",
        "Descuento_Esperado_Ponderado",
        "Deudas_Analizadas",
        "Deudas_Masivas",
        "Deudas_Con_PaB_Ideal",
        "Deudas_Sin_PaB_Ideal",
        "Tiene_Deudas_Liquidaciones",
        "Estado_Credito",
        "Tiene_Pipeline_Credito",
        "No_Opta_Credito",
        "Rechazo_Credito",
        "Credito_Viable",
        "Credito_Habilitado",
        "Credito_Detalle",
        "Tradicional_Habilitado",
        "Tipos_Analisis",
        "Viable_Por",
        "Fuente_Descuento",
        "Deudas_Referencia",
        "Trad_Alguna_Viable",
        "Cred_Alguna_Viable",
        "Trad_PaB_Origen_Total",
        "Trad_PaB_Actualizado_Total",
        "Trad_Descuento_Actual",
        "Trad_Pago_Actual",
        "Trad_Ingreso_Actual",
        "Trad_Apartado_Neto",
        "Trad_Descuento_Esperado_Ponderado",
        "Trad_Num_Deudas",
        "Trad_Deposito_Extra_Valor",
        "Trad_Deposito_Extra_Aplica",
        "Trad_Deposito_Extra_Detalle",
        "Trad_Contraoferta_Valor",
        "Trad_Contraoferta_Aplica",
        "Trad_Contraoferta_Detalle",
        "Trad_Liq_Insta_Aplica",
        "Trad_Liq_Insta_Detalle",
        "Trad_Viable",
        "Cred_PaB_Origen_Total",
        "Cred_PaB_Actualizado_Total",
        "Cred_PaB_Ideal_Total",
        "Cred_Descuento_Actual",
        "Cred_Pago_Actual",
        "Cred_Num_Deudas",
        "Cred_Descuento_Esperado_Ponderado",
        "Cred_Deposito_Extra_Valor",
        "Cred_Deposito_Extra_Aplica",
        "Cred_Deposito_Extra_Detalle",
        "Cred_Contraoferta_Valor",
        "Cred_Contraoferta_Aplica",
        "Cred_Contraoferta_Detalle",
        "Cred_Liq_Insta_Aplica",
        "Cred_Liq_Insta_Detalle",
        "Cred_Viable",
        "Acuerdo_Robo_Aplica",
        "Acuerdo_Robo_Valor",
        "Acuerdo_Robo_Deudas",
        "Acuerdo_Robo_Detalle",
        "Acuerdo_Robo_IDs",
        "IA_Liquidadora_Aplica",
        "IA_Liquidadora_Valor",
        "IA_Liquidadora_Detalle",
        "IA_Liquidadora_IDs",
        "Oportunidades",
        "Oportunidades_Generales",
        "Num_Oportunidades",
        "Num_Oportunidades_Calculadas",
        "Num_Oportunidades_Generales",
        "Es_Viable",
        "Portafolios_Detalle",
        "Deudas_Detalle",
        "Estados_Actualizacion",
        "Bancos",
        "Casas_Cobro",
    ]

# Función Auxiliar para Crear un Resultado Masivo Vacío
def _resultado_masivo_vacio() -> pd.DataFrame:
    """Devuelve un DataFrame vacío con todas las columnas del resultado masivo."""
    return pd.DataFrame(columns=_columnas_resultado_masivo())

# Función Auxiliar para Asegurar Todas las Columnas del Resultado Masivo
def _asegurar_columnas_resultado_masivo(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega las columnas faltantes con valores neutros según su tipo."""
    columnas_lista = {
        "Tipos_Analisis", "Oportunidades", "Deudas_Detalle", "Viable_Por",
        "Deudas_Referencia", "Oportunidades_Generales", "Portafolios_Detalle",
        "Acuerdo_Robo_IDs", "IA_Liquidadora_IDs", "Estados_Actualizacion",
        "Bancos", "Casas_Cobro",
    }
    columnas_texto = {
        "Referencia", "Nombre_Cliente", "Negociador", "Prospecto_Credito",
        "Prospecto_Tradicional", "Credito_Detalle", "Estado_Credito",
        "Fuente_Descuento",
        "Trad_Deposito_Extra_Detalle", "Trad_Contraoferta_Detalle",
        "Trad_Liq_Insta_Detalle", "Cred_Deposito_Extra_Detalle",
        "Cred_Contraoferta_Detalle", "Cred_Liq_Insta_Detalle",
        "Acuerdo_Robo_Valor", "Acuerdo_Robo_Detalle", "IA_Liquidadora_Detalle",
    }
    columnas_dict = {"Ingreso_Estimado_Detalle"}
    columnas_bool = {
        "Tiene_Deudas_Liquidaciones", "Tiene_Pipeline_Credito",
        "No_Opta_Credito", "Rechazo_Credito", "Credito_Viable",
        "Credito_Habilitado", "Tradicional_Habilitado",
        "Trad_Deposito_Extra_Aplica", "Trad_Contraoferta_Aplica",
        "Trad_Liq_Insta_Aplica", "Trad_Viable", "Trad_Alguna_Viable",
        "Cred_Deposito_Extra_Aplica", "Cred_Contraoferta_Aplica",
        "Cred_Liq_Insta_Aplica", "Cred_Viable", "Cred_Alguna_Viable",
        "Acuerdo_Robo_Aplica", "IA_Liquidadora_Aplica", "Es_Viable",
    }
    for columna in _columnas_resultado_masivo():
        if columna in df.columns:
            continue
        if columna in columnas_lista:
            df[columna] = [[] for _ in range(len(df))]
        elif columna in columnas_bool:
            df[columna] = False
        elif columna in columnas_texto:
            df[columna] = ""
        elif columna in columnas_dict:
            df[columna] = [{} for _ in range(len(df))]
        else:
            df[columna] = 0
    return df

# Función Auxiliar para Extraer el Id de Portafolio de la Metadata
def _extraer_id_portafolio(metadata: Any) -> str:
    """Devuelve el ``Id_Portafolio`` de la metadata de una masiva."""
    if not isinstance(metadata, dict):
        return ""
    return str(metadata.get("Id_Portafolio") or "").strip()

# Función Auxiliar para Extraer el PaB del Portafolio de la Metadata
def _extraer_pab_portafolio(metadata: Any) -> float:
    """Devuelve el ``PaB_Portafolio`` de la metadata o NaN si no existe."""
    if not isinstance(metadata, dict):
        return np.nan
    return _a_float(metadata.get("PaB_Portafolio"), default=np.nan)

# Función para Seleccionar el Mejor Descuento Vigente de Masivas por Deuda
def seleccionar_descuentos_masivas(
    *,
    masivas_df: pd.DataFrame,
    hoy: Optional[pd.Timestamp] = None,
) -> pd.DataFrame:
    """Selecciona un único descuento de Masivas por deuda.

    Reglas:
    - Solo se consideran registros con ``PaB_Propuesta`` mayor a 0.
    - Se descartan los registros con ``Fecha_Limite_Uso`` vencida.
    - Los registros sin metadata (o con metadata inválida) se consideran
      vigentes: la base existe y el aliado no reportó una fecha de expiración.
    - Si hay varios registros vigentes, se toma el de **menor PaB_Propuesta**
      (mejor descuento). Los empates se resuelven por la masiva más reciente.

    Además del descuento individual, devuelve la información del portafolio:
    ``Id_Portafolio``, ``PaB_Portafolio`` y ``Portafolio_Completo``. Una deuda
    pertenece a un portafolio cuando ``Metadata.Id_Portafolio`` no está vacío.
    ``Portafolio_Completo`` indica si el registro seleccionado cubre todas las
    deudas que la base reporta para ese portafolio.

    Args:
        masivas_df (pd.DataFrame): DataFrame de Masivas (``load_masivas``).
        hoy (Optional[pd.Timestamp]): Fecha de corte. Si es None se usa hoy en
            Bogotá.

    Returns:
        pd.DataFrame: Un registro por ``Id_Deuda`` con el mejor descuento vigente.
    """
    columnas_salida = [
        "Id_Deuda", "PaB_Propuesta", "Casa_Cobro", "Fecha_Masiva",
        "Fecha_Limite_Uso", "Es_Portafolio", "Fila_Sheets",
        "Id_Portafolio", "PaB_Portafolio", "Portafolio_Completo",
    ]
    if masivas_df is None or masivas_df.empty:
        return pd.DataFrame(columns=columnas_salida)
    if not {"Id_Deuda", "PaB_Propuesta"}.issubset(set(masivas_df.columns)):
        return pd.DataFrame(columns=columnas_salida)

    if hoy is None:
        hoy = pd.Timestamp.now(tz="America/Bogota").tz_localize(None).normalize()
    hoy = pd.Timestamp(hoy)
    if hoy.tzinfo is not None:
        hoy = hoy.tz_convert("America/Bogota").tz_localize(None)
    hoy = hoy.normalize()

    # Paso 1: Normalizar los Campos que se usan para comparar
    df = masivas_df.copy()
    df["Id_Deuda"] = df["Id_Deuda"].apply(_normalizar_id_deuda)
    df["PaB_Propuesta"] = pd.to_numeric(df["PaB_Propuesta"], errors="coerce")
    if "Fecha_Masiva" in df.columns:
        df["Fecha_Masiva"] = _normalizar_columna_fechas(df["Fecha_Masiva"])
    else:
        df["Fecha_Masiva"] = pd.NaT
    if "Fila_Sheets" in df.columns:
        df["Fila_Sheets"] = pd.to_numeric(df["Fila_Sheets"], errors="coerce")
    else:
        df["Fila_Sheets"] = np.nan
    if "Casa_Cobro" not in df.columns:
        df["Casa_Cobro"] = ""
    if "Es_Portafolio" not in df.columns:
        df["Es_Portafolio"] = False
    df["Fecha_Limite_Uso"] = df["Metadata"].apply(_fecha_limite_uso_masiva) if "Metadata" in df.columns else pd.NaT
    df["Id_Portafolio"] = df["Metadata"].apply(_extraer_id_portafolio) if "Metadata" in df.columns else ""
    pab_portafolio_metadata = (
        df["Metadata"].apply(_extraer_pab_portafolio)
        if "Metadata" in df.columns else pd.Series(np.nan, index=df.index)
    )
    if "PaB_Portafolio" in df.columns:
        pab_portafolio_columna = pd.to_numeric(df["PaB_Portafolio"], errors="coerce")
        df["PaB_Portafolio"] = pab_portafolio_metadata.where(
            pab_portafolio_metadata.notna(), pab_portafolio_columna
        )
    else:
        df["PaB_Portafolio"] = pab_portafolio_metadata

    # Guardamos las deudas que la base reporta para cada portafolio antes de
    # filtrar; así sabemos si el mejor registro seleccionado está incompleto.
    df_base_portafolios = df[df["Id_Portafolio"] != ""].copy()
    ids_por_portafolio = df_base_portafolios.groupby("Id_Portafolio")["Id_Deuda"].apply(
        lambda serie: set(serie)
    ).to_dict()

    # Paso 2: Quedarnos con Descuentos Válidos y Vigentes
    df = df[(df["Id_Deuda"] != "") & (df["PaB_Propuesta"] > 0)].copy()
    if df.empty:
        return pd.DataFrame(columns=columnas_salida)
    fecha_limite = pd.to_datetime(df["Fecha_Limite_Uso"], errors="coerce")
    vigente = fecha_limite.isna() | (fecha_limite.dt.normalize() >= hoy)
    df = df[vigente].copy()
    if df.empty:
        return pd.DataFrame(columns=columnas_salida)

    # Paso 3: Elegir el Menor PaB (Mejor Descuento) y, en Empate, el Más Reciente
    df = df.sort_values(
        by=["Id_Deuda", "PaB_Propuesta", "Fecha_Masiva", "Fila_Sheets"],
        ascending=[True, True, False, False],
        na_position="last",
    )
    df = df.drop_duplicates(subset=["Id_Deuda"], keep="first").copy()

    # Paso 4: Marcar si el Registro Seleccionado Cubre Todo el Portafolio
    ids_seleccionados = df[df["Id_Portafolio"] != ""].groupby(
        "Id_Portafolio"
    )["Id_Deuda"].apply(lambda serie: set(serie)).to_dict()
    df["Portafolio_Completo"] = df["Id_Portafolio"].apply(
        lambda id_portafolio: (
            bool(id_portafolio)
            and ids_por_portafolio.get(id_portafolio, set())
            == ids_seleccionados.get(id_portafolio, set())
        )
    )

    return df[columnas_salida].reset_index(drop=True)

# Función Auxiliar para Eliminar Actualizaciones Duplicadas
def _deduplicar_actualizaciones(
    actualizaciones_df: Optional[pd.DataFrame],
) -> pd.DataFrame:
    """Elimina registros repetidos de la misma deuda en el mismo instante.

    La hoja de Actualizaciones puede repetir una gestión por reintentos de
    escritura o cargas parciales. Se conserva la **última** fila de la hoja,
    que es el criterio con el que se resuelven las filas más recientes.

    Args:
        actualizaciones_df (Optional[pd.DataFrame]): Actualizaciones crudas.

    Returns:
        pd.DataFrame: Copia normalizada y sin duplicados por ``Id_Deuda`` +
        ``Fecha_Act``. Si faltan las columnas requeridas, devuelve una copia
        sin transformar.
    """
    if actualizaciones_df is None:
        return pd.DataFrame()
    if actualizaciones_df.empty:
        return actualizaciones_df.copy()
    if not {"Id_Deuda", "Fecha_Act"}.issubset(set(actualizaciones_df.columns)):
        return actualizaciones_df.copy()

    df = actualizaciones_df.copy()
    df["Id_Deuda"] = df["Id_Deuda"].apply(_normalizar_id_deuda)
    df["Fecha_Act"] = _normalizar_columna_fechas(df["Fecha_Act"])
    df = df[(df["Id_Deuda"] != "") & df["Fecha_Act"].notna()]
    return df.drop_duplicates(
        subset=["Id_Deuda", "Fecha_Act"], keep="last"
    ).reset_index(drop=True)

# Función Auxiliar para Mapear la Última Actualización por Deuda
def _mapear_ultima_actualizacion(
    *,
    deudas: pd.DataFrame,
    actualizaciones_df: Optional[pd.DataFrame],
) -> pd.DataFrame:
    """Agrega la última etiqueta y fecha de actualización de cada deuda.

    La calculadora masiva usa esta información para el panel de resumen y para
    los filtros por estado, incluso cuando el Descuento Actual sale de Masivas.
    No modifica ``PaB_Actualizado``: solo expone la gestión más reciente.

    Args:
        deudas (pd.DataFrame): Deudas con ``Id_Deuda``.
        actualizaciones_df (Optional[pd.DataFrame]): Actualizaciones del MEC.

    Returns:
        pd.DataFrame: Copia de ``deudas`` con ``Etiqueta_Act_Deuda`` y
        ``Fecha_Act_Deuda``. Las deudas sin actualización quedan vacías/NaT.
    """
    resultado = deudas.copy()
    resultado["Etiqueta_Act_Deuda"] = ""
    resultado["Fecha_Act_Deuda"] = pd.NaT

    if actualizaciones_df is None or actualizaciones_df.empty:
        return resultado
    if not {"Id_Deuda", "Fecha_Act", "Etiqueta_Act"}.issubset(
        set(actualizaciones_df.columns)
    ):
        return resultado

    acts = _deduplicar_actualizaciones(actualizaciones_df)
    if acts.empty:
        return resultado

    # Paso 1: Normalizar la etiqueta y quedarnos con la gestión más reciente
    acts["Etiqueta_Act"] = (
        acts["Etiqueta_Act"].fillna("").astype(str).str.strip().str.upper()
    )
    acts = acts.sort_values(by="Fecha_Act", kind="stable")
    acts = acts.drop_duplicates(subset=["Id_Deuda"], keep="last")

    mapa_etiqueta = acts.set_index("Id_Deuda")["Etiqueta_Act"].to_dict()
    mapa_fecha = acts.set_index("Id_Deuda")["Fecha_Act"].to_dict()

    # Paso 2: Cruzar por deuda sin alterar el pago resuelto por Masivas
    resultado["Etiqueta_Act_Deuda"] = (
        resultado["Id_Deuda"].map(mapa_etiqueta).fillna("").astype(str)
    )
    resultado["Fecha_Act_Deuda"] = pd.to_datetime(
        resultado["Id_Deuda"].map(mapa_fecha), errors="coerce"
    )
    return resultado

# Función Auxiliar para Construir el Mapa del Último Descuento en Base
def _mapa_ultimo_descuento_masivas(
    masivas_df: Optional[pd.DataFrame],
) -> dict[str, dict[str, Any]]:
    """Construye ``Id_Deuda -> último descuento en base`` de Masivas.

    Se toma la masiva más reciente (``Fecha_Masiva`` y luego ``Fila_Sheets``).
    Si esas columnas no existen, se mantiene el orden de la hoja y gana la
    primera fila, igual que en la resolución individual.
    """
    if masivas_df is None or masivas_df.empty:
        return {}
    if "Id_Deuda" not in masivas_df.columns:
        return {}

    df = masivas_df.copy()
    df["Id_Deuda"] = df["Id_Deuda"].apply(_normalizar_id_deuda)
    df = df[df["Id_Deuda"] != ""]
    if df.empty:
        return {}

    columnas_orden = [
        columna for columna in ("Fecha_Masiva", "Fila_Sheets")
        if columna in df.columns
    ]
    if columnas_orden:
        df = df.sort_values(
            by=columnas_orden, ascending=False, na_position="last"
        )
    df = df.drop_duplicates(subset=["Id_Deuda"], keep="first")

    pab = (
        pd.to_numeric(df["PaB_Propuesta"], errors="coerce")
        if "PaB_Propuesta" in df.columns
        else pd.Series(np.nan, index=df.index, dtype=float)
    )
    fechas = (
        df["Metadata"].apply(_fecha_limite_uso_masiva)
        if "Metadata" in df.columns
        else pd.Series(None, index=df.index, dtype=object)
    )
    return {
        deuda: {
            "pab": None if pd.isna(pab_deuda) else float(pab_deuda),
            "fecha": (
                None
                if fecha_deuda is None or pd.isna(fecha_deuda)
                else fecha_deuda
            ),
        }
        for deuda, pab_deuda, fecha_deuda in zip(df["Id_Deuda"], pab, fechas)
    }

# Función Auxiliar para Construir el Mapa de la Última Solicitud Exitosa
def _mapa_ultima_solicitud_exitosa(
    solicitudes_df: Optional[pd.DataFrame],
) -> dict[str, dict[str, Any]]:
    """Construye ``Id_Deuda -> última solicitud exitosa`` del MEC.

    Se ordenan las solicitudes exitosas por ``Fecha_Respuesta`` descendente y
    se conserva el primer monto encontrado para cada deuda, replicando el
    recorrido de ``_resolver_pab_actualizado_alianzas`` pero en una sola pasada.
    """
    if solicitudes_df is None or solicitudes_df.empty:
        return {}
    if "Estado_Solicitud" not in solicitudes_df.columns:
        return {}

    solicitudes = solicitudes_df[
        solicitudes_df["Estado_Solicitud"] == "Exitosa"
    ]
    if solicitudes.empty:
        return {}
    if "Fecha_Respuesta" in solicitudes.columns:
        solicitudes = solicitudes.sort_values(
            by="Fecha_Respuesta", ascending=False, na_position="last"
        )

    mapa: dict[str, dict[str, Any]] = {}
    for _, solicitud in solicitudes.iterrows():
        fecha = _a_timestamp(solicitud.get("Fecha_Respuesta"))
        if fecha is None:
            fecha = _a_timestamp(solicitud.get("Timestamp"))
        for campo in ("JSON_Respuesta", "Datos_Solicitud"):
            contenido = solicitud.get(campo)
            if not isinstance(contenido, (list, tuple)):
                continue
            for deuda in contenido:
                if not isinstance(deuda, dict):
                    continue
                deuda_norm = _normalizar_id_deuda(deuda.get("Id_Deuda"))
                if not deuda_norm or deuda_norm in mapa:
                    continue
                monto = _a_float(deuda.get("Monto_Propuesto"), default=np.nan)
                if pd.isna(monto):
                    continue
                mapa[deuda_norm] = {"pab": monto, "fecha": fecha}
    return mapa

# Función Auxiliar para Construir el Mapa de Fechas Límite de Pago de Alianzas
def _mapa_fechas_limite_pago_alianza(
    solicitudes_df: Optional[pd.DataFrame],
) -> dict[str, pd.Timestamp]:
    """Construye ``Id_Deuda -> Fecha_Limite_Pago`` de acuerdos exitosos del MEC."""
    if solicitudes_df is None or solicitudes_df.empty:
        return {}
    columnas_requeridas = {"Estado_Solicitud", "Tipo_Solicitud", "Fecha_Limite_Pago"}
    if not columnas_requeridas.issubset(set(solicitudes_df.columns)):
        return {}

    solicitudes = solicitudes_df[
        (solicitudes_df["Estado_Solicitud"] == "Exitosa")
        & (solicitudes_df["Tipo_Solicitud"].isin(["Acuerdo de Pago", "Oferta de Acuerdo"]))
        & (solicitudes_df["Fecha_Limite_Pago"].notna())
    ].copy()
    if "Es_Historico" in solicitudes.columns:
        solicitudes = solicitudes[~solicitudes["Es_Historico"].fillna(False).astype(bool)]
    if solicitudes.empty:
        return {}

    columnas_orden = [c for c in ("Fecha_Respuesta", "Timestamp") if c in solicitudes.columns]
    if columnas_orden:
        solicitudes = solicitudes.sort_values(
            by=columnas_orden, ascending=False, na_position="last"
        )

    mapa: dict[str, pd.Timestamp] = {}
    for _, solicitud in solicitudes.iterrows():
        fecha_limite = _a_timestamp(solicitud.get("Fecha_Limite_Pago"))
        if fecha_limite is None:
            continue
        deudas: set[str] = set()
        ids_deuda = str(solicitud.get("Ids_Deuda", "")).replace(",", "-")
        deudas.update(
            _normalizar_id_deuda(x)
            for x in ids_deuda.split("-")
            if _normalizar_id_deuda(x)
        )
        for campo in ("Datos_Solicitud", "JSON_Respuesta"):
            contenido = solicitud.get(campo)
            if not isinstance(contenido, (list, tuple)):
                continue
            for deuda in contenido:
                if isinstance(deuda, dict):
                    deuda_norm = _normalizar_id_deuda(deuda.get("Id_Deuda"))
                    if deuda_norm:
                        deudas.add(deuda_norm)
        for deuda in deudas:
            fecha_actual = mapa.get(deuda)
            if fecha_actual is None or fecha_limite > fecha_actual:
                mapa[deuda] = fecha_limite
    return mapa

# Función Auxiliar para Preparar los Acuerdos para Robo sin Consultar Metabase
def _preparar_acuerdos_robo_masivos(
    *,
    actualizaciones_df: Optional[pd.DataFrame],
    solicitudes_df: Optional[pd.DataFrame],
    liquidaciones: set[str],
    deudas: list[str],
    hoy: pd.Timestamp,
) -> tuple[dict[str, str], list[dict[str, str]]]:
    """Calcula los acuerdos para robo que se pueden resolver con Alianzas.

    Returns:
        tuple[dict[str, str], list[dict[str, str]]]: (acuerdos confirmados por
        Alianzas, deudas que necesitan consultar Metabase).
    """
    if actualizaciones_df is None or actualizaciones_df.empty:
        return {}, []
    columnas_requeridas = {"Id_Deuda", "Fecha_Act", "Etiqueta_Act"}
    if not columnas_requeridas.issubset(set(actualizaciones_df.columns)):
        return {}, []

    deudas_scope = {
        _normalizar_id_deuda(deuda)
        for deuda in deudas
        if _normalizar_id_deuda(deuda)
    }
    if not deudas_scope:
        return {}, []

    acts = _deduplicar_actualizaciones(actualizaciones_df)
    if acts.empty:
        return {}, []
    acts = acts[acts["Id_Deuda"].isin(deudas_scope)]
    if acts.empty:
        return {}, []

    # Paso 1: Última actualización ACUERDO por deuda
    acts_acuerdo = acts[
        acts["Etiqueta_Act"].astype(str).str.strip().str.upper() == "ACUERDO"
    ].copy()
    if acts_acuerdo.empty:
        return {}, []
    acts_acuerdo = acts_acuerdo.sort_values(by="Fecha_Act").drop_duplicates(
        subset=["Id_Deuda"], keep="last"
    )

    # Paso 2: Verificar que el ACUERDO sea la última gestión de la deuda
    ultimas = acts.sort_values(by="Fecha_Act").drop_duplicates(
        subset=["Id_Deuda"], keep="last"
    )[["Id_Deuda", "Fecha_Act"]]
    acuerdos = acts_acuerdo.merge(ultimas, on="Id_Deuda", suffixes=("_Acuerdo", "_Ultima"))
    acuerdos = acuerdos[
        acuerdos["Fecha_Act_Acuerdo"].notna()
        & (acuerdos["Fecha_Act_Acuerdo"] == acuerdos["Fecha_Act_Ultima"])
    ]
    if acuerdos.empty:
        return {}, []

    # Paso 3: Resolver primero la fecha de Alianzas
    fechas_alianza = _mapa_fechas_limite_pago_alianza(solicitudes_df)
    acuerdos_robo: dict[str, str] = {}
    pendientes: list[dict[str, str]] = []
    for _, acuerdo in acuerdos.iterrows():
        deuda = _normalizar_id_deuda(acuerdo.get("Id_Deuda"))
        if not deuda or deuda in liquidaciones:
            continue
        fecha_alianza = fechas_alianza.get(deuda)
        if fecha_alianza is not None:
            if fecha_alianza.normalize() < hoy:
                acuerdos_robo[deuda] = fecha_alianza.strftime("%d/%m/%Y")
            continue
        correo = str(acuerdo.get("Correo", "")).strip()
        if not correo or correo.lower() == "nan":
            continue
        pendientes.append({"Id_Deuda": deuda, "Correo": correo})
    return acuerdos_robo, pendientes

# Función Auxiliar para Construir las Fechas de Metabase de los Acuerdos
def _construir_fechas_metabase_acuerdos(
    *,
    vencimientos_df: Optional[pd.DataFrame],
    pendientes: list[dict[str, str]],
) -> dict[str, Any]:
    """Traduce la consulta batch de Metabase al mapa que espera el cálculo."""
    if vencimientos_df is None or vencimientos_df.empty or not pendientes:
        return {}

    df = vencimientos_df.copy()
    if not {"Id_Deuda", "Correo_Act", "Etiqueta_Act", "Fecha_Expiracion"}.issubset(set(df.columns)):
        return {}
    df["Id_Deuda"] = df["Id_Deuda"].apply(_normalizar_id_deuda)
    df["Correo_Act"] = df["Correo_Act"].astype(str).str.strip()
    df["Etiqueta_Act"] = df["Etiqueta_Act"].astype(str).str.strip().str.lower()
    df["Fecha_Expiracion"] = pd.to_datetime(df["Fecha_Expiracion"], errors="coerce")
    df = df[(df["Etiqueta_Act"] == "agreement") & (df["Fecha_Expiracion"].notna())]

    fechas: dict[str, Any] = {}
    for pendiente in pendientes:
        deuda = _normalizar_id_deuda(pendiente.get("Id_Deuda"))
        correo = str(pendiente.get("Correo", "")).strip()
        if not deuda:
            continue
        coincidencias = df[
            (df["Id_Deuda"] == deuda) & (df["Correo_Act"] == correo)
        ]
        if coincidencias.empty:
            # La consulta trajo datos, pero no un acuerdo para esta deuda/correo:
            # se reporta "Sin fecha" igual que la calculadora individual.
            fechas[deuda] = pd.NaT
        else:
            fechas[deuda] = coincidencias["Fecha_Expiracion"].max()
    return fechas

# Función Auxiliar para Calcular las Métricas de Tradicional
def _calcular_metricas_tradicional_masivas(
    *,
    deudas: pd.DataFrame,
    saldos: dict[str, dict[str, float]],
    group_col: str = "Referencia",
) -> pd.DataFrame:
    """Calcula las métricas y oportunidades tradicionales por grupo.

    Args:
        deudas (pd.DataFrame): Deudas con PaB_Actualizado y datos del cliente.
        saldos (dict[str, dict[str, float]]): Saldos y Por Cobrar por Referencia.
        group_col (str): Columna de agrupación. ``Referencia`` para el resumen
            del cliente o ``Unidad_Id`` para el detalle por portafolio.
    """
    columnas = [
        group_col, "Trad_PaB_Origen_Total", "Trad_PaB_Actualizado_Total",
        "Trad_Descuento_Actual", "Trad_Pago_Actual", "Trad_Ingreso_Actual",
        "Trad_Apartado_Neto", "Trad_Descuento_Esperado_Ponderado",
        "Trad_Num_Deudas", "Trad_Deposito_Extra_Valor",
        "Trad_Deposito_Extra_Aplica", "Trad_Deposito_Extra_Detalle",
        "Trad_Contraoferta_Valor", "Trad_Contraoferta_Aplica",
        "Trad_Contraoferta_Detalle", "Trad_Liq_Insta_Aplica",
        "Trad_Liq_Insta_Detalle", "Trad_Viable",
    ]
    if deudas is None or deudas.empty:
        return pd.DataFrame(columns=columnas)

    df = deudas.copy()
    df["_Desc_Ponderado"] = df["Descuento_Esperado"] * df["PaB_Origen"]
    agg = df.groupby(group_col, as_index=False).agg(
        Trad_PaB_Origen_Total=("PaB_Origen", "sum"),
        Trad_PaB_Actualizado_Total=("PaB_Actualizado", "sum"),
        Trad_Pricing=("Pricing", "first"),
        Trad_Apartado_Neto=("Apartado_Neto", "max"),
        Trad_Desc_Ponderado_Suma=("_Desc_Ponderado", "sum"),
        Trad_Num_Deudas=("Id_Deuda", "nunique"),
    )

    saldos_map = saldos.get("Saldos", {}) if isinstance(saldos, dict) else {}
    por_cobrar_map = saldos.get("PorCobrar", {}) if isinstance(saldos, dict) else {}
    referencia_por_grupo = df.groupby(group_col)["Referencia"].first().to_dict()
    agg["_Referencia"] = agg[group_col].map(referencia_por_grupo)
    agg["_Ahorro"] = agg["_Referencia"].map(lambda r: _a_float(saldos_map.get(r, 0)))
    agg["_Por_Cobrar"] = agg["_Referencia"].map(lambda r: _a_float(por_cobrar_map.get(r, 0)))

    origen = agg["Trad_PaB_Origen_Total"].astype(float)
    actualizado = agg["Trad_PaB_Actualizado_Total"].astype(float)
    pricing = agg["Trad_Pricing"].astype(float)
    ahorro = agg["_Ahorro"].astype(float)
    por_cobrar = agg["_Por_Cobrar"].astype(float)
    apartado = agg["Trad_Apartado_Neto"].astype(float)

    agg["Trad_Descuento_Actual"] = np.where(
        origen > 0, 1 - (actualizado / origen.replace(0, np.nan)), 0.0
    )
    agg["Trad_Descuento_Actual"] = agg["Trad_Descuento_Actual"].fillna(0.0).clip(0.0, 1.0)
    agg["Trad_Descuento_Esperado_Ponderado"] = np.where(
        origen > 0,
        agg["Trad_Desc_Ponderado_Suma"] / origen.replace(0, np.nan),
        0.0,
    )
    agg["Trad_Descuento_Esperado_Ponderado"] = agg["Trad_Descuento_Esperado_Ponderado"].fillna(0.0)
    agg["Trad_Pago_Actual"] = actualizado
    agg["Trad_Ingreso_Actual"] = np.maximum((origen - actualizado) * pricing, 0.0)

    comision = np.maximum((origen - actualizado) * pricing * IVA, 0.0)
    deposito = actualizado + comision + MONTO_ADICIONAL_DEPOSITO - (ahorro - por_cobrar)
    denominador = origen * (pricing * IVA - 1)
    contraoferta = np.where(
        denominador != 0,
        (ahorro - por_cobrar - origen - MONTO_ADICIONAL_DEPOSITO) / denominador,
        0.0,
    )

    agg["Trad_Deposito_Extra_Valor"] = deposito
    agg["Trad_Contraoferta_Valor"] = contraoferta

    # Depósito Extra: aplica si es >= 0 y cabe en 3 apartados o en 1M COP
    deposito_valido = deposito >= 0
    deposito_por_monto = deposito <= UMBRAL_DEPOSITO_EXTRA_MONTO
    deposito_por_apartado = np.where(
        apartado > 0,
        deposito / apartado.replace(0, np.nan) <= UMBRAL_DEPOSITO_EXTRA_APARTADOS,
        False,
    )
    agg["Trad_Deposito_Extra_Aplica"] = (
        deposito_valido & (deposito_por_monto | deposito_por_apartado)
    )

    # ContraOferta Viable: debe superar el Descuento Actual, ser <= 95% y
    # no superar el Descuento Esperado + 20 puntos.
    agg["Trad_Contraoferta_Aplica"] = (
        (contraoferta > agg["Trad_Descuento_Actual"])
        & (contraoferta <= UMBRAL_CONTRACOFERTA_MAXIMA)
        & (contraoferta <= agg["Trad_Descuento_Esperado_Ponderado"] + MARGEN_DESCUENTO_ESPERADO)
    )

    # Liquidación Instantánea Tradicional: exige un descuento mínimo real
    # (3% por defecto). Sin ese descuento, tener ahorro suficiente no basta.
    # Luego aplica si no requiere depósito o si el descuento actual ya alcanza
    # la contraoferta necesaria.
    agg["Trad_Liq_Insta_Aplica"] = (
        (agg["Trad_Descuento_Actual"] >= UMBRAL_DESCUENTO_MINIMO_LIQ_INSTA)
        & (
            (deposito < 0)
            | (agg["Trad_Descuento_Actual"] >= contraoferta)
        )
    )

    # Viabilidad: Pago Total (PaB actual + comisión con IVA + 20k) <= Ahorro - Por Cobrar
    pago_total = actualizado + agg["Trad_Ingreso_Actual"] * IVA + MONTO_ADICIONAL_DEPOSITO
    agg["Trad_Viable"] = pago_total <= (ahorro - por_cobrar)

    agg["Trad_Deposito_Extra_Detalle"] = [
        "Depósito requerido: ${:,.0f}; {:.2f} apartados netos.".format(
            deposito_valor,
            (deposito_valor / apartado_valor) if apartado_valor > 0 else 0.0,
        )
        for deposito_valor, apartado_valor in zip(
            agg["Trad_Deposito_Extra_Valor"].to_numpy(),
            agg["Trad_Apartado_Neto"].to_numpy(),
        )
    ]
    agg["Trad_Contraoferta_Detalle"] = [
        "Descuento requerido: {:.1%}; pago estimado: ${:,.0f}.".format(
            contraoferta_valor,
            origen_valor * (1 - contraoferta_valor),
        )
        for contraoferta_valor, origen_valor in zip(
            agg["Trad_Contraoferta_Valor"].to_numpy(),
            agg["Trad_PaB_Origen_Total"].to_numpy(),
        )
    ]
    agg["Trad_Liq_Insta_Detalle"] = [
        "Descuento actual: {:.1%}; descuento requerido: {:.1%}.".format(
            descuento_actual, contraoferta_valor
        )
        for descuento_actual, contraoferta_valor in zip(
            agg["Trad_Descuento_Actual"].to_numpy(),
            agg["Trad_Contraoferta_Valor"].to_numpy(),
        )
    ]
    return agg[columnas]

# Función Auxiliar para Calcular las Métricas de Crédito
def _calcular_metricas_credito_masivas(
    *,
    deudas: pd.DataFrame,
    group_col: str = "Referencia",
) -> pd.DataFrame:
    """Calcula las métricas y oportunidades de Crédito por grupo.

    Solo debe recibir deudas de unidades que se analizan por Crédito. Por la
    regla de portafolios, una unidad entra completa o no entra: si alguna deuda
    no tiene PaB Ideal, todo el portafolio queda fuera de Crédito.

    Args:
        deudas (pd.DataFrame): Deudas de las unidades habilitadas por Crédito.
        group_col (str): ``Referencia`` para el resumen o ``Unidad_Id`` para el
            detalle por portafolio.
    """
    columnas = [
        group_col, "Cred_PaB_Origen_Total", "Cred_PaB_Actualizado_Total",
        "Cred_PaB_Ideal_Total", "Cred_Descuento_Actual", "Cred_Pago_Actual",
        "Cred_Num_Deudas", "Cred_Descuento_Esperado_Ponderado",
        "Cred_Deposito_Extra_Valor", "Cred_Deposito_Extra_Aplica",
        "Cred_Deposito_Extra_Detalle", "Cred_Contraoferta_Valor",
        "Cred_Contraoferta_Aplica", "Cred_Contraoferta_Detalle",
        "Cred_Liq_Insta_Aplica", "Cred_Liq_Insta_Detalle", "Cred_Viable",
    ]
    if deudas is None or deudas.empty:
        return pd.DataFrame(columns=columnas)

    df = deudas.copy()
    df["_Desc_Ponderado"] = df["Descuento_Esperado"] * df["PaB_Origen"]
    agg = df.groupby(group_col, as_index=False).agg(
        Cred_PaB_Origen_Total=("PaB_Origen", "sum"),
        Cred_PaB_Actualizado_Total=("PaB_Actualizado", "sum"),
        Cred_PaB_Ideal_Total=("PaB_Ideal", "sum"),
        Cred_Apartado_Neto=("Apartado_Neto", "max"),
        Cred_Desc_Ponderado_Suma=("_Desc_Ponderado", "sum"),
        Cred_Num_Deudas=("Id_Deuda", "nunique"),
    )

    origen = agg["Cred_PaB_Origen_Total"].astype(float)
    actualizado = agg["Cred_PaB_Actualizado_Total"].astype(float)
    pab_ideal = agg["Cred_PaB_Ideal_Total"].astype(float)
    apartado = agg["Cred_Apartado_Neto"].astype(float)

    agg["Cred_Descuento_Actual"] = np.where(
        origen > 0, 1 - (actualizado / origen.replace(0, np.nan)), 0.0
    )
    agg["Cred_Descuento_Actual"] = agg["Cred_Descuento_Actual"].fillna(0.0).clip(0.0, 1.0)
    agg["Cred_Descuento_Esperado_Ponderado"] = np.where(
        origen > 0,
        agg["Cred_Desc_Ponderado_Suma"] / origen.replace(0, np.nan),
        0.0,
    )
    agg["Cred_Descuento_Esperado_Ponderado"] = agg["Cred_Descuento_Esperado_Ponderado"].fillna(0.0)
    agg["Cred_Pago_Actual"] = actualizado

    deposito = actualizado + MONTO_ADICIONAL_DEPOSITO - pab_ideal
    contraoferta = np.where(
        origen > 0,
        1 - ((pab_ideal + MONTO_ADICIONAL_DEPOSITO) / origen.replace(0, np.nan)),
        0.0,
    )
    contraoferta = np.nan_to_num(contraoferta, nan=0.0)

    agg["Cred_Deposito_Extra_Valor"] = deposito
    agg["Cred_Contraoferta_Valor"] = contraoferta
    agg["Cred_Viable"] = actualizado <= (pab_ideal + MONTO_ADICIONAL_DEPOSITO)

    deposito_valido = deposito >= 0
    deposito_por_monto = deposito <= UMBRAL_DEPOSITO_EXTRA_MONTO
    deposito_por_apartado = np.where(
        apartado > 0,
        deposito / apartado.replace(0, np.nan) <= UMBRAL_DEPOSITO_EXTRA_APARTADOS,
        False,
    )
    agg["Cred_Deposito_Extra_Aplica"] = (
        deposito_valido & (deposito_por_monto | deposito_por_apartado)
    )
    agg["Cred_Contraoferta_Aplica"] = (
        (contraoferta > agg["Cred_Descuento_Actual"])
        & (contraoferta <= UMBRAL_CONTRACOFERTA_MAXIMA)
        & (contraoferta <= agg["Cred_Descuento_Esperado_Ponderado"] + MARGEN_DESCUENTO_ESPERADO)
    )
    agg["Cred_Liq_Insta_Aplica"] = (deposito < 0) | (
        (agg["Cred_Descuento_Actual"] >= contraoferta)
        & (agg["Cred_Descuento_Actual"] != 0)
    )

    agg["Cred_Deposito_Extra_Detalle"] = [
        "Depósito requerido: ${:,.0f}; {:.2f} apartados netos.".format(
            deposito_valor,
            (deposito_valor / apartado_valor) if apartado_valor > 0 else 0.0,
        )
        for deposito_valor, apartado_valor in zip(
            agg["Cred_Deposito_Extra_Valor"].to_numpy(),
            agg["Cred_Apartado_Neto"].to_numpy(),
        )
    ]
    agg["Cred_Contraoferta_Detalle"] = [
        "Descuento requerido: {:.1%}; pago estimado: ${:,.0f}.".format(
            contraoferta_valor,
            origen_valor * (1 - contraoferta_valor),
        )
        for contraoferta_valor, origen_valor in zip(
            agg["Cred_Contraoferta_Valor"].to_numpy(),
            agg["Cred_PaB_Origen_Total"].to_numpy(),
        )
    ]
    agg["Cred_Liq_Insta_Detalle"] = [
        "Descuento actual: {:.1%}; descuento requerido: {:.1%}.".format(
            descuento_actual, contraoferta_valor
        )
        for descuento_actual, contraoferta_valor in zip(
            agg["Cred_Descuento_Actual"].to_numpy(),
            agg["Cred_Contraoferta_Valor"].to_numpy(),
        )
    ]
    return agg[columnas]

# --- Construcción de Unidades de Análisis (Portafolios) ---

# Función Auxiliar para Resolver el PaB_Actualizado desde Actualizaciones
def _resolver_pab_actualizado_actualizaciones(
    *,
    deudas: pd.DataFrame,
    actualizaciones_df: Optional[pd.DataFrame],
    masivas_df: Optional[pd.DataFrame] = None,
    solicitudes_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Resuelve el PaB_Actualizado de cada deuda desde las Actualizaciones.

    Replica la regla de la calculadora individual:
    - Se toma la actualización más reciente por deuda.
    - Solo se confía en ``ETIQUETAS_ACT_CONFIABLES``.
    - Si la etiqueta no es confiable o el PaB viene en 0, se usa ``PaB_Origen``.
    - Para ``ACTUALIZADO_ALIANZAS`` se cruza con Masivas y Solicitudes.
    - El valor se acota al ``PaB_Origen``.

    Args:
        deudas (pd.DataFrame): Deudas con ``Id_Deuda`` y ``PaB_Origen``.
        actualizaciones_df (Optional[pd.DataFrame]): Actualizaciones del MEC.
        masivas_df (Optional[pd.DataFrame]): Masivas para ACTUALIZADO_ALIANZAS.
        solicitudes_df (Optional[pd.DataFrame]): Solicitudes para ACTUALIZADO_ALIANZAS.

    Returns:
        pd.DataFrame: Copia de ``deudas`` con ``PaB_Actualizado_Deuda``,
        ``Etiqueta_Act_Deuda``, ``Fecha_Act_Deuda`` y ``Pago_Confiable``.
    """
    resultado = deudas.copy()
    resultado["PaB_Actualizado_Deuda"] = pd.to_numeric(
        resultado["PaB_Origen"], errors="coerce"
    ).fillna(0.0)
    resultado["Etiqueta_Act_Deuda"] = ""
    resultado["Fecha_Act_Deuda"] = pd.NaT
    resultado["Pago_Confiable"] = False
    resultado["Pab_Fila_Deuda"] = resultado["PaB_Actualizado_Deuda"]

    if actualizaciones_df is None or actualizaciones_df.empty:
        return resultado
    columnas_requeridas = {"Id_Deuda", "Fecha_Act", "Etiqueta_Act", "PaB_Actualizado"}
    if not columnas_requeridas.issubset(set(actualizaciones_df.columns)):
        return resultado

    # Paso 1: Quedarnos con la Última Actualización de Cada Deuda
    acts = _deduplicar_actualizaciones(actualizaciones_df)
    if acts.empty:
        return resultado
    acts["Etiqueta_Act"] = (
        acts["Etiqueta_Act"].fillna("").astype(str).str.strip().str.upper()
    )
    acts["PaB_Actualizado"] = pd.to_numeric(
        acts["PaB_Actualizado"], errors="coerce"
    )
    acts = acts.sort_values(by="Fecha_Act", kind="stable")
    acts = acts.drop_duplicates(subset=["Id_Deuda"], keep="last")

    mapa_etiqueta = acts.set_index("Id_Deuda")["Etiqueta_Act"].to_dict()
    mapa_fecha = acts.set_index("Id_Deuda")["Fecha_Act"].to_dict()
    mapa_pab = acts.set_index("Id_Deuda")["PaB_Actualizado"].to_dict()

    resultado["Etiqueta_Act_Deuda"] = (
        resultado["Id_Deuda"].map(mapa_etiqueta).fillna("").astype(str)
    )
    resultado["Fecha_Act_Deuda"] = pd.to_datetime(
        resultado["Id_Deuda"].map(mapa_fecha), errors="coerce"
    )
    resultado["Pab_Fila_Deuda"] = pd.to_numeric(
        resultado["Id_Deuda"].map(mapa_pab), errors="coerce"
    ).fillna(resultado["PaB_Actualizado_Deuda"])

    # Paso 2: Resolver ACTUALIZADO_ALIANZAS con el Cruce de Fuentes.
    # Precalculamos los mapas una sola vez para evitar recorrer Masivas y
    # Solicitudes completas por cada actualización (O(n*m) -> O(n+m)).
    confiable = resultado["Etiqueta_Act_Deuda"].isin(ETIQUETAS_ACT_CONFIABLES)
    mask_alianzas = confiable & resultado["Etiqueta_Act_Deuda"].eq("ACTUALIZADO_ALIANZAS")
    if mask_alianzas.any():
        mapa_masivas = _mapa_ultimo_descuento_masivas(masivas_df)
        mapa_solicitudes = _mapa_ultima_solicitud_exitosa(solicitudes_df)
        for indice in resultado.index[mask_alianzas]:
            deuda = resultado.at[indice, "Id_Deuda"]
            info_masiva = mapa_masivas.get(deuda)
            info_solicitud = mapa_solicitudes.get(deuda)
            if info_masiva is None and info_solicitud is None:
                continue

            pab_fila = _a_float(
                resultado.at[indice, "Pab_Fila_Deuda"], default=0.0
            )
            candidatos = []
            if info_masiva is not None:
                candidatos.append({
                    "pab": pab_fila if info_masiva["pab"] is None else info_masiva["pab"],
                    "fecha": info_masiva["fecha"],
                })
            if info_solicitud is not None:
                candidatos.append({
                    "pab": pab_fila if info_solicitud["pab"] is None else info_solicitud["pab"],
                    "fecha": info_solicitud["fecha"],
                })

            candidatos_con_fecha = [
                candidato for candidato in candidatos
                if candidato["fecha"] is not None
                and not pd.isna(candidato["fecha"])
            ]
            if not candidatos_con_fecha:
                # Sin fechas comparables se mantiene el valor de la fila.
                continue
            candidatos_con_fecha.sort(key=lambda c: c["fecha"], reverse=True)
            resultado.at[indice, "Pab_Fila_Deuda"] = max(
                candidatos_con_fecha[0]["pab"], 0.0
            )

    # Paso 3: Aplicar las Reglas de Confianza y Acotar al Origen
    pab_fila = pd.to_numeric(resultado["Pab_Fila_Deuda"], errors="coerce")
    origen = pd.to_numeric(resultado["PaB_Origen"], errors="coerce").fillna(0.0)
    resultado["Pago_Confiable"] = confiable & (pab_fila.fillna(0.0) > 0)
    pab_actualizado = np.where(
        confiable & (pab_fila.fillna(0.0) > 0),
        pab_fila.fillna(0.0),
        origen,
    )
    resultado["PaB_Actualizado_Deuda"] = np.minimum(pab_actualizado, origen)
    return resultado

# Función Auxiliar para Construir las Unidades desde Actualizaciones
def _construir_unidades_actualizaciones(
    *,
    deudas: pd.DataFrame,
    ventana_segundos: int = VENTANA_PORTAFOLIO_SEGUNDOS,
) -> pd.DataFrame:
    """Asigna ``Unidad_Id`` a las deudas según Actualizaciones o Bancos.

    Reglas:
    - Si el cliente no tiene ninguna actualización, se agrupan las deudas por
      los bancos de ``BANCOS_PORTAFOLIO`` (solo grupos de 2 o más deudas).
    - Si el cliente tiene actualizaciones, solo se agrupan las actualizaciones
      confiables consecutivas con la misma etiqueta y a ≤45 s. Las demás deudas
      quedan como unidades individuales.
    - Una deuda con actualización no confiable no forma portafolio de pago.

    Args:
        deudas (pd.DataFrame): Deudas con las columnas resueltas de actualización.
        ventana_segundos (int): Ventana máxima entre actualizaciones del grupo.

    Returns:
        pd.DataFrame: Deudas con ``Unidad_Id``, ``Tipo_Unidad`` y ``Etiqueta_Unidad``.
    """
    resultado = deudas.copy().reset_index(drop=True)
    resultado["Unidad_Id"] = ""
    resultado["Tipo_Unidad"] = "Deuda individual"
    resultado["Etiqueta_Unidad"] = "Deuda individual"
    resultado["Pago_Compartido"] = False
    if "Banco" not in resultado.columns:
        resultado["Banco"] = ""
    if resultado.empty:
        return resultado

    referencia = resultado["Referencia"].astype(str)
    banco_normalizado = resultado["Banco"].astype(str).str.strip()

    # Paso 1: Detectar si el Cliente Tiene Actualizaciones
    con_actualizacion = resultado["Fecha_Act_Deuda"].notna()
    referencias_con_act = set(resultado.loc[con_actualizacion, "Referencia"])

    # Paso 2a: Sin Actualizaciones -> Agrupar por BANCOS_PORTAFOLIO
    sin_actualizacion = ~resultado["Referencia"].isin(referencias_con_act)
    candidatas_banco = sin_actualizacion & banco_normalizado.isin(BANCOS_PORTAFOLIO)
    if candidatas_banco.any():
        grupos_banco = pd.DataFrame({
            "Referencia": referencia[candidatas_banco],
            "Banco": banco_normalizado[candidatas_banco],
        })
        conteos_banco = grupos_banco.groupby(
            ["Referencia", "Banco"], sort=False
        )["Referencia"].transform("size")
        indices_banco = conteos_banco.index[conteos_banco > 1]
        if len(indices_banco) > 0:
            refs_banco = referencia[indices_banco]
            bancos_grupo = banco_normalizado[indices_banco]
            resultado.loc[indices_banco, "Unidad_Id"] = (
                "BANCO::" + refs_banco + "::" + bancos_grupo
            )
            resultado.loc[indices_banco, "Tipo_Unidad"] = "Portafolio Banco"
            resultado.loc[indices_banco, "Etiqueta_Unidad"] = (
                "Portafolio " + bancos_grupo + " (banco)"
            )

    # Paso 2b: Con Actualizaciones -> Agrupar Actualizaciones Confiables
    pago_confiable = (
        resultado["Pago_Confiable"].fillna(False).astype(bool)
        if "Pago_Confiable" in resultado.columns
        else pd.Series(False, index=resultado.index)
    )
    indices_confiables = resultado.index[
        (~sin_actualizacion) & pago_confiable
    ]
    if len(indices_confiables) > 0:
        candidatas = resultado.loc[indices_confiables].copy()
        claves_act = ["Referencia", "Etiqueta_Act_Deuda"]
        candidatas = candidatas.sort_values(
            by=claves_act + ["Fecha_Act_Deuda"], kind="stable"
        )
        candidatas["_Gap"] = candidatas.groupby(
            claves_act
        )["Fecha_Act_Deuda"].diff().dt.total_seconds()
        candidatas["_Nuevo"] = (
            candidatas["_Gap"].isna()
            | (candidatas["_Gap"] > float(ventana_segundos))
        )
        candidatas["_Grupo"] = candidatas.groupby(
            claves_act
        )["_Nuevo"].cumsum()
        tamanos_grupo = candidatas.groupby(
            claves_act + ["_Grupo"], sort=False
        )["Referencia"].transform("size")
        candidatas = candidatas[tamanos_grupo > 1]
        if not candidatas.empty:
            fecha_minima = candidatas.groupby(
                claves_act + ["_Grupo"], sort=False
            )["Fecha_Act_Deuda"].transform("min")
            resultado.loc[candidatas.index, "Unidad_Id"] = (
                "ACT::" + candidatas["Referencia"].astype(str)
                + "::" + candidatas["Etiqueta_Act_Deuda"].astype(str)
                + "::" + candidatas["_Grupo"].astype(int).astype(str)
            )
            resultado.loc[candidatas.index, "Tipo_Unidad"] = (
                "Portafolio Actualizaciones"
            )
            resultado.loc[candidatas.index, "Etiqueta_Unidad"] = (
                "Portafolio "
                + candidatas["Etiqueta_Act_Deuda"].astype(str).str.title()
                + " · "
                + fecha_minima.dt.strftime("%d/%m %H:%M")
            )

    # Paso 3: Las Deudas que No Quedaron en un Portafolio son Individuales
    indices_individuales = resultado.index[resultado["Unidad_Id"] == ""]
    if len(indices_individuales) > 0:
        ids_individuales = resultado.loc[
            indices_individuales, "Id_Deuda"
        ].apply(_normalizar_id_deuda)
        resultado.loc[indices_individuales, "Unidad_Id"] = (
            "DEUDA::" + ids_individuales
        )
        resultado.loc[indices_individuales, "Etiqueta_Unidad"] = (
            "Deuda " + ids_individuales
        )

    return resultado

# Función Auxiliar para Construir las Unidades desde Masivas
def _construir_unidades_masivas(*, deudas: pd.DataFrame) -> pd.DataFrame:
    """Asigna ``Unidad_Id`` usando ``Metadata.Id_Portafolio`` de Masivas.

    Un ``Id_Portafolio`` no vacío indica que la deuda pertenece a un portafolio;
    si está vacío, la deuda se analiza individualmente.
    """
    resultado = deudas.copy().reset_index(drop=True)
    if "Id_Portafolio" not in resultado.columns:
        resultado["Id_Portafolio"] = ""
    id_portafolio = resultado["Id_Portafolio"].fillna("").astype(str).str.strip()
    mascara_portafolio = (
        id_portafolio.ne("")
        & ~id_portafolio.str.lower().isin(["nan", "none", "<na>"])
    )
    resultado["Unidad_Id"] = np.where(
        mascara_portafolio,
        "MAS::" + id_portafolio,
        "DEUDA::" + resultado["Id_Deuda"].astype(str),
    )
    resultado["Tipo_Unidad"] = np.where(
        mascara_portafolio, "Portafolio Masivas", "Deuda individual"
    )
    resultado["Etiqueta_Unidad"] = np.where(
        mascara_portafolio,
        "Portafolio Masivas · " + id_portafolio.str.slice(0, 8),
        "Deuda " + resultado["Id_Deuda"].astype(str),
    )
    resultado["Pago_Compartido"] = False
    return resultado

# Función Auxiliar para Aplicar el Pago de Cada Unidad a sus Deudas
def _aplicar_pago_unidades(
    *,
    deudas: pd.DataFrame,
    solo_masivas: bool,
) -> pd.DataFrame:
    """Calcula el pago actual de cada unidad y lo distribuye entre sus deudas.

    Para portafolios de Masivas se usa ``PaB_Portafolio`` cuando está completo;
    si falta o el grupo está incompleto, se usa la suma de ``PaB_Propuesta``.
    Para portafolios de Actualizaciones, si todas las deudas tienen el mismo
    valor se usa una sola vez; si difieren, se suman. En ambos casos el total
    se distribuye por ``PaB_Origen`` para que la suma por deuda coincida con el
    total de la unidad.
    """
    resultado = deudas.copy().reset_index(drop=True)
    resultado["PaB_Actualizado_Deuda_Original"] = pd.to_numeric(
        resultado.get("PaB_Actualizado_Deuda", resultado["PaB_Origen"]),
        errors="coerce",
    ).fillna(0.0)
    resultado["PaB_Actualizado"] = resultado["PaB_Actualizado_Deuda_Original"]
    resultado["_PaB_Actualizado_Unidad"] = resultado["PaB_Actualizado_Deuda_Original"]
    resultado["Pago_Compartido"] = False
    if "PaB_Masiva" not in resultado.columns:
        resultado["PaB_Masiva"] = 0.0
    if "PaB_Portafolio" not in resultado.columns:
        resultado["PaB_Portafolio"] = np.nan
    if "Portafolio_Completo" not in resultado.columns:
        resultado["Portafolio_Completo"] = False
    if resultado.empty:
        return resultado

    # Trabajamos con Series alineadas al índice para evitar un bucle por unidad.
    unidad = resultado["Unidad_Id"]
    origen = pd.to_numeric(resultado["PaB_Origen"], errors="coerce").fillna(0.0)
    valores_actuales = pd.to_numeric(
        resultado["PaB_Actualizado_Deuda_Original"], errors="coerce"
    ).fillna(0.0)
    tipo_unidad = resultado.groupby(
        "Unidad_Id", sort=False
    )["Tipo_Unidad"].transform("first")
    total_origen = origen.groupby(unidad, sort=False).transform("sum")
    num_deudas = origen.groupby(unidad, sort=False).transform("size")
    total = valores_actuales.groupby(unidad, sort=False).transform("first")
    pago_compartido = pd.Series(False, index=resultado.index)

    # Paso 1: Determinar el Total y si el Pago es Compartido
    if solo_masivas:
        es_portafolio = tipo_unidad == "Portafolio Masivas"
        pab_portafolio = pd.to_numeric(
            resultado["PaB_Portafolio"], errors="coerce"
        )
        pab_portafolio_grupo = pab_portafolio.groupby(
            unidad, sort=False
        ).transform("first")
        portafolio_completo = (
            resultado["Portafolio_Completo"].fillna(False).astype(bool)
            .groupby(unidad, sort=False).transform("min").astype(bool)
        )
        usar_total_portafolio = (
            es_portafolio
            & pab_portafolio_grupo.notna()
            & (pab_portafolio_grupo > 0)
            & portafolio_completo
        )
        pab_masiva = pd.to_numeric(
            resultado["PaB_Masiva"], errors="coerce"
        ).fillna(0.0).groupby(unidad, sort=False).transform("sum")
        total = pd.Series(
            np.where(
                es_portafolio,
                np.where(
                    usar_total_portafolio,
                    pab_portafolio_grupo.fillna(0.0),
                    pab_masiva,
                ),
                total,
            ),
            index=resultado.index,
        )
        pago_compartido = usar_total_portafolio
    else:
        es_actualizaciones = tipo_unidad == "Portafolio Actualizaciones"
        es_banco = tipo_unidad == "Portafolio Banco"
        valores_redondeados = valores_actuales.round(2)
        valores_iguales = valores_redondeados.groupby(
            unidad, sort=False
        ).transform("nunique") == 1
        usa_pago_unico = es_actualizaciones & valores_iguales & (total > 0)
        suma_valores = valores_actuales.groupby(
            unidad, sort=False
        ).transform("sum")
        total = pd.Series(
            np.select(
                [usa_pago_unico, es_actualizaciones, es_banco],
                [total, suma_valores, total_origen],
                default=total,
            ),
            index=resultado.index,
        )
        pago_compartido = usa_pago_unico

    total = pd.to_numeric(total, errors="coerce").fillna(0.0).clip(lower=0.0)
    total = pd.Series(
        np.where(total_origen > 0, np.minimum(total, total_origen), total),
        index=resultado.index,
    )

    # Paso 2: Distribuir el Total por Deuda
    denominador_origen = total_origen.where(total_origen > 0, np.nan)
    pagos_por_origen = (total * origen / denominador_origen).fillna(0.0)
    pagos = pd.Series(
        np.where(
            pago_compartido & (total_origen > 0),
            pagos_por_origen,
            valores_actuales,
        ),
        index=resultado.index,
    )

    # Garantizar que la suma por deuda coincida con el total de la unidad
    suma_pagos = pagos.groupby(unidad, sort=False).transform("sum")
    requiere_ajuste = (suma_pagos > 0) & ~np.isclose(suma_pagos, total)
    factor_ajuste = (
        total / suma_pagos.where(suma_pagos > 0, np.nan)
    ).fillna(1.0)
    pagos = pd.Series(
        np.where(requiere_ajuste, pagos * factor_ajuste, pagos),
        index=resultado.index,
    )
    requiere_distribucion = (suma_pagos <= 0) & (total > 0)
    pagos_iguales = (total / num_deudas.where(num_deudas > 0, np.nan)).fillna(0.0)
    pagos = pd.Series(
        np.where(
            requiere_distribucion,
            np.where(total_origen > 0, pagos_por_origen, pagos_iguales),
            pagos,
        ),
        index=resultado.index,
    )

    resultado["PaB_Actualizado"] = pagos.to_numpy()
    resultado["_PaB_Actualizado_Unidad"] = total.to_numpy()
    resultado["Pago_Compartido"] = pago_compartido.to_numpy()

    return resultado

# Función Auxiliar para Construir la Tabla de Unidades
def _construir_tabla_unidades(*, deudas: pd.DataFrame) -> pd.DataFrame:
    """Agrega una fila por ``Unidad_Id`` con sus métricas base."""
    df = deudas.copy()
    if "Id_Portafolio" not in df.columns:
        df["Id_Portafolio"] = ""
    df["_Desc_Ponderado"] = df["Descuento_Esperado"] * df["PaB_Origen"]
    unidades = df.groupby("Unidad_Id", as_index=False).agg(
        Referencia=("Referencia", "first"),
        Tipo_Unidad=("Tipo_Unidad", "first"),
        Etiqueta_Unidad=("Etiqueta_Unidad", "first"),
        Id_Portafolio=("Id_Portafolio", "first"),
        Num_Deudas=("Id_Deuda", "nunique"),
        PaB_Origen_Total=("PaB_Origen", "sum"),
        PaB_Actualizado_Total=("_PaB_Actualizado_Unidad", "first"),
        Pago_Compartido=("Pago_Compartido", "first"),
        Pricing=("Pricing", "first"),
        Apartado_Neto=("Apartado_Neto", "max"),
        PaB_Ideal_Total=("PaB_Ideal", "sum"),
        Tiene_Todas_PaB_Ideal=("Tiene_PaB_Ideal", "all"),
        Desc_Ponderado_Suma=("_Desc_Ponderado", "sum"),
    )
    unidades["Id_Portafolio"] = (
        unidades["Id_Portafolio"].fillna("").astype(str).replace("nan", "")
    )
    origen = unidades["PaB_Origen_Total"].astype(float)
    actualizado = unidades["PaB_Actualizado_Total"].astype(float)
    unidades["Descuento_Actual"] = np.where(
        origen > 0,
        1 - (actualizado / origen.replace(0, np.nan)),
        0.0,
    )
    unidades["Descuento_Actual"] = (
        pd.Series(unidades["Descuento_Actual"]).fillna(0.0).clip(0.0, 1.0)
    )
    unidades["Ingreso_Actual"] = np.maximum(
        (origen - actualizado) * unidades["Pricing"].astype(float), 0.0
    )
    unidades["Descuento_Esperado_Ponderado"] = np.where(
        origen > 0,
        unidades["Desc_Ponderado_Suma"] / origen.replace(0, np.nan),
        0.0,
    )
    unidades["Descuento_Esperado_Ponderado"] = (
        pd.Series(unidades["Descuento_Esperado_Ponderado"]).fillna(0.0)
    )
    df["_Id_Deuda_Norm"] = df["Id_Deuda"].apply(_normalizar_id_deuda)
    deudas_por_unidad: dict[str, list[str]] = {}
    for unidad, id_deuda in zip(
        df["Unidad_Id"].to_numpy(), df["_Id_Deuda_Norm"].to_numpy()
    ):
        deudas_unidad = deudas_por_unidad.get(unidad)
        if deudas_unidad is None:
            deudas_por_unidad[unidad] = [id_deuda]
        elif id_deuda not in deudas_unidad:
            deudas_unidad.append(id_deuda)
    for deudas_unidad in deudas_por_unidad.values():
        deudas_unidad.sort()
    unidades["Deudas"] = unidades["Unidad_Id"].map(deudas_por_unidad)
    unidades["Deudas"] = unidades["Deudas"].apply(
        lambda valor: valor if isinstance(valor, list) else []
    )
    return unidades

# Función Auxiliar para Agregar el Detalle de Deudas a Cada Unidad
def _agregar_detalle_unidades(
    *,
    unidades: pd.DataFrame,
    deudas: pd.DataFrame,
) -> pd.DataFrame:
    """Agrega ``Deudas_Detalle`` a la tabla de unidades."""
    df = deudas.copy()
    columnas_default = {
        "Banco": "",
        "PaB_Ideal": 0.0,
        "Prospecto": "N/A",
        "Prob_Liq": 0.0,
        "Tiene_Masiva": False,
        "Casa_Cobro": "",
        "Fecha_Limite_Uso": pd.NaT,
        "Usa_Tradicional": False,
        "Usa_Credito": False,
        "PaB_Actualizado_Deuda_Original": 0.0,
        "_PaB_Actualizado_Unidad": 0.0,
        "Pago_Compartido": False,
        "Etiqueta_Act_Deuda": "",
        "Fecha_Act_Deuda": pd.NaT,
    }
    for columna, valor_default in columnas_default.items():
        if columna not in df.columns:
            df[columna] = valor_default

    pab_origen = pd.to_numeric(df["PaB_Origen"], errors="coerce").fillna(0.0)
    pab_actualizado = pd.to_numeric(df["PaB_Actualizado"], errors="coerce").fillna(0.0)
    descuento = np.where(
        pab_origen > 0,
        1 - (pab_actualizado / pab_origen.replace(0, np.nan)),
        0.0,
    )
    descuento = np.clip(descuento, 0.0, 1.0)

    registros = [
        {
            "Id_Deuda": id_deuda,
            "Banco": banco,
            "PaB_Origen": origen,
            "PaB_Actualizado": actualizado,
            "PaB_Actualizado_Original": actualizado_original,
            "Descuento_Deuda": descuento_deuda,
            "PaB_Ideal": pab_ideal,
            "Prospecto": prospecto,
            "Prob_Liq": prob_liq,
            "Tiene_Masiva": tiene_masiva,
            "Casa_Cobro": casa_cobro,
            "Fecha_Limite_Uso": fecha_limite,
            "Usa_Tradicional": usa_tradicional,
            "Usa_Credito": usa_credito,
            "Unidad_Id": unidad_id,
            "Etiqueta_Unidad": etiqueta_unidad,
            "Tipo_Unidad": tipo_unidad,
            "PaB_Actualizado_Unidad": pab_unidad,
            "Pago_Compartido": pago_compartido,
            "Etiqueta_Actualizacion": etiqueta_actualizacion,
            "Fecha_Actualizacion": fecha_actualizacion,
        }
        for (
            id_deuda, banco, origen, actualizado, actualizado_original,
            descuento_deuda, pab_ideal, prospecto, prob_liq, tiene_masiva,
            casa_cobro, fecha_limite, usa_tradicional, usa_credito,
            unidad_id, etiqueta_unidad, tipo_unidad, pab_unidad,
            pago_compartido, etiqueta_actualizacion, fecha_actualizacion,
        ) in zip(
            df["Id_Deuda"].apply(_normalizar_id_deuda).to_numpy(),
            df["Banco"].fillna("").astype(str).to_numpy(),
            pab_origen.to_numpy(),
            pab_actualizado.to_numpy(),
            pd.to_numeric(
                df["PaB_Actualizado_Deuda_Original"], errors="coerce"
            ).fillna(0.0).to_numpy(),
            descuento,
            pd.to_numeric(df["PaB_Ideal"], errors="coerce").fillna(0.0).to_numpy(),
            df["Prospecto"].fillna("N/A").replace("", "N/A").astype(str).to_numpy(),
            pd.to_numeric(df["Prob_Liq"], errors="coerce").fillna(0.0).to_numpy(),
            df["Tiene_Masiva"].fillna(False).astype(bool).to_numpy(),
            df["Casa_Cobro"].fillna("").astype(str).to_numpy(),
            df["Fecha_Limite_Uso"].to_numpy(),
            df["Usa_Tradicional"].fillna(False).astype(bool).to_numpy(),
            df["Usa_Credito"].fillna(False).astype(bool).to_numpy(),
            df["Unidad_Id"].fillna("").astype(str).to_numpy(),
            df["Etiqueta_Unidad"].fillna("").astype(str).to_numpy(),
            df["Tipo_Unidad"].fillna("").astype(str).to_numpy(),
            pd.to_numeric(
                df["_PaB_Actualizado_Unidad"], errors="coerce"
            ).fillna(0.0).to_numpy(),
            df["Pago_Compartido"].fillna(False).astype(bool).to_numpy(),
            df["Etiqueta_Act_Deuda"].fillna("").astype(str).to_numpy(),
            df["Fecha_Act_Deuda"].to_numpy(),
        )
    ]

    detalles_por_unidad: dict[str, list[dict[str, Any]]] = {}
    for unidad, registro in zip(df["Unidad_Id"].to_numpy(), registros):
        detalles_por_unidad.setdefault(unidad, []).append(registro)

    resultado = unidades.copy()
    resultado["Deudas_Detalle"] = resultado["Unidad_Id"].map(detalles_por_unidad)
    resultado["Deudas_Detalle"] = resultado["Deudas_Detalle"].apply(
        lambda valor: valor if isinstance(valor, list) else []
    )
    return resultado

# Función Auxiliar para Obtener los Valores de Ingreso de una Unidad
def _valores_ingreso_unidad(
    *,
    fila: Any,
    prefijo: str,
) -> tuple[float, float, float]:
    """Devuelve ``(DUM, PaB Actual, Pricing)`` de una unidad y un tipo.

    Se usan las columnas del bloque (``Trad_*`` o ``Cred_*``) y se cae a los
    totales generales de la unidad cuando el bloque no las trae. Esto permite
    reutilizar la función tanto con el registro interno del cálculo como con el
    diccionario de ``Portafolios_Detalle`` que consume la UI.
    """
    pricing = _a_float(fila.get("Pricing"), default=0.0)
    origen = _a_float(
        fila.get("{}_PaB_Origen_Total".format(prefijo)), default=np.nan
    )
    actualizado = _a_float(
        fila.get("{}_PaB_Actualizado_Total".format(prefijo)), default=np.nan
    )
    if pd.isna(origen):
        origen = _a_float(fila.get("PaB_Origen_Total"), default=np.nan)
    if pd.isna(origen):
        origen = _a_float(fila.get("PaB_Origen"), default=np.nan)
    if pd.isna(actualizado):
        actualizado = _a_float(
            fila.get("PaB_Actualizado_Total"), default=np.nan
        )
    if pd.isna(actualizado):
        actualizado = _a_float(fila.get("PaB_Actualizado"), default=np.nan)
    return (
        0.0 if pd.isna(origen) else float(origen),
        0.0 if pd.isna(actualizado) else float(actualizado),
        max(float(pricing), 0.0),
    )

# Función Auxiliar para Calcular el Ingreso de una Oportunidad Calculada
def _ingreso_estimado_oportunidad(
    *,
    fila: Any,
    prefijo: str,
    nombre: str,
    valor: Any,
) -> float:
    """Calcula el ingreso de una oportunidad de una unidad.

    ``Depósito Extra`` y ``Liquidación Instantánea`` usan el Descuento Actual
    de la unidad. ``ContraOferta Viable`` usa el descuento viable calculado
    (``DUM * contraoferta * Pricing``), que equivale a
    ``(DUM - pago viable) * Pricing``. Siempre se calcula sin IVA.
    """
    origen, actualizado, pricing = _valores_ingreso_unidad(
        fila=fila, prefijo=prefijo
    )
    if nombre == "ContraOferta Viable":
        descuento_viable = min(max(_a_float(valor), 0.0), 1.0)
        return max(origen * descuento_viable * pricing, 0.0)
    return max((origen - actualizado) * pricing, 0.0)

# Función Auxiliar para Calcular el Ingreso de una Oportunidad General
def _ingreso_estimado_oportunidad_general(
    *,
    fila: Any,
    deudas: Any,
) -> float:
    """Calcula el ingreso de Robo/IA con el Descuento Actual de sus deudas.

    A diferencia de las oportunidades por unidad, una oportunidad general
    cubre solo algunas deudas. Por eso el ingreso se calcula únicamente sobre
    las deudas involucradas y no sobre el total de la unidad.
    """
    pricing = max(_a_float(fila.get("Pricing"), default=0.0), 0.0)
    detalles = fila.get("Deudas_Detalle")
    if not isinstance(detalles, list) or not detalles:
        return 0.0
    mapa_detalles: dict[str, dict[str, Any]] = {}
    for detalle in detalles:
        if not isinstance(detalle, dict):
            continue
        id_deuda = _normalizar_id_deuda(detalle.get("Id_Deuda"))
        if id_deuda:
            mapa_detalles[id_deuda] = detalle
    total = 0.0
    for deuda in _a_lista(deudas):
        detalle = mapa_detalles.get(_normalizar_id_deuda(deuda))
        if detalle is None:
            continue
        origen = _a_float(detalle.get("PaB_Origen"), default=0.0)
        actualizado = _a_float(detalle.get("PaB_Actualizado"), default=0.0)
        total += max(origen - actualizado, 0.0)
    return max(total * pricing, 0.0)

# Función Auxiliar para Etiquetar el Tipo de Análisis de una Oportunidad
def _etiqueta_tipo_analisis(prefijo: str) -> str:
    """Traduce el prefijo interno al nombre del tipo de análisis."""
    return "Tradicional" if prefijo == "Trad" else "Crédito"

# Prioridad para Desempatar el Ingreso Estimado
PRIORIDAD_INGRESO_ESTIMADO = {
    "Liquidación Instantánea": 0,
    "ContraOferta Viable": 1,
    "Depósito Extra": 2,
    "Acuerdo para Robo": 3,
    "IA Liquidadora": 4,
}

# Función Auxiliar para Obtener la Prioridad de una Oportunidad
def _prioridad_ingreso(oportunidad: dict[str, Any]) -> int:
    """Devuelve la prioridad de desempate de una oportunidad."""
    return PRIORIDAD_INGRESO_ESTIMADO.get(
        str(oportunidad.get("nombre") or ""), 99
    )

# Función Auxiliar para Construir las Oportunidades de una Unidad
def _oportunidades_de_unidad(
    *,
    fila: Any,
    prefijo: str,
    nombres: list[str],
) -> list[dict[str, Any]]:
    """Construye las oportunidades aplicables de una unidad."""
    configuracion = {
        "Depósito Extra": {
            "aplica": "{}_Deposito_Extra_Aplica",
            "valor": "{}_Deposito_Extra_Valor",
            "detalle": "{}_Deposito_Extra_Detalle",
        },
        "ContraOferta Viable": {
            "aplica": "{}_Contraoferta_Aplica",
            "valor": "{}_Contraoferta_Valor",
            "detalle": "{}_Contraoferta_Detalle",
        },
        "Liquidación Instantánea": {
            "aplica": "{}_Liq_Insta_Aplica",
            "valor": "{}_Descuento_Actual",
            "detalle": "{}_Liq_Insta_Detalle",
        },
    }
    resultado = []
    for nombre in nombres:
        config = configuracion[nombre]
        if not _a_bool(fila.get(config["aplica"].format(prefijo), False)):
            continue
        valor = fila.get(config["valor"].format(prefijo), 0.0)
        resultado.append({
            "nombre": nombre,
            "valor": valor,
            "detalle": str(fila.get(config["detalle"].format(prefijo), "")),
            "ingreso_estimado": _ingreso_estimado_oportunidad(
                fila=fila,
                prefijo=prefijo,
                nombre=nombre,
                valor=valor,
            ),
            "tipo_analisis": _etiqueta_tipo_analisis(prefijo),
        })
    return resultado

# Función Auxiliar para Construir el Detalle de Portafolios de un Cliente
def _construir_portafolios_detalle(
    *,
    unidades: pd.DataFrame,
    robo_por_ref: dict[str, list[tuple[str, str]]],
    ia_ids_por_ref: dict[str, list[str]],
    ia_prob_por_deuda: dict[str, float],
) -> list[dict[str, Any]]:
    """Convierte la tabla de unidades en el detalle que consume la UI."""
    resultado = []
    for registro in unidades.to_dict("records"):
        referencia = str(registro.get("Referencia") or "")
        deudas_unidad = set(registro.get("Deudas") or [])
        usa_tradicional = _a_bool(registro.get("Usa_Tradicional_Unidad"))
        usa_credito = _a_bool(registro.get("Usa_Credito_Unidad"))

        trad_oportunidades = (
            _oportunidades_de_unidad(
                fila=registro,
                prefijo="Trad",
                nombres=[
                    "Depósito Extra",
                    "ContraOferta Viable",
                    "Liquidación Instantánea",
                ],
            )
            if usa_tradicional else []
        )
        cred_oportunidades = (
            _oportunidades_de_unidad(
                fila=registro,
                prefijo="Cred",
                nombres=[
                    "Depósito Extra",
                    "ContraOferta Viable",
                    "Liquidación Instantánea",
                ],
            )
            if usa_credito else []
        )

        # Paso 1: Oportunidades Generales que Tocan las Deudas de la Unidad
        generales = []
        robo_items = [
            (deuda, fecha)
            for deuda, fecha in robo_por_ref.get(referencia, [])
            if deuda in deudas_unidad
        ]
        if robo_items:
            generales.append({
                "nombre": "Acuerdo para Robo",
                "valor": "{} deuda(s)".format(len(robo_items)),
                "detalle": "; ".join(
                    "{}: {}".format(deuda, fecha)
                    for deuda, fecha in robo_items
                ),
                "deudas": [deuda for deuda, _ in robo_items],
                "ingreso_estimado": _ingreso_estimado_oportunidad_general(
                    fila=registro,
                    deudas=[deuda for deuda, _ in robo_items],
                ),
                "tipo_analisis": "General",
            })
        ia_deudas = [
            deuda for deuda in ia_ids_por_ref.get(referencia, [])
            if deuda in deudas_unidad
        ]
        if ia_deudas:
            generales.append({
                "nombre": "IA Liquidadora",
                "valor": max(
                    ia_prob_por_deuda.get(deuda, 0.0)
                    for deuda in ia_deudas
                ),
                "detalle": "; ".join(
                    "ID_Deuda: {} - {:.0%} Prob Liq.".format(
                        deuda, ia_prob_por_deuda.get(deuda, 0.0)
                    )
                    for deuda in ia_deudas
                ),
                "deudas": ia_deudas,
                "ingreso_estimado": _ingreso_estimado_oportunidad_general(
                    fila=registro,
                    deudas=ia_deudas,
                ),
                "tipo_analisis": "General",
            })

        # Paso 2: Lista Única de Oportunidades para los Badges
        nombres = [
            oportunidad.get("nombre")
            for oportunidad in (
                trad_oportunidades + cred_oportunidades + generales
            )
        ]
        oportunidades = [
            nombre for nombre in OPORTUNIDADES if nombre in set(nombres)
        ]

        resultado.append({
            "Unidad_Id": str(registro.get("Unidad_Id") or ""),
            "Referencia": referencia,
            "Etiqueta": str(registro.get("Etiqueta_Unidad") or ""),
            "Tipo_Unidad": str(registro.get("Tipo_Unidad") or ""),
            "Id_Portafolio": str(registro.get("Id_Portafolio") or ""),
            "Deudas": sorted(deudas_unidad),
            "Num_Deudas": int(registro.get("Num_Deudas") or 0),
            "PaB_Origen": _a_float(registro.get("PaB_Origen_Total")),
            "PaB_Actualizado": _a_float(
                registro.get("PaB_Actualizado_Total")
            ),
            "Descuento_Actual": _a_float(registro.get("Descuento_Actual")),
            "Ingreso_Actual": _a_float(registro.get("Ingreso_Actual")),
            "Ingreso_Estimado": 0.0,
            "Ingreso_Estimado_Detalle": {},
            "Pricing": _a_float(registro.get("Pricing")),
            "Pago_Compartido": _a_bool(registro.get("Pago_Compartido")),
            "Tiene_Todas_PaB_Ideal": _a_bool(
                registro.get("Tiene_Todas_PaB_Ideal")
            ),
            "Usa_Tradicional": usa_tradicional,
            "Usa_Credito": usa_credito,
            "Trad_Viable": _a_bool(registro.get("Trad_Viable")),
            "Cred_Viable": _a_bool(registro.get("Cred_Viable")),
            "Trad_Oportunidades": trad_oportunidades,
            "Cred_Oportunidades": cred_oportunidades,
            "Oportunidades_Generales": generales,
            "Oportunidades": oportunidades,
            "Deudas_Detalle": registro.get("Deudas_Detalle", []),
        })
    return resultado


# --- Cálculo del Ingreso Estimado por Oportunidad ---

def _normalizar_tipos_ingreso(tipo_analisis: str) -> tuple[set[str], str]:
    """Traduce el tipo de análisis a los prefijos y al contexto del cálculo.

    Returns:
        tuple[set[str], str]: Prefijos habilitados (``Trad``/``Cred``) y el
        contexto para etiquetar las oportunidades generales: ``tradicional``,
        ``credito`` o ``general``.
    """
    texto = clean_tildes(str(tipo_analisis or "")).casefold()
    if "tradicional" in texto and "credito" in texto:
        return {"Trad", "Cred"}, "general"
    if "credito" in texto:
        return {"Cred"}, "credito"
    if "tradicional" in texto:
        return {"Trad"}, "tradicional"
    return {"Trad", "Cred"}, "general"

# Función Auxiliar para Construir el Detalle del Ingreso Estimado
def _construir_detalle_ingreso(
    *,
    unidad: dict[str, Any],
    oportunidad: dict[str, Any],
) -> dict[str, Any]:
    """Construye el diccionario que explica de dónde sale el ingreso."""
    deudas = oportunidad.get("deudas")
    if not isinstance(deudas, list) or not deudas:
        deudas = _a_lista(unidad.get("Deudas"))
    return {
        "unidad": str(
            unidad.get("Etiqueta") or unidad.get("Unidad_Id") or "Unidad"
        ),
        "unidad_id": str(unidad.get("Unidad_Id") or ""),
        "tipo_unidad": str(unidad.get("Tipo_Unidad") or ""),
        "oportunidad": str(oportunidad.get("nombre") or ""),
        "tipo_analisis": str(oportunidad.get("tipo_analisis") or ""),
        "ingreso_estimado": _a_float(oportunidad.get("ingreso_estimado")),
        "deudas": list(deudas),
    }

# Función para Calcular el Ingreso Estimado de un Cliente
def calcular_ingreso_estimado_oportunidades(
    portafolios: Any,
    *,
    tipo_analisis: str = "Todos",
    oportunidades: Optional[list[str]] = None,
) -> tuple[list[dict[str, Any]], float, dict[str, Any]]:
    """Calcula el ingreso estimado como el máximo entre las oportunidades.

    El ingreso se calcula por unidad/portafolio y por oportunidad, no sobre
    todas las deudas del cliente. Las oportunidades generales (Acuerdo para
    Robo e IA Liquidadora) usan el Descuento Actual de las deudas que cubren.

    Args:
        portafolios (Any): Lista de unidades de ``Portafolios_Detalle``.
        tipo_analisis (str): ``Todos``, ``Tradicional``, ``Crédito`` o
            ``Tradicional y Crédito``. Siempre restringe el cálculo.
        oportunidades (Optional[list[str]]): Nombres seleccionados en el filtro
            de Oportunidad. Si está vacío, se usan todas.

    Returns:
        tuple[list[dict], float, dict]: Unidades copiadas y enriquecidas con el
        ingreso de cada oportunidad, el máximo ingreso del cliente y el detalle
        del origen de ese máximo.
    """
    prefijos_permitidos, contexto_tipo = _normalizar_tipos_ingreso(
        tipo_analisis
    )
    nombres_permitidos = {
        str(nombre).strip()
        for nombre in (oportunidades or [])
        if str(nombre).strip()
    }
    filtrar_por_nombre = bool(nombres_permitidos)

    unidades_resultado: list[dict[str, Any]] = []
    mejor_ingreso = 0.0
    mejor_oportunidad: Optional[dict[str, Any]] = None
    mejor_detalle: dict[str, Any] = {}

    for unidad in portafolios or []:
        if not isinstance(unidad, dict):
            continue
        unidad_copia = dict(unidad)
        candidatos: list[dict[str, Any]] = []
        usa_tradicional = _a_bool(unidad.get("Usa_Tradicional"))
        usa_credito = _a_bool(unidad.get("Usa_Credito"))

        # Paso 1: Oportunidades Calculadas (Tradicional y Crédito)
        for prefijo, etiqueta in (("Trad", "Tradicional"), ("Cred", "Crédito")):
            clave_lista = "{}_Oportunidades".format(prefijo)
            habilitado = (
                usa_tradicional if prefijo == "Trad" else usa_credito
            )
            incluye_tipo = prefijo in prefijos_permitidos and habilitado
            oportunidades_unidad = []
            for oportunidad in _a_lista(unidad.get(clave_lista, [])):
                if not isinstance(oportunidad, dict):
                    continue
                nombre = str(oportunidad.get("nombre") or "").strip()
                copia = dict(oportunidad)
                copia["tipo_analisis"] = etiqueta
                copia["es_ingreso_estimado_maximo"] = False
                ingreso = (
                    _a_float(copia.get("ingreso_estimado"), default=np.nan)
                    if "ingreso_estimado" in copia else np.nan
                )
                if pd.isna(ingreso):
                    ingreso = _ingreso_estimado_oportunidad(
                        fila=unidad,
                        prefijo=prefijo,
                        nombre=nombre,
                        valor=copia.get("valor", 0.0),
                    )
                copia["ingreso_estimado"] = max(float(ingreso), 0.0)
                incluida = incluye_tipo and (
                    not filtrar_por_nombre or nombre in nombres_permitidos
                )
                copia["incluida_en_ingreso_estimado"] = bool(incluida)
                oportunidades_unidad.append(copia)
                if incluida:
                    candidatos.append(copia)
            unidad_copia[clave_lista] = oportunidades_unidad

        # Paso 2: Oportunidades Generales (Robo e IA)
        generales_habilitadas = (
            (contexto_tipo == "tradicional" and usa_tradicional)
            or (contexto_tipo == "credito" and usa_credito)
            or (
                contexto_tipo == "general"
                and (usa_tradicional or usa_credito)
            )
        )
        generales = []
        for oportunidad in _a_lista(unidad.get("Oportunidades_Generales", [])):
            if not isinstance(oportunidad, dict):
                continue
            nombre = str(oportunidad.get("nombre") or "").strip()
            copia = dict(oportunidad)
            copia["tipo_analisis"] = (
                "Tradicional" if contexto_tipo == "tradicional"
                else "Crédito" if contexto_tipo == "credito"
                else "General"
            )
            copia["es_ingreso_estimado_maximo"] = False
            ingreso = (
                _a_float(copia.get("ingreso_estimado"), default=np.nan)
                if "ingreso_estimado" in copia else np.nan
            )
            if pd.isna(ingreso):
                ingreso = _ingreso_estimado_oportunidad_general(
                    fila=unidad,
                    deudas=copia.get("deudas", []),
                )
            copia["ingreso_estimado"] = max(float(ingreso), 0.0)
            incluida = generales_habilitadas and (
                not filtrar_por_nombre or nombre in nombres_permitidos
            )
            copia["incluida_en_ingreso_estimado"] = bool(incluida)
            generales.append(copia)
            if incluida:
                candidatos.append(copia)
        unidad_copia["Oportunidades_Generales"] = generales

        # Paso 3: Máximo de la Unidad y del Cliente
        candidatos.sort(
            key=lambda candidato: (
                -_a_float(candidato.get("ingreso_estimado")),
                _prioridad_ingreso(candidato),
            )
        )
        ingreso_unidad = 0.0
        detalle_unidad: dict[str, Any] = {}
        for candidato in candidatos:
            ingreso = _a_float(candidato.get("ingreso_estimado"))
            if ingreso <= 0:
                continue
            detalle = _construir_detalle_ingreso(
                unidad=unidad, oportunidad=candidato
            )
            if ingreso > ingreso_unidad:
                ingreso_unidad = ingreso
                detalle_unidad = detalle
            if ingreso > mejor_ingreso:
                mejor_ingreso = ingreso
                mejor_oportunidad = candidato
                mejor_detalle = detalle
        unidad_copia["Ingreso_Estimado"] = float(ingreso_unidad)
        unidad_copia["Ingreso_Estimado_Detalle"] = detalle_unidad
        unidades_resultado.append(unidad_copia)

    if mejor_oportunidad is not None:
        mejor_oportunidad["es_ingreso_estimado_maximo"] = True
    return unidades_resultado, float(mejor_ingreso), mejor_detalle

# Función Auxiliar para Sincronizar las Oportunidades Generales del Cliente
def _sincronizar_oportunidades_generales(
    *,
    generales: Any,
    unidades: list[dict[str, Any]],
    detalle_maximo: dict[str, Any],
) -> list[dict[str, Any]]:
    """Actualiza el ingreso y el máximo de las oportunidades generales.

    La lista del cliente agrupa Robo/IA por nombre. El ingreso que se muestra
    es el **máximo por unidad**, igual que el cálculo del Ingreso Estimado, y
    no la suma de todas las unidades. Así el valor coincide con la oportunidad
    que compite por el máximo del cliente.
    """
    base = [dict(op) for op in _a_lista(generales) if isinstance(op, dict)]
    if not base:
        return []
    por_nombre: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for unidad in unidades:
        for oportunidad in _a_lista(unidad.get("Oportunidades_Generales", [])):
            if not isinstance(oportunidad, dict):
                continue
            nombre = str(oportunidad.get("nombre") or "").strip()
            por_nombre.setdefault(nombre, []).append((unidad, oportunidad))
    for oportunidad in base:
        nombre = str(oportunidad.get("nombre") or "").strip()
        candidatos = [
            (unidad, candidata)
            for unidad, candidata in por_nombre.get(nombre, [])
            if _a_bool(candidata.get("incluida_en_ingreso_estimado", True))
        ]
        if not candidatos:
            oportunidad["ingreso_estimado"] = 0.0
            oportunidad["tipo_analisis"] = "General"
            oportunidad["unidad"] = ""
            oportunidad["unidad_id"] = ""
            oportunidad["es_ingreso_estimado_maximo"] = False
            continue
        unidad_max, oportunidad_max = max(
            candidatos,
            key=lambda par: _a_float(par[1].get("ingreso_estimado")),
        )
        ingreso = _a_float(oportunidad_max.get("ingreso_estimado"))
        unidad_id = str(unidad_max.get("Unidad_Id") or "")
        oportunidad["ingreso_estimado"] = ingreso
        oportunidad["tipo_analisis"] = str(
            oportunidad_max.get("tipo_analisis") or "General"
        )
        oportunidad["unidad"] = str(
            unidad_max.get("Etiqueta") or unidad_id or "Unidad"
        )
        oportunidad["unidad_id"] = unidad_id
        oportunidad["es_ingreso_estimado_maximo"] = bool(
            detalle_maximo
            and str(detalle_maximo.get("oportunidad") or "") == nombre
            and str(detalle_maximo.get("unidad_id") or "") == unidad_id
            and np.isclose(
                _a_float(detalle_maximo.get("ingreso_estimado")), ingreso
            )
        )
    return base

# Función para Calcular el Ingreso Estimado en el Resultado Masivo
def calcular_ingreso_estimado_masivo(
    df: pd.DataFrame,
    *,
    tipo_analisis: str = "Todos",
    oportunidades: Optional[list[str]] = None,
) -> pd.DataFrame:
    """Agrega ``Ingreso_Estimado`` y su detalle al DataFrame masivo.

    Se recalcula con los filtros vigentes de la vista. Los clientes sin
    oportunidades aplicables quedan con ingreso 0 y detalle vacío.
    """
    if df is None:
        return pd.DataFrame({
            "Ingreso_Estimado": pd.Series(dtype=float),
            "Ingreso_Estimado_Detalle": pd.Series(dtype=object),
        })
    resultado = df.copy()
    if resultado.empty:
        resultado["Ingreso_Estimado"] = pd.Series(dtype=float)
        resultado["Ingreso_Estimado_Detalle"] = pd.Series(dtype=object)
        return resultado

    portafolios_lista = (
        resultado["Portafolios_Detalle"].tolist()
        if "Portafolios_Detalle" in resultado.columns
        else [None] * len(resultado)
    )
    generales_lista = (
        resultado["Oportunidades_Generales"].tolist()
        if "Oportunidades_Generales" in resultado.columns
        else [None] * len(resultado)
    )
    portafolios_nuevos: list[list[dict[str, Any]]] = []
    generales_nuevas: list[list[dict[str, Any]]] = []
    ingresos: list[float] = []
    detalles: list[dict[str, Any]] = []
    for portafolios, generales in zip(portafolios_lista, generales_lista):
        if not isinstance(portafolios, (list, tuple)):
            portafolios = []
        nuevas, ingreso, detalle = calcular_ingreso_estimado_oportunidades(
            portafolios,
            tipo_analisis=tipo_analisis,
            oportunidades=oportunidades,
        )
        portafolios_nuevos.append(nuevas)
        generales_nuevas.append(
            _sincronizar_oportunidades_generales(
                generales=generales,
                unidades=nuevas,
                detalle_maximo=detalle,
            )
        )
        ingresos.append(float(ingreso))
        detalles.append(detalle)

    if "Portafolios_Detalle" in resultado.columns:
        resultado["Portafolios_Detalle"] = pd.Series(
            portafolios_nuevos, dtype=object
        ).to_numpy()
    if "Oportunidades_Generales" in resultado.columns:
        resultado["Oportunidades_Generales"] = pd.Series(
            generales_nuevas, dtype=object
        ).to_numpy()
    resultado["Ingreso_Estimado"] = pd.to_numeric(
        pd.Series(ingresos), errors="coerce"
    ).fillna(0.0).to_numpy()
    resultado["Ingreso_Estimado_Detalle"] = pd.Series(
        detalles, dtype=object
    ).to_numpy()
    return resultado


def calcular_oportunidades_masivas_datos(
    *,
    asignacion_df: pd.DataFrame,
    masivas_df: pd.DataFrame,
    pab_ideal: dict[str, float],
    saldos: dict[str, dict[str, float]],
    prospectos_credito: dict[str, str],
    prospectos_tradicional: pd.DataFrame,
    pipeline_credito: pd.DataFrame,
    liquidaciones: set[str],
    solicitudes_df: Optional[pd.DataFrame] = None,
    actualizaciones_df: Optional[pd.DataFrame] = None,
    referencias: Optional[list[str]] = None,
    solo_masivas: bool = True,
    incluir_acuerdos_robo: bool = True,
    fechas_metabase: Optional[dict[str, Any]] = None,
    hoy: Optional[pd.Timestamp] = None,
    progreso_callback: Optional[Callable[[float, str], None]] = None,
) -> pd.DataFrame:
    """Calcula las oportunidades de todos los clientes de forma vectorizada.

    El cálculo se hace por **unidad de análisis**: cada portafolio detectado o
    cada deuda individual. Luego se consolidan las unidades a nivel de cliente.

    Fuente del Descuento Actual:
    - ``solo_masivas=True``: el mejor descuento vigente de Masivas por deuda.
      Los portafolios se identifican con ``Metadata.Id_Portafolio``; si está
      vacío, la deuda es individual.
    - ``solo_masivas=False``: Actualizaciones con las etiquetas confiables y la
      regla individual de ``ACTUALIZADO_ALIANZAS``. Los portafolios se detectan
      por actualizaciones consecutivas con la misma etiqueta a ≤45 s. Si el
      cliente no tiene actualizaciones, se agrupa por ``BANCOS_PORTAFOLIO``.

    Reglas de Crédito:
    - Se exige un estado apto en el Pipeline.
    - ``Cr Parcial`` solo permite Crédito; ``Tradicional`` solo permite Tradicional.
    - Una unidad se analiza por Crédito solo si **todas** sus deudas tienen
      PaB Ideal > 0. Si falta una, la unidad completa queda fuera de Crédito.

    Args:
        asignacion_df (pd.DataFrame): Asignación de Cartera.
        masivas_df (pd.DataFrame): Base del Mes de Masivas.
        pab_ideal (dict[str, float]): PaB Ideal por Id_Deuda.
        saldos (dict[str, dict[str, float]]): Saldos y Por Cobrar por Referencia.
        prospectos_credito (dict[str, str]): Prospecto de Crédito por Referencia.
        prospectos_tradicional (pd.DataFrame): Prospectos de Tradicional por deuda.
        pipeline_credito (pd.DataFrame): Último estado del Pipeline de Crédito.
        liquidaciones (set[str]): Ids de deuda liquidados.
        solicitudes_df (Optional[pd.DataFrame]): Solicitudes del MEC para Alianzas.
        actualizaciones_df (Optional[pd.DataFrame]): Actualizaciones del MEC.
        referencias (Optional[list[str]]): Referencias habilitadas para el usuario.
        solo_masivas (bool): Si True, solo analiza deudas con Masivas vigente.
        incluir_acuerdos_robo (bool): Si True, evalúa Acuerdo para Robo.
        fechas_metabase (Optional[dict[str, Any]]): Vencimientos de Metabase por deuda.
        hoy (Optional[pd.Timestamp]): Fecha de corte.
        progreso_callback (Optional[Callable[[float, str], None]]): Callback de avance.

    Returns:
        pd.DataFrame: Una fila por Referencia con sus métricas, oportunidades y
        el detalle de sus portafolios/unidades.
    """
    _reportar_progreso_masivo(progreso_callback, 0.02, "Validando la Asignación de Cartera...")
    if asignacion_df is None or asignacion_df.empty:
        return _resultado_masivo_vacio()
    if not {"Referencia", "Id_Deuda", "PaB_Origen"}.issubset(set(asignacion_df.columns)):
        return _resultado_masivo_vacio()
    if hoy is None:
        hoy = pd.Timestamp.now(tz="America/Bogota").tz_localize(None).normalize()
    hoy = pd.Timestamp(hoy)
    if hoy.tzinfo is not None:
        hoy = hoy.tz_convert("America/Bogota").tz_localize(None)
    hoy = hoy.normalize()

    # Paso 1: Normalizar la Asignación y Quedarnos con las Referencias Habilitadas
    deudas = asignacion_df.copy()
    deudas["Referencia"] = deudas["Referencia"].astype(str).str.replace(".0", "", regex=False).str.strip()
    deudas["Id_Deuda"] = deudas["Id_Deuda"].apply(_normalizar_id_deuda)
    if referencias is not None:
        referencias_norm = {str(r).replace(".0", "").strip() for r in referencias}
        deudas = deudas[deudas["Referencia"].isin(referencias_norm)]
    deudas = deudas[(deudas["Referencia"] != "") & (deudas["Id_Deuda"] != "")]
    if deudas.empty:
        return _resultado_masivo_vacio()

    # Guardamos todas las deudas de la Referencia (incluidas las que luego se
    # excluyen) para que el redireccionamiento a la calculadora individual
    # pueda apagar explícitamente las deudas que no pertenecen al portafolio.
    deudas_referencia = deudas.groupby("Referencia")["Id_Deuda"].apply(
        lambda serie: sorted(set(serie))
    ).to_dict()

    for columna in ("PaB_Origen", "Descuento_Esperado", "Apartado_Neto", "Pricing"):
        if columna not in deudas.columns:
            deudas[columna] = 0.0
        deudas[columna] = pd.to_numeric(deudas[columna], errors="coerce")
    deudas["PaB_Origen"] = deudas["PaB_Origen"].fillna(0.0).clip(lower=0.0)
    deudas["Descuento_Esperado"] = deudas["Descuento_Esperado"].fillna(0.0).clip(lower=0.0)
    deudas["Apartado_Neto"] = deudas["Apartado_Neto"].fillna(0.0).clip(lower=0.0)
    deudas["Pricing"] = deudas["Pricing"].fillna(0.15).clip(lower=0.0)
    if "Nombre_Cliente" not in deudas.columns:
        deudas["Nombre_Cliente"] = ""
    if "Negociador" not in deudas.columns:
        deudas["Negociador"] = "Sin Negociador Asignado"
    if "Banco" not in deudas.columns:
        deudas["Banco"] = ""
    deudas["Nombre_Cliente"] = deudas["Nombre_Cliente"].fillna("").astype(str).str.strip()
    deudas["Negociador"] = deudas["Negociador"].fillna("Sin Negociador Asignado").astype(str).str.strip()
    deudas["Banco"] = deudas["Banco"].fillna("").astype(str).str.strip()

    # Paso 2: Excluir Deudas Liquidadas y sin DUM Válido
    liquidaciones_norm = {_normalizar_id_deuda(d) for d in (liquidaciones or set())}
    clientes_con_liquidaciones = set(
        deudas.loc[deudas["Id_Deuda"].isin(liquidaciones_norm), "Referencia"]
    )
    deudas = deudas[~deudas["Id_Deuda"].isin(liquidaciones_norm)]
    deudas = deudas[deudas["PaB_Origen"] > 0]
    if deudas.empty:
        return _resultado_masivo_vacio()

    # Paso 3: Traer el Mejor Descuento Vigente de Masivas
    _reportar_progreso_masivo(progreso_callback, 0.16, "Cruzando descuentos de Masivas de Alianzas...")
    masivas_sel = seleccionar_descuentos_masivas(masivas_df=masivas_df, hoy=hoy)
    if not masivas_sel.empty:
        deudas = deudas.merge(
            masivas_sel[
                [
                    "Id_Deuda", "PaB_Propuesta", "Casa_Cobro", "Fecha_Masiva",
                    "Fecha_Limite_Uso", "Es_Portafolio", "Id_Portafolio",
                    "PaB_Portafolio", "Portafolio_Completo",
                ]
            ],
            on="Id_Deuda",
            how="left",
        )
    else:
        deudas["PaB_Propuesta"] = np.nan
        deudas["Casa_Cobro"] = ""
        deudas["Fecha_Masiva"] = pd.NaT
        deudas["Fecha_Limite_Uso"] = pd.NaT
        deudas["Es_Portafolio"] = False
        deudas["Id_Portafolio"] = ""
        deudas["PaB_Portafolio"] = np.nan
        deudas["Portafolio_Completo"] = False

    deudas["Tiene_Masiva"] = deudas["PaB_Propuesta"].notna() & (
        pd.to_numeric(deudas["PaB_Propuesta"], errors="coerce") > 0
    )
    deudas["PaB_Masiva"] = pd.to_numeric(deudas["PaB_Propuesta"], errors="coerce").clip(lower=0.0)
    deudas["PaB_Masiva"] = deudas["PaB_Masiva"].fillna(0.0)
    deudas["Id_Portafolio"] = deudas["Id_Portafolio"].fillna("").astype(str)
    deudas["Portafolio_Completo"] = deudas["Portafolio_Completo"].fillna(False).astype(bool)

    if solo_masivas:
        deudas = deudas[deudas["Tiene_Masiva"]]
        if deudas.empty:
            return _resultado_masivo_vacio()

    # Paso 4: Traer PaB Ideal y Prospectos por Deuda
    _reportar_progreso_masivo(progreso_callback, 0.28, "Cruzando PaB Ideal y Prospectos...")
    deudas["PaB_Ideal"] = deudas["Id_Deuda"].apply(
        lambda d: max(_a_float((pab_ideal or {}).get(_normalizar_id_deuda(d), 0.0)), 0.0)
    )
    deudas["Tiene_PaB_Ideal"] = deudas["PaB_Ideal"] > 0

    if prospectos_tradicional is not None and not prospectos_tradicional.empty:
        prosp = prospectos_tradicional.copy()
        if {"Id_Deuda", "Prospecto"}.issubset(set(prosp.columns)):
            prosp["Id_Deuda"] = prosp["Id_Deuda"].apply(_normalizar_id_deuda)
            if "Prob_Liq" not in prosp.columns:
                prosp["Prob_Liq"] = 0.0
            prosp["Prob_Liq"] = pd.to_numeric(prosp["Prob_Liq"], errors="coerce").fillna(0.0)
            prosp = prosp[["Id_Deuda", "Prospecto", "Prob_Liq"]].drop_duplicates(
                subset=["Id_Deuda"], keep="last"
            )
            deudas = deudas.merge(prosp, on="Id_Deuda", how="left")
        else:
            deudas["Prospecto"] = np.nan
            deudas["Prob_Liq"] = 0.0
    else:
        deudas["Prospecto"] = np.nan
        deudas["Prob_Liq"] = 0.0
    deudas["Prospecto"] = deudas["Prospecto"].where(deudas["Prospecto"].notna(), "N/A")
    deudas["Prob_Liq"] = pd.to_numeric(deudas["Prob_Liq"], errors="coerce").fillna(0.0)

    # Paso 5: Resolver el Descuento Actual y Construir las Unidades de Análisis
    _reportar_progreso_masivo(progreso_callback, 0.40, "Construyendo portafolios y unidades de análisis...")
    if solo_masivas:
        deudas["PaB_Actualizado_Deuda"] = np.minimum(
            pd.to_numeric(deudas["PaB_Masiva"], errors="coerce").fillna(0.0),
            deudas["PaB_Origen"],
        )
        # La última actualización se expone para el panel de resumen y los
        # filtros por estado, sin cambiar el pago que viene de Masivas.
        deudas = _mapear_ultima_actualizacion(
            deudas=deudas,
            actualizaciones_df=actualizaciones_df,
        )
        deudas = _construir_unidades_masivas(deudas=deudas)
    else:
        deudas = _resolver_pab_actualizado_actualizaciones(
            deudas=deudas,
            actualizaciones_df=actualizaciones_df,
            masivas_df=masivas_df,
            solicitudes_df=solicitudes_df,
        )
        deudas = _construir_unidades_actualizaciones(deudas=deudas)
    deudas = _aplicar_pago_unidades(deudas=deudas, solo_masivas=solo_masivas)
    deudas["Descuento_Deuda"] = np.where(
        deudas["PaB_Origen"] > 0,
        1 - (deudas["PaB_Actualizado"] / deudas["PaB_Origen"]),
        0.0,
    )
    deudas["Descuento_Deuda"] = np.clip(deudas["Descuento_Deuda"], 0.0, 1.0)

    # Paso 6: Construir la Base por Referencia
    _reportar_progreso_masivo(progreso_callback, 0.50, "Agrupando clientes y deudas...")
    deudas["_Desc_Ponderado"] = deudas["Descuento_Esperado"] * deudas["PaB_Origen"]
    base = deudas.groupby("Referencia", as_index=False).agg(
        Nombre_Cliente=("Nombre_Cliente", "first"),
        Negociador=("Negociador", "first"),
        Pricing=("Pricing", "first"),
        Apartado_Neto=("Apartado_Neto", "max"),
        PaB_Origen_Total=("PaB_Origen", "sum"),
        PaB_Actualizado_Total=("PaB_Actualizado", "sum"),
        Deudas_Analizadas=("Id_Deuda", "nunique"),
        Deudas_Masivas=("Tiene_Masiva", "sum"),
        Deudas_Con_PaB_Ideal=("Tiene_PaB_Ideal", "sum"),
        Desc_Ponderado_Suma=("_Desc_Ponderado", "sum"),
    )
    base["Nombre_Cliente"] = base["Nombre_Cliente"].fillna("").astype(str).str.strip()
    base["Negociador"] = base["Negociador"].fillna("Sin Negociador Asignado").astype(str).str.strip()
    base["Deudas_Sin_PaB_Ideal"] = base["Deudas_Analizadas"] - base["Deudas_Con_PaB_Ideal"]
    base["Tiene_Deudas_Liquidaciones"] = base["Referencia"].isin(clientes_con_liquidaciones)
    base["Deudas_Referencia"] = base["Referencia"].map(deudas_referencia).apply(
        lambda valor: valor if isinstance(valor, list) else []
    )
    base["Fuente_Descuento"] = "Masivas" if solo_masivas else "Actualizaciones"
    base["Ahorro"] = base["Referencia"].map(
        lambda r: _a_float((saldos or {}).get("Saldos", {}).get(r, 0.0))
    )
    base["Por_Cobrar"] = base["Referencia"].map(
        lambda r: _a_float((saldos or {}).get("PorCobrar", {}).get(r, 0.0))
    )
    base["Ahorro_Neto"] = base["Ahorro"] - base["Por_Cobrar"]
    base["Descuento_Actual"] = np.where(
        base["PaB_Origen_Total"] > 0,
        1 - (base["PaB_Actualizado_Total"] / base["PaB_Origen_Total"]),
        0.0,
    )
    base["Descuento_Actual"] = np.clip(base["Descuento_Actual"], 0.0, 1.0)
    base["Pago_Actual"] = base["PaB_Actualizado_Total"]
    base["Ingreso_Actual"] = np.maximum(
        (base["PaB_Origen_Total"] - base["PaB_Actualizado_Total"]) * base["Pricing"],
        0.0,
    )
    base["Descuento_Esperado_Ponderado"] = np.where(
        base["PaB_Origen_Total"] > 0,
        base["Desc_Ponderado_Suma"] / base["PaB_Origen_Total"],
        0.0,
    )
    base["Descuento_Esperado_Ponderado"] = base["Descuento_Esperado_Ponderado"].fillna(0.0)

    # Paso 7: Prospecto de Crédito y Viabilidad de Crédito
    def _prospecto_credito(ref: str) -> str:
        valor = (prospectos_credito or {}).get(ref, "Tradicional")
        if valor is None:
            return "Tradicional"
        try:
            if pd.isna(valor):
                return "Tradicional"
        except (TypeError, ValueError):
            pass
        valor = str(valor).strip()
        return valor if valor else "Tradicional"

    base["Prospecto_Credito"] = base["Referencia"].map(_prospecto_credito)
    prosp_trad_valido = deudas[deudas["Prospecto"] != "N/A"].copy()
    if not prosp_trad_valido.empty:
        prosp_trad_valido = prosp_trad_valido.sort_values(
            by=["Referencia", "Prospecto"], ascending=[True, True]
        )
        mejor_prosp = prosp_trad_valido.drop_duplicates(
            subset=["Referencia"], keep="first"
        ).set_index("Referencia")["Prospecto"].to_dict()
    else:
        mejor_prosp = {}
    base["Prospecto_Tradicional"] = base["Referencia"].map(mejor_prosp).fillna("N/A")

    pipe = pipeline_credito.copy() if pipeline_credito is not None else pd.DataFrame()
    if not pipe.empty and "Referencia" in pipe.columns:
        pipe["Referencia"] = pipe["Referencia"].astype(str).str.replace(".0", "", regex=False).str.strip()
        if "Fecha_Subida" in pipe.columns:
            pipe = pipe.sort_values(by="Fecha_Subida")
        pipe = pipe.drop_duplicates(subset=["Referencia"], keep="last").set_index("Referencia")
        estado_map = pipe["Status_Credito"].to_dict() if "Status_Credito" in pipe.columns else {}
        no_opta_map = pipe["No_Opta_Credito"].to_dict() if "No_Opta_Credito" in pipe.columns else {}
        rechazo_map = pipe["Rechazo_Credito"].to_dict() if "Rechazo_Credito" in pipe.columns else {}
        base["Estado_Credito"] = base["Referencia"].map(estado_map).fillna("")
        if no_opta_map:
            base["No_Opta_Credito"] = base["Referencia"].map(no_opta_map).fillna(False).astype(bool)
        else:
            base["No_Opta_Credito"] = base["Estado_Credito"].isin(ESTADOS_NO_OPP_CREDITO)
        if rechazo_map:
            base["Rechazo_Credito"] = base["Referencia"].map(rechazo_map).fillna(False).astype(bool)
        else:
            base["Rechazo_Credito"] = base["Estado_Credito"].isin(ESTADOS_NO_QUIERE_CREDITO)
    else:
        base["Estado_Credito"] = ""
        base["No_Opta_Credito"] = False
        base["Rechazo_Credito"] = False

    base["Estado_Credito"] = base["Estado_Credito"].apply(
        lambda valor: "" if str(valor).strip().casefold() in ["", "nan", "none"] else str(valor).strip()
    )
    base["Tiene_Pipeline_Credito"] = ~base["Estado_Credito"].astype(str).str.strip().str.casefold().isin(
        ["", "nan", "none"]
    )
    # Sin fila en el Pipeline no se bloquea Crédito: la ausencia de gestión
    # significa que el cliente aún no ha sido analizado, no que sea inviable.
    base["Credito_Viable"] = (
        ~base["No_Opta_Credito"]
        & ~base["Rechazo_Credito"]
    )

    prospecto_norm = base["Prospecto_Credito"].astype(str).str.strip().str.casefold()
    base["_Es_Cr_Parcial"] = prospecto_norm.str.contains("parcial", na=False)
    base["_Es_Tradicional"] = prospecto_norm.eq("tradicional")
    base["Tradicional_Habilitado"] = ~base["_Es_Cr_Parcial"]

    # Paso 8: Construir las Unidades y Asignar sus Tipos de Análisis
    _reportar_progreso_masivo(progreso_callback, 0.58, "Asignando tipos de análisis a cada portafolio...")
    unidades = _construir_tabla_unidades(deudas=deudas)
    base_idx = base.set_index("Referencia")
    unidades["Usa_Tradicional_Unidad"] = unidades["Referencia"].map(
        base_idx["Tradicional_Habilitado"]
    ).fillna(False).astype(bool)
    credito_viable_unidad = unidades["Referencia"].map(
        base_idx["Credito_Viable"]
    ).fillna(False).astype(bool)
    es_tradicional_unidad = unidades["Referencia"].map(
        base_idx["_Es_Tradicional"]
    ).fillna(False).astype(bool)
    unidades["Usa_Credito_Unidad"] = (
        credito_viable_unidad
        & ~es_tradicional_unidad
        & unidades["Tiene_Todas_PaB_Ideal"].fillna(False).astype(bool)
    )

    creditos_por_ref = unidades.groupby("Referencia")["Usa_Credito_Unidad"].any().to_dict()
    base["Credito_Habilitado"] = base["Referencia"].map(creditos_por_ref).fillna(False).astype(bool)
    base["Tipos_Analisis"] = base.apply(
        lambda r: [
            tipo for tipo, habilitado in (
                ("Tradicional", r["Tradicional_Habilitado"]),
                ("Crédito", r["Credito_Habilitado"]),
            ) if bool(habilitado)
        ],
        axis=1,
    )

    unidades_por_ref = {
        referencia: grupo for referencia, grupo in unidades.groupby("Referencia")
    }

    def _detalle_credito(row: pd.Series) -> str:
        if row["_Es_Tradicional"]:
            return "Prospecto Tradicional: no aplica el análisis por Crédito."
        if row["No_Opta_Credito"]:
            return "El cliente no opta a Crédito ({}).".format(row["Estado_Credito"])
        if row["Rechazo_Credito"]:
            return "El cliente rechazó Crédito ({}).".format(row["Estado_Credito"])

        grupo = unidades_por_ref.get(row["Referencia"], pd.DataFrame())
        total_unidades = int(len(grupo))
        unidades_credito = int(grupo["Usa_Credito_Unidad"].sum()) if total_unidades else 0
        unidades_excluidas = total_unidades - unidades_credito
        if unidades_credito == 0:
            return (
                "Ninguna de las {} unidades se analiza por Crédito: todas tienen "
                "al menos una deuda sin PaB Ideal.".format(total_unidades)
            )
        if row["Tiene_Pipeline_Credito"]:
            prefijo = "Crédito viable ({}).".format(row["Estado_Credito"])
        else:
            prefijo = (
                "Sin registro en el Pipeline de Crédito: se analiza por Crédito "
                "sin validación previa."
            )
        detalle = "{} {} de {} unidades se analizan por Crédito.".format(
            prefijo, unidades_credito, total_unidades
        )
        if unidades_excluidas > 0:
            detalle += (
                " {} unidad(es) quedan fuera del análisis de Crédito por deudas "
                "sin PaB Ideal.".format(unidades_excluidas)
            )
        return detalle

    base["Credito_Detalle"] = base.apply(_detalle_credito, axis=1)

    # Agregamos las banderas de la unidad a cada deuda para el detalle
    banderas_unidad = unidades.set_index("Unidad_Id")[
        ["Usa_Tradicional_Unidad", "Usa_Credito_Unidad"]
    ]
    deudas = deudas.merge(
        banderas_unidad, left_on="Unidad_Id", right_index=True, how="left"
    )
    deudas["Usa_Tradicional"] = deudas["Usa_Tradicional_Unidad"].fillna(False).astype(bool)
    deudas["Usa_Credito"] = deudas["Usa_Credito_Unidad"].fillna(False).astype(bool)

    # Paso 9: Métricas de Tradicional y Crédito por Unidad
    _reportar_progreso_masivo(progreso_callback, 0.66, "Calculando oportunidades por portafolio...")
    trad_unidades = _calcular_metricas_tradicional_masivas(
        deudas=deudas[deudas["Usa_Tradicional"]],
        saldos=saldos or {},
        group_col="Unidad_Id",
    )
    unidades = unidades.merge(trad_unidades, on="Unidad_Id", how="left")
    cred_unidades = _calcular_metricas_credito_masivas(
        deudas=deudas[deudas["Usa_Credito"]],
        group_col="Unidad_Id",
    )
    unidades = unidades.merge(cred_unidades, on="Unidad_Id", how="left")

    columnas_bool_unidad = [
        "Trad_Deposito_Extra_Aplica", "Trad_Contraoferta_Aplica",
        "Trad_Liq_Insta_Aplica", "Trad_Viable",
        "Cred_Deposito_Extra_Aplica", "Cred_Contraoferta_Aplica",
        "Cred_Liq_Insta_Aplica", "Cred_Viable",
    ]
    for columna in columnas_bool_unidad:
        unidades[columna] = unidades[columna].fillna(False).astype(bool)

    columnas_num_unidad = [
        "Trad_PaB_Origen_Total", "Trad_PaB_Actualizado_Total",
        "Trad_Descuento_Actual", "Trad_Pago_Actual", "Trad_Ingreso_Actual",
        "Trad_Apartado_Neto", "Trad_Descuento_Esperado_Ponderado",
        "Trad_Num_Deudas", "Trad_Deposito_Extra_Valor",
        "Trad_Contraoferta_Valor", "Cred_PaB_Origen_Total",
        "Cred_PaB_Actualizado_Total", "Cred_PaB_Ideal_Total",
        "Cred_Descuento_Actual", "Cred_Pago_Actual", "Cred_Num_Deudas",
        "Cred_Descuento_Esperado_Ponderado", "Cred_Deposito_Extra_Valor",
        "Cred_Contraoferta_Valor",
    ]
    for columna in columnas_num_unidad:
        unidades[columna] = pd.to_numeric(
            unidades[columna], errors="coerce"
        ).fillna(0.0)
    for columna in ("Trad_Num_Deudas", "Cred_Num_Deudas"):
        unidades[columna] = unidades[columna].astype(int)

    # Paso 10: Métricas Consolidadas del Cliente
    _reportar_progreso_masivo(progreso_callback, 0.74, "Consolidando oportunidades por cliente...")
    trad_cliente = _calcular_metricas_tradicional_masivas(
        deudas=deudas[deudas["Usa_Tradicional"]],
        saldos=saldos or {},
        group_col="Referencia",
    )
    base = base.merge(trad_cliente, on="Referencia", how="left")
    cred_cliente = _calcular_metricas_credito_masivas(
        deudas=deudas[deudas["Usa_Credito"]],
        group_col="Referencia",
    )
    base = base.merge(cred_cliente, on="Referencia", how="left")

    columnas_bool_cliente = [
        "Trad_Deposito_Extra_Aplica", "Trad_Contraoferta_Aplica",
        "Trad_Liq_Insta_Aplica", "Trad_Viable",
        "Cred_Deposito_Extra_Aplica", "Cred_Contraoferta_Aplica",
        "Cred_Liq_Insta_Aplica", "Cred_Viable",
    ]
    for columna in columnas_bool_cliente:
        base[columna] = base[columna].fillna(False).astype(bool)

    columnas_num_cliente = [
        "Trad_PaB_Origen_Total", "Trad_PaB_Actualizado_Total",
        "Trad_Descuento_Actual", "Trad_Pago_Actual", "Trad_Ingreso_Actual",
        "Trad_Apartado_Neto", "Trad_Descuento_Esperado_Ponderado",
        "Trad_Num_Deudas", "Trad_Deposito_Extra_Valor",
        "Trad_Contraoferta_Valor", "Cred_PaB_Origen_Total",
        "Cred_PaB_Actualizado_Total", "Cred_PaB_Ideal_Total",
        "Cred_Descuento_Actual", "Cred_Pago_Actual", "Cred_Num_Deudas",
        "Cred_Descuento_Esperado_Ponderado", "Cred_Deposito_Extra_Valor",
        "Cred_Contraoferta_Valor",
    ]
    for columna in columnas_num_cliente:
        base[columna] = pd.to_numeric(
            base[columna], errors="coerce"
        ).fillna(0.0)
    for columna in ("Trad_Num_Deudas", "Cred_Num_Deudas"):
        base[columna] = base[columna].astype(int)

    trad_viable_por_ref = unidades.assign(
        _Viable=unidades["Usa_Tradicional_Unidad"] & unidades["Trad_Viable"]
    ).groupby("Referencia")["_Viable"].any().to_dict()
    cred_viable_por_ref = unidades.assign(
        _Viable=unidades["Usa_Credito_Unidad"] & unidades["Cred_Viable"]
    ).groupby("Referencia")["_Viable"].any().to_dict()
    base["Trad_Alguna_Viable"] = base["Referencia"].map(trad_viable_por_ref).fillna(False).astype(bool)
    base["Cred_Alguna_Viable"] = base["Referencia"].map(cred_viable_por_ref).fillna(False).astype(bool)
    base["Es_Viable"] = base["Trad_Alguna_Viable"] | base["Cred_Alguna_Viable"]
    base["Viable_Por"] = base.apply(
        lambda r: [
            tipo for tipo, viable in (
                ("Tradicional", r["Trad_Alguna_Viable"]),
                ("Crédito", r["Cred_Alguna_Viable"]),
            ) if bool(viable)
        ],
        axis=1,
    )

    # Paso 11: Acuerdos para Robo e IA Liquidadora (Oportunidades Generales)
    _reportar_progreso_masivo(progreso_callback, 0.82, "Evaluando Acuerdos para Robo e IA Liquidadora...")
    acuerdos_robo: dict[str, str] = {}
    if incluir_acuerdos_robo:
        acuerdos_robo, pendientes = _preparar_acuerdos_robo_masivos(
            actualizaciones_df=actualizaciones_df,
            solicitudes_df=solicitudes_df,
            liquidaciones=liquidaciones_norm,
            deudas=deudas["Id_Deuda"].dropna().unique().tolist(),
            hoy=hoy,
        )
        if pendientes and fechas_metabase is not None:
            for pendiente in pendientes:
                deuda = _normalizar_id_deuda(pendiente.get("Id_Deuda"))
                if not deuda or deuda in acuerdos_robo:
                    continue
                valor = fechas_metabase.get(deuda)
                if valor is None:
                    # Metabase falló o no hay datos: no se asume la oportunidad
                    continue
                try:
                    if pd.isna(valor):
                        acuerdos_robo[deuda] = "Sin fecha"
                        continue
                except (TypeError, ValueError):
                    continue
                fecha_meta = _a_timestamp(valor)
                if fecha_meta is not None and fecha_meta.normalize() < hoy:
                    acuerdos_robo[deuda] = fecha_meta.strftime("%d/%m/%Y")

    deuda_a_ref = deudas.set_index("Id_Deuda")["Referencia"].to_dict()
    robo_por_ref: dict[str, list[tuple[str, str]]] = {}
    for deuda, fecha in acuerdos_robo.items():
        ref = deuda_a_ref.get(deuda)
        if ref:
            robo_por_ref.setdefault(ref, []).append((deuda, fecha))

    base["Acuerdo_Robo_Deudas"] = base["Referencia"].map(
        lambda r: len(robo_por_ref.get(r, []))
    )
    base["Acuerdo_Robo_Aplica"] = base["Acuerdo_Robo_Deudas"] > 0
    base["Acuerdo_Robo_Valor"] = base["Acuerdo_Robo_Deudas"].apply(
        lambda n: "{} deuda(s)".format(int(n))
    )
    base["Acuerdo_Robo_Detalle"] = base["Referencia"].map(
        lambda r: "; ".join("{}: {}".format(d, f) for d, f in robo_por_ref.get(r, []))
        if robo_por_ref.get(r) else "Sin acuerdos vencidos sin gestión posterior."
    )
    base["Acuerdo_Robo_IDs"] = base["Referencia"].map(
        lambda r: [d for d, _ in robo_por_ref.get(r, [])]
    )

    ia_por_ref = deudas.groupby("Referencia")["Prob_Liq"].max().to_dict()
    ia_detalle_por_ref: dict[str, str] = {}
    ia_ids_por_ref: dict[str, list[str]] = {}
    ia_deudas = deudas[deudas["Prob_Liq"] >= UMBRAL_PROB_LIQ_IA].copy()
    if not ia_deudas.empty:
        ia_deudas["_Id_Deuda_Norm"] = ia_deudas["Id_Deuda"].apply(
            _normalizar_id_deuda
        )
        ia_deudas["_Prob_Texto"] = ia_deudas["Prob_Liq"].map(
            lambda valor: "{:.0%}".format(valor)
        )
        ia_deudas["_Detalle"] = (
            "ID_Deuda: " + ia_deudas["_Id_Deuda_Norm"]
            + " - " + ia_deudas["_Prob_Texto"] + " Prob Liq."
        )
        ia_detalle_por_ref = ia_deudas.groupby(
            "Referencia", sort=False
        )["_Detalle"].agg("; ".join).to_dict()
        ia_ids_por_ref = ia_deudas.groupby(
            "Referencia", sort=False
        )["_Id_Deuda_Norm"].agg(list).to_dict()
    base["IA_Liquidadora_Valor"] = base["Referencia"].map(ia_por_ref).fillna(0.0)
    base["IA_Liquidadora_Aplica"] = base["IA_Liquidadora_Valor"] >= UMBRAL_PROB_LIQ_IA
    base["IA_Liquidadora_Detalle"] = base["Referencia"].map(
        lambda r: ia_detalle_por_ref.get(r, "Sin deudas con probabilidad >= 50%.")
    )
    base["IA_Liquidadora_IDs"] = base["Referencia"].map(
        lambda r: ia_ids_por_ref.get(r, [])
    )
    ia_prob_por_deuda = deudas.set_index("Id_Deuda")["Prob_Liq"].to_dict()

    # Paso 12: Detalle de Portafolios y Resumen de Oportunidades
    _reportar_progreso_masivo(progreso_callback, 0.90, "Preparando el detalle de portafolios...")
    unidades = _agregar_detalle_unidades(unidades=unidades, deudas=deudas)
    portafolios = _construir_portafolios_detalle(
        unidades=unidades,
        robo_por_ref=robo_por_ref,
        ia_ids_por_ref=ia_ids_por_ref,
        ia_prob_por_deuda=ia_prob_por_deuda,
    )
    portafolios_por_ref: dict[str, list[dict[str, Any]]] = {}
    for portafolio in portafolios:
        portafolios_por_ref.setdefault(
            portafolio["Referencia"], []
        ).append(portafolio)
    base["Portafolios_Detalle"] = base["Referencia"].map(portafolios_por_ref)
    base["Portafolios_Detalle"] = base["Portafolios_Detalle"].apply(
        lambda valor: valor if isinstance(valor, list) else []
    )

    def _oportunidades_generales(row: pd.Series) -> list[dict[str, Any]]:
        generales = []
        if bool(row["Acuerdo_Robo_Aplica"]):
            generales.append({
                "nombre": "Acuerdo para Robo",
                "valor": row["Acuerdo_Robo_Valor"],
                "detalle": row["Acuerdo_Robo_Detalle"],
                "deudas": list(row["Acuerdo_Robo_IDs"]),
            })
        if bool(row["IA_Liquidadora_Aplica"]):
            generales.append({
                "nombre": "IA Liquidadora",
                "valor": row["IA_Liquidadora_Valor"],
                "detalle": row["IA_Liquidadora_Detalle"],
                "deudas": list(row["IA_Liquidadora_IDs"]),
            })
        return generales

    base["Oportunidades_Generales"] = base.apply(
        _oportunidades_generales, axis=1
    )

    # Calculamos el Ingreso Estimado con todas las oportunidades. La vista lo
    # recalcula según los filtros de Oportunidad y Tipo de Análisis.
    base = calcular_ingreso_estimado_masivo(
        base, tipo_analisis="Todos", oportunidades=None
    )

    portafolios_array = base["Portafolios_Detalle"].to_numpy()
    generales_array = base["Oportunidades_Generales"].to_numpy()
    oportunidades_lista: list[list[str]] = []
    num_calculadas_lista: list[int] = []
    num_generales_lista: list[int] = []
    for portafolios_cliente, generales_cliente in zip(
        portafolios_array, generales_array
    ):
        nombres = []
        num_calculadas = 0
        for portafolio in portafolios_cliente:
            for oportunidad in (
                portafolio.get("Trad_Oportunidades", [])
                + portafolio.get("Cred_Oportunidades", [])
            ):
                nombres.append(oportunidad.get("nombre"))
                num_calculadas += 1
        for oportunidad in generales_cliente:
            nombres.append(oportunidad.get("nombre"))
        nombres_set = set(nombres)
        oportunidades_lista.append([
            nombre for nombre in OPORTUNIDADES if nombre in nombres_set
        ])
        num_calculadas_lista.append(num_calculadas)
        num_generales_lista.append(len(generales_cliente))

    base["Oportunidades"] = oportunidades_lista
    base["Num_Oportunidades_Calculadas"] = num_calculadas_lista
    base["Num_Oportunidades_Generales"] = num_generales_lista
    base["Num_Oportunidades"] = (
        base["Num_Oportunidades_Calculadas"] + base["Num_Oportunidades_Generales"]
    )

    detalles_lista: list[list[dict[str, Any]]] = []
    for portafolios_cliente in portafolios_array:
        detalles = []
        for portafolio in portafolios_cliente:
            detalles.extend(portafolio.get("Deudas_Detalle", []))
        detalles.sort(
            key=lambda detalle: (
                str(detalle.get("Banco") or ""),
                str(detalle.get("Id_Deuda") or ""),
            )
        )
        detalles_lista.append(detalles)
    base["Deudas_Detalle"] = detalles_lista

    # Paso 12b: Listas de Estados, Bancos y Casas de Cobro para Filtros y Resumen
    def _valores_unicos_detalle(
        detalle: Any,
        campo: str,
        etiqueta_vacio: str,
    ) -> list[str]:
        if not isinstance(detalle, list) or not detalle:
            return []
        valores = set()
        for deuda in detalle:
            if not isinstance(deuda, dict):
                continue
            valor = str(deuda.get(campo) or "").strip()
            valores.add(valor or etiqueta_vacio)
        return sorted(valores)

    base["Estados_Actualizacion"] = base["Deudas_Detalle"].apply(
        lambda detalle: _valores_unicos_detalle(
            detalle, "Etiqueta_Actualizacion", "Sin actualización"
        )
    )
    base["Bancos"] = base["Deudas_Detalle"].apply(
        lambda detalle: _valores_unicos_detalle(detalle, "Banco", "Sin banco")
    )
    base["Casas_Cobro"] = base["Deudas_Detalle"].apply(
        lambda detalle: _valores_unicos_detalle(
            detalle, "Casa_Cobro", "Sin casa de cobro"
        )
    )

    # Paso 13: Completar Columnas Faltantes y Normalizar Tipos
    base = _asegurar_columnas_resultado_masivo(base)
    columnas_numericas = [
        "Pricing", "Ahorro", "Por_Cobrar", "Ahorro_Neto", "PaB_Origen_Total",
        "PaB_Actualizado_Total", "Descuento_Actual", "Pago_Actual",
        "Ingreso_Actual", "Ingreso_Estimado", "Apartado_Neto", "Descuento_Esperado_Ponderado",
        "Deudas_Analizadas", "Deudas_Masivas", "Deudas_Con_PaB_Ideal",
        "Deudas_Sin_PaB_Ideal", "Trad_PaB_Origen_Total",
        "Trad_PaB_Actualizado_Total", "Trad_Descuento_Actual", "Trad_Pago_Actual",
        "Trad_Ingreso_Actual", "Trad_Apartado_Neto",
        "Trad_Descuento_Esperado_Ponderado", "Trad_Num_Deudas",
        "Trad_Deposito_Extra_Valor", "Trad_Contraoferta_Valor",
        "Cred_PaB_Origen_Total", "Cred_PaB_Actualizado_Total",
        "Cred_PaB_Ideal_Total", "Cred_Descuento_Actual", "Cred_Pago_Actual",
        "Cred_Num_Deudas", "Cred_Descuento_Esperado_Ponderado",
        "Cred_Deposito_Extra_Valor", "Cred_Contraoferta_Valor",
        "Acuerdo_Robo_Deudas", "IA_Liquidadora_Valor", "Num_Oportunidades",
        "Num_Oportunidades_Calculadas", "Num_Oportunidades_Generales",
    ]
    for columna in columnas_numericas:
        base[columna] = pd.to_numeric(base[columna], errors="coerce").fillna(0.0)

    columnas_booleanas = [
        "Tiene_Deudas_Liquidaciones", "Tiene_Pipeline_Credito",
        "No_Opta_Credito", "Rechazo_Credito", "Credito_Viable",
        "Credito_Habilitado", "Tradicional_Habilitado",
        "Trad_Deposito_Extra_Aplica", "Trad_Contraoferta_Aplica",
        "Trad_Liq_Insta_Aplica", "Trad_Viable", "Trad_Alguna_Viable",
        "Cred_Deposito_Extra_Aplica", "Cred_Contraoferta_Aplica",
        "Cred_Liq_Insta_Aplica", "Cred_Viable", "Cred_Alguna_Viable",
        "Acuerdo_Robo_Aplica", "IA_Liquidadora_Aplica", "Es_Viable",
    ]
    for columna in columnas_booleanas:
        base[columna] = base[columna].fillna(False).astype(bool)

    for columna in (
        "Referencia", "Nombre_Cliente", "Negociador", "Prospecto_Credito",
        "Prospecto_Tradicional", "Credito_Detalle", "Estado_Credito",
        "Trad_Deposito_Extra_Detalle", "Trad_Contraoferta_Detalle",
        "Trad_Liq_Insta_Detalle", "Cred_Deposito_Extra_Detalle",
        "Cred_Contraoferta_Detalle", "Cred_Liq_Insta_Detalle",
        "Acuerdo_Robo_Valor", "Acuerdo_Robo_Detalle", "IA_Liquidadora_Detalle",
        "Fuente_Descuento",
    ):
        base[columna] = base[columna].fillna("").astype(str)

    for columna in (
        "Deudas_Analizadas", "Deudas_Masivas", "Deudas_Con_PaB_Ideal",
        "Deudas_Sin_PaB_Ideal", "Trad_Num_Deudas", "Cred_Num_Deudas",
        "Acuerdo_Robo_Deudas", "Num_Oportunidades",
        "Num_Oportunidades_Calculadas", "Num_Oportunidades_Generales",
    ):
        base[columna] = pd.to_numeric(base[columna], errors="coerce").fillna(0).astype(int)

    _reportar_progreso_masivo(progreso_callback, 1.0, "Cálculo masivo completado.")
    return base[_columnas_resultado_masivo()].reset_index(drop=True)

def calcular_oportunidades_masivas(
    *,
    solo_masivas: bool = True,
    incluir_acuerdos_robo: bool = True,
    progreso_callback: Optional[Callable[[float, str], None]] = None,
) -> pd.DataFrame:
    """Carga las fuentes y calcula las oportunidades de todos los clientes.

    Esta función es la envoltura de Streamlit: carga los datos cacheados,
    construye el mapa batch de vencimientos de Metabase y delega el cálculo
    vectorizado a ``calcular_oportunidades_masivas_datos``.

    Args:
        solo_masivas (bool): Si True, solo analiza deudas con Masivas vigente.
        incluir_acuerdos_robo (bool): Si True, evalúa Acuerdos para Robo.
        progreso_callback (Optional[Callable[[float, str], None]]): Callback de avance.

    Returns:
        pd.DataFrame: Resultado con una fila por Referencia.
    """
    # Paso 1: Referencias Habilitadas según el Rol
    _reportar_progreso_masivo(progreso_callback, 0.02, "Verificando Referencias habilitadas...")
    referencias = obtener_referencias_habilitadas()
    if not referencias:
        return _resultado_masivo_vacio()

    # Paso 2: Cargar las Fuentes de Datos
    _reportar_progreso_masivo(progreso_callback, 0.08, "Cargando Asignación de Cartera...")
    asignacion_df = load_asignacion_cartera()
    if asignacion_df is None or asignacion_df.empty:
        return _resultado_masivo_vacio()
    _reportar_progreso_masivo(progreso_callback, 0.16, "Cargando Masivas de Alianzas...")
    masivas_df = load_masivas()
    _reportar_progreso_masivo(progreso_callback, 0.24, "Cargando PaB Ideal de Crédito...")
    pab_ideal = load_pab_ideal()
    _reportar_progreso_masivo(progreso_callback, 0.32, "Cargando Saldos de Clientes...")
    saldos = load_client_balances()
    _reportar_progreso_masivo(progreso_callback, 0.40, "Cargando Prospectos de Crédito...")
    prospectos_credito = load_prospectos_credito()
    _reportar_progreso_masivo(progreso_callback, 0.48, "Cargando Prospectos de Tradicional...")
    prospectos_tradicional = load_prospectos_tradicional()
    _reportar_progreso_masivo(progreso_callback, 0.56, "Cargando Pipeline de Crédito...")
    pipeline_credito = load_pipeline_credito()
    _reportar_progreso_masivo(progreso_callback, 0.62, "Cargando Liquidaciones...")
    liquidaciones = load_liquidaciones()
    # Las Actualizaciones se necesitan para Acuerdo para Robo y, cuando el
    # toggle está inactivo, también para el Descuento Actual.
    necesita_actualizaciones = incluir_acuerdos_robo or not solo_masivas
    solicitudes_df = (
        _obtener_solicitudes_mec_calculo()
        if (incluir_acuerdos_robo or not solo_masivas)
        else pd.DataFrame()
    )
    actualizaciones_df = (
        load_actualizacines_negos()
        if necesita_actualizaciones
        else pd.DataFrame()
    )
    hoy = pd.Timestamp.now(tz="America/Bogota").tz_localize(None).normalize()

    # Paso 3: Resolver los Vencimientos de Acuerdos en una Consulta Batch
    fechas_metabase: dict[str, Any] = {}
    if incluir_acuerdos_robo and actualizaciones_df is not None and not actualizaciones_df.empty:
        _reportar_progreso_masivo(progreso_callback, 0.68, "Preparando Acuerdos para Robo...")
        deudas_scope = (
            asignacion_df.loc[asignacion_df["Referencia"].isin(referencias), "Id_Deuda"]
            .apply(_normalizar_id_deuda)
            .dropna()
            .unique()
            .tolist()
        )
        acuerdos_alianza, pendientes = _preparar_acuerdos_robo_masivos(
            actualizaciones_df=actualizaciones_df,
            solicitudes_df=solicitudes_df,
            liquidaciones={_normalizar_id_deuda(d) for d in (liquidaciones or set())},
            deudas=deudas_scope,
            hoy=hoy,
        )
        if pendientes:
            _reportar_progreso_masivo(progreso_callback, 0.72, "Consultando vencimientos en Metabase...")
            vencimientos_df = load_vencimientos_acuerdos(
                debt_ids=tuple(sorted({p["Id_Deuda"] for p in pendientes}))
            )
            fechas_metabase = _construir_fechas_metabase_acuerdos(
                vencimientos_df=vencimientos_df,
                pendientes=pendientes,
            )

    # Paso 4: Calcular Vectorizadamente
    _reportar_progreso_masivo(progreso_callback, 0.78, "Calculando oportunidades masivas...")

    def _progreso_calculo(avance: float, mensaje: str) -> None:
        # El cálculo interno reporta 0-1; lo escalamos al tramo final de la barra.
        _reportar_progreso_masivo(
            progreso_callback, 0.78 + (0.20 * float(avance)), mensaje
        )

    resultado = calcular_oportunidades_masivas_datos(
        asignacion_df=asignacion_df,
        masivas_df=masivas_df,
        pab_ideal=pab_ideal,
        saldos=saldos,
        prospectos_credito=prospectos_credito,
        prospectos_tradicional=prospectos_tradicional,
        pipeline_credito=pipeline_credito,
        liquidaciones=liquidaciones,
        solicitudes_df=solicitudes_df,
        actualizaciones_df=actualizaciones_df,
        referencias=referencias,
        solo_masivas=solo_masivas,
        incluir_acuerdos_robo=incluir_acuerdos_robo,
        fechas_metabase=fechas_metabase,
        hoy=hoy,
        progreso_callback=_progreso_calculo,
    )
    _reportar_progreso_masivo(progreso_callback, 1.0, "Cálculo masivo completado.")
    return resultado