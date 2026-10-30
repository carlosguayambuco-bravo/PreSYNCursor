# Estándar usando Pep8
# Librerías de Python
from time import sleep
from typing import Any, Optional
from uuid import uuid4
# Librerías de Terceros
import pandas as pd
import streamlit as st
from pypdf.errors import FileNotDecryptedError, WrongPasswordError
# Librerías Locales
from data.data_loader import (
    load_cartera_activa,
    load_cartera_backup,
    load_current_month_solicitudes,
    load_data_archivos_subidos,
    load_liquidaciones_hist,
    load_liquidaciones_mec,
    load_solicitudes_hist,
    obtener_info_basica_deuda,
)
from data.data_uploader import (
    update_archivo_subido_in_google_sheets,
    upload_archivo_subido_to_google_sheets,
)
from modules.constants import TIPO_ARCHIVO_ACUERDO_FIRMADO, TIPO_ARCHIVO_SOPORTE_PAGO
from modules.gest_sols import (
    add_images_to_pdf,
    add_metadata_to_pdf,
    convertir_imagenes_a_pdf,
    generar_nombre_acuerdo_firmado,
    generar_nombre_soporte_pago,
    obtener_ids_deuda_validos,
    obtener_link_archivo_drive,
    unir_pdfs,
)
from utils.helpers_general import cleanNumber, formatNumber, getBDDaysDiffFloat

# --- Funciones Auxiliares Generales ---

def _normalizar_id(valor: Any) -> str:
    """Convierte un valor en un ID limpio (sin .0 y sin espacios)."""
    if valor is None:
        return ''
    try:
        if pd.isna(valor):
            return ''
    except (TypeError, ValueError):
        pass
    return str(valor).replace('.0', '').strip()

def _numero(valor: Any) -> float:
    """Convierte un valor numérico de forma segura, devolviendo 0.0 si no es válido."""
    numero = cleanNumber(valor, default_nan=0.0)
    if numero is None or pd.isna(numero):
        return 0.0
    return float(numero)

def _separar_ids(valor: Any) -> list[str]:
    """Separa los Ids de Deuda almacenados como texto con guiones."""
    if valor is None:
        return []
    try:
        if pd.isna(valor):
            return []
    except (TypeError, ValueError):
        pass
    texto = str(valor).strip()
    if not texto or texto.lower() in {'nan', 'none', 'nat'}:
        return []
    return [
        _normalizar_id(parte)
        for parte in texto.split('-')
        if _normalizar_id(parte)
    ]

def _formatear_fecha(valor: Any, formato: str = '%d-%m-%Y') -> str:
    """Formatea una fecha de Pandas de forma segura."""
    fecha = pd.to_datetime(valor, errors='coerce')
    if pd.isna(fecha):
        return 'Sin Fecha'
    return fecha.strftime(formato)

def _obtener_solicitudes_acuerdos_exitosos(solicitudes_df: pd.DataFrame) -> pd.DataFrame:
    """Deja solo Acuerdos de Pago u Ofertas de Acuerdo exitosas."""
    if solicitudes_df.empty:
        return solicitudes_df.copy()
    base = solicitudes_df.copy()
    base = base[base['Tipo_Solicitud'].isin(['Acuerdo de Pago', 'Oferta de Acuerdo'])]
    base = base[base['Estado_Solicitud'] == 'Exitosa']
    return base

def _agregar_id_origen(solicitudes_df: pd.DataFrame) -> pd.DataFrame:
    """Agrega la columna Id_Solicitud_Origen a partir de Id_Respuesta_Autom."""
    base = solicitudes_df.copy()

    def _obtener_origen(row: pd.Series) -> str:
        metadata = row.get('Metadata_Solicitud', {})
        if not isinstance(metadata, dict):
            metadata = {}
        id_autom = _normalizar_id(metadata.get('Id_Respuesta_Autom'))
        return id_autom or _normalizar_id(row.get('ID_Solicitud'))

    base['Id_Solicitud_Origen'] = base.apply(_obtener_origen, axis=1)
    return base

def _obtener_registros_acuerdo(*, archivos_df: pd.DataFrame, id_solicitud: str) -> pd.DataFrame:
    """Obtiene los registros de Acuerdo Firmado de una solicitud, ordenados por fecha."""
    if archivos_df.empty:
        return archivos_df.copy()
    registros = archivos_df[
        (archivos_df['Tipo_Archivo'] == TIPO_ARCHIVO_ACUERDO_FIRMADO)
        & (archivos_df['Id_Solicitud'] == _normalizar_id(id_solicitud))
    ].copy()
    return registros.sort_values('Fecha_Subida', kind='stable')

def _obtener_soportes_por_deuda(*, archivos_df: pd.DataFrame, ids_deuda: list[str]) -> pd.DataFrame:
    """Obtiene el último Soporte de Pago subido para cada deuda."""
    if archivos_df.empty or not ids_deuda:
        return pd.DataFrame()
    soportes = archivos_df[
        archivos_df['Tipo_Archivo'] == TIPO_ARCHIVO_SOPORTE_PAGO
    ].copy()
    if soportes.empty:
        return pd.DataFrame()
    soportes['Id_Deuda'] = soportes['Ids_Deuda'].apply(_separar_ids)
    soportes = soportes.explode('Id_Deuda')
    soportes = soportes[soportes['Id_Deuda'].isin(ids_deuda)]
    if soportes.empty:
        return pd.DataFrame()
    soportes = soportes.sort_values('Fecha_Subida', kind='stable')
    soportes = soportes.drop_duplicates(subset=['Id_Deuda'], keep='last')
    return soportes.set_index('Id_Deuda')

def _cargar_archivos_subidos_seguro() -> Optional[pd.DataFrame]:
    """Carga la hoja de Archivos Subidos mostrando un error claro si falla."""
    try:
        return load_data_archivos_subidos()
    except Exception as e:
        st.error(
            "No se pudo cargar la hoja 'Archivos_Subidos': {}".format(e),
            icon="❌",
        )
        return None

