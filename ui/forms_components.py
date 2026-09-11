# Estándar usando Pep8
# Librerías de Python
from typing import Any, Optional
# Librerías de Terceros
from pandera.typing import DataFrame
import pandas as pd
import streamlit as st
# Librerías Locales
from data.data_models import DeudasActivasSchema
from modules.forms import obtener_descuento_base, validar_descuento_base, obtener_descuento_optimo
from utils.helpers_general import cleanNumber, formatNumber, getBDDaysDiffFloat

def mostrar_seleccion_deudas(deudas_activas_df: DataFrame[DeudasActivasSchema]) -> list[str]:
    st.subheader("Deudas Activas del Cliente")
    st.info("Seleccione las deudas que desea incluir en el formulario de alianzas")

    # Vamos a Añadir 2 Checbox: Seleccionar Todas y Deseleccionar Todas
    colDeselectAll, colSelectAll  = st.columns(2, vertical_alignment="center")

    # Ordenamos los Datos por Banco
    deudas_activas_df = deudas_activas_df.sort_values(by=['Banco', 'Id_Deuda'], ascending=[True, True])

    with colDeselectAll:
        if st.button("Deseleccionar Todas", key="deselect_all_deudas", type="primary", width="stretch"):
            for _, row in deudas_activas_df.iterrows():
                st.session_state[f"select_deuda_{row['Id_Deuda']}"] = False
                st.session_state['deudas_seleccionadas'] = []

    with colSelectAll:
            if st.button("Seleccionar Todas", key="select_all_deudas", type="secondary", width="stretch"):
                for _, row in deudas_activas_df.iterrows():
                    st.session_state[f"select_deuda_{row['Id_Deuda']}"] = True
                    st.session_state['deudas_seleccionadas'] = deudas_activas_df['Id_Deuda'].tolist()

    # Van a ser 4 Columns: Checkbox de Seleccion, Id_Deuda, Banco, PaB_Origen
    colCH, colIdDeuda, colBanco, colPaBOrigen = st.columns([1, 2, 2, 2], vertical_alignment="center")

    # Añadimos los Headers
    with colCH:
        st.markdown("**Seleccionar**")
    with colIdDeuda:
        st.markdown("**Id Deuda**")
    with colBanco:
        st.markdown("**Banco**")
    with colPaBOrigen:
        st.markdown("**Deuda Bravo**")

    for _, row in deudas_activas_df.iterrows():
        with colCH:
            selected = st.toggle("Seleccionar Deuda", key=f"select_deuda_{row['Id_Deuda']}", value=True, label_visibility="collapsed")
            if selected:
                st.session_state['deudas_seleccionadas'].append(row['Id_Deuda'])
            else:
                if row['Id_Deuda'] in st.session_state['deudas_seleccionadas']:
                    st.session_state['deudas_seleccionadas'].remove(row['Id_Deuda'])

        with colIdDeuda:
            st.text(row['Id_Deuda'])

        with colBanco:
            st.text(row['Banco'])

        with colPaBOrigen:
            st.text(formatNumber(row['PaB_Origen']))

    # Definimos los Ids elegidos de las Deudas Seleccionadas
    deudas_seleccionadas = [deuda for deuda in deudas_activas_df['Id_Deuda'] if st.session_state.get(f"select_deuda_{deuda}", False)]

    return deudas_seleccionadas

def mostrar_monto_recomendado(*,referencia: str, deudas: list[str], pricing: float, deudas_seleccionadas_df: DataFrame[DeudasActivasSchema]) -> None:
    st.subheader("💰 Monto Recomendado para el Acuerdo")

    # Definimos el Pago Original como la Suma de PaB_Origen de todas las Deudas Seleccionadas
    pago_original = deudas_seleccionadas_df['PaB_Origen'].sum()
    pago_pl = deudas_seleccionadas_df['PaB_PL'].sum()
    descuento_pl = 1 - (pago_pl / pago_original) if pago_original > 0 else 0

    # Obtenemos el Descuento Óptimo
    descuento_optimo, tipo_pago = obtener_descuento_optimo(referencia=referencia, deudas=deudas, pricing=pricing, pago_total_original=pago_original, descuento_pl=descuento_pl)
    # Si el Descuento Óptimo es >= 1, mostramos mensaje de no es viable
    if descuento_optimo >= 1:
        st.info("No hay Recomendación de Monto, falta ahorro 😁")
    else:
        monto_recomendado = pago_original * (1-descuento_optimo)
        st.success(f"💰 Monto Recomendado: ${monto_recomendado:,.0f} (Descuento Óptimo: {descuento_optimo:.2%}, Tipo de Pago: {tipo_pago})")

