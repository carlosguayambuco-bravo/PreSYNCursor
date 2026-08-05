# Estándar usando Pep8
# Librerías de Python
# Librerías de Terceros
import pandas as pd
from pandera.typing import DataFrame
import streamlit as st
# Librerías Locales
from data.data_loader import load_current_month_solicitudes
from data.data_uploader import update_solicitud_in_google_sheets
from data.data_models import SolicitudesSchema
from modules.classes import get_banned_manager
from services.google_drive import GoogleDriveService

def obtener_mascara_sin_responder(solicitudes_df: DataFrame[SolicitudesSchema]) -> pd.Series:
    """
    Filtra las solicitudes que no han sido respondidas.

    Args:
        solicitudes_df (DataFrame[SolicitudesSchema]): DataFrame con todas las solicitudes.

    Returns:
        pd.Series: Serie con las solicitudes sin responder.
    """
    maskSinTocar = solicitudes_df["Estado_Solicitud"] == "Sin Tocar"
    maskBajoComite = solicitudes_df["Metadata_Solicitud"].apply(lambda x: x.get("Estado_Comite", 0)  == 1) & (solicitudes_df["Estado_Solicitud"] == "Bajo Comité")
    maskTitularIlocalizable = solicitudes_df["Metadata_Solicitud"].apply(lambda x: x.get("Estado_Titular_Ilocalizable", 0) == 1) & (solicitudes_df["Estado_Solicitud"] == "Titular Ilocalizable")
    return (maskSinTocar | maskBajoComite | maskTitularIlocalizable)

def distribuir_resultado_solicitud(solicitud: pd.Series) -> bool:
    """
    Distribuye el resultado de la solicitud a las diferentes solicitudes disponibles

    Args:
        solicitud (pd.Series): Información de la solicitud.

    Returns:
        bool: True si la distribución fue exitosa, False en caso contrario.
    """
    # Paso 1: Verificar que se puede Distribuir el Resultado de la Solicitud
    if solicitud['Estado_Solicitud'] != "Exitoso":
        # Solo actualizamos la Solicitud y ya
        return update_solicitud_in_google_sheets(solicitud)

    # Paso 2: Actualizar Solicitudes con mismas deudas, misma Casa_Cobro y mismo Tipo_Solicitud
    solicitudes_df: DataFrame[SolicitudesSchema] = load_current_month_solicitudes()
    idsFinal = ''.join([d['Id_Deuda'] for d in solicitud['JSON_Respuesta']])
    maskIds = (solicitudes_df['Ids_Deuda'] == idsFinal)
    maskCasa = (solicitudes_df['Casa_Cobro'] == solicitud['Casa_Cobro'])
    maskTipo = (solicitudes_df['Tipo_Solicitud'] == solicitud['Tipo_Solicitud'])
    maskFinal = maskIds & maskCasa & maskTipo

    curr_state = True # Inicializamos el True o False
    for _, solicitud_to_update in solicitudes_df[maskFinal].iterrows():
        solicitud_to_update['Estado_Solicitud'] = solicitud['Estado_Solicitud']
        solicitud_to_update['Metadata_Solicitud']['Metodo_Pago'] = solicitud['Metadata_Solicitud'].get('Metodo_Pago', '')
        solicitud_to_update['Metadata_Solicitud']['Comentario_Ejecutivo'] = solicitud['Metadata_Solicitud']['Comentario_Ejecutivo']
        solicitud_to_update['JSON_Respuesta'] = solicitud['JSON_Respuesta']
        solicitud_to_update['Fecha_Limite_Pago'] = solicitud['Fecha_Limite_Pago']
        solicitud_to_update['Ejecutivo'] = solicitud['Ejecutivo']
        solicitud_to_update['Fecha_Respuesta'] = solicitud['Fecha_Respuesta']

        # Actualizamos la Solicitud en Google Sheets
        curr_state = update_solicitud_in_google_sheets(solicitud_to_update) and curr_state

        # Verificamos que no haya habido algún error en la actualización
        if not curr_state:
            st.error(f"Error al actualizar la solicitud con ID: {solicitud_to_update['ID_Solicitud']}")
            return False

        # Agregamos el ID de la Solicitud a los Ids Banneados
        banned_manager = get_banned_manager()
        banned_manager.ban(solicitud_to_update['ID_Solicitud'])

    return curr_state


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
        Ids_Deudas='-'.join(str(d['Id_Deuda']) for d in solicitud_info['JSON_Respuesta']),
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
    folder_id = st.secrets['google_drive']['folder_id']
    # Paso 4: Subir el Archivo a Google Drive
    file_id = google_drive_service.upload_file(
        file_bytes=pdf_bytes,
        file_name=file_name,
        mime_type='application/pdf',
        folder_id=folder_id
    )
    # Paso 5: Retornar el ID del Archivo Subido
    return file_id

def generar_descarga_masiva_solicitudes(*,solicitudes_df: pd.DataFrame) -> bytes:
    """
    Genera un archivo CSV para la descarga masiva de solicitudes.

    Args:
        solicitudes_df (pd.DataFrame): DataFrame con las solicitudes a descargar.

    Returns:
        bytes: Contenido del archivo CSV en formato binario.
    """
    # Paso 1: Definir los Campos que se necesitan
    data_dict = {
        'Id_Solicitud': [],
        'Tipo_Solicitud': [],
        'Cedula': [],
        'Nombre_Cliente': [],
        'Id_Deuda': [],
        'Numero_Credito': [],
        'Banco': [],
        'Monto_Propuesto': [],
        'Numero_Cuotas': [],
        'Es_Portafolio': [],
    }

    # Paso 2: Iterar sobre cada solicitud y sus deudas para llenar el diccionario
    for _, solicitud in solicitudes_df.iterrows():
        for deuda in solicitud['Datos_Solicitud']:
            data_dict['Id_Solicitud'].append(solicitud['ID_Solicitud'])
            data_dict['Tipo_Solicitud'].append(solicitud['Tipo_Solicitud'])
            data_dict['Cedula'].append(solicitud['Cedula'])
            data_dict['Nombre_Cliente'].append(solicitud['Metadata_Solicitud']['Nombre_Cliente'])
            data_dict['Id_Deuda'].append(deuda['Id_Deuda'])
            data_dict['Numero_Credito'].append(deuda['Numero_Credito'])
            data_dict['Banco'].append(deuda['Banco'])
            data_dict['Monto_Propuesto'].append(deuda.get('Monto_Propuesto', ''))
            data_dict['Numero_Cuotas'].append(deuda.get('Num_Cuotas', ''))
            data_dict['Es_Portafolio'].append('1' if len(solicitud['Datos_Solicitud']) > 1 else '')

    # Paso 3: Crear un DataFrame a partir del diccionario
    download_df = pd.DataFrame(data_dict)

    # Paso 4: Verificaciones
    # Si Numero_Cuotas siempre es 1, se quita la columna
    if download_df['Numero_Cuotas'].nunique() == 1 and download_df['Numero_Cuotas'].iloc[0] == 1:
        download_df.drop(columns=['Numero_Cuotas'], inplace=True)
    # Si Es_Portafolio siempre esta vacio, se quita la columna
    if download_df['Es_Portafolio'].nunique() == 1 and download_df['Es_Portafolio'].iloc[0] == '':
        download_df.drop(columns=['Es_Portafolio'], inplace=True)

    # Paso 5: Convertir el DataFrame a CSV en formato binario
    csv_bytes = download_df.to_csv(index=False).encode('utf-8')

    return csv_bytes