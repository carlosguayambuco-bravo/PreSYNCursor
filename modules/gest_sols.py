# Estándar usando Pep8
# Librerías de Python
import json
import re
from typing import Literal, Any, Hashable, Optional
from io import BytesIO
# Librerías de Terceros
import numpy as np
import pandas as pd
from pandera.typing import DataFrame
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, TextStringObject
from pypdf.errors import FileNotDecryptedError, WrongPasswordError
import streamlit as st
# Librerías Locales
from data.data_loader import load_current_month_solicitudes, load_headcount_negociacion, load_liquidaciones, load_masivas
from data.data_uploader import update_massive_solicitudes_in_google_sheets, update_solicitud_in_google_sheets, upload_log_to_sheets, upload_massive_solicitudes_filtered_plantilla, upload_addendum_debt
from data.data_models import MasivasSchema, PlantillaSolicitudesSchema
from modules.classes import get_banned_manager
from modules.constants import EMAIL_SUBJECT_MAPPER, EMAIL_BODY_GENERAL, DEFAULT_CCS, CCS_CREDITO
from modules.forms import obtener_correo_lider_negociador, obtener_nombre_negociador
from services import GoogleDriveService, GoogleMailService
from utils.helpers_general import cleanNumber, formatNumber, getBDDaysDiffFloat_vectorized

METADATA_ESPECIALES_DISTRIBUIR = ['Max_Descuento_Otorgado','Addendums','Fecha_Solicitado','Id_Acuerdo_Pago']

def get_solicitud_txt(solicitud: pd.Series, origen: Literal['Datos_Solicitud','JSON_Respuesta'] = 'Datos_Solicitud') -> str:
    """
    Genera un texto descriptivo para una solicitud específica.

    Args:
        solicitud (pd.Series): Información de la solicitud.

    Returns:
        str: Texto descriptivo de la solicitud. Este str es bajo la Siguiente Plantilla:
        **Tipo de Solicitud**: {}
        **Cedula**: {}
        **Nombre del Cliente**: {}
        **Relación de Deudas**:
            - **Banco**: {}, **Numero_Credito**: {}, **Monto_Propuesto**: {}, (**Num_Cuotas**, si hay): {}
    """
    # Paso 1: Añadir los datos principales de la solicitud
    solicitud_txt = f"**Tipo de Solicitud**: {solicitud['Tipo_Solicitud']}\n"
    solicitud_txt += f"**Cedula**: {solicitud['Cedula']}\n"
    solicitud_txt += f"**Nombre del Cliente**: {solicitud['Metadata_Solicitud']['Nombre_Cliente']}\n"
    solicitud_txt += f"**Relación de Deudas**:\n"

    # Paso 2: Iterar sobre cada deuda en la solicitud y añadir sus detalles
    for deuda in solicitud[origen]:
        solicitud_txt += f"    - **Banco**: {deuda['Banco']}, **Numero_Credito**: {deuda['Numero_Credito']}, **Monto_Propuesto**: ${formatNumber(deuda['Monto_Propuesto'])}"
        if deuda.get('Num_Cuotas', 1) > 1:
            solicitud_txt += f", (**Num_Cuotas**: {deuda['Num_Cuotas']})"
        solicitud_txt += "\n"

    return solicitud_txt

def get_massive_solicitudes_txt(solicitudes_df: pd.DataFrame) -> str:
    """
    Genera un texto descriptivo para un conjunto de solicitudes.

    Args:
        solicitudes_df (pd.DataFrame): DataFrame con las solicitudes.

    Returns:
        str: Texto descriptivo de todas las solicitudes. Este str es bajo la Siguiente Plantilla:
        **Tipo de Solicitud**: {}
        **Cedula**: {}
        **Nombre del Cliente**: {}
        **Relación de Deudas**:
            - **Banco**: {}, **Numero_Credito**: {}, **Monto_Propuesto**: {}, (**Num_Cuotas**, si hay): {}
    """
    # Paso 1: Inicializar el texto masivo
    massive_txt = []

    # Paso 2: Iterar sobre cada solicitud y añadir su descripción
    for _, solicitud in solicitudes_df.iterrows():
        massive_txt += [get_solicitud_txt(solicitud)]

    return "\n___\n".join(massive_txt)

def get_descuento_en_base(*, debt: str, original_amount: float) -> list[str]:
    """
    Obtiene el descuento en base de datos para una deuda específica.

    Args:
        debt (str): Identificador de la deuda.
        original_amount (float): Monto original de la deuda.

    Returns:
        list[str]: Lista de descuentos en base de datos. Formato 'Casa Cobro - Valor - Descuento - Es Portafolio'.
        Este formato se aplica para todos los Descuentos que se encuentren
    """
    # Paso 1: Cargar los Descuentos
    descuentos_df: DataFrame[MasivasSchema] = load_masivas()
    # Paso 2: Buscar los Descuentos para la Deuda Específica
    descuentos_deuda = descuentos_df[descuentos_df['Id_Deuda'] == debt]
    # Si el DF esta vacío, retornamos una lista vacía
    if descuentos_deuda.empty:
        return []

    # Paso 3: Crear el Formato para los Descuentos
    descuentos_formateados = []
    for _, row in descuentos_deuda.iterrows():
        casa_cobro = row['Casa_Cobro']
        valor = row['PaB_Propuesta']
        descuento = 1 - valor / original_amount if original_amount != 0 else 0
        monto_portafolio = row["PaB_Portafolio"]
        es_portafolio = "SI" if (pd.notna(monto_portafolio) and monto_portafolio > 0) else "No"
        if es_portafolio == "SI":
            str_portafolio = f"**Portafolio**: {monto_portafolio:,.0f}"
        else:
            str_portafolio = "***No es Portafolio***"
        descuento_formateado = f"(*{debt}*) **{casa_cobro}**: {valor:,.0f} ({descuento:.1%}) - {str_portafolio}"
        descuentos_formateados.append(descuento_formateado)

    return descuentos_formateados

def es_solicitud_sin_responder(solicitud: pd.Series) -> bool:
    """
    Determina si una solicitud específica no ha sido respondida.

    Args:
        solicitud (pd.Series): Información de la solicitud.

    Returns:
        bool: True si la solicitud no ha sido respondida, False en caso contrario.
    """
    maskSinTocar = (solicitud["Estado_Solicitud"] == "Sin Tocar") | (solicitud["Estado_Solicitud"] == "Solicitado")
    maskBajoComite = solicitud["Metadata_Solicitud"].get("Estado_Comite", 0) == 3 and solicitud["Estado_Solicitud"] == "Bajo Comité"
    maskTitularIlocalizable = solicitud["Metadata_Solicitud"].get("Estado_Titular_Ilocalizable", 0) == 3 and solicitud["Estado_Solicitud"] == "Titular Ilocalizable"
    maskActual = not solicitud['Es_Historico']
    banner_manager = get_banned_manager()
    maskSinBan = (not banner_manager.is_banned(solicitud["ID_Solicitud"]))
    return (maskSinTocar or maskBajoComite or maskTitularIlocalizable) and maskSinBan and maskActual

def es_solicitud_aprobacion_necesaria(solicitud: pd.Series) -> bool:
    """
    Determina si una solicitud específica requiere aprobación.

    Args:
        solicitud (pd.Series): Información de la solicitud.

    Returns:
        bool: True si la solicitud requiere aprobación, False en caso contrario.
    """
    maskAprobComite = (solicitud["Metadata_Solicitud"].get("Estado_Comite", 0) == 1) and (solicitud["Estado_Solicitud"] == "Bajo Comité")
    maskAprobIlocalizado = (solicitud["Metadata_Solicitud"].get("Estado_Titular_Ilocalizable", 0) == 1) and (solicitud["Estado_Solicitud"] == "Titular Ilocalizable")
    return (maskAprobComite or maskAprobIlocalizado)

def es_acuerdo_reasignable(solicitud: pd.Series) -> Optional[bool]:
    """Determina si una solicitud de acuerdo de pago específica es reasignable

    Args:
        solicitud (pd.Series): Información de la Solicitud

    Returns:
        Optional[bool]: True si la solicitud es reasignable, False en caso contrario. None si no aplica
    """    
    # Paso 1: Verificar que sea de Acuerdo y Exitosa, y que no sea Histórica y que no este liquidada
    if solicitud['Estado_Solicitud'] != "Exitosa" or solicitud['Tipo_Solicitud'] == 'Validación' or solicitud['Es_Historico'] or ("Liquidado" in (obtener_estado_liquidacion(solicitud=solicitud) or "a")):
        return None
    # Paso 2: Verificamos que la Fecha_Limite_Pago no se haya cumplido
    elif solicitud['Fecha_Limite_Pago'].normalize() >= pd.Timestamp.now('America/Bogota').tz_localize(None).normalize():
        return False
    else: # De caso contrario si es Reasignable
        return True

def obtener_tipo_aprobacion_necesaria(solicitud: pd.Series) -> Optional[Literal["Comité", "Titular Ilocalizable"]]:
    """
    Determina el tipo de aprobación necesaria para una solicitud específica.

    Args:
        solicitud (pd.Series): Información de la solicitud.

    Returns:
        Optional[Literal["Comité", "Titular Ilocalizable"]]: Tipo de aprobación necesaria ("Comité" o "Titular Ilocalizable") o None si no requiere aprobación.
    """
    if (solicitud["Metadata_Solicitud"].get("Estado_Comite", 0) == 1) and (solicitud["Estado_Solicitud"] == "Bajo Comité"):
        return "Comité"
    elif (solicitud["Metadata_Solicitud"].get("Estado_Titular_Ilocalizable", 0) == 1) and (solicitud["Estado_Solicitud"] == "Titular Ilocalizable"):
        return "Titular Ilocalizable"
    else:
        return None

def obtener_mascara_sin_responder(solicitudes_df: pd.DataFrame) -> pd.Series:
    """
    Filtra las solicitudes que no han sido respondidas.

    Args:
        solicitudes_df (pd.DataFrame): DataFrame con todas las solicitudes.

    Returns:
        pd.Series: Serie con las solicitudes sin responder.
    """
    maskSinTocar = (solicitudes_df["Estado_Solicitud"] == "Sin Tocar") | (solicitudes_df["Estado_Solicitud"] == "Solicitado")
    maskBajoComite = solicitudes_df["Metadata_Solicitud"].apply(lambda x: x.get("Estado_Comite", 0) == 3) & (solicitudes_df["Estado_Solicitud"] == "Bajo Comité")
    maskTitularIlocalizable = solicitudes_df["Metadata_Solicitud"].apply(lambda x: x.get("Estado_Titular_Ilocalizable", 0) == 3) & (solicitudes_df["Estado_Solicitud"] == "Titular Ilocalizable")
    banner_manager = get_banned_manager()
    maskActual = ~(solicitudes_df['Es_Historico'])
    maskSinBan = solicitudes_df["ID_Solicitud"].apply(lambda x: not banner_manager.is_banned(x))
    return (maskSinTocar | maskBajoComite | maskTitularIlocalizable) & maskSinBan & maskActual

