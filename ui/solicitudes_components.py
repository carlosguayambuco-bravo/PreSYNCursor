# Estándar usando Pep8
# Librerías de Python
from typing import Optional
from time import sleep
# Librerías de Terceros
import numpy as np
import pandas as pd
from pandas import col
from pandera.typing import DataFrame
import streamlit as st
from st_copy import copy_button
import plotly.graph_objects as go
import plotly.express as px
# Librerías Locales
from data.data_uploader import upload_form_response_to_google_sheets
from modules.acuerdo_pdf_generator.agreement_pdf import generate_payment_agreement_pdf
from modules.bank_normalizer import BANCOS_UNICOS
from modules.constants import ESTADOS_POSIBLES_SOLICITUD, ESTADOS_PREFINALIZAR_SOLICITUD
from modules.forms import obtener_nombre_negociador
from modules.gest_sols import actualizar_aprobacion_necesaria, add_metadata_to_uploaded_pdf, check_if_acuerdo_pago_uploaded, check_if_validacion_uploaded, crear_plantilla_solicitud_acuerdo_pago, crear_plantilla_solicitud_validacion, es_solicitud_aprobacion_necesaria, es_solicitud_sin_responder, obtener_df_bancos_sin_responder, obtener_link_acuerdo_pago, obtener_mascara_aprobacion_necesaria, obtener_mascara_exitosas, obtener_promedio_respuestas_dia, obtener_promedio_tiempos_respuesta, obtener_tipo_aprobacion_necesaria, reiniciar_filtros_solicitudes_negociadores, subir_acuerdo_pago_a_google_drive, distribuir_resultado_solicitud, obtener_mascara_sin_responder, get_descuento_en_base, get_solicitud_txt, update_solicitudes_to_solicitado, upload_massive_addendums, reiniciar_filtros_solicitudes_ejecutivo, generate_plantilla_serie_acuerdo
from modules.classes import get_banned_manager
from utils.helpers_general import cleanNumber, formatNumber, getBDDaysDiffFloat_vectorized, getBDDaysDiffFloat

# Función para Mostrar los Filtros Generales de una Solicitud (Versión Ejecutivo)
def mostrar_filtros_generales_solicitud_ejecutivo(*, solicitudes_df: pd.DataFrame) -> pd.DataFrame:

    solicitudes_copy = solicitudes_df.copy()  # Creamos una copia del DataFrame para no modificar el original

    # Vamos a Crear 3 Columnas: Boton de Reinicio Total, Boton de Reinicio Basico y Boton de Recomendado
    colResetTotal, colResetBasico, colRecomendado = st.columns(3, vertical_alignment="center")

    with colResetTotal:
        st.button(
            label="Reiniciar Filtros (Total)",
            key="reiniciar_filtros_solicitudes_ejecutivo_total",
            type="secondary",
            on_click=reiniciar_filtros_solicitudes_ejecutivo,
            args=('reset',),
            help="Haga clic para reiniciar todos los filtros de solicitudes.",
        )

    with colResetBasico:
        usar_basico = st.button(
            label="Reiniciar Filtros (Básico)",
            key="reiniciar_filtros_solicitudes_ejecutivo_basico",
            type="primary",
            on_click=reiniciar_filtros_solicitudes_ejecutivo,
            args=('basic',),
            help="Haga clic para reiniciar los filtros de solicitudes de forma básica.",
        )

    with colRecomendado:
        usar_recomendado = st.toggle(
            label="**Filtros Recomendados**",
            key="filtros_recomendados_solicitudes",
            help="Haga clic para aplicar los filtros recomendados.",
        )

    # Paso 1: Crear 4 Columnas (Tipo de Solicitud, Aliado , Estado de Solicitud, Ejecutivo)
    colTipo, colAliado, colEstado, colEjecutivo = st.columns(4)

    with colTipo:
        tipo_solicitud = st.multiselect(
            label="**Tipo de Solicitud**",
            options=list(solicitudes_df["Tipo_Solicitud"].unique()),
            key="tipo_solicitud_gestion_input",
            help="Seleccione el tipo de solicitud que desea filtrar",
            disabled = usar_recomendado,
        )

    with colAliado:
        aliado_solicitud = st.multiselect(
            label="**Aliado - Casa de Cobro**",
            options=list(solicitudes_df["Casa_Cobro"].unique()),
            key="aliado_solicitud_gestion_input",
            help="Seleccione el aliado que desea filtrar",
            disabled = usar_recomendado,
        )

    with colEstado:
        estado_solicitud = st.multiselect(
            label="**Estado de Solicitud**",
            options=list(solicitudes_df["Estado_Solicitud"].unique()),
            key="estado_solicitud_gestion_input",
            help="Seleccione el estado de la solicitud que desea filtrar",
            disabled = usar_recomendado,
        )

    with colEjecutivo:
        ejecutivo_solicitud = st.multiselect(
            label="**Ejecutivo**",
            options=list(solicitudes_df["Ejecutivo"].unique()),
            key="ejecutivo_solicitud_gestion_input",
            help="Seleccione el ejecutivo que desea filtrar",
            disabled = usar_recomendado,
        )

    # Paso 2: Crear un Expander para Filtros Auxiliares (Persona que Solicita, Banco, ID, Cedula, Id_Deuda)
    with st.expander("Filtros Auxiliares", expanded=False):
        colPersona, colBanco, colID, colCedula, colIdDeuda = st.columns(5)

        with colPersona:
            persona_solicitud = st.selectbox(
                label="**Correo que Solicita**",
                options=["Todos"] + list(solicitudes_df["Correo"].unique()),
                index=0,
                key="persona_solicitud_gestion_input",
                help="Seleccione el correo de la persona que solicita",
                disabled = usar_recomendado,
            )

        with colBanco:
            banco_solicitud = st.multiselect(
                label="**Banco**",
                options= ["Todos"] + list(np.unique([d['Banco'] for datos in solicitudes_df['Datos_Solicitud'].values for d in datos])),
                key="banco_solicitud_gestion_input",
                help="Seleccione el banco que desea filtrar",
                disabled = usar_recomendado,
            )

        with colID:
            id_solicitud = st.selectbox(
                label="**ID de Solicitud**",
                options=["Todos"] + list(solicitudes_df["ID_Solicitud"].unique()),
                index=0,
                key="id_solicitud_gestion_input",
                help="Seleccione el ID de la solicitud que desea filtrar",
                disabled = usar_recomendado,
            )

        with colCedula:
            cedula_solicitud = st.selectbox(
                label="**Cédula**",
                options=["Todos"] + list(solicitudes_df["Cedula"].unique()),
                index=0,
                key="cedula_solicitud_gestion_input",
                help="Seleccione la cédula que desea filtrar",
                disabled = usar_recomendado,
            )

        with colIdDeuda:
            id_deuda_solicitud = st.selectbox(
                label="**ID de Deuda**",
                options=["Todos"] + list(np.unique([d for d in solicitudes_df['Ids_Deuda'].str.split('-').explode()])),
                index=0,
                key="id_deuda_solicitud_gestion_input",
                help="Seleccione el ID de deuda que desea filtrar",
                disabled = usar_recomendado,
            )

    # Paso 3: Aplicar ls filtros seleccionados al DataFrame de Solicitudes
    if tipo_solicitud:
        solicitudes_df = solicitudes_df[solicitudes_df["Tipo_Solicitud"].isin(tipo_solicitud)]

    if aliado_solicitud:
        solicitudes_df = solicitudes_df[solicitudes_df["Casa_Cobro"].isin(aliado_solicitud)]

    if estado_solicitud:
        solicitudes_df = solicitudes_df[solicitudes_df["Estado_Solicitud"].isin(estado_solicitud)]

    if ejecutivo_solicitud:
        solicitudes_df = solicitudes_df[solicitudes_df["Ejecutivo"].isin(ejecutivo_solicitud)]

    if persona_solicitud != "Todos":
        solicitudes_df = solicitudes_df[solicitudes_df["Correo"] == persona_solicitud]

    if not ("Todos" in banco_solicitud) and banco_solicitud:
        solicitudes_df = solicitudes_df[solicitudes_df["Datos_Solicitud"].apply(lambda x: any((d['Banco'] in banco_solicitud) for d in x))]

    if id_solicitud != "Todos":
        solicitudes_df = solicitudes_df[solicitudes_df["ID_Solicitud"] == id_solicitud]

    if cedula_solicitud != "Todos":
        solicitudes_df = solicitudes_df[solicitudes_df["Cedula"] == cedula_solicitud]

    if id_deuda_solicitud != "Todos":
        solicitudes_df = solicitudes_df[solicitudes_df["Ids_Deuda"].str.contains(id_deuda_solicitud)]

    # Paso 4: Quitar los IDs de Solicitudes que ya fueron respondidas y están en el BannedManager
    if usar_recomendado or usar_basico:
        banned_manager = get_banned_manager()
        solicitudes_df = solicitudes_df[~(solicitudes_df["ID_Solicitud"].apply(banned_manager.is_banned))]
        solicitudes_copy = solicitudes_copy[~(solicitudes_copy["ID_Solicitud"].apply(banned_manager.is_banned))]    

    # Si es Recomendado se realizan filtros aparte
    if usar_recomendado:
        # Siguiente: Dejar en Solicitudes:
        # Estados: Sin Tocar, Bajo Comité (Con estado comite 1), Titular Ilocalizable (Con estado ilocalizable 1)
        maskNotAnswered = obtener_mascara_sin_responder(solicitudes_copy)
        solicitudes_df = solicitudes_copy[maskNotAnswered].copy()

        # Siguiente: Crear Copia con Columna Prioridad
        # Paso 1: Crear Columna Fecha_Hoy
        calc_df = solicitudes_df.assign(Fecha_Hoy=pd.Timestamp.now('America/Bogota').tz_localize(None))
        # Paso 2: Crear Columna de Diferencia de Días Vectorizada
        calc_df["Diferencia_Dias"] = getBDDaysDiffFloat_vectorized(calc_df["Timestamp"], calc_df["Fecha_Hoy"])
        # Paso 3: X2 a la Diferencia_Dias si Tipo_Pago == 'Crédito'
        calc_df["Diferencia_Dias"] *= np.where(calc_df["Tipo_Pago"] == "Crédito", 2, 1)
        # Paso 4: Usar np.argsort para obtener los índices ordenados por Diferencia_Dias de mayor a menor
        sorted_indices = np.argsort((calc_df["Diferencia_Dias"]).to_numpy())
        # Paso 5: Aplicar este orden a solicitudes_df para obtener el DataFrame final ordenado
        solicitudes_df = solicitudes_df.iloc[sorted_indices]
    else:
        # Ordenamos los más antiguos primero
        solicitudes_df = solicitudes_df.sort_values(by="Timestamp", ascending=True)

    # Por Último devolvemos el DataFrame de Solicitudes filtrado
    return solicitudes_df

# Función Auxiliar para mostrar filtros generales de Solicitudes (Versión Negociador)
def mostrar_filtros_generales_solicitud_negociador(*, solicitudes_df: pd.DataFrame) -> pd.DataFrame:

    # Si no hay Solicitudes, no hacemos nada
    if solicitudes_df.empty:
        st.warning("No hay solicitudes disponibles para mostrar. Sube una Solicitud", icon="⚠️")
        return solicitudes_df

    # Paso 1: Filtros Generales
    # Se van a tener estos Filtros: Toggles (Sin Responder, Aprobación y Ordenamiento por Fecha)
    # Nombre Cliente, Tipo de Soliciutd, Estado Solicitud, Aliado
    
    # Creamos las Columnas
    colCliente, colTipoSolicitud, colEstado, colAliado, colToggles = st.columns(5, border=True)

    with colCliente:
        clientes_posibles = list(solicitudes_df["Metadata_Solicitud"].apply(lambda x: x.get("Nombre_Cliente", "Desconocido")).unique())
        cliente_seleccionado = st.selectbox(
            label="**👤 Nombre del Cliente**",
            options=["Todos"] + clientes_posibles,
            index=0,
            key="cliente_solicitud_nego_input",
            help="Seleccione el nombre del cliente que desea filtrar",
        )

    with colTipoSolicitud:
        tipos_posibles = list(solicitudes_df["Tipo_Solicitud"].unique())
        tipo_seleccionado = st.selectbox(
            label="**📋 Tipo de Solicitud**",
            options=["Todos"] + tipos_posibles,
            index=0,
            key="tipo_solicitud_nego_input",
            help="Seleccione el tipo de solicitud que desea filtrar",
        )

    with colEstado:
        estados_posibles = list(solicitudes_df["Estado_Solicitud"].unique())
        estado_seleccionado = st.selectbox(
            label="**📊 Estado de Solicitud**",
            options=["Todos"] + estados_posibles,
            index=0,
            key="estado_solicitud_nego_input",
            help="Seleccione el estado de la solicitud que desea filtrar",
        )

    with colAliado:
        aliados_posibles = list(solicitudes_df["Casa_Cobro"].unique())
        aliado_seleccionado = st.selectbox(
            label="**🥸 Aliado - Casa de Cobro**",
            options=["Todos"] + aliados_posibles,
            index=0,
            key="aliado_solicitud_nego_input",
            help="Seleccione el aliado que desea filtrar",
        )

    with colToggles:
        toggle_exitosas = st.toggle(
            label="**✅ Exitosas**",
            value=True,
            key="toggle_exitosas_solicitud_nego_input",
            help="Filtra las solicitudes que aún no han sido respondidas.",
        )
        toggle_aprobacion = st.toggle(
            label="**🔐 Requiere Aprobación**",
            value=False,
            key="toggle_aprobacion_solicitud_nego_input",
            help="Filtra las solicitudes que están en estado de aprobación.",
        )
        toggle_orden_fecha = st.toggle(
            label="**🗓️ Ordenar de Primera a Última**",
            value=False,
            key="toggle_orden_fecha_solicitud_nego_input",
            help="Ordena las solicitudes por fecha de creación.",
        )

    # Ahora Creamos un Expander para los Filtros Específicos, que son:
    # ID_Solicitud, Referencia, Id_Deuda, Banco, Persona que Solicito
    with st.expander("✴️ **Filtros Específicos**", expanded=False):
        # Creamos las 5 Columnas
        colID, colPersona, colReferencia, colIdDeuda, colBanco = st.columns(5, vertical_alignment="center")

        with colID:
            ids_posibles = list(solicitudes_df["ID_Solicitud"].unique())
            id_solicitud = st.selectbox(
                label="**🆔 ID de Solicitud**",
                options=["Todos"] + ids_posibles,
                index=0,
                key="id_solicitud_nego_input",
                help="Ingrese el ID de la solicitud que desea filtrar",
            )

        with colPersona:
            personas_posibles = list(solicitudes_df["Correo"].unique())
            persona_solicitud = st.selectbox(
                label="**📧 Persona que Solicita**",
                options=["Todos"] + personas_posibles,
                index=0,
                key="persona_solicitud_nego_input",
                help="Ingrese el correo de la persona que solicita la solicitud que desea filtrar",
            )

        with colReferencia:
            referencias_posibles = list(solicitudes_df["Referencia"].unique())
            referencia_solicitud = st.selectbox(
                label="**📄 Referencia**",
                options=["Todos"] + referencias_posibles,
                index=0,
                key="referencia_solicitud_nego_input",
                help="Ingrese la referencia de la solicitud que desea filtrar",
            )

        with colIdDeuda:
            # Obtenemos los IDs de Deuda posibles
            id_deuda_posibles = list(solicitudes_df["Ids_Deuda"].str.split("-").explode().unique())
            id_deuda_solicitud = st.multiselect(
                label="**🆔 ID de Deuda**",
                options=["Todos"] + id_deuda_posibles,
                default=["Todos"],
                key="id_deuda_solicitud_nego_input",
                help="Ingrese el ID de la deuda que desea filtrar",
            )

        with colBanco:
            bancos_posibles = list(solicitudes_df["Datos_Solicitud"].apply(lambda l: [x.get("Banco", "Desconocido") for x in l]).explode().unique())
            banco_solicitud = st.multiselect(
                label="**🏦 Banco**",
                options=["Todos"] + bancos_posibles,
                default=["Todos"],
                key="banco_solicitud_nego_input",
                help="Ingrese el nombre del banco que desea filtrar",
            )

    # Siguiente: Aplicar los Filtros Seleccionados al DataFrame de Solicitudes
    if cliente_seleccionado != "Todos":
        solicitudes_df = solicitudes_df[solicitudes_df["Metadata_Solicitud"].apply(lambda x: x.get("Nombre_Cliente", "Desconocido")) == cliente_seleccionado]

    if tipo_seleccionado != "Todos":
        solicitudes_df = solicitudes_df[solicitudes_df["Tipo_Solicitud"] == tipo_seleccionado]

    if estado_seleccionado != "Todos":
        solicitudes_df = solicitudes_df[solicitudes_df["Estado_Solicitud"] == estado_seleccionado]

    if aliado_seleccionado != "Todos":
        solicitudes_df = solicitudes_df[solicitudes_df["Casa_Cobro"] == aliado_seleccionado]

    if id_solicitud != "Todos":
        solicitudes_df = solicitudes_df[solicitudes_df["ID_Solicitud"] == id_solicitud]

    if persona_solicitud != "Todos":
        solicitudes_df = solicitudes_df[solicitudes_df["Correo"] == persona_solicitud]

    if referencia_solicitud != "Todos":
        solicitudes_df = solicitudes_df[solicitudes_df["Referencia"] == referencia_solicitud]

    if not ("Todos" in id_deuda_solicitud) and id_deuda_solicitud:
        solicitudes_df = solicitudes_df[solicitudes_df["Ids_Deuda"].str.contains("|".join(id_deuda_solicitud))]

    if not ("Todos" in banco_solicitud) and banco_solicitud:
        solicitudes_df = solicitudes_df[solicitudes_df["Datos_Solicitud"].apply(lambda l: [x.get("Banco", "Desconocido") for x in l]).apply(lambda x: any(b in x for b in banco_solicitud))]

    # Siguiente: Aplicar la Lógica de los Toggles
    if toggle_exitosas:
        maskExitosas = obtener_mascara_exitosas(solicitudes_df)
        solicitudes_df = solicitudes_df[maskExitosas]
    if toggle_aprobacion:
        maskAprobacion = obtener_mascara_aprobacion_necesaria(solicitudes_df)
        solicitudes_df = solicitudes_df[maskAprobacion]

    # Aplicamos el Ordenamiento por Fecha
    solicitudes_df = solicitudes_df.sort_values(by=["Fecha_Respuesta","Timestamp"], ascending=toggle_orden_fecha, na_position="last")

    # Por Último devolvemos el DataFrame de Solicitudes filtrado
    return solicitudes_df