def poner_monto_por_deuda(deudas_activas_df: DataFrame[DeudasActivasSchema]) -> list[dict[str,Any]]:
    st.subheader("🗒️ Montos Propuestos por Deuda")

    # 1. Copia de DataFrame y cálculo de %Total
    deudas_activas_df_copy = deudas_activas_df.copy()
    suma_pab = deudas_activas_df_copy['PaB_Origen'].sum()
    deudas_activas_df_copy['%Total'] = (
        deudas_activas_df_copy['PaB_Origen'] / suma_pab if suma_pab > 0 else 0
    )

    # 2. Inicialización de valores por primera vez (Valores por defecto)
    if 'usar_para_todos' not in st.session_state:
        st.session_state['usar_para_todos'] = True

    if 'pago_total' not in st.session_state:
        st.session_state['pago_total'] = formatNumber(round(suma_pab * 0.7, 2))

    pago_total = cleanNumber(st.session_state['pago_total'])

    for _, row in deudas_activas_df_copy.iterrows():
        key_monto = f"monto_propuesto_{row['Id_Deuda']}"
        key_cuotas = f"num_cuotas_{row['Id_Deuda']}"
        if key_monto not in st.session_state:
            st.session_state[key_monto] = formatNumber(pago_total * row['%Total'])
        if key_cuotas not in st.session_state:
            st.session_state[key_cuotas] = 1

    # 3. LÓGICA DE RECALCULO (Se ejecuta ANTES de dibujar los inputs en pantalla)
    if st.session_state['usar_para_todos']:
        # Si la opción "Distribuir" está activa, actualizamos el estado de cada deuda
        for _, row in deudas_activas_df_copy.iterrows():
            st.session_state[f"monto_propuesto_{row['Id_Deuda']}"] = formatNumber(pago_total * row['%Total'])
        # Aplicamos el formateo para el pago_total
        st.session_state['pago_total'] = formatNumber(pago_total)
    else:
        # Si se edita individualmente, recalculamos el total como la suma de las deudas
        pago_total_nuevo = sum(
            cleanNumber(st.session_state[f"monto_propuesto_{row['Id_Deuda']}"]) for _, row in deudas_activas_df_copy.iterrows()
        )
        st.session_state['pago_total'] = formatNumber(pago_total_nuevo)
        # Ahora Formateamos el monto_propuesto de cada deuda para que se vea bonito en pantalla
        for _, row in deudas_activas_df_copy.iterrows():
            key_monto = f"monto_propuesto_{row['Id_Deuda']}"
            st.session_state[key_monto] = formatNumber(st.session_state[key_monto])

    # 4. Renderizado de Controles Principales
    colPagoTotal, colUsarParaTodos, colCuotas = st.columns([2, 1, 1], vertical_alignment="center")

    with colPagoTotal:
        st.text_input(
            "Monto Total a Pagar",
            key="pago_total",  # Vinculado directamente al Session State
            help="Ingresar el Monto a Pagar por todas las Deudas",
            disabled=not st.session_state['usar_para_todos']
        )

    with colUsarParaTodos:
        st.toggle(
            "**Distribuir el Monto entre Deudas**",
            key="usar_para_todos",
            help="Si se selecciona, el Monto Total se distribuirá según el %Total."
        )

    with colCuotas:
        tipo_cuotas = st.selectbox(
            "Habilitar Solicitud a Cuotas",
            options=["No", "Por Deuda", "Para Todas las Deudas"],
            key="tipo_cuotas",
            help="Configurar pago en cuotas"
        )

    num_cuotas_global = 1
    if tipo_cuotas == 'Para Todas las Deudas':
        num_cuotas_global = st.number_input(
            "Número de Cuotas",
            min_value=1,
            max_value=60,
            value=3,
            step=1,
            key="num_cuotas_global_forms"
        )

    # 5. Encabezados de la Tabla
    if tipo_cuotas == 'Por Deuda':
        colIdDeuda, colPaBOrigen, colProp, colPorcentaje, colMontoPropuesto, colCuotasCol = st.columns([2, 2, 2, 1, 3, 2], gap="small", vertical_alignment="center")
    else:
        colIdDeuda, colPaBOrigen, colProp, colPorcentaje, colMontoPropuesto = st.columns([2, 2, 2, 1, 3], gap="small", vertical_alignment="center")

    with colIdDeuda:
        st.markdown("**Id Deuda**")
    with colPaBOrigen:
        st.markdown("**Deuda Bravo**")
    with colProp:
        st.markdown("**Descuento en Base**")
    with colPorcentaje:
        st.markdown("**% Total**")
    with colMontoPropuesto:
        st.markdown("**Monto Propuesto**")
    if tipo_cuotas == 'Por Deuda':
        with colCuotasCol: # type: ignore
            st.markdown("**Número de Cuotas**")

    # 6. Renderizado de Filas de la Tabla
    for _, row in deudas_activas_df_copy.iterrows():
        id_deuda = row['Id_Deuda']
        descuento_base = obtener_descuento_base(deuda=id_deuda)

        if tipo_cuotas == 'Por Deuda':
            colIdDeuda, colPaBOrigen, colProp, colPorcentaje, colMontoPropuesto, colCuotasCol = st.columns([2, 2, 2, 1, 3, 2], gap="small", vertical_alignment="center")
        else:
            colIdDeuda, colPaBOrigen, colProp, colPorcentaje, colMontoPropuesto = st.columns([2, 2, 2, 1, 3], gap="small", vertical_alignment="center")

        # Cambiamos los Session state para no depender de Value
        st.session_state[f"id_deuda_{id_deuda}_forms_input"] = row['Id_Deuda']
        st.session_state[f"pab_origen_{id_deuda}_forms_input"] = formatNumber(row['PaB_Origen'])
        st.session_state[f"descuento_base_{id_deuda}_forms_input"] = formatNumber(descuento_base) if pd.notna(descuento_base) else "N/A"
        st.session_state[f"porcentaje_{id_deuda}_forms_input"] = '{:.2%}'.format(row['%Total'])
        
        with colIdDeuda:
            st.text_input(
                "Id Deuda",
                disabled=True,
                label_visibility="collapsed",
                key=f"id_deuda_{id_deuda}_forms_input"
            )

        with colPaBOrigen:
            st.text_input(
                "Deuda Bravo",
                disabled=True,
                label_visibility="collapsed",
                key=f"pab_origen_{id_deuda}_forms_input"
            )

        with colProp:
            st.text_input(
                "Descuento en Base",
                disabled=True,
                label_visibility="collapsed",
                key=f"descuento_base_{id_deuda}_forms_input"
            )

        with colPorcentaje:
            st.text_input(
                "% Total",
                disabled=True,
                label_visibility="collapsed",
                key=f"porcentaje_{id_deuda}_forms_input"
            )

        with colMontoPropuesto:
            # Al no definir 'value', toma automáticamente el valor de st.session_state[key]
            st.text_input(
                "Monto Propuesto",
                disabled=st.session_state['usar_para_todos'],
                label_visibility="collapsed",
                key=f"monto_propuesto_{id_deuda}",
                help="Ingrese el Monto Propuesto para esta Deuda"
            )

        if tipo_cuotas == 'Por Deuda':
            with colCuotasCol: # type: ignore
                st.number_input(
                    "Número de Cuotas",
                    min_value=1,
                    max_value=60,
                    step=1,
                    label_visibility="collapsed",
                    key=f"num_cuotas_{id_deuda}",
                    help="Seleccione el número de cuotas para esta deuda"
                )

    # 7. Construcción de la Respuesta Final
    info_completa_deudas = []
    for _, row in deudas_activas_df_copy.iterrows():
        id_deuda = row['Id_Deuda']

        if tipo_cuotas == 'Por Deuda':
            cuotas_val = st.session_state.get(f"num_cuotas_{id_deuda}", 1)
        elif tipo_cuotas == 'Para Todas las Deudas':
            cuotas_val = num_cuotas_global
        else:
            cuotas_val = 1

        info_completa_deudas.append({
            "Id_Deuda": id_deuda,
            "Banco": row['Banco'],
            "Numero_Credito": row['Numero_Credito'],
            "Monto_Actual": row['PaB_Origen'],
            "Monto_Propuesto": cleanNumber(st.session_state[f"monto_propuesto_{id_deuda}"]),
            "Num_Cuotas": cuotas_val
        })

    return info_completa_deudas

