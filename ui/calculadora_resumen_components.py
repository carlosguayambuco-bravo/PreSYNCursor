# Estándar usando PEP8
# Librerías de Python
from typing import Any, Optional
# Librerías de Terceros
import pandas as pd
import streamlit as st
# Librerías Locales
from modules.resumen_oportunidades import calcular_resumen_oportunidades
from ui.calculadora_masiva_components import (
    LLAVE_RESULTADO_MASIVO,
    PREFIJO_FILTROS_RESUMEN,
    _es_verdadero,
    _formatear_monto,
    _formatear_porcentaje,
    _md,
    _mostrar_filtros_masivos,
    _normalizar_lista,
    calcular_y_guardar_resultado_masivo,
    filtrar_oportunidades_masivas,
)
from ui.forms_components import mostrar_componente_feedback
from utils.helpers_general import formatNumber

# --- Configuración de la Vista de Resumen ---
COLUMNAS_REQUERIDAS_RESUMEN = {
    "Portafolios_Detalle",
    "Ingreso_Estimado",
    "Deudas_Detalle",
    "Estados_Actualizacion",
    "Bancos",
    "Casas_Cobro",
}
ALTO_MAXIMO_DETALLE = 520
LLAVE_BUSQUEDA_DETALLE = "calc_resumen_busqueda_detalle"

# --- Funciones Auxiliares de Formato ---
def _monto_tabla(valor: Any) -> str:
    """Formatea un monto para las tablas del resumen."""
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        numero = 0.0
    if pd.isna(numero):
        numero = 0.0
    return "$ {}".format(formatNumber(int(round(numero))))

def _porcentaje_tabla(valor: Any) -> str:
    """Formatea un decimal como porcentaje para las tablas."""
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        numero = 0.0
    if pd.isna(numero):
        numero = 0.0
    return "{:.1%}".format(numero)

def _entero_tabla(valor: Any) -> str:
    """Formatea un conteo entero con separador de miles."""
    try:
        numero = int(round(float(valor)))
    except (TypeError, ValueError):
        numero = 0
    return "{:,}".format(numero)

def _tabla_formateada(
    df: pd.DataFrame,
    *,
    columnas_monto: tuple[str, ...] = (),
    columnas_porcentaje: tuple[str, ...] = (),
    columnas_entero: tuple[str, ...] = (),
    renombrar: Optional[dict[str, str]] = None,
) -> pd.DataFrame:
    """Copia una tabla y formatea sus columnas para mostrarla."""
    if df is None or df.empty:
        return pd.DataFrame()
    copia = df.copy()
    for columna in columnas_monto:
        if columna in copia.columns:
            copia[columna] = copia[columna].apply(_monto_tabla)
    for columna in columnas_porcentaje:
        if columna in copia.columns:
            copia[columna] = copia[columna].apply(_porcentaje_tabla)
    for columna in columnas_entero:
        if columna in copia.columns:
            copia[columna] = copia[columna].apply(_entero_tabla)
    if "Es_Total" in copia.columns:
        copia["Es_Total"] = copia["Es_Total"].apply(
            lambda valor: "Sí" if _es_verdadero(valor) else ""
        )
    if renombrar:
        copia = copia.rename(columns=renombrar)
    return copia

def _csv_bytes(df: pd.DataFrame) -> bytes:
    """Convierte una tabla en CSV UTF-8 con BOM para Excel."""
    return df.to_csv(index=False).encode("utf-8-sig")

def _grafico_barras(
    df: pd.DataFrame,
    *,
    categoria: str,
    valor: str,
    top: int = 15,
    alto: int = 320,
) -> None:
    """Muestra un gráfico de barras horizontal con la categoría y el valor."""
    if df is None or df.empty or categoria not in df.columns or valor not in df.columns:
        return
    datos = df[[categoria, valor]].copy()
    datos = datos[pd.to_numeric(datos[valor], errors="coerce").notna()]
    if datos.empty:
        return
    datos[categoria] = datos[categoria].astype(str)
    datos = datos.sort_values(valor, ascending=False).head(max(1, int(top)))
    datos = datos.set_index(categoria)
    st.bar_chart(datos, horizontal=True, height=int(alto))

