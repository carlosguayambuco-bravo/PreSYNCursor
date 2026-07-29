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

def mostrar_seleccion_deudas(deudas_activas_df: DataFrame[DeudasActivasSchema]) -> None:
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
            st.text('${:;.0f}'.format(row['PaB_Origen']))

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

    # Creamos una Copia de las Deudas Activas
    deudas_activas_df_copy = deudas_activas_df.copy()

    # Agregamos la Columna %Total como PaB_Origen / Suma de PaB_Origen de todas las deudas activas
    deudas_activas_df_copy['%Total'] = deudas_activas_df_copy['PaB_Origen'] / deudas_activas_df_copy['PaB_Origen'].sum()

    # Inicializamos el Session State usar_para_todos
    if 'usar_para_todos' not in st.session_state:
        st.session_state['usar_para_todos'] = True

    # Vamos a crear: Un Input para Pago Total ,un Selector para ver si usar ese monto como Portafolio
    # Y un tercero que es habilitar la Opción a Cuotas, individualmente para 1 deuda o para todas las deudas.
    colPagoTotal, colUsarParaTodos, colCuotas = st.columns([2, 1, 1])
    with colPagoTotal:
        pago_total = st.number_input(
            "Monto Total a Pagar",
            min_value=0.0,
            value=1000.0,
            step=100.0,
            format="%.0f",
            key="pago_total",
            help="Ingresar el Monto a Pagar por todas las Deudas",
            disabled=st.session_state['usar_para_todos']
        )
    with colUsarParaTodos:
        usar_para_todos = st.checkbox(
            "Distribuir el Monto entre Deudas",
            key="usar_para_todos",
            help="Si se selecciona, el Monto Total se distribuirá entre las deudas activas según su %Total. Si no se selecciona, se podrá ingresar un monto individual para cada deuda."
            )
    with colCuotas:
        tipo_cuotas = st.selectbox(
            "Habilitar Solicitud a Cuotas",
            options=["No", "Por Deuda", "Para Todas las Deudas"],
            key="tipo_cuotas",
            help="Si se selecciona, se podrá configurar el pago en cuotas para todas las Deudas o de forma Individual"
            )

    if tipo_cuotas == 'Para Todas las Deudas':
        # Mostramos un Slider para seleccionar el Número de Cuotas (1 a 60)
        num_cuotas = st.slider(
            "Número de Cuotas",
            min_value=1,
            max_value=60,
            value=12,
            step=1,
            key="num_cuotas",
            help="Seleccione el número de cuotas para el pago total"
        )

    # Creamos las Columnas de la Tabla: Id_Deuda, PaB_Origen, Monto_Propuesto, %Total, Monto Propuesto (Input), Cuotas (Input)
    if tipo_cuotas == 'Por Deuda':
        colIdDeuda, colPaBOrigen, colProp, colPorcentaje, colMontoPropuesto, colCuotas = st.columns([2, 2, 2, 1, 2, 2], gap = "small")
    else:
        colIdDeuda, colPaBOrigen, colProp, colPorcentaje, colMontoPropuesto = st.columns([2, 2, 2, 1, 2], gap = "small")

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
        with colCuotas:
            st.markdown("**Número de Cuotas**")

    for _, row in deudas_activas_df_copy.iterrows():
        with colIdDeuda:
            st.text(row['Id_Deuda'])

        with colPaBOrigen:
            st.text('${:;.0f}'.format(row['PaB_Origen']))

        with colProp:
            # Obtenemos el Descuento en Base
            descuento_base = obtener_descuento_base(deuda=row['Id_Deuda'])
            if not pd.isna(descuento_base):
                st.text('${:.0f}'.format(descuento_base))
            else:
                st.text("N/A")

        with colPorcentaje:
            st.text('{:.2%}'.format(row['%Total']))

        with colMontoPropuesto:
            st.number_input(
                "",
                min_value=0.0, 
                value=pago_total * row['%Total'],
                step=100.0, 
                format="%.0f", 
                key=f"monto_propuesto_{row['Id_Deuda']}",
                disabled=usar_para_todos,
            )
            if usar_para_todos:
                st.session_state[f"monto_propuesto_{row['Id_Deuda']}"] = pago_total * row['%Total']

        if tipo_cuotas == 'Por Deuda':
            with colCuotas:
                st.number_input(
                    "",
                    min_value=1,
                    max_value=60,
                    value=12,
                    step=1,
                    key=f"num_cuotas_{row['Id_Deuda']}",
                    help="Seleccione el número de cuotas para esta deuda"
                )

    # Ahora con todos los Montos Propuestos, actualizamos el Session State de pago_total
    if not usar_para_todos:
        st.session_state['pago_total'] = sum(
            st.session_state[f"monto_propuesto_{row['Id_Deuda']}"] for _, row in deudas_activas_df_copy.iterrows()
        )

    # Ahora Creamos la Lista de Información por Cada Deuda
    info_completa_deudas = []
    for _, row in deudas_activas_df_copy.iterrows():
        deuda_info = {
            "Id_Deuda": row['Id_Deuda'],
            "Monto_Propuesto": st.session_state[f"monto_propuesto_{row['Id_Deuda']}"],
            "Num_Cuotas": st.session_state.get(f"num_cuotas_{row['Id_Deuda']}", 1) if (tipo_cuotas == 'Por Deuda') else num_cuotas if (tipo_cuotas == 'Para Todas las Deudas') else 1
        }
        info_completa_deudas.append(deuda_info)

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
                st.text(f"**Deuda**: {deuda}")

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
                st.text('${:;.0f}'.format(deuda['Monto_Propuesto']))
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