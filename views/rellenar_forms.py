# Estándar usando Pep8
# Librerías de Python
import json
# Librerías de Terceros
import streamlit as st
import pandas as pd
# Librerías Propias
from data.data_uploader import upload_form_response_to_google_sheets
from modules.forms import cumple_condicion_actualizacion_deudas, mostrar_como_subir_solicitud_aliados_diferentes, obtener_aliado_en_base, obtener_deudas_activas_con_retry, obtener_referencia_por_deuda, obtener_ultima_actualizacion_deudas  # pyright: ignore[reportAttributeAccessIssue]
from ui.forms_components import mostrar_alertas_masivas_deudas, mostrar_monto_recomendado, mostrar_resumen_solicitud, mostrar_seleccion_deudas, poner_monto_por_deuda
from utils.helpers_general import cleanNumber

# Carga de Información Necesaria para el Formulario
# Se Necesita:
# Aliados Actuales
aliadosDict = st.session_state['aliados_dict']
# Saldos y Por Cobrar
saldosDict = st.session_state['saldos_dict']
# Addendums
addsDF = st.session_state['addendums_df']
# Deudas ya Liquidadas
debtsLiq = st.session_state['liquidations_set']
# Actualizaciones Masivas
masivasDF = st.session_state['masivas_df']
# Configuración del App
appConfig = st.session_state['app_config_dict']


# Inicializamos las Deudas Seleccionadas en el Session State si no Existe
if 'deudas_seleccionadas' not in st.session_state:
    st.session_state['deudas_seleccionadas'] = []


st.title("🗒️ Nuevo Formulario de Alianzas")
st.divider()

st.subheader("Referencia del Cliente")
# -- Campos del Formulario

# Referencia y Id_Deuda
cols = st.columns([1, 1])

# Referencia del Cliente
with cols[0]:
    referencia_cliente = st.number_input("Referencia del Cliente", help="Ingrese la referencia del cliente, Ejemplo: 3007083770", format="%d", step=1, min_value=0)

# Deuda Representante del Cliente
with cols[1]:
    id_deuda = st.number_input("Id_Deuda del Cliente, Ejemplo: 123456789",
    help="Ingrese el Id de alguna deuda del cliente (Solo válido cuando la Referencia no se encuentra)",
    format="%d", step=1, min_value=0,
    disabled = (not st.session_state.get('id_rep_needed',False)),
    )

# Validamos la Referencia
if not referencia_cliente:
    st.error("La referencia del cliente es obligatoria")
    st.stop()

# Limpiamos la Referencia y el id_deuda
referencia_cliente = str(referencia_cliente).strip() if referencia_cliente else ''
id_deuda = str(id_deuda).strip().replace('.0','') if id_deuda else ''

# Paso Siguiente: Obtener las Deudas Activas y la Última Actualización
# --- Deudas Activas ---
deudas_activas_df = obtener_deudas_activas_con_retry(referencia=referencia_cliente)

# Si ésta vácio entonces pasamos al segundo fallback: -> Buscar Referencia por Id_Deuda
if deudas_activas_df.empty:
    # Si el Id_Deuda es Vácio entonces no podemos hacer nada
    if not id_deuda and not st.session_state.get('id_rep_needed', False):
        st.session_state['id_rep_needed'] = True
        st.info("No se encontraron deudas activas para la referencia proporcionada. Por favor, ingrese algún Id Deuda de la Referencia para continuar.")
        st.rerun()

    if not id_deuda:
        st.info("Ingresa una deuda activa para buscar la Referencia del cliente. (La otorgada no tiene deudas activas)", icon = "ℹ️")
        st.stop()

    # Obtenemos la Referencia por Id_Deuda
    ref_antigua = referencia_cliente
    referencia_cliente = obtener_referencia_por_deuda(deuda=id_deuda)

    # Si la Referencia sigue siendo Vació entonces no podemos hacer nada
    if not referencia_cliente and not st.session_state.get('id_rep_needed', False):
        st.session_state['id_rep_needed'] = True
        st.error("No se encontró una referencia asociada al Id_Deuda proporcionado.")
        st.rerun()
        st.stop()

    # Obtenemos las Deudas Activas con la Referencia Obtenida
    deudas_activas_df = obtener_deudas_activas_con_retry(referencia=referencia_cliente)
