# Estándar usando PEP8
# Librerías de Python
from typing import Optional
# Librerías de Terceros
import numpy as np
import streamlit as st
# Librerías Locales
from data.data_loader import load_client_balances
from modules.constants import IVA
from modules.gest_sols import obtener_valor_pab_ideal
from modules.oportunidades import obtener_asignacion_para_referencia, obtener_estado_actual_credito, obtener_estado_liquidacion_deudas, obtener_pricing_para_referencia, obtener_prospecto_credito_para_referencia, obtener_prospecto_tradicional_para_deuda, obtener_prospecto_tradicional_para_referencia, obtener_referencias_habilitadas, obtener_ultima_actualizacion_deuda
from ui.forms_components import mostrar_componente_feedback
from utils.helpers_general import cleanNumber, formatNumber

# Función Auxiliar para Reiniciar la Selección de las Deudas
def reiniciar_seleccion_deudas(deudas: list[str], seleccionado: bool):
    for d in deudas:
        key_deuda_select = f"select_calc_ind_debt_{d}"
        st.session_state[key_deuda_select] = seleccionado

# Función Auxiliar para mostrar los Datos por Deuda de una Referencia en Específico
def mostrar_datos_por_deuda_referencia(referencia: str) -> list[str]:
    """Función para mostrar la escogencia de las Deudas. Para esto se muestran las siguientes columnas:
    - Selección de Deuda (Toggle)
    - Id_Deuda
    - Banco
    - PaB_Origen
    - Ultima Act

    Args:
        referencia (str): La Referencia que se seleccióno

    Returns:
        list[str]: Lista con las Deudas que se escogieron para analizar
    """
    # Primero Obtenemos los Datos de la Referencia Escogida
    datos_ref = obtener_asignacion_para_referencia(referencia)
    # Ordenamos los Datos por Banco y PaB_Origen
    datos_ref = datos_ref.sort_values(by=['Banco','PaB_Origen'])

    # Inicializamos las Llaves de Selección
    for d in datos_ref['Id_Deuda'].unique():
        key_deuda_select = f"select_calc_ind_debt_{d}"
        if not (key_deuda_select in st.session_state):
            st.session_state[key_deuda_select] = True

    # Creamos las Columnas para los Headers
    colSelect, colIdDebt, colBanco, colPaB, colAct = st.columns([1,2,2,2,3])
    with colSelect:
        st.markdown("**Seleccionar**")
    with colIdDebt:
        st.markdown("**Id de Deuda**")
    with colBanco:
        st.markdown("**Banco**")
    with colPaB:
        st.markdown("**Deuda Resuelve**")
    with colAct:
        st.markdown("**Última Actualización**")

    # Iteramos por cada uno de los datos
    for _, row in datos_ref.iterrows():
        # Creamos las Columnas para los Datos
        colSelect, colIdDebt, colBanco, colPaB, colAct = st.columns([1,2,2,2,3])
        # Vamos introduciendo los datos por columna
        key_deuda_select = "select_calc_ind_debt_{debt}".format(debt=row['Id_Deuda'])
        ultima_act_deuda = obtener_ultima_actualizacion_deuda(row['Id_Deuda'])
        prospecto_deuda = obtener_prospecto_tradicional_para_deuda(row['Id_Deuda'])

        with colSelect:
            st.toggle("Escogencia",key=key_deuda_select, label_visibility="collapsed")
        with colIdDebt:
            st.markdown("**{}**".format(row['Id_Deuda']))
            # Si la deuda es prospecto se agrega un st.caption
            if prospecto_deuda != "N/A":
                st.caption("🆔Prospecto Tradicional: **{}**".format(prospecto_deuda))
        with colBanco:
            st.write(row['Banco'])
        with colPaB:
            st.write("$ " +formatNumber(row['PaB_Origen']))
        with colAct:
            st.markdown(ultima_act_deuda)

    # Ahora Creamos 2 Botones: 1 para seleccionar todas y otra para deseleccionar todas
    colDeselectAll, colSelectAll = st.columns(2)
    deudas_unicas = list(datos_ref['Id_Deuda'].unique())

    with colDeselectAll:
        st.button(
            "**Deseleccionar Todas**",
            type="primary",
            width="stretch",
            icon="⛔",
            key = "deselect_all_debts_calc_ind",
            on_click=reiniciar_seleccion_deudas,
            kwargs={"deudas": deudas_unicas, "seleccionado": False}
        )

    with colSelectAll:
        st.button(
            "**Seleccionar Todas**",
            type="secondary",
            width="stretch",
            icon="🔅",
            key = "select_all_debts_calc_ind",
            on_click=reiniciar_seleccion_deudas,
            kwargs={"deudas": deudas_unicas, "seleccionado": True}
        )

    # Ahora obtenemos las deudas que estan seleccionadas
    deudas_seleccionadas = [
        debt for debt in deudas_unicas
        if st.session_state[f"select_calc_ind_debt_{debt}"]
    ]
    # Si no hay deudas Seleccionadas se detiene la selección y se muestra una alerta
    if not deudas_seleccionadas:
        st.warning("Selecciona al menos una deuda para continuar",icon="🚧")
        st.stop()
    # Devolvemos las Deudas y mostramos un st.caption de resumen
    st.caption("ℹ️Se seleccionaron {} de {} deudas ({:.0%})".format(
        len(deudas_seleccionadas),
        len(deudas_unicas),
        len(deudas_seleccionadas) / len(deudas_unicas)
    ))

    return deudas_seleccionadas