# Función Auxiliar para mostrar el Botón que va a Finalizar la Solicitud y mantener toda la Lógica de forma Interna
def mostrar_boton_actualizar_solicitudes(*, solicitud: pd.Series, pdf_bytes: Optional[bytes] = None) -> None:
    # Primero: Mostrar el Boton de la Solicitud y el Botón de Cancelar
    colCancelar, colBoton = st.columns([1, 1])

    with colCancelar:
        if st.button(
            label="**Cancelar**",
            key="cancelar_solicitud_{}".format(solicitud['ID_Solicitud']),
            help="Haga clic para cancelar la actualización de la solicitud.",
            width="stretch",
            type="secondary",
        ):
            st.rerun()

    with colBoton:
        actualizar_solicitud = st.button(
            label="**Finalizar Solicitud**",
            key="finalizar_solicitud_{}".format(solicitud['ID_Solicitud']),
            width="stretch",
            type="primary",
        )
    if actualizar_solicitud:
        with st.spinner("Subiendo Solicitud a Google Sheets..."):
            # Subimos el Acuerdo de Pago si es necesario
            if (pdf_bytes is not None) and len(pdf_bytes) > 0:
                file_id = subir_acuerdo_pago_a_google_drive(pdf_bytes=pdf_bytes, solicitud_info=solicitud)
                success = bool(file_id)
                # Guardamos el Id del Acuerdo en la Metadata de la Solicitud
                solicitud["Metadata_Solicitud"]["Id_Acuerdo_Pago"] = file_id
            else:
                success = True  # No hay PDF para subir, consideramos que la subida fue exitosa
            # Actualizamos la Solicitud en Google Sheets
            success = distribuir_resultado_solicitud(solicitud, pdf_bytes=pdf_bytes) and success
            # Actualizamos los Datos de Addendums
            upload_massive_addendums(solicitud=solicitud)
        if success:
            st.toast("Solicitud Finalizada y Actualizada a Google Sheets con Éxito.",icon="✅")
            sleep(2)
            st.rerun()
        else:
            st.error("Error al Subir la Solicitud a Google Sheets o el Acuerdo de Pago a Google Drive. Por favor, intente nuevamente.")

# Función Auxiliar para mostrar las Especificaciones del Acuerdo de Pago Generado
def mostrar_especificaciones_acuerdo_generado(*, solicitud: pd.Series) -> bytes:

    # Paso 1: Mostrar los Inputs del Acuerdo de Pago Generado
    with st.expander("**🔏 Especificaciones del Acuerdo de Pago Generado**", expanded=False):
        st.markdown("### **ℹ️ Información de la Solicitud**")

        # Reunimos la Información de las Deudas y los Addendums en uno Solo
        deudas_info = solicitud["JSON_Respuesta"] + solicitud["Metadata_Solicitud"].get("Addendums",[])

        # Definimos todas las Deudas Disponibles
        debt_ids = [d['Id_Deuda'] for d in deudas_info if cleanNumber(d['Monto_Propuesto'], default_nan=0) > 0]

        # Creamos una Vista de Pills para definir las Deudas a Usar
        selected_ids = st.pills(
            "**Deudas y Addendums usados**",
            options=debt_ids,
            default=debt_ids,
            help="Seleccione las deudas y addendums que desea incluir en el acuerdo de pago generado.",
            key = "deudas_addendums_solicitud_info_{}".format(solicitud['ID_Solicitud']),
            selection_mode="multi",
            width="stretch",
        )

        if selected_ids is None or not selected_ids:
            st.error("Debe seleccionar al menos una deuda o addendum para generar el acuerdo de pago.")
            st.stop()

        selected_deudas_info = [d for d in deudas_info if (d['Id_Deuda'] in selected_ids)]
        monto_total = sum(cleanNumber(d['Monto_Propuesto'], default_nan=0.0) for d in selected_deudas_info)

        # Creamos 3 Columnas para ayudar con la Organización de la Información
        col1Info, col2Info, col3Info = st.columns([2, 2, 2], vertical_alignment="center", gap="small")

        # 1.1 Referencia, Nombre del Cliente y Documento (Cedula) -> Inhabilitado
        with col1Info:
            st.text_input(
                label="**📄 Referencia**",
                value=solicitud["Referencia"],
                disabled=True,
                key="referencia_solicitud_info_{}".format(solicitud['ID_Solicitud']),
            )

        with col2Info:
            st.text_input(
                label="**👤 Nombre del Cliente**",
                value=solicitud["Metadata_Solicitud"]["Nombre_Cliente"],
                disabled=True,
                key="nombre_cliente_solicitud_info_{}".format(solicitud['ID_Solicitud']),
            )

        with col3Info:
            st.text_input(
                label="**🆔 Documento**",
                value=solicitud["Cedula"],
                disabled=True,
                key="cedula_solicitud_info_{}".format(solicitud['ID_Solicitud']),
            )

        # 1.2 Monto Total de Pago, Metodo de Pago y Fecha Limite de Pago (Desabilitados, ya estan como Inputs)
        with col1Info:
            st.text_input(
                label="**💰 Monto Total de Pago**",
                value="{:,.0f}".format(monto_total),
                disabled=True,
                key="monto_total_solicitud_info_{}".format(solicitud['ID_Solicitud']),
            )
        with col2Info:
            st.text_input(
                label="**💳 Método de Pago**",
                value=solicitud["Metadata_Solicitud"].get("Metodo_Pago", "Desconocido"),
                disabled=True,
                key="metodo_pago_solicitud_info_{}".format(solicitud['ID_Solicitud']),
            )
        with col3Info:
            st.text_input(
                label="**📅 Fecha Límite de Pago**",
                value=solicitud["Fecha_Limite_Pago"].strftime("%Y-%m-%d") if pd.notna(solicitud["Fecha_Limite_Pago"]) else "",
                disabled=True,
                key="fecha_limite_pago_solicitud_info_{}".format(solicitud['ID_Solicitud']),
            )

        # Ahora vamos a presentar por cada deuda seleccionada: Id_Deuda, Numero_Credito y Monto Propuesto
        for d in selected_deudas_info:
            if cleanNumber(d['Monto_Propuesto'], default_nan=0) <= 0:
                continue
            with col1Info:
                st.text_input(
                    label="**Id Deuda**",
                    value=d['Id_Deuda'],
                    disabled=True,
                    key="id_deuda_solicitud_info_{}_{}".format(solicitud['ID_Solicitud'], d['Id_Deuda']),
                )
            with col2Info:
                st.text_input(
                    label="**Número de Crédito**",
                    value=d['Numero_Credito'],
                    disabled=False, # Este si se puede cambiar
                    key="numero_credito_solicitud_info_{}_{}".format(solicitud['ID_Solicitud'], d['Id_Deuda']),
                )

            # Actualizamos la Key de Monto Propuesto dejando el valor por si se actualiza
            key_monto_propuesto = "monto_propuesto_solicitud_info_{}_{}".format(solicitud['ID_Solicitud'], d['Id_Deuda'])
            st.session_state[key_monto_propuesto] = formatNumber(d['Monto_Propuesto'])

            with col3Info:
                st.text_input(
                    label="**Monto Propuesto**",
                    value=formatNumber(d['Monto_Propuesto']),
                    disabled=True,
                    key="monto_propuesto_solicitud_info_{}_{}".format(solicitud['ID_Solicitud'], d['Id_Deuda']),
                )

        # Ahora vamos a crear el Botón para Descargar el Acuerdo de Pago en PDF
        # Primero Definimos la Key
        key_acuerdo = "acuerdo_gen_{ID_Sol}_{Ids_Deudas}".format(
            ID_Sol=solicitud['ID_Solicitud'],
            Ids_Deudas='-'.join(str(d['Id_Deuda']) for d in selected_deudas_info)
        )

        # Ahora Creamos el Botón de Generar el PDF
        generar_pdf = st.button(
            label="Generar Acuerdo de Pago en PDF",
            key=key_acuerdo + '_button',
            type="primary",
            help="Haga clic para generar el acuerdo de pago en formato PDF.",
        )
        if generar_pdf:
            with st.spinner("⚙️ Generando Acuerdo de Pago en PDF..."):
                # Paso 1: Crear la Serie de Datos
                serie_acuerdo = generate_plantilla_serie_acuerdo(solicitud=solicitud, deudas=selected_ids)
                # Paso 2: Obtener los Bytes del Acuerdo
                pdf_bytes = generate_payment_agreement_pdf(agreement=serie_acuerdo, assets_dir="assets", alpha=0.10) # type: ignore
                # Paso 3: Guardar los Bytes en el Session State
                st.session_state[key_acuerdo] = pdf_bytes

    return st.session_state.get(key_acuerdo, bytes())