def _mostrar_tabla(
    df: pd.DataFrame,
    *,
    columnas_monto: tuple[str, ...] = (),
    columnas_porcentaje: tuple[str, ...] = (),
    columnas_entero: tuple[str, ...] = (),
    renombrar: Optional[dict[str, str]] = None,
    alto: Optional[int] = None,
) -> None:
    """Muestra una tabla formateada o un mensaje si no hay datos."""
    if df is None or df.empty:
        st.caption("Sin datos para los filtros seleccionados.")
        return
    tabla = _tabla_formateada(
        df,
        columnas_monto=columnas_monto,
        columnas_porcentaje=columnas_porcentaje,
        columnas_entero=columnas_entero,
        renombrar=renombrar,
    )
    opciones: dict[str, Any] = {
        "hide_index": True,
        "width": "stretch",
    }
    if alto is not None:
        opciones["height"] = int(alto)
    st.dataframe(tabla, **opciones)

def _mostrar_bloque_dimension(
    resumen: dict[str, Any],
    *,
    clave: str,
    titulo: str,
    etiqueta_valor: str = "Valor",
    valor_grafico: str = "Ingreso_Estimado",
    top: int = 15,
) -> None:
    """Muestra una dimensión con tabla y gráfico de barras."""
    tabla = resumen.get(clave, pd.DataFrame())
    st.markdown("#### {}".format(titulo))
    if tabla is None or tabla.empty:
        st.caption("Sin datos para los filtros seleccionados.")
        return
    colTabla, colGrafico = st.columns([1.6, 1])
    with colTabla:
        _mostrar_tabla(
            tabla,
            columnas_monto=("Ingreso_Estimado", "Ingreso_Potencial"),
            columnas_porcentaje=("Porcentaje_Ingreso",),
            columnas_entero=("Incidencias", "Clientes", "Deudas", "Unidades"),
            renombrar={
                "Valor": etiqueta_valor,
                "Incidencias": "Incid.",
                "Clientes": "Clientes",
                "Deudas": "Deudas",
                "Unidades": "Unidades",
                "Ingreso_Estimado": "Ingreso Estimado",
                "Ingreso_Potencial": "Ingreso Potencial",
                "Porcentaje_Ingreso": "% Ingreso",
            },
            alto=320,
        )
    with colGrafico:
        _grafico_barras(
            tabla,
            categoria="Valor",
            valor=valor_grafico,
            top=top,
            alto=320,
        )