def obtener_mascara_exitosas(solicitudes_df: pd.DataFrame) -> pd.Series:
    """
    Filtra las solicitudes que han sido respondidas exitosamente.

    Args:
        solicitudes_df (pd.DataFrame): DataFrame con todas las solicitudes.

    Returns:
        pd.Series: Serie con las solicitudes exitosas.
    """
    return solicitudes_df["Estado_Solicitud"] == "Exitosa"

def obtener_mascara_reasignable(solicitudes_df: pd.DataFrame) -> pd.Series:
    """Filtra las Solicitudes con Posibilidad de Reasignación ante Acuerdos Caídos

    Args:
        solicitudes_df (pd.DataFrame): DataFrame con todas las solicitudes.

    Returns:
        pd.Series: Serie con las solicitudes reasignables (Acuerdos de Pago con Fecha_Limite_Pago Vencida).
    """
    # Creamos 5 Máscaras:
    # Máscara 1: Tipo de Solicitud
    maskTipo = (solicitudes_df['Tipo_Solicitud'] != 'Validación')
    # Máscara 2: Exitosa
    maskExitosa = (solicitudes_df["Estado_Solicitud"] == "Exitosa")
    # Máscara 3: Fecha Vencida
    maskVencida = solicitudes_df['Fecha_Limite_Pago'].dt.normalize() < pd.Timestamp.now('America/Bogota').tz_localize(None).normalize()
    # Máscara 4: Que no sea Histórica
    maskHist = ~(solicitudes_df['Es_Historico'])
    # Máscara 5: Que no sea Liquidado
    maskLiq = solicitudes_df.apply(lambda r: obtener_estado_liquidacion(solicitud=r),axis=1) == "Sin Liquidar" # type: ignore
    # Devolvemos la Consecución de Estas
    return maskTipo & maskExitosa & maskVencida & maskHist & maskLiq

def obtener_estado_liquidacion(*, solicitud: pd.Series) -> Optional[Literal["Sin Liquidar", "Liquidado Parcial", "Liquidado Total"]]:
    """
    Obtiene el Estado de Liquidación de una Solicitud Exitosa de Acuerdo de Pago u Oferta de Acuerdo.

    Args:
        solicitud (pd.Series): Información de la solicitud.

    Returns:
        Optional[Literal["Sin Liquidar", "Liquidado Parcial", "Liquidado Total"]]:
            - "Sin Liquidar": Ningún Id_Deuda de la Respuesta está en las Liquidaciones.
            - "Liquidado Parcial": Algunos Ids de la Respuesta están en las Liquidaciones, pero no todos.
            - "Liquidado Total": Todos los Ids de la Respuesta están en las Liquidaciones.
            - None: Si la Solicitud no es Exitosa o no es de tipo Acuerdo de Pago u Oferta de Acuerdo,
                o si no tiene Ids de Deuda en la Respuesta.
    """
    # Solo Aplica para Solicitudes Exitosas
    if (solicitud['Estado_Solicitud'] != 'Exitosa'):
        return None

    # Paso 1: Obtener los Ids de Deuda de la Respuesta
    json_respuesta = solicitud['JSON_Respuesta']
    if not isinstance(json_respuesta, list):
        return None
    ids_respuesta = [str(d['Id_Deuda']) for d in json_respuesta]
    if not ids_respuesta:
        return None

    # Paso 2: Cargar los Ids de Deuda Liquidados
    liquidaciones_ids: set[str] = load_liquidaciones()

    # Paso 3: Contar cuántos Ids de la Respuesta están Liquidados
    num_liquidados = sum(1 for id_deuda in ids_respuesta if id_deuda in liquidaciones_ids)

    # Paso 4: Determinar el Estado de Liquidación
    if num_liquidados == 0:
        return "Sin Liquidar"
    elif num_liquidados == len(ids_respuesta):
        return "Liquidado Total"
    else:
        return "Liquidado Parcial"

def obtener_mascara_aprobacion_necesaria(solicitudes_df: pd.DataFrame) -> pd.Series:
    """
    Filtra las solicitudes que requieren aprobación.

    Args:
        solicitudes_df (pd.DataFrame): DataFrame con todas las solicitudes.

    Returns:
        pd.Series: Serie con las solicitudes que requieren aprobación.
    """
    maskAprobComite = solicitudes_df["Metadata_Solicitud"].apply(lambda x: x.get("Estado_Comite", 0) == 1) & (solicitudes_df["Estado_Solicitud"] == "Bajo Comité")
    maskAprobIlocalizado = solicitudes_df["Metadata_Solicitud"].apply(lambda x: x.get("Estado_Titular_Ilocalizable", 0) == 1) & (solicitudes_df["Estado_Solicitud"] == "Titular Ilocalizable")
    return (maskAprobComite | maskAprobIlocalizado)

def actualizar_aprobacion_necesaria(*,solicitud: pd.Series, tipo_aprobacion: Optional[Literal["Comité", "Titular Ilocalizable"]], aprobado: bool, comentario: str = "") -> bool:
    """
    Actualiza el estado de aprobación de una solicitud específica.

    Args:
        solicitud (pd.Series): Información de la solicitud.
        aprobado (bool): Indica si la solicitud fue aprobada o no.
        comentario (str): Comentario del Negociador que enriquece el entendimiento de la aprobación o rechazo.

    Returns:
        bool: True si la actualización fue exitosa, False en caso contrario.
    """
    # Si no se conoce el tipo de aprobación se muestra un error y ya
    if tipo_aprobacion is None:
        st.error("No se puede actualizar la aprobación de la solicitud porque no se conoce el tipo de aprobación necesaria.")
        return False
    # Paso 1: Definir la Llave de Metadata según el Tipo de Aprobación
    llave_metadata = "Estado_Comite" if tipo_aprobacion == "Comité" else "Estado_Titular_Ilocalizable"
    # Paso 2: Actualizar el Estado (2 = Rechazado, 3 = Aprobado)
    solicitud['Metadata_Solicitud'][llave_metadata] = 3 if aprobado else 2
    # Paso 2.1: Actualizar el Comentario del Negociador con el Comentario de la Aprobación o Rechazo
    solicitud['Metadata_Solicitud']["Comentario_Negociador"] = comentario

    # Paso 3: Actualizar la Solicitud en Google Sheets
    return update_solicitud_in_google_sheets(solicitud=solicitud)