# Función para mostrar alertas de liquidación de deudas
def mostrar_alertas_liquidacion(*,deudas: list[str]):
    # Primero Obtenemos los estados de liquidación para cada deuda
    estados_liq = obtener_estado_liquidacion_deudas(deudas=deudas)
    # Ahora Iteramos y construimos el str con los baadges
    st.caption("✅Verificando que las deudas no esten liquidadas")
    str_badge = ""
    for idx, (d, is_liq) in enumerate(estados_liq.items(),start=1):

        str_badge += ":{color}-badge[ID: {debt_id} - **{liq_state}**]".format(
            color = "red" if is_liq else "green",
            debt_id = d,
            liq_state = "LIQUIDADA" if is_liq else "Sin Liq"
        )

        if idx % 5 == 0:
            if str_badge:
                st.markdown(str_badge)
                str_badge = ""

    # Mostramos si alguna falta
    if str_badge:
        st.markdown(str_badge)

    # Detenemos el App si hay alguna liquidada
    if any(estados_liq.values()):
        st.error("No puedes calcular datos para deudas liquidadas {}".format(
            "-".join([d for d, is_liq in estados_liq.items() if is_liq])
        ),icon="❌")
        st.stop()
    

# Función para mostrar alertas relacionadas con el cálculo por Crédito
def mostrar_alertas_credito(*, referencia: str, deudas: list[str]):
    # Primero inicializamos si ya se generó una alerta
    debtsIncumplir = []
    # Ahora iteramos por cada deuda
    with st.expander("⛔ Verificación de PaB Ideal desde Crédito", expanded=False):
        for d in deudas:
            pab_ideal = obtener_valor_pab_ideal(debt=d)
            if pab_ideal == 0:
                st.error("La Deuda <{}> NO CUENTA CON **PAB IDEAL**".format(d), icon="❌")
                debtsIncumplir += [d]
            else:
                st.success("Deuda <{}> tiene PaB Ideal de $ {:,.0f}".format(d,pab_ideal), icon = "✅")

    if debtsIncumplir:
        st.error(
            title="**SIN PAB IDEAL PARA TODAS LAS DEUDAS**",
            body="Las Deudas **{}** no tienen PaB ideal de crédito por lo que no se pueden analizar por este medio".format(
                ' - '.join(debtsIncumplir)
            ),
            icon="🚧"
        )
        st.stop()
    # Siguiente: Verificamos el Rechazo de Crédito
    status, rechazo, no_opp = obtener_estado_actual_credito(referencia)

    # Creamos 3 Columnas para Mostrar estos Datos
    colReferencia, colCred, colAlerta = st.columns([1,3,2])

    with colReferencia:
        st.metric(
            label="**Referencia**",
            value=referencia,
            delta=None
        )

    with colCred:
        str_cred = ":{color_status}-badge[{dato_status}]".format(
            color_status = "green" if status == "CERRADO" else ("gray" if not (rechazo or no_opp) else "red"),
            dato_status = status
        )
        # Agregamos detalle según rechazo o no_opp
        if rechazo:
            str_cred += " :{color_status}-badge[{dato_status}]".format(
                color_status = "yellow", dato_status = "⚠️CRÉDITO RECHAZADO"
            )
        if no_opp:
            str_cred += " :{color_status}-badge[{dato_status}]".format(
                color_status = "red", dato_status = "❌NO OPTA A CRÉDITO"
            )
        # Mostramos el Detalle
        st.markdown(str_cred)

    with colAlerta:
        if no_opp:
            st.error("Cliente no es Apto para Crédito", icon="❌")
            st.stop()
        elif rechazo:
            st.warning("Cliente ya había rechazado el crédito, aunque puede Salir 👍", icon="🚧")
        else:
            st.success("Cliente pasa precauciones de Crédito", icon="✅")

