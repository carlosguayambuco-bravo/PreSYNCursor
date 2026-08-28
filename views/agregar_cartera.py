# Estándar usando Pep8
# Librerías de Python
import io
from typing import Optional
import uuid
from time import sleep, time
# Librerías de Terceros
import numpy as np
import pandas as pd
import streamlit as st
from pandera.errors import SchemaErrors
# Librerías Locales
from data.data_loader import load_cartera_activa, load_pendiente_cruce, load_pendiente_cruce_con_cambios
from data.data_models import InputCruceSchema
from data.data_uploader import upload_base_cruce_info
from modules.forms import obtener_datos_completos_deudas
from modules.id_aut_deud.deuda_matcher import match_deudas
from modules.id_aut_deud.helpers import (
    COL_BANCO, COL_CEDULA, COL_CREDITO, COL_ID_CRUCE, COL_ID_DEUDA, COL_MONTO_ACTUAL,
    COL_MONTO_PROPUESTO, COL_NOMBRE,
    ETIQUETA_EXACTO, ETIQUETA_DUPLICADO, ETIQUETA_AMBIGUO, ETIQUETA_ADDENDUM, ETIQUETA_NULO,
    aplicar_cambios_id_definitivo, build_pendiente_cruce_df, limpiar_base_subida,
    transform_portafolio, generateFileName, uploadDBtoDrive,
)
from ui.cruce_deudas_components import (
    LLAVE_CAMBIOS_ID_DEFINITIVO, mostrar_deudas_cruce_paginadas, mostrar_filtros_cruce,
)
from utils.helpers_general import cleanNumber

ETIQUETAS_CRUCE = [ETIQUETA_EXACTO, ETIQUETA_DUPLICADO, ETIQUETA_AMBIGUO, ETIQUETA_ADDENDUM, ETIQUETA_NULO]

MIMETYPES = {
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'csv': 'text/csv',
}

COLUMNAS_MAPEABLES = [
    (COL_CEDULA, 'Cedula', ['cedula', 'documento', 'identificacion','cédula']),
    (COL_NOMBRE, 'Nombre del Cliente', ['nombre', 'cliente']),
    (COL_BANCO, 'Banco', ['banco', 'entidad','portafolio']),
    (COL_CREDITO, 'Número de Crédito', ['credito', 'numero crédito','numero_producto','numero_credito']),
    (COL_MONTO_ACTUAL, 'Monto Actual', ['monto actual', 'deuda', 'saldo', 'saldo insoluto']),
    (COL_ID_DEUDA, 'Id_Deuda (Opcional)', ['id deuda', 'id_deuda', 'id de la deuda']),
    (COL_MONTO_PROPUESTO, 'Monto Propuesto (Opcional)', ['monto propuesto', 'propuesta', 'descuento']),
]

# Función Auxiliar para Leer la Base Subida por el Usuario (xlsx o csv)
def _leer_base_subida(uploaded_file: io.BytesIO) -> pd.DataFrame:
    buffer_bytes = uploaded_file.getvalue()
    ext = uploaded_file.name.split('.')[-1].lower()

    # Caso 1: Excel
    if ext == 'xlsx':
        return pd.read_excel(io.BytesIO(buffer_bytes), dtype=str)

    # Caso 2: CSV (intentamos la lectura y si falla pedimos el separador)
    try:
        return pd.read_csv(io.BytesIO(buffer_bytes), dtype=str)
    except Exception:
        pass
    try:
        return pd.read_csv(io.BytesIO(buffer_bytes), dtype=str, encoding='latin-1')
    except Exception:
        pass

    separador = st.text_input(
        label="**🚧 No se pudo leer el CSV automáticamente. Indica el separador**",
        value=";",
        key="cruce_separador_csv_input",
        help="Escribe el separador usado en el archivo (Ej: ';', '|', '\\t').",
    )
    if separador:
        try:
            sep = '\t' if separador == '\\t' else separador
            return pd.read_csv(io.BytesIO(buffer_bytes), sep=sep, dtype=str)
        except Exception as e:
            st.error("No se pudo leer el CSV con el separador '{}': {}".format(separador, e), icon="❌")
            return pd.DataFrame()
    st.error("No se pudo leer el archivo CSV. Indica el separador para continuar.", icon="🚧")
    return pd.DataFrame()