def _mostrar_metricas(kpis: dict[str, Any]) -> None:
    """Muestra las métricas principales del panel."""
    fila1 = st.columns(4)
    with fila1[0]:
        st.metric(
            "**Clientes filtrados**",
            "{:,}".format(int(kpis.get("Clientes_Total", 0))),
            help=(
                "Clientes que cumplen los filtros. Con 'Solo con "
                "oportunidades' activo, todos tienen al menos una oportunidad."
            ),
        )
    with fila1[1]:
        st.metric(
            "**Clientes con oportunidad**",
            "{:,}".format(int(kpis.get("Clientes_Con_Oportunidad", 0))),
        )
    with fila1[2]:
        st.metric(
            "**Cobertura clientes**",
            _formatear_porcentaje(kpis.get("Cobertura_Clientes", 0)),
            help=(
                "Clientes con oportunidad / clientes filtrados. Desactiva "
                "'Solo con oportunidades' para incluir clientes sin oportunidad."
            ),
        )
    with fila1[3]:
        st.metric(
            "**Incidencias**",
            "{:,}".format(int(kpis.get("Incidencias", 0))),
            help="Una incidencia es una oportunidad aplicada a una unidad de análisis.",
        )

    fila2 = st.columns(4)
    with fila2[0]:
        st.metric(
            "**Deudas con oportunidad**",
            "{:,}".format(int(kpis.get("Deudas_Con_Oportunidad", 0))),
        )
    with fila2[1]:
        st.metric(
            "**Cobertura deudas**",
            _formatear_porcentaje(kpis.get("Cobertura_Deudas", 0)),
            help=(
                "Deudas con al menos una oportunidad / deudas analizadas de "
                "los clientes filtrados."
            ),
        )
    with fila2[2]:
        st.metric(
            "**Ingreso Estimado**",
            _formatear_monto(kpis.get("Ingreso_Estimado_Total", 0)),
            help=(
                "Suma de los máximos por unidad/portafolio. Evita el doble "
                "conteo entre oportunidades de la misma unidad."
            ),
        )
    with fila2[3]:
        st.metric(
            "**Ingreso Potencial**",
            _formatear_monto(kpis.get("Ingreso_Potencial_Total", 0)),
            help=(
                "Suma de todas las oportunidades. No se suma al Ingreso "
                "Estimado porque una unidad puede tener varias oportunidades."
            ),
        )

    fila3 = st.columns(4)
    with fila3[0]:
        st.metric(
            "**DUM con oportunidad**",
            _formatear_monto(kpis.get("DUM_Con_Oportunidad", 0)),
            help=(
                "DUM de las unidades/portafolios con al menos una oportunidad. "
                "En oportunidades generales se toma la unidad completa."
            ),
        )
    with fila3[1]:
        st.metric(
            "**Ingreso prom. / cliente**",
            _formatear_monto(kpis.get("Ingreso_Promedio_Cliente", 0)),
        )
    with fila3[2]:
        st.metric(
            "**DUM prom. / cliente**",
            _formatear_monto(kpis.get("DUM_Promedio_Cliente", 0)),
        )
    with fila3[3]:
        st.metric(
            "**Ingreso / DUM**",
            _formatear_porcentaje(kpis.get("Ingreso_Sobre_DUM", 0)),
        )

    fila4 = st.columns(4)
    with fila4[0]:
        st.metric(
            "**Unidades con oportunidad**",
            "{:,}".format(int(kpis.get("Unidades_Con_Oportunidad", 0))),
        )
    with fila4[1]:
        st.metric(
            "**Cobertura unidades**",
            _formatear_porcentaje(kpis.get("Cobertura_Unidades", 0)),
        )
    with fila4[2]:
        st.metric(
            "**Oportunidades / cliente**",
            "{:.2f}".format(
                float(kpis.get("Oportunidades_Promedio_Cliente", 0) or 0)
            ),
        )
    with fila4[3]:
        st.metric(
            "**Deudas / oportunidad**",
            "{:.2f}".format(
                float(kpis.get("Deudas_Promedio_Oportunidad", 0) or 0)
            ),
        )

def _mostrar_lectura_rapida(
    resumen: dict[str, Any],
) -> None:
    """Resume los principales hallazgos del panel."""
    por_oportunidad = resumen.get("por_oportunidad", pd.DataFrame())
    por_negociador = resumen.get("por_negociador", pd.DataFrame())
    por_banco = resumen.get("por_banco", pd.DataFrame())
    if por_oportunidad is None or por_oportunidad.empty:
        return

    oportunidades = por_oportunidad[
        ~por_oportunidad["Es_Total"].fillna(False).astype(bool)
    ]
    oportunidades = oportunidades[
        pd.to_numeric(
            oportunidades["Ingreso_Estimado"], errors="coerce"
        ).fillna(0) > 0
    ]
    if oportunidades.empty:
        return

    mejor = oportunidades.sort_values(
        "Ingreso_Estimado", ascending=False
    ).iloc[0]
    lineas = [
        "**Mayor ingreso estimado:** {} con {}.".format(
            mejor["Oportunidad"], _formatear_monto(mejor["Ingreso_Estimado"])
        )
    ]
    if por_negociador is not None and not por_negociador.empty:
        negociador = por_negociador.iloc[0]
        lineas.append(
            "**Negociador líder:** {} con {} y {} deuda(s).".format(
                negociador["Valor"],
                _formatear_monto(negociador["Ingreso_Estimado"]),
                int(negociador["Deudas"]),
            )
        )
    if por_banco is not None and not por_banco.empty:
        banco = por_banco.sort_values("Deudas", ascending=False).iloc[0]
        lineas.append(
            "**Banco con más deudas con oportunidad:** {} ({}).".format(
                banco["Valor"], int(banco["Deudas"])
            )
        )
    st.markdown("#### 💡 Lectura rápida")
    for linea in lineas:
        st.markdown("- {}".format(_md(linea)))

