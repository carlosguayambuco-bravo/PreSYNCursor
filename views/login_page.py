# Estándar usando Pep8
# Librerías de Python
# Librerías de Terceros
import streamlit as st
# Librerías Locales
from core.auth import get_auth_url

def show_login_page():
    st.title("Bienvenido a la Aplicación de Gestión de Formularios")
    st.write("Por favor, inicia sesión con tu cuenta de Google para continuar.")
    st.write("Si no tienes una cuenta, por favor contacta al administrador.")

    # Botón para iniciar sesión con Google
    if st.button("Iniciar sesión con Google"):
        auth_url = get_auth_url()
        st.write(f"[Haz clic aquí para iniciar sesión]({auth_url})")