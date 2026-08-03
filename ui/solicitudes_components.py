# Estándar usando Pep8
# Librerías de Python
from typing import Optional, Literal
# Librerías de Terceros
import numpy as np
import pandas as pd
from pandera.typing import DataFrame
import streamlit as st
# Librerías Locales
from data.data_models import SolicitudesSchema
from data.data_uploader import update_solicitud_in_google_sheets
from modules.constants import ESTADOS_POSIBLES_SOLICITUD, ESTADOS_PREFINALIZAR_SOLICITUD, ESTADOS_RESPONDIBLES_SOLICITUD
from modules.forms import obtener_nombre_negociador
from modules.gest_sols import generate_acuerdo_pago_pdf, subir_acuerdo_pago_a_google_drive
from modules.classes import get_banned_manager
from utils.helpers_general import cleanNumber, getBDDaysDiffFloat_vectorized

# Función para Reiniciar los Filtros de Solicitudes en el Session State
def reiniciar_filtros_solicitudes(method: Literal['reset','basic']) -> None:
    """
    Reinicia los filtros de solicitudes en el estado de la sesión.
    Esta función elimina las claves relacionadas con los filtros de solicitudes del estado de la sesión.
    """
    # Lista de claves a reiniciar del Session State
    keys_to_remove = [
        "tipo_solicitud_gestion_input",
        "aliado_solicitud_gestion_input",
        "estado_solicitud_gestion_input",
        "ejecutivo_solicitud_gestion_input",
        "persona_solicitud_gestion_input",
        "banco_solicitud_gestion_input",
        "id_solicitud_gestion_input",
        "cedula_solicitud_gestion_input",
        "id_deuda_solicitud_gestion_input",
    ]
    for key in keys_to_remove:
        st.session_state[key] = None
    # Ahora Cambiamos a False el Expander de Filtros Auxiliares si es que se reinicia todo
    if method == 'reset':
        st.session_state['expander_filtros_solicitudes_gestiones'] = False
    # Si es Básico, pasamos estado_solicitud_gestion_input a "Sin Tocar"
    if method == 'basic':
        st.session_state['estado_solicitud_gestion_input'] = "Sin Tocar"

    # Cambiam el Session_State de 