def _obtener_folder_ids() -> tuple[str, str]:
    """Obtiene y valida los IDs de las carpetas de Drive desde los secretos."""
    try:
        drive_secrets = dict(st.secrets['google_drive'])
    except Exception:
        st.error(
            "No se encontró la sección `[google_drive]` en los secretos de Streamlit.",
            icon="❌",
        )
        return '', ''

    folder_acuerdos = str(drive_secrets.get('folder_acuerdos_firmados', '') or '').strip()
    folder_soportes = str(drive_secrets.get('folder_soportes_pago', '') or '').strip()

    faltantes = []
    if not folder_acuerdos:
        faltantes.append('folder_acuerdos_firmados')
    if not folder_soportes:
        faltantes.append('folder_soportes_pago')

    if faltantes:
        st.error(
            "Faltan los siguientes secretos en `[google_drive]`: **{}**. "
            "Configúralos antes de usar la pestaña de archivos.".format(
                ', '.join(faltantes)
            ),
            icon="❌",
        )
        return '', ''

    return folder_acuerdos, folder_soportes

def _construir_pdf_desde_archivos(*, archivos: list, password: Optional[str]) -> bytes:
    """Convierte los archivos subidos (PDFs e imágenes) en un único PDF."""
    archivos_pdf = [
        archivo for archivo in archivos
        if (getattr(archivo, 'type', '') == 'application/pdf')
        or str(getattr(archivo, 'name', '')).lower().endswith('.pdf')
    ]
    imagenes = [
        archivo for archivo in archivos
        if str(getattr(archivo, 'type', '')).startswith('image/')
        or str(getattr(archivo, 'name', '')).lower().endswith(('.png', '.jpg', '.jpeg'))
    ]

    if not archivos_pdf and not imagenes:
        raise ValueError("Debe subir al menos un archivo PDF o una imagen.")

    pdf_bytes = b''
    if archivos_pdf:
        pdf_bytes = unir_pdfs(
            archivos_pdf=archivos_pdf,
            contrasenia_inicial=password or None,
        )

    if imagenes:
        if pdf_bytes:
            pdf_bytes = add_images_to_pdf(pdf_bytes=pdf_bytes, images=imagenes)
        else:
            pdf_bytes = convertir_imagenes_a_pdf(imagenes=imagenes)

    if not pdf_bytes:
        raise ValueError("No se pudo construir el PDF con los archivos subidos.")

    return pdf_bytes

def _construir_metadata_archivo(
    *,
    cedula: str,
    referencia: str,
    ids_deuda: list[str],
    id_solicitud: Optional[str] = None,
) -> tuple[dict[str, str], pd.Timestamp]:
    """Construye la metadata que se insertará dentro del PDF y el timestamp de subida."""
    ahora = pd.Timestamp.now(tz='America/Bogota').tz_localize(None)
    metadata = {
        'Correo': st.session_state.get('user_email', ''),
        'Timestamp': ahora.isoformat(),
        'Cedula': _normalizar_id(cedula),
        'Referencia': _normalizar_id(referencia),
        'Ids_Deuda': '-'.join(_normalizar_id(id_deuda) for id_deuda in ids_deuda),
    }
    if id_solicitud:
        metadata['Id_Solicitud'] = _normalizar_id(id_solicitud)
    return metadata, ahora.floor('min')

def _crear_info_archivo(
    *,
    tipo_archivo: str,
    nombre_archivo: str,
    correo_subida: str,
    referencia: str,
    cedula: str,
    fecha_subida: pd.Timestamp,
    ids_deuda: list[str],
    id_solicitud: Optional[str] = None,
) -> dict[str, Any]:
    """Construye el registro que se guardará en la hoja Archivos_Subidos."""
    return {
        'Id_Archivo': str(uuid4()),
        'Id_Archivo_Drive': '',
        'Nombre_Archivo': nombre_archivo,
        'Correo_Subida': correo_subida,
        'Referencia': _normalizar_id(referencia),
        'Cedula': _normalizar_id(cedula),
        'Fecha_Subida': fecha_subida,
        'Tipo_Archivo': tipo_archivo,
        'Id_Solicitud': _normalizar_id(id_solicitud) if id_solicitud else '',
        'Ids_Deuda': '-'.join(_normalizar_id(id_deuda) for id_deuda in ids_deuda),
    }

def _agregar_mapa_cedulas(mapa: dict[str, str], solicitudes_df: pd.DataFrame) -> None:
    """Agrega al mapa Id_Deuda -> Cedula a partir de un DataFrame de solicitudes."""
    if solicitudes_df is None or solicitudes_df.empty:
        return
    for _, solicitud in solicitudes_df.iterrows():
        cedula = _normalizar_id(solicitud.get('Cedula', ''))
        if not cedula:
            continue
        for id_deuda in _separar_ids(solicitud.get('Ids_Deuda', '')):
            mapa.setdefault(id_deuda, cedula)
        for deuda in (solicitud.get('Datos_Solicitud', []) or []):
            id_deuda = _normalizar_id(deuda.get('Id_Deuda', ''))
            if id_deuda:
                mapa.setdefault(id_deuda, cedula)

