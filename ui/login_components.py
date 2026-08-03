# Estándar usando Pep8
# Librerías de Python
# Librerías de Terceros
import streamlit as st
# Librerías Locales
from core.users import User

def show_user_info():
    # Primero Cargamos la Información del Usuario desde el estado de sesión
    user: User = st.session_state['user_obj']