def distribuir_resultado_solicitud(
        *,
    solicitud: pd.Series,
    pdf_bytes: Optional[bytes] = None,
    casa_cobro_old: Optional[str] = None
    ) -> bool:
    """
    Distribuye el resultado de la solicitud a las diferentes solicitudes disponibles

    Args:
        solicitud (pd.Series): Información de la solicitud.
        pdf_bytes (Optional[bytes]): Los bytes del PDF del Acuerdo de Pago
        casa_cobro_old (Optional[str]): La Casa antigua de la Solicitud (Si cambia 
        se responden las solicitudes con casas iguales)

    Returns:
        bool: True si la distribución fue exitosa, False en caso contrario.
    """

    # Paso 2: Actualizar Solicitudes con mismas deudas, misma Casa_Cobro y mismo Tipo_Solicitud (Sin Responder)
    solicitudes_df = load_current_month_solicitudes()
    idsFinal = '-'.join([d['Id_Deuda'] for d in solicitud['JSON_Respuesta']])
    maskIds = (solicitudes_df['Ids_Deuda'] == idsFinal)
    maskCasa = (solicitudes_df['Casa_Cobro'] == solicitud['Casa_Cobro']) | (solicitudes_df['Casa_Cobro'] == casa_cobro_old)
    if solicitud['Tipo_Solicitud'] == 'Validación':
        maskTipo = (solicitudes_df['Tipo_Solicitud'] == solicitud['Tipo_Solicitud'])
    elif solicitud['Tipo_Solicitud'] in ['Oferta de Acuerdo','Acuerdo de Pago']:
        maskTipo = ((solicitud['Estado_Solicitud'] == 'Exitosa')) | (solicitud['Tipo_Solicitud'].isin(['Oferta de Acuerdo','Acuerdo de Pago']))
    maskSinResponder = obtener_mascara_sin_responder(solicitudes_df)
    maskDiffID = (solicitudes_df['ID_Solicitud'] != solicitud['ID_Solicitud'])
    maskFinal = maskIds & maskCasa & maskTipo & maskSinResponder & maskDiffID

    solicitud['Metadata_Solicitud']['Id_Respuesta_Autom'] = solicitud['ID_Solicitud']

    updated_ids = set() # Inicializamos el Set de IDs Actualizados
    need_update_rows = [solicitud] # Inicializamos la lista de filas que necesitan ser actualizadas con la solicitud actual
    for _, solicitud_to_update in solicitudes_df[maskFinal].iterrows():

        # Verificamos que no sea la solicitud actual, de lo contrario se salta la actualización
        if solicitud_to_update['ID_Solicitud'] == solicitud['ID_Solicitud']:
            continue

        solicitud_to_update['Estado_Solicitud'] = solicitud['Estado_Solicitud']
        solicitud_to_update['Metadata_Solicitud']['Metodo_Pago'] = solicitud['Metadata_Solicitud'].get('Metodo_Pago', '')
        solicitud_to_update['Metadata_Solicitud']['Comentario_Ejecutivo'] = solicitud['Metadata_Solicitud'].get('Comentario_Ejecutivo', '')
        solicitud_to_update['Metadata_Solicitud']['Pago_Total_Obligatorio'] = solicitud['Metadata_Solicitud'].get('Pago_Total_Obligatorio', True)
        solicitud_to_update['JSON_Respuesta'] = solicitud.get('JSON_Respuesta', '')
        solicitud_to_update['Fecha_Limite_Pago'] = solicitud.get('Fecha_Limite_Pago', '')
        solicitud_to_update['Ejecutivo'] = solicitud['Ejecutivo']
        solicitud_to_update['Fecha_Respuesta'] = solicitud['Fecha_Respuesta']

        # Guardamos un trace en la Metadata
        solicitud_to_update['Metadata_Solicitud']['Id_Respuesta_Autom'] = solicitud['ID_Solicitud']

        for key in METADATA_ESPECIALES_DISTRIBUIR:
            if key in solicitud['Metadata_Solicitud']:
                solicitud_to_update['Metadata_Solicitud'][key] = solicitud['Metadata_Solicitud'][key]

        # Agregamos el ID de la Solicitud Actualizada al Set de IDs Actualizados
        updated_ids.add(solicitud_to_update['ID_Solicitud'])
        need_update_rows.append(solicitud_to_update)

    # Verificación Intermedia: Si la solicitud no es Exitosa, no hay posiblidad de Sub-Solicitudes, entonces se deja así

    # Paso 3: Actualizar Sub-Solicitdues si no es necesario el Pago Total Obligatorio y si es Exitosa y si es Validación
    if (not solicitud['Metadata_Solicitud'].get('Pago_Total_Obligatorio', True)) and (solicitud['Estado_Solicitud'] == 'Exitosa') and (solicitud['Tipo_Solicitud'] == 'Validación'):

        # Paso 3.1 Obtener las Sub-Solicitudes de la Solicitud Actual
        # Estás son solicitudes que tienen un subconjunto de los IDs de Deuda de la Solicitud Actual
        # Para esto necesitamos una Máscara que verifique que los IDs de Deuda de la Sub-Solicitud estén contenidos en los IDs de Deuda de la Solicitud Actual
        ids_solicitud_actual = set(d['Id_Deuda'] for d in solicitud['JSON_Respuesta'])
        mask_sub_solicitudes = solicitudes_df['Datos_Solicitud'].apply(lambda x: set(d['Id_Deuda'] for d in x).issubset(ids_solicitud_actual))
        # Creamos la Máscara como: mask_sub_solicitudes & maskCasa & maskTipo & maskSinResponder
        mask_sub_solicitudes_final = mask_sub_solicitudes & maskCasa & maskTipo & maskSinResponder & maskDiffID

        for _,sub_solicitud in solicitudes_df[mask_sub_solicitudes_final].iterrows():

            # Verificamos que no sea la solicitud actual, de lo contrario se salta la actualización
            if sub_solicitud['ID_Solicitud'] == solicitud['ID_Solicitud']:
                continue

            ids_solicitud_actual = set(d['Id_Deuda'] for d in sub_solicitud['Datos_Solicitud'])
            sub_solicitud['Estado_Solicitud'] = solicitud['Estado_Solicitud']
            sub_solicitud['Metadata_Solicitud']['Metodo_Pago'] = solicitud['Metadata_Solicitud'].get('Metodo_Pago', '')
            sub_solicitud['Metadata_Solicitud']['Comentario_Ejecutivo'] = solicitud['Metadata_Solicitud'].get('Comentario_Ejecutivo', '')
            sub_solicitud['Metadata_Solicitud']['Pago_Total_Obligatorio'] = solicitud['Metadata_Solicitud'].get('Pago_Total_Obligatorio', True)
            sub_solicitud['JSON_Respuesta'] = [ d for d in solicitud['JSON_Respuesta'] if d['Id_Deuda'] in ids_solicitud_actual ]
            sub_solicitud['Fecha_Limite_Pago'] = solicitud['Fecha_Limite_Pago']
            sub_solicitud['Ejecutivo'] = solicitud['Ejecutivo']
            sub_solicitud['Fecha_Respuesta'] = solicitud['Fecha_Respuesta']

            # Guardamos un trace en la Metadata
            sub_solicitud['Metadata_Solicitud']['Id_Respuesta_Autom'] = solicitud['ID_Solicitud']

            for key in METADATA_ESPECIALES_DISTRIBUIR:
                if key in solicitud['Metadata_Solicitud']:
                    sub_solicitud['Metadata_Solicitud'][key] = solicitud['Metadata_Solicitud'][key]

            # Agregamos el ID de la Sub-Solicitud Actualizada al Set de IDs Actualizados
            updated_ids.add(sub_solicitud['ID_Solicitud'])

            # Agregamos la Sub-Solicitud a la lista de filas que necesitan ser actualizadas
            need_update_rows.append(sub_solicitud)

    # Volvemos todas las que necesitan actualizaciones un DF (concatenar preservando tipos de datos)
    if need_update_rows:
        need_update_df = pd.concat(need_update_rows, axis=1).T.reset_index(drop=True)
    else:
        need_update_df = pd.DataFrame()

    # Si la Solicitud Inicial es Exitosa, Es Acuerdo de Pago u Oferta de Acuerdo y tenemos bytes del PDF
    # Se envia el correo correspondiente
    if solicitud['Estado_Solicitud'] == 'Exitosa' and solicitud['Tipo_Solicitud'] in ['Acuerdo de Pago', 'Oferta de Acuerdo'] and pdf_bytes is not None:
        # Definimos la Key del Session State para rastrear el Estado del Envío del Correo
        key_correo_enviado = 'correo_acuerdo_enviado_{}'.format(solicitud['ID_Solicitud'])
        # Verificamos si el Correo ya fue enviado en un intento anterior para no duplicarlo
        if st.session_state.get(key_correo_enviado, False):
            st.info("El correo con el Acuerdo de Pago ya fue enviado anteriormente, por lo que no se volverá a enviar.", icon="📧")
        elif send_email_acuerdos(solicitudes=need_update_rows, pdf_bytes=pdf_bytes):
            # Guardamos el Estado del Envío del Correo en el Session State
            st.session_state[key_correo_enviado] = True
        else:
            st.error("No se pudo enviar el correo con el Acuerdo de Pago. Reintentar", icon="❌")
            st.stop()
    elif pdf_bytes is None and solicitud['Estado_Solicitud'] == 'Exitosa' and solicitud['Tipo_Solicitud'] in ['Acuerdo de Pago', 'Oferta de Acuerdo']:
        st.warning("No se generó un PDF para el Acuerdo de Pago. Por favor, contacte al equipo de soporte.", icon="⚠️")

    # Por Último, devolvemos la actualización masiva
    success = update_massive_solicitudes_in_google_sheets(solicitudes_df=need_update_df)

    # Si se ejecutó la actualización y el estado es exitoso, se añaden los ids al banned_manager
    if success and solicitud['Estado_Solicitud'] == 'Exitosa':
        banned_manager = get_banned_manager()
        for id_solicitud in updated_ids:
            banned_manager.ban(id_solicitud)
        # Añadimos el ID de la solicitud original
        banned_manager.ban(solicitud['ID_Solicitud'])

    return success

def redistribuir_resultado_solicitud(
        *,
    solicitud: pd.Series, 
    pdf_bytes: Optional[bytes] = None,
    casa_cobro_old: Optional[str] = None,
    ) -> bool:
    """
    Re-Distribuye el resultado actualizado de una solicitud a las Solicitudes Espejo
    que comparten el mismo 'Id_Respuesta_Autom'. Si la solicitud es Exitosa y es de
    tipo Acuerdo de Pago u Oferta de Acuerdo, envía el correo de ajuste con el PDF.

    Args:
        solicitud (pd.Series): Información de la solicitud actualizada.
        pdf_bytes (Optional[bytes]): Bytes del PDF del Acuerdo de Pago ajustado.
        casa_cobro_old: Optional[str]: Casa de Cobro Antigua. no se usa, se 
        mantiene por compatibilidad con mostrar_boton_actualizar_solicitudes

    Returns:
        bool: True si la re-distribución fue exitosa, False en caso contrario.
    """
    # Paso 1: Cargar las Solicitudes del Mes en Curso
    solicitudes_df = load_current_month_solicitudes()

    # Paso 2: Inicializamos la Lista de Filas a Actualizar con la Solicitud Actual
    need_update_rows = [solicitud]

    # Paso 3: Buscar el Trace de la Respuesta Automática en la Metadata de la Solicitud
    id_respuesta_autom = solicitud['Metadata_Solicitud'].get('Id_Respuesta_Autom', None)

    # Paso 4: Si existe el Trace, buscamos y actualizamos las Solicitudes Espejo
    if id_respuesta_autom is not None:
        maskMismaRespuesta = solicitudes_df['Metadata_Solicitud'].apply(lambda x: x.get('Id_Respuesta_Autom', None) == id_respuesta_autom)
        maskDiffID = (solicitudes_df['ID_Solicitud'] != solicitud['ID_Solicitud'])
        maskFinal = maskMismaRespuesta & maskDiffID

        for _, solicitud_espejo in solicitudes_df[maskFinal].iterrows():

            # Obtenemos los IDs de Deuda de la Solicitud Espejo
            # Los Resultados por Deuda se aplican solo para las Deudas de estas Sub-Solicitudes
            ids_deudas_espejo = set(d['Id_Deuda'] for d in solicitud_espejo['Datos_Solicitud'])

            solicitud_espejo['Estado_Solicitud'] = solicitud['Estado_Solicitud']
            solicitud_espejo['Metadata_Solicitud']['Metodo_Pago'] = solicitud['Metadata_Solicitud'].get('Metodo_Pago', '')
            solicitud_espejo['Metadata_Solicitud']['Comentario_Ejecutivo'] = solicitud['Metadata_Solicitud'].get('Comentario_Ejecutivo', '')
            solicitud_espejo['Metadata_Solicitud']['Pago_Total_Obligatorio'] = solicitud['Metadata_Solicitud'].get('Pago_Total_Obligatorio', True)
            solicitud_espejo['JSON_Respuesta'] = [d for d in solicitud['JSON_Respuesta'] if d['Id_Deuda'] in ids_deudas_espejo]
            solicitud_espejo['Fecha_Limite_Pago'] = solicitud.get('Fecha_Limite_Pago', '')
            solicitud_espejo['Ejecutivo'] = solicitud['Ejecutivo']
            solicitud_espejo['Fecha_Respuesta'] = solicitud['Fecha_Respuesta']

            # Mantenemos el Trace de la Respuesta Automática en la Metadata
            solicitud_espejo['Metadata_Solicitud']['Id_Respuesta_Autom'] = id_respuesta_autom

            for key in METADATA_ESPECIALES_DISTRIBUIR:
                if key in solicitud['Metadata_Solicitud']:
                    solicitud_espejo['Metadata_Solicitud'][key] = solicitud['Metadata_Solicitud'][key]

            # Agregamos la Solicitud Espejo a la Lista de Filas a Actualizar
            need_update_rows.append(solicitud_espejo)

    # Paso 5: Si la Solicitud Inicial es Exitosa, Es Acuerdo de Pago u Oferta de Acuerdo y tenemos bytes del PDF
    # Se envia el correo de ajuste correspondiente
    if solicitud['Estado_Solicitud'] == 'Exitosa' and solicitud['Tipo_Solicitud'] in ['Acuerdo de Pago', 'Oferta de Acuerdo'] and pdf_bytes is not None:
        # Definimos la Key del Session State para rastrear el Estado del Envío del Correo de Ajuste
        key_correo_enviado = 'correo_ajuste_enviado_{}'.format(solicitud['ID_Solicitud'])
        # Verificamos si el Correo de Ajuste ya fue enviado en un intento anterior para no duplicarlo
        if st.session_state.get(key_correo_enviado, False):
            st.info("El correo de ajuste con el Acuerdo de Pago ya fue enviado anteriormente, por lo que no se volverá a enviar.", icon="📧")
        elif send_email_acuerdos(solicitudes=need_update_rows, pdf_bytes=pdf_bytes, es_ajuste=True):
            # Guardamos el Estado del Envío del Correo de Ajuste en el Session State
            st.session_state[key_correo_enviado] = True
        else:
            st.error("No se pudo enviar el correo de ajuste con el Acuerdo de Pago. Reintentar", icon="❌")
            st.stop()
    elif pdf_bytes is None and solicitud['Estado_Solicitud'] == 'Exitosa' and solicitud['Tipo_Solicitud'] in ['Acuerdo de Pago', 'Oferta de Acuerdo']:
        st.warning("No se generó un PDF para el Acuerdo de Pago. Por favor, contacte al equipo de soporte.", icon="⚠️")

    # Paso 6: Actualizar cada Solicitud en Google Sheets usando update_solicitud_in_google_sheets
    need_update_df = pd.DataFrame(need_update_rows).reset_index(drop=True)
    success =  update_massive_solicitudes_in_google_sheets(solicitudes_df=need_update_df)

    return success

