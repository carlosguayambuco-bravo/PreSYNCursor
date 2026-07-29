# Estándar usando Pep8
# Librerías de Python
# Librerías de Terceros
from pandera.typing import DataFrame
import pandas as pd
import streamlit as st
# Librerías Locales
from data.data_models import DeudasActivasSchema
from data.data_loader import load_masivas, load_addendums
from modules.forms import obtener_descuento_base, validar_descuento_base

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

def poner_monto_por_deuda(deudas_activas_df: DataFrame[DeudasActivasSchema]) -> None:
    st.subheader("Montos Propuestos por Deuda")

    # Cargamos las Masivas y Addendums
    masivas_df = load_masivas()
    adds_df = load_addendums()

    # Creamos una Copia de las Deudas Activas
    deudas_activas_df_copy = deudas_activas_df.copy()

    # Agregamos la Columna %Total como PaB_Origen / Suma de PaB_Origen de todas las deudas activas
    deudas_activas_df_copy['%Total'] = deudas_activas_df_copy['PaB_Origen'] / deudas_activas_df_copy['PaB_Origen'].sum()

    # Inicializamos el Session State usar_para_todos
    if 'usar_para_todos' not in st.session_state:
        st.session_state['usar_para_todos'] = True

    # Vamos a crear: Un Input para Pago Total y un Selector para ver si usar ese monto para todos
    colPagoTotal, colUsarParaTodos = st.columns([2, 1])
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

    # Creamos las Columnas de la Tabla: Id_Deuda, PaB_Origen, Monto_Propuesto, %Total, Monto Propuesto (Input)
    colIdDeuda, colPaBOrigen, colProp, colPorcentaje, colMontoPropuesto = st.columns([2, 2, 2, 1, 2])

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
            if usar_para_todos:
                monto_propuesto = pago_total * row['%Total']
                st.number_input(
                    "", 
                    min_value=0.0, 
                    value=monto_propuesto, 
                    step=100.0, 
                    format="%.0f", 
                    key=f"monto_propuesto_{row['Id_Deuda']}", 
                    disabled=True
                )
            else:
                monto_propuesto = st.number_input(
                    "", 
                    min_value=0.0, 
                    value=row['PaB_Origen'], 
                    step=100.0, 
                    format="%.0f", 
                    key=f"monto_propuesto_{row['Id_Deuda']}"
                )

    # Ahora con todos los Montos Propuestos, actualizamos el Session State de pago_total
    if usar_para_todos:
        st.session_state['pago_total'] = pago_total
    else:
        st.session_state['pago_total'] = sum(
            st.session_state[f"monto_propuesto_{row['Id_Deuda']}"] for _, row in deudas_activas_df_copy.iterrows()
        )

def mostrar_alertas_masivas(*, deudas_info: dict[str, float]) -> bool:
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