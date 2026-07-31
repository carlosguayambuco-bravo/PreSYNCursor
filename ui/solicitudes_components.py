# Estándar usando Pep8
# Librerías de Python
# Librerías de Terceros
import numpy as np
import pandas as pd
from pandera.typing import DataFrame
import streamlit as st
# Librerías Locales
from data.data_models import SolicitudesSchema
from modules.forms import obtener_nombre_negociador

# Función para Mostrar los Filtros Generales de una Solicitud
def mostrar_filtros_generales_solicitud(*, solicitudes_df: DataFrame[SolicitudesSchema]) -> DataFrame[SolicitudesSchema]:

    # Paso 1: Crear 4 Columnas (Tipo de Solicitud, Aliado , Estado de Solicitud, Ejecutivo)
    colTipo, colAliado, colEstado, colEjecutivo = st.columns(4)

    with colTipo:
        tipo_solicitud = st.selectbox(
            label="**Tipo de Solicitud**",
            options=["Todos"] + list(solicitudes_df["Tipo_Solicitud"].unique()),
            index=0,
            key="tipo_solicitud_gestion_input",
            help="Seleccione el tipo de solicitud que desea filtrar",
        )

    with colAliado:
        aliado_solicitud = st.selectbox(
            label="**Aliado - Casa de Cobro**",
            options=["Todos"] + list(solicitudes_df["Casa_Cobro"].unique()),
            index=0,
            key="aliado_solicitud_gestion_input",
            help="Seleccione el aliado que desea filtrar",
        )

    with colEstado:
        estado_solicitud = st.selectbox(
            label="**Estado de Solicitud**",
            options=["Todos"] + list(solicitudes_df["Estado_Solicitud"].unique()),
            index=0,
            key="estado_solicitud_gestion_input",
            help="Seleccione el estado de la solicitud que desea filtrar",
        )

    with colEjecutivo:
        ejecutivo_solicitud = st.selectbox(
            label="**Ejecutivo**",
            options=["Todos"] + list(solicitudes_df["Ejecutivo"].unique()),
            index=0,
            key="ejecutivo_solicitud_gestion_input",
            help="Seleccione el ejecutivo que desea filtrar",
        )

    # Paso 2: Crear un Expander para Filtros Auxiliares (Persona que Solicita, Banco, ID, Cedula, Id_Deuda)
    with st.expander("Filtros Auxiliares", expanded=False, key="expander_filtros_solicitudes_gestiones"):
        colPersona, colBanco, colID, colCedula, colIdDeuda = st.columns(5)

        with colPersona:
            persona_solicitud = st.selectbox(
                label="**Persona que Solicita (Correo)**",
                options=["Todos"] + list(solicitudes_df["Correo"].unique()),
                index=0,
                key="persona_solicitud_gestion_input",
                help="Seleccione el correo de la persona que solicita",
            )

        with colBanco:
            banco_solicitud = st.selectbox(
                label="**Banco**",
                options=["Todos"] + list(np.unique([d['Banco'] for d in solicitudes_df['Datos_Solicitud']])),
                index=0,
                key="banco_solicitud_gestion_input",
                help="Seleccione el banco que desea filtrar",
            )

        with colID:
            id_solicitud = st.selectbox(
                label="**ID de Solicitud**",
                options=["Todos"] + list(solicitudes_df["ID_Solicitud"].unique()),
                index=0,
                key="id_solicitud_gestion_input",
                help="Seleccione el ID de la solicitud que desea filtrar",
            )

        with colCedula:
            cedula_solicitud = st.selectbox(
                label="**Cédula**",
                options=["Todos"] + list(solicitudes_df["Cedula"].unique()),
                index=0,
                key="cedula_solicitud_gestion_input",
                help="Seleccione la cédula que desea filtrar",
            )

        with colIdDeuda:
            id_deuda_solicitud = st.selectbox(
                label="**ID de Deuda**",
                options=["Todos"] + list(np.unique([d for d in solicitudes_df['Ids_Deuda'].str.split('-').explode()])),
                index=0,
                key="id_deuda_solicitud_gestion_input",
                help="Seleccione el ID de deuda que desea filtrar",
            )

    # Paso 3: Aplicar ls filtros seleccionados al DataFrame de Solicitudes
    if tipo_solicitud != "Todos":
        solicitudes_df = solicitudes_df[solicitudes_df["Tipo_Solicitud"] == tipo_solicitud]

    if aliado_solicitud != "Todos":
        solicitudes_df = solicitudes_df[solicitudes_df["Casa_Cobro"] == aliado_solicitud]

    if estado_solicitud != "Todos":
        solicitudes_df = solicitudes_df[solicitudes_df["Estado_Solicitud"] == estado_solicitud]

    if ejecutivo_solicitud != "Todos":
        solicitudes_df = solicitudes_df[solicitudes_df["Ejecutivo"] == ejecutivo_solicitud]

    if persona_solicitud != "Todos" and st.session_state['expander_filtros_solicitudes_gestiones']:
        solicitudes_df = solicitudes_df[solicitudes_df["Correo"] == persona_solicitud]

    if banco_solicitud != "Todos" and st.session_state['expander_filtros_solicitudes_gestiones']:
        solicitudes_df = solicitudes_df[solicitudes_df["Datos_Solicitud"].apply(lambda x: any(d['Banco'] == banco_solicitud for d in x))]

    if id_solicitud != "Todos" and st.session_state['expander_filtros_solicitudes_gestiones']:
        solicitudes_df = solicitudes_df[solicitudes_df["ID_Solicitud"] == id_solicitud]

    if cedula_solicitud != "Todos" and st.session_state['expander_filtros_solicitudes_gestiones']:
        solicitudes_df = solicitudes_df[solicitudes_df["Cedula"] == cedula_solicitud]

    if id_deuda_solicitud != "Todos" and st.session_state['expander_filtros_solicitudes_gestiones']:
        solicitudes_df = solicitudes_df[solicitudes_df["Ids_Deuda"].str.contains(id_deuda_solicitud)]

    return solicitudes_df

