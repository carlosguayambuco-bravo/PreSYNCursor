# Estándar usando Pep8
# Librerías de Python
# Librerías de Terceros
import streamlit as st
# Librerías Locales
from core.users import User

def show_user_info():
    # Primero Cargamos la Información del Usuario desde el estado de sesión
    user: User = st.session_state['user_obj']

    # Ahora vamos a Poner en el Sidebar:
    # Circulo Avatar con la Inicial del Nombre del Usuario
    st.sidebar.markdown(
        f"""
        <div style="display: flex; flex-direction: column; align-items: center; margin-bottom: 10px;">
            <div style="width: 40px; height: 40px; border-radius: 50%; background-color: #4CAF50; color: white; display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 18px;">
                {user.name[0].upper()}
            </div>
            <div style="margin-top: 8px; text-align: center;">
                <strong>{user.name}</strong><br>
                <span style="font-size: 12px; font-weight: normal; font-style: italic;">
                    {user.email}
                </span>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # Ahora añadimos Botón de Cerrar Sesión en el Sidebar
    if st.sidebar.button("Cerrar Sesión", icon="🚪"):
        # Limpiamos el estado de sesión
        st.session_state.clear()
        # Redirigimos al usuario a la página de login
        st.rerun()

    # Añadimos un Divisor al Sidebar para que no interfiera con las páginas de la aplicación
    st.sidebar.divider()