# Función para Abrir el Dialogo de Respuesta de una Solicitud
@st.dialog("🗒️ Respuesta a Solicitud",dismissible=True,width="large",on_dismiss="rerun")
def dialog_respuesta_solicitud(*, solicitud: pd.Series) -> None:
    # Creamos una Copia de la solicitud que será la respuesta
    solicitud_respuesta = solicitud.copy()

    # A la Solicitud Respuesta le cambiamos la Fecha_Esperada_Pago a "" si es NaN
    if pd.isna(solicitud_respuesta["Fecha_Esperada_Pago"]):
        solicitud_respuesta["Fecha_Esperada_Pago"] = ""

    # Ahora Agregamos la Fecha_Respuesta a hoy en estos momentos
    solicitud_respuesta["Fecha_Respuesta"] = pd.Timestamp.now(tz='America/Bogota').tz_localize(None)

    # Actualizamos el Ejecutivo de la Solicitud Respuesta con el Nombre si existe, de lo contrario el Correo
    solicitud_respuesta["Ejecutivo"] = st.session_state.get('user_name', st.session_state.get('user_email', 'Desconocido'))

    st.markdown("### **ℹ️ Información de la Solicitud**")
    # Paso 1: Escogencia de Aliado, Estado de Solicitud y (Llamada )
    colAliado, colEstado, colLlamada = st.columns([2,2,1], vertical_alignment="center", border=True)

    with colAliado:
        aliado_final = st.selectbox(
            label="**🥸 Aliado - Casa de Cobro**",
            options=list(st.session_state["aliados_dict"].keys()),
            index=list(st.session_state["aliados_dict"].keys()).index(solicitud["Casa_Cobro"]),
            key="aliado_solicitud_respuesta_input_{}".format(solicitud['ID_Solicitud']),
        )

    with colEstado:
        estado_final = st.selectbox(
            label="**📊 Estado de Solicitud**",
            options=[e for e in ESTADOS_POSIBLES_SOLICITUD if e not in ["Sin Tocar","Vencida"]],
            index=None,
            key="estado_solicitud_respuesta_input_{}".format(solicitud['ID_Solicitud']),
        )

    with colLlamada:
        llamada_final = st.toggle(
            label="**📞 ¿Fue Llamada?**",
            value=False,
            key="llamada_solicitud_respuesta_input_{}".format(solicitud['ID_Solicitud']),
        )

    # Verificamos que ambos esten seleccionados para habilitar el botón de enviar respuesta
    if not (aliado_final and estado_final):
        st.info("Selecciona el Aliado Final y el Estado de Solicitud")
        st.stop()

    # Siguiente: Actualizamos la solicitud_respuesta con los valores seleccionados
    solicitud_respuesta["Casa_Cobro"] = aliado_final
    solicitud_respuesta["Estado_Solicitud"] = estado_final
    solicitud_respuesta["Metadata_Solicitud"]["Fue_Llamada"] = llamada_final

    # Siguiente: Verificaciones antes de Seguir con Solicitud
    # Actualizamos Bajo Comité y Titular Ilocalizable
    if estado_final == "Bajo Comité":
        solicitud_respuesta["Metadata_Solicitud"]["Estado_Comite"] = 1
    if estado_final == "Titular Ilocalizable":
        solicitud_respuesta["Metadata_Solicitud"]["Estado_Titular_Ilocalizable"] = 1

    # Siguente: Agregar Fecha_Solicitado si el estado es "Solicitado"
    if estado_final == "Solicitado":
        solicitud_respuesta["Metadata_Solicitud"]["Fecha_Solicitado"] = pd.Timestamp.now(tz='America/Bogota').tz_localize(None).strftime("%Y-%m-%d %H:%M:%S")

    # Ahora: Mostramos Botón de Finalizar que el Estado este en ESTADOS_PREFINALIZAR_SOLICITUD
    if estado_final in ESTADOS_PREFINALIZAR_SOLICITUD:

        # Añadimos la Posibilidad de Comentario
        cm_final = st.text_area(
            label="**Comentarios de la Solicitud**",
            value="",
            key="comentario_solicitud_respuesta_input_{}".format(solicitud['ID_Solicitud']),
            help="Ingrese cualquier comentario adicional sobre la solicitud.",
        )
        # Guardamos el Comentario en el Metadata de la Solicitud Respuesta
        solicitud_respuesta["Metadata_Solicitud"]["Comentario_Ejecutivo"] = cm_final

        st.success("La solicitud está en un estado que permite finalizarla.")
        # Mostramos el Botón para Finalizar la Solicitud
        mostrar_boton_actualizar_solicitudes(solicitud=solicitud_respuesta)
        st.stop()

    # En caso que no (es Exitosa), se requiere poner el Monto por Deuda, Cuotas y Fecha Límite de Pago
    # Paso 1: Escoger-> Fecha Limite de Pago, Monto Total, Checkbox de usar Monto Total y SelectBox para cuotas
    colFechaLimite, colMontoTotal, colUsarMontoTotal, colCuotas = st.columns([2, 2, 1, 1], vertical_alignment="center")

    # Paso 2: Inicializar Valores en el Session_State por Primera Vez
    monto_propuesto_total = sum(cleanNumber(d['Monto_Propuesto']) for d in solicitud["Datos_Solicitud"])
    key_monto_total = 'monto_total_{}_respuesta'.format(solicitud['ID_Solicitud'])
    key_usar_monto_total = 'usar_monto_total_{}'.format(solicitud['ID_Solicitud'])
    key_deudas_dist_monto = 'deudas_dist_monto_{}'.format(solicitud['ID_Solicitud'])
    deudas_posibles = [d['Id_Deuda'] for d in solicitud["Datos_Solicitud"]]

    if not (key_usar_monto_total in st.session_state):
        st.session_state[key_usar_monto_total] = True
    if not (key_monto_total in st.session_state):
        st.session_state[key_monto_total] = formatNumber(monto_propuesto_total)
    if not (key_deudas_dist_monto in st.session_state):
        st.session_state[key_deudas_dist_monto] = deudas_posibles
    for d in solicitud["Datos_Solicitud"]:
        key_monto = 'monto_propuesto_{}_{}'.format(solicitud['ID_Solicitud'], d['Id_Deuda'])
        key_cuotas = 'cuotas_{}_{}'.format(solicitud['ID_Solicitud'], d['Id_Deuda'])
        if not (key_monto in st.session_state):
            st.session_state[key_monto] = formatNumber(d['Monto_Propuesto'])
        if not (key_cuotas in st.session_state):
            st.session_state[key_cuotas] = d['Num_Cuotas']

    monto_propuesto_portafolio = sum(
        cleanNumber(d['Monto_Propuesto']) for d in solicitud["Datos_Solicitud"] if d['Id_Deuda'] in st.session_state[key_deudas_dist_monto]
    )

    # Paso 3: Aplicar Lógica de Recálculo basado en los Session States
    if st.session_state[key_usar_monto_total]:
        # Actualizamos el Session State de Monto Propuesto por Deuda basado en el Monto Total
        monto_total = cleanNumber(st.session_state[key_monto_total], default_nan=0.0)
        # Lo formateamos para que se vea bonito
        st.session_state[key_monto_total] = formatNumber(monto_total)
        # Iteramos por las Deudas
        for d in solicitud["Datos_Solicitud"]:
            key_monto = 'monto_propuesto_{}_{}'.format(solicitud['ID_Solicitud'], d['Id_Deuda'])
            if not (d['Id_Deuda'] in st.session_state[key_deudas_dist_monto]):
                # Actualizamos el Session State dejando el Monto Propuesto como "Sin Oferta"
                st.session_state[key_monto] = "Sin Oferta"
                continue
            # Calculamos el Monto Propuesto por Deuda basado en el Monto Total y el Monto Propuesto Original
            porcentaje_propuesto_original = cleanNumber(d['Monto_Propuesto']) / monto_propuesto_portafolio if monto_propuesto_portafolio > 0 else 0
            monto_propuesto_nuevo = round(monto_total * porcentaje_propuesto_original)
            # Actualizamos el Session State del Monto Propuesto por Deuda
            st.session_state[key_monto] = formatNumber(monto_propuesto_nuevo)
    else:
        # La Actualización del Monto Total se hace basado en la Suma de los Montos Propuestos por Deuda
        monto_total = sum(
            cleanNumber(st.session_state['monto_propuesto_{}_{}'.format(solicitud['ID_Solicitud'], d['Id_Deuda'])], default_nan=0.0) for d in solicitud["Datos_Solicitud"]
            )
        st.session_state[key_monto_total] = formatNumber(monto_total)
        # Actualizamos a cada Deuda el Monto Propuesto basado en el Session State
        for d in solicitud["Datos_Solicitud"]:
            key_monto = 'monto_propuesto_{}_{}'.format(solicitud['ID_Solicitud'], d['Id_Deuda'])
            estado_deuda = st.session_state[key_monto]
            # Actualizamos el Session State del Monto Propuesto por Deuda
            st.session_state[key_monto] = formatNumber(estado_deuda)

    with colFechaLimite:
        fecha_limite_pago = st.date_input(
            label="**Fecha Límite de Pago**",
            value=None,
            key="fecha_limite_pago_{}".format(solicitud['ID_Solicitud']),
            help="Ingrese la fecha límite de pago para la solicitud. Es Decir, fecha en que se vence el descuento.",
        )
        # La Convertimos a Timestamp para poder guardarla en la Solicitud
        if fecha_limite_pago:
            fecha_limite_pago = pd.Timestamp(fecha_limite_pago)

    with colMontoTotal:
        monto_total = st.text_input(
            label="**Monto de Portafolio**",
            key=key_monto_total,
            help="Ingrese el monto total propuesto para la solicitud. Este monto se distribuirá proporcionalmente entre las deudas.",
            disabled= not st.session_state[key_usar_monto_total],
        )

    with colUsarMontoTotal:
        usar_monto_total = st.toggle(
            label="**Usar el Monto de Portafolio**",
            key=key_usar_monto_total,
            help="Seleccione esta opción para distribuir el monto total propuesto entre las deudas.",
        )

    with colCuotas:
        cuotas_input = st.selectbox(
            label="**Número de Cuotas**",
            options=["No", "Por Deuda", "Para Todas las Deudas"],
            index=0,
            key="cuotas_{}".format(solicitud['ID_Solicitud']),
            help="Seleccione si desea establecer el número de cuotas para todas las deudas o por deuda individual.",
        )

    # Paso Siguiente: Mostrar el Pills de las deudas a escoger del Portafolio (Solo si se usa el monto total)
    if st.session_state[key_usar_monto_total]:
        st.pills(
            "**💼 Deudas a Incluir en el Portafolio**",
            options=deudas_posibles,
            default=deudas_posibles,
            help="Seleccione las deudas que desea incluir en el portafolio. Solo se distribuirá el monto total entre estas deudas.",
            key=key_deudas_dist_monto,
            selection_mode="multi",
            width="stretch",
        )

    # Paso Siguiente: Mostrar los Inputs por Deuda
    # Se va a Mostrar: Id_Deuda, Banco, Numero_Credito, Monto Propuesto y Cuotas (Si Hay)

    num_coutas_global = 1
    if cuotas_input == "Para Todas las Deudas":
        num_coutas_global = st.number_input(
            label="**Número de Cuotas para Todas las Deudas**",
            min_value=1,
            max_value=60,
            step=1,
            key="num_cuotas_global_{}".format(solicitud['ID_Solicitud']),
            help="Ingrese el número de cuotas para todas las deudas.",
            width="stretch",
        )

    # Siguiente: Expander para mostrar los Inputs por Deuda
    with st.expander("**💸 Respuesta por Deuda**", expanded=False):
        st.markdown("### **Datos por Deuda 🏦**")
        if cuotas_input == "Por Deuda":
            colIdDeuda, colNumCredito, colMontoActual, colSolicitado, colMontoPropuesto, colCuotasDeuda = st.columns(6, border=True)
        else:
            colIdDeuda, colNumCredito, colMontoActual, colSolicitado, colMontoPropuesto = st.columns(5, border=True)

        with colIdDeuda:
            st.markdown("**ID de Deuda**")
        with colNumCredito:
            st.markdown("**Número de Crédito**")
        with colMontoActual:
            st.markdown("**Monto Actual**")
        with colSolicitado:
            st.markdown("**$Solicitado**")
        with colMontoPropuesto:
            st.markdown("**Monto Propuesto**")
        if cuotas_input == "Por Deuda":
            with colCuotasDeuda: # type: ignore
                st.markdown("**Número de Cuotas**")

        # Iteramos por las Deudas de la Solicitud y Mostramos los Inputs correspondientes
        for d in solicitud["Datos_Solicitud"]:
            with colIdDeuda:
                st.text_input(
                    label="ID Deuda",
                    value=d['Id_Deuda'],
                    disabled=True,
                    key="id_deuda_{}_{}_response".format(solicitud['ID_Solicitud'], d['Id_Deuda']),
                    label_visibility="collapsed",
                )
            with colNumCredito:
                st.text_input(
                    label="Número de Crédito",
                    value=d['Numero_Credito'],
                    disabled=True,
                    key="numero_credito_{}_{}_response".format(solicitud['ID_Solicitud'], d['Id_Deuda']),
                    label_visibility="collapsed",
                )
            with colMontoActual:
                st.text_input(
                    label="Monto Actual",
                    value=formatNumber(d['Monto_Actual']),
                    disabled=True,
                    key="monto_actual_{}_{}_response".format(solicitud['ID_Solicitud'], d['Id_Deuda']),
                    label_visibility="collapsed",
                )
            with colSolicitado:
                st.text_input(
                    label="$Solicitado",
                    value=formatNumber(d['Monto_Propuesto']),
                    disabled=True,
                    key="monto_solicitado_{}_{}_response".format(solicitud['ID_Solicitud'], d['Id_Deuda']),
                    label_visibility="collapsed",
                )
            with colMontoPropuesto:
                key_monto = 'monto_propuesto_{}_{}'.format(solicitud['ID_Solicitud'], d['Id_Deuda'])
                st.text_input(
                    label="Monto Propuesto",
                    key=key_monto,
                    help="Ingrese el monto propuesto para la deuda {}.".format(d['Id_Deuda']),
                    label_visibility="collapsed",
                    disabled = usar_monto_total
                )
            if cuotas_input == "Por Deuda":
                with colCuotasDeuda: # type: ignore
                    key_cuotas = 'cuotas_{}_{}'.format(solicitud['ID_Solicitud'], d['Id_Deuda'])
                    st.number_input(
                        label="Número de Cuotas",
                        value=1,
                        min_value=1,
                        max_value=60,
                        step=1,
                        key=key_cuotas,
                        help="Ingrese el número de cuotas para la deuda {}.".format(d['Id_Deuda']),
                        label_visibility="collapsed",
                    )

        # Siguiente: Mostramos Posibilidad de Agregar Addendums
        with st.expander("**📝 Agregar Addendums a la Solicitud**", expanded=False):

            # Inicializamos la Cantidad de Addendums con 0 en el Session State si no existe
            key_addendums_count = 'addendums_count_{}'.format(solicitud['ID_Solicitud'])
            if not (key_addendums_count in st.session_state):
                st.session_state[key_addendums_count] = 0

            # Creamos las mismas columnas que antes sin Monto_Solicitado (Quitando Id Deuda y añadiendo Banco y Monto Actual)
            if cuotas_input == "Por Deuda":
                colBancoAdd, colNumCreditoAdd, colMontoActualAdd, colMontoPropuestoAdd, colCuotasDeudaAdd = st.columns(5, vertical_alignment="center")
            else:
                colBancoAdd, colNumCreditoAdd, colMontoActualAdd, colMontoPropuestoAdd = st.columns(4, vertical_alignment="center")

            with colBancoAdd:
                st.markdown("**Banco**")
            with colNumCreditoAdd:
                st.markdown("**Número de Crédito**")
            with colMontoActualAdd:
                st.markdown("**Monto Actual**")
            with colMontoPropuestoAdd:
                st.markdown("**Monto Propuesto**")
            if cuotas_input == "Por Deuda":
                with colCuotasDeudaAdd: # type: ignore
                    st.markdown("**Número de Cuotas**")

            # Ahora Iteramos por la Cantidad de Addendums y Mostramos los Inputs correspondientes
            for i in range(1,st.session_state[key_addendums_count]+1):

                # Inicializamos los Session States de los Addendums si no existen
                key_banco_add = 'addendums_banco_{}_{}'.format(solicitud['ID_Solicitud'], i)
                key_numero_credito_add = 'addendums_numero_credito_{}_{}'.format(solicitud['ID_Solicitud'], i)
                key_monto_actual_add = 'addendums_monto_actual_{}_{}'.format(solicitud['ID_Solicitud'], i)
                key_monto_propuesto_add = 'addendums_monto_propuesto_{}_{}'.format(solicitud['ID_Solicitud'], i)
                key_cuotas_add = 'addendums_cuotas_{}_{}'.format(solicitud['ID_Solicitud'], i)
                if not (key_banco_add in st.session_state):
                    st.session_state[key_banco_add] = ""
                if not (key_numero_credito_add in st.session_state):
                    st.session_state[key_numero_credito_add] = ""
                if not (key_monto_actual_add in st.session_state):
                    st.session_state[key_monto_actual_add] = ""
                if not (key_monto_propuesto_add in st.session_state):
                    st.session_state[key_monto_propuesto_add] = ""
                if not (key_cuotas_add in st.session_state):
                    st.session_state[key_cuotas_add] = 1

                with colBancoAdd:
                    st.selectbox(
                        label="",
                        options=BANCOS_UNICOS,
                        key='addendums_banco_{}_{}'.format(solicitud['ID_Solicitud'], i),
                        help="Ingrese el banco para el addendum {}.".format(i+1),
                        label_visibility="collapsed",
                        accept_new_options = True, # Permitimos agregar bancos por si no están
                    )
                with colNumCreditoAdd:
                    st.text_input(
                        "",
                        key='addendums_numero_credito_{}_{}'.format(solicitud['ID_Solicitud'], i),
                        help="Ingrese el número de crédito para el addendum {}.".format(i+1),
                        label_visibility="collapsed",
                    )
                with colMontoActualAdd:
                    st.text_input(
                        "",
                        key='addendums_monto_actual_{}_{}'.format(solicitud['ID_Solicitud'], i),
                        help="Ingrese el monto actual para el addendum {}.".format(i+1),
                        label_visibility="collapsed",
                    )
                with colMontoPropuestoAdd:
                    st.text_input(
                        "",
                        key='addendums_monto_propuesto_{}_{}'.format(solicitud['ID_Solicitud'], i),
                        help="Ingrese el monto propuesto para el addendum {}.".format(i+1),
                        label_visibility="collapsed",
                    )
                if cuotas_input == "Por Deuda":
                    with colCuotasDeudaAdd: # type: ignore
                        st.number_input(
                            label="Número de Cuotas",
                            key='addendums_cuotas_{}_{}'.format(solicitud['ID_Solicitud'], i),
                            help="Ingrese el número de cuotas para el addendum {}.".format(i+1),
                            label_visibility="collapsed",
                            value=1,
                            min_value=1,
                            max_value=60,
                            step=1,
                        )

            # Añadimos dos Botones: Uno para Agregar Addendum y Otro para Quitar Addendum
            colAddendumQuitar, colAddendumAgregar  = st.columns(2, vertical_alignment="center", gap="large")

            with colAddendumQuitar:
                if st.button(
                    label="Quitar Addendum",
                    key="quitar_addendum_{}".format(solicitud['ID_Solicitud']),
                    help="Haga clic para quitar un addendum de la solicitud.",
                    type="secondary",
                ):
                    if st.session_state[key_addendums_count] > 0:
                        st.session_state[key_addendums_count] -= 1
                        st.rerun(scope="fragment")
                    else:
                        st.toast("No hay addendums para quitar.", icon="⚠️")

            with colAddendumAgregar:
                if st.button(
                    label="Agregar Addendum",
                    key="agregar_addendum_{}".format(solicitud['ID_Solicitud']),
                    help="Haga clic para agregar un addendum a la solicitud.",
                    type="primary",
                ):
                    st.session_state[key_addendums_count] += 1
                    st.rerun(scope="fragment")

    # Siguiente: Generamos el JSON_Respuesta con: Monto Propuesto por Deuda, Cuotas por Deuda
    json_respuesta = []
    for d in solicitud["Datos_Solicitud"]:
        key_monto = 'monto_propuesto_{}_{}'.format(solicitud['ID_Solicitud'], d['Id_Deuda'])
        key_cuotas = 'cuotas_{}_{}'.format(solicitud['ID_Solicitud'], d['Id_Deuda'])
        monto_propuesto = cleanNumber(st.session_state[key_monto], default_nan=0.0)
        if cuotas_input == "Por Deuda":
            num_cuotas = int(st.session_state[key_cuotas])
        else:
            num_cuotas = num_coutas_global
        json_respuesta.append({
            "Id_Deuda": d['Id_Deuda'],
            "Banco": d['Banco'],
            "Numero_Credito": d['Numero_Credito'],
            "Monto_Propuesto": monto_propuesto,
            "Num_Cuotas": num_cuotas,
        })

    # Agreagamos el JSON_Respuesta a la solicitud_respuesta
    solicitud_respuesta["JSON_Respuesta"] = json_respuesta

    # Siguiente: Agregamos los Addendums a la solicitud_respuesta si existen
    addendums = []
    for i in range(1, st.session_state[key_addendums_count]+1):

        addendum_banco = st.session_state['addendums_banco_{}_{}'.format(solicitud['ID_Solicitud'], i)]
        addendum_numero_credito = st.session_state['addendums_numero_credito_{}_{}'.format(solicitud['ID_Solicitud'], i)]
        addendum_monto_actual = cleanNumber(st.session_state['addendums_monto_actual_{}_{}'.format(solicitud['ID_Solicitud'], i)], default_nan=0.0)
        addendum_monto_propuesto = cleanNumber(st.session_state['addendums_monto_propuesto_{}_{}'.format(solicitud['ID_Solicitud'], i)], default_nan=0.0)
        if cuotas_input == "Por Deuda":
            addendum_num_cuotas = int(st.session_state['addendums_cuotas_{}_{}'.format(solicitud['ID_Solicitud'], i)])
        else:
            addendum_num_cuotas = num_coutas_global

        # Si no hay banco o Numero de Credito no se agrega
        if not (addendum_banco or addendum_numero_credito):
            continue

        addendums.append({
            "Id_Deuda": "{}_ADD_{}".format(solicitud['Cedula'],str(i)),
            "Banco": addendum_banco,
            "Numero_Credito": addendum_numero_credito,
            "Monto_Actual": addendum_monto_actual,
            "Monto_Propuesto": addendum_monto_propuesto,
            "Num_Cuotas": addendum_num_cuotas,
        })

    # Añadimos los Addendums a la solicitud_respuesta
    solicitud_respuesta["Metadata_Solicitud"]["Addendums"] = addendums

    # Añadimos Fecha_Limite_Pago a la solicitud_respuesta si existe, de lo contrario mostrar alerta
    if fecha_limite_pago:
        solicitud_respuesta["Fecha_Limite_Pago"] = fecha_limite_pago
    else:
        st.warning("Debe ingresar una Fecha Límite de Pago para poder finalizar la solicitud.")
        st.stop()

    if fecha_limite_pago < pd.Timestamp.now(tz='America/Bogota').tz_localize(None).normalize():
        st.warning("La Fecha Límite de Pago no puede ser menor a la fecha actual.", icon="⚠️"   )
        st.stop()

    st.divider()

    # Siguiente: Añadir el Input de Pago Total Obligatorio (Checkbox), solo si existe más de una deuda
    if len(json_respuesta) > 1:
        colToggle, colInfo = st.columns([1, 4])
        with colToggle:
            pago_total_obligatorio = st.toggle(
                label="**Pago Total Obligatorio**",
                value=False,
                key="pago_total_obligatorio_{}".format(solicitud['ID_Solicitud']),
                help="Seleccione esta opción si el pago total es obligatorio para la solicitud.",
            )
            # Guardamos el Pago Total Obligatorio en la solicitud_respuesta
            solicitud_respuesta['Metadata_Solicitud']["Pago_Total_Obligatorio"] = pago_total_obligatorio
        with colInfo:
            st.info("El Pago Obligatorio significa que se debe aplicar el pago para todas la deudas")

    # Añadimos la Posibilidad de Comentario
    cm_final = st.text_area(
        label="**Comentarios de la Solicitud**",
        value="",
        key="comentario_solicitud_respuesta_input_{}".format(solicitud['ID_Solicitud']),
        help="Ingrese cualquier comentario adicional sobre la solicitud.",
    )
    # Guardamos el Comentario en el Metadata de la Solicitud Respuesta
    solicitud_respuesta["Metadata_Solicitud"]["Comentario_Ejecutivo"] = cm_final

    # Siguiente: Si es Validación, mostrar el Botón de Finalizar Solicitud
    if solicitud["Tipo_Solicitud"] == "Validación":
        mostrar_boton_actualizar_solicitudes(solicitud=solicitud_respuesta)
        st.stop()

    # Especificaciones de Acuerdo de Pago u Oferta de Pago
    with st.expander("**💸 Especificaciones de Acuerdo de Pago u Oferta de Pago**", expanded=True):

        # Creamos 2 Columnas: Una para Metodo de Pago y la Otra para Formato de Pago
        colMetodoPago, colFormatoPago = st.columns(2, vertical_alignment="top")

        # Como es Acuerdo de Pago u Oferta de Pago, mostramos un Input de Metodo de Pago (Efectivo-Cheque, PSE, Transferencia)
        with colMetodoPago:
            metodo_pago = st.radio(
                label="**Método de Pago**",
                options=["Efectivo-Cheque", "PSE", "Transferencia"],
                index=0,
                key="metodo_pago_{}".format(solicitud['ID_Solicitud']),
                help="Seleccione el método de pago para la solicitud.",
            )

        # Guardamos el Método de Pago en la metadata de la solicitud_respuesta
        solicitud_respuesta["Metadata_Solicitud"]["Metodo_Pago"] = metodo_pago

        with colFormatoPago:
            formato_pago = st.radio(
                label="**Formato de Acuerdo de Pago**",
                options=["Subir Archivo", "Generar PDF"],
                index=0,
                key="formato_pago_{}".format(solicitud['ID_Solicitud']),
                help="Seleccione el formato de pago para la solicitud.",
            )

        # Siguiente: Definir el formato_pago
        if formato_pago == "Subir Archivo":

            # Reunimos la Información de las Deudas y los Addendums en uno Solo
            deudas_info = solicitud_respuesta["JSON_Respuesta"] + solicitud_respuesta["Metadata_Solicitud"].get("Addendums",[])
    
            # Definimos todas las Deudas Disponibles
            debt_ids = [d['Id_Deuda'] for d in deudas_info]
    
            # Creamos una Vista de Pills para definir las Deudas a Usar
            selected_ids = st.pills(
                "**Deudas y Addendums usados**",
                options=debt_ids,
                default=debt_ids,
                help="Seleccione las deudas y addendums que desea incluir en el acuerdo de pago generado.",
                key = "deudas_addendums_solicitud_info_{}".format(solicitud['ID_Solicitud']),
                selection_mode="multi",
                width="stretch",
            )

            bytes_acuerdo = st.file_uploader(
                label="**Subir Acuerdo de Pago**",
                type=["pdf"],
                key="subir_acuerdo_pago_{}".format(solicitud['ID_Solicitud']),
                help="Suba el archivo PDF del acuerdo de pago.",
            )
            if bytes_acuerdo is None:
                st.warning("Debe subir un archivo PDF del acuerdo de pago para poder finalizar la solicitud.")
                st.stop()
            # Obtenemos los bytes del archivo subido
            bytes_acuerdo = bytes_acuerdo.getvalue()
            # Generamos la Metadata de la Solicitud
            metadata_to_add_acuerdo = generate_plantilla_serie_acuerdo(solicitud=solicitud_respuesta, deudas=selected_ids)
            # Guardamos la Metadata en el PDF
            bytes_acuerdo = add_metadata_to_uploaded_pdf(pdf_bytes=bytes_acuerdo, metadata=metadata_to_add_acuerdo.to_dict())

            
        elif formato_pago == "Generar PDF":
            bytes_acuerdo = mostrar_especificaciones_acuerdo_generado(solicitud=solicitud_respuesta)
            # Si no hay bytes_acuerdo, mostramos un error y detenemos la ejecución
            if (bytes_acuerdo is None) or (len(bytes_acuerdo) == 0):
                st.warning("Debes oprimir el Botón de Generar PDF para poder generar el Acuerdo de Pago")
                st.stop()

        # Creamos un popover para mostrar el PDF generado o subido
        with st.expander("**📄 Vista Previa del Acuerdo de Pago**", expanded=False):
            if bytes_acuerdo is not None and len(bytes_acuerdo) > 0:
                st.markdown("**Vista Previa del Acuerdo de Pago:**")
                st.pdf(bytes_acuerdo)
            else:
                st.warning("No hay un acuerdo de pago disponible para mostrar. Hay que subir o generar el acuerdo de pago en PDF.", icon="⚠️")
                st.stop()

    # Verificamos que exista el metodo de Pago
    if not metodo_pago:
        st.warning("Debe seleccionar un método de pago para poder finalizar la solicitud.", icon="⚠️")
        st.stop()

    # Siguiente: Mostramos el Botón de Finalizar Solicitud
    mostrar_boton_actualizar_solicitudes(solicitud=solicitud_respuesta, pdf_bytes=bytes_acuerdo)