# Función Auxiliar para Adivinar la Columna que corresponde a un dato del esquema
def _adivinar_columna(columnas: list, candidatos: list) -> str:
    columnas_lower = [str(c).strip().lower() for c in columnas]
    for candidato in candidatos:
        for i, col_lower in enumerate(columnas_lower):
            if candidato in col_lower:
                return columnas[i]
    return 'Sin Columna'

# Función Auxiliar para Limpiar las Keys de los Widgets de Columnas (al subir un archivo nuevo)
def _resetear_widgets_columnas() -> None:
    prefijos = ['cruce_col_', 'cruce_separador_csv_', 'cruce_portafolio_', 'cruce_tipo_cuota_', 'cruce_cuotas_input_', 'cruce_col_cuotas_', 'cruce_fecha_', 'cruce_montos_cuotas_']
    for key in list(st.session_state.keys()):
        if any(key.startswith(p) for p in prefijos): # type: ignore
            del st.session_state[key]

def _mostrar_seleccion_columnas(*,label: str, start_idx: int, end_idx: int, opciones_columnas: list[str], column_mapper: dict[str,str]) -> Optional[str]:
    st.markdown(f"#### **{label}**")
    for (col_std, label, candidatos) in COLUMNAS_MAPEABLES[start_idx:end_idx]:
        adivinada = _adivinar_columna(raw_df.columns.tolist(), candidatos)
        index_default = opciones_columnas.index(adivinada) if adivinada in opciones_columnas else 0
        column_mapper[col_std] = st.selectbox(
            label="**{}**".format(label),
            options=opciones_columnas,
            index=index_default,
            key="cruce_col_{}".format(col_std),
        )