else:
    ref_antigua = referencia_cliente

# Quitamos de las Deudas Activas las que ya han sido Liquidadas
deudas_activas_df = deudas_activas_df[~deudas_activas_df['Id_Deuda'].isin(debtsLiq)]

# Si el DF sigue siendo vacío entonces no podemos hacer nada
if deudas_activas_df.empty:
    st.error("No se encontraron deudas activas para la referencia proporcionada.")
    st.stop()

# Volvemos a dejar el Id_Deuda como intocable para que el usuario no lo cambie
st.session_state['id_rep_needed'] = False


# Verificamos que exista una Última Actualización para las Deudas Activas
ultima_actualizacion = obtener_ultima_actualizacion_deudas(debt_ids=deudas_activas_df['Id_Deuda'].tolist(), user_email=st.session_state.get('user_email', ''))
# Veriticamos que satisface la Condición de Mínimo de Días Hábiles para Actualización
cumple_condicion, dias_habiles_diff = cumple_condicion_actualizacion_deudas(ultima_actualizacion=ultima_actualizacion)
user = st.session_state['user_obj']
es_admin = (user.role == 'admin') and (not st.session_state.get('simulate_negotiator', True))


st.info('ℹ️Última Actualización de las Deudas Activas: {} (Hace {:.2f} días hábiles)'.format(
    ultima_actualizacion.strftime('%Y-%m-%d') if ultima_actualizacion else 'No Disponible',
    dias_habiles_diff,
))
if ((not cumple_condicion) and (not es_admin)) and not (st.secrets.get('LET_WITHOUT_UPDATE', False)):
    st.warning("La última actualización de las deudas activas fue hace {:.2f} días hábiles, lo cual es menor al mínimo necesario de {} días hábiles para poder continuar con el llenado del formulario.".format(
        dias_habiles_diff, appConfig['MIN_NECESSARY_DAYS_FOR_DEBT_UPDATE']
    ))
    st.info('Debes Actualizar alguna de las deudas activas antes de poder continuar con el llenado del formulario.')
    # Añadimos un Botón de Reintentar
    if st.button("**Reintentar**",
            key="reintentar_actualizacion_deudas",
            help="Presione este botón para reintentar la actualización de las deudas activas",
            icon="🔄",
            type="primary",
            width="stretch",
        ):
        obtener_ultima_actualizacion_deudas.clear()
        st.rerun()
    st.stop()

# Verificamos si tiene algún Addendum Activo
addendum_activo = addsDF[(addsDF['Referencia'] == referencia_cliente)]
if not addendum_activo.empty:
    # Añadimos los Addendums a las Deudas Activas
    deudas_activas_df = pd.concat([deudas_activas_df, addendum_activo[['Id_Deuda', 'Cedula', 'Banco', 'PaB_Origen','PaB_PL']]], ignore_index=True)

