# Estándar usando Pep8
# Librerías de Python
# Librerías de Terceros
import streamlit as st
import pandas as pd

def rellenar_formulario():
    st.title("🗒️ Nuevo Formulario de Alianzas")
    st.divider()

    st.subheader("Referencia del Cliente")
    # -- Campos del Formulario

    # Referencia del Cliente
    referencia_cliente = st.text_input("Referencia del Cliente, Ejemplo: 3007083770", max_chars=20, help="Ingrese la referencia del cliente")

    # Validamos la Referencia
    if not referencia_cliente and not( 'referencia_cliente' in st.session_state and st.session_state['referencia_cliente']):
        st.error("La referencia del cliente es obligatoria")
        return

    # Limpiamos la Referencia
    referencia_cliente = [char for char in referencia_cliente.strip().replace('.0','') if char.isdigit()]
    referencia_cliente = ''.join(referencia_cliente)

    # La guardamos en el estado de sesión
    st.session_state['referencia_cliente'] = referencia_cliente