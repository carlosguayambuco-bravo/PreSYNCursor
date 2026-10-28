# Estándar usando Pep8
# Librerías de Python
import json
from typing import Optional, get_args
# Librerías de Terceros
import numpy as np
import pandas as pd
import streamlit as st
# Librerías Locales
from data.data_loader import load_headcount_negociacion
from modules.classes import get_cruce_identificaciones_manager
from modules.constants import (
    COL_BANCO, COL_CEDULA, COL_CREDITO, COL_MONTO_ACTUAL, COL_NOMBRE,
    ETIQUETA_ADDENDUM, ETIQUETA_AMBIGUO, ETIQUETA_DUPLICADO, ETIQUETA_EXACTO,
    ETIQUETA_NULO, ETIQUETAS_CRUCE, PRIORIDAD_ETIQUETAS_CRUCE, TIPOS_STATUS,
)
from modules.id_aut_deud.helpers import obtener_pago_minimo, obtener_ultimo_status_cruce, search_data_deudas
from utils.helpers_general import formatNaN, replaceNaN

LLAVE_CAMBIOS_ID_DEFINITIVO = 'cambios_id_definitivo'
LLAVE_IDS_NO_VALIDADOS = 'cruce_ids_deuda_no_validados'
LLAVE_FILTRO_NO_VALIDADOS = 'filtro_cruce_solo_no_validados_input'
OPCION_SIN_OPCIONES = 'Sin Opciones Actuales'
ID_DEFINITIVO_ADDENDUM = 'ADDENDUM'

# Opciones de Ordenamiento de las Deudas a Identificar
OPCION_ORDEN_DF = 'Orden del DataFrame (Actual)'
OPCION_ORDEN_CEDULA = 'Cédula'
OPCION_ORDEN_NOMBRE = 'Nombre del Cliente'
OPCION_ORDEN_ETIQUETA = 'Etiqueta'

# Función Auxiliar para Obtener el Id_Definitivo Actual de un Registro (Cambio Pendiente o Metadata)
def _id_definitivo_actual(*, fila: pd.Series, cambios: dict) -> str:
    id_cruce = str(fila.get('Id_Cruce') or '')
    if id_cruce in cambios:
        return str(cambios[id_cruce])
    mtdt = fila.get('Metadata') or {}
    return str(mtdt.get('Id_Definitivo') or '')

# Función Auxiliar para Mostrar los Filtros de las Deudas a Identificar
def mostrar_filtros_cruce(*, cruce_df: pd.DataFrame) -> pd.DataFrame:
    # Si no hay Deudas a Identificar, no hacemos nada
    if cruce_df.empty:
        st.warning("No hay Deudas a Identificar para mostrar. Sube una base en la pestaña de Subida de Datos.", icon="⚠️")
        return cruce_df

    # Paso 1: Extraemos las Columnas de Filtro desde la Metadata
    df = cruce_df.copy()
    df['_Casa_Cobro'] = df['Metadata'].apply(lambda m: str(m.get('Casa_Cobro', '') or ''))
    df['_Alias_Casa'] = df['Metadata'].apply(lambda m: str(m.get('Alias_Casa', '') or ''))
    df['_Ejecutivo_Subida'] = df['Metadata'].apply(lambda m: str(m.get('Ejecutivo_Subida', '') or ''))
    df['_Etiqueta'] = df['Metadata'].apply(lambda m: str(m.get('Etiqueta', '') or ''))
    df['_Tiene_Id_Definitivo'] = df['Metadata'].apply(lambda m: (m.get('Id_Definitivo') not in (None, '')))
    df['_Archivo_Origen'] = df['Metadata'].apply(lambda m: str(m.get('Archivo_Origen', '') or ''))

    # Ids_Deuda No Validados (Post-Revisión): Set guardado al Actualizar la Información
    ids_no_validados = st.session_state.get(LLAVE_IDS_NO_VALIDADOS, set())
    hay_no_validados = len(ids_no_validados) > 0

    # Paso 2: Mostrar los Filtros (Casa de Cobro, Alias, Ejecutivo de Subida y Etiqueta)
    colCasa, colAlias, colEjecutivo, colEtiqueta = st.columns(4)

    with colCasa:
        casa_seleccionada = st.multiselect(
            label="**🥸 Casa de Cobro**",
            options=sorted(df['_Casa_Cobro'].unique().tolist()),
            key="filtro_cruce_casa_cobro_input",
            help="Seleccione las casas de cobro que desea ver.",
        )

    hay_aliases = (df['_Alias_Casa'] != '').any()
    with colAlias:
        if hay_aliases:
            alias_seleccionado = st.multiselect(
                label="**🏷️ Alias**",
                options=sorted(df.loc[df['_Alias_Casa'] != '', '_Alias_Casa'].unique().tolist()),
                key="filtro_cruce_alias_input",
                help="Seleccione los alias que desea ver.",
            )
        else:
            alias_seleccionado = []
            st.caption("Sin Alias disponibles")

    with colEjecutivo:
        ejecutivo_seleccionado = st.multiselect(
            label="**🧑‍💼 Ejecutivo de Subida**",
            options=sorted(df['_Ejecutivo_Subida'].unique().tolist()),
            key="filtro_cruce_ejecutivo_input",
            help="Seleccione los ejecutivos que subieron los datos.",
        )

    with colEtiqueta:
        etiqueta_seleccionada = st.multiselect(
            label="**🏷️ Etiqueta de la Deuda**",
            options=sorted(df['_Etiqueta'].unique().tolist()),
            key="filtro_cruce_etiqueta_input",
            help="Seleccione las etiquetas que desea ver.",
        )

    # Filtro de Post-Revisión: Solo Ids_Deuda No Validados (solo se muestra si hay Ids Erróneos)
    filtrar_no_validados = False
    if hay_no_validados:
        colNoValidados, colInfoNoValidados = st.columns([1, 3], vertical_alignment="center")
        with colNoValidados:
            filtrar_no_validados = st.toggle(
                label="**🚨 Solo Ids_Deuda No Validados**",
                key=LLAVE_FILTRO_NO_VALIDADOS,
                help="Muestra únicamente los registros cuyo Id_Deuda no existe en Berex, para su post-revisión.",
            )
        with colInfoNoValidados:
            st.caption(
                "Filtro de Post-Revisión: **{:,}** Id_Deuda sin validar en Berex.".format(len(ids_no_validados))
            )

    # Paso 3: Aplicar los Filtros Principales Seleccionados
    if casa_seleccionada:
        df = df[df['_Casa_Cobro'].isin(casa_seleccionada)]

    if alias_seleccionado:
        df = df[df['_Alias_Casa'].isin(alias_seleccionado)]

    if ejecutivo_seleccionado:
        df = df[df['_Ejecutivo_Subida'].isin(ejecutivo_seleccionado)]

    if etiqueta_seleccionada:
        df = df[df['_Etiqueta'].isin(etiqueta_seleccionada)]

    # Paso 3.1: Aplicar el Filtro de Post-Revisión (Solo Ids_Deuda No Validados)
    if filtrar_no_validados and not df.empty:
        cambios = st.session_state.get(LLAVE_CAMBIOS_ID_DEFINITIVO, {})
        ids_definitivos = df.apply(
            lambda fila: _id_definitivo_actual(fila=fila, cambios=cambios), axis=1
        )
        df = df[ids_definitivos.isin(ids_no_validados)]

    # Paso 4: Ayudas Auxiliares (Toggle de Id_Definitivo, Ordenamiento y Archivo de Origen)
    with st.expander("Ayudas Auxiliares", expanded=False):
        colToggle, colOrdenamiento, colArchivo = st.columns(3, vertical_alignment="center")

        with colToggle:
            incluir_con_definitivo = st.toggle(
                label="**✅ Incluir Deudas con Id_Definitivo**",
                value=False,
                key="filtro_cruce_incluir_definitivo_input",
                help="Activar para incluir también las deudas que ya tienen un Id_Definitivo asignado.",
            )
            st.caption("Por defecto los cruces exactos **NO se incluyen** para identificar")

        with colOrdenamiento:
            # El Ordenamiento por Cédula o Nombre solo tiene sentido si hay más de un valor distinto
            opciones_ordenamiento = [OPCION_ORDEN_DF]
            if df[COL_CEDULA].nunique() > 1:
                opciones_ordenamiento.append(OPCION_ORDEN_CEDULA)
            if df[COL_NOMBRE].nunique() > 1:
                opciones_ordenamiento.append(OPCION_ORDEN_NOMBRE)
            opciones_ordenamiento.append(OPCION_ORDEN_ETIQUETA)

            # Si la opción guardada ya no existe entre las disponibles, volvemos al orden del DF
            valor_orden_actual = st.session_state.get('filtro_cruce_ordenamiento_input', OPCION_ORDEN_DF)
            index_ordenamiento = (
                opciones_ordenamiento.index(valor_orden_actual)
                if valor_orden_actual in opciones_ordenamiento else 0
            )

            ordenamiento = st.selectbox(
                label="**Ordenamiento de los Datos**",
                options=opciones_ordenamiento,
                index=index_ordenamiento,
                key="filtro_cruce_ordenamiento_input",
                help="Selecciona el criterio con el que se ordenarán las deudas.",
            )

        with colArchivo:
            archivo_seleccionado = st.multiselect(
                label="**Archivo de Origen**",
                options=sorted(df['_Archivo_Origen'].unique().tolist()),
                key="filtro_cruce_archivo_origen_input",
                help="Seleccione los archivos de origen que desea ver.",
            )

    # Paso 5: Aplicar los Filtros Auxiliares Seleccionados
    # (el Filtro de No Validados debe incluir registros con Id_Definitivo para poder Corregirlos)
    if not incluir_con_definitivo and not filtrar_no_validados:
        df = df[~df['_Tiene_Id_Definitivo']]

    if archivo_seleccionado:
        df = df[df['_Archivo_Origen'].isin(archivo_seleccionado)]

    # Paso 6: Aplicar el Ordenamiento Seleccionado
    if ordenamiento == OPCION_ORDEN_CEDULA:
        df = df.sort_values(by=COL_CEDULA, kind='stable')
    elif ordenamiento == OPCION_ORDEN_NOMBRE:
        df = df.sort_values(by=COL_NOMBRE, kind='stable', na_position='last')
    elif ordenamiento == OPCION_ORDEN_ETIQUETA:
        df['_Prioridad_Etiqueta'] = df['_Etiqueta'].map(PRIORIDAD_ETIQUETAS_CRUCE)
        df = df.sort_values(by='_Prioridad_Etiqueta', kind='stable', na_position='last')

    # Paso 7: Devolver el DataFrame Filtrado y Ordenado (sin las Columnas Auxiliares)
    columnas_auxiliares = [
        '_Casa_Cobro', '_Alias_Casa', '_Ejecutivo_Subida', '_Etiqueta',
        '_Tiene_Id_Definitivo', '_Archivo_Origen', '_Prioridad_Etiqueta',
    ]
    return df.drop(columns=[c for c in columnas_auxiliares if c in df.columns])