def mostrar_alertas_masivas_deudas(*, deudas_info_list: list[dict[str, Any]]) -> bool:
    """
    Muestra alertas en Streamlit si alguna de las deudas seleccionadas tiene un monto propuesto menor al descuento base.
    
    Args:
        deudas_info (dict): Diccionario con Id_Deuda como clave y Monto Propuesto como valor.
    Returns:
        bool: True si alguna deuda cumple con la condición, False en caso contrario.
    """

    alguna_deuda_cumple = False  # Variable para verificar si alguna deuda cumple con la condición
    # Creamos deudas_info
    deudas_info = {deuda['Id_Deuda']: cleanNumber(deuda['Monto_Propuesto']) for deuda in deudas_info_list}
    with st.expander("Verificación de Descuentos en Base"):
        for deuda in deudas_info_list:
            cumple, mensaje = validar_descuento_base(deuda=deuda['Id_Deuda'], deudas_info=deudas_info)

            # Verificamos también que el monto propuesto no sea 0
            if deuda['Monto_Propuesto'] == 0:
                cumple = False
                mensaje = "El monto propuesto para esta deuda es 0, lo cual no es válido."

            colDeuda, colMensaje = st.columns([1, 4])

            with colDeuda:
                st.markdown(f"**Deuda**: {deuda['Id_Deuda']}")

            with colMensaje:
                if cumple:
                    st.success(mensaje, icon="✅")
                else:
                    st.error(mensaje, icon="❌")

            if cumple:
                alguna_deuda_cumple = True  # Al menos una deuda cumple con la condición

    return alguna_deuda_cumple