def _mostrar_resumen_general(resumen: dict[str, Any]) -> None:
    """Muestra los KPIs, la tabla por oportunidad y el tipo de análisis."""
    kpis = resumen.get("kpis", {})
    _mostrar_metricas(kpis)
    st.caption(
        "**Ingreso Estimado** = suma de los máximos por unidad/portafolio. "
        "**Ingreso Potencial** = suma de todas las oportunidades; no se suma al "
        "total porque una misma unidad puede tener varias oportunidades. El "
        "máximo de la tarjeta del cliente puede ser menor: allí se toma el mayor "
        "ingreso entre todas sus unidades, no la suma."
    )
    st.caption(
        "En la tabla por oportunidad, el **Ingreso Estimado** se atribuye solo "
        "a la oportunidad que ganó el máximo de su unidad. Por eso una "
        "oportunidad puede mostrar 0 en esa columna y un valor en **Ingreso "
        "Potencial**."
    )
    _mostrar_lectura_rapida(resumen)
    st.divider()

    por_oportunidad = resumen.get("por_oportunidad", pd.DataFrame())
    st.markdown("#### 🎯 Oportunidades por tipo")
    colTabla, colGrafico = st.columns([1.7, 1])
    with colTabla:
        _mostrar_tabla(
            por_oportunidad,
            columnas_monto=("Ingreso_Estimado", "Ingreso_Potencial"),
            columnas_porcentaje=("Porcentaje_Ingreso",),
            columnas_entero=("Incidencias", "Clientes", "Deudas", "Unidades"),
            renombrar={
                "Oportunidad": "Oportunidad",
                "Incidencias": "Incid.",
                "Clientes": "Clientes",
                "Deudas": "Deudas",
                "Unidades": "Unidades",
                "Ingreso_Estimado": "Ingreso Estimado",
                "Ingreso_Potencial": "Ingreso Potencial",
                "Porcentaje_Ingreso": "% del Ingreso",
                "Es_Total": "Total",
            },
            alto=380,
        )
    with colGrafico:
        if not por_oportunidad.empty:
            _grafico_barras(
                por_oportunidad[
                    ~por_oportunidad["Es_Total"].fillna(False).astype(bool)
                ],
                categoria="Oportunidad",
                valor="Ingreso_Estimado",
                top=10,
                alto=380,
            )

    st.divider()
    st.markdown("#### 🧩 Oportunidades por tipo de análisis")
    colTablaTipo, colGraficoTipo = st.columns([1.7, 1])
    with colTablaTipo:
        _mostrar_tabla(
            resumen.get("por_tipo_analisis", pd.DataFrame()),
            columnas_monto=("Ingreso_Estimado", "Ingreso_Potencial"),
            columnas_porcentaje=("Porcentaje_Ingreso",),
            columnas_entero=("Incidencias", "Clientes", "Deudas", "Unidades"),
            renombrar={
                "Tipo_Analisis": "Tipo de Análisis",
                "Incidencias": "Incid.",
                "Clientes": "Clientes",
                "Deudas": "Deudas",
                "Unidades": "Unidades",
                "Ingreso_Estimado": "Ingreso Estimado",
                "Ingreso_Potencial": "Ingreso Potencial",
                "Porcentaje_Ingreso": "% del Ingreso",
                "Es_Total": "Total",
            },
            alto=300,
        )
    with colGraficoTipo:
        tipo = resumen.get("por_tipo_analisis", pd.DataFrame())
        if not tipo.empty:
            _grafico_barras(
                tipo[~tipo["Es_Total"].fillna(False).astype(bool)],
                categoria="Tipo_Analisis",
                valor="Ingreso_Estimado",
                top=10,
                alto=300,
            )