def _resolver_cedula_deudas(*, deudas: list[str], solicitudes_df: pd.DataFrame) -> str:
    """Resuelve la cédula de un conjunto de deudas usando Sheets, Cartera y Metabase."""
    mapa: dict[str, str] = {}

    # Paso 1: Buscar en las solicitudes filtradas y en las del mes en curso
    _agregar_mapa_cedulas(mapa, solicitudes_df)
    try:
        _agregar_mapa_cedulas(mapa, load_current_month_solicitudes())
    except Exception:
        pass

    faltantes = [deuda for deuda in deudas if not mapa.get(deuda)]

    # Paso 2: Buscar en solicitudes históricas
    if faltantes:
        try:
            _agregar_mapa_cedulas(mapa, load_solicitudes_hist())
        except Exception:
            pass
        faltantes = [deuda for deuda in deudas if not mapa.get(deuda)]

    # Paso 3: Buscar en cartera activa y en el respaldo
    if faltantes:
        try:
            cartera_df = load_cartera_activa()
            for _, fila in cartera_df.iterrows():
                id_deuda = _normalizar_id(fila.get('Id_Deuda', ''))
                cedula = _normalizar_id(fila.get('Cedula', ''))
                if id_deuda and cedula:
                    mapa.setdefault(id_deuda, cedula)
        except Exception:
            pass
        faltantes = [deuda for deuda in deudas if not mapa.get(deuda)]

    if faltantes:
        try:
            backup_df = load_cartera_backup()
            for _, fila in backup_df.iterrows():
                id_deuda = _normalizar_id(fila.get('Id_Deuda', ''))
                cedula = _normalizar_id(fila.get('Cedula', ''))
                if id_deuda and cedula:
                    mapa.setdefault(id_deuda, cedula)
        except Exception:
            pass
        faltantes = [deuda for deuda in deudas if not mapa.get(deuda)]

    # Paso 4: Consultar Metabase por las deudas que sigan sin cédula
    for deuda in faltantes:
        info = obtener_info_basica_deuda(deuda=deuda)
        cedula = _normalizar_id(info.get('Cedula', ''))
        if cedula:
            mapa[deuda] = cedula

    # Paso 5: Validar que todas las deudas tengan cédula y que sea la misma
    deudas_sin_cedula = [deuda for deuda in deudas if not mapa.get(deuda)]
    if deudas_sin_cedula:
        st.error(
            "No se pudo obtener la cédula de las siguientes deudas: **{}**. "
            "Verifica que existan y vuelve a intentarlo.".format(
                ', '.join(str(deuda) for deuda in deudas_sin_cedula)
            ),
            icon="❌",
        )
        return ''

    cedulas = {mapa.get(deuda, '') for deuda in deudas if mapa.get(deuda, '')}
    if not cedulas:
        st.error(
            "No se pudo obtener la cédula de las deudas seleccionadas. "
            "Verifica que las deudas existan y vuelve a intentarlo.",
            icon="❌",
        )
        return ''

    if len(cedulas) > 1:
        st.error(
            "Las deudas seleccionadas pertenecen a clientes diferentes. "
            "Selecciona deudas de un mismo cliente para subir un soporte.",
            icon="❌",
        )
        return ''

    return cedulas.pop()

# --- Proceso de Subida ---

def _ejecutar_proceso_subida(
    *,
    state_key: str,
    password_key: str,
    archivos: list,
    folder_id: str,
    file_name: str,
    metadata_name: str,
    metadata: dict[str, Any],
    archivo_info: dict[str, Any],
    overwrite_record: Optional[pd.Series] = None,
    delete_previous: bool = False,
    mensaje_exito: str = "Archivo subido correctamente.",
    reset_keys: Optional[list[str]] = None,
) -> None:
    """
    Ejecuta la subida de un archivo a Drive y su registro en Sheets.

    Guarda el avance en st.session_state para que un fallo en Sheets no vuelva a
    subir el PDF a Drive y viceversa. En caso de fallo, deja el estado listo para
    mostrar un botón de reintento.
    """
    # Paso 1: Preparar el Estado de la Subida
    firma_archivos = '{}|{}'.format(
        int(delete_previous),
        '|'.join(
            '{}:{}:{}'.format(
                getattr(archivo, 'name', ''),
                getattr(archivo, 'size', 0),
                getattr(archivo, 'file_id', ''),
            )
            for archivo in archivos
        ),
    )
    state = st.session_state.get(state_key, {})
    if state.get('signature') != firma_archivos:
        state = {'signature': firma_archivos}
    state.setdefault('pdf_bytes', None)
    state.setdefault('drive_file_id', '')
    state.setdefault('sheets_done', False)
    state.setdefault('old_deleted', False)
    state.setdefault('archivo_info', dict(archivo_info))
    state['error'] = ''
    state['password_required'] = False
    st.session_state[state_key] = state

    progress = st.progress(0, text="Preparando el archivo...")
    drive_service = st.session_state['google_drive_service']
    error: Optional[str] = None
    error_password = False

    try:
        # Paso 2: Preparar el PDF e insertar la Metadata
        if not state.get('pdf_bytes'):
            progress.progress(10, text="Preparando el PDF...")
            password = st.session_state.get(password_key, '') or None
            pdf_bytes = _construir_pdf_desde_archivos(archivos=archivos, password=password)
            pdf_bytes = add_metadata_to_pdf(
                pdf_bytes=pdf_bytes,
                metadata_name=metadata_name,
                metadata=metadata,
                password=password,
            )
            state['pdf_bytes'] = pdf_bytes
            st.session_state[state_key] = state

        progress.progress(30, text="PDF preparado correctamente.")

        # Paso 3: Subir el PDF a Google Drive (si no se subió en un intento anterior)
        if not state.get('drive_file_id'):
            if delete_previous and overwrite_record is not None and not state.get('old_deleted'):
                old_file_id = _normalizar_id(overwrite_record.get('Id_Archivo_Drive', ''))
                if old_file_id:
                    progress.progress(40, text="Eliminando el archivo anterior...")
                    if not drive_service.delete_file(file_id=old_file_id):
                        raise RuntimeError(
                            "No se pudo eliminar el archivo anterior de Google Drive."
                        )
                state['old_deleted'] = True
                st.session_state[state_key] = state

            progress.progress(50, text="Subiendo el PDF a Google Drive...")
            file_id = drive_service.upload_file(
                file_bytes=state['pdf_bytes'],
                file_name=file_name,
                mime_type='application/pdf',
                folder_id=folder_id,
            )
            if not file_id:
                raise RuntimeError("No se pudo subir el PDF a Google Drive.")
            state['drive_file_id'] = file_id
            st.session_state[state_key] = state

        progress.progress(70, text="Archivo subido a Google Drive.")

        # Paso 4: Registrar en Google Sheets (si no se registró en un intento anterior)
        if not state.get('sheets_done'):
            info = dict(state.get('archivo_info', archivo_info))
            info['Id_Archivo_Drive'] = state['drive_file_id']

            if overwrite_record is not None:
                info['Id_Archivo'] = _normalizar_id(overwrite_record.get('Id_Archivo', ''))
                registrado = update_archivo_subido_in_google_sheets(
                    id_archivo=info['Id_Archivo'],
                    archivo_info=info,
                )
            else:
                registrado = upload_archivo_subido_to_google_sheets(archivo_info=info)

            if not registrado:
                raise RuntimeError("No se pudo guardar el registro en Google Sheets.")
            state['sheets_done'] = True
            st.session_state[state_key] = state

        # Paso 5: Finalizar
        progress.progress(100, text="Proceso completado.")
        st.toast(mensaje_exito, icon="✅")
        sleep(2)
        st.session_state.pop(state_key, None)
        for key in (reset_keys or []):
            st.session_state.pop(key, None)
        st.rerun()

    except (WrongPasswordError, FileNotDecryptedError) as e:
        error = str(e)
        error_password = True
    except ValueError as e:
        error = str(e)
        error_password = any(
            palabra in error.lower()
            for palabra in ('contrase', 'password', 'decrypt')
        )
    except Exception as e:
        error = str(e)

    # Paso 6: Guardar el Error y Pedir Reintento (sin volver a subir lo ya subido)
    if error:
        state['error'] = error
        state['password_required'] = error_password
        st.session_state[state_key] = state
        st.rerun()