# Función para Abrir el Dialogo de Respuesta de una Solicitud
@st.dialog("🗒️ Respuesta a Solicitud",dismissible=False,width="large")
def dialog_respuesta_solicitud(*, solicitud: pd.Series) -> None:
    pass


# Función para Mostrar los Datos de una Solicitud
def mostrar_datos_solicitud_ejecutivo(*,solicitud: pd.Series, is_main: bool = False) -> None:
    # Definimos el Nombre del Expander
    expander_name = "**{tipo}** • {aliado} | 📅 `{fecha}` | 📌 `{estado}` | 👤 **Ejecutivo:** {ejecutivo}".format(
        tipo=solicitud["Tipo_Solicitud"],
        fecha=solicitud["Fecha_Solicitud"].strftime("%Y-%m-%d %H:%M"),
        estado=solicitud["Estado_Solicitud"],
        ejecutivo=solicitud["Ejecutivo"],
        aliado=solicitud["Casa_Cobro"]
    )

    # Creamos el Expander para Mostrar los Datos de la Solicitud
    with st.expander(expander_name, expanded=is_main, key="expander_solicitud_{}".format(solicitud['ID_Solicitud'])):
        # Creamos un Espacio pequeño para Separar el Expander del Contenido
        st.space("xxsmall")

        # Creamos 4 Columnas para Mostrar: ID, Monto Total, Persona que Solicita y Bancos
        colID, colMonto, colPersona, colBancos = st.columns(4)

        with colID:
            st.markdown("**ID de Solicitud:**")
            st.code(solicitud["ID_Solicitud"], language="text")

        with colMonto:
            st.markdown("**Monto Total:**")
            monto_total_solicitud = sum(d['Monto_Propuesto'] for d in solicitud["Datos_Solicitud"])
            st.code("${:,.2f}".format(monto_total_solicitud), language="text")
        
        with colPersona:
            st.markdown("**Persona que Solicita:**")
            st.code(obtener_nombre_negociador(email=solicitud["Correo"], full_name=True), language="text")

        with colBancos:
            st.markdown("**Bancos:**")
            bancos_list = [d['Banco'] for d in solicitud["Datos_Solicitud"]]
            st.code(", ".join(bancos_list), language="text")

        # Siguiente: Caso Especial: Si es Acuerdo de Pago o Oferta de Pago, Mostrar Fecha de Pago y Tipo de Pago
        if solicitud["Tipo_Solicitud"] in ["Acuerdo de Pago", "Oferta de Pago"]:
            colFechaPago, colTipoPago = st.columns(2)

            with colFechaPago:
                st.markdown("**Fecha de Pago:**")
                fecha_pago = solicitud["Fecha_Esperada_Pago"].strftime("%Y-%m-%d") if pd.notnull(solicitud["Fecha_Esperada_Pago"]) else "No Brindada"
                st.code(fecha_pago, language="text")

            with colTipoPago:
                st.markdown("**Tipo de Pago:**")
                tipo_pago = solicitud["Tipo_Pago"] if pd.notnull(solicitud["Tipo_Pago"]) else "No Brindado"
                st.code(tipo_pago, language="text")

        # Paso Siguiente: Mostrar las Caracteristicas por Deuda de la Solicitud
        st.space("xxsmall")

        # Vamos a Crear 4 o 5 Columnas: Id_Deuda, Banco, Numero_Credito, Monto Propuesto , Cuotas(Si Hay)
        hay_cuotas = any(d['Num_Cuotas'] > 1 for d in solicitud["Datos_Solicitud"])

        if hay_cuotas:
            colIdDeuda, colBanco, colNumCredito, colMontoPropuesto, colCuotas = st.columns(5)
        else:
            colIdDeuda, colBanco, colNumCredito, colMontoPropuesto = st.columns(4)
            # Mostramos que es a 1 cuota
            st.info("Esta solicitud es a 1 cuota, por lo que no se muestran las cuotas.")

        with colIdDeuda:
            st.markdown("**ID de Deuda:**")
        with colBanco:
            st.markdown("**Banco:**")
        with colNumCredito:
            st.markdown("**Número de Crédito:**")
        with colMontoPropuesto:
            st.markdown("**Monto Propuesto:**")
        if hay_cuotas:
            with colCuotas: # type: ignore
                st.markdown("**Número de Cuotas:**")

        for d in solicitud["Datos_Solicitud"]:
            with colIdDeuda:
                st.code(d['Id_Deuda'], language="text")
            with colBanco:
                st.code(d['Banco'], language="text")
            with colNumCredito:
                st.code(d['Num_Credito'], language="text")
            with colMontoPropuesto:
                st.code("${:,.2f}".format(d['Monto_Propuesto']), language="text")
            if hay_cuotas:
                with colCuotas: # type: ignore
                    st.code(d['Num_Cuotas'], language="text")