# Diálogo para subir automáticamente una solicitud de acuerdo de pago después de una validación
@st.dialog("🗒️ Subir Solicitud de Acuerdo de Pago", dismissible=True, width="large", on_dismiss="rerun")
def dialog_subir_acuerdo_pago(*, solicitud: pd.Series) -> None:

    st.markdown("### **ℹ️ Información de la Solicitud de Acuerdo de Pago**")
    st.divider()

    # Paso 1: Mostrar la Escogencia de Deudas de la Respuesta de la Solicitud
    deudas_info = solicitud["JSON_Respuesta"] + solicitud["Metadata_Solicitud"].get("Addendums",[])

    if not deudas_info:
        st.warning("No hay deudas ni addendums disponibles para la solicitud. No se puede subir un acuerdo de pago.", icon="⚠️")
        st.stop()

    # Creamos una Visualización Tipo Pills para seleccionar las Deudas y Addendums a Usar
    debt_ids = [d['Id_Deuda'] for d in deudas_info if cleanNumber(d['Monto_Propuesto']) > 0]
    selected_ids = st.pills(
        "**Deudas y Addendums usados**",
        options=debt_ids,
        default=debt_ids,
        help="Seleccione las deudas y addendums que desea incluir en el acuerdo de pago generado.",
        key = "deudas_addendums_solicitud_info_{}".format(solicitud['ID_Solicitud']),
        selection_mode="multi",
        width="stretch",
        disabled = solicitud['Metadata_Solicitud'].get("Pago_Total_Obligatorio", False)
    )

    if solicitud['Metadata_Solicitud'].get("Pago_Total_Obligatorio", False):
        st.warning('El Pago tiene que ser por todas las deudas y addendums.', icon="⚠️")

    if not selected_ids:
        st.warning("Debe seleccionar al menos una deuda o addendum para poder subir el acuerdo de pago.", icon="⚠️")
        st.stop()

    with st.expander("**💸 Información de las Deudas Seleccionadas**", expanded=True):

        # Creamos 4 o 5 Columnas: Id_Deuda, Banco, Numero_Credito, Monto Propuesto y Cuotas (Si Hay)
        hay_cuotas = any(d['Num_Cuotas'] > 1 for d in deudas_info if d['Id_Deuda'] in selected_ids)
        if hay_cuotas:
            colIdDeuda, colBanco, colNumCredito, colMontoPropuesto, colCuotas = st.columns([3,3,3,6,3], vertical_alignment="top")
        else:
            colIdDeuda, colBanco, colNumCredito, colMontoPropuesto = st.columns([3,3,3,6], vertical_alignment="top")

        with colIdDeuda:
            st.markdown("**ID de Deuda:**")
        with colBanco:
            st.markdown("**Banco:**")
        with colNumCredito:
            st.markdown("**Número Crédito:**")
        with colMontoPropuesto:
            st.markdown("**Monto Propuesto:**")
        if hay_cuotas:
            with colCuotas: # type: ignore
                st.markdown("**Cuotas:**")
        for d in deudas_info:
            if not (d['Id_Deuda'] in selected_ids):
                continue
            with colIdDeuda:
                st.code(d['Id_Deuda'], language="text")
            with colBanco:
                st.code(d['Banco'], language="text")
            with colNumCredito:
                st.code(d['Numero_Credito'], language="text")
            with colMontoPropuesto:
                st.code(formatNumber(d['Monto_Propuesto']), language="text")
            if hay_cuotas:
                with colCuotas: # type: ignore
                    st.code(d['Num_Cuotas'], language="text")

    st.divider()

    # Paso 2: Mostrar los Inputs Específicos de la Solicitud de Acuerdo de Pago
    # Creamos 2 Columnas: Fecha_Esperada_Pago y Tipo de Pago
    colFechaEsperada, colTipoPago = st.columns(2, vertical_alignment="center", gap="large")
    with colFechaEsperada:
        fecha_esperada_pago = st.date_input(
            label="**Fecha Esperada de Pago**",
            value=None,
            key="fecha_esperada_pago_{}".format(solicitud['ID_Solicitud']),
            help="Ingrese la fecha esperada de pago para la solicitud.",
        )
        # La Convertimos a Timestamp para poder guardarla en la Solicitud
        if fecha_esperada_pago:
            fecha_esperada_pago = pd.Timestamp(fecha_esperada_pago)

    with colTipoPago:
        if hay_cuotas:
            posibles_pagos = ['Estructuraado','Refi']
        else:
            posibles_pagos = ['Tradicional','Crédito']
        tipo_pago = st.selectbox(
            label="**Tipo de Pago**",
            options=posibles_pagos,
            index=None,
            key="tipo_pago_{}".format(solicitud['ID_Solicitud']),
            help="Ingrese el tipo de pago para la solicitud.",
        )

    if not fecha_esperada_pago:
        st.warning("Debe ingresar una Fecha Esperada de Pago para poder subir la solicitud de acuerdo de pago.", icon="⚠️")
        st.stop()
    if not tipo_pago:
        st.warning("Debe ingresar un Tipo de Pago para poder subir la solicitud de acuerdo de pago.", icon="⚠️")
        st.stop()

    # Siguiente: Mostramos Input para Comentario dejando por defecto el Comentario actual
    cm_final = st.text_area(
        label="**Comentarios de la Solicitud**",
        value=solicitud["Metadata_Solicitud"].get("Comentario_Negociador", ""),
        key="comentario_solicitud_respuesta_input_{}".format(solicitud['ID_Solicitud']),
        help="Ingrese cualquier comentario adicional sobre la solicitud.",
    )

    # Ahora Creamos el Diccionario
    solicitud_respuesta = crear_plantilla_solicitud_acuerdo_pago(
        solicitud=solicitud,
        selected_ids=selected_ids,
        fecha_pago=fecha_esperada_pago,
        tipo_pago=tipo_pago,
        comentario=cm_final or "",
    )

    # Verificamos que esta solicitud no exista ya
    ya_existe_acuerdo = check_if_acuerdo_pago_uploaded(solicitud = solicitud_respuesta)

    # Vamos a Mostrar 2 Botones: Uno para salir del Dialog y otro para subir la Soliciutd
    colSalir, colSubir = st.columns(2, vertical_alignment="center", gap="large")
    with colSalir:
        st.button(
            label="**Salir**",
            key="salir_subir_acuerdo_pago_{}".format(solicitud['ID_Solicitud']),
            help="Haga clic para salir del diálogo de subir solicitud de acuerdo de pago.",
            on_click=st.rerun,
            type="secondary",
            width="stretch",
        )

    with colSubir:
        if st.button(
            label="**Subir Solicitud de Acuerdo de Pago**",
            key="subir_solicitud_acuerdo_pago_{}".format(solicitud['ID_Solicitud']),
            help="Haga clic para subir la solicitud de acuerdo de pago.",
            type="primary",
            width="stretch",
            disabled=ya_existe_acuerdo,
        ):
            # Subimos la Solicitud de Acuerdo de Pago
            with st.spinner("Subiendo Solicitud de Acuerdo de Pago..."):
                success, new_id = upload_form_response_to_google_sheets(response_info=solicitud_respuesta)
            if success:
                st.toast(f"Solicitud de Acuerdo de Pago subida exitosamente. (ID: {new_id})", icon="✅")
                sleep(2)
                st.rerun()
            else:
                st.toast("Intenta de Nuevo subir la Solicitud",icon="❌")

    if ya_existe_acuerdo:
        st.warning("Ya existe una solicitud de acuerdo de pago para esta solicitud. No se puede subir otra.", icon="⚠️")