def send_email_acuerdos(*,solicitudes: list[pd.Series], pdf_bytes: bytes, es_ajuste: bool = False):
    # Paso 1: Definir todos los Destinatarios Principales
    main_recipients = set([sol['Correo'] for sol in solicitudes])
    # Añadimos los Correos de Lideres
    correos_lideres = [obtener_correo_lider_negociador(email=cr) for cr in main_recipients]
    # Quitamos los Nulos
    correos_lideres = set([cr for cr in correos_lideres if not(cr is None)])
    main_recipients = ', '.join(list(main_recipients))
    # Paso 2: Definir todos los CCs (Default + Lideres)
    current_ccs = DEFAULT_CCS + list(correos_lideres)
    # Si el Tipo Pago == Crédito, se añade el CC de Crédito
    if any(sol['Tipo_Pago'] == 'Crédito' for sol in solicitudes):
        current_ccs += CCS_CREDITO
    # Paso 3: Generar el Nombre del Acuerdo
    pdf_name = generar_nombre_acuerdo_pago(solicitud_info=solicitudes[0])
    # Paso 4: Obtener el asunto del correo según el Tipo de Solicitud
    tipo_solicitud = solicitudes[0]['Tipo_Solicitud']
    asunto_correo = EMAIL_SUBJECT_MAPPER.get(tipo_solicitud, "Acuerdo de Pago")
    # Agregamos al Asunto los datos especificos de la solicitud
    asunto_correo = asunto_correo.format(
        referencia=solicitudes[0]['Referencia'],
        nombre_cliente=solicitudes[0]['Metadata_Solicitud']['Nombre_Cliente']
    )
    # Paso 5: Generar el Cuerpo del Correo
    string_solicitado = "por {}".format(obtener_nombre_negociador(email=solicitudes[0]['Correo'])) if len(solicitudes) > 1 else "por ti"
    body_correo = EMAIL_BODY_GENERAL.format(
        string_solicitado=string_solicitado,
        nombre_ejecutivo=st.session_state['user_name'],
        comentario_llamativo = solicitudes[0]['Metadata_Solicitud'].get('Comentario_Ejecutivo') or "Realizar el Pago lo más pronto posible"
    )
    # Si es un Ajuste, añadimos el Prefijo (AJUSTE) al Inicio del Asunto y del Cuerpo del Correo
    if es_ajuste:
        asunto_correo = "(AJUSTE) {}".format(asunto_correo)
        body_correo = re.sub(r'(<body[^>]*>)', r'\1<p style="font-weight: bold; color: #d9534f;">(AJUSTE)</p>', body_correo, count=1)
    # Paso 6: Traer el Servicio de Google Mail desde el Session State
    google_mail_service: GoogleMailService = st.session_state['google_mail_service']
    # Paso 7: Enviar el Correo y devolver los resultados
    return google_mail_service.send_email(
        to=main_recipients,
        cc_emails=current_ccs,
        subject=asunto_correo,
        body=body_correo,
        pdf_bytes=pdf_bytes,
        pdf_name=pdf_name,
    )

def upload_massive_addendums(*,solicitud: pd.Series) -> bool:
    """Sube los Addendums que se requieran a Alianzas - Ejecutivos

    Args:
        solicitud (pd.Series): Los Datos de la Solicitud

    Returns:
        bool: True si el proceso fue exitoso, False en caso contrario.
    """
    # Paso 1: Verificar si hay Addendums en la Solicitud
    if 'Addendums' not in solicitud['Metadata_Solicitud']:
        return True  # No hay Addendums, no hay nada que subir

    # Paso 2: Iterar sobre cada Addendum y subirlo a la Hoja de Masivas
    for addendum in solicitud['Metadata_Solicitud']['Addendums']:
        # Paso 2.1 Validar el Addendum (Numero_Credito no Nulo, Banco no Nulo, Monto_Actual>0, Monto_Propuesto>0)
        if not all([
            addendum.get('Numero_Credito'),
            addendum.get('Banco'),
            cleanNumber(addendum.get('Monto_Actual', 0)) > 0,
            cleanNumber(addendum.get('Monto_Propuesto', 0)) > 0
        ]):
            st.warning(f"El Addendum #{addendum.get('Id_Counter', 'N/A')} no se sube por falta de Datos.")
            continue  # Saltamos este Addendum y continuamos con el siguiente

        # Paso 2.2 Subir el Addendum a la Hoja de Masivas
        if not upload_addendum_debt(
            reference=solicitud['Referencia'],
            cedula=solicitud['Cedula'],
            bank=addendum.get('Banco', ''),
            number_credit=addendum.get('Numero_Credito', ''),
            aliado=solicitud['Casa_Cobro'],
            monto_inicial=cleanNumber(addendum.get('Monto_Actual', 0)),
            monto_propuesto=cleanNumber(addendum.get('Monto_Propuesto', 0))
        ):
            st.warning(f"El Addendum #{addendum.get('Id_Counter', 'N/A')} no se sube por un error en la subida.")
            continue  # Saltamos este Addendum y continuamos con el siguiente

    return True

def generar_nombre_acuerdo_pago(solicitud_info: pd.Series) -> str:
    """
    Genera un nombre de archivo para el Acuerdo de Pago basado en la información de la solicitud.

    Args:
        solicitud_info (pd.Series): Información de la solicitud.

    Returns:
        str: Nombre del archivo generado.
    """
    # Definimos el Esqueleto
    esqueleto_nombre = "Acuerdo_Pago_{ID_Solicitud}_{Ids_Deudas} - {Cedula}.pdf"
    return esqueleto_nombre.format(
        ID_Solicitud=solicitud_info['ID_Solicitud'],
        Ids_Deudas='-'.join(str(d['Id_Deuda']) for d in solicitud_info['JSON_Respuesta'] if cleanNumber(d['Monto_Propuesto']) > 0),
        Cedula=solicitud_info['Cedula']
    )

def subir_acuerdo_pago_a_google_drive(pdf_bytes: bytes, solicitud_info: pd.Series) -> str:
    """
    Sube un archivo PDF de Acuerdo de Pago a Google Drive.

    Args:
        pdf_bytes (bytes): Contenido del PDF en bytes.
        solicitud_info (pd.Series): Información de la solicitud.
        file_name (str): Nombre del archivo a subir.
        credentials_json (dict): Diccionario con las credenciales de Google Service Account.

    Returns:
        str: ID del archivo subido en Google Drive.
    """
    # Paso 1: Generar el Nombre del Archivo
    file_name = generar_nombre_acuerdo_pago(solicitud_info)
    # Paso 2: Traer el Servicio de Google Drive desde el Session State
    google_drive_service: GoogleDriveService = st.session_state['google_drive_service']
    # Paso 3: Traer el Folder_ID de los Secretos de Streamlit
    folder_id = st.secrets['google_drive']['folder_id_acuerdos_pago']
    # Paso 4: Subir el Archivo a Google Drive
    file_id = google_drive_service.upload_file(
        file_bytes=pdf_bytes,
        file_name=file_name,
        mime_type='application/pdf',
        folder_id=folder_id
    )
    # Paso 5: Retornar el ID del Archivo Subido
    return file_id

def eliminar_acuerdo_pago_de_google_drive(*, file_id: str) -> bool:
    """
    Elimina un archivo PDF de Acuerdo de Pago de Google Drive.

    Args:
        file_id (str): ID del archivo en Google Drive a eliminar.

    Returns:
        bool: True si la eliminación fue exitosa, False en caso contrario.
    """
    # Paso 1: Traer el Servicio de Google Drive desde el Session State
    google_drive_service: GoogleDriveService = st.session_state['google_drive_service']
    # Paso 2: Eliminar el Archivo de Google Drive
    return google_drive_service.delete_file(file_id=file_id)

def obtener_link_acuerdo_pago(file_id: str) -> str:
    """
    Obtiene el enlace de visualización de un archivo en Google Drive.

    Args:
        file_id (str): ID del archivo en Google Drive.

    Returns:
        str: Enlace de visualización del archivo.
    """
    return f"https://drive.google.com/open?id={file_id}"