# Función Auxiliar para Mostrar la Configuración del Cruce (Columnas, Modelo y Subida)
def _mostrar_configuracion_cruce(*, uploaded_file, raw_df: pd.DataFrame, ext: str) -> None:
    # --- 2. Selección del Aliado y Alias ---
    st.markdown("### 🥸 Selección del Aliado")
    colAliado, colAlias = st.columns(2)
    with colAliado:
        casa_cobro = st.selectbox(
            label="**🥸 Aliado - Casa de Cobro**",
            options=list(st.session_state["aliados_dict"].keys()),
            key="cruce_casa_cobro_input",
            index=0,
            help="Seleccione el aliado que entregó la base.",
        )
    with colAlias:
        alias = st.text_input(
            label="**🏷️ Alias (Opcional)**",
            key="cruce_alias_input",
            help="Texto pequeño para identificar la base en caso de multiples Contactos (Ej: 'Liquitty Administrada').",
        )
    # Clave base del cruce (relacionada con la Casa de Cobro, el Alias y el Archivo)
    base_key = "{}_{}_{}_{}".format(casa_cobro, alias or 'SIN_ALIAS', uploaded_file.name, uploaded_file.size)

    # --- 3. Selección de Columnas ---
    st.markdown("### 🧩 Selección de Columnas")
    st.info(
        "Selecciona la columna de la base que corresponde a cada dato del esquema.\nSi no existe **Cédula** o **Nombre del Cliente**, no es posible hacer el cruce",
        title="Aviso de Selección de Columnas",
    )
    opciones_columnas = ['Sin Columna'] + list(raw_df.columns)

    # Creamos el Mappeador Guardador de Columnas
    seleccion_cols: dict[str,str] = {}

    # Se crean 3 Columnas: Datos de Cliente, Datos de Deuda, Datos de Montos
    colClienteInfo, colDeudaInfo, colMontoInfo = st.columns(3, border=True)

    with colClienteInfo:
        _mostrar_seleccion_columnas(
            label = "Identificación del Cliente",
            start_idx = 0,
            end_idx = 2,
            opciones_columnas = opciones_columnas,
            column_mapper = seleccion_cols
        )

    with colDeudaInfo:
        _mostrar_seleccion_columnas(
            label = "Identificación de la Deuda",
            start_idx = 2,
            end_idx = 5,
            opciones_columnas = opciones_columnas,
            column_mapper = seleccion_cols
        )

    with colMontoInfo:
        _mostrar_seleccion_columnas(
            label = "Configuración Adicional",
            start_idx = 5,
            end_idx = len(COLUMNAS_MAPEABLES),
            opciones_columnas = opciones_columnas,
            column_mapper = seleccion_cols
        )

    col_cedula = seleccion_cols[COL_CEDULA]
    col_nombre = seleccion_cols[COL_NOMBRE]
    col_banco = seleccion_cols[COL_BANCO]
    col_monto_actual = seleccion_cols[COL_MONTO_ACTUAL]
    col_num_credito = seleccion_cols[COL_CREDITO]
    col_id_deuda = seleccion_cols[COL_ID_DEUDA]
    col_monto_propuesto = seleccion_cols[COL_MONTO_PROPUESTO]

    st.divider()

    # --- 3.1 Característica Especial: Portafolio ---
    st.markdown("### 💼 Manejo de Portafolios")

    portafolio_type = st.radio(
        label = "**Escoger el Modo del Portafolio**",
        options = [
            "Sin Portafolio",
            "Portafolio seleccionado en Columna",
            "Portafolio con Mismo Monto"
        ],
        captions=[
            "**Sin Portafolio**: Manejar los Datos subidos por Deuda",
            "**Seleccionado en Columna**: Una Columna indica si es Portafolio o no",
            "**Mismo Monto**: El Portafolio se detecta con el Mismo Monto",
        ],
        horizontal=True,
    )

    portafolio_type = portafolio_type.replace("*","")

    st.divider()

    # --- 3.2 Característica Especial: Montos a Plazos ---
    st.markdown("### 💸 Montos a Plazos (Opcional)")
    cols_montos_cuotas = st.multiselect(
        label="**💸 Columnas con Montos a Pagar en Cuotas**",
        options=list(raw_df.columns),
        key="cruce_montos_cuotas_cols",
        help="Selecciona una o varias columnas que definan los montos a pagar en cuotas.",
    )
    configs_cuotas = []
    if cols_montos_cuotas:
        for col_monto in cols_montos_cuotas:
            with st.container(border=True):
                tipo_definicion = st.segmented_control(
                    label="**Definición de Cuotas para '{}'**".format(col_monto),
                    options=["Definición por Input", "Definición por Columnas"],
                    default="Definición por Input",
                    key="cruce_tipo_cuota_{}".format(col_monto),
                )
                if tipo_definicion == "Definición por Input":
                    num_cuotas = st.number_input(
                        label="**🔢 Número de Cuotas**",
                        min_value=1,
                        max_value=120,
                        value=2,
                        step=1,
                        key="cruce_cuotas_input_{}".format(col_monto),
                        help="Los pagos a 1 cuota no se guardan (ese sería el Monto Propuesto).",
                    )
                    configs_cuotas.append({'col_monto': col_monto, 'tipo': 'input', 'cuotas': int(num_cuotas), 'col_cuotas': None})
                else:
                    col_cuotas = st.selectbox(
                        label="**📋 Columna con el Número de Cuotas**",
                        options=list(raw_df.columns),
                        key="cruce_col_cuotas_{}".format(col_monto),
                    )
                    configs_cuotas.append({'col_monto': col_monto, 'tipo': 'columnas', 'col_cuotas': col_cuotas})

    st.divider()

    # --- 3.3 Característica Especial: Fecha Límite de Pago ---
    st.markdown("### 📅 Fecha Límite de Pago")
    modo_fecha = st.segmented_control(
        label="**📅 ¿Cómo se define la Fecha Límite de Pago?**",
        options=["Por Columna", "Por Input de Fecha"],
        default="Por Columna",
        key="cruce_fecha_modo",
    )
    serie_fecha = None
    if modo_fecha == "Por Columna":
        col_fecha = st.selectbox(
            label="**📋 Columna de Fecha Límite de Pago**",
            options=list(raw_df.columns),
            key="cruce_fecha_col",
        )
        serie_fecha = pd.to_datetime(raw_df[col_fecha], errors='coerce')
        if serie_fecha.isna().any():
            st.warning(
                "⚠️ Hay **{:,}** valores sin fecha en la columna. Usa el input de fecha para rellenarlos:".format(
                    int(serie_fecha.isna().sum())
                )
            )
            fecha_fallback = st.date_input(
                label="**📅 Fecha de Relleno para los NaN**",
                key="cruce_fecha_fallback_input",
            )
            if fecha_fallback is not None:
                serie_fecha = serie_fecha.fillna(pd.Timestamp(fecha_fallback))
    else:
        fecha_input = st.date_input(
            label="**📅 Fecha Límite de Pago**",
            key="cruce_fecha_input",
        )
        if fecha_input is not None:
            serie_fecha = pd.Series([pd.Timestamp(fecha_input)] * len(raw_df), index=raw_df.index)
        else:
            serie_fecha = pd.Series([pd.NaT] * len(raw_df), index=raw_df.index)

    st.divider()

    # --- 4. Ejecución del Algoritmo de Identificación de Deudas ---
    st.markdown("### 🔎 Ejecución del Algoritmo de Identificación de Deudas")

    # 4.1 Selección de la Base de Cartera / Universo
    colToggleCartera, colInfoCartera = st.columns([1, 2], vertical_alignment="center")
    with colToggleCartera:
        usar_cartera_activa = st.toggle(
            label="**🗂️ Usar Cartera Activa (Sheets)**",
            value=False,
            key="cruce_usar_cartera_activa",
            help="Activado: trae la cartera desde Google Sheets. Desactivado: consulta Metabase (todas las reparadoras).",
        )
    with colInfoCartera:
        with st.spinner("Cargando la Base de Cartera / Universo...",show_time=True):
            if usar_cartera_activa:
                cartera_df = load_cartera_activa()
            else:
                cartera_df = obtener_datos_completos_deudas()
                if len(cartera_df) == 0:
                    st.warning("No se pudo traer la Cartera Activa desde Berex, Cambiando a Sheets...",title="Error de Berex", icon="😣")
                    cartera_df = load_cartera_activa()

            # Dejamos solo las Columnas Necesarias según el esquema InputCruceSchema
            cols_input = [c for c in InputCruceSchema.__fields__.keys() if c in cartera_df.columns]
            cartera_df = cartera_df[cols_input].copy()
            # Aseguramos la Columna Nombre_Cliente (algunas fuentes no la traen)
            if COL_NOMBRE not in cartera_df.columns:
                cartera_df[COL_NOMBRE] = ''
        st.caption("✅ Universo de comparación cargado: **{:,}** deudas".format(len(cartera_df)))

    # 4.2 Ejecución del Modelo de Identificación de Deudas
    key_pkg = "cruce_pkg_{}".format(base_key)
    ejecutar_modelo = st.button(
        label="⚙️ Ejecutar Algoritmo de Identificación de Deudas",
        type="primary",
        key="cruce_ejecutar_modelo",
        width="stretch",
        help="Ejecuta match_deudas para los registros que aún no tienen Id_Deuda.",
    )
    if ejecutar_modelo:
        if col_cedula == 'Sin Columna':
            st.error("Debes seleccionar la columna de **Cédula** para poder ejecutar el cruce.", icon="🚫")
        else:
            with st.spinner("⚙️ Ejecutando el Algoritmo de Identificación de Deudas..."):
                # Paso 1: Construir el DF Estandarizado con el Id_Cruce (UUID por Registro)
                cruce_std = pd.DataFrame()
                cruce_std[COL_ID_CRUCE] = [str(uuid.uuid4()) for _ in range(len(raw_df))]
                for col_std, col_sel in [(COL_CEDULA, col_cedula), (COL_NOMBRE, col_nombre), (COL_BANCO, col_banco), (COL_MONTO_ACTUAL, col_monto_actual), (COL_CREDITO, col_num_credito), (COL_ID_DEUDA, col_id_deuda), (COL_MONTO_PROPUESTO, col_monto_propuesto)]:
                    if col_sel != 'Sin Columna':
                        cruce_std[col_std] = raw_df[col_sel]

                # Paso 2: Serie de Portafolio_Ids (si aplica)
                portafolio_serie = None
                if usar_portafolio:
                    if valores_portafolio:
                        df_portafolio = raw_df.copy()
                        df_portafolio[COL_ID_CRUCE] = cruce_std[COL_ID_CRUCE]
                        if COL_CEDULA in cruce_std.columns:
                            df_portafolio[COL_CEDULA] = cruce_std[COL_CEDULA]
                        if COL_NOMBRE in cruce_std.columns:
                            df_portafolio[COL_NOMBRE] = cruce_std[COL_NOMBRE]
                        portafolio_serie = transform_portafolio(
                            df_portafolio, str(col_portafolio), cols_unir_portafolio, valores_portafolio
                        )
                        # Seguridad: las filas sin grupo (NaN) mantienen su propio Id_Cruce
                        portafolio_serie = portafolio_serie.fillna(cruce_std[COL_ID_CRUCE])
                    else:
                        st.warning("Selecciona los valores que indican Portafolio para poder agruparlos.", icon="⚠️")

                # Paso 3: Pagos a Cuotas por Registro (no se guardan pagos a 1 cuota)
                pagos_cuotas_lista = []
                for i in range(len(raw_df)):
                    pagos_fila = []
                    for cfg in configs_cuotas:
                        monto_cuota = cleanNumber(raw_df[cfg['col_monto']].iloc[i], default_nan=np.nan)
                        if pd.isna(monto_cuota):
                            continue
                        if cfg['tipo'] == 'input':
                            cuotas = cfg['cuotas']
                        else:
                            cuotas = cleanNumber(raw_df[cfg['col_cuotas']].iloc[i], default_nan=np.nan)
                        if pd.isna(cuotas) or int(cuotas) <= 1:
                            continue
                        pagos_fila.append({'Cuotas': int(cuotas), 'Monto': float(monto_cuota), 'En_Portafolio': False})
                    pagos_cuotas_lista.append(pagos_fila)

                # Paso 4: Filtrar solo los Registros sin Id_Deuda (si se seleccionó la columna)
                if col_id_deuda != 'Sin Columna':
                    mask_sin_id = cruce_std[COL_ID_DEUDA].isna() | (cruce_std[COL_ID_DEUDA].astype(str).str.strip() == '')
                else:
                    mask_sin_id = pd.Series([True] * len(cruce_std), index=cruce_std.index)
                match_input = cruce_std[mask_sin_id].copy()

                # Inicializamos el Tiempo de Ejecución
                start_cruce = time()
                # Paso 5: Ejecutar el Modelo de Identificación de Deudas
                resultado = match_deudas(df_buscar=match_input, df_datos=cartera_df, casa_cobro=casa_cobro)
                # Finalizamos el Tiempo de Ejecución
                end_cruce = time()

                # Paso 6: Guardar el Paquete del Cruce en el Session State
                st.session_state[key_pkg] = {
                    'cruce_std': cruce_std,
                    'match_result': resultado,
                    'cartera': cartera_df,
                    'pagos_cuotas_lista': pagos_cuotas_lista,
                    'fecha_limite_serie': serie_fecha,
                    'portafolio_serie': portafolio_serie,
                    'configs_cuotas': configs_cuotas,
                }
                st.toast("✅ Modelo Ejecutado con Éxito", icon="⚙️")

                st.caption("ℹ️ Tiempo Tomado: {:.2f} segundos".format(
                    end_cruce - start_cruce
                ))

    # Vista Previa de los Resultados del Modelo
    if key_pkg in st.session_state:
        pkg = st.session_state[key_pkg]
        resultado_previa = pkg['match_result']
        st.markdown("#### 📊 Resumen del Cruce Ejecutado")
        conteo = resultado_previa['Etiqueta_Registro'].value_counts().to_dict() if not resultado_previa.empty else {}
        cols_resumen = st.columns(len(ETIQUETAS_CRUCE))
        for col_metrica, etiqueta in zip(cols_resumen, ETIQUETAS_CRUCE):
            with col_metrica:
                st.metric(label=etiqueta, value=conteo.get(etiqueta, 0))
        n_pre_identificadas = len(pkg['cruce_std']) - len(resultado_previa)
        if n_pre_identificadas > 0:
            st.caption("ℹ️ {} registro(s) ya traían Id_Deuda en la base y se asumen identificados.".format(n_pre_identificadas))

    # --- 5. Subida de Datos (Drive + Limpieza + Sheets con un solo botón) ---
    st.markdown("### 🚀 Subida de Datos")
    key_sheets_subido = "cruce_sheets_subido_{}".format(base_key)
    if key_pkg not in st.session_state:
        st.info("Primero ejecuta el algoritmo de identificación para habilitar la subida de datos.", icon="ℹ️")
    else:
        subir_datos = st.button(
            label="🚀 Subir Datos a Google Drive y Google Sheets",
            type="primary",
            key="cruce_subir_datos",
            width="stretch",
            disabled=st.session_state.get(key_sheets_subido, False),
            help="Sube la base original a Drive, la limpia, la formatea y la sube a Sheets.",
        )
        if subir_datos:
            pkg = st.session_state[key_pkg]

            # 5.1 Subida de la Base Original a Google Drive (solo una vez)
            key_drive = "cruce_base_drive_subida_{}".format(base_key)
            if not st.session_state.get(key_drive, False):
                with st.spinner("📤 Subiendo la Base a Google Drive..."):
                    nombre_drive = generateFileName(str(casa_cobro), alias) + "." + ext
                    file_id_drive = uploadDBtoDrive(uploaded_file.getvalue(), MIMETYPES[ext], nombre_drive)
                if not file_id_drive:
                    st.error("No se pudo subir la base a Google Drive. Intenta nuevamente.", icon="❌")
                else:
                    st.session_state[key_drive] = True
                    st.toast("✅ Base Subida a Google Drive", icon="📤")

            # 5.2 Limpieza y Formateo según PendienteCruceSchema
            if st.session_state.get(key_drive, False):
                with st.spinner("🧹 Limpiando y Formateando los Datos..."):
                    cruce_limpio = limpiar_base_subida(
                        pkg['cruce_std'],
                        montos_cuotas_cols=[cfg['col_monto'] for cfg in pkg['configs_cuotas']],
                    )
                    try:
                        df_pendiente = build_pendiente_cruce_df(
                            cruce_df=cruce_limpio,
                            match_result=pkg['match_result'],
                            cartera_df=pkg['cartera'],
                            pagos_cuotas_lista=pkg['pagos_cuotas_lista'],
                            fecha_limite_serie=pkg['fecha_limite_serie'],
                            casa_cobro=str(casa_cobro),
                            ejecutivo_subida=st.session_state.get('user_email', 'Sin Correo'),
                            portafolio_serie=pkg['portafolio_serie'],
                            alias_casa=(alias or None),
                            id_deuda_col=(COL_ID_DEUDA if COL_ID_DEUDA in pkg['cruce_std'].columns else None),
                        )
                    except SchemaErrors as e:
                        st.error(
                            "Los datos formateados no cumplen el esquema PendienteCruceSchema. "
                            "Revisa los datos de la base (Ej: Cédulas vacías o inválidas).",
                            icon="❌",
                        )
                        with st.expander("🔍 Detalle del Error de Validación", expanded=False):
                            st.write(str(e)[:3000])
                    else:
                        # 5.3 Subida de la Información a Google Sheets
                        with st.spinner("📤 Subiendo Datos a Google Sheets..."):
                            exito_sheets = upload_base_cruce_info(cruce_df=df_pendiente)
                        if exito_sheets:
                            st.session_state[key_sheets_subido] = True
                            st.toast("✅ Base de Cruce Subida con Éxito", icon="✅")
                            st.success(
                                "✅ Se subieron **{:,}** registros a Google Sheets. "
                                "Ya puedes revisarlos en la pestaña de Escogencia Manual.".format(len(df_pendiente)),
                                icon="🎉",
                            )

        if st.session_state.get(key_sheets_subido, False):
            st.success("✅ Esta base ya fue subida a Google Drive y Google Sheets.", icon="✅")

