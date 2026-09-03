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
from data.data_loader import load_cartera_activa, load_pendiente_cruce, load_pendiente_cruce_con_cambios, obtener_datos_completos_deudas, verificar_existencias_deudas
from data.data_models import InputCruceSchema, PendienteCruceSchema
from data.data_uploader import upload_base_cruce_info
from modules.constants import COL_BANCO, COL_CEDULA, COL_CREDITO, COL_ID_CRUCE, COL_ID_DEUDA, COL_MONTO_ACTUAL, COL_MONTO_PROPUESTO, COL_NOMBRE, COLUMNAS_MAPEABLES, ETIQUETA_EXACTO, ETIQUETAS_CRUCE, MIMETYPES
from modules.id_aut_deud.deuda_matcher import match_deudas
from modules.id_aut_deud.helpers import (
    aplicar_cambios_id_definitivo, build_pendiente_cruce_df, leer_base_subida, limpiar_base_subida, mostrar_seleccion_columnas, resetear_widgets_columnas,
    generateFileName, uploadDBtoDrive,
)
from ui.cruce_deudas_components import (
    ID_DEFINITIVO_ADDENDUM, LLAVE_CAMBIOS_ID_DEFINITIVO, mostrar_deudas_cruce_paginadas, mostrar_filtros_cruce,
)
from utils.helpers_general import cleanNumber
from utils.helpers_sheets import convert_data_to_string

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

    # Definimos las Columnas del DF
    columnas_df = raw_df.columns.tolist()

    # Se crean 3 Columnas: Datos de Cliente, Datos de Deuda, Datos de Montos
    colClienteInfo, colDeudaInfo, colMontoInfo = st.columns(3, border=True)

    with colClienteInfo:
        mostrar_seleccion_columnas(
            label = "Identificación del Cliente",
            start_idx = 0,
            end_idx = 2,
            opciones_columnas = opciones_columnas,
            column_mapper = seleccion_cols,
            columnas_df = columnas_df,
        )

    with colDeudaInfo:
        mostrar_seleccion_columnas(
            label = "Identificación de la Deuda",
            start_idx = 2,
            end_idx = 5,
            opciones_columnas = opciones_columnas,
            column_mapper = seleccion_cols,
            columnas_df = columnas_df,
        )

    with colMontoInfo:
        mostrar_seleccion_columnas(
            label = "Configuración Adicional",
            start_idx = 5,
            end_idx = len(COLUMNAS_MAPEABLES),
            opciones_columnas = opciones_columnas,
            column_mapper = seleccion_cols,
            columnas_df = columnas_df,
        )

    col_cedula = seleccion_cols[COL_CEDULA]
    col_nombre = seleccion_cols[COL_NOMBRE]
    col_banco = seleccion_cols[COL_BANCO]
    col_monto_actual = seleccion_cols[COL_MONTO_ACTUAL]
    col_num_credito = seleccion_cols[COL_CREDITO]
    col_id_deuda = seleccion_cols[COL_ID_DEUDA]
    col_monto_propuesto = seleccion_cols[COL_MONTO_PROPUESTO]

    # Verificamos que la Columna Cedula o Nombre este presente, de lo contrario paramos
    if col_cedula == 'Sin Columna' and col_nombre == 'Sin Columna':
        st.info("Selecciona las Columnas para continuar con la Subida", icon="ℹ️")
        st.stop()

    st.warning('Asegurate de Seleccionar **TODAS** las Columnas',icon='⚠️')

    st.divider()

    # --- 3.1 Característica Especial: Montos a Plazos ---
    st.markdown("### 💸 Montos a Plazos (Opcional)")
    
    tipo_cuotas = st.radio(
        label="**Tipo de Selección de Cuotas**",
        options = [
            "**Sin Plazos a Cuotas**",
            "**Seleccionar Monto y Poner Cuotas**",
            "**Seleccionar Monto y Cuotas**",
        ],
        captions=[
            "La Casa no acepta solicitudes a coutas",
            "Seleccionas la Columna del Pago y pones el #Cuotas que son",
            "Seleccionas la Columna del Pago y la Columna que indica las cuotas",
        ],
        horizontal = True,
        index = None,
        key = "tipo_cuotas_sel_{}".format(base_key),
    )

    if tipo_cuotas is None:
        st.info("Selecciona si hay Montos Aprobados por Cuotas")
        st.stop()

    tipo_cuotas = tipo_cuotas.replace('*','')

    # Definimos la Selección de las Columnas y sus Cuotas
    cuotas_cols_config = {}
    if tipo_cuotas == 'Seleccionar Monto y Poner Cuotas':
        st.space()
        # Inicalizamos el Conteo de Configuraciones a Cuotas
        key_count_cuotas = 'cuotas_count_{}'.format(base_key)
        if not (key_count_cuotas in st.session_state):
            st.session_state[key_count_cuotas] = 1

        count_cuotas = st.session_state[key_count_cuotas]

        # Creamos 3 Columnas: Identificador, Columna de Cuotas, Selector de Cuotas
        colIdCt, colNCt, colSelectCt = st.columns([1,2,2], border = True)

        for i in range(1,count_cuotas+1):
            with colIdCt:
                st.text_input(
                    label="#Configuración de Cuotas",
                    value = "Cuotas #{}".format(i),
                    key="cuota_show_{}_{}".format(i,base_key),
                    disabled=True
                )

            with colNCt:
                columna_cuota_monto = st.selectbox(
                    label = "**Columna de Monto a Cuotas**",
                    options = columnas_df,
                    index = None,
                    key = "cuota_col_{}_{}".format(i,base_key)
                )

            with colSelectCt:
                num_cuotas_input = st.number_input(
                    label = "**Número de Cuotas**",
                    value = 2,
                    min_value = 2,
                    key = "cuota_size_{}_{}".format(i,base_key)
                )
        
            # Guardamos los Resultados
            if not (columna_cuota_monto is None):
                cuotas_cols_config[columna_cuota_monto] = {
                    'type':'value',
                    'cuotas':num_cuotas_input,
                }

        # Mostramos Botón de Añadir o Quitar Opciones de Columnas
        colQuitCt, colAddCt = st.columns(2)

        with colQuitCt:
            st.button(
                label="**Quitar Opciones a Cuotas**",
                key = "delete_cuota_count_{}".format(base_key),
                on_click= lambda: st.session_state.update({key_count_cuotas:max(st.session_state[key_count_cuotas]-1,1)}),
                width = "stretch",
            )

        with colAddCt:
            st.button(
                label="**Agregar Opciones a Cuotas**",
                key = "add_cuota_count_{}".format(base_key),
                on_click= lambda: st.session_state.update({key_count_cuotas:st.session_state[key_count_cuotas]+1}),
                width = "stretch",
                type="primary",
            )
    elif tipo_cuotas == 'Seleccionar Monto y Cuotas':
        st.space()
        # Mostramos la Selección de Columna de Monto y Columna de Cuotas
        colMCT, colCCT = st.columns(2)
        with colMCT:
            monto_col_cuota = st.selectbox(
                label = "**Columna del Monto de Pago por Cuotas**",
                key="monto_col_cuotas_{}".format(base_key),
                options = columnas_df,
                index=0,
            )
        with colCCT:
            cuotas_col = st.selectbox(
                label = "**Columna de No Cuotas**",
                key="cuotas_col_cuotas_{}".format(base_key),
                options = columnas_df,
                index=0,
            )

        # Verificamos que la Columna de Cuotas no tenga NaNs, de lo contrario mostramos como inputarlo
        if raw_df[cuotas_col].isna().any():
            colWrnCT, colNaNCT = st.columns(2)
            with colWrnCT:
                st.warning("Hay **{} datos sin Cuotas** en la Columna Seleccionada ({})".format(
                    raw_df[cuotas_col].isna().sum(), cuotas_col
                ))
            with colNaNCT:
                nan_cuotas = st.number_input(
                    label = "**Número de Cuotas**",
                    value = 2,
                    min_value = 2,
                    key = "cuota_nan_{}".format(base_key)
                )

        # Añadimos alerta ante no monto presente
        if raw_df[monto_col_cuota].isna().any():
            st.warning("La Cuota Seleccionada de Monto Por Cuotas contiene {} NaNs (no se tendrán en cuenta)".format(
                raw_df[monto_col_cuota].isna().sum()
            ))

        # Guardamos los Resultados
        cuotas_cols_config[monto_col_cuota] = {
            "type":'col',
            "col_cuotas":cuotas_col,
            "cuotas_fallback":nan_cuotas,
        }

    st.divider()

    # --- 3.2 Características Especiales: Fecha Límite de Pago y Máximo Descuento---

    colFechaEsperada, colMaxDisc = st.columns(2, border=True, gap="small")

    with colFechaEsperada:
        st.markdown("### 📅 Fecha Máxima de Pago")
        modo_fecha = st.segmented_control(
            label="**¿Cómo se define la Fecha Máxima de Pago?**",
            options=["Por Columna", "Por Input de Fecha"],
            default="Por Input de Fecha",
            key="cruce_fecha_modo_{}".format(base_key),
        )
        serie_fecha = None
        if modo_fecha == "Por Columna":
            col_fecha = st.selectbox(
                label="**📋 Columna de Fecha Límite de Pago**",
                options=list(raw_df.columns),
                key="cruce_fecha_col_{}".format(base_key),
            )
            serie_fecha = pd.to_datetime(raw_df[col_fecha], errors='coerce')
            if serie_fecha.isna().any():
                st.warning(
                    "⚠️ Hay **{:,}** valores sin fecha en la columna. Usa el input de fecha para rellenarlos:".format(
                        int(serie_fecha.isna().sum())
                    )
                )
                fecha_fallback = st.date_input(
                    label="**📅 Fecha de Relleno para los Datos sin Fecha Máxima de Pago**",
                    key="cruce_fecha_fallback_input_{}".format(base_key),
                )
                if fecha_fallback is not None:
                    serie_fecha = serie_fecha.fillna(pd.Timestamp(fecha_fallback))
        else:
            fecha_input = st.date_input(
                label="**📅 Fecha Límite de Pago**",
                key="cruce_fecha_input_{}".format(base_key),
                value=None,
                min_value="today",
            )
            if fecha_input is not None:
                serie_fecha = pd.Series([pd.Timestamp(fecha_input)] * len(raw_df), index=raw_df.index)
            else:
                serie_fecha = pd.Series([pd.NaT] * len(raw_df), index=raw_df.index)

    with colMaxDisc:
        st.markdown("### **🗒️ Tipo de Descuento Brindado**")

        st.space()

        tipo_descuento = st.radio(
            label = "**Tipo de Descuento**",
            options = [
                "**Descuento Máximo**",
                "**Posibilidad a ContraOfertas**",
            ],
            captions = [
                "No se permite un descuento mayor al de la base",
                "Se permite un descuento mayor con contraoferta y/o bajo comité"
            ],
            horizontal = True,
            index = None,
            key = "tipo_descuento_{}".format(base_key),
        )

    if (serie_fecha.isna().any()) or (tipo_descuento is None):
        st.warning("Selecciona la Fecha Límite de Pago y el Tipo de Descuento para continuar")
        st.stop()
    elif serie_fecha.min() < pd.Timestamp.now('America/Bogota').tz_localize(None).normalize():
        st.warning("Se están subiendo actualizaciones ya vencidas (**Fecha Límite Menor a Hoy**)")

    st.divider()

    # --- 4. Ejecución del Algoritmo de Identificación de Deudas ---
    st.markdown("### 🔎 Ejecución del Algoritmo de Identificación de Deudas")

    # 4.1 Selección de la Base de Cartera / Universo
    colToggleCartera, colInfoCartera = st.columns([1, 2], vertical_alignment="center")
    with colToggleCartera:
        usar_cartera_berex = st.toggle(
            label="**🗂️ Usar Cartera de Berex**",
            value=True,
            key="cruce_usar_cartera_berex",
            help="Activado: trae la cartera desde Google Sheets. Desactivado: consulta Metabase (todas las reparadoras).",
        )
    with colInfoCartera:
        with st.spinner("Cargando la Base de Cartera / Universo...",show_time=True):
            if usar_cartera_berex:
                cartera_df = obtener_datos_completos_deudas()
                if len(cartera_df) == 0:
                    st.warning("No se pudo traer la Cartera Activa desde Berex, Cambiando a Sheets...",title="Error de Berex", icon="😣")
                    cartera_df = load_cartera_activa()
            else:
                cartera_df = load_cartera_activa()

            # Dejamos solo las Columnas Necesarias según el esquema InputCruceSchema
            cols_input = [c for c in InputCruceSchema.empty().columns if c in cartera_df.columns]
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

                # Paso 2: Pagos a Cuotas por Registro (no se guardan pagos a 1 cuota)
                pagos_cuotas_lista = {}
                for i in range(len(raw_df)):
                    pagos_fila = []
                    for col, cfg in cuotas_cols_config.items():
                        monto_cuotas = cleanNumber(raw_df[col].iloc[i],default_nan=np.nan)
                        if pd.isna(monto_cuotas):
                            continue
                        # Verificamos si es por Input o por Valor
                        if cfg['type'] == 'value':
                            pagos_fila.append({'Cuotas': int(cfg['cuotas']), 'Monto': float(monto_cuotas)})
                        elif cfg['type'] == 'col':
                            # Ahora es por doble columna con fallback de cuotas
                            num_cuotas = cleanNumber(raw_df[cfg['col_cuotas']].iloc[i],default_nan=cfg['cuotas_fallback'])
                            pagos_fila.append({'Cuotas': int(num_cuotas), 'Monto': float(monto_cuotas)})

                    pagos_cuotas_lista[cruce_std[COL_ID_CRUCE].iloc[i]] = pagos_fila

                # Paso 3: Filtrar solo los Registros sin Id_Deuda (si se seleccionó la columna)
                if col_id_deuda != 'Sin Columna':
                    mask_sin_id = cruce_std[COL_ID_DEUDA].isna() | (cruce_std[COL_ID_DEUDA].astype(str).str.strip() == '')
                else:
                    mask_sin_id = pd.Series([True] * len(cruce_std), index=cruce_std.index)
                match_input = cruce_std[mask_sin_id].copy()

                # Validamos los DFs
                cartera_df = InputCruceSchema.validate(cartera_df)

                # Inicializamos el Tiempo de Ejecución
                start_cruce = time()
                # Paso 5: Ejecutar el Modelo de Identificación de Deudas
                resultado = match_deudas(df_buscar=match_input, df_datos=cartera_df, casa_cobro=casa_cobro) # type: ignore
                # Finalizamos el Tiempo de Ejecución
                end_cruce = time()

                # Paso 6: Guardar el Paquete del Cruce en el Session State
                st.session_state[key_pkg] = {
                    'cruce_std': cruce_std,
                    'match_result': resultado,
                    'cartera': cartera_df,
                    'pagos_cuotas_lista': pagos_cuotas_lista,
                    'fecha_limite_serie': serie_fecha,
                    'tipo_descuento_base': tipo_descuento,
                    'nombre_archivo': uploaded_file.name or "Sin Nombre",
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
        st.space()
        # Mostramos un Resumen por Etiqueta
        conteo = resultado_previa['Etiqueta_Registro'].value_counts().to_dict() if not resultado_previa.empty else {}
        cols_resumen = st.columns(len(ETIQUETAS_CRUCE), border=True)

        for col_metrica, etiqueta in zip(cols_resumen, ETIQUETAS_CRUCE):
            with col_metrica:
                num_coincidencias = conteo.get(etiqueta, 0)

                st.metric(
                    label="**{}**".format(etiqueta), 
                    value=num_coincidencias,
                    delta = "{:.1%} del Total".format(
                        num_coincidencias / len(resultado_previa)
                    ),
                    delta_color = "green" if (etiqueta == ETIQUETA_EXACTO) else "gray",
                    delta_arrow="off",
                )

        n_pre_identificadas = len(pkg['cruce_std']) - len(resultado_previa)
        if n_pre_identificadas > 0:
            st.caption("ℹ️ {} registro(s) ya traían Id_Deuda en la base y se asumen identificados.".format(n_pre_identificadas))

    st.divider()

    # --- 5. Subida de Datos (Drive + Limpieza + Sheets con un solo botón) ---
    st.markdown("### 🚀 Subida de Datos")
    key_sheets_subido = "cruce_sheets_subido_{}".format(base_key)
    if not (key_pkg in st.session_state):
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
            if not st.session_state.get(key_drive, False) and False:
                with st.spinner("📤 Subiendo la Base a Google Drive..."):
                    nombre_drive = generateFileName(str(casa_cobro), alias) + "." + ext
                    file_id_drive = uploadDBtoDrive(uploaded_file.getvalue(), MIMETYPES[ext], nombre_drive)
                if not file_id_drive:
                    st.error("No se pudo subir la base a Google Drive. Intenta nuevamente.", icon="❌")
                    st.stop()
                else:
                    st.session_state[key_drive] = True
                    st.toast("✅ Base Subida a Google Drive", icon="📤")
            else:
                st.success('Base subida previamente a Drive, No es Necesario Subirla de Nuevo',icon="✅")

            # 5.2 Limpieza y Formateo según PendienteCruceSchema
            if st.session_state.get(key_drive, False) or True:
                with st.spinner("🧹 Limpiando y Formateando los Datos..."):
                    cruce_limpio = limpiar_base_subida(
                        pkg['cruce_std'],
                        montos_cuotas_cols=list(cuotas_cols_config.keys()),
                    )
                    try:
                        df_pendiente = build_pendiente_cruce_df(
                            cruce_df=cruce_limpio,
                            match_result=pkg['match_result'],
                            cartera_df=pkg['cartera'],
                            pagos_cuotas_dict=pkg['pagos_cuotas_lista'],
                            fecha_limite_serie=pkg['fecha_limite_serie'],
                            casa_cobro=str(casa_cobro),
                            ejecutivo_subida=st.session_state.get('user_email', 'Sin Correo'),
                            descuento_maximo = pkg['tipo_descuento_base'] == 'Descuento Máximo',
                            nombre_archivo = pkg['nombre_archivo'],
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
                                "✅ Se subieron **{:,}** registros a Google Sheets. \n"
                                "Ya puedes revisarlos en la pestaña de Escogencia Manual.".format(len(df_pendiente)),
                                icon="🎉",
                            )
                            st.balloons()
                            sleep(1)
                            st.rerun()
                        else:
                            st.error('Error en Subida de Datos (REVISAR)', icon = "❌")
                            st.stop()

        if st.session_state.get(key_sheets_subido, False):
            st.success("Esta base ya fue subida a Google Drive y Google Sheets.", icon="✅")
# --- Página Principal ---
tab_subida, tab_escogencia, tab_control = st.tabs(
    tabs = ["📤 Subida de Datos", "✍️ Identificación Manual", "🟢 Control"],
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
                resetear_widgets_columnas(id_archivo)

            # Lectura de la Base
            raw_df = leer_base_subida(uploaded_file)
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
        st.markdown("### ✍️ Escogencia Manual del Id de Deuda")
        st.info(
            "Aquí puedes revisar los cruces que no fueron exactos y definir manualmente el "
            "Id_Deuda definitivo de cada registro, o marcarlo como Addendum.",
            icon="ℹ️",
        )

        # Carga de las Deudas a Identificar (con Cambios Locales aplicados)
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
                cambios: dict[str, str] = st.session_state.get(LLAVE_CAMBIOS_ID_DEFINITIVO, {})
                if not cambios:
                    st.warning("No hay cambios de Id_Definitivo pendientes por aplicar.", icon="⚠️")
                else:
                    df_actualizar = aplicar_cambios_id_definitivo(cruce_df=cruce_df, cambios=cambios)
                    # Validamos el DF
                    df_actualizar = PendienteCruceSchema.validate(df_actualizar, lazy=True)
                    # Verificamos que las Deudas Existan (Excluyendo ADDENDUMS)
                    deudas_cambios = [d for d in cambios.values() if d != ID_DEFINITIVO_ADDENDUM]
                    with st.spinner("🔍 Validando que los Id_Deuda existan..."):
                        # Obtenemos los Resultados
                        resultados = verificar_existencias_deudas(deudas=deudas_cambios)
                        # Verificamos los Resultados
                        deudas_no_existentes = [d for d, existe in resultados.items() if not existe]
                        if deudas_no_existentes:
                            st.error(
                                "No se puede actualizar la base porque los siguientes Id_Deuda no existen en Berex: {}".format(
                                    ", ".join(deudas_no_existentes)
                                ),
                                icon="❌",
                            )
                            st.stop()
                        else:
                            st.success("✅ Todos los Id_Deuda a actualizar existen en Berex.", icon="✅")
                    with st.spinner("📤 Registrando Cambios en Google Sheets..."):
                        exito_upd = upload_base_cruce_info(cruce_df=df_actualizar)
                    if exito_upd:
                        st.session_state[LLAVE_CAMBIOS_ID_DEFINITIVO] = {}
                        st.toast("Cambios Registrados con Éxito ({} cambios)".format(len(cambios)), icon="✅")
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

if tab_control.open:
    with tab_control:   
        st.info("Sin Implementar")