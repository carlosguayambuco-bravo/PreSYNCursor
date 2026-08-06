# Estándar usando Pep8
# Librerías de Python
from typing import Optional, Literal
# Librerías de Terceros
import numpy as np
import pandas as pd
from pandera.typing import DataFrame
import streamlit as st
from st_copy_to_clipboard import st_copy_to_clipboard
# Librerías Locales
from data.data_models import SolicitudesSchema
from modules.acuerdo_pdf_generator.agreement_pdf import generate_payment_agreement_pdf
from modules.bank_normalizer import BANCOS_UNICOS
from modules.constants import ESTADOS_POSIBLES_SOLICITUD, ESTADOS_PREFINALIZAR_SOLICITUD, ESTADOS_RESPONDIBLES_SOLICITUD
from modules.forms import obtener_nombre_negociador
from modules.gest_sols import subir_acuerdo_pago_a_google_drive, distribuir_resultado_solicitud, obtener_mascara_sin_responder, get_descuento_en_base, get_solicitud_txt, upload_massive_addendums, reiniciar_filtros_solicitudes, generate_plantilla_serie_acuerdo
from modules.classes import get_banned_manager
from utils.helpers_general import cleanNumber, getBDDaysDiffFloat_vectorized

# Función para Mostrar los Filtros Generales de una Solicitud
def mostrar_filtros_generales_solicitud(*, solicitudes_df: DataFrame[SolicitudesSchema]) -> DataFrame[SolicitudesSchema]:

    solicitudes_copy = solicitudes_df.copy()  # Creamos una copia del DataFrame para no modificar el original

    # Vamos a Crear 3 Columnas: Boton de Reinicio Total, Boton de Reinicio Basico y Boton de Recomendado
    colResetTotal, colResetBasico, colRecomendado = st.columns(3, vertical_alignment="center")

    with colResetTotal:
        st.button(
            label="Reiniciar Filtros (Total)",
            key="reiniciar_filtros_solicitudes_total",
            type="secondary",
            on_click=reiniciar_filtros_solicitudes,
            args=('reset',),
            help="Haga clic para reiniciar todos los filtros de solicitudes.",
        )

    with colResetBasico:
        usar_basico = st.button(
            label="Reiniciar Filtros (Básico)",
            key="reiniciar_filtros_solicitudes_basico",
            type="primary",
            on_click=reiniciar_filtros_solicitudes,
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
        sorted_indices = np.argsort((calc_df["Diferencia_Dias"]* -1).to_numpy())
        # Paso 5: Aplicar este orden a solicitudes_df para obtener el DataFrame final ordenado
        solicitudes_df = solicitudes_df.iloc[sorted_indices]
    else:
        # Ordenamos los más antiguos primero
        solicitudes_df = solicitudes_df.sort_values(by="Timestamp", ascending=True)

    # Por Último devolvemos el DataFrame de Solicitudes filtrado
    return solicitudes_df

# Función Auxiliar para mostrar el Botón que va a Finalizar la Solicitud y mantener toda la Lógica de forma Interna
def mostrar_boton_actualizar_solicitudes(*, solicitud: pd.Series, pdf_bytes: Optional[bytes] = None) -> None:
    # Primero: Mostrar el Boton de la Solicitud y el Botón de Cancelar
    colCancelar, colBoton = st.columns([1, 1])

    with colCancelar:
        st.button(
            label="Cancelar",
            key="cancelar_solicitud_{}".format(solicitud['ID_Solicitud']),
            on_click=st.rerun,
            help="Haga clic para cancelar la actualización de la solicitud.",
            width="stretch",
            type="secondary",
        )

    with colBoton:
        actualizar_solicitud = st.button(
            label="Finalizar Solicitud",
            key="finalizar_solicitud_{}".format(solicitud['ID_Solicitud']),
            width="stretch",
            type="primary",
        )
    if actualizar_solicitud:
        with st.spinner("Subiendo Solicitud a Google Sheets..."):
            # Actualizamos la Solicitud en Google Sheets
            success = distribuir_resultado_solicitud(solicitud)
            # Subimos el Acuerdo de Pago si es necesario
            if (pdf_bytes is not None) and len(pdf_bytes) > 0:
                file_id = subir_acuerdo_pago_a_google_drive(pdf_bytes=pdf_bytes, solicitud_info=solicitud)
                success = success and bool(file_id)
            # Actualizamos los Datos de Addendums
            upload_massive_addendums(solicitud=solicitud)
        if success:
            st.toast("Solicitud Finalizada y Actualizada a Google Sheets con Éxito.",icon="✅")
            # Agregamos el ID de la Solicitud al BannedManager para que no se pueda volver a responder
            banned_manager = get_banned_manager()
            banned_manager.ban(solicitud["ID_Solicitud"])
            st.rerun()
        else:
            st.error("Error al Subir la Solicitud a Google Sheets o el Acuerdo de Pago a Google Drive. Por favor, intente nuevamente.")

# Función Auxiliar para mostrar las Especificaciones del Acuerdo de Pago Generado
def mostrar_especificaciones_acuerdo_generado(*, solicitud: pd.Series) -> bytes:

    # Paso 1: Mostrar los Inputs del Acuerdo de Pago Generado

    with st.expander("**Especificaciones del Acuerdo de Pago Generado**", expanded=False, icon="🔏"):
        st.markdown("### **ℹ️ Información de la Solicitud**")

        # Reunimos la Información de las Deudas y los Addendums en uno Solo
        deudas_info = solicitud["Datos_Solicitud"] + solicitud["Metadata_Solicitud"].get("Addendums",[])

        # Definimos todas las Deudas Disponibles
        debt_ids = [d['Id_Deuda'] for d in deudas_info]

        # Creamos una Vista de Pills para definir las Deudas a Usar
        selected_ids = st.pills(
            label="**Deudas y Addendums usados**",
            options=debt_ids,
            default=debt_ids,
            help="Seleccione las deudas y addendums que desea incluir en el acuerdo de pago generado.",
            key = "deudas_addendums_solicitud_info_{}".format(solicitud['ID_Solicitud'])
        )

        if selected_ids is None or not selected_ids:
            st.error("Debe seleccionar al menos una deuda o addendum para generar el acuerdo de pago.")
            st.stop()

        selected_deudas_info = [d for d in deudas_info if (d['Id_Deuda'] in selected_ids)]
        monto_total = sum(d['Monto_Propuesto'] for d in selected_deudas_info)

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
                value=solicitud["Tipo_Pago"],
                disabled=True,
                key="metodo_pago_solicitud_info_{}".format(solicitud['ID_Solicitud']),
            )
        with col3Info:
            st.text_input(
                label="**📅 Fecha Límite de Pago**",
                value=solicitud["Fecha_Esperada_Pago"].strftime("%Y-%m-%d") if pd.notna(solicitud["Fecha_Esperada_Pago"]) else "",
                disabled=True,
                key="fecha_limite_pago_solicitud_info_{}".format(solicitud['ID_Solicitud']),
            )

        # Ahora vamos a presentar por cada deuda seleccionada: Id_Deuda, Numero_Credito y Monto Propuesto
        for d in selected_deudas_info:
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
                    disabled=True,
                    key="numero_credito_solicitud_info_{}_{}".format(solicitud['ID_Solicitud'], d['Id_Deuda']),
                )
            with col3Info:
                st.text_input(
                    label="**Monto Propuesto**",
                    value="{:,.0f}".format(d['Monto_Propuesto']),
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
            key=key_acuerdo,
            type="primary",
            help="Haga clic para generar el acuerdo de pago en formato PDF.",
            disabled = len(st.session_state.get(key_acuerdo, bytes())) > 0,
        )
        if generar_pdf:
            with st.spinner("⚙️ Generando Acuerdo de Pago en PDF..."):
                # Paso 1: Crear la Serie de Datos
                serie_acuerdo = generate_plantilla_serie_acuerdo(solicitud=solicitud)
                # Paso 2: Obtener los Bytes del Acuerdo
                pdf_bytes = generate_payment_agreement_pdf(agreement=serie_acuerdo, assets_dir="assets", alpha=0.10) # type: ignore
                # Paso 3: Guardar los Bytes en el Session State
                st.session_state[key_acuerdo] = pdf_bytes

    return st.session_state.get(key_acuerdo, bytes())