def generar_plantilla_masiva_solicitudes(solicitudes_df: pd.DataFrame, modo_portafolio: bool = False, usar_total: bool =False) -> pd.DataFrame:
    """
    Genera una plantilla masiva de solicitudes a partir de un DataFrame de solicitudes.

    Args:
        solicitudes_df (pd.DataFrame): DataFrame con las solicitudes.
        modo_portafolio: (bool, default False): Si se agrupan las Solicitudes por Portafolio o se dejan por Deuda
        usar_total: (bool, default False): Si se dejan todas las Solicitudes o solo sin responder

    Returns:
        pd.DataFrame: DataFrame con la plantilla masiva de solicitudes.
    """
    # Paso 0: Dejar solicitudes sin responder
    if not usar_total:
        mask_sin_responder = obtener_mascara_sin_responder(solicitudes_df)
        solicitudes_df = solicitudes_df[mask_sin_responder]

    # Paso 1: Iterar sobre cada solicitud y llenar la plantilla
    filas = []
    for _, solicitud in solicitudes_df.iterrows():
        nueva_fila = {
            'Casa_Cobro': solicitud['Casa_Cobro'],
            'Tipo_Solicitud': solicitud['Tipo_Solicitud'],
            'Cedula': solicitud['Cedula'],
            'Nombre_Cliente': solicitud['Metadata_Solicitud']['Nombre_Cliente'],
            'Portafolio': '1' if len(solicitud['Datos_Solicitud']) > 1 else ''
        }
        if not modo_portafolio:
            for deuda in solicitud['Datos_Solicitud']:
                # Añadimos Contenidos Específicos por Deuda
                deuda_dict = nueva_fila.copy()
                deuda_dict['Banco'] = deuda['Banco']
                deuda_dict['Numero_Obligacion'] = deuda['Numero_Credito']
                deuda_dict['Propuesta'] = cleanNumber(deuda.get('Monto_Propuesto', np.nan), default_nan=np.nan)
                deuda_dict['Plazos'] = deuda.get('Num_Cuotas', '')
                deuda_dict['Id_Deuda'] = deuda.get('Id_Deuda','')
                filas.append(deuda_dict)
                continue
        else:
            nueva_fila['Banco'] = ' | '.join([d['Banco'] for d in solicitud['Datos_Solicitud']])
            nueva_fila['Numero_Obligacion'] = ' | '.join([str(d['Numero_Credito']) for d in solicitud['Datos_Solicitud']])
            nueva_fila['Propuesta'] = sum([cleanNumber(d.get('Monto_Propuesto', 0)) for d in solicitud['Datos_Solicitud']])
            nueva_fila['Plazos'] = max([d.get('Num_Cuotas',1) for d in solicitud['Datos_Solicitud']])
            nueva_fila['Id_Deuda'] = solicitud['Ids_Deuda']

            filas.append(nueva_fila)
            continue

    # Creamos el DataFrame
    plantilla_df = pd.DataFrame(filas)

    if plantilla_df.empty:
        return PlantillaSolicitudesSchema.empty()

    # Quitamos Datos donde no haya Propuesta
    plantilla_df = plantilla_df.dropna(subset=['Propuesta'])

    # Ordenamos las Columnas correctamente según el Schema de PlantillaSolicitudesSchema
    plantilla_df = plantilla_df[PlantillaSolicitudesSchema.empty().columns]

    # Validamos el DataFrame con el Schema de PlantillaSolicitudesSchema
    plantilla_df = PlantillaSolicitudesSchema.validate(plantilla_df)

    # Ahora vamos a Quitar las Columnas de Portafolio y Plazos si no hay datos en ellas
    if plantilla_df['Portafolio'].nunique() == 1 and plantilla_df['Portafolio'].iloc[0] == '':
        plantilla_df = plantilla_df.drop(columns=['Portafolio'])

    return plantilla_df

def generar_descarga_masiva_solicitudes(*,solicitudes_df: pd.DataFrame, en_portafolio: bool, usar_total: bool) -> bytes:
    """
    Genera un archivo CSV para la descarga masiva de solicitudes.

    Args:
        solicitudes_df (pd.DataFrame): DataFrame con las solicitudes a descargar.
        en_portafolio (bool): Si se genera el DF en portafolio o por Deuda
        usar_total (bool): Si se usan todas las Solicitudes

    Returns:
        bytes: Contenido del archivo CSV en formato binario.
    """
    # Paso 1: Generar la Plantilla Masiva de Solicitudes
    download_df = generar_plantilla_masiva_solicitudes(solicitudes_df, modo_portafolio=en_portafolio, usar_total=usar_total)
    if download_df.empty:
        return bytes()

    # Paso 2: Convertir el DataFrame a CSV en formato binario
    csv_bytes = download_df.to_csv(index=False,sep=';').encode('utf-8')

    return csv_bytes

def subir_masivo_plantilla_solicitudes(solicitudes_df: pd.DataFrame, en_portafolio: bool, usar_total: bool) -> bool:
    """
    Sube una plantilla masiva de solicitudes a Google Sheets.

    Args:
        solicitudes_df (pd.DataFrame): DataFrame con las solicitudes a subir.
        en_portafolio (bool): Si se genera el DF en portafolio o por Deuda
        usar_total (bool): Si se genera con todas las Solicitudes (incluyendo respuestas)

    Returns:
        bool: True si la subida fue exitosa, False en caso contrario.
    """
    # Mostramos un Toast de Recordar que solo se suben solicitudes sin respuesta
    st.toast("Recuerda que solo se dejan solicitudes que aún no tengan respuesta", icon="ℹ️")

    # Paso 1: Generar la Plantilla Masiva de Solicitudes
    with st.spinner("Subiendo Información a Google Sheets..."):
        plantilla_df = generar_plantilla_masiva_solicitudes(solicitudes_df, modo_portafolio=en_portafolio, usar_total = usar_total)

        # Paso 2: Subir la Plantilla Masiva a Google Sheets
        success = upload_massive_solicitudes_filtered_plantilla(plantilla_df)

        # Paso 3: Registrar el Log de la Subida Masiva de Solicitudes
        upload_log_to_sheets(info="Subida de Plantilla Masiva de Solicitudes",
            detail=f"{st.session_state['user_email']} subió {len(plantilla_df)} solicitudes filtradas a Google Sheets. ({'Éxito' if success else 'Fallo'})"
        )

    return success

# Función para Reiniciar los Filtros de Solicitudes en el Session State
def reiniciar_filtros_solicitudes_ejecutivo(method: Literal['reset','basic'] = "reset") -> None:
    """
    Reinicia los filtros de solicitudes en el estado de la sesión.
    Esta función elimina las claves relacionadas con los filtros de solicitudes del estado de la sesión.
    """
    # Lista de claves a reiniciar del Session State
    keys_to_remove = [
        "tipo_solicitud_gestion_input",
        "aliado_solicitud_gestion_input",
        "estado_solicitud_gestion_input",
        "ejecutivo_solicitud_gestion_input",
        "persona_solicitud_gestion_input",
        "banco_solicitud_gestion_input",
        "id_solicitud_gestion_input",
        "cedula_solicitud_gestion_input",
        "id_deuda_solicitud_gestion_input",
        "organizar_abc_solicitudes_gestion_input",
        "estado_liq_ejec_input",
    ]
    keys_to_list = [
        'tipo_solicitud_gestion_input',
        'aliado_solicitud_gestion_input',
        'estado_solicitud_gestion_input',
        'ejecutivo_solicitud_gestion_input',
        'banco_solicitud_gestion_input'
    ]
    keys_to_Todos = [
        "persona_solicitud_gestion_input",
        "id_solicitud_gestion_input",
        "cedula_solicitud_gestion_input",
        "id_deuda_solicitud_gestion_input",
        "estado_liq_ejec_input",
    ]
    for key in keys_to_remove:
        if key in keys_to_list:
            st.session_state[key] = []
        elif key in keys_to_Todos:
            st.session_state[key] = "Todos"
        else:
            st.session_state[key] = None

    # Reiniciamos también filtros_recomendados_solicitudes y organizar_abc_solicitudes_gestion_input a False
    st.session_state['filtros_recomendados_solicitudes'] = False
    st.session_state['organizar_abc_solicitudes_gestion_input'] = False
    # Si es Básico, pasamos estado_solicitud_gestion_input a "Sin Tocar"
    if method == 'basic':
        st.session_state['estado_solicitud_gestion_input'] = "Sin Tocar"

def reiniciar_filtros_solicitudes_negociadores() -> None:
    """
    Reinicia los filtros de solicitudes para los negociadores en el estado de la sesión.
    Esta función elimina las claves relacionadas con los filtros de solicitudes del estado de la sesión.
    """
    # Lista de claves a reiniciar del Session State
    keys_to_remove = [
        'id_deuda_solicitud_nego_input',
        'banco_solicitud_nego_input',
        'cliente_solicitud_nego_input',
        'tipo_solicitud_nego_input',
        'estado_solicitud_nego_input',
        'aliado_solicitud_nego_input',
        'id_solicitud_nego_input',
        'persona_solicitud_nego_input',
        'referencia_solicitud_nego_input',
        'toggle_exitosas_solicitud_nego_input',
        'toggle_aprobacion_solicitud_nego_input',
        'toggle_orden_fecha_solicitud_nego_input',
        "fecha_min_solicitud_nego_input",
        "fecha_max_solicitud_nego_input",
        "reasignable_solicitud_nego_input",
        "estado_liq_nego_input",
    ]
    keys_to_list = [
        'id_deuda_solicitud_nego_input',
        'banco_solicitud_nego_input',
    ]
    keys_to_Todos = [
        'cliente_solicitud_nego_input',
        'tipo_solicitud_nego_input',
        'estado_solicitud_nego_input',
        'aliado_solicitud_nego_input',
        'id_solicitud_nego_input',
        'persona_solicitud_nego_input',
        'referencia_solicitud_nego_input',
        "estado_liq_nego_input",
    ]
    keys_to_False = [
        'toggle_exitosas_solicitud_nego_input',
        'toggle_aprobacion_solicitud_nego_input',
        'toggle_orden_fecha_solicitud_nego_input',
        'reasignable_solicitud_nego_input',
    ]

    for key in keys_to_remove:
        if key in keys_to_list:
            st.session_state[key] = []
        elif key in keys_to_Todos:
            st.session_state[key] = "Todos"
        elif key in keys_to_False:
            st.session_state[key] = False
        else:
            st.session_state[key] = None