# Función Auxiliar para Mostrar la Advertencia del Filtro de Ids_Deuda No Validados
def mostrar_advertencia_ids_no_validados() -> None:
    # Si no hay Ids_Deuda No Validados, no se muestra nada
    ids_no_validados = st.session_state.get(LLAVE_IDS_NO_VALIDADOS, set())
    if not ids_no_validados:
        return

    # Resumimos la Lista de Ids para la Advertencia
    ids_texto = ", ".join(sorted(str(i) for i in ids_no_validados))
    if len(ids_texto) > 300:
        ids_texto = "{}...".format(ids_texto[:300])

    if st.session_state.get(LLAVE_FILTRO_NO_VALIDADOS, False):
        st.warning(
            "**Filtro activo: Solo Ids_Deuda No Validados.** Se muestran únicamente los registros cuyo "
            "Id_Deuda no existe en Berex. Corrige el Id_Deuda y vuelve a actualizar: los Ids válidos "
            "sí se guardarán.\n\n**Ids_Deuda No Validados ({:,})**: {}".format(
                len(ids_no_validados), ids_texto
            ),
            icon="🚨",
        )
    else:
        st.warning(
            "Hay **{:,}** Id_Deuda que no existen en Berex y quedaron pendientes de corrección. "
            "Activa el filtro **Solo Ids_Deuda No Validados** en la sección de filtros para su "
            "post-revisión.\n\n**Ids_Deuda No Validados ({:,})**: {}".format(
                len(ids_no_validados), len(ids_no_validados), ids_texto
            ),
            icon="⚠️",
        )

# Función Auxiliar para estilizar el DF de las Deudas Posibles
def estilizar_deudas(deudas_df: pd.DataFrame, id_definitivo: Optional[str] = None):
    deudas_df = deudas_df[
        ['Banco', 'Numero_Credito', 'Monto_Actual', 'Id_Deuda']
        + (['Es_Liquidada'] if 'Es_Liquidada' in deudas_df.columns else [])
    ]

    # 1. Crear el objeto Styler base
    styler = deudas_df.style

    # 2. Mostrar Numero_Credito sin notación científica
    styler = styler.format({
        'Numero_Credito': lambda v: f'{v:.0f}' if (pd.notna(v) and isinstance(v, (int, float))) else (v if pd.notna(v) else ''),
    })

    # 3. Aplicar color de fondo por fila si existe la columna Es_Liquidada
    if 'Es_Liquidada' in deudas_df.columns:
        styler = styler.apply(
            lambda r: [
                'background-color: {}'.format(
                    "#ce1424" if r['Es_Liquidada'] else "#009723"
                )
            ] * len(r),
            axis=1
        ).hide(subset=['Es_Liquidada'], axis='columns')

    # 4. Resaltar el Id_Definitivo Escogido (o todos los Id_Deuda si no se indica)
    if id_definitivo and (str(id_definitivo) != ETIQUETA_ADDENDUM):
        styler = styler.map(
            lambda v: (
                'font-weight: bold; text-decoration: underline;'
                if str(v) == str(id_definitivo)
                else ''
            ),
            subset=['Id_Deuda']
        )
    else:
        styler = styler.map(
            lambda v: 'font-weight: bold;',
            subset=['Id_Deuda']
        )

    # 5. Aplicar negrita a los encabezados
    styler = styler.set_table_styles([
        {'selector': 'th', 'props': [('font-weight', 'bold')]}
    ])

    return styler

# Función Auxiliar para Formatear la Fecha de Identificación del Cache (Hora Local Bogotá)
def _formatear_fecha_identificacion(timestamp) -> str:
    try:
        fecha = pd.to_datetime(float(timestamp), unit='s', utc=True).tz_convert('America/Bogota')
    except (TypeError, ValueError):
        return 'N/A'
    if pd.isna(fecha):
        return 'N/A'
    return fecha.strftime('%Y-%m-%d %X')

# Función Auxiliar para Mostrar un Registro del Cruce (Vista de 2 Columnas)
def mostrar_registro_cruce(*, registro: pd.Series) -> None:
    # Paso 1: Extraemos la Metadata y el Id_Cruce del Registro
    mtdt = dict(registro['Metadata'])
    id_cruce = str(registro['Id_Cruce'])
    id_definitivo_previo = str(mtdt.get('Id_Definitivo') or '')

    # Paso 2: Inicializamos el Diccionario de Cambios en el Session State
    st.session_state.setdefault(LLAVE_CAMBIOS_ID_DEFINITIVO, {})
    cambios = st.session_state[LLAVE_CAMBIOS_ID_DEFINITIVO]

    # Paso 3: Datos del Usuario y Gestor Compartido de Identificaciones
    gestor_identificaciones = get_cruce_identificaciones_manager()
    usuario_actual = st.session_state.get('user_email', 'N/A')
    nombre_usuario = getattr(st.session_state.get('user_obj'), 'name', '') or ''
    nombre_usuario = nombre_usuario.split()[0].upper() if nombre_usuario.split() else 'N/A'

    # Columna Izquierda (70%): Información de las Posibles Deudas
    # Columna Derecha (30%): Input del Id_Deuda Definitivo
    colData, colDeudas, colSeleccion = st.columns([1,2,1], vertical_alignment="center", gap="small")

    with colData:
        # Acá mostramos: Casa de Cobro, Alias, Cedula
        # Creamos el String que va a ser el Guia
        strGuia = "> **Cedula**: {}".format(replaceNaN(value=registro['Cedula'], nan_replace="Sin Cédula Proporcionada"))
        strGuia += "\n\n> **Número de Crédito**: {}".format(replaceNaN(value=registro['Numero_Credito'], nan_replace="Sin Num. Cred. Proporcionado"))
        strGuia += "\n\n> **Banco**: {}".format(replaceNaN(value=registro['Banco'], nan_replace="Sin Banco Proporcionado"))
        strGuia += "\n\n> **Monto Actual**: $ {}".format(formatNaN(value=registro['Monto_Actual'], nan_replace="Sin Monto Actual Brindado.", format_str="{:,.0f}"))
        pago_minimo = obtener_pago_minimo(mtdt)
        monto_pago_minimo = (pago_minimo or {}).get('Monto', np.nan)
        strGuia += "\n\n> **Pago Mínimo**: $ {}".format(formatNaN(value=monto_pago_minimo, nan_replace="Sin Pago Propuesto", format_str="{:,.0f}"))
        st.markdown(strGuia)

    with colDeudas:
        # Mostramos la Etiqueta y el Id_Definitivo Actual (si existe) del Registro
        strInfo = "**Etiqueta**: {} | **ID_Actual**: {}".format(
            replaceNaN(value=mtdt.get('Etiqueta'), nan_replace="Sin Etiqueta Proporcionada"),
            replaceNaN(value=mtdt.get('Id_Definitivo'), nan_replace="Sin ID Definitivo Proporcionado")
        )
        st.caption(strInfo, text_alignment="center")

        key_deudas = 'cruce_deudas_posibles_{}'.format(registro['Cedula'])
        if not st.session_state.get(key_deudas, pd.DataFrame()).empty:
            dfDeudas = st.session_state[key_deudas]
        elif registro['Metadata']['Deudas_Posibles']:
            # Creamos el DF
            dfDeudas = pd.DataFrame(registro['Metadata']['Deudas_Posibles'])
        else:
            dfDeudas = pd.DataFrame()

        if dfDeudas.empty:
            st.error("Deudas no Encontradas al Ejecutar el Algoritmo de Cruce", icon="❌",title="Sin Deudas")
        else:
            with st.expander("**👁️ Ver Deudas Posibles**", expanded=(registro['Metadata']['Etiqueta'] == ETIQUETA_EXACTO)):
                # Formateamos el DF para que se vea la fila en rojo si esta liquidada
                st.dataframe(
                    data=estilizar_deudas(dfDeudas), 
                    width="stretch", 
                    hide_index=True, 
                    column_order=['Banco','Numero_Credito','Monto_Actual','Id_Deuda'],
                    column_config={'Monto_Actual':st.column_config.NumberColumn("Monto_Actual", format="localized")}
                )

        # Agregamos Botón de Actualización de Datos
        if registro['Cedula'] and (registro['Cedula'] not in ['', None]):
            st.button(
                label="**Buscar Deudas Activas**",
                icon="🔎",
                on_click=search_data_deudas,
                kwargs= {'cedula': registro['Cedula']},
                type="primary",
                width="stretch",
                key="cruce_boton_busqueda_deudas_{}".format(registro["Id_Cruce"]),
                disabled=not (st.session_state.get(key_deudas,None) is None)
            )

        st.caption("**Id del Cruce**: {}".format(
            registro["Id_Cruce"]
        ))

    with colSeleccion:
        # El valor previo define si el toggle arranca marcado como Addendum
        valor_previo = cambios.get(id_cruce, mtdt.get('Id_Definitivo'))
        es_addendum = (valor_previo == ID_DEFINITIVO_ADDENDUM)

        # Vamos a Mostrar 2 cosas: Motivos del Cruce y Resultado
        strResultado = "> **Motivos del Cruce**: {}".format(
            ("-".join(mtdt.get('Motivos_Cruce') or []) or "Sin Cruce")
        )
        strResultado += "\n\n>**RESULTADO DEL CRUCE: {}**".format(
            mtdt.get('Etiqueta') or "NO CRUZADO"
        )

        marcar_addendum = st.toggle(
            label="**ℹ️ Marcar como Addendum**",
            value=es_addendum,
            key="cruce_addendum_toggle_{}".format(id_cruce),
            help="Al activarlo, el Id_Definitivo será ADDENDUM y no se podrá escoger un Id_Deuda.",
        )

        if marcar_addendum:
            # Si está activo, el Id_Definitivo será ADDENDUM
            if id_definitivo_previo != ID_DEFINITIVO_ADDENDUM:
                cambios[id_cruce] = ID_DEFINITIVO_ADDENDUM
                gestor_identificaciones.registrar(
                    id_cruce=id_cruce,
                    correo=usuario_actual,
                    nombre=nombre_usuario,
                )
            else:
                # Limpiamos un Cambio No-Op que haya quedado de una Versión Anterior
                cambios.pop(id_cruce, None)
            st.selectbox(
                label="**🆔 Id_Deuda Definitivo**",
                options=[ID_DEFINITIVO_ADDENDUM],
                index=0,
                disabled=True,
                key="cruce_id_def_addendum_{}".format(id_cruce),
            )
        else:
            valor_actual = cambios.get(id_cruce, mtdt.get('Id_Definitivo'))
            # Si el toggle se acaba de quitar, no dejamos el ADDENDUM pendiente
            if valor_actual == ID_DEFINITIVO_ADDENDUM:
                if cambios.get(id_cruce) == ID_DEFINITIVO_ADDENDUM:
                    cambios.pop(id_cruce, None)
                valor_actual = mtdt.get('Id_Definitivo')
            # De lo Contrario definimos las opciones posibles
            # Caso A: No se han buscado las deudas de la Cédula
            if st.session_state.get(key_deudas,None) is None:
                deudas_posibles = mtdt.get('Deudas_Posibles') or []
                opciones = [str(d.get('Id_Deuda', '') or '') for d in deudas_posibles if d.get('Id_Deuda') not in (None, '')]
            # Caso B: Ya se buscaron las Deudas
            else:
                opciones = dfDeudas['Id_Deuda'].tolist()

            if not opciones:
                opciones = [OPCION_SIN_OPCIONES]

            # Aseguramos que el valor actual esté entre las opciones (por defecto)
            if (valor_actual not in (None, '')) and (valor_actual != ID_DEFINITIVO_ADDENDUM) and (str(valor_actual) not in opciones):
                opciones = [str(valor_actual)] + opciones

            index_valor = opciones.index(str(valor_actual)) if ((valor_actual not in (None, '')) and (str(valor_actual) in opciones)) else None
            seleccion = st.selectbox(
                label="**🆔 Id_Deuda Definitivo**",
                options=opciones,
                index=index_valor,
                accept_new_options=True,
                key="cruce_id_def_select_{}".format(id_cruce),
                help="Escoge el Id_Deuda definitivo entre las Deudas Posibles o escribe uno nuevo.",
            )
            # Guardamos la selección en el diccionario del Session State
            # (ignorando el estado del propio input para que no se borre al cambiar de página)
            if seleccion and seleccion != OPCION_SIN_OPCIONES:
                if str(seleccion) != id_definitivo_previo:
                    cambios[id_cruce] = seleccion
                    gestor_identificaciones.registrar(
                        id_cruce=id_cruce,
                        correo=usuario_actual,
                        nombre=nombre_usuario,
                    )
                else:
                    # Limpiamos un Cambio No-Op que haya quedado de una Versión Anterior
                    cambios.pop(id_cruce, None)

        # Aviso de Identificación Compartida: se muestra al final de la Columna de Selección
        identificacion = gestor_identificaciones.obtener(id_cruce)
        if identificacion:
            st.success(
                "La Deuda ya fue identificada por **{}**".format(
                    identificacion.get('nombre') or 'N/A'
                ),
                title="Deuda ya identificada",
                icon="✅",
            )
            st.caption(
                "**Fecha de Identificación**: {}".format(
                    _formatear_fecha_identificacion(identificacion.get('fecha_identificacion'))
                )
            )