# Función para Mostrar las oportunidades
def mostrar_oportunidades_referencia(*,referencia: str, debts_selected: list[str]):
    # La idea aquí sera mostrar st.badges con cada Oportunidad que aplique a la izquierda
    # A la derecha mostrar los detalles de cada oportunidad

    # Toca crear función de calcular oportunidades donde: Devuelva diciconario con nombre de oportunidad y valor
    # opps_cliente = calcular_opps_cliente(referencia=referencia, deudas = debts_selected)

    # Dejo el esquema para llenar
    colRef, colDetalle = st.columns([1,3],vertical_alignment="top", border=True)
    with colRef:
        st.metric(
            label="**Referencia**",
            value=referencia
        )
        # st.markdown ( color-badge[opp] for opp in opps_cliente) if opps_cliente else st.error("Sin Oportunidades")
    
    with colDetalle:
        colHNombre, colHDescripcion, colHValor = st.columns([1,3,2],vertical_alignment="top")
        with colHNombre:
            st.markdown("##### **🧮 Oportunidad**")
        with colHDescripcion:
            st.markdown("##### **❔¿Que significa?**")
        with colHValor:
            st.markdown("##### **🔅 Valor**")

        # for opp in opps_cliente: HAY QUE AGREGAR LOS VALORES EN LAS CONSTANTES
        #     colNombre, colDescripcion, colValor = st.columns([1,3,2],vertical_alignment="top")

        #     with colNombre:
        #         st.badge(opp, color=COLORES_OPORTUNIDADES[opp], icon=ICONOS_OPORTUNIDADES[opp])
        #     with colDescripcion:
        #         st.markdown(DESCRIPCION_OPORTUNIDADES[opp])
        #     with colValor:
        #         st.markdown(opps_cliente[opp])

# Función Auxiliar para Mostrar la Selección de una Deuda
def mostrar_seleccion_deuda(*,deuda: str, init_pab: Optional[float]) -> float:
    """Función para mostrar la selección de una deuda
    Basicamente debe mostrar el ID, el valor de la deuda
    Sliders con Descuento y PaB, Ingreso Manual de Descuento y PaB, el Descuento Final, PaB Final y el ingreso que dejaría

    Args:
        deuda (str): El Id de la Deuda Seleccionada
        init_pab (Optional[float]): El PaB con Descuento inicial a tomar

    Returns:
        float: El Pago por la Deuda
    """ 
    # Primero Inicializamos los Estados de Cálculo de la Deuda
    # Aquí se deben inicializar los valores y calcular para atrás según el último cambio

    # Luego Creamos las Columnas
    colIdDum, colSliders, colManual, colDiscPayment, colIngreso = st.columns([1,3,1,1,1], vertical_alignment="center")

    with colIdDum:
        st.metric(
            label="🆔Id Deuda",
            value=deuda
        )
        # st.caption("✅DUM: **" + formatNumber(dum_deuda) + "**")
    
    with colSliders:
        st.slider(
            label="**Descuento**"
        )
        st.slider(
            label="PaB"
        )

    with colManual:
        st.text_input(
            label="**Descuento**"
        )
        st.text_input(
            label="**PaB**"
        )

        # Se limpian los datos con cleanNumber
    
    with colDiscPayment:
        # 
        st.metric(
            label="**✅ %Descuento**"
        )
        st.metric(
            label="**💵 PaB**"
        )

    # with colIngreso:
        # st.metric(
        #     label="😁Ingreso",
        #     value=f"{ingreso:,.2f}",
        #     delta = f"${ingreso * (1+IVA):,.2f} con IVA"
        # )
    
    # Por último devolvemos el PaB
    # return pab_deuda

