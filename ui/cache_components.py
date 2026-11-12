# Estándar usando Pep8
# Librerías de Python
from time import sleep
# Librerías de Terceros
import streamlit as st

# Función Auxiliar para Reiniciar los Caches y sus Llaves de Session State
def reiniciar_caches(*, funciones: list, claves_session_state: list[str]) -> None:
    # Limpiamos el Cache de Cada Función Recibida
    for func in funciones:
        func.clear()
    # Limpiamos las Llaves del Session State Asociadas para que los Datos se Recarguen
    for clave in claves_session_state:
        st.session_state.pop(clave, None)

# Función Auxiliar para Mostrar una Fila de Reset de Cache
def _mostrar_fila_reset(*, nombre: str, func, ss_keys: list[str]) -> None:
    # Creamos 2 Columnas Alineadas: Nombre de la Función y Botón de Reseteo
    colNombre, colBoton = st.columns([3, 1], vertical_alignment="center", gap="small")

    with colNombre:
        st.code(nombre, language="text")

    with colBoton:
        if st.button(
            "Reiniciar",
            key="reset_cache_{}".format(nombre),
            help="Reiniciar el cache de la función {}".format(nombre),
            icon="🔄",
            width="stretch",
        ):
            # Limpiamos el Cache de la Función y sus Llaves Asociadas
            reiniciar_caches(funciones=[func], claves_session_state=ss_keys)

            st.toast("Cache de {} reiniciado correctamente".format(nombre), icon="✅")
            sleep(1)
            st.rerun()

# Función Auxiliar para Mostrar una Sección de Funciones con Cache
def mostrar_seccion_cache(*, titulo: str, descripcion: str, funciones: list[tuple]) -> None:
    st.subheader(titulo)
    st.caption(descripcion)

    # Creamos la Fila de Encabezados de las 2 Columnas
    colNombreHeader, colBotonHeader = st.columns([3, 1], vertical_alignment="center", gap="small")
    with colNombreHeader:
        st.markdown("**Nombre de la Función**")
    with colBotonHeader:
        st.markdown("**Reseteo de la Función**")

    # Iteramos por cada una de las Funciones con Cache
    for nombre, func, ss_keys in funciones:
        _mostrar_fila_reset(nombre=nombre, func=func, ss_keys=ss_keys)