# Función Auxiliar para Mostrar las Deudas a Identificar de forma Paginada
def mostrar_deudas_cruce_paginadas(*, cruce_df: pd.DataFrame, key: str) -> None:
    """Muestra las Deudas a Identificar en sub-páginas manejadas de forma local.

    Divide el DataFrame en páginas según la cantidad de registros por página
    seleccionada (10-20-30-40) y renderiza cada registro de la página actual
    con la función mostrar_registro_cruce. El estado de la paginación se guarda
    en el Session State de forma local, aislado con la `key` indicada.
    """
    # --- Estado Local de la Paginación (aislado por `key`) ---
    key_registros_por_pagina = "paginacion_deudas_registros_por_pagina_{}".format(key)
    key_pagina_actual = "paginacion_deudas_pagina_actual_{}".format(key)

    st.session_state.setdefault(key_registros_por_pagina, 10)
    st.session_state.setdefault(key_pagina_actual, 1)

    total_deudas = len(cruce_df)
    if total_deudas == 0:
        st.caption("**Mostrando 0 de 0 Deudas.** (**0.0%**)")
        return

    registros_por_pagina = st.session_state[key_registros_por_pagina]
    total_paginas = max(1, np.ceil(total_deudas / registros_por_pagina))
    pagina_actual = min(st.session_state[key_pagina_actual], total_paginas)
    st.session_state[key_pagina_actual] = pagina_actual

    # Rebanada del DataFrame correspondiente a la página actual
    inicio = int((pagina_actual - 1) * registros_por_pagina)
    fin = int(min(inicio + registros_por_pagina, total_deudas))
    pagina_df = cruce_df.iloc[inicio:fin]

    # Paso 1: Mostrar los Registros de la Página Actual
    for _, registro in pagina_df.iterrows():
        mostrar_registro_cruce(registro=registro)
        st.divider()

    # Paso 2: Caption con los Registros Mostrados y su Porcentaje
    st.caption(
        "**Mostrando {}-{} de {} Deudas.** (**{:.1%}**, **{}** páginas en total)".format(
            inicio + 1,
            fin,
            total_deudas,
            len(pagina_df) / total_deudas,
            total_paginas
        )
    )

    # Paso 3: Aplicar la Navegación Seleccionada
    if total_paginas > 1:
        if st.session_state.get("paginacion_deudas_ir_inicio_{}".format(key)):
            st.session_state[key_pagina_actual] = 1
            st.rerun()
        elif st.session_state.get("paginacion_deudas_anterior_{}".format(key)):
            st.session_state[key_pagina_actual] = max(1, pagina_actual - 1)
            st.rerun()
        elif st.session_state.get("paginacion_deudas_siguiente_{}".format(key)):
            st.session_state[key_pagina_actual] = min(total_paginas, pagina_actual + 1)
            st.rerun()
        elif st.session_state.get("paginacion_deudas_ir_final_{}".format(key)):
            st.session_state[key_pagina_actual] = total_paginas
            st.rerun()

    # Paso 4: Controles de Paginación (Izquierda: Registros por Página)
    colRegistros, colEspacio, colSelectPag, colNavegacion = st.columns([2, 1, 1, 2], vertical_alignment="center", gap="large")

    with colRegistros:
        def reiniciar_pagina_actual() -> None:
            st.session_state[key_pagina_actual] = 1

        st.selectbox(
            "**Registros por página**",
            options=[10, 20, 30, 40],
            key=key_registros_por_pagina,
            on_change=reiniciar_pagina_actual,
            help="Selecciona cuántas deudas quieres ver por página.",
            disabled=(total_deudas <= 10),
        )

    with colSelectPag:
        st.number_input(
            label="Página Actual",
            value=1,
            key=key_pagina_actual,
            min_value=1,
            max_value=int(total_paginas),
            disabled=total_paginas <= 1,
            help="La página actual en la que te encuentras"
        )

    # Paso 5: Controles de Paginación (Derecha: Máximo 5 Botones de Navegación)
    with colNavegacion:
        st.space("xxsmall")

        if total_paginas > 1:
            colInicio, colAnterior, colActual, colSiguiente, colFinal = st.columns(
                5, vertical_alignment="center", gap="small"
            )

            with colInicio:
                st.button(
                    "<<",
                    key="paginacion_deudas_ir_inicio_{}".format(key),
                    disabled=(pagina_actual == 1),
                    help="Ir a la primera página de deudas.",
                    width="stretch",
                )
            with colAnterior:
                st.button(
                    str(max(1, pagina_actual - 1)) if pagina_actual - 1 > 0 else "N/A",
                    key="paginacion_deudas_anterior_{}".format(key),
                    disabled=(pagina_actual == 1),
                    help="Ir a la página anterior de deudas.",
                    width="stretch",
                )
            with colActual:
                st.button(
                    str(pagina_actual),
                    key="paginacion_deudas_actual_{}".format(key),
                    type="primary",
                    help="Página actual de deudas.",
                    width="stretch",
                    on_click=None,
                )
            with colSiguiente:
                st.button(
                    str(min(total_paginas, pagina_actual + 1)),
                    key="paginacion_deudas_siguiente_{}".format(key),
                    disabled=(pagina_actual >= total_paginas),
                    help="Ir a la página siguiente de deudas.",
                    width="stretch",
                )
            with colFinal:
                st.button(
                    ">>",
                    key="paginacion_deudas_ir_final_{}".format(key),
                    disabled=(pagina_actual >= total_paginas),
                    help="Ir a la última página de deudas.",
                    width="stretch",
                )
        else:
            # Una sola página: solo se muestra el indicador de la página actual
            st.button(
                str(pagina_actual),
                key="paginacion_deudas_actual_{}".format(key),
                disabled=True,
                type="primary",
                help="Página actual de deudas.",
                width="stretch",
            )

# =============================================================================
# Detalles de Cruce (Auditoría de Registros)
# =============================================================================

# Opciones de Ordenamiento de los Detalles del Cruce
OPCION_DETALLE_ORDEN_ORIGINAL = 'Orden original (Id_Registro)'
OPCION_DETALLE_ORDEN_ETIQUETA = 'Etiqueta (prioridad de negocio)'
OPCION_DETALLE_ORDEN_FECHA_INICIAL = 'Fecha de cruce inicial'
OPCION_DETALLE_ORDEN_FECHA_RECONOCIDO = 'Fecha de reconocimiento'
OPCION_DETALLE_ORDEN_FECHA_SUBIDO = 'Fecha de subida a Base del Mes'
OPCION_DETALLE_ORDEN_ULTIMA_ACTUALIZACION = 'Última actualización'
OPCION_DETALLE_ORDEN_CEDULA = 'Cédula'
OPCION_DETALLE_ORDEN_NOMBRE = 'Nombre del Cliente'
OPCION_DETALLE_ORDEN_DF = 'Orden actual del DataFrame'

# Opciones de Dirección del Ordenamiento
OPCION_DETALLE_DIRECCION_ASC = '↑ Ascendente'
OPCION_DETALLE_DIRECCION_DESC = '↓ Descendente'

# Opciones del Filtro de Id_Definitivo
OPCION_DETALLE_ID_TODOS = 'Todos'
OPCION_DETALLE_ID_CON = 'Con Id_Definitivo'
OPCION_DETALLE_ID_SIN = 'Sin Id_Definitivo'
OPCION_DETALLE_ID_ADDENDUM = 'Solo ADDENDUM'

# Opciones del Filtro de Fecha
OPCION_DETALLE_FECHA_INICIAL = 'Fecha de cruce inicial (Sin Reconocer)'
OPCION_DETALLE_FECHA_RECONOCIDO = 'Fecha de reconocimiento (Reconocido)'
OPCION_DETALLE_FECHA_SUBIDO = 'Fecha de subida (Subido Alianzas)'
OPCION_DETALLE_FECHA_ULTIMA = 'Última actualización'

MAPA_CAMPOS_FECHA_DETALLE = {
    OPCION_DETALLE_FECHA_INICIAL: '_Fecha_Sin_Reconocer',
    OPCION_DETALLE_FECHA_RECONOCIDO: '_Fecha_Reconocido',
    OPCION_DETALLE_FECHA_SUBIDO: '_Fecha_Subido_Alianzas',
    OPCION_DETALLE_FECHA_ULTIMA: '_Ultima_Fecha',
}

