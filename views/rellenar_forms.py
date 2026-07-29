# Estándar usando Pep8
# Librerías de Python
# Librerías de Terceros
import streamlit as st
import pandas as pd
# Librerías Propias
from modules.forms import cumple_condicion_actualizacion_deudas
from ui.forms_components import mostrar_seleccion_deudas, poner_monto_por_deuda
from data.data_loader import load_aliados, load_app_config, load_client_balances, load_current_month_solicitudes, load_liquidaciones, load_masivas, load_addendums, load_pab_ideal, obtener_referencia_por_deuda, obtener_deudas_activas, obtener_ultima_actualizacion_deudas

def rellenar_formulario():
    # Carga de Información Necesaria para el Formulario
    # Se Necesita:
    # Solicitudes MEC
    solsDF = load_current_month_solicitudes()
    # Aliados Actuales
    aliadosDict = load_aliados()
    # Saldos y Por Cobrar
    saldosDict = load_client_balances()
    # Addendums
    addsDF = load_addendums()
    # PaB Ideal
    pabIdealDF = load_pab_ideal()
    # Deudas ya Liquidadas
    debtsLiq = load_liquidaciones()
    # Actualizaciones Masivas
    masivasDF = load_masivas()
    # Configuración del App
    appConfig = load_app_config()


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
        referencia_cliente = st.number_input("Referencia del Cliente, Ejemplo: 3007083770", help="Ingrese la referencia del cliente")

    # Deuda Representante del Cliente
    with cols[1]:
        id_deuda = st.number_input("Id_Deuda del Cliente, Ejemplo: 123456789",
        help="Ingrese el Id de alguna deuda del cliente",
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
    deudas_activas_df = obtener_deudas_activas(referencia=referencia_cliente)

    # Si ésta vácio entonces pasamos al segundo fallback: -> Buscar Referencia por Id_Deuda
    if deudas_activas_df.empty:
        # Si el Id_Deuda es Vácio entonces no podemos hacer nada
        if not id_deuda:
            st.session_state['id_rep_needed'] = True
            st.info("No se encontraron deudas activas para la referencia proporcionada. Por favor, ingrese algún Id Deuda de la Referencia para continuar.")
            st.stop()

        # Obtenemos la Referencia por Id_Deuda
        ref_antigua = referencia_cliente
        referencia_cliente = obtener_referencia_por_deuda(deuda=id_deuda)

        # Si la Referencia sigue siendo Vació entonces no podemos hacer nada
        if not referencia_cliente:
            st.error("No se encontró una referencia asociada al Id_Deuda proporcionado.")
            st.stop()

        # Obtenemos las Deudas Activas con la Referencia Obtenida
        deudas_activas_df = obtener_deudas_activas(referencia=referencia_cliente)

    # Quitamos de las Deudas Activas las que ya han sido Liquidadas
    deudas_activas_df = deudas_activas_df[~deudas_activas_df['Id_Deuda'].isin(debtsLiq)]

    # Si el DF sigue siendo vacío entonces no podemos hacer nada
    if deudas_activas_df.empty:
        st.error("No se encontraron deudas activas para la referencia proporcionada.")
        st.stop()


    # Verificamos que exista una Última Actualización para las Deudas Activas
    ultima_actualizacion = obtener_ultima_actualizacion_deudas(debt_ids=deudas_activas_df['Id_Deuda'].tolist(), user_email=st.session_state.get('user_email', ''))
    # Veriticamos que satisface la Condición de Mínimo de Días Hábiles para Actualización
    cumple_condicion, dias_habiles_diff = cumple_condicion_actualizacion_deudas(ultima_actualizacion=ultima_actualizacion)
    if not cumple_condicion:
        st.warning("La última actualización de las deudas activas fue hace {:.2f} días hábiles, lo cual es menor al mínimo necesario de {} días hábiles para poder continuar con el llenado del formulario.".format(
            dias_habiles_diff, appConfig['MIN_NECESSARY_DAYS_FOR_DEBT_UPDATE']
        ))
        st.info('Debes Actualizar alguna de las deudas activas antes de poder continuar con el llenado del formulario.')
        st.stop()

    # Verificamos si tiene algún Addendum Activo
    addendum_activo = addsDF[(addsDF['Referencia'] == referencia_cliente) & (addsDF['Estado'] == 'Activo')]
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
        porCobrarAntiguo = saldosDict['Por Cobrar'][ref_antigua]
        porCobrarNuevo = saldosDict['Por Cobrar'][referencia_cliente]
        porCobrarReal = max(porCobrarAntiguo, porCobrarNuevo)

        pricing = deudas_activas_df['Pricing'].max()

        # Guardamos esta Información en los Session_State si es Necesario
        if referencia_cliente != st.session_state.get('ultima_referencia', ''):
            st.session_state['saldo_real'] = saldoReal
            st.session_state['por_cobrar_real'] = porCobrarReal
            st.session_state['pricing'] = '{:.2f}%'.format(pricing * 100)

        # Ahora los Vamos Poniendo como Inputs en el Formulario
        with colSaldos:
            st.number_input("Saldo del Cliente",
                disabled=False, 
                format="%0.0f",
                help="Saldo del Cliente según lo que se reporta en SALDOS",
                key = "saldo_real",
                icon="💰",
            )
        with colPorCobrar:
            st.number_input("Por Cobrar del Cliente",
                disabled=False, 
                format="%0.0f",
                help="Por Cobrar del Cliente según lo que se reporta en SALDOS",
                key = "por_cobrar_real",
                icon="💸",
            )
        with colPricing:
            st.text_input("Pricing del Cliente",
                disabled=True,
                help="Pricing del Cliente según lo que se reporta en la Base de Datos",
                key = "pricing",
                icon="📈",
            )

    # Añadimos un Subheader para la Selección de Deudas
    st.divider()
    st.subheader("Selección de Deudas Activas")

    # Mostramos la Selección de Deudas
    mostrar_seleccion_deudas(deudas_activas_df=deudas_activas_df) # type: ignore

    # Guardamos la Referencia como Ultima en el Session_State
    st.session_state['ultima_referencia'] = referencia_cliente

    # Filtramos el DF para dejar solo las Deudas Seleccionadas
    deudas_seleccionadas_df = deudas_activas_df[deudas_activas_df['Id_Deuda'].isin(st.session_state['deudas_seleccionadas'])]

    # Dado que añadimos info de los Addendums reescribimos la Columna Pricing con el valor máximo de Pricing entre las Deudas Seleccionadas
    deudas_seleccionadas_df['Pricing'] = deudas_activas_df['Pricing'].max()

    # Verificamos que al menos una Deuda esté Seleccionada
    if not st.session_state['deudas_seleccionadas']:
        st.warning("Debe seleccionar al menos una deuda activa para poder continuar con el llenado del formulario.")
        st.stop()

    # Siguiente Paso: Seleccionar Tipo de Solicitud y el Aliado
    st.divider()
    st.subheader("🫡Selección de Tipo de Solicitud y Aliado")

    col1, col2 = st.columns(2)

    with col1:
        tipo_solicitud = st.radio(
            "Tipo de Solicitud",
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
            "Aliado - Casa de Cobro",
            options=list(aliadosDict.keys())+['Directo Base'],
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
    poner_monto_por_deuda(deudas_activas_df=deudas_seleccionadas_df) # type: ignore

    # --- Siguiente: Alertas y Verificaciones ---

    # Alerta 1: Descuento en Base y Aliado Brinda Descuento Máximo
    masivas_locales = masivasDF[masivasDF['Id_Deuda'].isin(st.session_state['deudas_seleccionadas'])]
    if aliado_seleccionado != 'Directo Base' and not masivas_locales.empty:
        aliado_brinda_descuento_maximo = aliadosDict[aliado_seleccionado]['Brinda Descuento Máximo']
        if aliado_brinda_descuento_maximo:
            st.warning("El aliado seleccionado brinda descuento máximo, por lo que una oferta de mejora de descuento puede no ser aceptada. Se recomienda revisar las condiciones de la solicitud antes de continuar.")

    # Alerta 2: Verificacion de Descuentos en Base
    if not masivas_locales.empty:
        pass
