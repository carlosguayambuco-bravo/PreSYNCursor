# Estándar usando Pep8
# Librerías de Python
# Librerías de Terceros
import pandas as pd
import streamlit as st
# Librerías Locales

def mostrar_seleccion_deudas(deudas_activas_df: pd.DataFrame):
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