def _mostrar_controles_estado_subida(
    *,
    state_key: str,
    password_key: str,
) -> bool:
    """Muestra el input de contraseña y el botón de reintento cuando hay un error."""
    state = st.session_state.get(state_key, {})
    if not state:
        return False

    if state.get('password_required'):
        st.info(
            "El PDF está protegido con contraseña. Ingresa la contraseña y vuelve a intentarlo.",
            icon="🔒",
        )
        st.text_input(
            "**Contraseña del PDF**",
            type="password",
            key=password_key,
            help="Ingresa la contraseña del PDF para poder procesarlo.",
        )

    if state.get('error'):
        st.error("Error en el proceso: {}".format(state['error']), icon="❌")
        return st.button(
            "**Reintentar**",
            key="{}_reintentar".format(state_key),
            type="primary",
            width="stretch",
        )

    return False

# --- Vista de Acuerdo de Pago Firmado ---

def _mostrar_vista_acuerdo_firmado(*, solicitudes_df: pd.DataFrame, folder_id: str) -> None:
    """Muestra el flujo para subir un Acuerdo de Pago Firmado."""
    st.subheader("📝 Subir Acuerdo de Pago Firmado")
    st.caption(
        "Selecciona la solicitud de origen y sube el acuerdo firmado por el cliente. "
        "Solo se muestran Acuerdos de Pago u Ofertas de Acuerdo exitosas."
    )

    archivos_df = _cargar_archivos_subidos_seguro()
    if archivos_df is None:
        return

    base = _obtener_solicitudes_acuerdos_exitosos(solicitudes_df=solicitudes_df)
    if base.empty:
        st.info(
            "No hay Acuerdos de Pago u Ofertas de Acuerdo exitosas en las solicitudes filtradas.",
            icon="ℹ️",
        )
        return

    base = _agregar_id_origen(solicitudes_df=base)
    origenes = base[base['ID_Solicitud'] == base['Id_Solicitud_Origen']].copy()
    if origenes.empty:
        st.info(
            "No se encontraron solicitudes de origen para los acuerdos filtrados.",
            icon="ℹ️",
        )
        return

    # Paso 1: Selector de Referencia
    referencias = sorted(origenes['Referencia'].dropna().unique().tolist())
    referencias = [referencia for referencia in referencias if str(referencia).strip()]
    if not referencias:
        st.info("No se encontraron referencias en las solicitudes de origen.", icon="ℹ️")
        return

    colReferencia, colSolicitud = st.columns(2, vertical_alignment="bottom")

    if st.session_state.get('archivos_acuerdo_referencia') not in referencias:
        st.session_state['archivos_acuerdo_referencia'] = referencias[0]

    with colReferencia:
        referencia = st.selectbox(
            "**Referencia**",
            options=referencias,
            key="archivos_acuerdo_referencia",
            help="Selecciona la referencia del cliente.",
        )

    solicitudes_referencia = origenes[origenes['Referencia'] == referencia].copy()
    solicitudes_referencia['_fecha_orden'] = pd.to_datetime(
        solicitudes_referencia['Fecha_Respuesta'], errors='coerce'
    )
    solicitudes_referencia = solicitudes_referencia.sort_values(
        ['_fecha_orden', 'Timestamp'],
        ascending=True,
        na_position='first',
    )

    ids_solicitud = solicitudes_referencia['ID_Solicitud'].tolist()
    if not ids_solicitud:
        st.info("No hay solicitudes de origen para la referencia seleccionada.", icon="ℹ️")
        return

    def _nombre_ejecutivo(row: pd.Series) -> str:
        ejecutivo = row.get('Ejecutivo')
        if pd.isna(ejecutivo) or not str(ejecutivo).strip():
            return 'Sin Asignar'
        return str(ejecutivo).split()[0].title()

    etiquetas_solicitud = {
        row['ID_Solicitud']: "ID: {} - {} - {}".format(
            row['ID_Solicitud'],
            _nombre_ejecutivo(row),
            _formatear_fecha(row.get('Fecha_Respuesta')),
        )
        for _, row in solicitudes_referencia.iterrows()
    }

    # Paso 2: Selector de Solicitud (por defecto la última)
    key_solicitud = "archivos_acuerdo_solicitud_{}".format(referencia)
    if st.session_state.get(key_solicitud) not in ids_solicitud:
        st.session_state[key_solicitud] = ids_solicitud[-1]

    with colSolicitud:
        id_solicitud = st.selectbox(
            "**ID de Solicitud**",
            options=ids_solicitud,
            index=len(ids_solicitud) - 1,
            format_func=lambda id_sol: etiquetas_solicitud.get(id_sol, id_sol),
            key=key_solicitud,
            help="Selecciona la solicitud de origen del acuerdo.",
        )

    solicitud = solicitudes_referencia[
        solicitudes_referencia['ID_Solicitud'] == id_solicitud
    ].iloc[0]

    ids_deuda = obtener_ids_deuda_validos(solicitud=solicitud)
    if not ids_deuda:
        st.error(
            "La solicitud seleccionada no tiene deudas con Monto_Propuesto mayor a 0.",
            icon="❌",
        )
        return

    # Paso 3: Verificar si ya existe un Acuerdo Firmado
    registros_previos = _obtener_registros_acuerdo(
        archivos_df=archivos_df,
        id_solicitud=id_solicitud,
    )
    registro_previo = registros_previos.iloc[-1] if not registros_previos.empty else None
    sobreescribir = False
    key_sobreescribir = "archivos_acuerdo_sobreescribir_{}".format(id_solicitud)

    if registro_previo is not None:
        st.warning(
            "El Acuerdo de Pago Firmado de esta solicitud ya fue subido previamente. "
            "Si continúas, se eliminará el archivo anterior y se actualizará su registro.",
            icon="⚠️",
        )
        sobreescribir = st.toggle(
            "Confirmo que deseo sobrescribir el Acuerdo de Pago Firmado",
            value=False,
            key=key_sobreescribir,
            help="Debes activar esta opción para reemplazar el archivo existente.",
        )
    else:
        key_sobreescribir = ''

    # Paso 4: Métricas de la Solicitud
    fecha_respuesta = pd.to_datetime(solicitud.get('Fecha_Respuesta'), errors='coerce')
    fecha_limite = pd.to_datetime(solicitud.get('Fecha_Limite_Pago'), errors='coerce')
    ahora = pd.Timestamp.now(tz='America/Bogota').tz_localize(None)
    json_respuesta = solicitud.get('JSON_Respuesta', [])
    if not isinstance(json_respuesta, list):
        json_respuesta = []
    datos_solicitud = solicitud.get('Datos_Solicitud', [])
    if not isinstance(datos_solicitud, list):
        datos_solicitud = []

    monto_total = sum(
        _numero(deuda.get('Monto_Propuesto', 0))
        for deuda in json_respuesta
    )
    ids_validos_set = set(ids_deuda)
    monto_actual = sum(
        _numero(deuda.get('Monto_Actual', 0))
        for deuda in datos_solicitud
        if _normalizar_id(deuda.get('Id_Deuda', '')) in ids_validos_set
    )

    colFechas, colValor = st.columns(2, border=True)
    with colFechas:
        if pd.notna(fecha_respuesta):
            dias_respuesta = getBDDaysDiffFloat(fecha_respuesta, ahora)
            st.metric(
                "**Fecha de Respuesta**",
                value=fecha_respuesta.strftime('%d-%m-%Y'),
                delta="Hace {:.1f} días hábiles".format(dias_respuesta),
                delta_color="gray",
                delta_arrow="off",
            )
        else:
            st.metric("**Fecha de Respuesta**", value="No Brindada")

        if pd.notna(fecha_limite):
            dias_limite = getBDDaysDiffFloat(fecha_limite, ahora)
            vencida = fecha_limite < ahora.normalize()
            st.metric(
                "**Fecha Límite de Pago**",
                value=fecha_limite.strftime('%d-%m-%Y'),
                delta="{} {:.1f} días hábiles".format(
                    "Retraso de" if vencida else "Faltan",
                    abs(dias_limite),
                ),
                delta_color="red" if vencida else "green",
                delta_arrow="down" if vencida else "up",
            )
        else:
            st.metric("**Fecha Límite de Pago**", value="No Brindada")

    with colValor:
        descuento = 1 - (monto_total / monto_actual) if monto_actual > 0 else 0
        st.metric(
            "**Valor Total a Pagar**",
            value=formatNumber(monto_total),
            delta="{:.1%} de Descuento".format(descuento) if monto_actual > 0 else "N/A",
            delta_color="gray",
            delta_arrow="off",
        )

    # Paso 5: Subida de Archivos
    archivos = st.file_uploader(
        "**Archivos del Acuerdo de Pago Firmado**",
        type=['pdf', 'png', 'jpg', 'jpeg'],
        accept_multiple_files=True,
        key="archivos_acuerdo_uploader_{}".format(id_solicitud),
        help="Puedes subir uno o varios PDFs e imágenes. Se unirán en un solo PDF.",
    )

    state_key = "archivos_acuerdo_estado_{}".format(id_solicitud)
    password_key = "archivos_acuerdo_password_{}".format(id_solicitud)

    reintentar = _mostrar_controles_estado_subida(
        state_key=state_key,
        password_key=password_key,
    )

    subir = st.button(
        "**Subir Acuerdo de Pago Firmado**",
        key="archivos_acuerdo_subir_{}".format(id_solicitud),
        type="primary",
        width="stretch",
        disabled=(
            not archivos
            or (registro_previo is not None and not sobreescribir)
        ),
        help="Sube el PDF a Drive y registra la información en Google Sheets.",
    )

    if (subir or reintentar) and (registro_previo is None or sobreescribir):
        metadata, fecha_subida = _construir_metadata_archivo(
            cedula=solicitud.get('Cedula', ''),
            referencia=solicitud.get('Referencia', ''),
            ids_deuda=ids_deuda,
            id_solicitud=id_solicitud,
        )
        nombre_archivo = generar_nombre_acuerdo_firmado(solicitud=solicitud)
        archivo_info = _crear_info_archivo(
            tipo_archivo=TIPO_ARCHIVO_ACUERDO_FIRMADO,
            nombre_archivo=nombre_archivo,
            correo_subida=st.session_state.get('user_email', ''),
            referencia=solicitud.get('Referencia', ''),
            cedula=solicitud.get('Cedula', ''),
            fecha_subida=fecha_subida,
            ids_deuda=ids_deuda,
            id_solicitud=id_solicitud,
        )

        _ejecutar_proceso_subida(
            state_key=state_key,
            password_key=password_key,
            archivos=archivos,
            folder_id=folder_id,
            file_name=nombre_archivo,
            metadata_name="Acuerdo_Firmado_Info_Metadata",
            metadata=metadata,
            archivo_info=archivo_info,
            overwrite_record=registro_previo,
            delete_previous=registro_previo is not None,
            mensaje_exito="Acuerdo de Pago Firmado subido correctamente.",
            reset_keys=[key_sobreescribir] if key_sobreescribir else None,
        )