# Claves de los Widgets de Filtros (para poder Limpiarlos)
LLAVES_FILTROS_DETALLES = [
    'detalles_cruce_busqueda_input',
    'detalles_cruce_casa_input',
    'detalles_cruce_alias_input',
    'detalles_cruce_archivo_input',
    'detalles_cruce_etiqueta_input',
    'detalles_cruce_estado_input',
    'detalles_cruce_identificado_input',
    'detalles_cruce_ejecutivo_input',
    'detalles_cruce_tipo_id_input',
    'detalles_cruce_contraoferta_input',
    'detalles_cruce_solo_observaciones_input',
    'detalles_cruce_campo_fecha_input',
    'detalles_cruce_rango_fecha_input',
]

LLAVE_MAPA_NOMBRES_DETALLES = 'detalles_cruce_mapa_nombres'

# Función Auxiliar para Convertir un Valor a Texto de Búsqueda
def _texto_busqueda(valor) -> str:
    if valor is None:
        return ''
    try:
        if pd.isna(valor):
            return ''
    except (TypeError, ValueError):
        pass
    return str(valor).strip()

# Función Auxiliar para Limpiar un Id que pudo Quedar como Float
def _texto_id(valor) -> str:
    texto = _texto_busqueda(valor)
    if texto.endswith('.0'):
        texto = texto[:-2]
    return texto

# Función Auxiliar para Obtener la Metadata de un Registro como Diccionario
def _obtener_metadata_detalle(registro: pd.Series) -> dict:
    mtdt = registro.get('Metadata')
    if isinstance(mtdt, dict):
        return mtdt
    if isinstance(mtdt, str) and mtdt.strip():
        try:
            metadata = json.loads(mtdt)
        except (json.JSONDecodeError, TypeError):
            return {}
        return metadata if isinstance(metadata, dict) else {}
    return {}

# Función Auxiliar para Parsear una Fecha de Auditoría (Hora Local Bogotá)
def _parsear_fecha_detalle(valor) -> Optional[pd.Timestamp]:
    if valor is None:
        return None
    if isinstance(valor, str) and valor.strip().lower() in ('', 'nan', 'nat', 'none'):
        return None
    fecha = pd.to_datetime(valor, errors='coerce')
    if pd.isna(fecha):
        return None
    fecha = pd.Timestamp(fecha)
    if fecha.tzinfo is not None:
        fecha = fecha.tz_convert('America/Bogota').tz_localize(None)
    return fecha

# Función Auxiliar para Obtener las Fechas de los Estados del Cruce
def _fechas_status_detalle(mtdt: dict) -> dict[str, Optional[pd.Timestamp]]:
    statuses = list(get_args(TIPOS_STATUS))
    crudo = mtdt.get('Ultima_Actualizacion')

    # Compatibilidad con Metadata Serializada como Texto
    if isinstance(crudo, str) and crudo.strip().startswith('{'):
        try:
            crudo = json.loads(crudo)
        except json.JSONDecodeError:
            crudo = None

    # Copiamos el Diccionario para no Mutar la Metadata Original
    crudo = dict(crudo) if isinstance(crudo, dict) else {}

    # Compatibilidad con el Esquema Anterior
    status_legado = mtdt.get('Cruce_Status')
    if status_legado in statuses:
        fecha_legado = _parsear_fecha_detalle(mtdt.get('Fecha_Identificacion'))
        if fecha_legado is not None:
            crudo.setdefault(status_legado, fecha_legado)

    return {
        status: _parsear_fecha_detalle(crudo.get(status))
        for status in statuses
    }

# Función Auxiliar para Obtener la Fecha Más Reciente de un Registro
def _ultima_fecha_detalle(fechas: dict[str, Optional[pd.Timestamp]]) -> Optional[pd.Timestamp]:
    validas = [fecha for fecha in fechas.values() if fecha is not None]
    return max(validas) if validas else None

# Función Auxiliar para Convertir una Fecha en Texto (Hora Local Bogotá)
def _formatear_fecha_detalle(fecha) -> str:
    if fecha is None:
        return 'No registrada'
    if pd.isna(fecha):
        return 'No registrada'
    return pd.Timestamp(fecha).strftime('%Y-%m-%d %H:%M')

# Función Auxiliar para Convertir una Fecha en Texto Corto (Solo Día)
def _formatear_fecha_corta_detalle(fecha) -> str:
    if fecha is None:
        return 'No registrada'
    if pd.isna(fecha):
        return 'No registrada'
    return pd.Timestamp(fecha).strftime('%Y-%m-%d')

# Función Auxiliar para Formatear una Duración entre Dos Fechas
def _formatear_duracion_detalle(desde, hasta) -> str:
    if (desde is None) or (hasta is None):
        return '—'
    if pd.isna(desde) or pd.isna(hasta):
        return '—'
    delta = pd.Timestamp(hasta) - pd.Timestamp(desde)
    if delta.total_seconds() < 0:
        return 'Fechas invertidas'
    dias = delta.days
    horas, resto = divmod(delta.seconds, 3600)
    minutos = resto // 60
    if dias > 0:
        return '{}d {}h'.format(dias, horas)
    if horas > 0:
        return '{}h {}m'.format(horas, minutos)
    return '{}m'.format(minutos)

# Función Auxiliar para Normalizar el Valor de un Responsable
def _categoria_responsable_detalle(valor) -> str:
    texto = _texto_busqueda(valor)
    if texto.lower() in ('', 'n/a', 'nan', 'none', 'sin correo'):
        return 'No registrado'
    if texto.lower() in ('automatico', 'automático'):
        return 'Automatico'
    return texto

# Función Auxiliar para Mostrar un Responsable con Nombre y Correo
def _nombre_responsable_detalle(valor, mapa_nombres: dict[str, str]) -> str:
    texto = _texto_busqueda(valor)
    if texto.lower() in ('', 'n/a', 'nan', 'none', 'sin correo'):
        return 'No registrado'
    if texto.lower() in ('automatico', 'automático'):
        return 'Automático'
    nombre = mapa_nombres.get(texto.lower())
    if nombre:
        return '{} ({})'.format(nombre, texto)
    return texto

# Función Auxiliar para Obtener el Tipo de Identificación de un Registro
def _tipo_identificacion_detalle(*, identificado_por, motivos: list[str]) -> str:
    texto = _texto_busqueda(identificado_por)
    if texto.lower() in ('automatico', 'automático'):
        if any('id_deuda input' in str(motivo).lower() for motivo in motivos):
            return 'Automático (Id_Deuda de la base)'
        return 'Automático (cruce exacto)'
    if texto.lower() in ('', 'n/a', 'nan', 'none', 'sin correo'):
        return 'Sin identificar'
    return 'Manual'

# Función Auxiliar para Detectar Observaciones de Auditoría en un Registro
def _observaciones_auditoria_detalle(
        *,
        mtdt: dict,
        fechas: dict[str, Optional[pd.Timestamp]],
        etiqueta: str,
        id_definitivo: str,
        identificado_por: str,
    ) -> list[str]:
    observaciones = []
    fecha_inicial = fechas.get('Sin Reconocer')
    fecha_reconocido = fechas.get('Reconocido')
    fecha_subido = fechas.get('Subido Alianzas')
    id_def = _texto_id(id_definitivo)
    identificado = _texto_busqueda(identificado_por).lower()

    if fecha_inicial is None:
        observaciones.append('Sin fecha de cruce inicial (Sin Reconocer).')
    if (fecha_inicial is not None) and (fecha_reconocido is not None) and (fecha_inicial > fecha_reconocido):
        observaciones.append('La fecha de cruce inicial es posterior a la fecha de reconocimiento.')
    if (fecha_reconocido is not None) and (identificado in ('', 'n/a', 'nan', 'none', 'sin correo')):
        observaciones.append('Reconocido sin responsable registrado (Identificado_Por).')
    if (fecha_subido is not None) and (not id_def):
        observaciones.append('Subido Alianzas sin Id_Definitivo.')
    if id_def and (fecha_reconocido is None):
        observaciones.append('Id_Definitivo asignado sin fecha de reconocimiento.')
    if (fecha_reconocido is not None) and (fecha_subido is not None) and (fecha_reconocido > fecha_subido):
        observaciones.append('Reconocimiento posterior a la subida a la Base del Mes (re-identificación).')
    if (etiqueta == ETIQUETA_EXACTO) and (not id_def):
        observaciones.append('Etiqueta EXACTO sin Id_Definitivo.')
    if id_def and (id_def != ETIQUETA_ADDENDUM):
        deudas_posibles = [
            _texto_id(deuda.get('Id_Deuda'))
            for deuda in (mtdt.get('Deudas_Posibles') or [])
            if isinstance(deuda, dict)
        ]
        if deudas_posibles and (id_def not in deudas_posibles):
            observaciones.append('Id_Definitivo fuera de las Deudas_Posibles (posible búsqueda manual).')
    return observaciones

