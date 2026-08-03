# Estándar usando Pep8
# Librerías de Python
# Librerías de Terceros
import streamlit as st
# Librerías Locales

def error_page_view(error_message: str):
    """Muestra una página de error en Streamlit con un mensaje personalizado."""
    st.set_page_config(page_title="Error", layout="centered")
    st.error(f"Ha ocurrido un error: {error_message}")
    st.stop()