# Función para Mostrar los Filtros Generales de una Solicitud
def mostrar_filtros_generales_solicitud(*, solicitudes_df: DataFrame[SolicitudesSchema]) -> DataFrame[SolicitudesSchema]:

    solicitudes_copy = solicitudes_df.copy()  # Creamos una copia del DataFrame para no modificar el original

    # Vamos a Crear 3 Columnas: Boton de Reinicio Total, Boton de Reinicio Basico y Boton de Recomendado
    colResetTotal, colResetBasico, colRecomendado = st.columns(3)

    with colResetTotal:
        st.button(
            label="Reiniciar Filtros (Total)",
            key="reiniciar_filtros_solicitudes_total",
            on_click=reiniciar_filtros_solicitudes,
            args=('reset',),
            help="Haga clic para reiniciar todos los filtros de solicitudes.",
        )

    with colResetBasico:
        usar_basico = st.button(
            label="Reiniciar Filtros (Básico)",
            key="reiniciar_filtros_solicitudes_basico",
            on_click=reiniciar_filtros_solicitudes,
            args=('basic',),
            help="Haga clic para reiniciar los filtros de solicitudes de forma básica.",
        )

    with colRecomendado:
        usar_recomendado = st.checkbox(
            label="Filtros Recomendados",
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
    with st.expander("Filtros Auxiliares", expanded=False, key="expander_filtros_solicitudes_gestiones"):
        colPersona, colBanco, colID, colCedula, colIdDeuda = st.columns(5)

        with colPersona:
            persona_solicitud = st.selectbox(
                label="**Persona que Solicita (Correo)**",
                options=["Todos"] + list(solicitudes_df["Correo"].unique()),
                index=0,
                key="persona_solicitud_gestion_input",
                help="Seleccione el correo de la persona que solicita",
                disabled = usar_recomendado,
            )

        with colBanco:
            banco_solicitud = st.multiselect(
                label="**Banco**",
                options= ["Todos"] + list(np.unique([d['Banco'] for d in solicitudes_df['Datos_Solicitud']])),
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

    modo_expandido = st.session_state.get('expander_filtros_solicitudes_gestiones', False)

    if persona_solicitud != "Todos" and modo_expandido:
        solicitudes_df = solicitudes_df[solicitudes_df["Correo"] == persona_solicitud]

    if banco_solicitud != "Todos" and modo_expandido:
        solicitudes_df = solicitudes_df[solicitudes_df["Datos_Solicitud"].apply(lambda x: any((d['Banco'] in banco_solicitud) for d in x))]

    if id_solicitud != "Todos" and modo_expandido:
        solicitudes_df = solicitudes_df[solicitudes_df["ID_Solicitud"] == id_solicitud]

    if cedula_solicitud != "Todos" and modo_expandido:
        solicitudes_df = solicitudes_df[solicitudes_df["Cedula"] == cedula_solicitud]

    if id_deuda_solicitud != "Todos" and modo_expandido:
        solicitudes_df = solicitudes_df[solicitudes_df["Ids_Deuda"].str.contains(id_deuda_solicitud)]

    # Paso 4: Quitar los IDs de Solicitudes que ya fueron respondidas y están en el BannedManager
    if usar_recomendado or usar_basico:
        banned_manager = get_banned_manager()
        solicitudes_df = solicitudes_df[~(solicitudes_df["ID_Solicitud"].apply(banned_manager.is_banned))]
        solicitudes_copy = solicitudes_copy[~(solicitudes_copy["ID_Solicitud"].apply(banned_manager.is_banned))]

    # Si es Recomendado se realizan filtros aparte
    if usar_recomendado:
        # Ahora Aplicamos un reset de los filtros para que se vean reflejados los cambios
        st.session_state['expander_filtros_solicitudes_gestiones'] = False
        # Siguiente: Dejar en Solicitudes:
        # Estados: Sin Tocar, Bajo Comité (Con estado comite 1), Titular Ilocalizable (Con estado ilocalizable 1)
        maskSinTocar = solicitudes_copy["Estado_Solicitud"] == "Sin Tocar"
        maskBajoComite = solicitudes_copy["Metadata_Solicitud"].apply(lambda x: x.get("Estado_Comite", 0)  == 1) & (solicitudes_copy["Estado_Solicitud"] == "Bajo Comité")
        maskTitularIlocalizable = solicitudes_copy["Metadata_Solicitud"].apply(lambda x: x.get("Estado_Titular_Ilocalizable", 0) == 1) & (solicitudes_copy["Estado_Solicitud"] == "Titular Ilocalizable")
        solicitudes_df = solicitudes_copy[maskSinTocar | maskBajoComite | maskTitularIlocalizable].copy()

        # Siguiente: Crear Copia con Columna Prioridad
        # Paso 1: Crear Columna Fecha_Hoy
        calc_df = solicitudes_df.assign(Fecha_Hoy=pd.Timestamp.now('America/Bogota').tz_localize(None))
        # Paso 2: Crear Columna de Diferencia de Días Vectorizada
        calc_df["Diferencia_Dias"] = getBDDaysDiffFloat_vectorized(calc_df["Fecha_Solicitud"], calc_df["Fecha_Hoy"])
        # Paso 3: X2 a la Diferencia_Dias si Tipo_Pago == 'Crédito'
        calc_df["Diferencia_Dias"] *= np.where(calc_df["Tipo_Pago"] == "Crédito", 2, 1)
        # Paso 4: Usar np.argsort para obtener los índices ordenados por Diferencia_Dias de mayor a menor
        sorted_indices = np.argsort((calc_df["Diferencia_Dias"]* -1).to_numpy())
        # Paso 5: Aplicar este orden a solicitudes_df para obtener el DataFrame final ordenado
        solicitudes_df = solicitudes_df.iloc[sorted_indices]
    else:
        # Ordenamos los más antiguos primero
        solicitudes_df = solicitudes_df.sort_values(by="Fecha_Solicitud", ascending=True)

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
        )

    with colBoton:
        actualizar_solicitud = st.button(
            label="Finalizar Solicitud",
            key="finalizar_solicitud_{}".format(solicitud['ID_Solicitud']),
        )
    if actualizar_solicitud:
        with st.spinner("Subiendo Solicitud a Google Sheets..."):
            # Actualizamos la Solicitud en Google Sheets
            success = update_solicitud_in_google_sheets(solicitud)
            # Subimos el Acuerdo de Pago si es necesario
            if pdf_bytes is not None:
                file_id = subir_acuerdo_pago_a_google_drive(pdf_bytes=pdf_bytes, solicitud_info=solicitud)
                success = success and bool(file_id)
        if success:
            st.toast("Solicitud Finalizada y Actualizada a Google Sheets con Éxito.",icon="✅")
            # Agregamos el ID de la Solicitud al BannedManager para que no se pueda volver a responder
            banned_manager = get_banned_manager()
            banned_manager.ban(solicitud["ID_Solicitud"])
            st.rerun()
        else:
            st.error("Error al Subir la Solicitud a Google Sheets o el Acuerdo de Pago a Google Drive. Por favor, intente nuevamente.")

# Función para Abrir el Dialogo de Respuesta de una Solicitud
@st.dialog("🗒️ Respuesta a Solicitud",dismissible=False,width="large")
def dialog_respuesta_solicitud(*, solicitud: pd.Series) -> None:
    # Creamos una Copia de la solicitud que será la respuesta
    solicitud_respuesta = solicitud.copy()

    st.markdown("### **Información de la Solicitud 🥸**")
    # Paso 1: Escogencia de Aliado, Estado de Solicitud y si Fue llamada
    colAliado, colEstado, colLlamada = st.columns(3)

    with colAliado:
        aliado_final = st.selectbox(
            label="**Aliado - Casa de Cobro**",
            options=list(st.session_state["aliados_dict"].keys()),
            index=list(st.session_state["aliados_dict"].keys()).index(solicitud["Casa_Cobro"]),
            key="aliado_solicitud_respuesta_input_{}".format(solicitud['ID_Solicitud']),
        )

    with colEstado:
        estado_final = st.selectbox(
            label="**Estado de Solicitud**",
            options=[e for e in ESTADOS_POSIBLES_SOLICITUD if e not in ["Sin Tocar","Vencida"]],
            index=None,
            key="estado_solicitud_respuesta_input_{}".format(solicitud['ID_Solicitud']),
        )

    with colLlamada:
        llamada_final = st.checkbox(
            label="**¿Fue Llamada?**",
            value=False,
            key="llamada_solicitud_respuesta_input_{}".format(solicitud['ID_Solicitud']),
        )

    # Añadimos campo para poner comentarios de la Solicitud
    comentario_final = st.text_area(
        label="**Comentarios de la Solicitud**",
        value="",
        key="comentario_solicitud_respuesta_input_{}".format(solicitud['ID_Solicitud']),
        help="Ingrese cualquier comentario adicional sobre la solicitud.",
    )

    # Verificamos que ambos esten seleccionados para habilitar el botón de enviar respuesta
    if not (aliado_final and estado_final):
        st.info("Selecciona el Aliado Final y el Estado de Solicitud")
        st.stop()

    # Siguiente: Actualizamos la solicitud_respuesta con los valores seleccionados
    solicitud_respuesta["Casa_Cobro"] = aliado_final
    solicitud_respuesta["Estado_Solicitud"] = estado_final
    solicitud_respuesta["Metadata_Solicitud"]["Fue_Llamada"] = llamada_final
    # Si hay Comentario lo Actualizamos
    if comentario_final:
        solicitud_respuesta["Metadata_Solicitud"]["Comentario_Ejecutivo"] = comentario_final

    # Siguiente: Verificaciones antes de Seguir con Solicitud
    # Actualizamos Bajo Comité y Titular Ilocalizable
    if estado_final == "Bajo Comité":
        solicitud_respuesta["Metadata_Solicitud"]["Estado_Comite"] = 1
    if estado_final == "Titular Ilocalizable":
        solicitud_respuesta["Metadata_Solicitud"]["Estado_Titular_Ilocalizable"] = 1

    # Ahora: Mostramos Botón de Finalizar que el Estado este en ESTADOS_PREFINALIZAR_SOLICITUD
    if estado_final in ESTADOS_PREFINALIZAR_SOLICITUD:
        st.success("La solicitud está en un estado que permite finalizarla.")
        # Mostramos el Botón para Finalizar la Solicitud
        mostrar_boton_actualizar_solicitudes(solicitud=solicitud_respuesta)
        st.stop()

    # En caso que no (es Exitosa), se requiere poner el Monto por Deuda, Cuotas y Fecha Límite de Pago
    # Paso 1: Escoger-> Fecha Limite de Pago, Monto Total, Checkbox de usar Monto Total y SelectBox para cuotas
    colFechaLimite, colMontoTotal, colUsarMontoTotal, colCuotas = st.columns(4)

    # Paso 2: Inicializar Valores en el Session_State por Primera Vez
    monto_propuesto_total = sum(d['Monto_Propuesto'] for d in solicitud["Datos_Solicitud"])
    key_monto_total = 'monto_total_{}_respuesta'.format(solicitud['ID_Solicitud'])
    key_usar_monto_total = 'usar_monto_total_{}'.format(solicitud['ID_Solicitud'])

    if not (key_usar_monto_total in st.session_state):
        st.session_state[key_usar_monto_total] = True
    if not (key_monto_total in st.session_state):
        st.session_state[key_monto_total] = '{:,.2f}'.format(monto_propuesto_total) 
    for d in solicitud["Datos_Solicitud"]:
        key_monto = 'monto_propuesto_{}_{}'.format(solicitud['ID_Solicitud'], d['Id_Deuda'])
        key_cuotas = 'cuotas_{}_{}'.format(solicitud['ID_Solicitud'], d['Id_Deuda'])
        if not (key_monto in st.session_state):
            st.session_state[key_monto] = '{:,.2f}'.format(d['Monto_Propuesto'])
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
            st.session_state[key_monto] = '{:,.2f}'.format(monto_propuesto_nuevo)
    else:
        # La Actualización del Monto Total se hace basado en la Suma de los Montos Propuestos por Deuda
        monto_total = sum(
            cleanNumber(st.session_state['monto_propuesto_{}_{}'.format(solicitud['ID_Solicitud'], d['Id_Deuda'])], default_nan=0.0) for d in solicitud["Datos_Solicitud"]
            )
        st.session_state[key_monto_total] = '{:,.2f}'.format(monto_total)

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
            label="**Monto Total**",
            key=key_monto_total,
            help="Ingrese el monto total propuesto para la solicitud. Este monto se distribuirá proporcionalmente entre las deudas.",
        )

    with colUsarMontoTotal:
        usar_monto_total = st.checkbox(
            label="**Distribuir el Monto Total**",
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
            step=1,
            key="num_cuotas_global_{}".format(solicitud['ID_Solicitud']),
            help="Ingrese el número de cuotas para todas las deudas.",
        )

    if cuotas_input == "Por Deuda":
        colIdDeuda, colNumCredito, colSolicitado, colMontoPropuesto, colCuotasDeuda = st.columns(5)
    else:
        colIdDeuda, colNumCredito, colSolicitado, colMontoPropuesto = st.columns(4)

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
            st.code(d['Num_Credito'], language="text")
        with colSolicitado:
            st.code(d['Monto_Propuesto'], language="text")
        with colMontoPropuesto:
            key_monto = 'monto_propuesto_{}_{}'.format(solicitud['ID_Solicitud'], d['Id_Deuda'])
            st.text_input(
                "",
                key=key_monto,
                help="Ingrese el monto propuesto para la deuda {}.".format(d['Id_Deuda']),
                label_visibility="collapsed",
            )
        if cuotas_input == "Por Deuda":
            with colCuotasDeuda: # type: ignore
                key_cuotas = 'cuotas_{}_{}'.format(solicitud['ID_Solicitud'], d['Id_Deuda'])
                st.text_input(
                    "",
                    key=key_cuotas,
                    help="Ingrese el número de cuotas para la deuda {}.".format(d['Id_Deuda']),
                    label_visibility="collapsed",
                )

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
            "Monto_Propuesto": monto_propuesto,
            "Num_Cuotas": num_cuotas,
        })

    # Agreagamos el JSON_Respuesta a la solicitud_respuesta
    solicitud_respuesta["JSON_Respuesta"] = json_respuesta

    # Añadimos Fecha_Limite_Pago a la solicitud_respuesta si existe, de lo contrario mostrar alerta
    if fecha_limite_pago:
        solicitud_respuesta["Fecha_Limite_Pago"] = fecha_limite_pago
    else:
        st.warning("Debe ingresar una Fecha Límite de Pago para poder finalizar la solicitud.")
        st.stop()

    # Siguiente: Añadir el Input de Pago Total Obligatorio (Checkbox), solo si existe más de una deuda
    if len(json_respuesta) > 1:
        colCheckbox, colInfo = st.columns([1, 4])
        with colCheckbox:
            pago_total_obligatorio = st.checkbox(
                label="**Pago Total Obligatorio**",
                value=False,
                key="pago_total_obligatorio_{}".format(solicitud['ID_Solicitud']),
                help="Seleccione esta opción si el pago total es obligatorio para la solicitud.",
            )
            # Guardamos el Pago Total Obligatorio en la solicitud_respuesta
            solicitud_respuesta['Metadata_Solicitud']["Pago_Total_Obligatorio"] = pago_total_obligatorio
        with colInfo:
            st.info("El Pago Obligatorio significa que se debe aplicar el pago para todas la deudas")

    # Siguiente: Si es Validación, mostrar el Botón de Finalizar Solicitud
    if solicitud["Tipo_Solicitud"] == "Validación":
        mostrar_boton_actualizar_solicitudes(solicitud=solicitud_respuesta)
        st.stop()

    # Creamos 2 Columnas: Una para Tipo de Pago y la Otra para Formato de Pago
    colTipoPago, colFormatoPago = st.columns(2)

    # Como es Acuerdo de Pago u Oferta de Pago, mostramos un Input de Tipo de Pago (Efectivo-Cheque, PSE, Transferencia)
    with colTipoPago:
        tipo_pago = st.radio(
            label="**Tipo de Pago**",
            options=["Efectivo-Cheque", "PSE", "Transferencia"],
            index=0,
            key="tipo_pago_{}".format(solicitud['ID_Solicitud']),
            help="Seleccione el tipo de pago para la solicitud.",
        )

        # Guardamos el Tipo de Pago en la solicitud_respuesta
        solicitud_respuesta["Tipo_Pago"] = tipo_pago

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
        bytes_acuerdo = generate_acuerdo_pago_pdf(solicitud_info=solicitud_respuesta)
        # Si no hay bytes_acuerdo, mostramos un error y detenemos la ejecución
        if (bytes_acuerdo is None) or (len(bytes_acuerdo) == 0):
            st.error("Error al generar el PDF del acuerdo de pago. Por favor, intente nuevamente creelo manualmente.")
            st.stop()

    # Siguiente: Mostramos el Botón de Finalizar Solicitud
    mostrar_boton_actualizar_solicitudes(solicitud=solicitud_respuesta, pdf_bytes=bytes_acuerdo)


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

        # Por Último: Mostramos el Botón para Responder la Solicitud
        # Definimos si la Solicitud se ha respondido o no, para deshabilitar el botón si ya fue respondida
        responded_solicitud = (solicitud["Estado_Solicitud"] in ESTADOS_RESPONDIBLES_SOLICITUD)
        # Verificamos que no esté en el BannedManager
        banned_manager = get_banned_manager()
        if banned_manager.is_banned(solicitud["ID_Solicitud"]):
            responded_solicitud = True
        # Verificamos que no este a la espera de comité o ilocalizable, ya que no se puede responder hasta que se resuelva el estado
        if (solicitud["Metadata_Solicitud"].get("Estado_Comite", 0) == 1) or (solicitud["Metadata_Solicitud"].get("Estado_Ilocalizable", 0) == 1):
            responded_solicitud = True

        st.space("xxsmall")

        # Creamos Dos Columnas: Una para Informacion y otra para el Boton
        colInfo, colBoton = st.columns([4, 1])

        with colInfo:
            if responded_solicitud:
                st.info("Esta solicitud ya ha sido respondida o está en espera de comité/ilocalizable, por lo que no se puede responder nuevamente.")
            else:
                st.info("Puede responder esta solicitud haciendo clic en el botón de la derecha. Esto abrirá un diálogo donde podrá ingresar su respuesta.")

        with colBoton:
            st.button(
                label="Responder Solicitud",
                key="responder_solicitud_{}".format(solicitud['ID_Solicitud']),
                on_click=dialog_respuesta_solicitud,
                args=(solicitud,),
                disabled=responded_solicitud,
                help="Haga clic para responder la solicitud. Esta acción abrirá un diálogo donde podrá ingresar su respuesta.",
        )