# Estándar usando Pep8
# Librerías de Python
# Librerías de Terceros
import streamlit as st
# Librerías Locales

# Vista para pruebas :b
# Prueba de Multiselect con format_func 
def format_prueba(selected: str):
    if selected == "JCAP":
        return "**JCAP** (*Selected*) :blue[Prueba]"
    return selected

st.multiselect(
    "Prueba de Selección",
    options=["JCAP","COVINOC"],
    format_func=format_prueba
)