def _mostrar_distribuciones(resumen: dict[str, Any]) -> None:
    """Muestra las distribuciones por dimensiones de negocio."""
    st.markdown("### 🧩 Distribuciones")
    st.caption(
        "Los ingresos por dimensión se asignan proporcionalmente al DUM de cada "
        "deuda. Los filtros de estado, banco y casa de cobro seleccionan clientes "
        "con al menos una deuda que cumple; el detalle conserva todas las "
        "oportunidades del cliente. El **Ingreso Estimado** se reconcilia con el "
        "total; el **Ingreso Potencial** no es aditivo entre dimensiones porque "
        "una unidad puede tener varias oportunidades."
    )

    colNegociador, colProspectoCredito = st.columns(2)
    with colNegociador:
        _mostrar_bloque_dimension(
            resumen,
            clave="por_negociador",
            titulo="👤 Por negociador",
            etiqueta_valor="Negociador",
            valor_grafico="Ingreso_Estimado",
            top=10,
        )
    with colProspectoCredito:
        _mostrar_bloque_dimension(
            resumen,
            clave="por_prospecto_credito",
            titulo="🏦 Por prospecto de crédito",
            etiqueta_valor="Prospecto Crédito",
            valor_grafico="Clientes",
            top=10,
        )

    colProspectoTrad, colTipoUnidad = st.columns(2)
    with colProspectoTrad:
        _mostrar_bloque_dimension(
            resumen,
            clave="por_prospecto_tradicional",
            titulo="💳 Por prospecto de tradicional",
            etiqueta_valor="Prospecto Tradicional",
            valor_grafico="Deudas",
            top=10,
        )
    with colTipoUnidad:
        _mostrar_bloque_dimension(
            resumen,
            clave="por_tipo_unidad",
            titulo="📦 Por tipo de unidad",
            etiqueta_valor="Tipo de Unidad",
            valor_grafico="Ingreso_Estimado",
            top=10,
        )

    colBanco, colCasa = st.columns(2)
    with colBanco:
        _mostrar_bloque_dimension(
            resumen,
            clave="por_banco",
            titulo="🏛️ Por banco",
            etiqueta_valor="Banco",
            valor_grafico="Deudas",
            top=12,
        )
    with colCasa:
        _mostrar_bloque_dimension(
            resumen,
            clave="por_casa_cobro",
            titulo="🤝 Por casa de cobro",
            etiqueta_valor="Casa de Cobro",
            valor_grafico="Deudas",
            top=12,
        )

    _mostrar_bloque_dimension(
        resumen,
        clave="por_rango_descuento",
        titulo="📉 Por rango de Descuento Actual",
        etiqueta_valor="Rango de Descuento",
        valor_grafico="Deudas",
        top=12,
    )

def _mostrar_estados(resumen: dict[str, Any]) -> None:
    """Muestra los estados del Pipeline y las últimas actualizaciones."""
    st.markdown("### 🔄 Estados de las oportunidades")
    st.caption(
        "La población incluye únicamente clientes y deudas con al menos una "
        "oportunidad. La **última actualización** es la etiqueta más reciente "
        "registrada por deuda; **Sin actualización** indica que la deuda no "
        "tiene gestión en Actualizaciones. El **Ingreso Estimado** se reconcilia "
        "con el total; el **Ingreso Potencial** no es aditivo entre estados."
    )

    colPipeline, colActualizacion = st.columns(2)
    with colPipeline:
        st.markdown("#### 🏦 Pipeline de Crédito")
        _mostrar_tabla(
            resumen.get("por_estado_pipeline", pd.DataFrame()),
            columnas_monto=("Ingreso_Estimado", "Ingreso_Potencial"),
            columnas_porcentaje=("Porcentaje_Ingreso",),
            columnas_entero=("Incidencias", "Clientes", "Deudas", "Unidades"),
            renombrar={
                "Valor": "Estado",
                "Incidencias": "Incid.",
                "Ingreso_Estimado": "Ingreso Estimado",
                "Ingreso_Potencial": "Ingreso Potencial",
                "Porcentaje_Ingreso": "% Ingreso",
            },
            alto=320,
        )
        _grafico_barras(
            resumen.get("por_estado_pipeline", pd.DataFrame()),
            categoria="Valor",
            valor="Clientes",
            top=15,
            alto=300,
        )
    with colActualizacion:
        st.markdown("#### 🗂️ Última actualización")
        _mostrar_tabla(
            resumen.get("por_estado_actualizacion", pd.DataFrame()),
            columnas_monto=("Ingreso_Estimado", "Ingreso_Potencial"),
            columnas_porcentaje=("Porcentaje_Ingreso",),
            columnas_entero=("Incidencias", "Clientes", "Deudas", "Unidades"),
            renombrar={
                "Valor": "Última Actualización",
                "Incidencias": "Incid.",
                "Ingreso_Estimado": "Ingreso Estimado",
                "Ingreso_Potencial": "Ingreso Potencial",
                "Porcentaje_Ingreso": "% Ingreso",
            },
            alto=320,
        )
        _grafico_barras(
            resumen.get("por_estado_actualizacion", pd.DataFrame()),
            categoria="Valor",
            valor="Deudas",
            top=15,
            alto=300,
        )

    st.divider()
    st.markdown("#### 🔀 Oportunidades por estado")
    colCrucePipeline, colCruceActualizacion = st.columns(2)
    with colCrucePipeline:
        st.markdown("**Oportunidades × Pipeline de Crédito (clientes)**")
        cruce = resumen.get("cruce_oportunidad_pipeline", pd.DataFrame())
        if cruce is None or cruce.empty:
            st.caption("Sin datos para los filtros seleccionados.")
        else:
            st.dataframe(cruce, hide_index=True, width="stretch")
    with colCruceActualizacion:
        st.markdown("**Oportunidades × Última actualización (deudas)**")
        cruce = resumen.get("cruce_oportunidad_actualizacion", pd.DataFrame())
        if cruce is None or cruce.empty:
            st.caption("Sin datos para los filtros seleccionados.")
        else:
            st.dataframe(cruce, hide_index=True, width="stretch")