# Mostramos las Características del Cliente (Saldos, Por Cobrar y Pricing)
with st.expander("Características del Cliente"):
    colSaldos, colPorCobrar, colPricing = st.columns(3)

    # Definimos el Saldo, Por Cobrar y Pricing
    saldoAntiguo = saldosDict['Saldos'][ref_antigua]
    saldoNuevo = saldosDict['Saldos'][referencia_cliente]
    saldoReal = max(saldoAntiguo, saldoNuevo)
    porCobrarAntiguo = saldosDict['PorCobrar'][ref_antigua]
    porCobrarNuevo = saldosDict['PorCobrar'][referencia_cliente]
    porCobrarReal = max(porCobrarAntiguo, porCobrarNuevo)

    pricing = deudas_activas_df['Pricing'].max()

    # Guardamos esta Información en los Session_State si es Necesario
    if referencia_cliente != st.session_state.get('ultima_referencia', ''):
        st.session_state['saldo_real'] = saldoReal
        st.session_state['por_cobrar_real'] = porCobrarReal
        st.session_state['pricing'] = '{:.2f}%'.format(pricing * 100)

        # Reiniciamos las Deudas Seleccionadas si la Referencia Cambia
        st.session_state['deudas_seleccionadas'] = []
        deudas_seleccionadas = []

    # Ahora los Vamos Poniendo como Inputs en el Formulario
    with colSaldos:
        st.number_input("**Saldo del Cliente**",
            disabled=False, 
            format="%0.0f",
            help="Saldo del Cliente según lo que se reporta en SALDOS",
            key = "saldo_real",
            icon="💰",
        )
    with colPorCobrar:
        st.number_input("**Por Cobrar del Cliente**",
            disabled=False, 
            format="%0.0f",
            help="Por Cobrar del Cliente según lo que se reporta en SALDOS",
            key = "por_cobrar_real",
            icon="💸",
        )
    with colPricing:
        st.text_input("**Pricing del Cliente**",
            disabled=True,
            help="Pricing del Cliente según lo que se reporta en la Base de Datos",
            key = "pricing",
            icon="📈",
        )

# Añadimos un Subheader para la Selección de Deudas
st.divider()
st.subheader("Selección de Deudas Activas")

# Mostramos la Selección de Deudas
deudas_seleccionadas = mostrar_seleccion_deudas(deudas_activas_df=deudas_activas_df) # type: ignore

# Guardamos la Referencia como Ultima en el Session_State
st.session_state['ultima_referencia'] = referencia_cliente

# Filtramos el DF para dejar solo las Deudas Seleccionadas
deudas_seleccionadas_df = deudas_activas_df[deudas_activas_df['Id_Deuda'].isin(deudas_seleccionadas)]

# Dado que añadimos info de los Addendums reescribimos la Columna Pricing con el valor máximo de Pricing entre las Deudas Seleccionadas
deudas_seleccionadas_df['Pricing'] = deudas_activas_df['Pricing'].max()

# Verificamos que al menos una Deuda esté Seleccionada
if not deudas_seleccionadas:
    st.warning("Debe seleccionar al menos una deuda activa para poder continuar con el llenado del formulario.")
    st.stop()

# Siguiente Paso: Seleccionar Tipo de Solicitud y el Aliado
st.divider()
st.subheader("🫡Selección de Tipo de Solicitud y Aliado")

col1, col2 = st.columns(2)

with col1:
    tipo_solicitud = st.radio(
        "**Tipo de Solicitud**",
        ["**Validación**","**Acuerdo de Pago**","**Oferta de Acuerdo**"],
        captions=[
            '**Validación**: Averiguar descuento y/o Casa de Cobro',
            '**Acuerdo de Pago**: Negociar un acuerdo de pago con el cliente',
            '**Oferta de Acuerdo**: Ofertar un valor de pago, si se acepta, se genera un acuerdo de pago',
        ],
        index=None,
        help="Seleccione el tipo de solicitud que desea realizar",
    )
with col2:
    aliado_seleccionado = st.selectbox(
        "**Aliado - Casa de Cobro**",
        options=list(aliadosDict.keys()),
        help="Seleccione el aliado con el que desea realizar la solicitud",
        index=None,
    )

# Verificamos que ambos tengan una selección válida
if not tipo_solicitud or not aliado_seleccionado:
    st.warning("Selecciona ambas opciones para continuar con el formulario 😁")
    st.stop()

# Limpiamos el Tipo de Solicitud Quitando los Asteriscos
tipo_solicitud = tipo_solicitud.replace('*','').strip()

st.divider()

# Mostramos la Selección de los Montos Propuestos por Deuda
info_completa_deudas = poner_monto_por_deuda(deudas_activas_df=deudas_seleccionadas_df) # type: ignore