def obtener_promedio_tiempos_respuesta(solicitudes_df: pd.DataFrame, *, simular_respuestas_hoy: bool = False) -> dict[str, Any]:
    """
    Calcula el promedio de tiempos de respuesta para las solicitudes.

    Args:
        solicitudes_df (pd.DataFrame): DataFrame con las solicitudes.
        simular_respuestas_hoy (bool, default False): Si es True, las solicitudes sin
            Fecha de Respuesta se simulan como respondidas en este instante (Zona Horaria
            America/Bogota) para incluirlas en el cálculo de los tiempos de respuesta.

    Returns:
        dict[str, float]: Diccionario con los promedios de tiempos de respuesta.
            - 'promedio_general': Promedio general de días de respuesta.
            - 'promedio_por_tipo': Promedio de días de respuesta por tipo de solicitud.
    """
    # Paso 1: Si se simula, rellenar las Fechas de Respuesta vacías con la fecha/hora actual
    if simular_respuestas_hoy:
        solicitudes_df = solicitudes_df.copy()
        mask_sin_respuesta = solicitudes_df['Fecha_Respuesta'].isna()
        # Usamos Zona Horaria America/Bogota y luego la quitamos para no mezclar
        # datos con y sin Zona Horaria en las comparaciones
        fecha_hoy = pd.Timestamp.now('America/Bogota').tz_localize(None)
        solicitudes_df.loc[mask_sin_respuesta, 'Fecha_Respuesta'] = fecha_hoy

    # Paso 2: Crear Columna de Tiempos Respuesta como Diferencia en Días entre Fecha_Respuesta y Timestamp
    solicitudes_aux = solicitudes_df.reset_index(drop=True)
    solicitudes_aux['Tiempo_Respuesta_Dias'] = getBDDaysDiffFloat_vectorized(
        solicitudes_aux['Fecha_Respuesta'],
        solicitudes_aux['Timestamp']
    )

    # Paso 3: Calcular el Promedio General de Tiempos de Respuesta
    promedio_general = solicitudes_aux['Tiempo_Respuesta_Dias'].mean()

    # Paso 4: Calcular el Promedio de Tiempos de Respuesta por Tipo de Solicitud
    promedio_por_tipo = solicitudes_aux.groupby('Tipo_Solicitud')['Tiempo_Respuesta_Dias'].mean().to_dict()

    return {
        'promedio_general': promedio_general,
        'promedio_por_tipo': promedio_por_tipo
    }

def obtener_promedio_respuestas_dia(solicitudes_df: pd.DataFrame) -> dict[str, Any]:
    """
    Calcula el promedio de respuestas por día para las solicitudes.

    Args:
        solicitudes_df (pd.DataFrame): DataFrame con las solicitudes.

    Returns:
        dict[str, float]: Diccionario con los promedios de respuestas por día.
            - 'promedio_general': Promedio general de respuestas por día.
            - 'promedio_por_tipo': Promedio de respuestas por día por tipo de solicitud.
    """
    # Paso 1: Crear Columna de Fecha de Respuesta como Fecha sin Hora
    solicitudes_aux = solicitudes_df.reset_index(drop=True)
    solicitudes_aux['Fecha_Respuesta_Solo_Fecha'] = solicitudes_aux['Fecha_Respuesta'].dt.date

    # Paso 2: Calcular el Promedio General de Respuestas por Día
    promedio_general = solicitudes_aux.groupby('Fecha_Respuesta_Solo_Fecha').size().mean()

    # Paso 3: Calcular el Promedio de Respuestas por Día por Tipo de Solicitud
    promedio_por_tipo = solicitudes_aux.groupby(['Tipo_Solicitud', 'Fecha_Respuesta_Solo_Fecha']).size().groupby('Tipo_Solicitud').mean().to_dict()

    return {
        'promedio_general': promedio_general,
        'promedio_por_tipo': promedio_por_tipo
    }

def obtener_resumen_respuestas_vencidas(solicitudes_df: pd.DataFrame) -> dict[str, Any]:
    """
    Calcula el resumen de respuestas vencidas entre las solicitudes ya respondidas.

    Args:
        solicitudes_df (pd.DataFrame): DataFrame con las solicitudes.

    Returns:
        dict[str, Any]: Diccionario con el resumen de respuestas vencidas.
            - 'total_general': Total de solicitudes vencidas con respuesta.
            - 'total_por_tipo': Total de solicitudes vencidas por tipo de solicitud.
            - 'total_respondidas': Total de solicitudes con respuesta consideradas.
    """
    # Paso 1: Dejar solo las Solicitudes con Respuesta (Opuesto a la Máscara de Sin Responder)
    mask_respondidas = ~obtener_mascara_sin_responder(solicitudes_df)
    solicitudes_respondidas = solicitudes_df[mask_respondidas].reset_index(drop=True)

    # Si no hay Solicitudes Respondidas, devolvemos el Resumen Vacío
    if solicitudes_respondidas.empty:
        return {
            'total_general': 0,
            'total_por_tipo': {},
            'total_respondidas': 0,
        }

    # Paso 2: Identificar las Solicitudes Vencidas por su Estado
    mask_vencidas = (solicitudes_respondidas['Estado_Solicitud'] == 'Vencida')

    # Paso 3: Calcular el Total General de Solicitudes Vencidas
    total_general = int(mask_vencidas.sum())

    # Paso 4: Calcular el Total de Solicitudes Vencidas por Tipo de Solicitud
    total_por_tipo = solicitudes_respondidas[mask_vencidas].groupby('Tipo_Solicitud').size().to_dict()

    return {
        'total_general': total_general,
        'total_por_tipo': total_por_tipo,
        'total_respondidas': len(solicitudes_respondidas),
    }

def obtener_resumen_respuestas_automaticas(solicitudes_df: pd.DataFrame) -> dict[str, Any]:
    """
    Calcula el resumen de respuestas automáticas entre las solicitudes ya respondidas.

    Una respuesta es automática cuando el Id_Respuesta_Autom guardado en la Metadata
    difiere del ID_Solicitud de la fila. Si la llave no existe, se asume que la
    respuesta no fue automática (se compara contra el mismo ID_Solicitud).

    Args:
        solicitudes_df (pd.DataFrame): DataFrame con las solicitudes.

    Returns:
        dict[str, Any]: Diccionario con el resumen de respuestas automáticas.
            - 'total_general': Total de respuestas automáticas.
            - 'total_por_tipo': Total de respuestas automáticas por tipo de solicitud.
            - 'total_respondidas': Total de solicitudes con respuesta consideradas.
    """
    # Paso 1: Dejar solo las Solicitudes con Respuesta (Opuesto a la Máscara de Sin Responder)
    mask_respondidas = ~obtener_mascara_sin_responder(solicitudes_df)
    solicitudes_respondidas = solicitudes_df[mask_respondidas].reset_index(drop=True)

    # Si no hay Solicitudes Respondidas, devolvemos el Resumen Vacío
    if solicitudes_respondidas.empty:
        return {
            'total_general': 0,
            'total_por_tipo': {},
            'total_respondidas': 0,
        }

    # Paso 2: Identificar las Respuestas Automáticas
    # Si Id_Respuesta_Autom difiere del ID_Solicitud, la respuesta fue automática
    mask_automaticas = solicitudes_respondidas.apply(
        lambda row: str(row['Metadata_Solicitud'].get('Id_Respuesta_Autom', row['ID_Solicitud'])) != str(row['ID_Solicitud']),
        axis=1
    )

    # Paso 3: Calcular el Total General de Respuestas Automáticas
    total_general = int(mask_automaticas.sum())

    # Paso 4: Calcular el Total de Respuestas Automáticas por Tipo de Solicitud
    total_por_tipo = solicitudes_respondidas[mask_automaticas].groupby('Tipo_Solicitud').size().to_dict()

    return {
        'total_general': total_general,
        'total_por_tipo': total_por_tipo,
        'total_respondidas': len(solicitudes_respondidas),
    }

def obtener_resumen_liquidaciones(solicitudes_df: pd.DataFrame) -> dict[str, Any]:
    """
    Calcula el resumen de solicitudes liquidadas entre las solicitudes exitosas.

    Una solicitud liquidada se refiere a una solicitud que tenga alguna de sus solicitudes liquidadas.

    Args:
        solicitudes_df (pd.DataFrame): DataFrame con las solicitudes.

    Returns:
        dict[str, Any]: Diccionario con el resumen de solicitudes con Liquidación.
            - 'total_general': Total de solicitudes liquidadas.
            - 'total_tipo_sol_tipo_liq': Total de solicitudes liquidadas por Tipo de Solicitud y Tipo de Liquidación.
            - 'deudas_clientes_tipo_sol': Total de solicitudes liquidadas en #Deudas Únicas y #Clientes Únicos (Desglose por Tipo_Solicitud)
            - 'total_deudas_unicas': Número de Deudas Únicas entre las solicitudes liquidadas (Sin importar el Tipo de Solicitud).
            - 'total_clientes_unicos': Número de Clientes Únicos entre las solicitudes liquidadas (Sin importar el Tipo de Solicitud).
    """
    # Paso 1: Crear la Columna de Estado_Liquidacion si no existe
    solicitudes_aux = solicitudes_df.copy()
    if 'Estado_Liquidacion' not in solicitudes_aux.columns:
        serie_liq = solicitudes_aux.apply(lambda r: obtener_estado_liquidacion(solicitud=r), axis=1) # type: ignore
        solicitudes_aux['Estado_Liquidacion'] = serie_liq.mask(serie_liq.isna(), "N/A")

    # Paso 2: Dejar solo las Solicitudes Liquidadas (Estado_Liquidacion contiene 'Liquidado')
    mask_liquidadas = solicitudes_aux['Estado_Liquidacion'].astype(str).str.contains("Liquidado", regex=False)
    solicitudes_liquidadas = solicitudes_aux[mask_liquidadas]

    # Si no hay Solicitudes Liquidadas, devolvemos el Resumen Vacío
    if solicitudes_liquidadas.empty:
        return {
            'total_general': 0,
            'total_tipo_sol_tipo_liq': {},
            'deudas_clientes_tipo_sol': {},
            'total_deudas_unicas': 0,
            'total_clientes_unicos': 0,
        }

    # Paso 3: Calcular el Total General de Solicitudes Liquidadas
    total_general = len(solicitudes_liquidadas)

    # Paso 4: Calcular el Total de Liquidadas por Tipo de Solicitud y Tipo de Liquidación
    resumen_cruzado = solicitudes_liquidadas.groupby(['Tipo_Solicitud', 'Estado_Liquidacion']).size()
    total_tipo_sol_tipo_liq = resumen_cruzado.unstack(fill_value=0).to_dict(orient='index')

    # Paso 5: Calcular #Deudas Únicas y #Clientes Únicos por Tipo de Solicitud (y en General)
    deudas_clientes_tipo_sol = {}
    ids_deudas_unicos_general: set[str] = set()
    cedulas_unicas_general: set[str] = set()
    for tipo_solicitud, grupo in solicitudes_liquidadas.groupby('Tipo_Solicitud'):
        ids_deudas_unicos: set[str] = set()
        cedulas_unicas: set[str] = set()
        for _, solicitud in grupo.iterrows():
            json_respuesta = solicitud['JSON_Respuesta']
            if isinstance(json_respuesta, list):
                ids_deudas_unicos.update(str(d['Id_Deuda']) for d in json_respuesta)
            cedula = solicitud['Cedula']
            if pd.notna(cedula):
                cedulas_unicas.add(str(cedula))
        ids_deudas_unicos_general.update(ids_deudas_unicos)
        cedulas_unicas_general.update(cedulas_unicas)
        deudas_clientes_tipo_sol[tipo_solicitud] = {
            'num_deudas_unicas': len(ids_deudas_unicos),
            'num_clientes_unicos': len(cedulas_unicas),
        }

    return {
        'total_general': total_general,
        'total_tipo_sol_tipo_liq': total_tipo_sol_tipo_liq,
        'deudas_clientes_tipo_sol': deudas_clientes_tipo_sol,
        'total_deudas_unicas': len(ids_deudas_unicos_general),
        'total_clientes_unicos': len(cedulas_unicas_general),
    }