def _preparar_detalle_vista(detalle: pd.DataFrame) -> pd.DataFrame:
    """Prepara el detalle de oportunidades para mostrarlo y descargarlo."""
    if detalle is None or detalle.empty:
        return pd.DataFrame()
    columnas = [
        "Referencia",
        "Nombre_Cliente",
        "Negociador",
        "Oportunidad",
        "Tipo_Analisis",
        "Etiqueta_Unidad",
        "Deudas",
        "Prospecto_Credito",
        "Prospecto_Tradicional",
        "Estado_Pipeline",
        "Ingreso_Estimado_Oportunidad",
        "Ingreso_Asignado_Unidad",
        "Es_Maximo_Unidad",
    ]
    disponibles = [columna for columna in columnas if columna in detalle.columns]
    vista = detalle[disponibles].copy()
    if "Deudas" in vista.columns:
        vista["Deudas"] = vista["Deudas"].apply(
            lambda valor: ", ".join(
                str(deuda) for deuda in _normalizar_lista(valor)
            )
        )
    if "Ingreso_Estimado_Oportunidad" in vista.columns:
        vista["Ingreso_Estimado_Oportunidad"] = vista[
            "Ingreso_Estimado_Oportunidad"
        ].apply(_monto_tabla)
    if "Ingreso_Asignado_Unidad" in vista.columns:
        vista["Ingreso_Asignado_Unidad"] = vista[
            "Ingreso_Asignado_Unidad"
        ].apply(_monto_tabla)
    if "Es_Maximo_Unidad" in vista.columns:
        vista["Es_Maximo_Unidad"] = vista["Es_Maximo_Unidad"].apply(
            lambda valor: "✅" if _es_verdadero(valor) else ""
        )
    return vista.rename(columns={
        "Nombre_Cliente": "Cliente",
        "Tipo_Analisis": "Tipo de Análisis",
        "Etiqueta_Unidad": "Unidad",
        "Prospecto_Credito": "Prospecto Crédito",
        "Prospecto_Tradicional": "Prospecto Tradicional",
        "Estado_Pipeline": "Estado Pipeline",
        "Ingreso_Estimado_Oportunidad": "Ingreso Oportunidad",
        "Ingreso_Asignado_Unidad": "Ingreso Máximo Unidad",
        "Es_Maximo_Unidad": "Máx. Unidad",
    })