# Diálogo para ContraOfertar una Solicitud de Validación (Sin Implementar)
@st.dialog("🫡 ContraOfertar Solicitud de Validación", dismissible=True, width="large", on_dismiss="rerun")
def ajustar_contraoferta_solicitud(*, solicitud: pd.Series) -> None:
    st.markdown("### **ℹ️ Información de la ContraOferta de Solicitud de Validación (`{}`)**".format(
        solicitud['ID_Solicitud']
    ))
    st.divider()

    st.success("Para seguir, ingresa los montos que deseas proponer para cada deuda")

    # Paso 1: Inicializar las Llaves de Montos Propuestos y Cuotas por Deuda en el Session State
    key_monto_total_co = 'monto_total_contraoferta_{}'.format(solicitud['ID_Solicitud'])
    key_deudas_dist_monto_co = 'deudas_dist_monto_contraoferta_{}'.format(solicitud['ID_Solicitud'])
    key_usar_monto_total_co = 'usar_monto_total_contraoferta_{}'.format(solicitud['ID_Solicitud'])
    deudas_posibles = [d['Id_Deuda'] for d in solicitud["JSON_Respuesta"] if cleanNumber(d['Monto_Propuesto']) > 0]
    if not (key_monto_total_co in st.session_state):
        st.session_state[key_monto_total_co] = formatNumber(sum(
            cleanNumber(d['Monto_Propuesto']) for d in solicitud["JSON_Respuesta"]
        ))
    if not (key_deudas_dist_monto_co in st.session_state):
        st.session_state[key_deudas_dist_monto_co] = deudas_posibles
    if not (key_usar_monto_total_co in st.session_state):
        st.session_state[key_usar_monto_total_co] = True
    for d in solicitud["JSON_Respuesta"]:
        key_monto = 'monto_propuesto_co_{}_{}'.format(solicitud['ID_Solicitud'], d['Id_Deuda'])
        key_cuotas = 'cuotas_co_{}_{}'.format(solicitud['ID_Solicitud'], d['Id_Deuda'])
        if not (key_monto in st.session_state):
            st.session_state[key_monto] = formatNumber(d['Monto_Propuesto'])
        if not (key_cuotas in st.session_state):
            st.session_state[key_cuotas] = d.get('Num_Cuotas', 1)

    # Definimos las Deudas Posibles para la ContraOferta
    deudas_posibles = st.session_state[key_deudas_dist_monto_co]
    monto_prop_posible = sum([cleanNumber(d['Monto_Propuesto']) for d in solicitud["JSON_Respuesta"] if d['Id_Deuda'] in deudas_posibles])

    # Paso 2: Aplicar los Recálculos
    if st.session_state[key_usar_monto_total_co]:
        # 2.1: Limpiar el Monto Total
        valor_total_co = cleanNumber(st.session_state[key_monto_total_co])
        st.session_state[key_monto_total_co] = formatNumber(valor_total_co)
        # 2.2: Recalcular los Montos Propuestos por Deuda
        for d in solicitud["JSON_Respuesta"]:
            if not (d['Id_Deuda'] in deudas_posibles):
                continue

            # Paso 1: Calcular el % de Deuda con respecto al Total de Deudas Posibles
            monto_deuda = cleanNumber(d['Monto_Propuesto'])
            porcentaje = (monto_deuda / monto_prop_posible) if monto_prop_posible > 0 else 0
            # Paso 2: Recalcular el Monto Propuesto
            key_monto = 'monto_propuesto_co_{}_{}'.format(solicitud['ID_Solicitud'], d['Id_Deuda'])
            st.session_state[key_monto] = formatNumber(valor_total_co * porcentaje)
    else:
        # 2.1: Recalcular el Monto Total
        valor_total_co = sum([cleanNumber(st.session_state['monto_propuesto_co_{}_{}'.format(solicitud['ID_Solicitud'], d['Id_Deuda'])]) for d in solicitud["JSON_Respuesta"] if d['Id_Deuda'] in deudas_posibles])
        st.session_state[key_monto_total_co] = formatNumber(valor_total_co)
        # 2.2 Limpiar los Montos Propuestos por Deuda que esten dentro de las Deudas Posibles
        for d in solicitud["JSON_Respuesta"]:
            if not (d['Id_Deuda'] in deudas_posibles):
                continue
            key_monto = 'monto_propuesto_co_{}_{}'.format(solicitud['ID_Solicitud'], d['Id_Deuda'])
            st.session_state[key_monto] = formatNumber(st.session_state[key_monto])

    # Paso 3: Crear las Columnas de: Monto Total, usar Monto Total y Cuotas
    colMontoTotal, colUsarMontoTotal, colCuotas = st.columns([3, 1,3], vertical_alignment="center", gap="large")
    with colMontoTotal:
        st.text_input(
            label="**Monto Total de la ContraOferta**",
            value=st.session_state[key_monto_total_co],
            key=key_monto_total_co,
            help="Ingrese el monto total de la contraoferta.",
            label_visibility="collapsed",
        )
    with colUsarMontoTotal:
        st.toggle(
            label="**Usar Monto Total**",
            value=True,
            key=f"usar_monto_total_co_{solicitud['ID_Solicitud']}",
            help="Marque esta opción para usar el monto total de la contraoferta.",
        )

    with colCuotas:
        tipo_cuotas = st.radio(
            label="**Distribución de Cuotas**",
            options=["No", "Por Deuda", "Para Todas las Deudas"],
            index=0,
            key="tipo_cuotas_co_{}".format(solicitud['ID_Solicitud']),
            help="Seleccione cómo desea distribuir las cuotas para la contraoferta.",
        )

    # Paso 4: Creamos la visualización pills para mostrar las deudas posibles
    selected_deudas = st.pills(
        "**Deudas Posibles para la ContraOferta**",
        options=deudas_posibles,
        default=deudas_posibles,
        help="Seleccione las deudas que desea incluir en la contraoferta.",
        key = key_deudas_dist_monto_co,
        selection_mode="multi",
        width="stretch",
        disabled = solicitud['Metadata_Solicitud'].get("Pago_Total_Obligatorio", False)
    )

    if not selected_deudas:
        st.warning("Debe seleccionar al menos una deuda para poder realizar la contraoferta.", icon="⚠️")
        st.stop()

    # Paso 5: Mostramos los Inputs de Monto Propuesto y Cuotas por Deuda
    with st.expander("**💸 Montos Propuestos y Cuotas por Deuda**", expanded=True):
        # Creamos 4 o 5 Columnas: Id_Deuda, Numero_Credito, Monto Actual, Monto Respuesta y Monto Contraoferta (y Cuotas si hay)
        if tipo_cuotas == "Por Deuda":
            colIdDeuda, colNumCredito, colMontoActual, colMontoRespuesta, colMontoContraOferta, colCuotas = st.columns([3,3,3,3,5,5], vertical_alignment="top")
        else:
            colIdDeuda, colNumCredito, colMontoActual, colMontoRespuesta, colMontoContraOferta = st.columns([3,3,3,3,5], vertical_alignment="top")

        num_cuotas_global = 1
        if tipo_cuotas == "Para Todas las Deudas":
            num_cuotas_global = st.number_input(
                label="**Número de Cuotas Global**",
                value=1,
                key="num_cuotas_global_co_{}".format(solicitud['ID_Solicitud']),
                help="Ingrese el número de cuotas global para la contraoferta.",
                min_value=1,
                max_value=60,
                step=1,
            )

        with colIdDeuda:
            st.markdown("**ID Deuda:**")
        with colNumCredito:
            st.markdown("**Número Crédito:**")
        with colMontoActual:
            st.markdown("**Monto Actual:**")
        with colMontoRespuesta:
            st.markdown("**Monto Respuesta:**")
        with colMontoContraOferta:
            st.markdown("**Monto ContraOferta:**")
        if tipo_cuotas == "Por Deuda":
            with colCuotas: # type: ignore
                st.markdown("**Cuotas:**")

        for d in solicitud["JSON_Respuesta"]:
            if not (d['Id_Deuda'] in selected_deudas):
                continue

            with colIdDeuda:
                st.text_input(
                    label = "",
                    value = d['Id_Deuda'],
                    disabled=True,
                    key="id_deuda_co_{}_{}".format(solicitud['ID_Solicitud'], d['Id_Deuda']),
                    label_visibility="collapsed",
                )
            with colNumCredito:
                st.text_input(
                    label = "",
                    value = d['Numero_Credito'],
                    disabled=True,
                    key="numero_credito_co_{}_{}".format(solicitud['ID_Solicitud'], d['Id_Deuda']),
                    label_visibility="collapsed",
                )
            with colMontoActual:
                monto_actual = next((cleanNumber(d['Monto_Actual']) for d in solicitud["Datos_Solicitud"] if d['Id_Deuda'] == d['Id_Deuda']), 0.0)
                st.text_input(
                    label = "",
                    value = formatNumber(monto_actual),
                    disabled=True,
                    key="monto_actual_co_{}_{}".format(solicitud['ID_Solicitud'], d['Id_Deuda']),
                    label_visibility="collapsed",
                )
            with colMontoRespuesta:
                st.text_input(
                    label = "",
                    value = formatNumber(d['Monto_Propuesto']),
                    disabled=True,
                    key="monto_respuesta_co_{}_{}".format(solicitud['ID_Solicitud'], d['Id_Deuda']),
                    label_visibility="collapsed",
                )
            with colMontoContraOferta:
                st.text_input(
                    label = "",
                    value = st.session_state['monto_propuesto_co_{}_{}'.format(solicitud['ID_Solicitud'], d['Id_Deuda'])],
                    key='monto_propuesto_co_{}_{}'.format(solicitud['ID_Solicitud'], d['Id_Deuda']),
                    help="Ingrese el monto propuesto para la deuda {}.".format(d['Id_Deuda']),
                    label_visibility="collapsed",
                )
            if tipo_cuotas == "Por Deuda":
                with colCuotas: # type: ignore
                    st.number_input(
                        label="Número de Cuotas",
                        key='cuotas_co_{}_{}'.format(solicitud['ID_Solicitud'], d['Id_Deuda']),
                        help="Ingrese el número de cuotas para la deuda {}.".format(d['Id_Deuda']),
                        label_visibility="collapsed",
                        value=st.session_state['cuotas_co_{}_{}'.format(solicitud['ID_Solicitud'], d['Id_Deuda'])],
                        min_value=1,
                        max_value=60,
                        step=1,
                    )

    # Siguiente: Construi el Nuevo Datos_Solicitud
    datos = []
    for d in solicitud["JSON_Respuesta"]:
        if not (d['Id_Deuda'] in selected_deudas):
            continue
        monto_actual = next((cleanNumber(d['Monto_Actual']) for d in solicitud["Datos_Solicitud"] if d['Id_Deuda'] == d['Id_Deuda']), 0.0)

        monto_propuesto = cleanNumber(st.session_state['monto_propuesto_co_{}_{}'.format(solicitud['ID_Solicitud'], d['Id_Deuda'])], default_nan=0.0)
        if tipo_cuotas == "Por Deuda":
            num_cuotas = int(st.session_state['cuotas_co_{}_{}'.format(solicitud['ID_Solicitud'], d['Id_Deuda'])])
        else:
            num_cuotas = num_cuotas_global
        datos.append({
            "Id_Deuda": d['Id_Deuda'],
            "Banco": d['Banco'],
            "Numero_Credito": d['Numero_Credito'],
            "Monto_Actual": monto_actual,
            "Monto_Propuesto": monto_propuesto,
            "Num_Cuotas": num_cuotas,
        })

    # Creamos la Posibilidad de Agregar un Comentario Final
    cm_final = st.text_area(
        label="**Comentarios de la ContraOferta**",
        value=solicitud["Metadata_Solicitud"].get("Comentario_Negociador", ""),
        key="comentario_contraoferta_input_{}".format(solicitud['ID_Solicitud']),
        help="Ingrese cualquier comentario adicional sobre la contraoferta.",
    )

    # Creamos la nueva solicitud
    nueva_solicitud = crear_plantilla_solicitud_validacion(
        solicitud=solicitud,
        selected_ids_info=datos,
        comentario=cm_final or "",
    )

    # Verificamos que esta solicitud no exista ya
    ya_existe_contraoferta = check_if_validacion_uploaded(solicitud = nueva_solicitud, old_id = solicitud['ID_Solicitud'])

    # Ahora Creamos los 2 Botones: Uno para Cancelar y Otro para ContraOfertar
    colCancelar, colContraOfertar = st.columns(2, vertical_alignment="center", gap="large")
    with colCancelar:
        if st.button(
            label="**Cancelar**",
            key="cancelar_contraoferta_solicitud_{}".format(solicitud['ID_Solicitud']),
            help="Haga clic para cancelar la contraoferta de la solicitud.",
            type="secondary",
            width="stretch",
        ):
            st.rerun()

    with colContraOfertar:
        if st.button(
            label="**ContraOfertar**",
            key="contraofertar_solicitud_{}".format(solicitud['ID_Solicitud']),
            help="Haga clic para realizar la contraoferta de la solicitud.",
            type="primary",
            width="stretch",
            disabled=ya_existe_contraoferta,
        ):
            with st.spinner("Subiendo ContraOferta de Solicitud de Validación..."):
                success = upload_form_response_to_google_sheets(response_info=nueva_solicitud)
            if success:
                st.toast("ContraOferta de Solicitud de Validación subida exitosamente.", icon="✅")
                sleep(2)
                st.rerun()
            else:
                st.error("Intenta de Nuevo subir la ContraOferta de Solicitud de Validación", icon="❌")

    if ya_existe_contraoferta:
        st.warning("Ya existe una contraoferta para esta solicitud. No se puede subir otra.", icon="⚠️")