# Mostramos el Monto Recomendado para la Solicitud (Si es Validacion u Oferta de Acuerdo)
if tipo_solicitud in ['Validación', 'Oferta de Acuerdo']:
    mostrar_monto_recomendado(
        referencia=referencia_cliente,
        deudas=deudas_seleccionadas,
        pricing=deudas_seleccionadas_df['Pricing'].max(),
        deudas_seleccionadas_df=deudas_seleccionadas_df, # type: ignore
    )

deudas_info = {deuda: cleanNumber(st.session_state.get(f'monto_propuesto_{deuda}', 0)) for deuda in deudas_seleccionadas}

# Ajuste: Cuando es Directo Base, se busca en las Deudas Masivas
masivas_locales = masivasDF[masivasDF['Id_Deuda'].isin(deudas_seleccionadas)]

if aliado_seleccionado.lower().strip() == 'directo base':
    # Alerta de Modificación 1: Todas las Deudas Seleccionadas tienen un Descuento en Base
    if len(masivas_locales) < len(deudas_seleccionadas):
        st.warning("No todas las deudas seleccionadas tienen un descuento en base.", icon="⚠️")
        st.stop()

    if es_admin:
        st.dataframe(masivas_locales)

    # Alerta de Modificación 2: Todas las Deudas tienen Descuento en Base para un Mismo Aliado
    if len(masivas_locales['Casa_Cobro'].unique()) > 1:
        # Creamos una Lista de los Aliados Posibles
        aliados_posibles = []

        for aliado in masivas_locales['Casa_Cobro'].unique():
            deudas_aliado = set(masivas_locales[masivas_locales['Casa_Cobro'] == aliado]['Id_Deuda'].tolist())
            if all((deuda in deudas_aliado for deuda in deudas_seleccionadas)):
                aliados_posibles.append(aliado)

        if not aliados_posibles:
            st.warning("No todas las deudas seleccionadas tienen un descuento en base para un mismo aliado.", icon="⚠️")
            # Mostramos como Subir la Solicitud dadas las diferentes deudas
            mostrar_como_subir_solicitud_aliados_diferentes(
                ml = masivas_locales,
                es_admin = es_admin,
            )
            st.stop()

        if es_admin:
            st.info("Los Aliados Posibles para las Deudas Seleccionadas son: ({})".format(", ".join(aliados_posibles)), icon="ℹ️")

        # Ahora Cambiamos el Aliado al Nuevo
        if len(aliados_posibles) == 1:
            aliado_seleccionado = aliados_posibles[0]
        else:
            aliado_seleccionado = obtener_aliado_en_base(deudas=deudas_seleccionadas, aliados_posibles=aliados_posibles)


    else:
        aliado_seleccionado = masivas_locales['Casa_Cobro'].iloc[0]

    if es_admin:
        st.info(f"Se ha cambiado automáticamente el aliado seleccionado a **{aliado_seleccionado}** ya que todas las deudas seleccionadas tienen un descuento en base para este aliado.", icon="ℹ️")

    # Verificación última: Que el Aliado este en la Lista de Aliados Posibles
    if aliado_seleccionado not in aliadosDict:
        st.warning("Error de Selección de Aliado Interna, manda DM sobre la Referencia y Deudas que intentaste", icon="⚠️")
        st.stop()

    aliado_cambiado = True
else:
    aliado_cambiado = False

# --- Siguiente: Alertas y Verificaciones ---

# Alerta 1: Descuento en Base y Aliado Brinda Descuento Máximo

if not masivas_locales.empty:
    aliado_brinda_descuento_maximo = aliadosDict[aliado_seleccionado].brinda_maximo_descuento()
    if aliado_brinda_descuento_maximo:
        st.warning("El aliado seleccionado brinda descuento máximo, por lo que una oferta de mejora de descuento puede no ser aceptada. Se recomienda revisar las condiciones de la solicitud antes de continuar.")