def _mostrar_detalle(resumen: dict[str, Any]) -> None:
    """Muestra el detalle de oportunidades y las descargas."""
    st.markdown("### 📋 Detalle de oportunidades")
    st.caption(
        "Una fila por unidad/portafolio y oportunidad. **Máx. Unidad** indica "
        "la oportunidad que aporta el Ingreso Estimado de esa unidad."
    )
    detalle = resumen.get("detalle", pd.DataFrame())
    if detalle is None or detalle.empty:
        st.info("No hay oportunidades para los filtros seleccionados.")
        return

    busqueda = st.text_input(
        "**Buscar en el detalle**",
        key=LLAVE_BUSQUEDA_DETALLE,
        placeholder="Referencia, cliente, negociador u oportunidad",
    )
    vista = detalle
    if str(busqueda or "").strip():
        texto = str(busqueda).strip().casefold()
        columnas_busqueda = [
            columna for columna in (
                "Referencia", "Nombre_Cliente", "Negociador", "Oportunidad"
            ) if columna in vista.columns
        ]
        mascara = pd.Series(False, index=vista.index)
        for columna in columnas_busqueda:
            mascara |= vista[columna].astype(str).str.casefold().str.contains(
                texto, na=False, regex=False
            )
        vista = vista[mascara]

    vista_mostrar = _preparar_detalle_vista(vista)
    if vista_mostrar.empty:
        st.caption("No hay filas que coincidan con la búsqueda.")
    else:
        st.dataframe(
            vista_mostrar,
            hide_index=True,
            width="stretch",
            height=ALTO_MAXIMO_DETALLE,
        )

    st.markdown("#### 📥 Descargas")
    st.caption(
        "Las descargas usan las filas visibles después de la búsqueda del detalle."
    )
    colDetalle, colDetalleDeudas, colOportunidad, colNegociador = st.columns(4)
    with colDetalle:
        st.download_button(
            "**Descargar detalle (CSV)**",
            data=_csv_bytes(vista),
            file_name="detalle_oportunidades.csv",
            mime="text/csv",
            width="stretch",
        )
    with colDetalleDeudas:
        st.download_button(
            "**Descargar detalle por deuda (CSV)**",
            data=_csv_bytes(resumen.get("detalle_deudas", pd.DataFrame())),
            file_name="detalle_oportunidades_por_deuda.csv",
            mime="text/csv",
            width="stretch",
        )
    with colOportunidad:
        st.download_button(
            "**Descargar por oportunidad (CSV)**",
            data=_csv_bytes(resumen.get("por_oportunidad", pd.DataFrame())),
            file_name="resumen_por_oportunidad.csv",
            mime="text/csv",
            width="stretch",
        )
    with colNegociador:
        st.download_button(
            "**Descargar por negociador (CSV)**",
            data=_csv_bytes(resumen.get("por_negociador", pd.DataFrame())),
            file_name="resumen_por_negociador.csv",
            mime="text/csv",
            width="stretch",
        )

# --- Bloque de Cálculo ---
def _mostrar_controles_calculo(
    *,
    llave_boton: str,
    expandido: bool = False,
) -> Optional[bool]:
    """Muestra el toggle de fuente y el botón de cálculo.

    Returns:
        Optional[bool]: None si no se presionó calcular, True si el cálculo
        terminó bien y False si falló.
    """
    contenedor = st.expander(
        "🚀 Calcular oportunidades" if expandido else "🔄 Recalcular oportunidades",
        expanded=expandido,
    )
    with contenedor:
        colToggle, colBoton = st.columns(
            [2, 1], vertical_alignment="center"
        )
        with colToggle:
            valor_inicial = st.session_state.get(
                "calc_masiva_solo_masivas_aplicado",
                st.session_state.get("calc_masiva_solo_masivas", True),
            )
            solo_masivas = st.toggle(
                "**Solo de Masivas de Alianzas**",
                value=bool(valor_inicial),
                key="calc_resumen_solo_masivas",
                help=(
                    "Activo: el descuento sale de la Base del Mes de Masivas. "
                    "Inactivo: sale de las Actualizaciones."
                ),
            )
        with colBoton:
            calcular = st.button(
                "**Calcular Oportunidades**",
                type="primary",
                icon="🚀",
                width="stretch",
                key=llave_boton,
            )
        if calcular:
            st.session_state["calc_masiva_solo_masivas"] = bool(solo_masivas)
            if calcular_y_guardar_resultado_masivo(
                solo_masivas=bool(solo_masivas)
            ) is None:
                return False
            return True
    return None