# Función Auxiliar para Construir las Columnas Internas de Detalles y Auditoría
def _construir_df_detalles(*, cruce_df: pd.DataFrame, mapa_nombres: dict[str, str]) -> pd.DataFrame:
    # Quitamos Columnas Internas de una Construcción Anterior
    columnas_internas = [columna for columna in cruce_df.columns if str(columna).startswith('_')]
    df_base = cruce_df.drop(columns=columnas_internas).copy()

    filas = []
    for _, registro in df_base.iterrows():
        mtdt = _obtener_metadata_detalle(registro)
        fechas = _fechas_status_detalle(mtdt)
        etiqueta = str(mtdt.get('Etiqueta') or '').strip()
        id_definitivo = _texto_id(mtdt.get('Id_Definitivo'))
        identificado_por = _texto_busqueda(mtdt.get('Identificado_Por'))
        ejecutivo_subida = _texto_busqueda(mtdt.get('Ejecutivo_Subida'))
        id_registro = mtdt.get('Id_Registro')
        id_registro_num = pd.to_numeric(id_registro, errors='coerce')
        if pd.isna(id_registro_num) or (float(id_registro_num) <= 0):
            id_registro_num = np.nan

        motivos = mtdt.get('Motivos_Cruce') or []
        if isinstance(motivos, str):
            motivos = [motivo.strip() for motivo in motivos.split('|') if motivo.strip()]
        else:
            motivos = [str(motivo) for motivo in motivos if str(motivo).strip()]

        deudas_posibles = [
            deuda for deuda in (mtdt.get('Deudas_Posibles') or [])
            if isinstance(deuda, dict)
        ]
        pagos_cuotas = [
            pago for pago in (mtdt.get('Pagos_Cuotas') or [])
            if isinstance(pago, dict)
        ]

        tipo_identificacion = _tipo_identificacion_detalle(
            identificado_por=identificado_por,
            motivos=motivos,
        )
        observaciones = _observaciones_auditoria_detalle(
            mtdt=mtdt,
            fechas=fechas,
            etiqueta=etiqueta,
            id_definitivo=id_definitivo,
            identificado_por=identificado_por,
        )
        fecha_limite = _parsear_fecha_detalle(mtdt.get('Fecha_Limite_Pago'))
        monto_actual_original = pd.to_numeric(mtdt.get('Monto_Actual_Original'), errors='coerce')
        fecha_inicial = fechas.get('Sin Reconocer')
        fecha_reconocido = fechas.get('Reconocido')
        fecha_subido = fechas.get('Subido Alianzas')
        ultima_fecha = _ultima_fecha_detalle(fechas)

        texto_deudas = ' '.join(
            '{} {} {}'.format(
                _texto_id(deuda.get('Id_Deuda')),
                _texto_busqueda(deuda.get('Banco')),
                _texto_busqueda(deuda.get('Numero_Credito')),
            )
            for deuda in deudas_posibles
        )
        texto_busqueda = ' '.join([
            _texto_busqueda(registro.get(COL_CEDULA)),
            _texto_busqueda(registro.get(COL_NOMBRE)),
            _texto_busqueda(registro.get('Id_Cruce')),
            _texto_busqueda(registro.get(COL_CREDITO)),
            _texto_busqueda(id_definitivo),
            _texto_busqueda(registro.get(COL_BANCO)),
            _texto_busqueda(mtdt.get('Archivo_Origen')),
            _texto_busqueda(mtdt.get('Casa_Cobro')),
            _texto_busqueda(mtdt.get('Alias_Casa')),
            _texto_busqueda(identificado_por),
            _nombre_responsable_detalle(identificado_por, mapa_nombres),
            _texto_busqueda(ejecutivo_subida),
            _nombre_responsable_detalle(ejecutivo_subida, mapa_nombres),
            _texto_busqueda(etiqueta),
            _texto_busqueda(mtdt.get('Tipo_Contraoferta')),
            _texto_busqueda(tipo_identificacion),
            texto_deudas,
        ]).lower()

        filas.append({
            '_Casa_Cobro': _texto_busqueda(mtdt.get('Casa_Cobro')),
            '_Alias_Casa': _texto_busqueda(mtdt.get('Alias_Casa')),
            '_Archivo_Origen': _texto_busqueda(mtdt.get('Archivo_Origen')),
            '_Ejecutivo_Subida': ejecutivo_subida,
            '_Ejecutivo_Subida_Categoria': _categoria_responsable_detalle(ejecutivo_subida),
            '_Etiqueta': etiqueta,
            '_Prioridad_Etiqueta': PRIORIDAD_ETIQUETAS_CRUCE.get(etiqueta, 99),
            '_Id_Definitivo': id_definitivo,
            '_Tiene_Id_Definitivo': bool(id_definitivo),
            '_Es_Addendum': (id_definitivo == ETIQUETA_ADDENDUM),
            '_Identificado_Por': identificado_por,
            '_Identificado_Por_Categoria': _categoria_responsable_detalle(identificado_por),
            '_Tipo_Identificacion': tipo_identificacion,
            '_Id_Registro': _texto_busqueda(id_registro),
            '_Id_Registro_Num': id_registro_num,
            '_Fecha_Sin_Reconocer': fecha_inicial if fecha_inicial is not None else pd.NaT,
            '_Fecha_Reconocido': fecha_reconocido if fecha_reconocido is not None else pd.NaT,
            '_Fecha_Subido_Alianzas': fecha_subido if fecha_subido is not None else pd.NaT,
            '_Ultima_Fecha': ultima_fecha if ultima_fecha is not None else pd.NaT,
            '_Fecha_Limite_Pago': fecha_limite if fecha_limite is not None else pd.NaT,
            '_Estado': obtener_ultimo_status_cruce(mtdt),
            '_Motivos_Cruce': motivos,
            '_Deudas_Posibles': deudas_posibles,
            '_Pagos_Cuotas': pagos_cuotas,
            '_Tipo_Contraoferta': _texto_busqueda(mtdt.get('Tipo_Contraoferta')),
            '_Portafolio_Ids': _texto_busqueda(mtdt.get('Portafolio_Ids')),
            '_Monto_Actual_Original': monto_actual_original,
            '_Observaciones': observaciones,
            '_N_Observaciones': len(observaciones),
            '_Busqueda': texto_busqueda,
        })

    if not filas:
        return df_base

    df_detalles = pd.DataFrame(filas, index=df_base.index)

    # Aseguramos los Tipos de las Columnas de Fechas y Números
    for columna in [
        '_Fecha_Sin_Reconocer', '_Fecha_Reconocido', '_Fecha_Subido_Alianzas',
        '_Ultima_Fecha', '_Fecha_Limite_Pago',
    ]:
        df_detalles[columna] = pd.to_datetime(df_detalles[columna], errors='coerce')
    df_detalles['_Id_Registro_Num'] = pd.to_numeric(df_detalles['_Id_Registro_Num'], errors='coerce')
    df_detalles['_Monto_Actual_Original'] = pd.to_numeric(df_detalles['_Monto_Actual_Original'], errors='coerce')

    return pd.concat([df_base, df_detalles], axis=1)

# Función Auxiliar para Cargar el Mapa de Correos a Nombres desde el HeadCount
def _cargar_mapa_nombres_detalle() -> dict[str, str]:
    try:
        headcount_df = load_headcount_negociacion()
    except Exception:
        return {}
    if (headcount_df is None) or headcount_df.empty:
        return {}
    mapa = {}
    for _, fila in headcount_df.iterrows():
        correo = _texto_busqueda(fila.get('Correo')).lower()
        nombre = _texto_busqueda(fila.get('Nombre'))
        if correo and nombre and (correo not in mapa):
            mapa[correo] = nombre
    return mapa

# Función Auxiliar para Obtener el Mapa de Nombres (Cacheado en la Sesión)
def _obtener_mapa_nombres_detalle() -> dict[str, str]:
    mapa = st.session_state.get(LLAVE_MAPA_NOMBRES_DETALLES)
    if isinstance(mapa, dict) and mapa:
        return mapa
    mapa = _cargar_mapa_nombres_detalle()
    if mapa:
        st.session_state[LLAVE_MAPA_NOMBRES_DETALLES] = mapa
    return mapa

# Función Auxiliar para Formatear un Texto Opcional en los Filtros
def _formatear_texto_opcional_detalle(valor, etiqueta_vacio: str) -> str:
    return valor if _texto_busqueda(valor) else etiqueta_vacio

# Función Auxiliar para Formatear un Responsable en los Filtros
def _formatear_responsable_filtro_detalle(valor, mapa_nombres: dict[str, str]) -> str:
    categoria = _categoria_responsable_detalle(valor)
    if categoria == 'No registrado':
        return 'No registrado'
    if categoria == 'Automatico':
        return 'Automático'
    return _nombre_responsable_detalle(categoria, mapa_nombres)

# Función Auxiliar para Formatear el Tipo de Contraoferta
def _formatear_contraoferta_detalle(valor) -> str:
    return valor if _texto_busqueda(valor) else 'No registrada'

# Función Auxiliar para Limpiar los Filtros de Detalles
def _limpiar_filtros_detalles() -> None:
    for llave in LLAVES_FILTROS_DETALLES:
        st.session_state.pop(llave, None)

# Función Auxiliar para Formatear un Monto
def _formatear_monto_detalle(valor) -> str:
    numero = pd.to_numeric(valor, errors='coerce')
    return formatNaN(value=numero, nan_replace='No registrado', format_str="${:,.0f}")

# Función Auxiliar para Formatear un Id_Definitivo
def _formatear_id_detalle(valor) -> str:
    texto = _texto_id(valor)
    return texto if texto else 'Sin asignar'

# Función Auxiliar para Obtener el Color de una Etiqueta
def _color_etiqueta_detalle(etiqueta: str) -> str:
    return {
        ETIQUETA_EXACTO: 'green',
        ETIQUETA_DUPLICADO: 'orange',
        ETIQUETA_AMBIGUO: 'yellow',
        ETIQUETA_ADDENDUM: 'violet',
        ETIQUETA_NULO: 'red',
    }.get(etiqueta, 'gray')

# Función Auxiliar para Obtener el Color de un Estado
def _color_estado_detalle(estado: str) -> str:
    return {
        'Sin Reconocer': 'gray',
        'Reconocido': 'blue',
        'Subido Alianzas': 'green',
    }.get(estado, 'gray')

# Función Auxiliar para Crear un Badge Markdown
def _badge_detalle(*, texto: str, color: str) -> str:
    texto = _texto_busqueda(texto) or 'SIN INFORMACIÓN'
    return ":{}-badge[{}]".format(color, texto)

