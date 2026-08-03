# Estándar usando Pep8
# Librerías de Python
# Librerías de Terceros
import streamlit as st
# Librerías Locales
from data.data_loader import load_logs

st.title("😎Logs de la Aplicación")
st.divider()

# Cargamos los Logs
active_logs_df = load_logs()
st.toast("Se han cargado los logs de la aplicación desde Google Sheets.", icon="✅")

# Creamos 4 Columnas para mostrar los Logs
colTimestamp, colUser, colAction, colDetails = st.columns([1, 1, 1, 2])

# Iteramos por cada uno de los datos
for index, row in active_logs_df.iterrows():
    with colTimestamp:
        st.code(row["Timestamp"].strftime("%Y-%m-%d %H:%M:%S"), language="text")
    with colUser:
        st.code(row["Usuario"], language="text")
    with colAction:
        st.code(row["Motivo"], language="text")
    with colDetails:
        st.write(row["Detalle"])

st.divider()
st.markdown("""
    **Nota:** Los logs de la aplicación se almacenan en Google Sheets para fines de auditoría y seguimiento de acciones. Cada acción realizada por los usuarios se registra con un timestamp, el usuario que realizó la acción, el motivo de la acción y detalles adicionales si es necesario.
    ### **😁No hay más Logs**
""")