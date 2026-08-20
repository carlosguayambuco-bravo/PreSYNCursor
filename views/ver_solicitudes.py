# Estándar usando Pep8
# Librerías de Python
# Librerías de Terceros
import streamlit as st
# Librerías Locales
from data.data_loader import load_current_month_solicitudes
from modules.forms import obtener_nombre_negociador
from modules.gest_sols import filtrar_solicitudes_por_usuario_actual, obtener_correos_a_cargo_usuario_actual, reiniciar_filtros_solicitudes_negociadores
from ui.solicitudes_components import mostrar_boton_limpiar_filtros_negociador, mostrar_datos_solicitud_negociador, mostrar_filtros_generales_solicitud_negociador, mostrar_resumen_solicitudes_negociador

# Paso 1: Cargar el DataFrame de Solicitudes
solicitudes_df = load_current_month_solicitudes()
# Paso 2: Filtar las Solicitudes segun el Usuario
solicitudes_df = filtrar_solicitudes_por_usuario_actual(solicitudes_df=solicitudes_df)

# Creamos la Función de Cambio de Pestaña
def on_change_tab_gest_sols():
    # Si el cambio de pestaña fue a la pestaña de Dashboard, reiniciamos los filtros de solicitudes
    if st.session_state['tabs_ver_solicitudes'] == "😎 Resumen de Solicitudes":
        reiniciar_filtros_solicitudes_negociadores()

# Inicializamos el Session State de Cantidad_Solicitudes_Ver_Negociador si no existe
if not ('Cantidad_Solicitudes_Ver_Negociador' in st.session_state):
    st.session_state['Cantidad_Solicitudes_Ver_Negociador'] = 10  # Valor por defecto


# --- Elementos de la Interfaz de Usuario ---
solicitudes_filtered = mostrar_filtros_generales_solicitud_negociador(solicitudes_df=solicitudes_df)

# Añadimos un Divisor
st.divider()

# Creamos las 2 Pestañas: Ver Solicitudes y Resumen de Solicitudes
tabVer, tabResumen = st.tabs(
    ["📄 Ver Solicitudes", "😎 Resumen de Solicitudes"], 
    on_change=on_change_tab_gest_sols,
    key="tabs_ver_solicitudes",
    width="stretch",
)

# Si no hay solicitudes, mostramos un mensaje
if solicitudes_filtered.empty:
    st.info("No hay solicitudes para mostrar. Si quieres reinicia los filtros.", icon="ℹ️")
    mostrar_boton_limpiar_filtros_negociador(key_extra="_vacio")
    st.stop()

if tabVer.open:
    with tabVer:
        st.title("📄 Ver Solicitudes")
        st.space("small")

        # Mostramos las Solicitudes según la Cantidad_Solicitudes_Ver_Negociador
        for _, solicitud in solicitudes_filtered.head(st.session_state['Cantidad_Solicitudes_Ver_Negociador']).iterrows():
            mostrar_datos_solicitud_negociador(solicitud=solicitud)

        # Creamos una Caption de cuantas soilicitudes estamos mostrando
        st.caption(
            "**Mostrando {} de {} Solicitudes.** (**{:.1%}**)".format(
                min(st.session_state['Cantidad_Solicitudes_Ver_Negociador'], len(solicitudes_filtered)),
                len(solicitudes_filtered),
                min(st.session_state['Cantidad_Solicitudes_Ver_Negociador'], len(solicitudes_filtered)) / len(solicitudes_filtered) if len(solicitudes_filtered) > 0 else 0
            )
        )

        # Creamos 2 Botones: Cargar Mas Solicitudes y Reiniciar Filtros
        colMas, colReiniciar = st.columns([2, 2], gap="large")

        with colMas:
            mas_solicitudes = st.button(
                "Cargar Más Solicitudes",
                key="cargar_mas_solicitudes_button",
                help="Haz clic para cargar más solicitudes",
                disabled=len(solicitudes_filtered) <= st.session_state['Cantidad_Solicitudes_Ver_Negociador'],
                type="primary"
            )

        with colReiniciar:
            mostrar_boton_limpiar_filtros_negociador(key_extra="_ver_solicitudes")

        if mas_solicitudes:
            st.session_state['Cantidad_Solicitudes_Ver_Negociador'] += 10  # Incrementamos en 10 la cantidad de solicitudes a mostrar
            st.rerun()  # Recargamos la página para mostrar más solicitudes

if tabResumen.open:
    with tabResumen:
        st.title("😎 Resumen de Solicitudes")
        st.space("small")

        # Paso 1: Definir quién se va a mostrar
        if st.session_state.get('ver_todos_a_mi_cargo', False):
            correos_revisar = obtener_correos_a_cargo_usuario_actual()
        else:
            correos_revisar = solicitudes_filtered['Correo'].unique().tolist()

        # Mostramos un Resumen general de las solicitudes 
        st.header("📊 Resumen General de Solicitudes")
        mostrar_resumen_solicitudes_negociador(solicitudes=solicitudes_df, nego_name='general', show_header=False)

        st.divider()

        st.header("👌 Resumen de Solicitudes por Negociador")
        for correo in correos_revisar:
            # Definimos el Nombre del Expander
            nombre_negociador = obtener_nombre_negociador(email=correo)
            nombre_expander = f"👤 {nombre_negociador} ({correo})"
            key_expander = f"expander_{correo}"
            with st.expander(nombre_expander, expanded=False, key=key_expander):
                # Filtramos las Solicitudes por el Correo del Negociador
                solicitudes_negociador = solicitudes_df[solicitudes_df['Correo'] == correo]
                mostrar_resumen_solicitudes_negociador(solicitudes=solicitudes_negociador, nego_name=nombre_negociador.replace(" ", "_").lower(), show_header=False)

        st.divider()
        # Siguiente: Mostramos el toggle para ver todos a mi cargo y para expandir o no todos los expanders
        colToggle, colExpand, colLimpiarBtt = st.columns([2, 2, 2], gap="large")
        with colToggle:
            ver_todos_a_mi_cargo = st.toggle(
                "Ver Todos a mi Cargo",
                value=st.session_state.get('ver_todos_a_mi_cargo', False),
                key="ver_todos_a_mi_cargo_toggle",
                help="Si marcas esta opción, se mostrarán todos los negociadores a tu cargo.",
            )
            st.session_state['ver_todos_a_mi_cargo'] = ver_todos_a_mi_cargo
        with colExpand:
            expandir_todos = st.toggle(
                "Expandir Todos",
                value=st.session_state.get('expandir_todos', False),
                key="expandir_todos_toggle",
                help="Si marcas esta opción, se expandirán todos los resúmenes de negociadores.",
            )
            if expandir_todos:
                for correo in correos_revisar:
                    key_expander = f"expander_{correo}"
                    st.session_state[key_expander] = True

        with colLimpiarBtt:
            mostrar_boton_limpiar_filtros_negociador(key_extra="_ver_resumen")