# Estándar usando Pep8
# Librerías de Python
# Librerías de Terceros
import streamlit as st
# Librerías Locales
from core.auth import authenticate_user
from core.permissions import get_permit_pages
from utils.initializer import initialize_services, initialize_test_states, initialize_data
from ui.login_components import show_user_info
from views.login_page import show_login_page

# Definimos si estamos en Modo Debugging
modo_debugging = st.secrets.get('debugging_mode',True)
st.set_page_config(layout="wide")

initialize_services(modo_debugging)  # Inicializamos los servicios de la aplicación

initialize_data(modo_debugging)  # Inicializamos los datos de la aplicación

# Inicializamos los estados de prueba o Aplicamos autenticación
if modo_debugging:
    initialize_test_states()
else:
    # Aquí se ejecuta la autenticación de Google
    authenticate_user()

# --- Usuario sin Autenticar ---
if not ('user_obj' in st.session_state):
    show_login_page()  # Mostramos la página de login
    st.stop()  # Detenemos la ejecución del script hasta que el usuario se autentique
else:
    # Usuario Autenticado
    show_user_info()  # Mostramos la información del usuario en la barra lateral
    # Obtenemos el Rol del Usuario
    user_role = st.session_state.user_obj.role
    # Obtenemos las Vistas para el Usuario
    user_permitted_pages = get_permit_pages(user_role)
    # Creamos la Navegación de Páginas según los Permisos del Usuario
    pg = st.navigation(user_permitted_pages)
    pg.run()  # Ejecutamos la página seleccionada por el usuario