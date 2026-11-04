# Estándar usando PEP8
# Librerías de Python
# Librerías de Terceros
import streamlit as st
# Librerías Locales
from data.data_loader import load_client_balances
from modules.oportunidades import obtener_asignacion_para_referencia, obtener_pricing_para_referencia, obtener_prospecto_credito_para_referencia, obtener_prospecto_tradicional_para_deuda, obtener_prospecto_tradicional_para_referencia, obtener_referencias_habilitadas, obtener_ultima_actualizacion_deuda
from utils.helpers_general import formatNumber

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