# Función para Mostrar los Filtros y el Ordenamiento de los Detalles del Cruce
def mostrar_filtros_detalles_cruce(*, cruce_df: pd.DataFrame) -> pd.DataFrame:
    # Si no hay Registros, no se Muestra Nada
    if cruce_df.empty:
        st.warning(
            "No hay registros de cruce para mostrar. Sube una base en la pestaña de Subida de Datos.",
            icon="⚠️",
        )
        return cruce_df

    # Paso 1: Cargar los Nombres y Construir las Columnas Internas
    mapa_nombres = _obtener_mapa_nombres_detalle()
    df = _construir_df_detalles(cruce_df=cruce_df, mapa_nombres=mapa_nombres)

    # Paso 2: Valores Únicos para los Filtros (calculados sobre TODOS los registros)
    opciones_casa = sorted(df['_Casa_Cobro'].unique().tolist())
    hay_aliases = bool((df['_Alias_Casa'] != '').any())
    opciones_alias = sorted(df.loc[df['_Alias_Casa'] != '', '_Alias_Casa'].unique().tolist()) if hay_aliases else []
    opciones_archivo = sorted(df['_Archivo_Origen'].unique().tolist())
    valores_etiqueta = set(df['_Etiqueta'].unique().tolist())
    opciones_etiqueta = [etiqueta for etiqueta in ETIQUETAS_CRUCE if etiqueta in valores_etiqueta]
    opciones_etiqueta += sorted(valores_etiqueta - set(ETIQUETAS_CRUCE))
    statuses = list(get_args(TIPOS_STATUS))
    valores_estado = set(df['_Estado'].unique().tolist())
    opciones_estado = [status for status in statuses if status in valores_estado]
    opciones_estado += sorted(valores_estado - set(statuses))
    opciones_identificado = sorted(
        df['_Identificado_Por_Categoria'].unique().tolist(),
        key=lambda valor: (_formatear_responsable_filtro_detalle(valor, mapa_nombres).lower(), valor),
    )
    opciones_ejecutivo = sorted(
        df['_Ejecutivo_Subida_Categoria'].unique().tolist(),
        key=lambda valor: (_formatear_responsable_filtro_detalle(valor, mapa_nombres).lower(), valor),
    )
    opciones_contraoferta = sorted(
        df['_Tipo_Contraoferta'].unique().tolist(),
        key=lambda valor: _formatear_contraoferta_detalle(valor).lower(),
    )

    # Paso 3: Filtros Principales
    with st.container(border=True):
        st.markdown("#### 🔎 Filtros de Auditoría")

        colBusqueda, colCasa, colAlias, colArchivo = st.columns([2, 1, 1, 1])
        with colBusqueda:
            busqueda = st.text_input(
                label="**🔤 Búsqueda**",
                placeholder="Cédula, nombre, Id_Cruce, crédito, Id_Deuda...",
                key="detalles_cruce_busqueda_input",
                help="Busca en cédula, nombre, Id_Cruce, número de crédito, banco, Id_Definitivo, deudas posibles, archivo y responsables.",
            )
        with colCasa:
            casa_seleccionada = st.multiselect(
                label="**🥸 Casa de Cobro**",
                options=opciones_casa,
                format_func=lambda valor: _formatear_texto_opcional_detalle(valor, 'Sin casa de cobro'),
                key="detalles_cruce_casa_input",
                help="Selecciona las casas de cobro que deseas ver.",
            )
        with colAlias:
            if hay_aliases:
                alias_seleccionado = st.multiselect(
                    label="**🏷️ Alias**",
                    options=opciones_alias,
                    key="detalles_cruce_alias_input",
                    help="Selecciona los alias que deseas ver.",
                )
            else:
                alias_seleccionado = []
                st.caption("Sin alias disponibles")
        with colArchivo:
            archivo_seleccionado = st.multiselect(
                label="**📂 Archivo de Origen**",
                options=opciones_archivo,
                format_func=lambda valor: _formatear_texto_opcional_detalle(valor, 'Sin archivo'),
                key="detalles_cruce_archivo_input",
                help="Selecciona los archivos que deseas ver.",
            )

        colEtiqueta, colEstado, colIdentificado, colEjecutivo = st.columns(4)
        with colEtiqueta:
            etiqueta_seleccionada = st.multiselect(
                label="**🏷️ Etiqueta**",
                options=opciones_etiqueta,
                format_func=lambda valor: valor if valor else 'Sin etiqueta',
                key="detalles_cruce_etiqueta_input",
                help="Etiquetas del resultado del cruce.",
            )
        with colEstado:
            estado_seleccionado = st.multiselect(
                label="**🚦 Estado Actual**",
                options=opciones_estado,
                format_func=lambda valor: valor if valor else 'Sin estado',
                key="detalles_cruce_estado_input",
                help="Último estado registrado del cruce (por fecha).",
            )
        with colIdentificado:
            identificado_seleccionado = st.multiselect(
                label="**🧑‍💼 Identificado Por**",
                options=opciones_identificado,
                format_func=lambda valor: _formatear_responsable_filtro_detalle(valor, mapa_nombres),
                key="detalles_cruce_identificado_input",
                help="Responsable de la identificación: manual, automática o sin registrar.",
            )
        with colEjecutivo:
            ejecutivo_seleccionado = st.multiselect(
                label="**📤 Ejecutivo de Subida**",
                options=opciones_ejecutivo,
                format_func=lambda valor: _formatear_responsable_filtro_detalle(valor, mapa_nombres),
                key="detalles_cruce_ejecutivo_input",
                help="Persona que subió la base del aliado.",
            )

        colTipoId, colContraoferta, colObservaciones, colLimpiar = st.columns(
            [1.2, 1.2, 1.4, 1], vertical_alignment="bottom"
        )
        with colTipoId:
            tipo_id = st.selectbox(
                label="**🆔 Id_Definitivo**",
                options=[
                    OPCION_DETALLE_ID_TODOS,
                    OPCION_DETALLE_ID_CON,
                    OPCION_DETALLE_ID_SIN,
                    OPCION_DETALLE_ID_ADDENDUM,
                ],
                key="detalles_cruce_tipo_id_input",
                help="Filtra por la presencia del Id_Definitivo o por los ADDENDUM.",
            )
        with colContraoferta:
            if opciones_contraoferta:
                contraoferta_seleccionada = st.multiselect(
                    label="**💸 Tipo de Contraoferta**",
                    options=opciones_contraoferta,
                    format_func=_formatear_contraoferta_detalle,
                    key="detalles_cruce_contraoferta_input",
                    help="Tipo de contraoferta registrado en el cruce.",
                )
            else:
                contraoferta_seleccionada = []
                st.caption("Sin tipos de contraoferta")
        with colObservaciones:
            solo_observaciones = st.toggle(
                label="**🚨 Solo con observaciones**",
                key="detalles_cruce_solo_observaciones_input",
                help="Muestra únicamente los registros con posibles inconsistencias de auditoría.",
            )
        with colLimpiar:
            st.button(
                label="**🧹 Limpiar Filtros**",
                key="detalles_cruce_limpiar_filtros",
                on_click=_limpiar_filtros_detalles,
                width="stretch",
            )

        # Paso 4: Filtro de Fechas (por defecto la Fecha de Cruce Inicial)
        st.markdown("##### 📅 Filtro por Fechas de Auditoría")
        colCampoFecha, colRangoFecha = st.columns([1, 2])
        with colCampoFecha:
            campo_fecha = st.selectbox(
                label="**Campo de Fecha**",
                options=list(MAPA_CAMPOS_FECHA_DETALLE.keys()),
                key="detalles_cruce_campo_fecha_input",
                help="Fecha de cruce inicial, reconocimiento, subida o última actualización.",
            )
        with colRangoFecha:
            rango_fecha = st.date_input(
                label="**Rango de Fechas**",
                value=(),
                format="DD/MM/YYYY",
                key="detalles_cruce_rango_fecha_input",
                help="Selecciona la fecha inicial y final del rango. Si lo dejas vacío, no se filtra por fecha.",
            )
        st.caption(
            "La **fecha de cruce inicial** (`Sin Reconocer`) es la fecha en que se cargó el registro. "
            "Úsala para identificar qué se priorizó primero y qué al final."
        )

    # Paso 5: Aplicar los Filtros Seleccionados
    if busqueda and busqueda.strip():
        df = df[df['_Busqueda'].str.contains(busqueda.strip(), case=False, na=False, regex=False)]

    if casa_seleccionada:
        df = df[df['_Casa_Cobro'].isin(casa_seleccionada)]
    if alias_seleccionado:
        df = df[df['_Alias_Casa'].isin(alias_seleccionado)]
    if archivo_seleccionado:
        df = df[df['_Archivo_Origen'].isin(archivo_seleccionado)]
    if etiqueta_seleccionada:
        df = df[df['_Etiqueta'].isin(etiqueta_seleccionada)]
    if estado_seleccionado:
        df = df[df['_Estado'].isin(estado_seleccionado)]
    if identificado_seleccionado:
        df = df[df['_Identificado_Por_Categoria'].isin(identificado_seleccionado)]
    if ejecutivo_seleccionado:
        df = df[df['_Ejecutivo_Subida_Categoria'].isin(ejecutivo_seleccionado)]
    if contraoferta_seleccionada:
        df = df[df['_Tipo_Contraoferta'].isin(contraoferta_seleccionada)]

    if tipo_id == OPCION_DETALLE_ID_CON:
        df = df[df['_Tiene_Id_Definitivo']]
    elif tipo_id == OPCION_DETALLE_ID_SIN:
        df = df[~df['_Tiene_Id_Definitivo']]
    elif tipo_id == OPCION_DETALLE_ID_ADDENDUM:
        df = df[df['_Es_Addendum']]

    if solo_observaciones:
        df = df[df['_N_Observaciones'] > 0]

    # Aplicar el Rango de Fechas
    inicio_fecha = None
    fin_fecha = None
    if isinstance(rango_fecha, (tuple, list)):
        if len(rango_fecha) == 1:
            inicio_fecha = fin_fecha = rango_fecha[0]
        elif len(rango_fecha) >= 2:
            inicio_fecha = rango_fecha[0]
            fin_fecha = rango_fecha[1]
    elif rango_fecha:
        inicio_fecha = fin_fecha = rango_fecha

    if (inicio_fecha is not None) and (fin_fecha is not None):
        if inicio_fecha > fin_fecha:
            inicio_fecha, fin_fecha = fin_fecha, inicio_fecha
        columna_fecha = MAPA_CAMPOS_FECHA_DETALLE.get(campo_fecha, '_Fecha_Sin_Reconocer')
        serie_fecha = pd.to_datetime(df[columna_fecha], errors='coerce')
        mask_fecha = (serie_fecha.dt.date >= inicio_fecha) & (serie_fecha.dt.date <= fin_fecha)
        df = df[mask_fecha]

    # Paso 6: Ordenamiento
    st.markdown("#### ↕️ Ordenamiento")
    colOrden, colDireccion, colInfoOrden = st.columns([2, 1.2, 2], vertical_alignment="center")
    with colOrden:
        orden = st.selectbox(
            label="**Ordenar Por**",
            options=[
                OPCION_DETALLE_ORDEN_ORIGINAL,
                OPCION_DETALLE_ORDEN_ETIQUETA,
                OPCION_DETALLE_ORDEN_FECHA_INICIAL,
                OPCION_DETALLE_ORDEN_FECHA_RECONOCIDO,
                OPCION_DETALLE_ORDEN_FECHA_SUBIDO,
                OPCION_DETALLE_ORDEN_ULTIMA_ACTUALIZACION,
                OPCION_DETALLE_ORDEN_CEDULA,
                OPCION_DETALLE_ORDEN_NOMBRE,
                OPCION_DETALLE_ORDEN_DF,
            ],
            key="detalles_cruce_orden_input",
            help="Criterio de ordenamiento de los registros.",
        )
    with colDireccion:
        direccion = st.segmented_control(
            label="**Dirección**",
            options=[OPCION_DETALLE_DIRECCION_ASC, OPCION_DETALLE_DIRECCION_DESC],
            default=OPCION_DETALLE_DIRECCION_DESC,
            key="detalles_cruce_direccion_input",
            help="Ascendente o descendente según el criterio seleccionado.",
        ) or OPCION_DETALLE_DIRECCION_DESC
    with colInfoOrden:
        if orden == OPCION_DETALLE_ORDEN_ORIGINAL:
            st.caption("Ascendente: fila 1 → N · Descendente: fila N → 1. El número de fila se reinicia por archivo.")
        elif orden == OPCION_DETALLE_ORDEN_ETIQUETA:
            st.caption("Ascendente: EXACTO → NULO · Descendente: NULO → EXACTO.")
        elif orden == OPCION_DETALLE_ORDEN_FECHA_INICIAL:
            st.caption("Ascendente: cruce más antiguo primero · Descendente: cruce más reciente primero.")
        elif orden == OPCION_DETALLE_ORDEN_FECHA_RECONOCIDO:
            st.caption("Ascendente: reconocimiento más antiguo primero · Descendente: más reciente primero.")
        elif orden == OPCION_DETALLE_ORDEN_FECHA_SUBIDO:
            st.caption("Ascendente: subida más antigua primero · Descendente: subida más reciente primero.")
        elif orden == OPCION_DETALLE_ORDEN_ULTIMA_ACTUALIZACION:
            st.caption("Ascendente: última actualización más antigua · Descendente: más reciente.")
        elif orden == OPCION_DETALLE_ORDEN_CEDULA:
            st.caption("Ascendente: A → Z · Descendente: Z → A.")
        elif orden == OPCION_DETALLE_ORDEN_NOMBRE:
            st.caption("Ascendente: A → Z · Descendente: Z → A.")
        else:
            st.caption("Ascendente: orden actual de Google Sheets · Descendente: orden inverso.")

    ascendente = (direccion == OPCION_DETALLE_DIRECCION_ASC)
    if orden == OPCION_DETALLE_ORDEN_ORIGINAL:
        df = df.sort_values(
            by=['_Id_Registro_Num', '_Archivo_Origen'],
            ascending=[ascendente, True],
            na_position='last',
            kind='stable',
        )
    elif orden == OPCION_DETALLE_ORDEN_ETIQUETA:
        df = df.sort_values(
            by=['_Prioridad_Etiqueta', '_Id_Registro_Num'],
            ascending=[ascendente, ascendente],
            na_position='last',
            kind='stable',
        )
    elif orden == OPCION_DETALLE_ORDEN_FECHA_INICIAL:
        df = df.sort_values(
            by=['_Fecha_Sin_Reconocer', '_Id_Registro_Num'],
            ascending=[ascendente, ascendente],
            na_position='last',
            kind='stable',
        )
    elif orden == OPCION_DETALLE_ORDEN_FECHA_RECONOCIDO:
        df = df.sort_values(
            by=['_Fecha_Reconocido', '_Id_Registro_Num'],
            ascending=[ascendente, ascendente],
            na_position='last',
            kind='stable',
        )
    elif orden == OPCION_DETALLE_ORDEN_FECHA_SUBIDO:
        df = df.sort_values(
            by=['_Fecha_Subido_Alianzas', '_Id_Registro_Num'],
            ascending=[ascendente, ascendente],
            na_position='last',
            kind='stable',
        )
    elif orden == OPCION_DETALLE_ORDEN_ULTIMA_ACTUALIZACION:
        df = df.sort_values(
            by=['_Ultima_Fecha', '_Id_Registro_Num'],
            ascending=[ascendente, ascendente],
            na_position='last',
            kind='stable',
        )
    elif orden == OPCION_DETALLE_ORDEN_CEDULA:
        df = df.sort_values(
            by=[COL_CEDULA, '_Id_Registro_Num'],
            ascending=[ascendente, ascendente],
            na_position='last',
            kind='stable',
        )
    elif orden == OPCION_DETALLE_ORDEN_NOMBRE:
        df = df.sort_values(
            by=[COL_NOMBRE, '_Id_Registro_Num'],
            ascending=[ascendente, ascendente],
            na_position='last',
            kind='stable',
        )
    elif orden == OPCION_DETALLE_ORDEN_DF and not ascendente:
        df = df.iloc[::-1]

    # Paso 7: Resumen de los Registros Filtrados
    total = len(cruce_df)
    filtrados = len(df)
    con_id = int(df['_Tiene_Id_Definitivo'].sum()) if filtrados else 0
    addendums = int(df['_Es_Addendum'].sum()) if filtrados else 0
    sin_id = filtrados - con_id
    con_observaciones = int((df['_N_Observaciones'] > 0).sum()) if filtrados else 0
    st.caption(
        "**{:,}** de **{:,}** registros coinciden con los filtros · "
        "Con Id_Definitivo: **{:,}** · Sin Id_Definitivo: **{:,}** · "
        "ADDENDUM: **{:,}** · Con observaciones: **{:,}**".format(
            filtrados, total, con_id, sin_id, addendums, con_observaciones
        )
    )

    # Paso 8: Devolver el DataFrame Filtrado y Ordenado (con Columnas Internas)
    return df