# Función para Abrir el Dialogo de Respuesta de una Solicitud
@st.dialog("🗒️ Respuesta a Solicitud",dismissible=True,width="large")
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
    monto_propuesto_total = sum(d['Monto_Propuesto'] for d in solicitud["Datos_Solicitud"])
    key_monto_total = 'monto_total_{}_respuesta'.format(solicitud['ID_Solicitud'])
    key_usar_monto_total = 'usar_monto_total_{}'.format(solicitud['ID_Solicitud'])

    if not (key_usar_monto_total in st.session_state):
        st.session_state[key_usar_monto_total] = True
    if not (key_monto_total in st.session_state):
        st.session_state[key_monto_total] = '{:,.0f}'.format(monto_propuesto_total) 
    for d in solicitud["Datos_Solicitud"]:
        key_monto = 'monto_propuesto_{}_{}'.format(solicitud['ID_Solicitud'], d['Id_Deuda'])
        key_cuotas = 'cuotas_{}_{}'.format(solicitud['ID_Solicitud'], d['Id_Deuda'])
        if not (key_monto in st.session_state):
            st.session_state[key_monto] = '{:,.0f}'.format(d['Monto_Propuesto'])
        if not (key_cuotas in st.session_state):
            st.session_state[key_cuotas] = '{}'.format(d['Num_Cuotas'])

    # Paso 3: Aplicar Lógica de Recálculo basado en los Session States
    if st.session_state[key_usar_monto_total]:
        # Actualizamos el Session State de Monto Propuesto por Deuda basado en el Monto Total
        monto_total = cleanNumber(st.session_state[key_monto_total], default_nan=0.0)
        # Iteramos por las Deudas
        for d in solicitud["Datos_Solicitud"]:
            key_monto = 'monto_propuesto_{}_{}'.format(solicitud['ID_Solicitud'], d['Id_Deuda'])
            # Limpiamos el Monto Propuesto a float
            monto_total_float = cleanNumber(monto_total, default_nan=0.0)
            # Calculamos el Monto Propuesto por Deuda basado en el Monto Total y el Monto Propuesto Original
            porcentaje_propuesto_original = monto_total_float / monto_propuesto_total if monto_propuesto_total > 0 else 0
            monto_propuesto_nuevo = monto_total * porcentaje_propuesto_original
            # Actualizamos el Session State del Monto Propuesto por Deuda
            st.session_state[key_monto] = '{:,.0f}'.format(monto_propuesto_nuevo)
    else:
        # La Actualización del Monto Total se hace basado en la Suma de los Montos Propuestos por Deuda
        monto_total = sum(
            cleanNumber(st.session_state['monto_propuesto_{}_{}'.format(solicitud['ID_Solicitud'], d['Id_Deuda'])], default_nan=0.0) for d in solicitud["Datos_Solicitud"]
            )
        st.session_state[key_monto_total] = '{:,.0f}'.format(monto_total)

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
        usar_monto_total = st.checkbox(
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

    # Paso Siguiente: Mostrar los Inputs por Deuda
    # Se va a Mostrar: Id_Deuda, Banco, Numero_Credito, Monto Propuesto y Cuotas (Si Hay)
    st.markdown("### **Datos por Deuda 🏦**")

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
    with st.expander("**Respuesta por Deuda**", expanded=False):
        if cuotas_input == "Por Deuda":
            colIdDeuda, colNumCredito, colSolicitado, colMontoPropuesto, colCuotasDeuda = st.columns(5, vertical_alignment="center")
        else:
            colIdDeuda, colNumCredito, colSolicitado, colMontoPropuesto = st.columns(4, vertical_alignment="center")

        with colIdDeuda:
            st.markdown("**ID de Deuda**")
        with colNumCredito:
            st.markdown("**Número de Crédito**")
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
                st.code(d['Id_Deuda'], language="text")
            with colNumCredito:
                st.code(d['Numero_Credito'], language="text")
            with colSolicitado:
                st.code(d['Monto_Propuesto'], language="text")
            with colMontoPropuesto:
                key_monto = 'monto_propuesto_{}_{}'.format(solicitud['ID_Solicitud'], d['Id_Deuda'])
                st.text_input(
                    "",
                    key=key_monto,
                    help="Ingrese el monto propuesto para la deuda {}.".format(d['Id_Deuda']),
                    label_visibility="collapsed",
                    disabled = usar_monto_total
                )
            if cuotas_input == "Por Deuda":
                with colCuotasDeuda: # type: ignore
                    key_cuotas = 'cuotas_{}_{}'.format(solicitud['ID_Solicitud'], d['Id_Deuda'])
                    st.number_input(
                        "",
                        value=1,
                        min_value=1,
                        max_value=60,
                        step=1,
                        key=key_cuotas,
                        help="Ingrese el número de cuotas para la deuda {}.".format(d['Id_Deuda']),
                        label_visibility="collapsed",
                    )

        # Siguiente: Mostramos Posibilidad de Agregar Addendums
        with st.expander("**Agregar Addendums a la Solicitud**", expanded=False, icon = "📝"):

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
            for i in range(st.session_state[key_addendums_count]):
                with colBancoAdd:
                    st.selectbox(
                        "",
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
                            "",
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

            with colAddendumAgregar:
                if st.button(
                    label="Agregar Addendum",
                    key="agregar_addendum_{}".format(solicitud['ID_Solicitud']),
                    help="Haga clic para agregar un addendum a la solicitud.",
                    type="primary",
                ):
                    st.session_state[key_addendums_count] += 1

    st.divider()

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
    for i in range(st.session_state[key_addendums_count]):
        addendum_banco = st.session_state['addendums_banco_{}_{}'.format(solicitud['ID_Solicitud'], i)]
        addendum_numero_credito = st.session_state['addendums_numero_credito_{}_{}'.format(solicitud['ID_Solicitud'], i)]
        addendum_monto_actual = cleanNumber(st.session_state['addendums_monto_actual_{}_{}'.format(solicitud['ID_Solicitud'], i)], default_nan=0.0)
        addendum_monto_propuesto = cleanNumber(st.session_state['addendums_monto_propuesto_{}_{}'.format(solicitud['ID_Solicitud'], i)], default_nan=0.0)
        if cuotas_input == "Por Deuda":
            addendum_num_cuotas = int(st.session_state['addendums_cuotas_{}_{}'.format(solicitud['ID_Solicitud'], i)])
        else:
            addendum_num_cuotas = num_coutas_global
        addendums.append({
            "Id_Deuda": "ADD_{}".format(str(i)),
            "Banco": addendum_banco,
            "Numero_Credito": addendum_numero_credito,
            "Monto_Actual": addendum_monto_actual,
            "Monto_Propuesto": addendum_monto_propuesto,
            "Num_Cuotas": addendum_num_cuotas,
        })

    # Añadimos los Addendums a la solicitud_respuesta
    if len(addendums) > 0:
        solicitud_respuesta["Metadata_Solicitud"]["Addendums"] = addendums

    # Añadimos Fecha_Limite_Pago a la solicitud_respuesta si existe, de lo contrario mostrar alerta
    if fecha_limite_pago:
        solicitud_respuesta["Fecha_Limite_Pago"] = fecha_limite_pago
    else:
        st.warning("Debe ingresar una Fecha Límite de Pago para poder finalizar la solicitud.")
        st.stop()

    st.space("small")

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

        # Creamos 2 Columnas: Una para Tipo de Pago y la Otra para Formato de Pago
        colTipoPago, colFormatoPago = st.columns(2, vertical_alignment="top")

        # Como es Acuerdo de Pago u Oferta de Pago, mostramos un Input de Tipo de Pago (Efectivo-Cheque, PSE, Transferencia)
        with colTipoPago:
            tipo_pago = st.radio(
                label="**Método de Pago**",
                options=["Efectivo-Cheque", "PSE", "Transferencia"],
                index=0,
                key="metodo_pago_{}".format(solicitud['ID_Solicitud']),
                help="Seleccione el método de pago para la solicitud.",
            )

            # Guardamos el Método de Pago en la metadata de la solicitud_respuesta
            solicitud_respuesta["Metadata_Solicitud"]["Metodo_Pago"] = tipo_pago

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
                st.warning("No hay un acuerdo de pago disponible para mostrar.")

    # Siguiente: Mostramos el Botón de Finalizar Solicitud
    mostrar_boton_actualizar_solicitudes(solicitud=solicitud_respuesta, pdf_bytes=bytes_acuerdo)

# Función para Mostrar los Datos de una Solicitud
def mostrar_datos_solicitud_ejecutivo(*,solicitud: pd.Series, is_main: bool = False) -> None:
    # Definimos el Nombre del Expander
    expander_name = "**{tipo}** • {aliado} | 📅 `{fecha}` | 📌 `{estado}` | 👤 **Ejecutivo:** {ejecutivo}".format(
        tipo=solicitud["Tipo_Solicitud"],
        fecha=solicitud["Timestamp"].strftime("%Y-%m-%d %H:%M"),
        estado=solicitud["Estado_Solicitud"],
        ejecutivo=solicitud["Ejecutivo"],
        aliado=solicitud["Casa_Cobro"]
    )

    # Creamos el Expander para Mostrar los Datos de la Solicitud
    with st.expander(expander_name, expanded=is_main):
        # Creamos un Espacio pequeño para Separar el Expander del Contenido
        st.space("xxsmall")


        # Creamos 5 Columnas para Mostrar: ID, Monto Total, Persona que Solicita ,Bancos y Cedula
        colID, colMonto, colPersona, colBancos, colCedula = st.columns([1,1,2,2,1],vertical_alignment="center")

        with colID:
            st.metric(
                label="**ID de Solicitud:**", value=solicitud["ID_Solicitud"],
                help = "El ID de la Solicitud que se mantiende de forma interna en el Sistema",
            )

        with colMonto:
            monto_total_solicitud = sum(d['Monto_Propuesto'] for d in solicitud["Datos_Solicitud"])
            st.metric(
                label="**Monto Total:**", value="${:,.2f}".format(monto_total_solicitud),
                help = "El monto total de la solicitud (La Suma de los Valores Propuestos por Deuda) que se va a enviar al Aliado",
            )
        
        with colPersona:
            nombre_nego = obtener_nombre_negociador(email=solicitud["Correo"], full_name=False)
            st.metric(
                label="**Persona que Solicita:**", value=nombre_nego,
                help = "El Nombre del Negociador que realizó la solicitud",
            )

        with colBancos:
            bancos_list = set([d['Banco'] for d in solicitud["Datos_Solicitud"]])
            bancos_str = ", ".join(bancos_list)
            st.metric(
                label="**Bancos:**", value=bancos_str,
                help = "Los Bancos involucrados en la solicitud",
            )

        with colCedula:
            # Primero Creamos una Cedula Limpia:
            cedula_limpia = "{:,.0f}".format(cleanNumber(solicitud["Cedula"])) if pd.notnull(cleanNumber(solicitud["Cedula"])) else "No Brindada"
            # Reemplazamos las comas por puntos
            cedula_limpia = cedula_limpia.replace(",", ".")
            st.metric(
                label="**Cédula:**", value=cedula_limpia,
                help = "El Número de Cedula del titular Solicitado",
            )

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
        st.space("xsmall")
        st.divider()

        # Creamos un Botón para Copiar los Datos de la Solicitud
        colBotonCopy, colInfoCopy = st.columns([1, 5], vertical_alignment="center")
        solicitud_txt = get_solicitud_txt(solicitud=solicitud)
        with colBotonCopy:
            if st_copy_to_clipboard(solicitud_txt, key="copy_solicitud_{}_info".format(solicitud['ID_Solicitud'])):
                st.toast("Datos de la solicitud {} copiados al portapapeles.".format(solicitud['ID_Solicitud']), icon=":material/content_copy:")
        
        with colInfoCopy:
            st.markdown("**Copiar Datos de la Solicitud**")
            st.info("Haga clic en el botón para copiar todos los datos de la solicitud al portapapeles.", icon="ℹ️")

        # Vamos a Crear 6 o 7 Columnas: Boton de Copiar, Id_Deuda, Banco, Numero_Credito, Actualizaciones en Base, Monto Propuesto , Cuotas(Si Hay)
        hay_cuotas = any(d['Num_Cuotas'] > 1 for d in solicitud["Datos_Solicitud"])

        with st.expander("**Detalles de la Solicitud por Deuda**", expanded=False, icon="💰"):

            if hay_cuotas:
                colBtCopy, colIdDeuda, colBanco, colNumCredito, colActualizaciones, colMontoPropuesto, colCuotas = st.columns([1,3,3,3,6,6,3], vertical_alignment="center")
            else:
                colBtCopy, colIdDeuda, colBanco, colNumCredito, colActualizaciones, colMontoPropuesto = st.columns([1,3,3,3,6,6], vertical_alignment="center")

            with colBtCopy:
                st.markdown("**Copiar**")
            with colIdDeuda:
                st.markdown("**ID de Deuda:**")
            with colBanco:
                st.markdown("**Banco:**")
            with colNumCredito:
                st.markdown("**Número de Crédito:**")
            with colActualizaciones:
                st.markdown("**Descuentos en Base:**")
            with colMontoPropuesto:
                st.markdown("**Monto Propuesto:**")
            if hay_cuotas:
                with colCuotas: # type: ignore
                    st.markdown("**Cuotas:**")

            for d in solicitud["Datos_Solicitud"]:

                txt_debt = "ID Deuda: {}\nBanco: {}\nNúmero de Crédito: {}\nMonto Propuesto: ${:,.2f}".format(
                    d['Id_Deuda'], d['Banco'], d['Numero_Credito'], d['Monto_Propuesto']
                )

                with colBtCopy:
                    if st_copy_to_clipboard(txt_debt, key="copy_debt_{}".format(d['Id_Deuda'])):
                        st.toast("Datos de la deuda {} copiados al portapapeles.".format(d['Id_Deuda']), icon=":material/content_copy:")

                with colIdDeuda:
                    st.code(d['Id_Deuda'], language="text")
                with colBanco:
                    st.code(d['Banco'], language="text")
                with colNumCredito:
                    st.code(d['Numero_Credito'], language="text")
                with colActualizaciones:
                    datos_act = get_descuento_en_base(debt=d['Id_Deuda'], original_amount=d['Monto_Actual'])
                    with st.popover("**Descuentos en Base {}**".format(d['Id_Deuda']), icon="👌"):
                        if datos_act:
                            for descuento in datos_act:
                                st.markdown(descuento)
                        else:
                            st.info("No hay descuentos en base para esta deuda.", icon="ℹ️")
                with colMontoPropuesto:
                    st.code("${:,.2f}".format(d['Monto_Propuesto']), language="text")
                if hay_cuotas:
                    with colCuotas: # type: ignore
                        st.code(d['Cuotas'], language="text")

        st.divider()

        # Por Último: Mostramos el Botón para Responder la Solicitud
        # Definimos si la Solicitud se ha respondido o no, para deshabilitar el botón si ya fue respondida
        solicitud_ya_gestionada = (solicitud["Estado_Solicitud"] in ESTADOS_RESPONDIBLES_SOLICITUD)
        # Verificamos que no esté en el BannedManager
        banned_manager = get_banned_manager()
        if banned_manager.is_banned(solicitud["ID_Solicitud"]):
            solicitud_ya_gestionada = True
        # Verificamos que no este a la espera de comité o ilocalizable, ya que no se puede responder hasta que se resuelva el estado
        if (solicitud["Metadata_Solicitud"].get("Estado_Comite", 0) == 1) or (solicitud["Metadata_Solicitud"].get("Estado_Ilocalizable", 0) == 1):
            solicitud_ya_gestionada = True

        st.space("xsmall")

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