# Díalogo para Confirmar la Actualización de las Solicitudes a "Solicitado"
@st.dialog("🫡 Confirmar Actualización de Solicitudes", dismissible=True, width="large", on_dismiss="rerun")
def dialog_confirmar_actualizacion_solicitudes(*, solicitudes: pd.DataFrame) -> None:
    st.markdown("### **ℹ️ Información de la Actualización de Solicitudes**")
    st.divider()

    # Mostramos un Mensaje de Confirmación
    st.warning(
        "¿Está seguro que desea actualizar las solicitudes seleccionadas a 'Solicitado'? Esta acción no se puede deshacer.",
        icon="⚠️",
    )

    # Mostramos un Resumen de las Solicitudes a Actualizar
    st.markdown("### **Resumen de Solicitudes a Actualizar**")
    # Creamos 3 Métricas: Número de Solicitudes, Número de Deudas y Monto Total Propuesto
    num_solicitudes = len(solicitudes)
    num_deudas = sum(len(s['Datos_Solicitud']) for _, s in solicitudes.iterrows())
    monto_total_propuesto = sum(sum(cleanNumber(d['Monto_Propuesto']) for d in s['Datos_Solicitud']) for _, s in solicitudes.iterrows())

    colNumSolicitudes, colNumDeudas, colMontoTotal = st.columns(3, vertical_alignment="center", border=True)
    with colNumSolicitudes:
        st.metric(
            label="**🆔 Número de Solicitudes**",
            value=num_solicitudes,
            delta=None,
            help="Número de solicitudes que se actualizarán a 'Solicitado'.",
        )
    with colNumDeudas:
        st.metric(
            label="**🔢 Número de Deudas**",
            value=num_deudas,
            delta=None,
            help="Número de deudas que se actualizarán a 'Solicitado'.",
        )
    with colMontoTotal:
        st.metric(
            label="**💸 Monto Total Propuesto**",
            value=formatNumber(monto_total_propuesto),
            delta=None,
            help="Monto total propuesto que se actualizará a 'Solicitado'.",
        )

    st.space("medium")

    # Mostramos 2 Botones: Uno para Cancelar y Otro para Confirmar
    colCancelar, colConfirmar = st.columns(2, vertical_alignment="center", gap="large")
    with colCancelar:
        if st.button(
            label="**Cancelar**",
            key="cancelar_actualizacion_solicitudes",
            help="Haga clic para cancelar la actualización de solicitudes.",
            type="secondary",
            width="stretch",
        ):
            st.rerun()

    with colConfirmar:
        if st.button(
            label="**Confirmar Actualización**",
            key="confirmar_actualizacion_solicitudes",
            help="Haga clic para confirmar la actualización de solicitudes.",
            type="primary",
            width="stretch",
        ):
            # Actualizamos las Solicitudes a "Solicitado"
            success = update_solicitudes_to_solicitado(solicitudes=solicitudes)
            if success:
                st.toast("Solicitudes actualizadas exitosamente a 'Solicitado'.", icon="✅")
                st.rerun()
            else:
                st.toast("Intenta de Nuevo actualizar las Solicitudes",icon="❌")

# Función Auxiliar para Mostrar los Detalles de los Solicitudes de Deuda
def mostrar_detalles_solicitudes_deuda(*, solicitud: pd.Series, disable_inputs: bool = False, origen: str) -> None:
    # Creamos 6 Columnas: Id_Deuda, Banco, Numero_Credito, Actualizaciones en Base, Monto Propuesto , Cuotas(Si Hay)
    hay_cuotas = any(d['Num_Cuotas'] > 1 for d in solicitud["Datos_Solicitud"])

    if hay_cuotas:
        colIdDeuda, colBanco, colNumCredito, colActualizaciones, colMontoPropuesto, colCuotas = st.columns([3,3,3,5,6,3], vertical_alignment="top")
    else:
        colIdDeuda, colBanco, colNumCredito, colActualizaciones, colMontoPropuesto = st.columns([3,3,3,5,6], vertical_alignment="top")

    with colIdDeuda:
        st.markdown("**ID de Deuda:**")
    with colBanco:
        st.markdown("**Banco:**")
    with colNumCredito:
        st.markdown("**Número Crédito:**")
    with colActualizaciones:
        st.markdown("**Descuentos en Base:**")
    with colMontoPropuesto:
        st.markdown("**Monto Propuesto:**")
    if hay_cuotas:
        with colCuotas: # type: ignore
            st.markdown("**Cuotas:**")

    for d in solicitud["Datos_Solicitud"]:
        with colIdDeuda:
            st.text_input(
                label = "**ID de Deuda**",
                value = d['Id_Deuda'],
                disabled=True,
                help="ID de la deuda. No se puede modificar.",
                key="id_deuda_{}_{}_show_{}".format(solicitud['ID_Solicitud'], d['Id_Deuda'], origen)
            )
        with colBanco:
            st.text_input(
                label = "**Banco**",
                value = d['Banco'],
                disabled=True,
                help="Banco de la deuda. No se puede modificar.",
                key="banco_{}_{}_show_{}".format(solicitud['ID_Solicitud'], d['Id_Deuda'], origen)
            )
        with colNumCredito:
            st.text_input(
                label = "**Número Crédito**",
                value = d['Numero_Credito'],
                disabled=True,
                help="Número de crédito de la deuda. No se puede modificar.",
                key="numero_credito_{}_{}_show_{}".format(solicitud['ID_Solicitud'], d['Id_Deuda'], origen)
            )
        with colActualizaciones:
            datos_act = get_descuento_en_base(debt=d['Id_Deuda'], original_amount=d['Monto_Actual'])
            st.space("small")
            with st.popover(
                "**Descuentos - {}**".format(d['Id_Deuda']),
                icon="👌",
                help = "Descuentos en base",
            ):
                if datos_act:
                    for descuento in datos_act:
                        st.markdown(descuento)
                else:
                    st.info("No hay descuentos en base para esta deuda.", icon="ℹ️")
        with colMontoPropuesto:
            st.text_input(
                label = "**Monto Propuesto**",
                value = formatNumber(d['Monto_Propuesto']),
                disabled=disable_inputs,
                help="Monto propuesto para la deuda.",
                key="monto_propuesto_{}_{}_show_{}".format(solicitud['ID_Solicitud'], d['Id_Deuda'], origen)
            )
        if hay_cuotas:
            with colCuotas: # type: ignore
                st.text_input(
                    label = "**Número de Cuotas**",
                    value = d['Num_Cuotas'],
                    disabled=disable_inputs,
                    help="Número de cuotas para la deuda.",
                    key="num_cuotas_{}_{}_show_{}".format(solicitud['ID_Solicitud'], d['Id_Deuda'], origen)
                    )

# Función Auxiliar para mostrar los detalles de la respuesta de la Solicitud por Deuda
def mostrar_detalles_respuesta_deuda(*, solicitud: pd.Series) -> None:
    # Creamos 6 Columnas: Id_Deuda, Banco, Numero_Credito, Monto Solicitado, Monto Respuesta, Cuotas (Si Hay)
    deudas_info = solicitud["JSON_Respuesta"]
    hay_cuotas = any(d['Num_Cuotas'] > 1 for d in deudas_info)
    if hay_cuotas:
        colIdDeuda, colBanco, colNumCredito, colMontoSolicitado, colMontoRespuesta, colCuotas = st.columns([3,3,3,6,6,3], vertical_alignment="top")
    else:
        colIdDeuda, colBanco, colNumCredito, colMontoSolicitado, colMontoRespuesta = st.columns([3,3,3,6,6], vertical_alignment="top")

    with colIdDeuda:
        st.markdown("**Id Deuda:**")
    with colBanco:
        st.markdown("**Banco:**")
    with colNumCredito:
        st.markdown("**Número de Crédito:**")
    with colMontoSolicitado:
        st.markdown("**Monto Solicitado:**")
    with colMontoRespuesta:
        st.markdown("**Monto Respuesta:**")
    if hay_cuotas:
        with colCuotas: # type: ignore
            st.markdown("**Cuotas:**")
    
    for d in solicitud["Datos_Solicitud"]:
        # Definimos el Monto Solicitado Original de la Deuda
        monto_respuesta = next((cleanNumber(item['Monto_Propuesto']) for item in solicitud["JSON_Respuesta"] if item["Id_Deuda"] == d["Id_Deuda"]), "N/A")
        with colIdDeuda:
            st.code(d['Id_Deuda'], language="text")
        with colBanco:
            st.code(d['Banco'], language="text")
        with colNumCredito:
            st.code(d['Numero_Credito'], language="text")
        with colMontoSolicitado:
            st.code(formatNumber(d['Monto_Propuesto']), language="text")
        with colMontoRespuesta:
            if monto_respuesta != "N/A":
                st.code(formatNumber(monto_respuesta), language="text")
            else:
                st.code("No Brindado", language="text")
        if hay_cuotas:
            with colCuotas: # type: ignore
                st.code(d['Num_Cuotas'], language="text")

# Función para Mostrar los Datos de una Solicitud
def mostrar_datos_solicitud_ejecutivo(*,solicitud: pd.Series, is_main: bool = False) -> None:
    # Definimos el Nombre del Expander
    expander_name = "`{id}` {tipo:<15} • {aliado} | 📅 `{fecha}` | 📌 `{estado}` | 👤 **Ejecutivo:** {ejecutivo}".format(
        tipo='**{}**'.format(solicitud["Tipo_Solicitud"]),
        fecha=solicitud["Timestamp"].strftime("%Y-%m-%d %H:%M"),
        estado=solicitud["Estado_Solicitud"],
        ejecutivo=solicitud["Ejecutivo"],
        aliado=solicitud["Casa_Cobro"],
        id=solicitud["ID_Solicitud"]
    )

    # Creamos el Expander para Mostrar los Datos de la Solicitud
    with st.expander(expander_name, expanded=is_main):
        # Creamos un Espacio pequeño para Separar el Expander del Contenido
        st.space("small")


        # Creamos 4 Columnas para Mostrar: Monto Total, Persona que Solicita ,Bancos y Cedula
        colMonto, colPersona, colBancos, colCedula = st.columns([2,2,2,2],vertical_alignment="center")

        with colMonto:
            monto_total_solicitud = sum(cleanNumber(d['Monto_Propuesto']) for d in solicitud["Datos_Solicitud"])
            monto_actual_solicitud = sum(cleanNumber(d['Monto_Actual']) for d in solicitud["Datos_Solicitud"])
            st.metric(
                label="**Monto Total:**", value=formatNumber(monto_total_solicitud),
                help = "El monto total de la solicitud (La Suma de los Valores Propuestos por Deuda) que se va a enviar al Aliado",
                delta="{:.1%} de Descuento".format(1 - monto_total_solicitud / monto_actual_solicitud) if monto_actual_solicitud > 0 else "N/A",
                border=True,
            )
        
        with colPersona:
            nombre_nego = obtener_nombre_negociador(email=solicitud["Correo"], full_name=False)
            st.metric(
                label="**Persona que Solicita:**", value=nombre_nego,
                help = "El Nombre del Negociador que realizó la solicitud",
                border=True,
                delta = "{}".format(solicitud["Correo"]),
                delta_color="gray",
                delta_arrow="off"
            )

        with colBancos:
            bancos_list = set([d['Banco'] for d in solicitud["Datos_Solicitud"]])
            bancos_str = ", ".join(bancos_list)
            st.metric(
                label="**Bancos:**", value=bancos_str,
                help = "Los Bancos involucrados en la solicitud",
                border=True,
                delta = "Número de Bancos: {}".format(len(bancos_list)),
                delta_color="gray",
                delta_arrow="off",
            )

        with colCedula:
            # Primero Creamos una Cedula Limpia:
            cedula_limpia = "{:,.0f}".format(cleanNumber(solicitud["Cedula"])) if pd.notnull(cleanNumber(solicitud["Cedula"])) else "No Brindada"
            # Reemplazamos las comas por puntos
            cedula_limpia = cedula_limpia.replace(",", ".")
            st.metric(
                label="**Cédula:**", value=cedula_limpia,
                help = "El Número de Cedula del titular Solicitado",
                border=True,
                delta = "{}".format(solicitud["Metadata_Solicitud"]["Nombre_Cliente"]),
                delta_color="gray",
                delta_arrow="off",
            )

        # Siguiente: Caso Especial: Si es Acuerdo de Pago o Oferta de Pago, Mostrar Fecha de Pago y Tipo de Pago
        if solicitud["Tipo_Solicitud"] in ["Acuerdo de Pago", "Oferta de Acuerdo"]:
            colFechaPago, colTipoPago = st.columns(2)

            with colFechaPago:
                fecha_pago = solicitud["Fecha_Esperada_Pago"].strftime("%Y-%m-%d") if pd.notnull(solicitud["Fecha_Esperada_Pago"]) else "No Brindada"
                falta_para_pago = getBDDaysDiffFloat(solicitud["Fecha_Esperada_Pago"], pd.Timestamp.now(tz='America/Bogota').tz_localize(None)) if pd.notnull(solicitud["Fecha_Esperada_Pago"]) else None
                st.metric(
                    label="**Fecha de Pago:**", value=fecha_pago,
                    help = "La Fecha Esperada de Pago del Acuerdo u Oferta de Pago",
                    border=True,
                    delta_color = "red" if solicitud["Fecha_Esperada_Pago"] < pd.Timestamp.now(tz='America/Bogota').tz_localize(None) else "green",
                    delta_arrow="down" if solicitud["Fecha_Esperada_Pago"] < pd.Timestamp.now(tz='America/Bogota').tz_localize(None) else "up",
                    delta = "{} {:.1f} días hábiles".format("Faltan" if falta_para_pago > 0 else "Retraso de", falta_para_pago) if falta_para_pago is not None else "No Brindada",
                )

            with colTipoPago:
                st.metric(
                    label="**Tipo de Pago:**", value=solicitud["Tipo_Pago"] if pd.notnull(solicitud["Tipo_Pago"]) else "No Brindado",
                    help = "El Método de Pago del Acuerdo u Oferta de Pago",
                    border=True,
                    delta="Ojala que paguen",
                    delta_color="gray",
                    delta_arrow="off",
                )

        # Si hay Comentario_Negociador en la Metadata, se muestra
        if "Comentario_Negociador" in solicitud["Metadata_Solicitud"]:
            comentario_negociador = solicitud["Metadata_Solicitud"]["Comentario_Negociador"]
            if comentario_negociador:
                st.info("**Comentario del Negociador:** {}".format(comentario_negociador), icon="ℹ️")

        # Si hay Fecha_Solicitado se muestra (calculando la diferencia en días hábiles)
        if "Fecha_Solicitado" in solicitud["Metadata_Solicitud"]:
            fecha_solicitado = pd.to_datetime(solicitud["Metadata_Solicitud"]["Fecha_Solicitado"], dayfirst=False, errors='coerce')
            if fecha_solicitado:
                diferencia_dias = getBDDaysDiffFloat(fecha_solicitado, pd.Timestamp.now(tz='America/Bogota').tz_localize(None))
                st.metric(
                    label="**Fecha de Solicitud:**", value=fecha_solicitado.strftime("%Y-%m-%d %H:%M"),
                    help = "La Fecha en que se solicitó la solicitud",
                    delta = "{:.1f} días hábiles atrás".format(diferencia_dias),
                    delta_color="green" if diferencia_dias < 3 else "red",
                    delta_arrow="down",
                    border=True,
                )
        # Paso Siguiente: Mostrar las Caracteristicas por Deuda de la Solicitud
        st.divider()

        # Creamos un Botón para Copiar los Datos de la Solicitud
        colBotonCopy, colInfoCopy = st.columns([1, 5], vertical_alignment="top")
        solicitud_txt = get_solicitud_txt(solicitud=solicitud)
        with colBotonCopy:
            if copy_button(solicitud_txt, key="copy_solicitud_{}_info".format(solicitud['ID_Solicitud'])):
                st.toast("Datos de la solicitud {} copiados al portapapeles.".format(solicitud['ID_Solicitud']), icon=":material/content_copy:")
        
        with colInfoCopy:
            st.info("Haga clic en el botón para copiar todos los datos de la solicitud al portapapeles.", icon="ℹ️")

        with st.expander("**💰 Detalles de la Solicitud por Deuda**", expanded=False):
            mostrar_detalles_solicitudes_deuda(solicitud=solicitud, disable_inputs=True, origen="ejecutivo")

        # Por Último: Mostramos el Botón para Responder la Solicitud
        solicitud_ya_gestionada = not es_solicitud_sin_responder(solicitud)

        # Creamos Dos Columnas: Una para Informacion y otra para el Boton
        colInfo, colBoton = st.columns([4, 2], vertical_alignment="top")

        with colInfo:
            if solicitud_ya_gestionada:
                st.success("Esta solicitud ya ha sido respondida o está en espera de comité/ilocalizable.", icon="✅")
            else:
                st.info("Haz click para responder la solicitud.", icon="ℹ️")

        with colBoton:
            if st.button(
                label="Responder Solicitud",
                key="responder_solicitud_{}".format(solicitud['ID_Solicitud']),
                disabled=solicitud_ya_gestionada,
                type = "primary",
                help="Haga clic para responder la solicitud. Esta acción abrirá un diálogo donde podrá ingresar su respuesta.",
            ):
                dialog_respuesta_solicitud(solicitud=solicitud)

