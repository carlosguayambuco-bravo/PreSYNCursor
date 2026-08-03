# Estándar usando Pep8
# Librerías de Python
# Librerías de Terceros
import streamlit as st
# Librerías Locales
from core.auth import get_auth_url

st.title("😁Bienvenido a la Aplicación de Gestión de Alianzas")
st.write("🔏Por favor, inicia sesión con tu cuenta de Google para continuar.")
st.write("Si no tienes una cuenta, por favor contacta al administrador.")
st.divider()

# Botón para iniciar sesión con Google
link_url = get_auth_url()
st.link_button("Iniciar sesión con Google", link_url, icon='🗒️', width="stretch")
st.stop()  # Detenemos la ejecución del script hasta que el usuario se autentique