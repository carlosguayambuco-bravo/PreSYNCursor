# Estándar usando Pep8
# Librerías de Python
# Librerías de Terceros
import streamlit as st
# Librerías Locales
from utils.initializer import initialize_services, initialize_test_states, initialize_data
from views.rellenar_forms import rellenar_formulario_view

# Definimos si estamos en Modo Debugging
modo_debugging = st.secrets.get('debugging_mode',True)
st.set_page_config(layout="wide")

initialize_services(modo_debugging)  # Inicializamos los servicios de la aplicación

initialize_data(modo_debugging)  # Inicializamos los datos de la aplicación

# Inicializamos los estados de prueba
initialize_test_states()

rellenar_formulario_view()  # Ejecutamos la vista principal para rellenar formularios