# Función Auxiliar para Mostrar los Datos de una Solicitud para Negociador
def mostrar_datos_solicitud_negociador(*,solicitud):
    # Definimos el Nombre del Expander
    expander_name = "`{id}` {tipo:<15} • {aliado} | 📅 `{fecha}` | 📌 `{estado}`".format(
        tipo='**{}**'.format(solicitud["Tipo_Solicitud"]),
        fecha=solicitud["Timestamp"].strftime("%Y-%m-%d %H:%M"),
        estado=solicitud["Estado_Solicitud"],
        aliado=solicitud["Casa_Cobro"],
        id=solicitud["ID_Solicitud"]
    )

    with st.expander(expander_name, expanded=False):

        # Vamos a Mostrar: Referencia, Monto Total, Ejecutivo, Fecha de Solicitud
        colReferencia, colMontoTotal, colEjecutivo, colFechaSolicitud = st.columns([2, 2, 2, 2], vertical_alignment="center")
        with colReferencia:
            st.metric(
                label="**Referencia:**", value=solicitud["Referencia"],
                help = "La Referencia del Cliente que realizó la solicitud",
                delta = "CC: {}".format(solicitud["Cedula"]) if pd.notnull(solicitud["Cedula"]) else "No Brindada",
                delta_color="gray",
                delta_arrow="off",
                border=True,
            )
        with colMontoTotal:
            monto_total_solicitud = sum(cleanNumber(d['Monto_Propuesto']) for d in solicitud["Datos_Solicitud"])
            monto_actual_solicitud = sum(cleanNumber(d['Monto_Actual']) for d in solicitud["Datos_Solicitud"])
            st.metric(
                label="**Monto Total:**", value=formatNumber(monto_total_solicitud),
                help = "El monto total de la solicitud (La Suma de los Valores Propuestos por Deuda) que se va a enviar al Aliado",
                delta="{:.1%} de Descuento".format(1 - monto_total_solicitud / monto_actual_solicitud) if monto_actual_solicitud > 0 else "N/A",
                border=True,
            )
        with colEjecutivo:
            st.metric(
                label="**Ejecutivo:**",
                value=solicitud["Ejecutivo"] if pd.notnull(solicitud["Ejecutivo"]) else "Sin Asignar",
                help = "El Ejecutivo que atiende la solicitud",
                border=True,
            )
        with colFechaSolicitud:
            dias_delta = getBDDaysDiffFloat(
                solicitud["Timestamp"], pd.Timestamp.now(tz='America/Bogota').tz_localize(None)
            )
            st.metric(
                label="**Fecha de Solicitud:**",
                value=solicitud["Timestamp"].strftime("%Y-%m-%d %H:%M"),
                help = "La fecha y hora en que se realizó la solicitud",
                delta = "{:.1f} días atrás".format(dias_delta),
                border=True,
                delta_color="red" if dias_delta > 7 else "green",
                delta_arrow="down" if dias_delta > 7 else "up",
            )

        # Mostramos el Comentario del Negociadoor y el Ejecutivo
        comentario_negociador = solicitud["Metadata_Solicitud"].get("Comentario_Negociador", "")
        comentario_ejecutivo = solicitud["Metadata_Solicitud"].get("Comentario_Ejecutivo", "")

        if comentario_negociador:
            st.info("**Comentario del Negociador:** {}".format(comentario_negociador), icon="ℹ️")
        if comentario_ejecutivo:
            st.info("**Comentario del Ejecutivo:** {}".format(comentario_ejecutivo), icon="ℹ️")

        # Siguiente: Especificaciones si es Acuerdo de Pago u Oferta de Pago
        if solicitud["Tipo_Solicitud"] in ["Acuerdo de Pago", "Oferta de Acuerdo"]:
            # Dos Columnas: Una para Fecha de Pago y otra para Tipo de Pago
            colFechaPago, colTipoPago = st.columns(2, vertical_alignment="center")

            with colFechaPago:
                fecha_pago = solicitud["Fecha_Esperada_Pago"].strftime("%Y-%m-%d") if pd.notnull(solicitud["Fecha_Esperada_Pago"]) else "No Brindada"
                falta_para_pago = getBDDaysDiffFloat(solicitud["Fecha_Esperada_Pago"], pd.Timestamp.now(tz='America/Bogota').tz_localize(None)) if pd.notnull(solicitud["Fecha_Esperada_Pago"]) else None
                ya_paso_fecha = solicitud["Fecha_Esperada_Pago"] < pd.Timestamp.now(tz='America/Bogota').tz_localize(None) if pd.notnull(solicitud["Fecha_Esperada_Pago"]) else None
                st.metric(
                    label="**Fecha de Pago:**", value=fecha_pago,
                    help = "La Fecha Esperada de Pago del Acuerdo u Oferta de Pago",
                    border=True,
                    delta_color = "red" if ya_paso_fecha else "green",
                    delta_arrow="down" if ya_paso_fecha else "up",
                    delta = "{} {:.1f} días hábiles".format("Faltan" if ya_paso_fecha else "Retraso de", falta_para_pago) if falta_para_pago is not None else "No Brindada",
                )

            with colTipoPago:
                st.metric(
                    label="**Tipo de Pago:**", value=solicitud["Tipo_Pago"] if pd.notnull(solicitud["Tipo_Pago"]) else "No Brindado",
                    help = "El Método de Pago del Acuerdo u Oferta de Pago",
                    border=True,
                    width="stretch",
                    delta="Pagar la Solicitud :D",
                    delta_color="gray",
                    delta_arrow="off",
                )

        # Si hay Fecha_Solicitado se muestra (calculando la diferencia en días hábiles)
        if "Fecha_Solicitado" in solicitud["Metadata_Solicitud"]:
            fecha_solicitado = pd.to_datetime(solicitud["Metadata_Solicitud"]["Fecha_Solicitado"], dayfirst=False, errors='coerce')
            if fecha_solicitado:
                diferencia_dias = getBDDaysDiffFloat(fecha_solicitado, pd.Timestamp.now(tz='America/Bogota').tz_localize(None))
                st.metric(
                    label="**Fecha de Solicitud:**", value=fecha_solicitado.strftime("%Y-%m-%d %H:%M"),
                    help = "La Fecha en que se solicitó la solicitud",
                    delta = "{:.1f} días hábiles atrás".format(diferencia_dias),
                    delta_color="green" if diferencia_dias < 3 else "red",
                    delta_arrow="down",
                    border=True,
                    width="stretch",
                )

        # Añadimos un Divisor
        st.divider()

        # Mostramos los Datos por Deuda de la Solicitud en un Expander
        with st.expander("**💰 Detalles de la Solicitud por Deuda**", expanded=False):
            mostrar_detalles_solicitudes_deuda(solicitud=solicitud, disable_inputs=True, origen="negociador")

        # Si no esta gestionada, se muestra un mensaje de información de que no se ha respondido
        if es_solicitud_sin_responder(solicitud):
            st.info("Esta solicitud aún no ha sido respondida por un ejecutivo. Por favor, espere a que un ejecutivo la gestione.", icon="ℹ️")
            return 

        # Siguiente verificación: SI neceista aprobación es necesario que se aprube o desapruebe
        if es_solicitud_aprobacion_necesaria(solicitud):
            # Definimos el Tipo de AProbación
            tipo_aprobacion = obtener_tipo_aprobacion_necesaria(solicitud)
            st.info("Esta solicitud requiere aprobación de tipo: {}".format(tipo_aprobacion), icon="ℹ️")

            # Creamos 2 Botones: Uno para Aprobar y Otro para Desaprobar la Solicitud
            colAprobar, colDesaprobar = st.columns(2, vertical_alignment="center", gap="large")

            with colAprobar:
                hacer_aprobacion = st.button(
                    label="Aprobar Solicitud",
                    key="aprobar_solicitud_{}".format(solicitud['ID_Solicitud']),
                    help="Haga clic para aprobar la solicitud. Esta acción enviará la solicitud al aliado.",
                    type="primary",
                    width="stretch",
                )
            with colDesaprobar:
                hacer_desaprobacion = st.button(
                    label="Desaprobar Solicitud",
                    key="desaprobar_solicitud_{}".format(solicitud['ID_Solicitud']),
                    help="Haga clic para desaprobar la solicitud. Esta acción enviará la solicitud al aliado.",
                    type="secondary",
                    width="stretch",
                )

            if hacer_aprobacion or hacer_desaprobacion:
                aprobado = hacer_aprobacion
                # Subimos la Aprobación
                success = actualizar_aprobacion_necesaria(
                    solicitud=solicitud,
                    tipo_aprobacion=tipo_aprobacion,
                    aprobado=aprobado
                )
                if success:
                    st.toast("Solicitud {} {} correctamente.".format(solicitud['ID_Solicitud'], "aprobada" if aprobado else "desaprobada"), icon="✅")
                    st.rerun()
                else:
                    st.error("Hubo un error al {} la solicitud {}. Por favor, intente nuevamente.".format("aprobar" if aprobado else "desaprobar", solicitud['ID_Solicitud']), icon="❌")

            # Acabamos la función aquí, ya que no se puede continuar con la solicitud hasta que se apruebe o desapruebe
            return 

        # Siguiente Paso: Mostramos la Info de la Respuesta
        st.subheader("**📋 Información de la Respuesta a la Solicitud**")

        # Creamos Columnas para Mostrar: Fecha de Respuesta, Estado de Solicitud, Monto Respuesta (Si Hay)
        if solicitud["Estado_Solicitud"] == "Exitosa":
            colFechaResp, colEstadoSolicitud, colMontoRespuesta = st.columns([2, 2, 2], vertical_alignment="center")
        else:
            colFechaResp, colEstadoSolicitud = st.columns([2, 2], vertical_alignment="center")

        with colFechaResp:
            st.metric(
                label="**Fecha de Respuesta:**",
                value=solicitud["Fecha_Respuesta"].strftime("%Y-%m-%d") if pd.notnull(solicitud["Fecha_Respuesta"]) else "No Brindada",
                help = "La Fecha de Respuesta de la solicitud",
                border=True,
                width="stretch",
            )
        with colEstadoSolicitud:
            st.metric(
                label="**Estado de Solicitud:**",
                value=solicitud["Estado_Solicitud"],
                help = "El Estado de la solicitud",
                border=True,
                width="stretch",
            )

        if solicitud["Estado_Solicitud"] == "Exitosa":
            with colMontoRespuesta: # type: ignore
                deudas_respuesta = solicitud.get("JSON_Respuesta", []) + solicitud.get("Metadata_Solicitud", {}).get("Addendums", [])
                deudas_respuesta = [d['Id_Deuda'] for d in deudas_respuesta]
                monto_total_respuesta = sum(cleanNumber(d['Monto_Propuesto']) for d in solicitud["Datos_Solicitud"])
                monto_actual_respuesta = sum(cleanNumber(d['Monto_Actual']) for d in solicitud["Datos_Solicitud"] if d['Id_Deuda'] in deudas_respuesta)
                st.metric(
                    label="**Monto Respuesta:**", value=formatNumber(monto_total_respuesta),
                    help = "El monto total de la respuesta (La Suma de los Valores Propuestos por Deuda) que se envió al Aliado",
                    delta="{:.1%} de Descuento".format(1 - monto_total_respuesta / monto_actual_respuesta) if monto_actual_respuesta > 0 else "N/A",
                    border=True,
                    width="stretch",
                )

        # Mostramos los Comentarios del Ejecutivo otra vez
        comentario_ejecutivo = solicitud["Metadata_Solicitud"].get("Comentario_Ejecutivo", "")
        if comentario_ejecutivo:
            st.info("**Comentario del Ejecutivo:** {}".format(comentario_ejecutivo), icon="ℹ️")

        # Si la Solicitud no es Exitosa, todo finaliza aquí
        if solicitud["Estado_Solicitud"] != "Exitosa":
            return

        # Siguiente: Mostrar los Detalles de la Respuesta por Deuda en un Expander
        with st.expander("**💰 Detalles de la Respuesta por Deuda**", expanded=True):
            mostrar_detalles_respuesta_deuda(solicitud=solicitud)

        # Siguiente: Mostrar Fecha_Limite_Pago, Pago Total Obligatorio y Metodo de Pago si no es Validación
        if solicitud["Tipo_Solicitud"] == "Validación":
            colFechaLimite, colPagoTotal = st.columns([2, 2], border=True)
        else:
            colFechaLimite, colPagoTotal, colMetodoPago = st.columns([2, 2, 2], border=True)

        with colFechaLimite:
            fecha_limite_pago = solicitud.get("Fecha_Limite_Pago", None)
            st.metric(
                label="**Fecha Límite de Pago:**",
                value=fecha_limite_pago.strftime("%Y-%m-%d") if pd.notnull(fecha_limite_pago) else "No Brindada",
                help = "La Fecha Límite de Pago de la solicitud",
                width="stretch",
            )
        with colPagoTotal:
            aplica_pto = solicitud.get("Metadata_Solicitud", {}).get("Pago_Total_Obligatorio", False)
            st.metric(
                label="**Pago Total Obligatorio:**",
                value="Sí" if aplica_pto else "No",
                help = "El monto total obligatorio de la solicitud",
                delta= "Necesitas pagar todas las deudas" if aplica_pto else "Puedes pagar deudas de forma individual",
                width="stretch",
            )
        if solicitud["Tipo_Solicitud"] != "Validación":
            with colMetodoPago:  # type: ignore
                st.metric(
                    label="**Método de Pago:**",
                    value=solicitud.get("Metodo_Pago", "No Brindado"),
                    help = "El Método de Pago de la solicitud",
                    width="stretch",
                )

        # Siguiente: Mostrar el Botón al acuerdo de Pago o de Posibilidad de Subir Solicitud de Acuerdo
        if solicitud["Tipo_Solicitud"] in ["Acuerdo de Pago", "Oferta de Acuerdo"]:
            file_id = solicitud.get("Metadata_Solicitud", {}).get("Id_Acuerdo_Pago", None)
            if file_id is None or file_id == "":
                st.warning("No se encontró el archivo del Acuerdo de Pago. Por favor, contacte al ejecutivo.", icon="⚠️")
            else:
                # Creamos 2 Botonos: Link al Acuerdo de Pago y Botón para Copiar datos de la solicitud
                colLinkAcuerdo, colBotonCopiar = st.columns([4, 1], vertical_alignment="center")
                with colLinkAcuerdo:
                    url_acuerdo_pago = obtener_link_acuerdo_pago(file_id)
                    st.link_button(
                        label="📄 Ver Acuerdo de Pago",
                        url=url_acuerdo_pago,
                        width="stretch",
                        type="primary",
                        help="Haga clic para ver el Acuerdo de Pago en PDF.",
                    )
                with colBotonCopiar:
                    txt_copiar = get_solicitud_txt(solicitud=solicitud,origen='JSON_Respuesta')
                    copy_button(txt_copiar, key="copy_solicitud_{}_respuesta".format(solicitud['ID_Solicitud']),tooltip="Copiar Resultado")
        else:

            # Creamos 3 Columnas: 1 para Boton de Abrir Dialogo, una para ajustar la oferta y otra de botón copiar
            colBotonAbrir, colInfoBoton, colBotonCopiar = st.columns([3, 4, 1], vertical_alignment="center")

            with colBotonAbrir:
                if st.button(
                    label="**Subir Solicitud de Acuerdo de Pago**",
                    width="stretch",
                    type="primary",
                    key = "abrir_dialogo_ac_pago_{}".format(solicitud['ID_Solicitud']),
                    help = "Botón para tener la Posibilidad de subir un Acuerdo de Pago",
                    icon="📄"
                ):
                    dialog_subir_acuerdo_pago(solicitud=solicitud)

            with colInfoBoton:
                if st.button(
                    label="**Generar ContraOferta**",
                    width="stretch",
                    type="secondary",
                    key = "ajustar_oferta_pago_{}".format(solicitud['ID_Solicitud']),
                    help = "Botón para ajustar la oferta de pago de la solicitud",
                    icon="🔄",
                ):
                    ajustar_contraoferta_solicitud(solicitud=solicitud)

            with colBotonCopiar:
                txt_copiar = get_solicitud_txt(solicitud=solicitud,origen='JSON_Respuesta')
                copy_button(txt_copiar, key="copy_solicitud_{}_respuesta".format(solicitud['ID_Solicitud']),tooltip="Copiar Resultado")

