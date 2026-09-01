# Estándar usando Pep8
# Librerías de Python
# Librerías de Terceros
import streamlit as st
# Librerías Locales
from data.data_loader import (
    execute_query_cache, load_addendums, load_aliados_dataframe, load_app_config, load_cartera_activa,
    load_cartera_backup, load_client_balances, load_headcount_negociacion,
    load_liquidaciones, load_logs, load_masivas, load_pab_ideal,
    load_pendiente_cruce, load_reference_changes, load_solicitudes_mec,
    load_special_user_permissions, obtener_datos_completos_deudas,
    obtener_deudas_activas_con_retry, obtener_referencia_por_deuda,
    obtener_ultima_actualizacion_deudas,
)
from data.data_uploader import get_solicitud_id_to_row_mapping
from modules.classes import get_banned_manager
from ui.cache_components import mostrar_seccion_cache

# Lista de Funciones con Cache de Google Sheets: (Nombre, Función, Llaves del Session State Asociadas)
CACHE_FUNCS_GOOGLE_SHEETS = [
    ("load_solicitudes_mec", load_solicitudes_mec, ["solicitudes_mec_df", "solicitudes_headers", "local_solicitudes_changes"]),
    ("load_reference_changes", load_reference_changes, ["changes_references_dict"]),
    ("load_client_balances", load_client_balances, ["saldos_dict"]),
    ("load_pab_ideal", load_pab_ideal, ["pab_ideal_dict"]),
    ("load_aliados_dataframe", load_aliados_dataframe, ["aliados_dict"]),
    ("load_masivas", load_masivas, ["masivas_df"]),
    ("load_addendums", load_addendums, ["addendums_df"]),
    ("load_liquidaciones", load_liquidaciones, ["liquidations_set"]),
    ("load_headcount_negociacion", load_headcount_negociacion, ["headcount_df"]),
    ("load_app_config", load_app_config, ["app_config_dict"]),
    ("load_special_user_permissions", load_special_user_permissions, ["special_user_permissions_dict"]),
    ("load_cartera_activa", load_cartera_activa, []),
    ("load_logs", load_logs, []),
    ("load_cartera_backup", load_cartera_backup, []),
    ("load_pendiente_cruce", load_pendiente_cruce, ["local_cruce_changes"]),
    ("get_solicitud_id_to_row_mapping", get_solicitud_id_to_row_mapping, []),
]

# Lista de Funciones con Cache de Metabase: (Nombre, Función, Llaves del Session State Asociadas)
CACHE_FUNCS_METABASE = [
    ("obtener_referencia_por_deuda", obtener_referencia_por_deuda, []),
    ("obtener_deudas_activas_con_retry", obtener_deudas_activas_con_retry, []),
    ("obtener_ultima_actualizacion_deudas", obtener_ultima_actualizacion_deudas, []),
    ("obtener_datos_completos_deudas", obtener_datos_completos_deudas, []),
    ("execute_query_cache", execute_query_cache,[])
]

# Lista de Recursos con Cache: (Nombre, Función, Llaves del Session State Asociadas)
CACHE_RESOURCES = [
    ("get_banned_manager", get_banned_manager, []),
]

st.title("🤖 Manejo de Cache")
st.divider()

st.markdown("""
    En esta vista puedes reiniciar el cache de las funciones de carga de datos de forma individual.
    Al reiniciar el cache de una función, la próxima vez que se necesiten sus datos se volverán a
    consultar desde su origen (Google Sheets o Metabase).
""")

# --- Sección de Google Sheets ---
mostrar_seccion_cache(
    titulo="📊 Funciones de Google Sheets",
    descripcion="Funciones con cache de las llamadas a Google Sheets.",
    funciones=CACHE_FUNCS_GOOGLE_SHEETS,
)

st.divider()

# --- Sección de Metabase ---
mostrar_seccion_cache(
    titulo="🔍 Funciones de Metabase",
    descripcion="Funciones con cache de las consultas a Metabase.",
    funciones=CACHE_FUNCS_METABASE,
)

st.divider()

# --- Sección de Recursos ---
mostrar_seccion_cache(
    titulo="⚙️ Recursos de la Aplicación",
    descripcion="Recursos de la aplicación que mantienen estado en memoria.",
    funciones=CACHE_RESOURCES,
)

st.divider()
st.markdown("""
    **Nota:** El cache de las funciones se limpia de forma individual y los datos asociados se
    recargarán automáticamente desde su origen en la próxima ejecución de la aplicación.
""")