def mostrar_resumen_solicitud(*, 
        referencia: str,
        deudas_seleccionadas_df: DataFrame[DeudasActivasSchema],
        info_completa_deudas: list[dict[str, Any]],
        tipo_solicitud: str,
        nombre_aliado: str,
        fecha_esperada_pago: Optional[pd.Timestamp] = None,
        tipo_pago: Optional[str] = None,
        comentario: Optional[str] = None,
    ) -> None:
    st.subheader("📄 Resumen de la Solicitud")

    # Creamos 2 Columnas: Una para mostrar la Referencia y los datos de deudas y Otra para mostrar el Monto, Descuento y Tipo de Solicitud
    colResumen, colMonto = st.columns([5, 3], vertical_alignment="center")

    # Calculamos el Monto de la Solicitud y el Descuento que se tendría con respecto al Monto Original de las Deudas Seleccionadas
    montoTotal = sum(cleanNumber(deuda['Monto_Propuesto']) for deuda in info_completa_deudas)
    montoTotalOriginal = deudas_seleccionadas_df['PaB_Origen'].sum()
    descuentoTotal = 1 - (montoTotal / montoTotalOriginal) if montoTotalOriginal > 0 else 0

    with colResumen:
        st.metric(
            "Referencia del Cliente",
            value=referencia
        )
        # Ahora Vamos a Mostrar por Cada Deuda Seleccionada, el Monto Propuesto y el Número de Cuotas
        colIdDeuda, colMontoPropuesto, colNumCuotas = colResumen.columns([2, 2, 2], gap="small", border=True)
        with colIdDeuda:
            st.markdown("**Id Deuda**")
        with colMontoPropuesto:
            st.markdown("**Monto Propuesto**")
        with colNumCuotas:
            st.markdown("**Número de Cuotas**")

        for deuda in info_completa_deudas:
            with colIdDeuda:
                st.text(deuda['Id_Deuda'])
            with colMontoPropuesto:
                st.text('$'+formatNumber(deuda['Monto_Propuesto']))
            with colNumCuotas:
                st.text(deuda['Num_Cuotas'])


    with colMonto:
        st.metric(
            "Tipo de Solicitud",
            value=tipo_solicitud
        )
        st.metric(
            "Aliado",
            value=nombre_aliado
        )
        st.metric(
            label="Monto Total de la Solicitud",
            value=f"${montoTotal:,.0f}",
            delta=f"Descuento Total: {descuentoTotal:.2%}",
            delta_color="green" if descuentoTotal < 0.7 else "yellow" if descuentoTotal < 0.90 else "red"
        )

    # Ahora, si existe Fecha esperada de Pago y Tipo de Pago los Mostramos
    if fecha_esperada_pago and tipo_pago:
        st.markdown("#### ℹ️ **Detalles de Pago**")

        st.divider()

        colFechaEspPago, colTipoPago = st.columns(2, gap="large")

        with colFechaEspPago:
            # Calculamos la Diferencia en Días Hábiles a hoy
            diff_days = getBDDaysDiffFloat(
                fecha_esperada_pago.tz_localize(None),
                pd.Timestamp.now('America/Bogota').tz_localize(None)
                )
            st.metric(
                label="Fecha Esperada de Pago",
                value=fecha_esperada_pago.strftime("%Y-%m-%d"),
                border=True,
                delta = "En {:.2f} días hábiles".format(diff_days),
                delta_color="green" if diff_days > 5 else "yellow" if diff_days>=2 else "red",
            )
        with colTipoPago:
            st.metric(
                label="Tipo de Pago",
                value=tipo_pago,
                border=True,
                delta="Pagar si es exitosa",
                delta_color="green",
            )

    st.info(comentario or "Sin Comentario", title="Comentario de la Solicitud", icon="🫡")