# --- Página Principal ---
tab_subida, tab_escogencia = st.tabs(
    tabs = ["📤 Subida de Datos", "✍️ Identificación Manual"],
    on_change="rerun"
)

# ==============================
# Tab 1: Subida de Datos
# ==============================
if tab_subida.open:
    with tab_subida:
        st.markdown("### 📥 Introducción de Datos")

        # --- 1. Recepción de la Base ---
        uploaded_file = st.file_uploader(
            label="**📎 Sube la Base del Aliado**",
            type=["xlsx", "csv"],
            accept_multiple_files=False,
            key="cruce_archivo_subida",
            help="Solo se acepta un archivo .xlsx o .csv.",
        )

        if uploaded_file is None:
            st.warning("Esperando la subida de un archivo...", icon="⏳")
        else:
            # Detección de un archivo nuevo para reiniciar los widgets de columnas
            id_archivo = "{}_{}".format(uploaded_file.name, uploaded_file.size)
            if st.session_state.get('cruce_archivo_actual') != id_archivo:
                st.session_state['cruce_archivo_actual'] = id_archivo
                _resetear_widgets_columnas()

            # Lectura de la Base
            raw_df = _leer_base_subida(uploaded_file)
            if raw_df is not None:
                ext = uploaded_file.name.split('.')[-1].lower()
                st.caption("✅ Base leída: **{:,}** registros y **{}** columnas".format(len(raw_df), raw_df.shape[1]))
                with st.expander("🔎 Vista Previa de la Base (Primeros 50 Registros)", expanded=False):
                    st.dataframe(raw_df.head(50), width="stretch")

                # Configuración del Cruce (Columnas, Modelo y Subida de Datos)
                _mostrar_configuracion_cruce(uploaded_file=uploaded_file, raw_df=raw_df, ext=ext)

