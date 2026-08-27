# Estándar usando Pep8
# Librerías de Python
# Librerías de Terceros
import numpy as np
import pandas as pd
import streamlit as st
# Librerías Locales

LLAVE_CAMBIOS_ID_DEFINITIVO = 'cambios_id_definitivo'
OPCION_SIN_OPCIONES = 'Sin Opciones Actuales'
ID_DEFINITIVO_ADDENDUM = 'ADDENDUM'

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

    incluir_con_definitivo = st.toggle(
        label="**✅ Incluir Deudas con Id_Definitivo**",
        value=False,
        key="filtro_cruce_incluir_definitivo_input",
        help="Activar para incluir también las deudas que ya tienen un Id_Definitivo asignado.",
    )

    # Paso 3: Aplicar los Filtros Seleccionados al DataFrame
    if casa_seleccionada:
        df = df[df['_Casa_Cobro'].isin(casa_seleccionada)]

    if alias_seleccionado:
        df = df[df['_Alias_Casa'].isin(alias_seleccionado)]

    if ejecutivo_seleccionado:
        df = df[df['_Ejecutivo_Subida'].isin(ejecutivo_seleccionado)]

    if etiqueta_seleccionada:
        df = df[df['_Etiqueta'].isin(etiqueta_seleccionada)]

    if not incluir_con_definitivo:
        df = df[~df['_Tiene_Id_Definitivo']]

    # Paso 4: Devolver el DataFrame Filtrado (sin las Columnas Auxiliares)
    return df.drop(columns=['_Casa_Cobro', '_Alias_Casa', '_Ejecutivo_Subida', '_Etiqueta', '_Tiene_Id_Definitivo'])

# Función Auxiliar para Mostrar un Registro del Cruce (Vista de 2 Columnas)
def mostrar_registro_cruce(*, registro: pd.Series) -> None:
    # Paso 1: Extraemos la Metadata y el Id_Cruce del Registro
    mtdt = dict(registro['Metadata'])
    id_cruce = str(registro['Id_Cruce'])

    # Paso 2: Inicializamos el Diccionario de Cambios en el Session State
    st.session_state.setdefault(LLAVE_CAMBIOS_ID_DEFINITIVO, {})
    cambios = st.session_state[LLAVE_CAMBIOS_ID_DEFINITIVO]

    # Columna Izquierda (70%): Información de las Posibles Deudas
    # Columna Derecha (30%): Input del Id_Deuda Definitivo
    colIzquierda, colDerecha = st.columns([7, 3], vertical_alignment="top", gap="medium")

    with colIzquierda:
        titulo_expander = "🔎 {} - {} [{}]".format(
            mtdt.get('Casa_Cobro', ''),
            registro.get('Cedula', ''),
            mtdt.get('Etiqueta', ''),
        )
        with st.expander(titulo_expander, expanded=False):
            info_basica = {
                'Cédula': registro.get('Cedula', ''),
                'Nombre del Cliente': registro.get('Nombre_Cliente', ''),
                'Banco': registro.get('Banco', ''),
                'Monto Actual': registro.get('Monto_Actual', ''),
                'Número de Crédito': registro.get('Numero_Credito', ''),
                'Etiqueta': mtdt.get('Etiqueta', ''),
                'Casa de Cobro': mtdt.get('Casa_Cobro', ''),
                'Alias': mtdt.get('Alias_Casa', ''),
                'Ejecutivo de Subida': mtdt.get('Ejecutivo_Subida', ''),
                'Fecha de Identificación': mtdt.get('Fecha_Identificacion', ''),
                'Fecha Límite de Pago': mtdt.get('Fecha_Limite_Pago', ''),
                'Id_Definitivo': mtdt.get('Id_Definitivo', 'Sin Definir'),
                'Portafolio': mtdt.get('Portafolio_Ids', ''),
            }
            info_basica = {k: (str(v) if v is not None else '') for k, v in info_basica.items()}
            st.dataframe(
                pd.DataFrame({'Dato': list(info_basica.keys()), 'Valor': list(info_basica.values())}),
                hide_index=True,
                width="stretch",
            )
            st.markdown("**💼 Deudas Posibles**")
            deudas_posibles = mtdt.get('Deudas_Posibles', []) or []
            if deudas_posibles:
                st.dataframe(pd.DataFrame(deudas_posibles), hide_index=True, width="stretch")
            else:
                st.caption("Sin Deudas Posibles")

    with colDerecha:
        # El valor previo define si el toggle arranca marcado como Addendum
        valor_previo = cambios.get(id_cruce, mtdt.get('Id_Definitivo'))
        es_addendum = (valor_previo == ID_DEFINITIVO_ADDENDUM)

        marcar_addendum = st.toggle(
            label="**🚫 Marcar como Addendum**",
            value=es_addendum,
            key="cruce_addendum_toggle_{}".format(id_cruce),
            help="Al activarlo, el Id_Definitivo será ADDENDUM y no se podrá escoger un Id_Deuda.",
        )

        if marcar_addendum:
            # Si está activo, el Id_Definitivo será ADDENDUM
            cambios[id_cruce] = ID_DEFINITIVO_ADDENDUM
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
            deudas_posibles = mtdt.get('Deudas_Posibles', []) or []
            opciones = [str(d.get('Id_Deuda', '') or '') for d in deudas_posibles if d.get('Id_Deuda') not in (None, '')]
            hay_opciones = bool(opciones)
            if not hay_opciones:
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
                cambios[id_cruce] = seleccion

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
    inicio = (pagina_actual - 1) * registros_por_pagina
    fin = min(inicio + registros_por_pagina, total_deudas)
    pagina_df = cruce_df.iloc[inicio:fin]

    # Paso 1: Mostrar los Registros de la Página Actual
    for _, registro in pagina_df.iterrows():
        mostrar_registro_cruce(registro=registro)

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
            key=key_pagina_actual,
            min_value=1,
            max_value=total_paginas,
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
