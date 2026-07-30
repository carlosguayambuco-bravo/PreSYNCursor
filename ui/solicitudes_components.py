# Estándar usando Pep8
# Librerías de Python
# Librerías de Terceros
import numpy as np
import pandas as pd
from pandera.typing import DataFrame
import streamlit as st
# Librerías Locales
from data.data_models import SolicitudesSchema
from modules.constants import ESTADOS_POSIBLES_SOLICITUD
from modules.forms import obtener_nombre_negociador

# Función para Mostrar los Filtros Generales de una Solicitud
def mostrar_filtros_generales_solicitud(*, solicitudes_df: DataFrame[SolicitudesSchema]) -> DataFrame[SolicitudesSchema]:

    # Lógica de Filtrado: Estado_Solicitud, Ejecutivo, Tipo de Solicitud, Banco

    return solicitudes_df

# Función para Mostrar los Datos de una Solicitud
def mostrar_datos_solicitud_ejecutivo(*,solicitud: pd.Series, is_main: bool = False) -> None:
    # Definimos el Nombre del Expander
    expander_name = "**Tipo**: {tipo} | **ID**: {id_solicitud} - {nombre_solicitante} | **Bancos**: {bancos} | **Fecha**: {fecha}".format(
        id_solicitud=solicitud["ID_Solicitud"],
        nombre_solicitante=obtener_nombre_negociador(email=solicitud["Correo"]),
        bancos=', '.join(np.unique([d['Banco'] for d in solicitud['Datos_Solicitud']])),
        fecha=solicitud["fecha"].strftime("%Y-%m-%d %H:%M"),
        tipo=solicitud["Tipo_Solicitud"],
    )

    aliados_posibles = list(st.session_state["aliados_dict"].keys()) + ['Directo Base']

    # Creamos un Expander para Mostrar los Datos de la Solicitud
    with st.expander(expander_name, expanded=is_main):
        # Escogencias Principales: Aliado y Estado de Solicitud
        colAliado, colEstado = st.columns(2)
        with colAliado:
            aliado_respuesta = st.selectbox(
                label="Aliado Escalado",
                options=aliados_posibles,
                index=aliados_posibles.index(solicitud["Casa_Cobro"]) if solicitud["Casa_Cobro"] in aliados_posibles else None,
                key=f"aliado_{solicitud['ID_Solicitud']}_input",
                help="Seleccione el aliado que otorgo respuesta para la(s) obligacion(es)",
            )

        with colEstado:
            estado_respuesta = st.selectbox(
                label="Estado de Solicitud",
                options=ESTADOS_POSIBLES_SOLICITUD,
                index=ESTADOS_POSIBLES_SOLICITUD.index(solicitud["Estado_Solicitud"]) if solicitud["Estado_Solicitud"] in ESTADOS_POSIBLES_SOLICITUD else None,
                key=f"estado_{solicitud['ID_Solicitud']}_input",
                help="Seleccione el estado de la solicitud que deseas dejar",
            )

        # Siguiente: Mostrar Selección de Pagos y Datos de Solicitud