# Función para mostrar la calculadora individual
def mostrar_calculadora_individual(): 
    st.subheader("😁 Calculadora Individual por Referencia")

    # Mostramos un Selector de la Referencia, con otras 3 columnas para ahorro Neto, Pricing y Prospectos
    refs_habilitadas = obtener_referencias_habilitadas()

    colRef, colAhorro, colPricing, colProspectos = st.columns([2, 1, 1, 2])
    with colRef:
        ref_escogida = st.selectbox(
            "**😁 Referencia a Analizar**",
            options=refs_habilitadas,
            index=None,
            help="Selecciona la Referencia que deseas analizar. Solo se muestran las Referencias habilitadas para tu usuario.",
            key="selectbox_referencia_calc_ind"
        )
        st.caption("Si no te sale la Ref es porque no estuvó asignada :(")

    if ref_escogida is None:
        st.info("Escoge una Referencia para Continuar",icon="ℹ️")
        st.stop()

    with colAhorro:
        # Traemos los Datos de la Referencia Escogida
        saldosDict = load_client_balances()
        # Obtenemos el Ahorro y el Por Cobrar del Cliente
        ahorro = saldosDict['Saldos'][ref_escogida]
        porcobrar = saldosDict['PorCobrar'][ref_escogida]
        ahorro_neto = ahorro - porcobrar
        st.metric(
            label="💰 Ahorro Neto",
            value=f"${ahorro_neto:,.0f}",
            delta=f"${ahorro:,.0f} - ${porcobrar:,.0f}",
            delta_color="inverse"
        )

    with colPricing:
        pricing_ref = obtener_pricing_para_referencia(ref_escogida)
        st.metric(
            label="💲 Pricing",
            value=f"${pricing_ref:,.0%}",
            delta="Pricing" if pricing_ref > 0.15 else "Tradicional",
            delta_color="normal"
        )

    with colProspectos:
        # Obtenemos los Prospectos de Crédito y Tradicional
        prosp_cred = obtener_prospecto_credito_para_referencia(ref_escogida)
        prosp_trad = obtener_prospecto_tradicional_para_referencia(ref_escogida)
        # Ahora los mostramos
        st.badge(
            f"Batch: **{prosp_cred}**", color="green" if prosp_cred != "Tradicional" else "gray"
        )
        st.badge(
            f"Prospecto Tradicional: **{prosp_trad}**", color="blue" if prosp_cred != "N/A" else "gray"
        )

    # Mostramos los Datos de Selección de Deudas
    debts_selected = mostrar_datos_por_deuda_referencia(ref_escogida)

    # Mostramos la alerta de las deudas
    mostrar_alertas_liquidacion(deudas = debts_selected)

    # Escoger el Tipo de Análisis: Por Crédito o Tradicional
    tipo_analisis = st.radio(
        label="**🧮 Tipo de Análisis a Realizar**",
        options=[
            "**Por Tradicional**",
            "**Por Crédito**"
        ],
        captions=[
            "El Análisis se realiza con el Ahorro del Cliente",
            "El Análisis se realiza con el PAB Ideal que otorga Crédito",
        ],
        horizontal=True,
        key="select_analysis_calc_ind",
        index=1 if "parcial" in prosp_cred.lower() else (0 if prosp_cred == "Tradicional" else None),
        disabled= (prosp_cred == "Tradicional") or ("parcial" in prosp_cred.lower()),
    )

    if tipo_analisis is None:
        st.stop()

    opp_credito = (not ("Tradicional" in tipo_analisis))

    # En caso de ser Crédito, debe de existir un PaB Ideal, de lo contrario se muestra una alerta
    if opp_credito:
        mostrar_alertas_credito(referencia=ref_escogida,deudas=debts_selected)

    # Creamos las Configuraciones Iniciales (para el Feedback)
    configs = {
        "Referencia": ref_escogida,
        "Deudas": debts_selected
    }

    # Creamos 3 Columnas: Columna Ahorro, Columna Por Cobrar y Columna Depósito Extra
    colAhorroInput, colPorCobrarInput, colDEInput = st.columns(3, border=True)
    # Inicalizamos Valores
    dictInitInputs = {
        f"ahorro_input_{ref_escogida}_calc_opps": ahorro,
        f"porcobrar_input_{ref_escogida}_calc_opps": porcobrar,
        f"dep_extra_input_{ref_escogida}_calc_opps": 0,
    }
    for key, val in dictInitInputs.items():
        if not (key in st.session_state):
            st.session_state[key] = val
        # Ahora los Actualizamos limpiandolos
        cleanedVal = cleanNumber(st.session_state[key], default_nan=np.nan)
        # Verificamos si es un NaN
        if np.isnan(cleanedVal):
            st.error("No se puede convertir el valor {} a Númerico".format(st.session_state[key]))
            cleanedVal = 0
        # Actualizamos la llave
        st.session_state[key] = formatNumber(cleanedVal)

        # Agregamos los Valores a la Configuración
        name_input = key[:key.index("_input")]
        configs[name_input] = cleanedVal

    # Ahora Mostramos los inputs
    with colAhorroInput:
        ahorro_input = st.text_input(
            label="**💵 Ahorro**",
            key = f"ahorro_input_{ref_escogida}_calc_opps"
        )
    with colPorCobrarInput:
        porcobrar_input = st.text_input(
            label="**💼 Por Cobrar**",
            key = f"porcobrar_input_{ref_escogida}_calc_opps"
        )
    with colDEInput:
        dep_extra_input = st.text_input(
            label="**📈 Depósito Extra**",
            key = f"dep_extra_input_{ref_escogida}_calc_opps"
        )

    # Se crean 2 Columnas: Columna de Detalles de Deudas y Columna de Resultados
    colDetallesDeudas, colResultados = st.columns([4,1], vertical_alignment="center", gap="xsmall")

    pab_deudas = {}

    with colDetallesDeudas:
        for d in debts_selected:
            with st.container(border=True):
                pab_deudas[d] = mostrar_seleccion_deuda(deuda=d)

    with colResultados:
        # Mostramos Dum Total, PaB, Ingreso ,Pago Total del Cliente y si es Viable
        st.metric(
            label="**💰 DUM Total**"
        )
        st.metric(
            label="**💵 PaB**"
        )
        st.metric(
            label="**😁 Ingreso**",
            delta = "{:,.2f} con IVA"
        )
        st.metric(
            label="**ℹ️ Pago Total**"
            #value = sum(pab_deudas.values()) + ingreso*(1+IVA)
        )
        st.metric(
            label="**❔Es Viable**",
            # value="Viable 😁" if 
            # es_viable_cliente(
            # referencia=ref_escogida, 
            # pab_deudas = pab_deudas, 
            # ahorro_neto = ahorro_input + dep_extra_input - porcobrar_input) 
            # else "❌ No Viable"
        )
        # Para Calcular la viabilidad del cliente hay que ver si es opp de liq instantanea dado el nuevo ahorro,por cobrar y deposito extra

    st.divider()
    # Mostramos las Oportunidades de la Referencia
    mostrar_oportunidades_referencia(referencia = ref_escogida, deudas = debts_selected)

    st.divider()
    # Mostramos Componente de Feedback
    mostrar_componente_feedback(origin="Calculadora_Individual_Opps",configs=configs)