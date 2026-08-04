# Estándar usando Pep8
# Librerías de Python
# Librerías de Terceros
import streamlit as st
# Librerías Locales
from core.auth import get_auth_url

def show_login_page():

    st.set_page_config(page_title="Login - Gestión de Alianzas", page_icon="🔏")

    st.title("😁Bienvenido a la Aplicación de Gestión de Alianzas")
    st.write("🔏Por favor, inicia sesión con tu cuenta de Google para continuar.")
    st.write("Si no tienes una cuenta, por favor contacta al administrador.")
    st.divider()

    # Botón para iniciar sesión con Google
    if not ("auth_url_generated" in st.session_state):
        auth_url = get_auth_url()
        st.session_state["auth_url_generated"] = True
        st.session_state["auth_url"] = auth_url
    else:
        auth_url = st.session_state["auth_url"]

    st.markdown(
    f"""
        <a href="{auth_url}" target="_self" style="text-decoration: none; display: block; width: 100%;">
            <button style="
                width: 100%;
                background-color: #FF4B4B;
                color: white;
                border: none;
                padding: 0.5rem 1rem;
                font-size: 1rem;
                font-weight: 500;
                border-radius: 0.5rem;
                cursor: pointer;
                transition: background-color 0.2s ease, border-color 0.2s ease;
                display: flex;
                align-items: center;
                justify-content: center;
                box-sizing: border-box;
                line-height: 1.6;
                font-family: Source Sans Pro, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
            "
            onmouseover="this.style.backgroundColor='#FF2B2B';"
            onmouseout="this.style.backgroundColor='#FF4B4B';"
            >
                🤐 Iniciar Sesión con Google
            </button>
        </a>
        """,
        unsafe_allow_html=True,
    )
    st.stop()  # Detenemos la ejecución del script hasta que el usuario se autentique