# --- Vista de Soporte de Pago ---

def _mostrar_vista_soporte_pago(*, solicitudes_df: pd.DataFrame, folder_id: str) -> None:
    """Muestra el flujo para subir un Soporte de Pago de una o varias deudas."""
    st.subheader("🧾 Subir Soporte de Pago")
    st.caption(
        "Selecciona la referencia y las deudas liquidadas que cubre el soporte. "
        "Puedes subir un PDF o imágenes; se unirán en un solo archivo."
    )

    archivos_df = _cargar_archivos_subidos_seguro()
    if archivos_df is None:
        return

    # Paso 1: Cargar Liquidaciones
    liquidaciones = load_liquidaciones_mec()
    # Leemos el estado del toggle antes de renderizarlo para que, al activarlo,
    # las referencias históricas ya estén disponibles en el mismo rerun.
    incluir_historial_previo = bool(st.session_state.get("archivos_soporte_incluir_historial", False))
    if incluir_historial_previo:
        historicas = load_liquidaciones_hist()
        liquidaciones = pd.concat([liquidaciones, historicas], ignore_index=True)

    if liquidaciones.empty:
        st.info("No se encontraron liquidaciones para mostrar.", icon="ℹ️")
        return

    liquidaciones = liquidaciones.sort_values('Fecha_Liq', ascending=False)
    liquidaciones = liquidaciones.drop_duplicates(subset=['Id_Deuda'], keep='first')

    referencias = sorted(liquidaciones['Referencia'].dropna().unique().tolist())
    referencias = [referencia for referencia in referencias if str(referencia).strip()]
    if not referencias:
        st.info("No se encontraron referencias en las liquidaciones.", icon="ℹ️")
        return

    colReferencia, colDeudas = st.columns(2, vertical_alignment="top")

    if st.session_state.get('archivos_soporte_referencia') not in referencias:
        st.session_state['archivos_soporte_referencia'] = referencias[0]

    # Paso 2: Selector de Referencia e Inclusión de Históricos
    with colReferencia:
        referencia = st.selectbox(
            "**Referencia**",
            options=referencias,
            key="archivos_soporte_referencia",
            help="Selecciona la referencia del cliente.",
        )
        st.toggle(
            "Incluir Liquidaciones Anteriores",
            value=incluir_historial_previo,
            key="archivos_soporte_incluir_historial",
            help="Incluye las liquidaciones históricas además de las del mes en curso.",
        )

    deudas_referencia = liquidaciones[liquidaciones['Referencia'] == referencia].copy()
    deudas_referencia = deudas_referencia.sort_values('Fecha_Liq', ascending=False)
    deudas_referencia = deudas_referencia.drop_duplicates(subset=['Id_Deuda'], keep='first')
    ids_disponibles = deudas_referencia['Id_Deuda'].tolist()
    etiquetas_deuda = {
        row['Id_Deuda']: "{} | {} | {}".format(
            row['Id_Deuda'],
            formatNumber(_numero(row.get('PaB_Liq', 0))),
            _formatear_fecha(row.get('Fecha_Liq')),
        )
        for _, row in deudas_referencia.iterrows()
    }

    # Paso 3: Selector de Deudas
    key_deudas = "archivos_soporte_deudas_{}".format(referencia)
    seleccion_previa = st.session_state.get(key_deudas, [])
    if not isinstance(seleccion_previa, list):
        seleccion_previa = []
    if seleccion_previa:
        st.session_state[key_deudas] = [
            id_deuda for id_deuda in seleccion_previa if id_deuda in ids_disponibles
        ]

    with colDeudas:
        deudas_seleccionadas = st.multiselect(
            "**Ids de Deuda**",
            options=ids_disponibles,
            format_func=lambda id_deuda: etiquetas_deuda.get(id_deuda, id_deuda),
            key=key_deudas,
            help="Selecciona una o varias deudas que cubre el soporte.",
        )

    if not deudas_seleccionadas:
        st.info("Selecciona al menos una deuda para continuar.", icon="ℹ️")
        return

    # Paso 4: Verificar Soportes ya Subidos
    soportes_previos = _obtener_soportes_por_deuda(
        archivos_df=archivos_df,
        ids_deuda=deudas_seleccionadas,
    )
    deudas_ya_subidas = set(soportes_previos.index) if not soportes_previos.empty else set()
    todas_subidas = set(deudas_seleccionadas).issubset(deudas_ya_subidas)
    continuar_sobreescritura = True
    key_sobreescribir = "archivos_soporte_sobreescribir_{}_{}".format(
        referencia, "_".join(deudas_seleccionadas)
    )

    if todas_subidas:
        st.warning(
            "Todas las deudas seleccionadas ya tienen un Soporte de Pago subido. "
            "Si continúas, se agregará un nuevo soporte y las vistas mostrarán el más reciente.",
            icon="⚠️",
        )
        continuar_sobreescritura = st.toggle(
            "Confirmo que deseo agregar un nuevo Soporte de Pago",
            value=False,
            key=key_sobreescribir,
            help="Debes activar esta opción para continuar con deudas ya soportadas.",
        )
    elif deudas_ya_subidas:
        st.info(
            "{} de las {} deudas seleccionadas ya tienen soporte. "
            "Se agregará un nuevo registro y se conservarán los anteriores.".format(
                len(deudas_ya_subidas), len(deudas_seleccionadas)
            ),
            icon="ℹ️",
        )

    # Paso 5: Resolver Cédula del Cliente
    cedula = _resolver_cedula_deudas(
        deudas=deudas_seleccionadas,
        solicitudes_df=solicitudes_df,
    )
    if not cedula:
        return

    # Paso 6: Subida de Archivos
    sufijo_deudas = "_".join(deudas_seleccionadas)
    archivos = st.file_uploader(
        "**Archivos del Soporte de Pago**",
        type=['pdf', 'png', 'jpg', 'jpeg'],
        accept_multiple_files=True,
        key="archivos_soporte_uploader_{}_{}".format(referencia, sufijo_deudas),
        help="Puedes subir uno o varios PDFs e imágenes. Se unirán en un solo PDF.",
    )

    state_key = "archivos_soporte_estado_{}_{}".format(referencia, sufijo_deudas)
    password_key = "archivos_soporte_password_{}_{}".format(referencia, sufijo_deudas)

    reintentar = _mostrar_controles_estado_subida(
        state_key=state_key,
        password_key=password_key,
    )

    subir = st.button(
        "**Subir Soporte de Pago**",
        key="archivos_soporte_subir_{}".format(referencia),
        type="primary",
        width="stretch",
        disabled=not archivos or not continuar_sobreescritura,
        help="Sube el PDF a Drive y registra la información en Google Sheets.",
    )

    if (subir or reintentar) and continuar_sobreescritura:
        metadata, fecha_subida = _construir_metadata_archivo(
            cedula=cedula,
            referencia=referencia,
            ids_deuda=deudas_seleccionadas,
        )
        nombre_archivo = generar_nombre_soporte_pago(
            cedula=cedula,
            ids_deuda=deudas_seleccionadas,
        )
        archivo_info = _crear_info_archivo(
            tipo_archivo=TIPO_ARCHIVO_SOPORTE_PAGO,
            nombre_archivo=nombre_archivo,
            correo_subida=st.session_state.get('user_email', ''),
            referencia=referencia,
            cedula=cedula,
            fecha_subida=fecha_subida,
            ids_deuda=deudas_seleccionadas,
            id_solicitud=None,
        )

        _ejecutar_proceso_subida(
            state_key=state_key,
            password_key=password_key,
            archivos=archivos,
            folder_id=folder_id,
            file_name=nombre_archivo,
            metadata_name="Soporte_Pago_Info_Metadata",
            metadata=metadata,
            archivo_info=archivo_info,
            overwrite_record=None,
            delete_previous=False,
            mensaje_exito="Soporte de Pago subido correctamente.",
            reset_keys=[key_sobreescribir],
        )