def obtener_df_bancos_sin_responder(solicitudes_df: pd.DataFrame) -> pd.DataFrame:
    """
    Obtiene un DataFrame con la cantidad de solicitudes sin responder por banco.

    Args:
        solicitudes_df (pd.DataFrame): DataFrame con las solicitudes.

    Returns:
        pd.DataFrame: DataFrame con la cantidad de solicitudes sin responder por banco.
            Columnas: 'Banco', 'Cantidad_Sin_Responder'
    """
    # Paso 1: Filtrar las Solicitudes Sin Responder
    mask_sin_responder = obtener_mascara_sin_responder(solicitudes_df)
    solicitudes_sin_responder = solicitudes_df[mask_sin_responder]

    # Paso 2: Crear Columna Axuiliar Bancos que viene desde Datos_Solicitud
    solicitudes_sin_responder = solicitudes_sin_responder.assign(
        Bancos=solicitudes_sin_responder['Datos_Solicitud'].apply(lambda x: [d['Banco'] for d in x])
    )

    # Paso 3: Explode la Columna Bancos para tener una fila por cada Banco
    solicitudes_exploded = solicitudes_sin_responder.explode('Bancos')

    # Paso 4: Agrupar por Banco y Contar la Cantidad de Solicitudes Sin Responder
    df_bancos_sin_responder = solicitudes_exploded.groupby('Bancos').size().reset_index(name='Solicitudes Sin Responder').rename(columns={'Bancos': 'Banco'})

    return df_bancos_sin_responder

def generate_plantilla_serie_acuerdo(*, solicitud: pd.Series, deudas: list[str], sufijo: str = '') -> pd.Series:
    """
    Genera una plantilla de serie para un acuerdo de pago basado en la información de la solicitud.

    Args:
        solicitud (pd.Series): Información de la solicitud.
        deudas (list[str]): Lista de IDs de Deuda a incluir en el Acuerdo.
        sufijo (str, default ''): Sufijo de las Keys del Session State (Para el Modo Edición).

    Returns:
        pd.Series: Serie con la plantilla del acuerdo de pago.
    """
    # Paso 1: Crear un diccionario con los datos necesarios para el acuerdo
    acuerdo_data = {
        "ID_Solicitud": solicitud['ID_Solicitud'],
        "Referencia": solicitud['Referencia'],
        "Cedula": solicitud['Cedula'],
        "Metadata_Solicitud": {
            "Nombre_Cliente": solicitud['Metadata_Solicitud']['Nombre_Cliente'],
            "Metodo_Pago": solicitud['Metadata_Solicitud'].get('Metodo_Pago', ''),
            "Comentario_Ejecutivo": solicitud['Metadata_Solicitud'].get('Comentario_Ejecutivo', ''),
        },
        "Fecha_Esperada_Pago": pd.to_datetime(solicitud['Fecha_Esperada_Pago']).strftime("%Y-%m-%d") if pd.notna(pd.to_datetime(solicitud['Fecha_Esperada_Pago'])) else '',
        "Fecha_Limite_Pago": pd.to_datetime(solicitud['Fecha_Limite_Pago']).strftime("%Y-%m-%d")  if pd.notna(pd.to_datetime(solicitud['Fecha_Limite_Pago'])) else '',
        "Casa_Cobro": solicitud['Casa_Cobro'],
        "Ejecutivo": solicitud['Ejecutivo'],
        "JSON_Respuesta": [
            {
                "Id_Deuda": deuda['Id_Deuda'],
                "Banco": deuda['Banco'],
                "Numero_Credito": st.session_state.get(
                    "numero_credito_solicitud_info_{}_{}{}".format(solicitud['ID_Solicitud'], deuda['Id_Deuda'], sufijo),
                    deuda.get('Numero_Credito', 'N/A')
                ),
                "Monto_Propuesto": cleanNumber(deuda.get('Monto_Propuesto', 0), default_nan=0.0),
                "Num_Cuotas": cleanNumber(deuda.get('Num_Cuotas', 1), default_nan=1.0)
            }
            for deuda in (solicitud['JSON_Respuesta'] + solicitud["Metadata_Solicitud"].get("Addendums", [])) if (cleanNumber(deuda.get('Monto_Propuesto', 0), default_nan=0.0) > 0) and (deuda['Id_Deuda'] in deudas)
        ]
    }

    # Paso 2: Convertir el diccionario a una Serie de Pandas
    return pd.Series(acuerdo_data)

def add_metadata_to_uploaded_pdf(*, pdf_bytes: bytes, metadata: dict[Hashable, Any], password: str | None = None) -> bytes:
    """Procesa el PDF. Si falla por encriptación, eleva la excepción para que la UI la maneje."""
    if password == '':
        password = None

    try:
        reader = PdfReader(BytesIO(pdf_bytes))

        if reader.is_encrypted:
            if password is None:
                raise FileNotDecryptedError("El archivo requiere contraseña.")

            resultado = reader.decrypt(password)
            if resultado == 0:
                raise WrongPasswordError("La contraseña del PDF es incorrecta.")

        writer = PdfWriter()

        for page in reader.pages:
            writer.add_page(page)

        hidden_key = NameObject("/Acuerdo_Info_Metadata")
        hidden_value = TextStringObject(json.dumps({
            "agreement": metadata,
            "generated_at": pd.Timestamp.now('America/Bogota').isoformat()
        }, ensure_ascii=False))

        writer.add_metadata({hidden_key: hidden_value})

        output_pdf_bytes = BytesIO()
        writer.write(output_pdf_bytes)
        return output_pdf_bytes.getvalue()

    except (WrongPasswordError, FileNotDecryptedError):
        raise

# Función Auxiliar para obtener los Correos a Cargo del Usuario Actual
def obtener_correos_a_cargo_usuario_actual() -> list[str]:
    """
    Obtiene los correos electrónicos de los usuarios a cargo del usuario actual.

    Returns:
        list[str]: Lista de correos electrónicos de los usuarios a cargo.
    """
    # Paso 1: Obtener el correo del usuario actual desde el estado de la sesión
    user_email = st.session_state.get('user_email', '')

    # Paso 2: Cargar el Headcount de Negociación
    headcount_df = load_headcount_negociacion()

    # Si el Usuario es Administrador, se retornan todos los Correos
    if st.session_state.get('user_role', '') == 'admin':
        return headcount_df['Correo'].unique().tolist()

    # Paso 3: Obtener la Fila para este correo
    user_row = headcount_df[headcount_df['Correo'] == user_email]
    if user_row.empty:
        return []  # Retornamos una lista vacía si no se encuentra el usuario

    user_row = user_row.iloc[0]

    # Paso 4: Obtener el Nombre del Negociador
    nombre_negociador = user_row['Nombre']

    # Paso 5: Buscar los Correos donde el Lider tenga ese nombre
    lider_emails = headcount_df[headcount_df['Nombre'] == nombre_negociador]['Correo'].tolist()

    return lider_emails

# Función Auxiliar para obtener el DF de las Solicitudes del Usario Actual
def filtrar_solicitudes_por_usuario_actual(solicitudes_df: pd.DataFrame) -> pd.DataFrame:
    """
    Filtra las solicitudes para obtener solo aquellas que pertenecen al usuario actual.

    Args:
        solicitudes_df (pd.DataFrame): DataFrame con todas las solicitudes.

    Returns:
        pd.DataFrame: DataFrame filtrado con las solicitudes del usuario actual.
    """
    # Paso 1: Obtener los Correos a Cargo del Usuario Actual
    correos_a_cargo = obtener_correos_a_cargo_usuario_actual()
    # Paso 2: Filtrar el DataFrame de Solicitudes por los Correos a Cargo o Reasignables
    mask_reasignable = obtener_mascara_reasignable(solicitudes_df)
    mask_correos_lider = solicitudes_df['Correo'].isin(correos_a_cargo)
    mask_correos_usuario_actual = (solicitudes_df['Correo'] == st.session_state.get('user_email', ''))
    mask_final = (mask_correos_lider | mask_correos_usuario_actual | mask_reasignable)
    # Paso 3: Crear el DF Dejando los Reasignables primero
    return solicitudes_df[mask_final]