# Diálogo de Confirmación para Subir una Solicitud con Saldo Negativo
@st.dialog("⚠️ Confirmar Subida de Solicitud", dismissible=True, width="large", on_dismiss="rerun")
def mostrar_dialogo_alerta_saldo(*,
        referencia: str,
        saldo_real: float,
        por_cobrar_real: float,
        ultima_actualizacion: Optional[pd.Timestamp],
        cumple_condicion_actualizacion: bool,
        dias_habiles_diff: float,
        min_dias_actualizacion: float,
    ) -> None:
    # Calculamos el Saldo Neto del Cliente (Saldo - Por Cobrar)
    saldo_neto = saldo_real - por_cobrar_real

    # Mostramos la Alerta de Poco Ahorro del Cliente
    st.error(
        "El cliente con Referencia **{}** presenta poco ahorro para cubrir el Por Cobrar (Saldo Neto: ${:,.0f}). ¿Está seguro de querer subir la solicitud?".format(referencia, saldo_neto),
        icon="⚠️",
    )

    # Mostramos el Saldo, el Por Cobrar y el Saldo Neto del Cliente
    colSaldo, colPorCobrar, colSaldoNeto = st.columns(3, vertical_alignment="center", border=True)

    with colSaldo:
        st.metric(
            label="**💰 Saldo del Cliente**",
            value="${:,.0f}".format(saldo_real),
            border=True,
        )

    with colPorCobrar:
        st.metric(
            label="**💸 Por Cobrar del Cliente**",
            value="${:,.0f}".format(por_cobrar_real),
            border=True,
        )

    with colSaldoNeto:
        st.metric(
            label="**📉 Saldo Neto (Saldo - Por Cobrar)**",
            value="${:,.0f}".format(saldo_neto),
            delta="Poco Ahorro" if saldo_neto <= 0 else None,
            delta_color="red",
            border=True,
        )

    st.divider()

    # Mostramos de Nuevo la Última Actualización de las Deudas Activas
    st.markdown("#### **ℹ️ Última Actualización de las Deudas Activas**")
    st.info('Última Actualización: {} (Hace {:.2f} días hábiles)'.format(
        ultima_actualizacion.strftime('%Y-%m-%d') if ultima_actualizacion else 'No Disponible',
        dias_habiles_diff,
    ))

    if not cumple_condicion_actualizacion:
        st.warning("La última actualización de las deudas activas fue hace {:.2f} días hábiles, lo cual es menor al mínimo necesario de {} días hábiles. Verifique nuevamente antes de subir la solicitud.".format(
            dias_habiles_diff, min_dias_actualizacion
        ))

    st.divider()

    # Creamos 2 Columnas: Confirmar y Cancelar la Solicitud
    colConfirmar, colCancelar = st.columns(2, vertical_alignment="center", gap="large")

    with colConfirmar:
        if st.button(
            label="**Confirmar Solicitud**",
            key="confirmar_solicitud_saldo",
            help="Presione este botón para confirmar y subir la solicitud.",
            type="primary",
            icon="✅",
            width="stretch",
        ):
            # Marcamos la Confirmación para que la Vista Suba la Solicitud
            st.session_state['confirmar_envio_saldo_bajo'] = True
            st.rerun()

    with colCancelar:
        if st.button(
            label="**Cancelar Solicitud**",
            key="cancelar_solicitud_saldo",
            help="Presione este botón para cancelar la subida de la solicitud.",
            type="secondary",
            icon="❌",
            width="stretch",
        ):
            st.session_state['confirmar_envio_saldo_bajo'] = False
            st.rerun()