# --- Vista Principal del Resumen ---
def mostrar_calculadora_resumen() -> None:
    """Muestra el panel agregado de oportunidades masivas."""
    st.subheader("📊 Resumen de Oportunidades")
    st.markdown(
        "Vista agregada de las oportunidades de la cartera habilitada para tu "
        "rol. Usa el último cálculo de **Oportunidades Masivas** y comparte sus "
        "filtros. Permite dimensionar oportunidades, clientes, deudas, ingreso "
        "estimado y estados sin recorrer cliente por cliente."
    )

    resultado = st.session_state.get(LLAVE_RESULTADO_MASIVO)
    if not isinstance(resultado, pd.DataFrame) or resultado.empty:
        st.info(
            "Aún no hay un cálculo masivo disponible. Configura la fuente y "
            "presiona **Calcular Oportunidades** para comenzar.",
            icon="ℹ️",
        )
        estado_calculo = _mostrar_controles_calculo(
            llave_boton="calc_resumen_boton_calcular",
            expandido=True,
        )
        if estado_calculo is not True:
            return
        resultado = st.session_state.get(LLAVE_RESULTADO_MASIVO)

    else:
        estado_calculo = _mostrar_controles_calculo(
            llave_boton="calc_resumen_boton_recalcular",
            expandido=False,
        )
        if estado_calculo is False:
            return
        if estado_calculo is True:
            resultado = st.session_state.get(LLAVE_RESULTADO_MASIVO)

    if not isinstance(resultado, pd.DataFrame) or resultado.empty:
        st.warning(
            "No se encontraron Referencias con deudas analizables. Revisa la "
            "Asignación de Cartera o el alcance de Referencias.",
            icon="⚠️",
        )
        return

    if not COLUMNAS_REQUERIDAS_RESUMEN.issubset(set(resultado.columns)):
        st.warning(
            "El resultado guardado pertenece a una versión anterior de la "
            "calculadora. Recalcula para habilitar el resumen por estados, "
            "bancos y casas de cobro.",
            icon="⚠️",
        )
        if st.button(
            "**Recalcular oportunidades**",
            type="primary",
            icon="🚀",
            key="calc_resumen_boton_actualizar",
        ):
            if calcular_y_guardar_resultado_masivo(
                solo_masivas=bool(
                    st.session_state.get(
                        "calc_masiva_solo_masivas_aplicado", True
                    )
                )
            ) is not None:
                st.rerun()
        return

    with st.container(border=True):
        filtros = _mostrar_filtros_masivos(
            resultado,
            prefijo=PREFIJO_FILTROS_RESUMEN,
            incluir_orden=False,
        )

    filtrado = filtrar_oportunidades_masivas(resultado, **filtros)
    fuente = str(
        resultado.get("Fuente_Descuento", pd.Series(["Masivas"])).iloc[0]
    ).strip() or "Masivas"
    st.caption(
        "Mostrando **{:,}** de **{:,}** clientes después de los filtros. "
        "Descuento desde **{}**. Para ver la cobertura sobre toda la cartera, "
        "desactiva **Solo con oportunidades**.".format(
            len(filtrado), len(resultado), fuente
        )
    )
    if filtrado.empty:
        st.warning(
            "No hay clientes que cumplan los filtros seleccionados. Ajusta los "
            "filtros o recalcula.",
            icon="⚠️",
        )
        return

    resumen = calcular_resumen_oportunidades(filtrado)

    tabGeneral, tabDistribuciones, tabEstados, tabDetalle = st.tabs([
        "📊 General",
        "🧩 Distribuciones",
        "🔄 Estados",
        "📋 Detalle y descarga",
    ])

    with tabGeneral:
        _mostrar_resumen_general(resumen)
    with tabDistribuciones:
        _mostrar_distribuciones(resumen)
    with tabEstados:
        _mostrar_estados(resumen)
    with tabDetalle:
        _mostrar_detalle(resumen)

    configs_feedback = {
        "Fuente_Descuento": fuente,
        "Total_Clientes": int(len(resultado)),
        "Clientes_Filtrados": int(len(filtrado)),
        "Clientes_Con_Oportunidad": int(
            resumen.get("kpis", {}).get("Clientes_Con_Oportunidad", 0)
        ),
        "Incidencias": int(
            resumen.get("kpis", {}).get("Incidencias", 0)
        ),
        "Ingreso_Estimado": float(
            resumen.get("kpis", {}).get("Ingreso_Estimado_Total", 0)
        ),
        "Filtros": {
            clave: str(valor)
            if not isinstance(valor, (list, tuple, dict))
            else valor
            for clave, valor in filtros.items()
        },
    }
    mostrar_componente_feedback(
        origin="Calculadora_Resumen_Opps",
        configs=configs_feedback,
        type_container="expander",
    )
