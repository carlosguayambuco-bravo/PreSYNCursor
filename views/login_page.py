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

    st.link_button("Iniciar sesión con Google", url=auth_url, type="primary", width="stretch", icon="🔏")

    st.space("medium")
    # Creamos un Botón para volver a generar el enlace de autenticación en caso de que el usuario no pueda iniciar sesión
    if st.button("🔄 Volver a generar enlace de autenticación",type="secondary",width="stretch"):
        auth_url = get_auth_url()
        st.session_state["auth_url"] = auth_url
        st.session_state["auth_url_generated"] = True
        st.toast("Enlace de autenticación regenerado. Por favor, intenta iniciar sesión nuevamente.",icon="🔄")

    st.stop()