# --- Vista de Crear Carpeta con Filtros ---

def _crear_carpeta_con_accesos(
    *,
    es_acuerdos: bool,
    base_folder_id: str,
    archivos_match: pd.DataFrame,
) -> None:
    """Crea/limpia la carpeta personal y agrega accesos directos a los archivos filtrados."""
    email = st.session_state.get('user_email', '')
    prefijo = email.split('@')[0]
    nombre_carpeta = "{}_{}".format(
        'Acs_Firmados' if es_acuerdos else 'Soportes',
        prefijo,
    )
    state_key = "archivos_carpeta_id_{}".format('acuerdos' if es_acuerdos else 'soportes')
    progress = st.progress(0, text="Verificando la carpeta...")
    drive_service = st.session_state['google_drive_service']

    try:
        # Paso 1: Verificar o Crear la Carpeta
        encontrada = drive_service.find_folder(
            folder_name=nombre_carpeta,
            parent_id=base_folder_id,
        )
        if encontrada is None:
            raise RuntimeError("No se pudo verificar si la carpeta existe en Google Drive.")

        folder_id = encontrada or st.session_state.get(state_key, '')
        if not folder_id:
            progress.progress(15, text="Creando la carpeta...")
            folder_id = drive_service.create_folder(
                folder_name=nombre_carpeta,
                parent_id=base_folder_id,
            )
        if not folder_id:
            raise RuntimeError("No se pudo crear la carpeta en Google Drive.")
        st.session_state[state_key] = folder_id

        # Paso 2: Limpiar la Carpeta
        progress.progress(35, text="Limpiando la carpeta...")
        if not drive_service.delete_folder_contents(folder_id):
            raise RuntimeError("No se pudo limpiar el contenido de la carpeta.")

        # Paso 3: Agregar Accesos Directos
        archivos_unicos = archivos_match[
            archivos_match['Id_Archivo_Drive'].astype(str).str.strip() != ''
        ].drop_duplicates(subset=['Id_Archivo_Drive'], keep='last')
        total_archivos = len(archivos_unicos)
        if total_archivos == 0:
            raise RuntimeError("No hay archivos válidos para agregar a la carpeta.")

        for indice, (_, archivo) in enumerate(archivos_unicos.iterrows(), start=1):
            progreso = 35 + int((indice / total_archivos) * 60)
            progress.progress(
                min(progreso, 95),
                text="Agregando acceso directo {} de {}...".format(indice, total_archivos),
            )
            acceso_id = drive_service.create_shortcut(
                target_file_id=_normalizar_id(archivo.get('Id_Archivo_Drive', '')),
                folder_id=folder_id,
                shortcut_name=str(archivo.get('Nombre_Archivo', 'Archivo PDF')),
            )
            if not acceso_id:
                raise RuntimeError(
                    "No se pudo crear el acceso directo para el archivo '{}'.".format(
                        archivo.get('Nombre_Archivo', '')
                    )
                )

        progress.progress(100, text="Carpeta creada correctamente.")
        colExito, colLink = st.columns([3, 2], vertical_alignment="center")
        with colExito:
            mensaje_accesos = (
                "Se creó 1 acceso directo en la carpeta '{}'.".format(nombre_carpeta)
                if total_archivos == 1
                else "Se crearon {} accesos directos en la carpeta '{}'.".format(
                    total_archivos, nombre_carpeta
                )
            )
            st.success(mensaje_accesos, icon="✅")
        with colLink:
            st.link_button(
                "**Ir a la Carpeta**",
                url="https://drive.google.com/drive/folders/{}".format(folder_id),
                width="stretch",
                type="primary",
            )

    except Exception as e:
        st.error("Error al crear la carpeta: {}".format(e), icon="❌")