# Función Auxiliar para crear la plantilla de solicitud de acuerdo de pago
def crear_plantilla_solicitud_acuerdo_pago(
        *,
        solicitud: pd.Series,
        selected_ids: list[str],
        fecha_pago: pd.Timestamp,
        tipo_pago: str,
        comentario: str,
    ) -> dict[str, Any]:
    """Crea la Plantilla de Solicitud a subir a partir de la validación exitosa

    Args:
        solicitud (pd.Series): Los Datos de la Solicitud actual
        selected_ids (list[str]): Lista de los ID_Deuda a subir para la nueva solicitud

    Returns:
        pd.Series: La plantilla de la nueva solicitud de acuerdo de pago.
    """
    # Paso 1: Definir los Valores Iniciales
    solicitud_template = {
        'Referencia': solicitud['Referencia'],
        'Cedula': solicitud['Cedula'],
        'Ids_Deuda': '-'.join(selected_ids),
        'Casa_Cobro': solicitud['Casa_Cobro'],
        'Tipo_Solicitud': 'Acuerdo de Pago',
        'Datos_Solicitud': json.dumps(
        [
            {
                'Id_Deuda': deuda['Id_Deuda'],
                'Banco': deuda['Banco'],
                'Numero_Credito': deuda['Numero_Credito'],
                'Monto_Propuesto': cleanNumber(deuda.get('Monto_Propuesto', 0)),
                'Num_Cuotas': deuda.get('Num_Cuotas', 1),
                'Monto_Actual': cleanNumber(next((d.get('Monto_Actual',0) for d in solicitud['Datos_Solicitud'] if d['Id_Deuda'] == deuda['Id_Deuda']), 0)),
            }
            for deuda in (solicitud['JSON_Respuesta'] + solicitud["Metadata_Solicitud"].get("Addendums", []))
            if (cleanNumber(deuda.get('Monto_Propuesto', 0)) > 0) and (deuda['Id_Deuda'] in selected_ids)
        ]
        ),
        'Ejecutivo': solicitud['Ejecutivo'],
        'Fecha_Esperada_Pago': fecha_pago.strftime('%Y-%m-%d %H:%M:%S'),
        'Tipo_Pago': tipo_pago,
        'Metadata_Solicitud': json.dumps({
            'Nombre_Cliente': solicitud['Metadata_Solicitud']['Nombre_Cliente'],
            'Comentario_Negociador': comentario,
            'Origen_Solicitud': solicitud['ID_Solicitud'],
            'Es_Reasignado': (solicitud['Correo'] != st.session_state['user_email']),
        }),
        'Estado_Solicitud': 'Sin Tocar',
    }

    return solicitud_template

# Función Auxiliar para crear la plantilla de solicitud de validación
def crear_plantilla_solicitud_validacion(
        *,
        solicitud: pd.Series,
        selected_ids_info: list[dict[str, Any]],
        comentario: str,
    ) -> dict[str, Any]:
    """Crea la Plantilla de Solicitud a subir a partir de la validación exitosa

    Args:
        solicitud (pd.Series): Los Datos de la Solicitud actual
        selected_ids_info (list[dict[str, Any]]): Lista de diccionarios con la información de las deudas seleccionadas

    Returns:
        pd.Series: La plantilla de la nueva solicitud de validación.
    """
    # Paso 1: Definir los Valores Iniciales
    solicitud_template = {
        'Referencia': solicitud['Referencia'],
        'Cedula': solicitud['Cedula'],
        'Ids_Deuda': '-'.join([str(deuda['Id_Deuda']) for deuda in selected_ids_info]),
        'Casa_Cobro': solicitud['Casa_Cobro'],
        'Tipo_Solicitud': 'Validación',
        'Datos_Solicitud': json.dumps(
            selected_ids_info
        ),
        'Ejecutivo': solicitud['Ejecutivo'],
        'Metadata_Solicitud': json.dumps({
            'Nombre_Cliente': solicitud['Metadata_Solicitud']['Nombre_Cliente'],
            'Comentario_Negociador': comentario,
            'Origen_Solicitud': solicitud['ID_Solicitud'],
            'Es_Reasignado': (solicitud['Correo'] != st.session_state['user_email']),
        }),
        'Estado_Solicitud': 'Sin Tocar',
    }

    return solicitud_template

# Función Auxiliar para actualizar las Solicitudes a 'Solicitado'
def update_solicitudes_to_solicitado(*, solicitudes: pd.DataFrame) -> bool:
    # Paso 1: Actualizar el Estado de las Solicitudes a 'Solicitado'
    solicitudes['Estado_Solicitud'] = 'Solicitado'
    # Paso 2: Agregar Fecha_Solicitado a Metadata_Solicitud
    fechaActual = pd.Timestamp.now('America/Bogota').strftime('%Y-%m-%d %H:%M:%S')
    solicitudes['Metadata_Solicitud'] = solicitudes['Metadata_Solicitud'].apply(
        lambda x: x.update({'Fecha_Solicitado': fechaActual}) or x
    )
    # Paso 3: Actualizamos el Ejecutivo
    solicitudes['Ejecutivo'] = st.session_state.get('user_name', st.session_state.get('user_email', 'Desconocido'))
    # Paso 4: Subir las Solicitudes Actualizadas a Google Sheets
    return update_massive_solicitudes_in_google_sheets(solicitudes_df=solicitudes)

# Función Auxiliar para actualizar las Solicitudes a 'Vencida' (Cierre de Mes)
def update_solicitudes_to_vencida(*, solicitudes: pd.DataFrame) -> bool:
    # Paso 1: Actualizar el Estado de las Solicitudes a 'Vencida'
    solicitudes['Estado_Solicitud'] = 'Vencida'
    # Paso 2: Actualizar la Fecha de Respuesta a Hoy (Zona Horaria America/Bogota)
    fechaActual = pd.Timestamp.now('America/Bogota').tz_localize(None)
    solicitudes['Fecha_Respuesta'] = fechaActual
    # Paso 3: Actualizamos el Ejecutivo
    solicitudes['Ejecutivo'] = st.session_state.get('user_name', st.session_state.get('user_email', 'Desconocido'))
    # Paso 4: Actualizar el Comentario del Ejecutivo en la Metadata (Cierre de Mes)
    solicitudes['Metadata_Solicitud'] = solicitudes['Metadata_Solicitud'].apply(
        lambda x: {**x, 'Comentario_Ejecutivo': "*Solicitud cerrada por ejecutivo dado el cambio del Mes en Curso*"}
    )
    # Paso 5: Subir las Solicitudes Actualizadas a Google Sheets
    return update_massive_solicitudes_in_google_sheets(solicitudes_df=solicitudes)

# Función Auxiliar para verificar si no se ha subido un Acuerdo de Pago para la Solicitud
def check_if_acuerdo_pago_uploaded(*, solicitud: dict[str, Any]) -> bool:
    """
    Verifica si ya se ha subido un Acuerdo de Pago para la solicitud dada.

    Args:
        solicitud (dict[str, Any]): Información de la solicitud.

    Returns:
        bool: True si ya se ha subido un Acuerdo de Pago, False en caso contrario.
    """
    # Paso 1: Traer datos de solicitudes de Google Sheets
    solicitudes_df = load_current_month_solicitudes()
    # Paso 2: Crear las Máscaras para filtrar
    # Las máscaras son: maskCasa, maskTipo, maskNoExitosa, maskCorreo, maskIds
    maskCasa = (solicitudes_df['Casa_Cobro'] == solicitud['Casa_Cobro'])
    maskNoExitosa = (solicitudes_df['Estado_Solicitud'] == 'No Exitosa')
    maskTipo = (solicitudes_df['Tipo_Solicitud'] == 'Acuerdo de Pago')
    maskCorreo = (solicitudes_df['Correo'] == st.session_state.get('user_email', 'Desconocido'))
    maskIds = (solicitudes_df['Ids_Deuda'] == solicitud['Ids_Deuda'])
    # Paso 3: Combinamos las máscaras para obtener la máscara final
    mask_final = maskCasa & maskTipo & maskCorreo & maskIds
    return mask_final.any()

# Función Auxiliar para verificar si ya se subio una solicitud de Validación para la Solicitud
def check_if_validacion_uploaded(*, solicitud: dict[str, Any], old_id: str) -> bool:
    """
    Verifica si ya se ha subido una solicitud de Validación para la solicitud dada.

    Args:
        solicitud (dict[str, Any]): Información de la solicitud.

    Returns:
        bool: True si ya se ha subido una solicitud de Validación, False en caso contrario.
    """
    # Paso 1: Traer datos de solicitudes de Google Sheets
    solicitudes_df = load_current_month_solicitudes()
    # Paso 2: Crear las Máscaras para filtrar
    # Las máscaras son: maskCasa, maskTipo, maskCorreo, maskIds y Mascara de Origen Solicitud
    maskCasa = (solicitudes_df['Casa_Cobro'] == solicitud['Casa_Cobro'])
    maskTipo = (solicitudes_df['Tipo_Solicitud'] == 'Validación')
    maskCorreo = (solicitudes_df['Correo'] == st.session_state.get('user_email', 'Desconocido'))
    maskIds = (solicitudes_df['Ids_Deuda'] == solicitud['Ids_Deuda'])
    maskOrigen = (solicitudes_df['Metadata_Solicitud'].apply(lambda x: x.get('Origen_Solicitud', None) == old_id))
    # Paso 3: Combinamos las máscaras para obtener la máscara final
    mask_final = maskCasa & maskTipo & maskCorreo & maskIds & maskOrigen
    return mask_final.any()

def obtener_casas_cobro_base(*, deudas: list[str]) -> list[str]:
    # Paso 1: Cargar las Actualizaciones Masivas
    massive_df = load_masivas()
    # Paso 2: Filtrar por Id_Deuda las Deudas Brindadas
    massive_debts = massive_df[massive_df['Id_Deuda'].isin(deudas)]
    # Paso 3: Devolver la lista de Casas (Sin Duplicados ya que puede haber varios Registros por Deuda)
    if not massive_debts.empty:
        return list(dict.fromkeys(massive_debts['Casa_Cobro'].tolist()))
    else:
        return []

def unir_pdfs(*,archivos_pdf, contrasenia_inicial: str|None =None) -> bytes:
    """
    Une múltiples archivos PDF (provenientes de st.file_uploader) en un solo buffer en memoria.
    Soporta PDFs encriptados con una misma contraseña usando la versión moderna de pypdf.
    """
    if not isinstance(archivos_pdf, list):
        archivos_pdf = [archivos_pdf]

    writer = PdfWriter()

    for archivo in archivos_pdf:
        try:
            archivo.seek(0)
            reader = PdfReader(archivo)

            if reader.is_encrypted:
                if not contrasenia_inicial:
                    raise ValueError(f"El archivo '{archivo.name}' está protegido y no se envió contraseña.")

                resultado = reader.decrypt(contrasenia_inicial)
                if resultado == 0:
                    raise WrongPasswordError(f"La contraseña no es correcta para el archivo: {archivo.name}")

            writer.append(reader)

        except (FileNotDecryptedError, WrongPasswordError, ValueError):
            raise
        except Exception as e:
            if "password" in str(e).lower() or "decrypt" in str(e).lower():
                raise ValueError(f"Error de contraseña con el archivo: {archivo.name}") from e
            raise

    pdf_buffer = BytesIO()
    writer.write(pdf_buffer)
    writer.close()

    bytes_resultado = pdf_buffer.getvalue()
    pdf_buffer.close()

    return bytes_resultado