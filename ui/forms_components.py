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

def mostrar_seleccion_deudas(deudas_activas_df: DataFrame[DeudasActivasSchema]) -> list[str]:
    st.subheader("Deudas Activas del Cliente")
    st.info("Seleccione las deudas que desea incluir en el formulario de alianzas")

    # Van a ser 4 Columns: Checkbox de Seleccion, Id_Deuda, Banco, PaB_Origen
    colCH, colIdDeuda, colBanco, colPaBOrigen = st.columns([1, 2, 2, 2])

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
            selected = st.checkbox("", key=f"deuda_{row['Id_Deuda']}", value=True)
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
            st.text('${:,.0f}'.format(row['PaB_Origen']))

    # Definimos los Ids elegidos de las Deudas Seleccionadas
    deudas_seleccionadas = [deuda for deuda in deudas_activas_df['Id_Deuda'] if st.session_state.get(f"deuda_{deuda}", False)]

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
        st.session_state['pago_total'] = float(suma_pab * 0.6)

    for _, row in deudas_activas_df_copy.iterrows():
        key_monto = f"monto_propuesto_{row['Id_Deuda']}"
        key_cuotas = f"num_cuotas_{row['Id_Deuda']}"
        if key_monto not in st.session_state:
            st.session_state[key_monto] = float(st.session_state['pago_total'] * row['%Total'])
        if key_cuotas not in st.session_state:
            st.session_state[key_cuotas] = 1

    # 3. LÓGICA DE RECALCULO (Se ejecuta ANTES de dibujar los inputs en pantalla)
    if st.session_state['usar_para_todos']:
        # Si la opción "Distribuir" está activa, actualizamos el estado de cada deuda
        for _, row in deudas_activas_df_copy.iterrows():
            st.session_state[f"monto_propuesto_{row['Id_Deuda']}"] = float(
                st.session_state['pago_total'] * row['%Total']
            )
    else:
        # Si se edita individualmente, recalculamos el total como la suma de las deudas
        st.session_state['pago_total'] = float(sum(
            st.session_state[f"monto_propuesto_{row['Id_Deuda']}"] for _, row in deudas_activas_df_copy.iterrows()
        ))

    # 4. Renderizado de Controles Principales
    colPagoTotal, colUsarParaTodos, colCuotas = st.columns([2, 1, 1])

    with colPagoTotal:
        st.number_input(
            "Monto Total a Pagar",
            min_value=0.0,
            step=100.0,
            format="%.0f",
            key="pago_total",  # Vinculado directamente al Session State
            help="Ingresar el Monto a Pagar por todas las Deudas",
            disabled=not st.session_state['usar_para_todos']
        )

    with colUsarParaTodos:
        st.checkbox(
            "Distribuir el Monto entre Deudas",
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
        num_cuotas_global = st.slider(
            "Número de Cuotas",
            min_value=1,
            max_value=60,
            value=12,
            step=1,
            key="num_cuotas_global"
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

        with colIdDeuda:
            st.text(id_deuda)

        with colPaBOrigen:
            st.text('${:,.0f}'.format(row['PaB_Origen']))

        with colProp:
            descuento_base = obtener_descuento_base(deuda=id_deuda)
            if not pd.isna(descuento_base):
                st.text('${:,.0f}'.format(descuento_base))
            else:
                st.text("N/A")

        with colPorcentaje:
            st.text('{:.2%}'.format(row['%Total']))

        with colMontoPropuesto:
            # Al no definir 'value', toma automáticamente el valor de st.session_state[key]
            st.number_input(
                "",
                min_value=0.0,
                step=100.0,
                format="%.0f",
                disabled=st.session_state['usar_para_todos'],
                label_visibility="collapsed",
                key=f"monto_propuesto_{id_deuda}",
                help="Ingrese el Monto Propuesto para esta Deuda"
            )

        if tipo_cuotas == 'Por Deuda':
            with colCuotasCol: # type: ignore
                st.number_input(
                    "",
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
            "Monto_Propuesto": st.session_state[f"monto_propuesto_{id_deuda}"],
            "Num_Cuotas": cuotas_val
        })

    return info_completa_deudas

def mostrar_alertas_masivas_deudas(*, deudas_info: dict[str, float]) -> bool:
    """
    Muestra alertas en Streamlit si alguna de las deudas seleccionadas tiene un monto propuesto menor al descuento base.
    
    Args:
        deudas_info (dict): Diccionario con Id_Deuda como clave y Monto Propuesto como valor.
    Returns:
        bool: True si alguna deuda cumple con la condición, False en caso contrario.
    """

    alguna_deuda_cumple = False  # Variable para verificar si alguna deuda cumple con la condición
    with st.expander("Verificación de Descuentos en Base"):
        for deuda in deudas_info.keys():
            cumple, mensaje = validar_descuento_base(deuda=deuda, deudas_info=deudas_info)

            colDeuda, colMensaje = st.columns([1, 4])

            with colDeuda:
                st.markdown(f"**Deuda**: {deuda}")

            with colMensaje:
                if cumple:
                    st.success(mensaje)
                else:
                    st.error(mensaje)

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
    ) -> None:
    st.subheader("📄 Resumen de la Solicitud")

    # Creamos 2 Columnas: Una para mostrar la Referencia y los datos de deudas y Otra para mostrar el Monto, Descuento y Tipo de Solicitud
    colResumen, colMonto = st.columns([5, 2], vertical_alignment="center")

    # Calculamos el Monto de la Solicitud y el Descuento que se tendría con respecto al Monto Original de las Deudas Seleccionadas
    montoTotal = sum(deuda['Monto_Propuesto'] for deuda in info_completa_deudas)
    montoTotalOriginal = deudas_seleccionadas_df['PaB_Origen'].sum()
    descuentoTotal = 1 - (montoTotal / montoTotalOriginal) if montoTotalOriginal > 0 else 0

    with colResumen:
        st.metric(
            "Referencia del Cliente",
            value=referencia
        )
        # Ahora Vamos a Mostrar por Cada Deuda Seleccionada, el Monto Propuesto y el Número de Cuotas
        colIdDeuda, colMontoPropuesto, colNumCuotas = colResumen.columns([2, 2, 2], gap="small")
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
                st.text('${:,.0f}'.format(deuda['Monto_Propuesto']))
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
            delta_color="green" if descuentoTotal < 0.85 else "yellow" if descuentoTotal < 0.90 else "red"
        )

    # Ahora, si existe Fecha esperada de Pago y Tipo de Pago los Mostramos
    if fecha_esperada_pago and tipo_pago:
        st.markdown("#### ℹ️ **Detalles de Pago**")
        st.metric(
            label="Fecha Esperada de Pago",
            value=fecha_esperada_pago.strftime("%Y-%m-%d")
        )
        st.metric(
            label="Tipo de Pago",
            value=tipo_pago
        )