def _mostrar_vista_carpeta_filtrada(
    *,
    solicitudes_df: pd.DataFrame,
    folder_acuerdos: str,
    folder_soportes: str,
) -> None:
    """Muestra el flujo para crear una carpeta con accesos directos filtrados."""
    st.subheader("📂 Crear Carpeta de Soportes con Filtros")
    st.caption(
        "Crea una carpeta personal con accesos directos a los archivos que coinciden "
        "con los filtros actuales de solicitudes exitosas."
    )

    opcion = st.radio(
        "**Tipo de Archivo**",
        options=['Acuerdos de Pago Firmados', 'Soportes de Pago'],
        horizontal=True,
        key="archivos_carpeta_tipo",
    )
    es_acuerdos = opcion == 'Acuerdos de Pago Firmados'
    tipo_archivo = (
        TIPO_ARCHIVO_ACUERDO_FIRMADO if es_acuerdos else TIPO_ARCHIVO_SOPORTE_PAGO
    )
    base_folder_id = folder_acuerdos if es_acuerdos else folder_soportes

    archivos_df = _cargar_archivos_subidos_seguro()
    if archivos_df is None:
        return

    archivos_tipo = archivos_df[archivos_df['Tipo_Archivo'] == tipo_archivo].copy()
    base = _obtener_solicitudes_acuerdos_exitosos(solicitudes_df=solicitudes_df)

    if base.empty:
        st.info(
            "No hay solicitudes exitosas de Acuerdo de Pago u Oferta de Acuerdo "
            "con los filtros actuales.",
            icon="ℹ️",
        )

    # Paso 1: Calcular Coincidencias
    if es_acuerdos:
        base_origen = _agregar_id_origen(solicitudes_df=base) if not base.empty else base
        ids_origen = set(base_origen['Id_Solicitud_Origen']) if not base_origen.empty else set()
        archivos_match = archivos_tipo[
            archivos_tipo['Id_Solicitud'].isin(ids_origen)
        ].copy()

        ids_deuda_match: set[str] = set()
        if not archivos_match.empty:
            for ids_deuda in archivos_match['Ids_Deuda']:
                ids_deuda_match.update(_separar_ids(ids_deuda))

        numero_deudas = len(ids_deuda_match)
    else:
        deudas_base: set[str] = set()
        for _, solicitud in base.iterrows():
            deudas_base.update(obtener_ids_deuda_validos(solicitud=solicitud))

        deudas_match: set[str] = set()
        if not archivos_tipo.empty and deudas_base:
            soportes_exploded = archivos_tipo.copy()
            soportes_exploded['Id_Deuda'] = soportes_exploded['Ids_Deuda'].apply(_separar_ids)
            soportes_exploded = soportes_exploded.explode('Id_Deuda')
            deudas_match = set(soportes_exploded['Id_Deuda'].dropna().unique()) & deudas_base
            ids_archivo_match = soportes_exploded[
                soportes_exploded['Id_Deuda'].isin(deudas_match)
            ]['Id_Archivo'].unique()
            archivos_match = archivos_tipo[
                archivos_tipo['Id_Archivo'].isin(ids_archivo_match)
            ].copy()
        else:
            archivos_match = archivos_tipo.iloc[0:0].copy()

        numero_deudas = len(deudas_match)

    archivos_match = archivos_match[
        archivos_match['Id_Archivo_Drive'].astype(str).str.strip() != ''
    ].drop_duplicates(subset=['Id_Archivo_Drive'], keep='last')
    if not archivos_match.empty:
        archivos_match = archivos_match.sort_values('Fecha_Subida', ascending=False)

    numero_clientes = archivos_match['Cedula'].nunique() if not archivos_match.empty else 0
    numero_archivos = archivos_match['Id_Archivo_Drive'].nunique() if not archivos_match.empty else 0

    # Paso 2: Resumen
    colClientes, colDeudas, colArchivos = st.columns(3, border=True)
    with colClientes:
        st.metric("**Número de Clientes**", value=numero_clientes)
    with colDeudas:
        st.metric("**Número de Deudas/Obligaciones**", value=numero_deudas)
    with colArchivos:
        st.metric("**Número de Archivos Encontrados**", value=numero_archivos)

    # Paso 3: Tabla de Archivos
    if archivos_match.empty:
        st.info("No se encontraron archivos que coincidan con los filtros.", icon="ℹ️")
    else:
        tabla = archivos_match.copy()
        tabla['Link al PDF'] = tabla['Id_Archivo_Drive'].apply(obtener_link_archivo_drive)
        tabla['Fecha_Subida'] = pd.to_datetime(
            tabla['Fecha_Subida'], errors='coerce'
        ).dt.strftime('%Y-%m-%d %H:%M')
        tabla = tabla[['Correo_Subida', 'Fecha_Subida', 'Cedula', 'Referencia', 'Link al PDF']]
        tabla = tabla.rename(columns={
            'Correo_Subida': 'Quién lo Subió',
            'Fecha_Subida': 'Cuándo lo Subió',
            'Cedula': 'Cédula Asociada',
            'Referencia': 'Referencia Asociada',
        })
        st.dataframe(
            tabla,
            column_config={
                'Link al PDF': st.column_config.LinkColumn(
                    'Link al PDF',
                    display_text='Abrir PDF',
                ),
            },
            hide_index=True,
            height=300,
            width='stretch',
        )

    # Paso 4: Botón para Crear la Carpeta
    if st.button(
        "**Crear Carpeta con Accesos Directos**",
        key="archivos_carpeta_crear_{}".format('acuerdos' if es_acuerdos else 'soportes'),
        type="primary",
        width="stretch",
        disabled=archivos_match.empty,
        help="Crea la carpeta personal, la limpia y agrega los accesos directos.",
    ):
        _crear_carpeta_con_accesos(
            es_acuerdos=es_acuerdos,
            base_folder_id=base_folder_id,
            archivos_match=archivos_match,
        )