# Alerta 2: Pago Obligatorio de Solicitud (Para Validación)
if tipo_solicitud == 'Validación':
    aliado_brinda_pago_obligatorio = aliadosDict[aliado_seleccionado].pagar_co_obligatorio()
    if aliado_brinda_pago_obligatorio:
        st.warning("Dadas las Características del Aliado seleccionado, se requiere el pago obligatorio en caso de realizarse la validación.")

# Alerta 3: Verificar si el Aliado da Posibilidades de Cuotas
# Verificamos si Permite Cuotas
aliado_brinda_cuotas = aliadosDict[aliado_seleccionado].permite_cuotas()
# Verificamos si en la Solciitud se realiza una opción a cuotas
solicitud_a_cuotas = any(deuda_info['Num_Cuotas'] > 1 for deuda_info in info_completa_deudas)
if not aliado_brinda_cuotas and solicitud_a_cuotas:
    st.warning("El aliado seleccionado no brinda la posibilidad de cuotas, por lo que se recomienda revisar las condiciones de la solicitud antes de continuar.")

# Alerta 4: Verificacion de Descuentos en Base
if (not masivas_locales.empty) and tipo_solicitud in ['Validación', 'Oferta de Acuerdo']:
    #  Verificamos por cada Deuda si se cumple
    avanzar_proceso = mostrar_alertas_masivas_deudas(deudas_info_list=info_completa_deudas)
else:
    avanzar_proceso = True

if not avanzar_proceso:
    st.error("La(s) Deuda(s) seleccionada(s) ya tienen una oferta de pago menor a la Solicitada")
    st.stop()

# Alerta 5: Verificar que los Montos Propuestos no sean 0 en alguna de las Deudas
for deuda_info in info_completa_deudas:
    if deuda_info['Monto_Propuesto'] <= 0:
        st.error(f"El monto propuesto para la deuda {deuda_info['Id_Deuda']} es menor o igual a 0, lo cual no es válido. Por favor, ingrese un monto válido para continuar.")
        st.stop()

# --- Siguiente: Si es Acuerdo o Oferta de Pago dar Especificaciones
if tipo_solicitud in ['Acuerdo de Pago', 'Oferta de Acuerdo']:
    st.divider()

    st.subheader("💰 Especificaciones del Acuerdo de Pago")

    # Creamos 2 Columnas: Fecha Esperada de Pago y Tipo de Pago
    colFechaPago, colTipoPago = st.columns(2)

    with colFechaPago:
        fecha_esperada_pago = st.date_input(
            "**Fecha Esperada de Pago**",
            value="today",
            help="Seleccione la fecha esperada de pago del acuerdo",
        )
        # Volvemos la Fecha a Timestamp
        fecha_esperada_pago = pd.Timestamp(fecha_esperada_pago)

    with colTipoPago:
        # Verificamos los Pagos Posibles según la Cantidad de Cuotas
        solicitud_a_cuotas = any(deuda_info['Num_Cuotas'] > 1 for deuda_info in info_completa_deudas)
        if solicitud_a_cuotas:
            posibles_pagos = ['Estructuraado','Refi']
        else:
            posibles_pagos = ['Tradicional','Crédito']

        tipo_pago = st.selectbox(
            "**Tipo de Pago**",
            options=posibles_pagos,
            help="Seleccione el tipo de pago que se realizará en el acuerdo",
            index=None,
        )

    # Verificamos que ambos tengan una selección válida
    if not fecha_esperada_pago or not tipo_pago:
        st.warning("Selecciona ambas opciones para continuar con el formulario", icon="😁")
        st.stop()
    elif fecha_esperada_pago < pd.Timestamp.now('America/Bogota').tz_localize(None).normalize():
        st.error("La fecha esperada de pago no puede ser menor a la fecha actual. Por favor, seleccione una fecha válida.", icon="❌")
        st.stop()
else:
    fecha_esperada_pago = None
    tipo_pago = None