# Función para Mostrar el Detalle Individual de un Registro de Cruce
def mostrar_detalle_registro_cruce(*, registro: pd.Series) -> None:
    # Paso 1: Asegurar que el Registro Tenga las Columnas Internas
    if '_Estado' not in registro.index:
        mapa_nombres = _obtener_mapa_nombres_detalle()
        registro = _construir_df_detalles(
            cruce_df=pd.DataFrame([registro]),
            mapa_nombres=mapa_nombres,
        ).iloc[0]

    # Paso 2: Extraer los Datos del Registro y su Metadata
    mtdt = _obtener_metadata_detalle(registro)
    fechas = _fechas_status_detalle(mtdt)
    fecha_inicial = fechas.get('Sin Reconocer')
    fecha_reconocido = fechas.get('Reconocido')
    fecha_subido = fechas.get('Subido Alianzas')
    ultima_fecha = _ultima_fecha_detalle(fechas)

    etiqueta = str(registro.get('_Etiqueta') or '')
    estado = str(registro.get('_Estado') or 'Sin Reconocer')
    id_definitivo = _texto_id(registro.get('_Id_Definitivo'))
    identificado_por = _texto_busqueda(registro.get('_Identificado_Por'))
    ejecutivo_subida = _texto_busqueda(registro.get('_Ejecutivo_Subida'))
    tipo_identificacion = str(registro.get('_Tipo_Identificacion') or '')
    observaciones = registro.get('_Observaciones') or []
    motivos = registro.get('_Motivos_Cruce') or []
    deudas_posibles = registro.get('_Deudas_Posibles') or []
    pagos_cuotas = registro.get('_Pagos_Cuotas') or []
    tipo_contraoferta = _texto_busqueda(registro.get('_Tipo_Contraoferta'))
    portafolio_ids = _texto_busqueda(registro.get('_Portafolio_Ids'))
    mapa_nombres = _obtener_mapa_nombres_detalle()

    # Nombres para Mostrar
    identificado_mostrar = _nombre_responsable_detalle(identificado_por, mapa_nombres)
    if tipo_identificacion.startswith('Automático'):
        identificado_mostrar = tipo_identificacion
    ejecutivo_mostrar = _nombre_responsable_detalle(ejecutivo_subida, mapa_nombres)

    # Datos Principales
    nombre_cliente = replaceNaN(value=registro.get(COL_NOMBRE), nan_replace='Sin nombre')
    cedula = replaceNaN(value=registro.get(COL_CEDULA), nan_replace='Sin cédula')
    banco = replaceNaN(value=registro.get(COL_BANCO), nan_replace='Sin banco')
    numero_credito = replaceNaN(value=registro.get(COL_CREDITO), nan_replace='Sin número de crédito')
    monto_actual = _formatear_monto_detalle(registro.get(COL_MONTO_ACTUAL))
    monto_actual_original = _formatear_monto_detalle(registro.get('_Monto_Actual_Original'))
    fecha_limite = _formatear_fecha_corta_detalle(registro.get('_Fecha_Limite_Pago'))
    id_cruce = _texto_busqueda(registro.get('Id_Cruce'))
    id_registro = _texto_busqueda(registro.get('_Id_Registro')) or '—'
    archivo = _texto_busqueda(registro.get('_Archivo_Origen')) or 'Sin archivo'
    casa = _texto_busqueda(registro.get('_Casa_Cobro')) or 'Sin casa de cobro'
    alias = _texto_busqueda(registro.get('_Alias_Casa'))
    pago_minimo = obtener_pago_minimo(mtdt) or {}
    pago_minimo_texto = 'Sin pago registrado'
    if pago_minimo:
        pago_minimo_texto = "{} a {} cuota(s)".format(
            _formatear_monto_detalle(pago_minimo.get('Monto')),
            int(float(pago_minimo.get('Cuotas', 1) or 1)),
        )
    motivos_texto = ' · '.join(motivos) if motivos else 'Sin motivos registrados'
    portafolio_texto = portafolio_ids if portafolio_ids else 'Sin portafolio'
    tipo_contraoferta_texto = tipo_contraoferta if tipo_contraoferta else 'No registrada'

    # Paso 3: Tarjeta Resumen
    with st.container(border=True):
        colDatos, colAuditoria = st.columns([3, 2], gap="medium")

        with colDatos:
            st.markdown("#### 👤 {} · 🪪 {}".format(nombre_cliente, cedula))
            badges = [
                _badge_detalle(texto=etiqueta or 'SIN ETIQUETA', color=_color_etiqueta_detalle(etiqueta)),
                _badge_detalle(texto=estado, color=_color_estado_detalle(estado)),
                _badge_detalle(texto=casa, color='gray'),
            ]
            if alias:
                badges.append(_badge_detalle(texto=alias, color='gray'))
            st.markdown(" ".join(badges))
            st.caption(
                "**Banco**: {} | **N° Crédito**: {} | **Monto Actual**: {} | **Fecha Límite**: {}".format(
                    banco, numero_credito, monto_actual, fecha_limite
                )
            )
            st.caption(
                "**Id_Definitivo**: `{}` | **Identificado por**: {} | **Última actualización**: {}".format(
                    _formatear_id_detalle(id_definitivo), identificado_mostrar, _formatear_fecha_detalle(ultima_fecha)
                )
            )
            st.caption(
                "**Archivo**: {} | **Fila original**: {} | **Id del Cruce**: `{}`".format(
                    archivo, id_registro, id_cruce
                )
            )
            st.caption("**Fecha de cruce inicial**: {}".format(_formatear_fecha_detalle(fecha_inicial)))
            if observaciones:
                st.warning(
                    "**{} observación(es) de auditoría.** Revisa el detalle completo.".format(len(observaciones)),
                    icon="⚠️",
                )

        with colAuditoria:
            st.markdown("**🕵️ Trazabilidad**")
            st.markdown(
                "\n".join([
                    "- 📥 **Cruce inicial** (`Sin Reconocer`): {}".format(_formatear_fecha_detalle(fecha_inicial)),
                    "  - 👤 Base subida por: {}".format(ejecutivo_mostrar),
                    "- ✅ **Reconocido**: {}".format(_formatear_fecha_detalle(fecha_reconocido)),
                    "  - 👤 Identificado por: {}".format(identificado_mostrar),
                    "- 📤 **Subido Alianzas**: {}".format(_formatear_fecha_detalle(fecha_subido)),
                    "  - 👤 Responsable: No registrado",
                ])
            )
            st.caption(
                "⏱️ Cruce → Reconocido: **{}** · Reconocido → Subido: **{}**".format(
                    _formatear_duracion_detalle(fecha_inicial, fecha_reconocido),
                    _formatear_duracion_detalle(fecha_reconocido, fecha_subido),
                )
            )

        # Paso 4: Detalle Completo
        with st.expander("🔍 Ver detalle completo", expanded=False):
            colCruce, colAuditoriaDetalle = st.columns(2, gap="medium")

            with colCruce:
                st.markdown("##### 📋 Datos del Cruce")
                st.markdown(
                    "\n".join([
                        "- **Etiqueta**: {}".format(etiqueta or 'Sin etiqueta'),
                        "- **Motivos del Cruce**: {}".format(motivos_texto),
                        "- **Tipo de Contraoferta**: {}".format(tipo_contraoferta_texto),
                        "- **Id_Definitivo**: `{}`".format(_formatear_id_detalle(id_definitivo)),
                        "- **Portafolio(s)**: {}".format(portafolio_texto),
                        "- **Deudas Posibles**: {}".format(len(deudas_posibles)),
                        "- **Monto Actual (Aliado)**: {}".format(monto_actual),
                        "- **Monto Actual Original (Local)**: {}".format(monto_actual_original),
                        "- **Pago Mínimo**: {}".format(pago_minimo_texto),
                    ])
                )

            with colAuditoriaDetalle:
                st.markdown("##### 🕵️ Auditoría")
                auditoria_df = pd.DataFrame([
                    {
                        'Estado': 'Sin Reconocer',
                        'Fecha': _formatear_fecha_detalle(fecha_inicial),
                        'Responsable': ejecutivo_mostrar,
                        'Duración': '—',
                    },
                    {
                        'Estado': 'Reconocido',
                        'Fecha': _formatear_fecha_detalle(fecha_reconocido),
                        'Responsable': identificado_mostrar,
                        'Duración': _formatear_duracion_detalle(fecha_inicial, fecha_reconocido),
                    },
                    {
                        'Estado': 'Subido Alianzas',
                        'Fecha': _formatear_fecha_detalle(fecha_subido),
                        'Responsable': 'No registrado',
                        'Duración': _formatear_duracion_detalle(fecha_reconocido, fecha_subido),
                    },
                ])
                st.dataframe(
                    auditoria_df,
                    width="stretch",
                    hide_index=True,
                    height=min(35 * (len(auditoria_df) + 1), 160),
                )

            st.divider()
            colDeudas, colPagos = st.columns([2, 1], gap="medium")

            with colDeudas:
                st.markdown("##### 🏦 Deudas Posibles")
                if deudas_posibles:
                    deudas_df = pd.DataFrame([
                        {
                            'Banco': _texto_busqueda(deuda.get('Banco')),
                            'Numero_Credito': _texto_busqueda(deuda.get('Numero_Credito')),
                            'Monto_Actual': pd.to_numeric(deuda.get('Monto_Actual'), errors='coerce'),
                            'Id_Deuda': _texto_id(deuda.get('Id_Deuda')),
                            'Es_Liquidada': bool(deuda.get('Es_Liquidada', False)),
                        }
                        for deuda in deudas_posibles
                    ])
                    st.dataframe(
                        estilizar_deudas(deudas_df, id_definitivo=id_definitivo),
                        width="stretch",
                        hide_index=True,
                        column_order=['Banco', 'Numero_Credito', 'Monto_Actual', 'Id_Deuda'],
                        column_config={
                            'Monto_Actual': st.column_config.NumberColumn('Monto_Actual', format='localized'),
                        },
                        height=min(35 * (len(deudas_df) + 1), 240),
                    )
                    st.caption(
                        "🟥 Deuda liquidada · 🟩 Deuda activa{}.".format(
                            " · La deuda escogida se muestra subrayada"
                            if id_definitivo and (id_definitivo != ETIQUETA_ADDENDUM)
                            else ""
                        )
                    )
                else:
                    st.caption("Sin deudas posibles registradas.")

            with colPagos:
                st.markdown("##### 💸 Pagos a Cuotas")
                if pagos_cuotas:
                    pagos_df = pd.DataFrame([
                        {
                            'Cuotas': int(float(pago.get('Cuotas', 1) or 1)),
                            'Monto': pd.to_numeric(pago.get('Monto'), errors='coerce'),
                        }
                        for pago in pagos_cuotas
                    ])
                    st.dataframe(
                        pagos_df,
                        width="stretch",
                        hide_index=True,
                        column_config={
                            'Monto': st.column_config.NumberColumn('Monto', format='localized'),
                        },
                        height=min(35 * (len(pagos_df) + 1), 180),
                    )
                else:
                    st.caption("Sin pagos a cuotas registrados.")

            if observaciones:
                st.warning(
                    "\n".join("- {}".format(observacion) for observacion in observaciones),
                    icon="⚠️",
                    title="Observaciones de Auditoría",
                )
            else:
                st.success("Sin observaciones de auditoría para este registro.", icon="✅")