# ==============================
# Tab 2: Escogencia Manual de Id_Deuda Definitivo
# ==============================
if tab_escogencia.open:
    with tab_escogencia:
        st.markdown("### ✍️ Escogencia Manual del Id_Deuda Definitivo")
        st.info(
            "Aquí puedes revisar los cruces que no fueron exactos y definir manualmente el "
            "Id_Deuda definitivo de cada registro, o marcarlo como Addendum.",
            icon="ℹ️",
        )

        # Carga de las Deudas a Identificar (con Cambios Locales aplicados)
        with st.spinner("⏳ Cargando Deudas a Identificar desde Google Sheets..."):
            cruce_df = load_pendiente_cruce_con_cambios()

        # Sección de Filtros
        cruce_filtrado = mostrar_filtros_cruce(cruce_df=cruce_df)

        st.divider()

        # Sección de Identificación (vista paginada)
        mostrar_deudas_cruce_paginadas(cruce_df=cruce_filtrado, key="cruce_pendientes")

        st.divider()

        # Actualización de la Información
        st.markdown("### 💾 Actualización de Información")
        colActualizar, colReset = st.columns([3, 1], vertical_alignment="center", gap="medium")

        with colActualizar:
            if st.button(
                label="💾 Actualizar Cambios a Google Sheets",
                type="primary",
                key="cruce_actualizar_cambios",
                width="stretch",
                help="Actualiza la Metadata (Id_Definitivo y Última Actualización) de los registros modificados.",
            ):
                cambios = st.session_state.get(LLAVE_CAMBIOS_ID_DEFINITIVO, {})
                if not cambios:
                    st.warning("No hay cambios de Id_Definitivo pendientes por aplicar.", icon="⚠️")
                else:
                    df_actualizar = aplicar_cambios_id_definitivo(cruce_df=cruce_df, cambios=cambios)
                    with st.spinner("📤 Registrando Cambios en Google Sheets..."):
                        exito_upd = upload_base_cruce_info(cruce_df=df_actualizar)
                    if exito_upd:
                        st.session_state[LLAVE_CAMBIOS_ID_DEFINITIVO] = {}
                        st.toast("✅ Cambios Registrados con Éxito", icon="✅")
                        sleep(1)
                        st.rerun()

        with colReset:
            if st.button(
                label="🔄 Reset de Cache",
                key="cruce_reset_cache",
                width="stretch",
                help="Reinicia el cache de carga de las Deudas a Identificar y recarga desde Sheets.",
            ):
                load_pendiente_cruce.clear()
                st.rerun()