# Mostramos un Campo para añadir Comentarios Adicionales sobre la Solicitud
comentario_adicional = st.text_area(
    "**Comentarios Adicionales sobre la Solicitud**",
    value="",
    help="Ingrese cualquier comentario adicional sobre la solicitud (Ejemplo: Válidar Máximo Descuento)",
)

# Mostramos el Resumen de la Solicitud dentro de un expander
with st.expander("**Ver Resumen de la Solicitud**", expanded=True):
    mostrar_resumen_solicitud(
        referencia=referencia_cliente,
        deudas_seleccionadas_df=deudas_seleccionadas_df, # type: ignore
        info_completa_deudas=info_completa_deudas,
        tipo_solicitud=tipo_solicitud,
        nombre_aliado=aliado_seleccionado if not (aliado_cambiado and (not es_admin)) else "DIRECTO BASE",
        fecha_esperada_pago=fecha_esperada_pago,
        tipo_pago=tipo_pago,
        comentario=comentario_adicional,
    )

# --- Siguiente: Botón de Envío del Formulario ---
st.divider()
st.subheader("✅ Envío del Formulario")

# Vamos a Construir la Respuesta como un Diccionario
response_info = {
    "Referencia": referencia_cliente,
    'Cedula': deudas_seleccionadas_df['Cedula'].iloc[0],
    'Ids_Deuda': '-'.join(deudas_seleccionadas_df['Id_Deuda'].tolist()),
    'Casa_Cobro': aliado_seleccionado,
    'Tipo_Solicitud': tipo_solicitud,
    'Datos_Solicitud': json.dumps(info_completa_deudas, ensure_ascii=False),
    'Ejecutivo': aliadosDict[aliado_seleccionado].obtener_ejecutivo() if aliado_seleccionado != 'Directo Base' else '',
    'Fecha_Esperada_Pago': fecha_esperada_pago.strftime('%Y-%m-%d') if fecha_esperada_pago else '',
    'Tipo_Pago': tipo_pago if tipo_pago else '',
    'Metadata_Solicitud': json.dumps({
        'Nombre_Cliente': deudas_activas_df['Nombre_Cliente'].iloc[0].title(),
        'Comentario_Negociador': comentario_adicional,
    }, ensure_ascii=False),
    'Estado_Solicitud': 'Sin Tocar',
}

# Creamos 2 Columnas: Una para el Botón de Envío y otra para el Mensaje de Éxito
colBoton, colMensaje = st.columns([1, 2])

ref_enviar_completa = referencia_cliente + ''.join((d['Id_Deuda'] for d in info_completa_deudas))
ya_enviado = (ref_enviar_completa != '') and (ref_enviar_completa == st.session_state.get('ultima_referencia_enviada'))

with colBoton:
    enviar_formulario = st.button(
        "Enviar Formulario",
        help="Presione este botón para enviar el formulario (Solo se envía una vez)",
        type="primary",
        key="enviar_formulario",
        disabled=ya_enviado,
    )

with colMensaje:
    if enviar_formulario and not ya_enviado:
        # 1. Bloqueamos inmediatamente para evitar dobles clics en cola
        st.session_state['ultima_referencia_enviada'] = ref_enviar_completa

        # 2. Ejecutamos el proceso a Google Sheets
        with st.spinner("Enviando formulario..."):
            success_response, new_id = upload_form_response_to_google_sheets(response_info=response_info)

        if success_response:
            st.toast(f"Formulario enviado correctamente!, ℹ️ID de Solicitud: {new_id}", icon="✅")
            # 3. Recargamos la app para aplicar instantáneamente el estado 'disabled' al botón
            st.rerun()
        else:
            # Si hubo error, liberamos el candado para que el usuario pueda reintentar
            st.session_state['ultima_referencia_enviada'] = None
            st.toast("Error al enviar el formulario. Por favor, intente nuevamente.", icon="❌")

    elif ya_enviado:
        st.info("Esta referencia ya fue enviada previamente con esas deudas.")
    else:
        st.info("Presione el botón para enviar el formulario (Solo se envía una vez)")