# Función para Mostrar los Detalles del Cruce de forma Paginada
def mostrar_detalles_cruce_paginados(*, cruce_df: pd.DataFrame, key: str) -> None:
    """Muestra los detalles del cruce en sub-páginas manejadas localmente.

    Divide el DataFrame en páginas según la cantidad de registros por página
    seleccionada (10-20-30-40) y renderiza cada registro de la página actual
    con la función mostrar_detalle_registro_cruce. El estado de la paginación
    se guarda en el Session State de forma local, aislado con la `key` indicada.
    """
    # Paso 1: Si no hay Registros, no se Muestra Nada
    total_registros = len(cruce_df)
    if total_registros == 0:
        st.info("No hay registros que coincidan con los filtros seleccionados.", icon="🔍")
        return

    # Paso 2: Asegurar las Columnas Internas de Detalles
    if '_Estado' not in cruce_df.columns:
        mapa_nombres = _obtener_mapa_nombres_detalle()
        cruce_df = _construir_df_detalles(cruce_df=cruce_df, mapa_nombres=mapa_nombres)

    # Paso 3: Estado Local de la Paginación (aislado por `key`)
    key_registros_por_pagina = "paginacion_detalles_registros_por_pagina_{}".format(key)
    key_pagina_actual = "paginacion_detalles_pagina_actual_{}".format(key)
    key_firma = "paginacion_detalles_firma_{}".format(key)

    st.session_state.setdefault(key_registros_por_pagina, 10)
    st.session_state.setdefault(key_pagina_actual, 1)

    # Paso 4: Reiniciar la Página si Cambian los Filtros o el Ordenamiento
    firma_actual = int(pd.util.hash_pandas_object(cruce_df['Id_Cruce'].astype(str), index=False).sum())
    if st.session_state.get(key_firma) != firma_actual:
        st.session_state[key_firma] = firma_actual
        st.session_state[key_pagina_actual] = 1

    registros_por_pagina = int(st.session_state[key_registros_por_pagina])
    if registros_por_pagina not in (10, 20, 30, 40):
        registros_por_pagina = 10
        st.session_state[key_registros_por_pagina] = 10
    total_paginas = max(1, int(np.ceil(total_registros / registros_por_pagina)))
    pagina_actual = int(st.session_state.get(key_pagina_actual, 1))
    pagina_actual = min(max(1, pagina_actual), total_paginas)
    st.session_state[key_pagina_actual] = pagina_actual

    # Paso 5: Rebanada de la Página Actual
    inicio = int((pagina_actual - 1) * registros_por_pagina)
    fin = int(min(inicio + registros_por_pagina, total_registros))
    pagina_df = cruce_df.iloc[inicio:fin]

    # Paso 6: Controles de Paginación (Superiores)
    with st.container(border=True):
        colRegistros, colPagina, colNavegacion = st.columns([1.2, 1, 2.2], vertical_alignment="center", gap="medium")

        with colRegistros:
            def _reiniciar_pagina_detalles() -> None:
                st.session_state[key_pagina_actual] = 1

            st.selectbox(
                label="**Registros por página**",
                options=[10, 20, 30, 40],
                key=key_registros_por_pagina,
                on_change=_reiniciar_pagina_detalles,
                disabled=(total_registros <= 10),
                help="Selecciona cuántos registros quieres ver por página.",
            )

        with colPagina:
            st.number_input(
                label="**Página Actual**",
                min_value=1,
                max_value=int(total_paginas),
                key=key_pagina_actual,
                disabled=(total_paginas <= 1),
                help="Escribe la página a la que quieres ir.",
            )

        with colNavegacion:
            st.space("xxsmall")
            if total_paginas > 1:
                colInicio, colAnterior, colActual, colSiguiente, colFinal = st.columns(
                    5, vertical_alignment="center", gap="small"
                )

                def _ir_a_pagina_detalles(nueva_pagina: int) -> None:
                    st.session_state[key_pagina_actual] = nueva_pagina

                with colInicio:
                    st.button(
                        "<<",
                        key="paginacion_detalles_ir_inicio_{}".format(key),
                        disabled=(pagina_actual == 1),
                        on_click=_ir_a_pagina_detalles,
                        args=(1,),
                        help="Ir a la primera página.",
                        width="stretch",
                    )
                with colAnterior:
                    st.button(
                        str(max(1, pagina_actual - 1)),
                        key="paginacion_detalles_anterior_{}".format(key),
                        disabled=(pagina_actual == 1),
                        on_click=_ir_a_pagina_detalles,
                        args=(max(1, pagina_actual - 1),),
                        help="Ir a la página anterior.",
                        width="stretch",
                    )
                with colActual:
                    st.button(
                        str(pagina_actual),
                        key="paginacion_detalles_actual_{}".format(key),
                        type="primary",
                        disabled=True,
                        help="Página actual.",
                        width="stretch",
                    )
                with colSiguiente:
                    st.button(
                        str(min(total_paginas, pagina_actual + 1)),
                        key="paginacion_detalles_siguiente_{}".format(key),
                        disabled=(pagina_actual >= total_paginas),
                        on_click=_ir_a_pagina_detalles,
                        args=(min(total_paginas, pagina_actual + 1),),
                        help="Ir a la página siguiente.",
                        width="stretch",
                    )
                with colFinal:
                    st.button(
                        ">>",
                        key="paginacion_detalles_ir_final_{}".format(key),
                        disabled=(pagina_actual >= total_paginas),
                        on_click=_ir_a_pagina_detalles,
                        args=(int(total_paginas),),
                        help="Ir a la última página.",
                        width="stretch",
                    )
            else:
                st.button(
                    "1",
                    key="paginacion_detalles_actual_{}".format(key),
                    disabled=True,
                    type="primary",
                    help="Página actual.",
                    width="stretch",
                )

    # Paso 7: Mostrar los Registros de la Página Actual
    st.caption(
        "**Mostrando {}-{} de {:,} registros.** (**{:.1%}**, **{}** páginas en total)".format(
            inicio + 1,
            fin,
            total_registros,
            len(pagina_df) / total_registros,
            total_paginas,
        )
    )

    for _, registro in pagina_df.iterrows():
        mostrar_detalle_registro_cruce(registro=registro)

    # Paso 8: Caption Final con la Página Actual
    st.caption("Página **{}** de **{}**.".format(pagina_actual, total_paginas))
