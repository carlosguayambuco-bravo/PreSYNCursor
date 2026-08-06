# Estándar usando Pep8
# Librerías de Python
# Librerías de Terceros
import numpy as np
import pandas as pd
from pandera.typing import DataFrame
import streamlit as st
# Librerías Locales
from data.data_loader import load_current_month_solicitudes, load_masivas
from data.data_uploader import update_solicitud_in_google_sheets, upload_log_to_sheets, upload_massive_solicitudes_to_google_sheets, upload_addendum_debt
from data.data_models import SolicitudesSchema, MasivasSchema, PlantillaSolicitudesSchema
from modules.classes import get_banned_manager
from services.google_drive import GoogleDriveService

def get_solicitud_txt(solicitud: pd.Series) -> str:
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
    for deuda in solicitud['Datos_Solicitud']:
        solicitud_txt += f"    - **Banco**: {deuda['Banco']}, **Numero_Credito**: {deuda['Numero_Credito']}, **Monto_Propuesto**: ${deuda['Monto_Propuesto']:,.2f}"
        if deuda.get('Num_Cuotas', 1) > 1:
            solicitud_txt += f", (**Num_Cuotas**: {deuda['Num_Cuotas']})"
        solicitud_txt += "\n"

    return solicitud_txt

def get_massive_solicitudes_txt(solicitudes_df: DataFrame[SolicitudesSchema]) -> str:
    """
    Genera un texto descriptivo para un conjunto de solicitudes.

    Args:
        solicitudes_df (DataFrame[SolicitudesSchema]): DataFrame con las solicitudes.

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
        es_portafolio = "Si" if (monto_portafolio > 0) else "No"
        if es_portafolio == "Si":
            str_portafolio = f"**Portafolio**: {monto_portafolio:,.0f}"
        else:
            str_portafolio = "***No es Portafolio***"
        descuento_formateado = f"**{casa_cobro}**: {valor:,.0f} ({descuento:.1%}) - {str_portafolio}"
        descuentos_formateados.append(descuento_formateado)

    return descuentos_formateados

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
    banner_manager = get_banned_manager()
    maskSinBan = solicitudes_df["ID_Solicitud"].apply(lambda x: not banner_manager.is_banned(x))
    return (maskSinTocar | maskBajoComite | maskTitularIlocalizable) & maskSinBan

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

    # Paso 2: Actualizar Solicitudes con mismas deudas, misma Casa_Cobro y mismo Tipo_Solicitud (Sin Responder)
    solicitudes_df: DataFrame[SolicitudesSchema] = load_current_month_solicitudes()
    idsFinal = ''.join([d['Id_Deuda'] for d in solicitud['JSON_Respuesta']])
    maskIds = (solicitudes_df['Ids_Deuda'] == idsFinal)
    maskCasa = (solicitudes_df['Casa_Cobro'] == solicitud['Casa_Cobro'])
    maskTipo = (solicitudes_df['Tipo_Solicitud'] == solicitud['Tipo_Solicitud'])
    maskSinResponder = obtener_mascara_sin_responder(solicitudes_df)
    maskFinal = maskIds & maskCasa & maskTipo & maskSinResponder

    curr_state = True # Inicializamos el True o False
    updated_ids = set() # Inicializamos el Set de IDs Actualizados
    for _, solicitud_to_update in solicitudes_df[maskFinal].iterrows():

        # Verificamos que no sea la solicitud actual, de lo contrario se salta la actualización
        if solicitud_to_update['ID_Solicitud'] == solicitud['ID_Solicitud']:
            continue

        solicitud_to_update['Estado_Solicitud'] = solicitud['Estado_Solicitud']
        solicitud_to_update['Metadata_Solicitud']['Metodo_Pago'] = solicitud['Metadata_Solicitud'].get('Metodo_Pago', '')
        solicitud_to_update['Metadata_Solicitud']['Comentario_Ejecutivo'] = solicitud['Metadata_Solicitud']['Comentario_Ejecutivo']
        solicitud_to_update['JSON_Respuesta'] = solicitud['JSON_Respuesta']
        solicitud_to_update['Fecha_Limite_Pago'] = solicitud['Fecha_Limite_Pago']
        solicitud_to_update['Ejecutivo'] = solicitud['Ejecutivo']
        solicitud_to_update['Fecha_Respuesta'] = solicitud['Fecha_Respuesta']

        # Actualizamos Addendums si hay
        if 'Addendums' in solicitud['Metadata_Solicitud']:
            solicitud_to_update['Metadata_Solicitud']['Addendums'] = solicitud['Metadata_Solicitud']['Addendums']

        # Actualizamos la Solicitud en Google Sheets
        curr_state = update_solicitud_in_google_sheets(solicitud_to_update) and curr_state

        # Verificamos que no haya habido algún error en la actualización
        if not curr_state:
            st.error(f"Error al actualizar la solicitud con ID: {solicitud_to_update['ID_Solicitud']}")
            return False

        # Agregamos el ID de la Solicitud a los Ids Banneados
        banned_manager = get_banned_manager()
        banned_manager.ban(solicitud_to_update['ID_Solicitud'])

        # Agregamos el ID de la Solicitud Actualizada al Set de IDs Actualizados
        updated_ids.add(solicitud_to_update['ID_Solicitud'])

    # Paso 3: Actualizar Sub-Solicitdues si no es necesario el Pago Total Obligatorio
    if solicitud['Metadata_Solicitud'].get('Pago_Total_Obligatorio', False):

        # Paso 3.1 Obtener las Sub-Solicitudes de la Solicitud Actual
        # Estás son solicitudes que tienen un subconjunto de los IDs de Deuda de la Solicitud Actual
        # Para esto necesitamos una Máscara que verifique que los IDs de Deuda de la Sub-Solicitud estén contenidos en los IDs de Deuda de la Solicitud Actual
        ids_solicitud_actual = set(d['Id_Deuda'] for d in solicitud['JSON_Respuesta'])
        mask_sub_solicitudes = solicitudes_df['Datos_Solicitud'].apply(lambda x: set(d['Id_Deuda'] for d in x).issubset(ids_solicitud_actual))
        # Creamos la Máscara como: mask_sub_solicitudes & maskCasa & maskTipo & maskSinResponder
        mask_sub_solicitudes_final = mask_sub_solicitudes & maskCasa & maskTipo & maskSinResponder

        for _,sub_solicitud in solicitudes_df[mask_sub_solicitudes_final].iterrows():

            # Verificamos que no sea la solicitud actual, de lo contrario se salta la actualización
            if sub_solicitud['ID_Solicitud'] == solicitud['ID_Solicitud']:
                continue

            ids_solicitud_actual = set(d['Id_Deuda'] for d in sub_solicitud['Datos_Solicitud'])
            sub_solicitud['Estado_Solicitud'] = solicitud['Estado_Solicitud']
            sub_solicitud['Metadata_Solicitud']['Metodo_Pago'] = solicitud['Metadata_Solicitud'].get('Metodo_Pago', '')
            sub_solicitud['Metadata_Solicitud']['Comentario_Ejecutivo'] = solicitud['Metadata_Solicitud']['Comentario_Ejecutivo']
            sub_solicitud['JSON_Respuesta'] = [ d for d in solicitud['JSON_Respuesta'] if d['Id_Deuda'] in ids_solicitud_actual ]
            sub_solicitud['Fecha_Limite_Pago'] = solicitud['Fecha_Limite_Pago']
            sub_solicitud['Ejecutivo'] = solicitud['Ejecutivo']
            sub_solicitud['Fecha_Respuesta'] = solicitud['Fecha_Respuesta']

            # Actualizamos Addendums si hay
            if 'Addendums' in solicitud['Metadata_Solicitud']:
                sub_solicitud['Metadata_Solicitud']['Addendums'] = solicitud['Metadata_Solicitud']['Addendums']

            # Actualizamos la Sub-Solicitud en Google Sheets
            curr_state = update_solicitud_in_google_sheets(sub_solicitud) and curr_state

            # Verificamos que no haya habido algún error en la actualización
            if not curr_state:
                st.error(f"Error al actualizar la sub-solicitud con ID: {sub_solicitud['ID_Solicitud']}")
                return False

            # Agregamos el ID de la Sub-Solicitud Actualizada al Set de IDs Actualizados
            updated_ids.add(sub_solicitud['ID_Solicitud'])

    # Por Último, subimos la solicitud Inicial a actualizar
    return update_solicitud_in_google_sheets(solicitud) and curr_state

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
            addendum.get('Monto_Actual', 0) > 0,
            addendum.get('Monto_Propuesto', 0) > 0
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
            monto_inicial=addendum.get('Monto_Actual', 0),
            monto_propuesto=addendum.get('Monto_Propuesto', None)
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

def generar_plantilla_masiva_solicitudes(solicitudes_df: DataFrame[SolicitudesSchema]) -> pd.DataFrame:
    """
    Genera una plantilla masiva de solicitudes a partir de un DataFrame de solicitudes.

    Args:
        solicitudes_df (DataFrame[SolicitudesSchema]): DataFrame con las solicitudes.

    Returns:
        pd.DataFrame: DataFrame con la plantilla masiva de solicitudes.
    """

    # Paso 1: Iterar sobre cada solicitud y llenar la plantilla
    filas = []
    for _, solicitud in solicitudes_df.iterrows():
        for deuda in solicitud['Datos_Solicitud']:
            nueva_fila = {
                'Tipo_Solicitud': solicitud['Tipo_Solicitud'],
                'Cedula': solicitud['Cedula'],
                'Nombre_Cliente': solicitud['Metadata_Solicitud']['Nombre_Cliente'],
                'Numero_Obligacion': deuda['Numero_Credito'],
                'Banco': deuda['Banco'],
                'Propuesta': deuda.get('Monto_Propuesto', np.nan),
                'Portafolio': '1' if len(solicitud['Datos_Solicitud']) > 1 else '',
                'Plazos': deuda.get('Num_Cuotas', ''),
            }
            filas.append(nueva_fila)

    # Creamos el DataFrame
    plantilla_df = pd.DataFrame(filas)

    # Quitamos Datos donde no haya Propuesta
    plantilla_df = plantilla_df.dropna(subset=['Propuesta'])

    # Ordenamos las Columnas correctamente según el Schema de PlantillaSolicitudesSchema
    plantilla_df = plantilla_df[PlantillaSolicitudesSchema.empty().columns]

    # Validamos el DataFrame con el Schema de PlantillaSolicitudesSchema
    plantilla_df = PlantillaSolicitudesSchema.validate(plantilla_df)

    # Ahora vamos a Quitar las Columnas de Portafolio y Plazos si no hay datos en ellas
    if plantilla_df['Portafolio'].nunique() == 1 and plantilla_df['Portafolio'].iloc[0] == '':
        plantilla_df = plantilla_df.drop(columns=['Portafolio'])
    if plantilla_df['Plazos'].nunique() == 1 and plantilla_df['Plazos'].iloc[0] == '':
        plantilla_df = plantilla_df.drop(columns=['Plazos'])

    return plantilla_df

def generar_descarga_masiva_solicitudes(*,solicitudes_df: DataFrame[SolicitudesSchema]) -> bytes:
    """
    Genera un archivo CSV para la descarga masiva de solicitudes.

    Args:
        solicitudes_df (pd.DataFrame): DataFrame con las solicitudes a descargar.

    Returns:
        bytes: Contenido del archivo CSV en formato binario.
    """
    # Paso 1: Generar la Plantilla Masiva de Solicitudes
    download_df = generar_plantilla_masiva_solicitudes(solicitudes_df)

    # Paso 2: Convertir el DataFrame a CSV en formato binario
    csv_bytes = download_df.to_csv(index=False).encode('utf-8')

    return csv_bytes

def subir_masivo_plantilla_solicitudes(solicitudes_df: DataFrame[SolicitudesSchema]) -> bool:
    """
    Sube una plantilla masiva de solicitudes a Google Sheets.

    Args:
        solicitudes_df (pd.DataFrame): DataFrame con las solicitudes a subir.

    Returns:
        bool: True si la subida fue exitosa, False en caso contrario.
    """
    # Paso 1: Generar la Plantilla Masiva de Solicitudes
    plantilla_df = generar_plantilla_masiva_solicitudes(solicitudes_df)

    # Paso 2: Registrar el Log de la Subida Masiva de Solicitudes
    upload_log_to_sheets(info="Subida de Plantilla Masiva de Solicitudes",
        detail=f"{st.session_state['user_email']} subió {len(plantilla_df)} solicitudes filtradas a Google Sheets.")

    # Paso 3: Subir la Plantilla Masiva a Google Sheets
    return upload_massive_solicitudes_to_google_sheets(plantilla_df)