# --- Función Principal de la Pestaña ---

def mostrar_pestana_archivos(*, solicitudes_df: pd.DataFrame, es_ejecutivo: bool = False) -> None:
    """
    Muestra la pestaña de subida y organización de Acuerdos Firmados y Soportes de Pago.

    Args:
        solicitudes_df (pd.DataFrame): Solicitudes filtradas de la vista actual.
        es_ejecutivo (bool): Si es True, habilita la creación de carpetas con filtros.
    """
    # Paso 1: Validar los Secretos de Google Drive
    folder_acuerdos, folder_soportes = _obtener_folder_ids()
    if not folder_acuerdos or not folder_soportes:
        return

    st.title("📁 Archivos de Acuerdos y Soportes")
    st.caption(
        "Centraliza los Acuerdos de Pago Firmados y los Soportes de Pago, "
        "y genera carpetas con accesos directos para las auditorías de cierre."
    )

    # Paso 2: Seleccionar la Acción
    opciones = [
        'Subir Acuerdo de Pago Firmado',
        'Subir Soporte de Pago',
    ]
    if es_ejecutivo:
        opciones.append('Crear Carpeta de Soportes con Filtros')

    # Si el usuario cambió de rol, evitamos conservar una opción que ya no existe
    if st.session_state.get('archivos_accion_principal') not in opciones:
        st.session_state['archivos_accion_principal'] = opciones[0]

    opcion = st.radio(
        "**¿Qué deseas hacer?**",
        options=opciones,
        horizontal=True,
        key="archivos_accion_principal",
    )

    st.divider()

    # Paso 3: Mostrar la Vista Correspondiente
    if opcion == 'Subir Acuerdo de Pago Firmado':
        _mostrar_vista_acuerdo_firmado(
            solicitudes_df=solicitudes_df,
            folder_id=folder_acuerdos,
        )
    elif opcion == 'Subir Soporte de Pago':
        _mostrar_vista_soporte_pago(
            solicitudes_df=solicitudes_df,
            folder_id=folder_soportes,
        )
    else:
        _mostrar_vista_carpeta_filtrada(
            solicitudes_df=solicitudes_df,
            folder_acuerdos=folder_acuerdos,
            folder_soportes=folder_soportes,
        )