# Función Auxiliar para mostrar el Resumen del Ejecutivo de sus Solicitudes
def mostrar_resumen_solicitudes_ejecutivo(*, solicitudes: pd.DataFrame) -> None:
    st.title("😎 Resumen de Solicitudes")
    # Siguiente: Definición del Dashboard de Resumen de Solicitudes
    st.divider()
    # Creamos 2 Columnas: 1 para Pie Graph de Estados de Solicitudes y otra para KPIs
    colPieEstados, colKPIs = st.columns([4, 2], gap = "small", vertical_alignment="center", border=True,)

    with colPieEstados:
        st.subheader("📊 Distribución de Estados de Solicitudes")
        # Creamos el Gráfico de Pie de Estados de Solicitudes
        fig_pie_estados = px.pie(
            solicitudes,
            names='Estado_Solicitud',
            title='Distribución de Estados de Solicitudes',
            hole=0.4,
            color_discrete_sequence=px.colors.qualitative.Set3
        )
        st.plotly_chart(fig_pie_estados,width= "stretch")

    with colKPIs:
        tiempos_respuesta = obtener_promedio_tiempos_respuesta(solicitudes)
        respuestas_por_dia = obtener_promedio_respuestas_dia(solicitudes)
        mascara_sin_responder = obtener_mascara_sin_responder(solicitudes)
        solicitudes_sin_responder = mascara_sin_responder.sum()

        st.subheader("📈 KPIs de Respuesta")
        st.metric(
            "**Solicitudes Sin Responder**", 
            f"{solicitudes_sin_responder} Solicitudes", 
            delta_color= "green" if solicitudes_sin_responder <= 20 else "red"
        )
        st.metric(
            "**Promedio de Tiempo de Respuesta (días)**", 
            f"{tiempos_respuesta['promedio_general']:.2f}",
            delta_color= "green" if tiempos_respuesta['promedio_general'] <= 3 else "red" # type: ignore
        )
        st.metric(
            "**Respuestas por Día**",
            f"{respuestas_por_dia['promedio_general']:.2f}",
            delta_color= "green" if respuestas_por_dia['promedio_general'] >= 10 else "red" # type: ignore
        )
        # Ahora Creamos 2 Popovers para mostrar los detalles de los KPIs
        with st.popover("Respuestas por Día", icon="ℹ️"):
            st.write("**Promedio de Respuestas por Día por Tipo de Solicitud:**")
            for dia, respuestas in respuestas_por_dia['promedio_por_tipo'].items(): # type: ignore
                st.write(f"- {dia}: {respuestas:.2f} respuestas")

        with st.popover("Tiempos por Tipo", icon="ℹ️"):
            st.write("**Promedio de Tiempo de Respuesta por Tipo de Solicitud:**")
            for tipo, tiempo in tiempos_respuesta['promedio_por_tipo'].items(): # type: ignore
                st.write(f"- {tipo}: {tiempo:.2f} días")

    # Añadimos un Divisor
    st.divider()
    # Siguientes Gráficos: Solicitudes sin Responder por Casa de Cobro, Bancos y Ejecutivos
    st.subheader("📊 Solicitudes Sin Responder")

    if solicitudes_sin_responder > 0:
        # La Estructura será: 2 Columnas: Casa de Cobro y Ejecutivo
        colCasaCobro, colEjecutivo = st.columns([4,3], gap = "small", vertical_alignment="center", border=True,)

        with colCasaCobro: # La única con gráfico de Barras, además este debe ser vertical
            st.subheader("🥸 Por Casa de Cobro")

            fig_casa_cobro = px.bar(
                solicitudes.groupby('Casa_Cobro').size().reset_index(name='count'),
                x='count',                # Swapped: values on x-axis
                y='Casa_Cobro',            # Swapped: labels on y-axis
                title='Solicitudes Sin Responder por Casa de Cobro',
                color='count',
                orientation='h',           # Set orientation to horizontal
                color_continuous_scale=px.colors.sequential.Viridis
            )

            # Ahora Renombramos los ejes para que sean más claros
            fig_casa_cobro.update_layout(
                xaxis_title="Cantidad de Solicitudes Sin Responder",
                yaxis_title="Casa de Cobro",
                coloraxis_colorbar=dict(title="Cantidad")
            )

            # Optional: To keep the top category at the top of the chart
            fig_casa_cobro.update_layout(yaxis={'categoryorder': 'total ascending'})

            st.plotly_chart(fig_casa_cobro, width='stretch', key="casa_cobro_no_response_ejecutivo")

        with colEjecutivo: # Mostramos un Pie
            st.subheader("👨‍💼 Por Ejecutivo")
            fig_ejecutivo = px.pie(
                solicitudes.groupby('Ejecutivo').size().reset_index(name='count'),
                names='Ejecutivo',
                values='count',
                title='Solicitudes Sin Responder por Ejecutivo',
                hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Set3
            )
            st.plotly_chart(fig_ejecutivo, width='stretch', key="ejecutivo_no_response_ejecutivo")
    else:
        st.success("No hay solicitudes sin responder en este momento.", icon="✅")

# Función Auxiliar para mostrar el resumen de una persona de sus solicitudes
def mostrar_resumen_solicitudes_negociador(*, solicitudes: pd.DataFrame, nego_name: str, show_header: bool = True) -> None:
    # Paso 1: Verificar si hay solicitudes
    if solicitudes.empty:
        st.info("No hay solicitudes disponibles para mostrar.", icon="ℹ️")
        return

    # Paso 2: Sacar KPIs
    # Número de Solicitudes (con Exitosas y % de Exitosas)
    num_solicitudes = len(solicitudes)
    num_solicitudes_exitosas = np.sum(solicitudes["Estado_Solicitud"] == "Exitosa")
    porcentaje_exitosas = (num_solicitudes_exitosas / num_solicitudes) * 100 if num_solicitudes > 0 else 0
    # Numero de Deudas y Clientes Solicitados
    num_deudas = solicitudes["Datos_Solicitud"].apply(len).sum()
    num_clientes = solicitudes["Referencia"].nunique()
    # Días hasta Respuesta Promedio y Días hasta Respuesta Máximo
    # Primero Obtenemos las Solicitudes con Respuesta
    sols_respondidas = ~obtener_mascara_sin_responder(solicitudes)
    if sols_respondidas.any():
        dias_respuesta = getBDDaysDiffFloat_vectorized(
            solicitudes.loc[sols_respondidas, "Timestamp"],
            solicitudes.loc[sols_respondidas, "Fecha_Respuesta"]
        )
        dias_respuesta_promedio = dias_respuesta.mean()
        dias_respuesta_maximo = dias_respuesta.max()
    else:
        dias_respuesta_promedio = 0
        dias_respuesta_maximo = 0

    if show_header:
        st.subheader("**📊 Resumen de Solicitudes del Negociador**")

    # Paso 3: Mostrar los KPIs en 3 Columnas
    colNumSols, colNumDeudas, colDiasRespuesta = st.columns(3, vertical_alignment="center")

    with colNumSols:
        st.metric(
            label="**Número de Solicitudes:**",
            value=num_solicitudes,
            help="El número total de solicitudes realizadas por el negociador.",
            delta="{} Exitosas ({:.1f}% Exitosas)".format(num_solicitudes_exitosas, porcentaje_exitosas),
            delta_color="green" if porcentaje_exitosas > 50 else "yellow" if porcentaje_exitosas > 20 else "red",
            border=True,
        )
    with colNumDeudas:
        st.metric(
            label="**Deudas y Clientes Solicitados:**",
            value="{} deudas, {} clientes".format(num_deudas, num_clientes),
            help="El número total de deudas e clientes incluidos en las solicitudes.",
            delta = "{} deudas por cliente en promedio".format(num_deudas / num_clientes) if num_clientes > 0 else "N/A",
            delta_color="gray",
            delta_arrow="off",
            border=True
        )
    with colDiasRespuesta:
        st.metric(
            label="**Días hasta Respuesta (Promedio):**",
            value="{:.1f}".format(dias_respuesta_promedio),
            delta = "{:.1f} días máximo".format(dias_respuesta_maximo),
            delta_color = "green" if dias_respuesta_promedio < 3 else "yellow" if dias_respuesta_promedio < 7 else "red",
            delta_arrow = "up" if dias_respuesta_promedio > 7 else "down",
            help="El número promedio de días que toma responder a una solicitud.",
            border=True
        )

    st.divider()

    st.subheader("**📋 Solicitudes en el Tiempo**")

    # Vamos a Crear un Gráfico de lineas que va a acumular:
    # Solicitudes realizadas (por Timestamp)
    # Solicitudes respondidas (por Fecha_Respuesta)

    # Paso 1: Crear los DFs separados por Timestamp y Fecha_Respuesta
    df_timestamp = solicitudes[solicitudes["Timestamp"].notna()].copy()
    df_respuesta = solicitudes[solicitudes["Fecha_Respuesta"].notna()].copy()

    # Paso 2: Ordenar los Dfs por sus fechas
    df_timestamp = df_timestamp.sort_values(by="Timestamp")
    df_respuesta = df_respuesta.sort_values(by="Fecha_Respuesta")

    # Paso 3: Crear el Conteo Acumulado
    df_timestamp['Conteo'] = 1
    df_respuesta['Conteo'] = 1
    df_timestamp_acumulado = df_timestamp.groupby(df_timestamp["Timestamp"].dt.date).agg({"Conteo": "sum"}).cumsum().reset_index()
    df_respuesta_acumulado = df_respuesta.groupby(df_respuesta["Fecha_Respuesta"].dt.date).agg({"Conteo": "sum"}).cumsum().reset_index()

    # Paso 4: Crear el Gráfico de Líneas con Plotly
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df_timestamp_acumulado["Timestamp"],
        y=df_timestamp_acumulado["Conteo"],
        mode='lines+markers',
        name='Solicitudes Realizadas',
        line=dict(color='blue', width=2),
        marker=dict(size=6),
        fill='tozeroy',
        fillcolor='rgba(0, 0, 255, 0.1)'
    ))

    fig.add_trace(go.Scatter(
        x=df_respuesta_acumulado["Fecha_Respuesta"],
        y=df_respuesta_acumulado["Conteo"],
        mode='lines+markers',
        name='Solicitudes Respondidas',
        line=dict(color='green', width=2),
        marker=dict(size=6),
        fill='tozeroy',
        fillcolor='rgba(0, 255, 0, 0.1)',
    ))

    # Actualizamos el Layout del Gráfico
    fig.update_layout(
        title='Solicitudes en el Tiempo',
        xaxis_title='Fecha',
        yaxis_title='Número de Solicitudes',
        legend_title='Tipo de Solicitud',
        hovermode='x unified'
    )

    # Mostramos el Gráfico
    st.plotly_chart(fig, width="stretch", key=f"solicitudes_tiempo_{nego_name}")

    st.divider()

    st.subheader("**🤖 Distribución de Solicitudes**")

    # Vamos a Crear 2 Pies
    # Pie de Estados de Solicitud
    # Pie de Aliados Solicitados (Casa_Cobro)

    colEstados, colAliados = st.columns(2, vertical_alignment="center", border=True)

    with colEstados:
        # Creamos un Pie de Estados de Solicitud
        estados_counts = solicitudes["Estado_Solicitud"].value_counts()
        fig_estados = go.Figure(data=[go.Pie(labels=estados_counts.index, values=estados_counts.values, hole=.4)])
        fig_estados.update_layout(title_text='Distribución de Estados de Solicitud')
        st.plotly_chart(fig_estados, width="stretch", key=f"estados_solicitud_{nego_name}")

    with colAliados:
        # Creamos un Pie de Aliados Solicitados (Casa_Cobro)
        aliados_counts = solicitudes["Casa_Cobro"].value_counts()
        fig_aliados = go.Figure(data=[go.Pie(labels=aliados_counts.index, values=aliados_counts.values, hole=.4)])
        fig_aliados.update_layout(title_text='Distribución de Aliados Solicitados')
        st.plotly_chart(fig_aliados, width="stretch", key=f"aliados_solicitud_{nego_name}")

# Función Auxiliar para mostrar el Botón que limpia los Filtros Versión Negociador
def mostrar_boton_limpiar_filtros_negociador(key_extra: str):
    reiniciar_filtros = st.button(
        "Reiniciar Filtros",
        key="reiniciar_filtros_button" + key_extra,
        help="Haz clic para reiniciar los filtros de solicitudes",
        on_click=reiniciar_filtros_solicitudes_negociadores,
        type="secondary"
    )