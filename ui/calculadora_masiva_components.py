# Estándar usando PEP8
# Librerías de Python
import math
from typing import Any, Callable, Optional
# Librerías de Terceros
import numpy as np
import pandas as pd
import streamlit as st
# Librerías Locales
from modules.constants import (
    COLORES_OPORTUNIDADES,
    DESCRIPCION_OPORTUNIDADES,
    ICONOS_OPORTUNIDADES,
    LLAVE_REDIRECCION_CALCULADORA,
    OPORTUNIDADES,
)
from modules.oportunidades import (
    calcular_ingreso_estimado_masivo,
    calcular_oportunidades_masivas,
)
from ui.forms_components import mostrar_componente_feedback
from utils.helpers_general import clean_tildes, escapar_dolar_markdown, formatNumber

# --- Configuración de la Vista Masiva ---
OPCION_TODOS = "Todos"
OPCIONES_TIPO_ANALISIS = [
    "Todos",
    "Tradicional",
    "Crédito",
    "Tradicional y Crédito",
]
# Prefijos de las columnas y del detalle por unidad según el tipo de análisis
PREFIJOS_TIPO_ANALISIS = {
    "Tradicional": ("Trad",),
    "Crédito": ("Cred",),
    "Tradicional y Crédito": ("Trad", "Cred"),
}
COLUMNAS_HABILITADO_TIPO = {
    "Trad": "Tradicional_Habilitado",
    "Cred": "Credito_Habilitado",
}
OPORTUNIDADES_CALCULADAS = [
    "Depósito Extra",
    "ContraOferta Viable",
    "Liquidación Instantánea",
]
OPORTUNIDADES_GENERALES = [
    "Acuerdo para Robo",
    "IA Liquidadora",
]
COLUMNAS_APLICA_OPORTUNIDAD = {
    "Trad": {
        "Depósito Extra": "Trad_Deposito_Extra_Aplica",
        "ContraOferta Viable": "Trad_Contraoferta_Aplica",
        "Liquidación Instantánea": "Trad_Liq_Insta_Aplica",
    },
    "Cred": {
        "Depósito Extra": "Cred_Deposito_Extra_Aplica",
        "ContraOferta Viable": "Cred_Contraoferta_Aplica",
        "Liquidación Instantánea": "Cred_Liq_Insta_Aplica",
    },
}
COLUMNAS_APLICA_GENERAL = {
    "Acuerdo para Robo": "Acuerdo_Robo_Aplica",
    "IA Liquidadora": "IA_Liquidadora_Aplica",
}
OPCIONES_ORDEN_MASIVA = [
    "Mayor Ingreso Estimado",
    "Más oportunidades",
    "Mayor Descuento Actual",
    "Mayor DUM",
    "Mayor Ahorro Neto",
    "Referencia (A-Z)",
    "Nombre del Cliente (A-Z)",
]
REGISTROS_POR_PAGINA_MASIVA = [10, 20, 30, 50]
REGISTROS_POR_PAGINA_DEFAULT = 10
LLAVE_RESULTADO_MASIVO = "calc_masiva_resultado"
LLAVE_PAGINA_MASIVA = "calc_masiva_pagina"
LLAVE_PAGINA_INPUT_MASIVA = "calc_masiva_pagina_input"
PREFIJO_FILTROS_MASIVOS = "calc_masiva_filtro_"
PREFIJO_FILTROS_RESUMEN = "calc_resumen_filtro_"
LLAVE_FILTROS_COMPARTIDOS = "calc_opps_filtros_compartidos"
ALTO_MAXIMO_DETALLE_PORTAFOLIOS = 420

# --- Funciones Puras de Paginación y Formato ---
def _normalizar_pagina_actual(valor: Any, total_paginas: int) -> int:
    """Convierte cualquier valor a una página entera válida.

    Streamlit puede dejar en Session State strings o floats si el usuario
    escribe en un input. La paginación siempre debe trabajar con enteros para
    que ``DataFrame.iloc`` no falle.
    """
    total = max(1, int(total_paginas))
    try:
        pagina = int(float(valor))
    except (TypeError, ValueError):
        pagina = 1
    return min(max(pagina, 1), total)

def _calcular_slice_pagina(
    *,
    pagina: int,
    total_registros: int,
    registros_por_pagina: int,
) -> tuple[int, int]:
    """Devuelve el inicio y el fin enteros de la página solicitada."""
    total = max(0, int(total_registros))
    por_pagina = max(1, int(registros_por_pagina))
    pagina = max(1, int(pagina))
    inicio = min((pagina - 1) * por_pagina, total)
    fin = min(inicio + por_pagina, total)
    return int(inicio), int(fin)

def _formatear_monto(valor: Any) -> str:
    """Formatea un monto en COP para mostrarlo en las tarjetas."""
    try:
        monto = float(valor)
    except (TypeError, ValueError):
        monto = 0.0
    if pd.isna(monto):
        monto = 0.0
    return "$ {}".format(formatNumber(monto))

def _md(texto: Any) -> str:
    """Escapa los ``$`` para que Markdown no los trate como LaTeX."""
    return escapar_dolar_markdown(texto)

def _formatear_porcentaje(valor: Any) -> str:
    """Formatea un decimal como porcentaje."""
    try:
        porcentaje = float(valor)
    except (TypeError, ValueError):
        porcentaje = 0.0
    if pd.isna(porcentaje):
        porcentaje = 0.0
    return "{:.1%}".format(porcentaje)

def _formatear_monto_sin_simbolo(valor: Any) -> str:
    """Formatea un monto entero en COP sin símbolo para ahorrar espacio."""
    try:
        monto = float(valor)
    except (TypeError, ValueError):
        monto = 0.0
    if pd.isna(monto):
        monto = 0.0
    return formatNumber(int(round(monto)))

def _formatear_valor_oportunidad_masiva(*, nombre: str, valor: Any) -> str:
    """Formatea el valor de una oportunidad según su tipo de negocio."""
    if nombre == "Depósito Extra":
        return _formatear_monto_sin_simbolo(valor)
    if nombre in {"ContraOferta Viable", "Liquidación Instantánea", "IA Liquidadora"}:
        return _formatear_porcentaje(valor)
    return str(valor)

def _normalizar_lista(valor: Any) -> list[Any]:
    """Convierte un valor de columna lista en una lista segura."""
    if isinstance(valor, (list, tuple, set)):
        return list(valor)
    return []

def _es_verdadero(valor: Any) -> bool:
    """Convierte banderas con posibles NaN a booleano sin tratarlas como True."""
    try:
        if pd.isna(valor):
            return False
    except (TypeError, ValueError):
        pass
    return bool(valor)

def _reiniciar_pagina_masiva() -> None:
    """Callback: vuelve a la primera página cuando cambia un filtro."""
    st.session_state[LLAVE_PAGINA_MASIVA] = 1
    st.session_state.pop(LLAVE_PAGINA_INPUT_MASIVA, None)

def _limpiar_filtros_masivos() -> None:
    """Elimina los filtros y la paginación de un cálculo anterior."""
    for key in list(st.session_state.keys()):
        if key.startswith(PREFIJO_FILTROS_MASIVOS) or key.startswith(
            PREFIJO_FILTROS_RESUMEN
        ):
            del st.session_state[key]
    st.session_state.pop(LLAVE_FILTROS_COMPARTIDOS, None)
    st.session_state.pop(LLAVE_PAGINA_MASIVA, None)
    st.session_state.pop(LLAVE_PAGINA_INPUT_MASIVA, None)

# --- Estado Compartido de Filtros entre las Pestañas Masiva y Resumen ---
def _clave_filtro(prefijo: str, nombre: str) -> str:
    """Devuelve la clave de Session State de un filtro."""
    return "{}{}".format(prefijo, nombre)

def _filtros_compartidos() -> dict[str, Any]:
    """Recupera el diccionario de filtros compartidos."""
    valor = st.session_state.get(LLAVE_FILTROS_COMPARTIDOS, {})
    return valor if isinstance(valor, dict) else {}

def _valor_filtro_compartido(nombre: str, default: Any) -> Any:
    """Recupera un filtro compartido o su valor por defecto."""
    return _filtros_compartidos().get(nombre, default)

def _preparar_texto(
    *, prefijo: str, nombre: str, default: str
) -> tuple[str, Optional[str]]:
    """Devuelve la clave y el valor inicial de un text_input."""
    clave = _clave_filtro(prefijo, nombre)
    if clave in st.session_state:
        return clave, None
    valor = _valor_filtro_compartido(nombre, default)
    return clave, str(valor) if valor is not None else default

def _preparar_selectbox(
    *, prefijo: str, nombre: str, opciones: list[str], default: str
) -> tuple[str, Optional[int]]:
    """Devuelve la clave y el índice inicial de un selectbox."""
    clave = _clave_filtro(prefijo, nombre)
    if clave in st.session_state:
        return clave, None
    valor = _valor_filtro_compartido(nombre, default)
    if valor not in opciones:
        valor = default
    return clave, opciones.index(valor)

def _preparar_multiselect(
    *, prefijo: str, nombre: str, opciones: list[str], default: list[str]
) -> tuple[str, Optional[list[str]]]:
    """Devuelve la clave y la selección inicial de un multiselect."""
    clave = _clave_filtro(prefijo, nombre)
    if clave in st.session_state:
        return clave, None
    valor = _valor_filtro_compartido(nombre, default)
    if not isinstance(valor, (list, tuple, set)):
        valor = default
    seleccion = [opcion for opcion in valor if opcion in opciones]
    if valor and not seleccion:
        # Si ninguna de las opciones guardadas sigue vigente, volvemos a todas.
        seleccion = list(default)
    return clave, seleccion

def _preparar_rango(
    *,
    prefijo: str,
    nombre: str,
    minimo: float,
    maximo: float,
    default: tuple[float, float],
    cast_int: bool = False,
) -> tuple[str, Optional[tuple[float, float]]]:
    """Devuelve la clave y el rango inicial de un slider."""
    clave = _clave_filtro(prefijo, nombre)
    if clave in st.session_state:
        return clave, None
    valor = _valor_filtro_compartido(nombre, default)
    try:
        if not isinstance(valor, (list, tuple)) or len(valor) != 2:
            raise ValueError
        inferior = min(max(float(valor[0]), float(minimo)), float(maximo))
        superior = min(max(float(valor[1]), float(minimo)), float(maximo))
        if inferior > superior:
            inferior, superior = superior, inferior
        if cast_int:
            inferior, superior = int(round(inferior)), int(round(superior))
        return clave, (inferior, superior)
    except (TypeError, ValueError):
        return clave, default

def _preparar_bool(
    *, prefijo: str, nombre: str, default: bool
) -> tuple[str, Optional[bool]]:
    """Devuelve la clave y el valor inicial de un checkbox o toggle."""
    clave = _clave_filtro(prefijo, nombre)
    if clave in st.session_state:
        return clave, None
    return clave, bool(_valor_filtro_compartido(nombre, default))

def _opciones_lista(df: pd.DataFrame, columna: str) -> list[str]:
    """Extrae las opciones únicas de una columna que contiene listas."""
    if columna not in df.columns:
        return []
    valores = set()
    for lista in df[columna].dropna():
        if isinstance(lista, (list, tuple, set)):
            for valor in lista:
                texto = str(valor).strip()
                if texto:
                    valores.add(texto)
        else:
            texto = str(lista).strip()
            if texto:
                valores.add(texto)
    return sorted(valores)

# --- Filtros de Tipo de Análisis ---
def _nombres_oportunidades_de_tipo(portafolios: Any, prefijo: str) -> set[str]:
    """Devuelve las oportunidades presentes en el bloque de un tipo.

    Args:
        portafolios (Any): Detalle de portafolios/unidades del cliente.
        prefijo (str): ``Trad`` para Tradicional o ``Cred`` para Crédito.

    Returns:
        set[str]: Nombres de las oportunidades aplicables en ese bloque.
    """
    clave = "{}_Oportunidades".format(prefijo)
    nombres: set[str] = set()
    for portafolio in _normalizar_lista(portafolios):
        if not isinstance(portafolio, dict):
            continue
        for oportunidad in _normalizar_lista(portafolio.get(clave, [])):
            if isinstance(oportunidad, dict):
                nombre = str(oportunidad.get("nombre") or "").strip()
            else:
                nombre = str(oportunidad or "").strip()
            if nombre:
                nombres.add(nombre)
    return nombres

def _mascara_oportunidades_de_tipo(
    df: pd.DataFrame,
    *,
    prefijo: str,
    requeridas: list[str],
) -> pd.Series:
    """Construye la máscara de oportunidades de un bloque de análisis.

    Cuando hay oportunidades calculadas seleccionadas se exige al menos una de
    ellas en el bloque. Si no hay ninguna seleccionada, basta con que exista
    cualquier oportunidad calculada del tipo. El detalle por unidad se usa para
    que el filtro coincida con las tarjetas; si no está disponible, se usan las
    banderas agregadas del cliente como respaldo.
    """
    requeridas_tipo = [
        nombre for nombre in requeridas if nombre in OPORTUNIDADES_CALCULADAS
    ]
    nombres_buscados = requeridas_tipo or OPORTUNIDADES_CALCULADAS

    if "Portafolios_Detalle" in df.columns:
        nombres_set = set(nombres_buscados)
        return df["Portafolios_Detalle"].apply(
            lambda portafolios: bool(
                _nombres_oportunidades_de_tipo(portafolios, prefijo) & nombres_set
            )
        ).astype(bool)

    columnas_evaluar = [
        COLUMNAS_APLICA_OPORTUNIDAD[prefijo][nombre]
        for nombre in nombres_buscados
        if COLUMNAS_APLICA_OPORTUNIDAD[prefijo][nombre] in df.columns
    ]
    mascara = pd.Series(False, index=df.index)
    for columna in columnas_evaluar:
        mascara |= df[columna].fillna(False).astype(bool)
    return mascara

def _mascara_oportunidades_generales(
    df: pd.DataFrame,
    seleccionadas: list[str],
) -> pd.Series:
    """Construye la máscara de oportunidades generales seleccionadas."""
    mascara = pd.Series(False, index=df.index)
    for nombre in seleccionadas:
        columna = COLUMNAS_APLICA_GENERAL.get(nombre)
        if columna and columna in df.columns:
            mascara |= df[columna].fillna(False).astype(bool)
    return mascara

def _mascara_lista(
    df: pd.DataFrame,
    columna: str,
    valores: list[str],
) -> pd.Series:
    """Marca los clientes que tienen al menos un valor de la lista."""
    if columna not in df.columns:
        return pd.Series(True, index=df.index)
    valores_set = set(valores)
    return df[columna].apply(
        lambda lista: bool(set(_normalizar_lista(lista)) & valores_set)
    )

# --- Filtros de Oportunidades Masivas ---
def filtrar_oportunidades_masivas(
    df: pd.DataFrame,
    *,
    busqueda: str = "",
    negociadores: Optional[list[str]] = None,
    prospectos: Optional[list[str]] = None,
    prospectos_tradicionales: Optional[list[str]] = None,
    estados_actualizacion: Optional[list[str]] = None,
    estados_pipeline: Optional[list[str]] = None,
    bancos: Optional[list[str]] = None,
    casas_cobro: Optional[list[str]] = None,
    tipo_analisis: str = OPCION_TODOS,
    oportunidades: Optional[list[str]] = None,
    solo_con_oportunidades: bool = True,
    solo_viables: bool = False,
    descuento_min: float = 0.0,
    descuento_max: float = 1.0,
    dum_min: Optional[float] = None,
    dum_max: Optional[float] = None,
    excluir_clientes_con_liquidaciones: bool = False,
    orden: str = "Mayor Ingreso Estimado",
    invertir_orden: bool = False,
) -> pd.DataFrame:
    """Aplica los filtros de la vista masiva sin tocar widgets de Streamlit.

    Args:
        df (pd.DataFrame): Resultado de ``calcular_oportunidades_masivas``.
        busqueda (str): Texto a buscar en Referencia o Nombre_Cliente.
        negociadores (Optional[list[str]]): Negociadores seleccionados.
        prospectos (Optional[list[str]]): Prospectos de Crédito seleccionados.
        prospectos_tradicionales (Optional[list[str]]): Prospectos de
            Tradicional seleccionados.
        estados_actualizacion (Optional[list[str]]): Últimas etiquetas de
            actualización que debe tener al menos una deuda del cliente.
        estados_pipeline (Optional[list[str]]): Estados del Pipeline de Crédito
            seleccionados. El valor vacío se trata como "Sin registro en Pipeline".
        bancos (Optional[list[str]]): Bancos que debe tener al menos una deuda.
        casas_cobro (Optional[list[str]]): Casas de cobro que debe tener al
            menos una deuda.
        tipo_analisis (str): Tradicional, Crédito, ambos o Todos. Con
            ``solo_con_oportunidades`` activo se combina con las oportunidades
            para exigir que existan en el bloque del tipo elegido; sin
            oportunidades seleccionadas exige al menos una oportunidad del tipo.
            Con ``solo_con_oportunidades`` inactivo mantiene el filtro de
            viabilidad del análisis (Tradicional_Habilitado/Credito_Habilitado).
        oportunidades (Optional[list[str]]): Oportunidades que debe tener el cliente.
        solo_con_oportunidades (bool): Si True, exige Num_Oportunidades > 0 y
            cambia el significado de ``tipo_analisis`` al de resultado por tipo.
        solo_viables (bool): Si True, exige Es_Viable.
        descuento_min (float): Descuento Actual mínimo (0-1).
        descuento_max (float): Descuento Actual máximo (0-1).
        dum_min (Optional[float]): DUM total mínimo.
        dum_max (Optional[float]): DUM total máximo.
        excluir_clientes_con_liquidaciones (bool): Oculta clientes con deudas liquidadas.
        orden (str): Criterio de ordenamiento.
        invertir_orden (bool): Si True, invierte el orden natural del criterio.

    Returns:
        pd.DataFrame: DataFrame filtrado y ordenado.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    resultado = df.copy()

    # Paso 1: Búsqueda por Referencia o Nombre del Cliente
    texto = str(busqueda or "").strip().casefold()
    if texto:
        mask_referencia = resultado["Referencia"].astype(str).str.casefold().str.contains(
            texto, na=False, regex=False
        )
        mask_nombre = resultado["Nombre_Cliente"].astype(str).str.casefold().str.contains(
            texto, na=False, regex=False
        )
        resultado = resultado[mask_referencia | mask_nombre]

    # Paso 2: Filtros Categóricos
    if negociadores:
        negociadores_validos = [n for n in negociadores if str(n).strip()]
        if negociadores_validos and OPCION_TODOS not in negociadores_validos:
            resultado = resultado[resultado["Negociador"].isin(negociadores_validos)]

    if prospectos:
        prospectos_validos = [p for p in prospectos if str(p).strip()]
        if prospectos_validos:
            resultado = resultado[resultado["Prospecto_Credito"].isin(prospectos_validos)]

    if prospectos_tradicionales:
        tradicionales_validos = [
            p for p in prospectos_tradicionales if str(p).strip()
        ]
        if (
            tradicionales_validos
            and "Prospecto_Tradicional" in resultado.columns
        ):
            resultado = resultado[
                resultado["Prospecto_Tradicional"].isin(tradicionales_validos)
            ]

    if estados_pipeline:
        estados_validos = [e for e in estados_pipeline if str(e).strip()]
        if estados_validos and "Estado_Credito" in resultado.columns:
            estado = (
                resultado["Estado_Credito"]
                .fillna("")
                .astype(str)
                .str.strip()
            )
            estado = estado.where(
                estado.ne(""), "Sin registro en Pipeline"
            )
            resultado = resultado[estado.isin(estados_validos)]

    if estados_actualizacion:
        estados_validos = [
            e for e in estados_actualizacion if str(e).strip()
        ]
        if estados_validos:
            resultado = resultado[
                _mascara_lista(
                    resultado, "Estados_Actualizacion", estados_validos
                )
            ]

    if bancos:
        bancos_validos = [b for b in bancos if str(b).strip()]
        if bancos_validos:
            resultado = resultado[
                _mascara_lista(resultado, "Bancos", bancos_validos)
            ]

    if casas_cobro:
        casas_validas = [c for c in casas_cobro if str(c).strip()]
        if casas_validas:
            resultado = resultado[
                _mascara_lista(resultado, "Casas_Cobro", casas_validas)
            ]

    # Paso 3: Oportunidades Seleccionadas
    seleccionadas = [o for o in (oportunidades or []) if o in OPORTUNIDADES]
    prefijos_tipo = PREFIJOS_TIPO_ANALISIS.get(str(tipo_analisis).strip(), ())

    # Paso 4: Tipo de Análisis
    if prefijos_tipo:
        if solo_con_oportunidades:
            # El tipo de análisis filtra por resultado: la oportunidad debe
            # existir en el bloque Tradicional y/o Crédito de la unidad.
            for prefijo in prefijos_tipo:
                resultado = resultado[
                    _mascara_oportunidades_de_tipo(
                        resultado,
                        prefijo=prefijo,
                        requeridas=seleccionadas,
                    )
                ]
        else:
            # Sin "Solo con oportunidades" se mantiene el filtro de viabilidad
            # del análisis: el tipo debe estar habilitado para el cliente.
            mascara_habilitado = pd.Series(True, index=resultado.index)
            for prefijo in prefijos_tipo:
                columna = COLUMNAS_HABILITADO_TIPO[prefijo]
                mascara_habilitado &= resultado[columna].astype(bool)
            resultado = resultado[mascara_habilitado]

    # Paso 5: Oportunidades Seleccionadas
    if seleccionadas:
        if prefijos_tipo and solo_con_oportunidades:
            # Las oportunidades calculadas ya se filtraron por bloque. Las
            # generales (Robo/IA) se exigen además y no pertenecen a un tipo.
            generales = [
                nombre for nombre in seleccionadas
                if nombre in OPORTUNIDADES_GENERALES
            ]
            if generales:
                resultado = resultado[
                    _mascara_oportunidades_generales(resultado, generales)
                ]
        else:
            resultado = resultado[
                resultado["Oportunidades"].apply(
                    lambda ops: any(o in _normalizar_lista(ops) for o in seleccionadas)
                )
            ]

    # Paso 6: Filtros Booleanos y Numéricos
    if solo_con_oportunidades:
        resultado = resultado[
            pd.to_numeric(resultado["Num_Oportunidades"], errors="coerce").fillna(0) > 0
        ]
    if solo_viables:
        resultado = resultado[resultado["Es_Viable"].astype(bool)]

    descuento = pd.to_numeric(resultado["Descuento_Actual"], errors="coerce").fillna(0.0)
    descuento_min = min(max(float(descuento_min), 0.0), 1.0)
    descuento_max = min(max(float(descuento_max), 0.0), 1.0)
    if descuento_min > descuento_max:
        descuento_min, descuento_max = descuento_max, descuento_min
    resultado = resultado[descuento.between(descuento_min, descuento_max, inclusive="both")]

    dum = pd.to_numeric(resultado["PaB_Origen_Total"], errors="coerce").fillna(0.0)
    if dum_min is not None:
        resultado = resultado[dum >= float(dum_min)]
        dum = pd.to_numeric(resultado["PaB_Origen_Total"], errors="coerce").fillna(0.0)
    if dum_max is not None:
        resultado = resultado[dum <= float(dum_max)]

    if excluir_clientes_con_liquidaciones:
        resultado = resultado[~resultado["Tiene_Deudas_Liquidaciones"].astype(bool)]

    # Recalculamos el Ingreso Estimado con los filtros vigentes. El máximo se
    # toma por unidad/oportunidad y no sobre todas las deudas del cliente.
    resultado = calcular_ingreso_estimado_masivo(
        resultado,
        tipo_analisis=tipo_analisis,
        oportunidades=seleccionadas,
    )

    # Paso 7: Ordenamiento
    if resultado.empty:
        return resultado.reset_index(drop=True)

    if "Ingreso_Estimado" not in resultado.columns:
        resultado["Ingreso_Estimado"] = 0.0

    if orden == "Mayor Ingreso Estimado":
        columnas_orden = ["Ingreso_Estimado", "Num_Oportunidades", "Referencia"]
        ascendente = [False, False, True]
    elif orden == "Mayor Descuento Actual":
        columnas_orden = ["Descuento_Actual", "Num_Oportunidades", "Referencia"]
        ascendente = [False, False, True]
    elif orden == "Mayor DUM":
        columnas_orden = ["PaB_Origen_Total", "Num_Oportunidades", "Referencia"]
        ascendente = [False, False, True]
    elif orden == "Mayor Ahorro Neto":
        columnas_orden = ["Ahorro_Neto", "Num_Oportunidades", "Referencia"]
        ascendente = [False, False, True]
    elif orden == "Referencia (A-Z)":
        columnas_orden = ["Referencia"]
        ascendente = [True]
    elif orden == "Nombre del Cliente (A-Z)":
        columnas_orden = ["Nombre_Cliente", "Referencia"]
        ascendente = [True, True]
    else:
        columnas_orden = ["Num_Oportunidades", "Descuento_Actual", "Referencia"]
        ascendente = [False, False, True]

    if invertir_orden:
        ascendente = [not valor for valor in ascendente]

    return resultado.sort_values(
        by=columnas_orden, ascending=ascendente, na_position="last"
    ).reset_index(drop=True)

# --- Render de Filtros ---
def _mostrar_filtros_masivos(
    df: pd.DataFrame,
    *,
    prefijo: str = PREFIJO_FILTROS_MASIVOS,
    incluir_orden: bool = True,
    on_change: Optional[Callable[[], None]] = None,
) -> dict[str, Any]:
    """Renderiza los filtros compartidos y devuelve sus valores actuales.

    Los filtros se comparten entre la pestaña masiva y la de resumen. Cada
    pestaña usa su propio prefijo de widgets, pero los valores se sincronizan
    en ``LLAVE_FILTROS_COMPARTIDOS`` para que cambiar de pestaña no los pierda.
    """
    negociadores = sorted(
        df["Negociador"].dropna().astype(str)
        .replace("", "Sin Negociador Asignado").unique().tolist()
    )
    prospectos = sorted(
        df["Prospecto_Credito"].dropna().astype(str).unique().tolist()
    )
    if "Prospecto_Tradicional" in df.columns:
        prospectos_tradicionales = sorted(
            df["Prospecto_Tradicional"].dropna().astype(str).str.strip()
            .replace("", "N/A").unique().tolist()
        )
    else:
        prospectos_tradicionales = []
    if "Estado_Credito" in df.columns:
        estados_pipeline = sorted(
            df["Estado_Credito"].fillna("").astype(str).str.strip()
            .replace("", "Sin registro en Pipeline").unique().tolist()
        )
    else:
        estados_pipeline = []
    estados_actualizacion = _opciones_lista(df, "Estados_Actualizacion")
    bancos = _opciones_lista(df, "Bancos")
    casas_cobro = _opciones_lista(df, "Casas_Cobro")

    if "PaB_Origen_Total" in df.columns:
        dum_valores = pd.to_numeric(
            df["PaB_Origen_Total"], errors="coerce"
        ).dropna()
    else:
        dum_valores = pd.Series(dtype=float)
    dum_min = int(np.floor(dum_valores.min())) if not dum_valores.empty else 0
    dum_max = int(np.ceil(dum_valores.max())) if not dum_valores.empty else 1
    if dum_max <= dum_min:
        dum_max = dum_min + 1
    dum_paso = max(1, int((dum_max - dum_min) / 100))

    st.markdown("### 🔎 Filtros de Oportunidades")
    colBusqueda, colNegociador, colProspecto, colProspectoTrad = st.columns(
        [2, 1.3, 1.5, 1.5]
    )
    with colBusqueda:
        clave, valor_inicial = _preparar_texto(
            prefijo=prefijo, nombre="busqueda", default=""
        )
        opciones_busqueda: dict[str, Any] = {
            "key": clave,
            "placeholder": "Ej. REF-123 o Nombre",
            "on_change": on_change,
        }
        if valor_inicial is not None:
            opciones_busqueda["value"] = valor_inicial
        busqueda = st.text_input(
            "**Buscar Referencia o Cliente**", **opciones_busqueda
        )
    with colNegociador:
        clave, indice_inicial = _preparar_selectbox(
            prefijo=prefijo,
            nombre="negociador",
            opciones=[OPCION_TODOS] + negociadores,
            default=OPCION_TODOS,
        )
        opciones_negociador: dict[str, Any] = {
            "options": [OPCION_TODOS] + negociadores,
            "key": clave,
            "on_change": on_change,
        }
        if indice_inicial is not None:
            opciones_negociador["index"] = indice_inicial
        negociador = st.selectbox("**Negociador**", **opciones_negociador)
    with colProspecto:
        clave, seleccion_inicial = _preparar_multiselect(
            prefijo=prefijo,
            nombre="prospecto",
            opciones=prospectos,
            default=prospectos,
        )
        opciones_prospecto: dict[str, Any] = {
            "options": prospectos,
            "key": clave,
            "on_change": on_change,
        }
        if seleccion_inicial is not None:
            opciones_prospecto["default"] = seleccion_inicial
        prospectos_sel = st.multiselect(
            "**Prospecto de Crédito**", **opciones_prospecto
        )
    with colProspectoTrad:
        clave, seleccion_inicial = _preparar_multiselect(
            prefijo=prefijo,
            nombre="prospecto_tradicional",
            opciones=prospectos_tradicionales,
            default=prospectos_tradicionales,
        )
        opciones_prospecto_trad: dict[str, Any] = {
            "options": prospectos_tradicionales,
            "key": clave,
            "on_change": on_change,
        }
        if seleccion_inicial is not None:
            opciones_prospecto_trad["default"] = seleccion_inicial
        prospectos_trad_sel = st.multiselect(
            "**Prospecto de Tradicional**", **opciones_prospecto_trad
        )

    colTipo, colOportunidad, colEstadoPipe, colEstadoAct = st.columns(
        [1.3, 1.8, 1.4, 1.4]
    )
    with colTipo:
        clave, indice_inicial = _preparar_selectbox(
            prefijo=prefijo,
            nombre="tipo_analisis",
            opciones=OPCIONES_TIPO_ANALISIS,
            default=OPCION_TODOS,
        )
        opciones_tipo: dict[str, Any] = {
            "options": OPCIONES_TIPO_ANALISIS,
            "key": clave,
            "help": (
                "Con 'Solo con oportunidades' activo se combina con la "
                "Oportunidad: muestra los clientes que la tienen por el tipo "
                "elegido. Sin oportunidad elegida, exige al menos una "
                "oportunidad de ese tipo. Si desactivas 'Solo con "
                "oportunidades', filtra por viabilidad del análisis. El "
                "Ingreso Estimado se calcula solo con las oportunidades de "
                "este tipo."
            ),
            "on_change": on_change,
        }
        if indice_inicial is not None:
            opciones_tipo["index"] = indice_inicial
        tipo_analisis = st.selectbox(
            "**Tipo de Análisis**", **opciones_tipo
        )
    with colOportunidad:
        clave, seleccion_inicial = _preparar_multiselect(
            prefijo=prefijo,
            nombre="oportunidad",
            opciones=OPORTUNIDADES,
            default=[],
        )
        opciones_oportunidad: dict[str, Any] = {
            "options": OPORTUNIDADES,
            "key": clave,
            "help": (
                "Sin selección se muestran todas las oportunidades. Al "
                "combinar con un Tipo de Análisis, la oportunidad debe existir "
                "en el bloque Tradicional o Crédito elegido. El Ingreso "
                "Estimado se calcula con las oportunidades seleccionadas."
            ),
            "on_change": on_change,
        }
        if seleccion_inicial is not None:
            opciones_oportunidad["default"] = seleccion_inicial
        oportunidades = st.multiselect(
            "**Oportunidad**", **opciones_oportunidad
        )
    with colEstadoPipe:
        clave, seleccion_inicial = _preparar_multiselect(
            prefijo=prefijo,
            nombre="estado_pipeline",
            opciones=estados_pipeline,
            default=estados_pipeline,
        )
        opciones_estado_pipe: dict[str, Any] = {
            "options": estados_pipeline,
            "key": clave,
            "on_change": on_change,
        }
        if seleccion_inicial is not None:
            opciones_estado_pipe["default"] = seleccion_inicial
        estados_pipeline_sel = st.multiselect(
            "**Estado del Pipeline**", **opciones_estado_pipe
        )
    with colEstadoAct:
        clave, seleccion_inicial = _preparar_multiselect(
            prefijo=prefijo,
            nombre="estado_actualizacion",
            opciones=estados_actualizacion,
            default=estados_actualizacion,
        )
        opciones_estado_act: dict[str, Any] = {
            "options": estados_actualizacion,
            "key": clave,
            "on_change": on_change,
        }
        if seleccion_inicial is not None:
            opciones_estado_act["default"] = seleccion_inicial
        estados_actualizacion_sel = st.multiselect(
            "**Última Actualización**", **opciones_estado_act
        )

    colBanco, colCasa, colDescuento, colDum = st.columns([1.5, 1.5, 2, 2])
    with colBanco:
        clave, seleccion_inicial = _preparar_multiselect(
            prefijo=prefijo,
            nombre="banco",
            opciones=bancos,
            default=bancos,
        )
        opciones_banco: dict[str, Any] = {
            "options": bancos,
            "key": clave,
            "on_change": on_change,
        }
        if seleccion_inicial is not None:
            opciones_banco["default"] = seleccion_inicial
        bancos_sel = st.multiselect("**Banco**", **opciones_banco)
    with colCasa:
        clave, seleccion_inicial = _preparar_multiselect(
            prefijo=prefijo,
            nombre="casa_cobro",
            opciones=casas_cobro,
            default=casas_cobro,
        )
        opciones_casa: dict[str, Any] = {
            "options": casas_cobro,
            "key": clave,
            "on_change": on_change,
        }
        if seleccion_inicial is not None:
            opciones_casa["default"] = seleccion_inicial
        casas_sel = st.multiselect(
            "**Casa de Cobro**", **opciones_casa
        )
    with colDescuento:
        clave, valor_inicial = _preparar_rango(
            prefijo=prefijo,
            nombre="descuento",
            minimo=0.0,
            maximo=100.0,
            default=(0.0, 100.0),
        )
        opciones_descuento: dict[str, Any] = {
            "min_value": 0.0,
            "max_value": 100.0,
            "step": 0.5,
            "key": clave,
            "on_change": on_change,
        }
        if valor_inicial is not None:
            opciones_descuento["value"] = valor_inicial
        descuento_min, descuento_max = st.slider(
            "**Descuento Actual (%)**", **opciones_descuento
        )
    with colDum:
        clave, valor_inicial = _preparar_rango(
            prefijo=prefijo,
            nombre="dum",
            minimo=float(dum_min),
            maximo=float(dum_max),
            default=(float(dum_min), float(dum_max)),
            cast_int=True,
        )
        opciones_dum: dict[str, Any] = {
            "min_value": int(dum_min),
            "max_value": int(dum_max),
            "step": int(dum_paso),
            "key": clave,
            "on_change": on_change,
        }
        if valor_inicial is not None:
            opciones_dum["value"] = valor_inicial
        dum_rango = st.slider(
            "**DUM Total (COP)**", **opciones_dum
        )

    colSoloOportunidades, colSoloViables, colExcluirLiquidados, colEspacio = (
        st.columns([1.3, 1, 1.5, 2.2])
    )
    with colSoloOportunidades:
        clave, valor_inicial = _preparar_bool(
            prefijo=prefijo,
            nombre="solo_oportunidades",
            default=True,
        )
        opciones_solo_oportunidades: dict[str, Any] = {
            "key": clave,
            "help": (
                "Si está activo, el Tipo de Análisis filtra por las "
                "oportunidades del bloque Tradicional o Crédito. Si lo "
                "desactivas, el Tipo de Análisis vuelve a filtrar por "
                "viabilidad del análisis."
            ),
            "on_change": on_change,
        }
        if valor_inicial is not None:
            opciones_solo_oportunidades["value"] = valor_inicial
        solo_con_oportunidades = st.checkbox(
            "**Solo con oportunidades**", **opciones_solo_oportunidades
        )
    with colSoloViables:
        clave, valor_inicial = _preparar_bool(
            prefijo=prefijo,
            nombre="solo_viables",
            default=False,
        )
        opciones_solo_viables: dict[str, Any] = {
            "key": clave,
            "on_change": on_change,
        }
        if valor_inicial is not None:
            opciones_solo_viables["value"] = valor_inicial
        solo_viables = st.checkbox(
            "**Solo viables**", **opciones_solo_viables
        )
    with colExcluirLiquidados:
        clave, valor_inicial = _preparar_bool(
            prefijo=prefijo,
            nombre="excluir_liquidados",
            default=False,
        )
        opciones_excluir: dict[str, Any] = {
            "key": clave,
            "on_change": on_change,
        }
        if valor_inicial is not None:
            opciones_excluir["value"] = valor_inicial
        excluir_liquidados = st.checkbox(
            "**Excluir clientes con deudas liquidadas**", **opciones_excluir
        )

    if incluir_orden:
        colOrden, colInvertir, colEspacioOrden = st.columns([1.5, 1, 2.5])
        with colOrden:
            clave, indice_inicial = _preparar_selectbox(
                prefijo=prefijo,
                nombre="orden",
                opciones=OPCIONES_ORDEN_MASIVA,
                default=OPCIONES_ORDEN_MASIVA[0],
            )
            opciones_orden: dict[str, Any] = {
                "options": OPCIONES_ORDEN_MASIVA,
                "key": clave,
                "on_change": on_change,
            }
            if indice_inicial is not None:
                opciones_orden["index"] = indice_inicial
            orden = st.selectbox("**Ordenar por**", **opciones_orden)
        with colInvertir:
            clave, valor_inicial = _preparar_bool(
                prefijo=prefijo,
                nombre="invertir_orden",
                default=False,
            )
            opciones_invertir: dict[str, Any] = {
                "key": clave,
                "help": (
                    "Cada criterio conserva su orden natural: los montos de "
                    "mayor a menor y las Referencias de A a Z. Actívalo para "
                    "invertirlo."
                ),
                "on_change": on_change,
            }
            if valor_inicial is not None:
                opciones_invertir["value"] = valor_inicial
            invertir_orden = st.toggle(
                "**Invertir orden**", **opciones_invertir
            )
    else:
        compartidos = _filtros_compartidos()
        orden = compartidos.get("orden", OPCIONES_ORDEN_MASIVA[0])
        if orden not in OPCIONES_ORDEN_MASIVA:
            orden = OPCIONES_ORDEN_MASIVA[0]
        invertir_orden = bool(compartidos.get("invertir_orden", False))

    # Guardamos los valores para que la otra pestaña los recupere
    st.session_state[LLAVE_FILTROS_COMPARTIDOS] = {
        "busqueda": busqueda,
        "negociador": negociador,
        "prospecto": prospectos_sel,
        "prospecto_tradicional": prospectos_trad_sel,
        "tipo_analisis": tipo_analisis,
        "oportunidad": oportunidades,
        "estado_pipeline": estados_pipeline_sel,
        "estado_actualizacion": estados_actualizacion_sel,
        "banco": bancos_sel,
        "casa_cobro": casas_sel,
        "orden": orden,
        "invertir_orden": invertir_orden,
        "descuento": (descuento_min, descuento_max),
        "dum": (dum_rango[0], dum_rango[1]),
        "solo_oportunidades": solo_con_oportunidades,
        "solo_viables": solo_viables,
        "excluir_liquidados": excluir_liquidados,
    }

    return {
        "busqueda": busqueda,
        "negociadores": [negociador] if negociador != OPCION_TODOS else [],
        "prospectos": prospectos_sel,
        "prospectos_tradicionales": prospectos_trad_sel,
        "estados_pipeline": estados_pipeline_sel,
        "estados_actualizacion": estados_actualizacion_sel,
        "bancos": bancos_sel,
        "casas_cobro": casas_sel,
        "tipo_analisis": tipo_analisis,
        "oportunidades": oportunidades,
        "solo_con_oportunidades": solo_con_oportunidades,
        "solo_viables": solo_viables,
        "descuento_min": float(descuento_min) / 100.0,
        "descuento_max": float(descuento_max) / 100.0,
        "dum_min": float(dum_rango[0]),
        "dum_max": float(dum_rango[1]),
        "excluir_clientes_con_liquidaciones": excluir_liquidados,
        "orden": orden,
        "invertir_orden": invertir_orden,
    }

# --- Render de Tarjetas ---
def _oportunidades_de_bloque(
    *,
    fila: pd.Series,
    prefijo: str,
    nombres: list[str],
) -> list[tuple[str, Any, str]]:
    """Construye las oportunidades aplicables de un bloque Tradicional o Crédito."""
    configuracion = {
        "Depósito Extra": {
            "aplica": "{}_Deposito_Extra_Aplica",
            "valor": "{}_Deposito_Extra_Valor",
            "detalle": "{}_Deposito_Extra_Detalle",
        },
        "ContraOferta Viable": {
            "aplica": "{}_Contraoferta_Aplica",
            "valor": "{}_Contraoferta_Valor",
            "detalle": "{}_Contraoferta_Detalle",
        },
        "Liquidación Instantánea": {
            "aplica": "{}_Liq_Insta_Aplica",
            "valor": "{}_Descuento_Actual",
            "detalle": "{}_Liq_Insta_Detalle",
        },
    }
    resultado = []
    for nombre in nombres:
        config = configuracion[nombre]
        if not _es_verdadero(fila.get(config["aplica"].format(prefijo), False)):
            continue
        resultado.append((
            nombre,
            fila.get(config["valor"].format(prefijo), 0.0),
            str(fila.get(config["detalle"].format(prefijo), "")),
        ))
    return resultado

def _mostrar_badges_deudas(*, deudas: Any) -> None:
    """Muestra los Ids de Deuda como badges dentro de un contenedor horizontal."""
    deudas_limpias = [
        str(deuda).replace(".0", "").strip()
        for deuda in _normalizar_lista(deudas)
        if str(deuda).replace(".0", "").strip()
    ]
    if not deudas_limpias:
        st.caption("Sin deudas")
        return
    with st.container(horizontal=True):
        for deuda in deudas_limpias:
            st.badge(deuda, icon="🆔", color="gray")

def _formatear_valor_oportunidad_unidad(*, nombre: str, valor: Any) -> str:
    """Formatea el valor de una oportunidad para las filas por unidad."""
    return _formatear_valor_oportunidad_masiva(nombre=nombre, valor=valor)

def _mostrar_ingreso_oportunidad(oportunidad: dict[str, Any]) -> None:
    """Muestra el ingreso estimado de una oportunidad y resalta el máximo.

    Se usa en la columna de la oportunidad para que el negociador vea cuánto
    aporta cada unidad/oportunidad y cuál define el Ingreso Estimado del
    cliente.
    """
    if "ingreso_estimado" not in oportunidad:
        return
    try:
        ingreso = float(oportunidad.get("ingreso_estimado"))
    except (TypeError, ValueError):
        return
    if pd.isna(ingreso):
        return
    texto = _md(_formatear_monto(ingreso))
    if _es_verdadero(oportunidad.get("es_ingreso_estimado_maximo")):
        st.markdown("💸 **{}** :green[**MÁXIMO**]".format(texto))
    else:
        st.caption("💸 {}".format(texto))
    if (
        "incluida_en_ingreso_estimado" in oportunidad
        and not _es_verdadero(oportunidad.get("incluida_en_ingreso_estimado"))
    ):
        st.caption("Fuera del filtro de ingreso.")

def _mostrar_fila_oportunidad_unidad(
    *,
    unidad: dict[str, Any],
    oportunidad: dict[str, Any],
    mostrar_descripcion: bool,
) -> None:
    """Muestra una fila de oportunidad con su unidad y sus deudas."""
    nombre = str(oportunidad.get("nombre", ""))
    colOportunidad, colDescripcion, colValor, colDeudas = st.columns(
        [1.2, 3.2, 1.0, 1.8], vertical_alignment="top"
    )
    with colOportunidad:
        st.badge(
            nombre,
            color=COLORES_OPORTUNIDADES.get(nombre, "gray"),
            icon=ICONOS_OPORTUNIDADES.get(nombre, "🔅"),
        )
        _mostrar_ingreso_oportunidad(oportunidad)
    with colDescripcion:
        if mostrar_descripcion:
            st.markdown(_md(DESCRIPCION_OPORTUNIDADES.get(nombre, "")))
        detalle = str(oportunidad.get("detalle", "") or "").strip()
        if detalle:
            st.caption(_md(detalle))
    with colValor:
        st.markdown("**{}**".format(_md(_formatear_valor_oportunidad_unidad(
            nombre=nombre, valor=oportunidad.get("valor", 0.0)
        ))))
    with colDeudas:
        etiqueta = str(unidad.get("Etiqueta", "") or "Unidad")
        st.caption("**{}**".format(_md(etiqueta)))
        st.caption("{} deuda(s)".format(int(unidad.get("Num_Deudas", 0) or 0)))
        _mostrar_badges_deudas(deudas=unidad.get("Deudas", []))

def _mostrar_bloque_analisis(
    *,
    cliente: pd.Series,
    tipo: str,
    portafolios: list[dict[str, Any]],
) -> None:
    """Muestra un bloque lateral de análisis por Tradicional o Crédito."""
    es_tradicional = tipo == "Tradicional"
    prefijo = "Trad" if es_tradicional else "Cred"
    habilitado = _es_verdadero(
        cliente.get("Tradicional_Habilitado" if es_tradicional else "Credito_Habilitado", False)
    )
    st.markdown("#### 💳 Análisis por Tradicional" if es_tradicional else "#### 🏦 Análisis por Crédito")

    if not habilitado:
        if es_tradicional:
            st.info(
                "No habilitado: el prospecto es **Cr Parcial** y solo permite Crédito.",
                icon="ℹ️",
            )
        else:
            st.info(_md(cliente.get("Credito_Detalle", "")) or "No habilitado para este cliente.", icon="ℹ️")
        return

    st.caption(
        "PaB Origen: **{}** | PaB Actual: **{}** | Descuento: **{}**".format(
            _md(_formatear_monto(cliente.get("{}_PaB_Origen_Total".format(prefijo), 0))),
            _md(_formatear_monto(cliente.get("{}_PaB_Actualizado_Total".format(prefijo), 0))),
            _md(_formatear_porcentaje(cliente.get("{}_Descuento_Actual".format(prefijo), 0))),
        )
    )
    if not es_tradicional:
        st.caption(_md(cliente.get("Credito_Detalle", "")))

    clave = "Usa_Tradicional" if es_tradicional else "Usa_Credito"
    clave_ops = "Trad_Oportunidades" if es_tradicional else "Cred_Oportunidades"
    unidades = [
        unidad for unidad in portafolios
        if _es_verdadero(unidad.get(clave, False))
    ]
    if not unidades:
        st.caption("Sin unidades habilitadas para este análisis.")
        return

    deudas_analisis = sorted({
        str(deuda)
        for unidad in unidades
        for deuda in _normalizar_lista(unidad.get("Deudas", []))
    })
    st.caption(
        "**Deudas usadas en este análisis ({}):**".format(len(deudas_analisis))
    )
    _mostrar_badges_deudas(deudas=deudas_analisis)

    vistos: set[str] = set()
    unidades_con_oportunidades = 0
    primera_oportunidad = True
    for unidad in unidades:
        oportunidades = _normalizar_lista(unidad.get(clave_ops, []))
        if not oportunidades:
            continue
        unidades_con_oportunidades += 1
        for oportunidad in oportunidades:
            nombre = str(oportunidad.get("nombre", ""))
            mostrar_descripcion = nombre not in vistos
            if mostrar_descripcion:
                vistos.add(nombre)
            if not primera_oportunidad:
                st.divider()
            primera_oportunidad = False
            _mostrar_fila_oportunidad_unidad(
                unidad=unidad,
                oportunidad=oportunidad,
                mostrar_descripcion=mostrar_descripcion,
            )

    if unidades_con_oportunidades == 0:
        st.caption("Sin oportunidades en las unidades de este análisis.")
    else:
        sin_oportunidades = len(unidades) - unidades_con_oportunidades
        if sin_oportunidades > 0:
            st.caption(
                "{} unidad(es) sin oportunidades en este análisis.".format(
                    sin_oportunidades
                )
            )

def _mostrar_oportunidades_de_unidad(
    *,
    unidad: dict[str, Any],
    clave: str,
) -> None:
    """Muestra una lista compacta de oportunidades dentro de una unidad."""
    oportunidades = _normalizar_lista(unidad.get(clave, []))
    if not oportunidades:
        st.caption("Sin oportunidades.")
        return
    for oportunidad in oportunidades:
        nombre = str(oportunidad.get("nombre", ""))
        colNombre, colDescripcion, colValor = st.columns(
            [1.2, 3.5, 1.3], vertical_alignment="top"
        )
        with colNombre:
            st.badge(
                nombre,
                color=COLORES_OPORTUNIDADES.get(nombre, "gray"),
                icon=ICONOS_OPORTUNIDADES.get(nombre, "🔅"),
            )
            _mostrar_ingreso_oportunidad(oportunidad)
        with colDescripcion:
            st.markdown(_md(DESCRIPCION_OPORTUNIDADES.get(nombre, "")))
            detalle = str(oportunidad.get("detalle", "") or "").strip()
            if detalle:
                st.caption(_md(detalle))
            deudas = _normalizar_lista(oportunidad.get("deudas", []))
            if deudas:
                _mostrar_badges_deudas(deudas=deudas)
        with colValor:
            st.markdown("**{}**".format(_md(_formatear_valor_oportunidad_unidad(
                nombre=nombre, valor=oportunidad.get("valor", 0.0)
            ))))

def _mostrar_oportunidades_generales(*, cliente: pd.Series) -> None:
    """Muestra Acuerdo para Robo e IA Liquidadora con sus deudas."""
    generales = _normalizar_lista(cliente.get("Oportunidades_Generales", []))
    if not generales:
        return
    st.markdown("#### 🔁 Oportunidades Generales")
    vistos: set[str] = set()
    primera_oportunidad = True
    for oportunidad in generales:
        nombre = str(oportunidad.get("nombre", ""))
        if not primera_oportunidad:
            st.divider()
        primera_oportunidad = False
        colNombre, colDescripcion, colValor, colDeudas = st.columns(
            [1.2, 3.2, 1.0, 1.8], vertical_alignment="top"
        )
        with colNombre:
            st.badge(
                nombre,
                color=COLORES_OPORTUNIDADES.get(nombre, "gray"),
                icon=ICONOS_OPORTUNIDADES.get(nombre, "🔅"),
            )
            _mostrar_ingreso_oportunidad(oportunidad)
            unidad_oportunidad = str(
                oportunidad.get("unidad", "") or ""
            ).strip()
            if unidad_oportunidad:
                st.caption(
                    _md("Unidad del máximo: {}".format(unidad_oportunidad))
                )
        with colDescripcion:
            if nombre not in vistos:
                st.markdown(_md(DESCRIPCION_OPORTUNIDADES.get(nombre, "")))
                vistos.add(nombre)
            detalle = str(oportunidad.get("detalle", "") or "").strip()
            if detalle:
                st.caption(_md(detalle))
        with colValor:
            st.markdown("**{}**".format(_md(_formatear_valor_oportunidad_unidad(
                nombre=nombre, valor=oportunidad.get("valor", 0.0)
            ))))
        with colDeudas:
            deudas = _normalizar_lista(oportunidad.get("deudas", []))
            st.caption("{} deuda(s) involucrada(s)".format(len(deudas)))
            _mostrar_badges_deudas(deudas=deudas)

def _mostrar_detalle_deudas(*, cliente: pd.Series) -> None:
    """Muestra el detalle de las deudas analizadas dentro de un expander."""
    detalle = _normalizar_lista(cliente.get("Deudas_Detalle", []))
    if not detalle:
        st.caption("No hay deudas analizadas para esta Referencia.")
        return

    filas = []
    for deuda in detalle:
        fecha_limite = deuda.get("Fecha_Limite_Uso")
        if fecha_limite is not None and not pd.isna(fecha_limite):
            try:
                fecha_limite = pd.Timestamp(fecha_limite).strftime("%d/%m/%Y")
            except (TypeError, ValueError):
                fecha_limite = ""
        else:
            fecha_limite = ""
        fecha_actualizacion = deuda.get("Fecha_Actualizacion")
        if fecha_actualizacion is not None and not pd.isna(fecha_actualizacion):
            try:
                fecha_actualizacion = pd.Timestamp(
                    fecha_actualizacion
                ).strftime("%d/%m/%Y")
            except (TypeError, ValueError):
                fecha_actualizacion = ""
        else:
            fecha_actualizacion = ""
        filas.append({
            "Id_Deuda": deuda.get("Id_Deuda", ""),
            "Banco": str(deuda.get("Banco") or ""),
            "DUM": _formatear_monto(deuda.get("PaB_Origen", 0)),
            "PaB Actual": _formatear_monto(deuda.get("PaB_Actualizado", 0)),
            "Descuento": _formatear_porcentaje(deuda.get("Descuento_Deuda", 0)),
            "PaB Ideal": _formatear_monto(deuda.get("PaB_Ideal", 0)),
            "Prospecto Trad.": str(deuda.get("Prospecto") or "N/A"),
            "Prob. Liq.": _formatear_porcentaje(deuda.get("Prob_Liq", 0)),
            "En Masivas": "✅" if _es_verdadero(deuda.get("Tiene_Masiva")) else "❌",
            "Tradicional": "✅" if _es_verdadero(deuda.get("Usa_Tradicional")) else "❌",
            "Crédito": "✅" if _es_verdadero(deuda.get("Usa_Credito")) else "❌",
            "Unidad": str(deuda.get("Etiqueta_Unidad") or ""),
            "Casa de Cobro": str(deuda.get("Casa_Cobro") or ""),
            "Última Actualización": str(
                deuda.get("Etiqueta_Actualizacion") or "Sin actualización"
            ),
            "Fecha Actualización": fecha_actualizacion,
            "Vigente Hasta": fecha_limite,
        })

    with st.expander("🔎 Ver deudas analizadas", expanded=False):
        st.dataframe(
            pd.DataFrame(filas),
            hide_index=True,
            width="stretch",
        )

def _mostrar_detalle_portafolios(*, cliente: pd.Series) -> None:
    """Muestra el detalle de cada portafolio o unidad de análisis."""
    portafolios = _normalizar_lista(cliente.get("Portafolios_Detalle", []))
    with st.expander("📦 Detalle por portafolio / unidad de análisis", expanded=False):
        if not portafolios:
            st.caption("No hay portafolios ni unidades para esta Referencia.")
            return
        with st.container(height=ALTO_MAXIMO_DETALLE_PORTAFOLIOS):
            for unidad in portafolios:
                with st.container(border=True):
                    colHeader, colBadges = st.columns(
                        [3, 2], vertical_alignment="center"
                    )
                    with colHeader:
                        st.markdown("**{}**".format(_md(unidad.get("Etiqueta", ""))))
                        st.caption(
                            "Tipo: **{}** | ID Portafolio: **{}**".format(
                                _md(unidad.get("Tipo_Unidad", "")),
                                _md(unidad.get("Id_Portafolio", "") or "N/A"),
                            )
                        )
                    with colBadges:
                        st.badge(
                            "{} deuda(s)".format(int(unidad.get("Num_Deudas", 0) or 0)),
                            color="gray",
                            icon="🆔",
                        )
                        if _es_verdadero(unidad.get("Trad_Viable")):
                            st.badge("Viable Tradicional", color="green", icon="✅")
                        if _es_verdadero(unidad.get("Cred_Viable")):
                            st.badge("Viable Crédito", color="blue", icon="✅")

                    _mostrar_badges_deudas(deudas=unidad.get("Deudas", []))
                    st.caption(
                        "DUM: **{}** | PaB Actual: **{}** | Descuento: **{}**".format(
                            _md(_formatear_monto(unidad.get("PaB_Origen", 0))),
                            _md(_formatear_monto(unidad.get("PaB_Actualizado", 0))),
                            _md(_formatear_porcentaje(unidad.get("Descuento_Actual", 0))),
                        )
                    )
                    st.caption(
                        "Ingreso Actual: **{}** | Ingreso Estimado (filtros): **{}**".format(
                            _md(_formatear_monto(unidad.get("Ingreso_Actual", 0))),
                            _md(_formatear_monto(unidad.get("Ingreso_Estimado", 0))),
                        )
                    )
                    if _es_verdadero(unidad.get("Pago_Compartido")):
                        st.caption(
                            "ℹ️ El pago de esta unidad se comparte entre sus deudas; "
                            "el PaB por deuda mostrado es una distribución por DUM."
                        )

                    if _es_verdadero(unidad.get("Usa_Tradicional")):
                        st.markdown("**💳 Tradicional**")
                        _mostrar_oportunidades_de_unidad(
                            unidad=unidad, clave="Trad_Oportunidades"
                        )
                    else:
                        st.caption("💳 Tradicional: no habilitado.")

                    if _es_verdadero(unidad.get("Usa_Credito")):
                        st.markdown("**🏦 Crédito**")
                        _mostrar_oportunidades_de_unidad(
                            unidad=unidad, clave="Cred_Oportunidades"
                        )
                    else:
                        st.caption(
                            "🏦 Crédito: no habilitado (deudas sin PaB Ideal, "
                            "pipeline no apto o prospecto Tradicional)."
                        )

                    generales = _normalizar_lista(
                        unidad.get("Oportunidades_Generales", [])
                    )
                    if generales:
                        st.markdown("**🔁 Generales**")
                        _mostrar_oportunidades_de_unidad(
                            unidad=unidad, clave="Oportunidades_Generales"
                        )

# --- Redireccionamiento a la Calculadora Individual ---
def _preparar_estado_redireccion_individual(
    *,
    referencia: str,
    deudas_referencia: list[str],
    deudas_unidad: list[str],
    tipo_analisis: str,
) -> tuple[dict[str, Any], list[str]]:
    """Construye las llaves de Session State para abrir la calculadora individual.

    Marca explícitamente como ``False`` todas las deudas de la Referencia y como
    ``True`` solo las deudas de la unidad seleccionada. Así no quedan deudas
    activas de un análisis anterior.

    Returns:
        tuple[dict[str, Any], list[str]]: Valores a escribir y llaves a limpiar.
    """
    referencia = str(referencia)
    deudas_referencia_norm = [
        str(deuda).replace(".0", "").strip()
        for deuda in (deudas_referencia or [])
        if str(deuda).replace(".0", "").strip()
    ]
    deudas_unidad_norm = [
        str(deuda).replace(".0", "").strip()
        for deuda in (deudas_unidad or [])
        if str(deuda).replace(".0", "").strip()
    ]

    valores: dict[str, Any] = {}
    for deuda in deudas_referencia_norm:
        valores["select_calc_ind_debt_{}".format(deuda)] = False
    for deuda in deudas_unidad_norm:
        valores["select_calc_ind_debt_{}".format(deuda)] = True

    es_credito = clean_tildes(
        str(tipo_analisis).strip()
    ).casefold().startswith("cred")
    valores["selectbox_referencia_calc_ind"] = referencia
    valores["select_analysis_calc_ind"] = (
        "**Por Crédito**" if es_credito else "**Por Tradicional**"
    )
    valores["continuar_calc_opp_{}".format(referencia)] = True
    valores[LLAVE_REDIRECCION_CALCULADORA] = True

    modo = "credito" if es_credito else "tradicional"
    claves_limpiar = [
        "ahorro_input_{}_calc_opps".format(referencia),
        "porcobrar_input_{}_calc_opps".format(referencia),
        "dep_extra_input_{}_calc_opps".format(referencia),
        "portafolio_total_{}_{}_calc_opps".format(referencia, modo),
        "portafolio_deudas_{}_{}_calc_opps".format(referencia, modo),
    ]
    # Limpiamos la simulación de PaB/descuento de todas las deudas de la
    # Referencia para que la calculadora individual arranque con los valores
    # oficiales y no reutilice un análisis anterior.
    for deuda in deudas_referencia_norm:
        claves_limpiar.extend([
            "calc_ind_init_{}_{}".format(modo, deuda),
            "calc_ind_pab_{}_{}".format(modo, deuda),
            "calc_ind_disc_{}_{}".format(modo, deuda),
            "calc_ind_pab_slider_{}_{}".format(modo, deuda),
            "calc_ind_disc_slider_{}_{}".format(modo, deuda),
            "calc_ind_pab_text_{}_{}".format(modo, deuda),
            "calc_ind_disc_text_{}_{}".format(modo, deuda),
        ])
    return valores, claves_limpiar

def _mostrar_redireccion_individual(*, cliente: pd.Series) -> None:
    """Muestra el selector para abrir una unidad en la calculadora individual."""
    portafolios = _normalizar_lista(cliente.get("Portafolios_Detalle", []))
    if not portafolios:
        return
    referencia = str(cliente.get("Referencia", ""))
    deudas_referencia = _normalizar_lista(cliente.get("Deudas_Referencia", []))
    etiquetas: list[str] = []
    mapa: dict[str, dict[str, Any]] = {}
    for indice, unidad in enumerate(portafolios, start=1):
        etiqueta_base = str(unidad.get("Etiqueta") or "Unidad {}".format(indice))
        etiqueta = etiqueta_base
        contador = 2
        while etiqueta in mapa:
            etiqueta = "{} ({})".format(etiqueta_base, contador)
            contador += 1
        etiquetas.append(etiqueta)
        mapa[etiqueta] = unidad

    with st.popover("🔁 Analizar en la calculadora individual", width="stretch"):
        st.caption(
            "Selecciona el portafolio/deuda y el tipo de análisis. Se abrirá la "
            "pestaña individual con la Referencia, las deudas y el tipo listos."
        )
        etiqueta = st.selectbox(
            "**Portafolio o deuda**",
            options=etiquetas,
            key="calc_masiva_redir_unidad_{}".format(referencia),
        )
        unidad = mapa[etiqueta]
        tipos: list[str] = []
        if _es_verdadero(unidad.get("Usa_Tradicional")):
            tipos.append("Tradicional")
        if _es_verdadero(unidad.get("Usa_Credito")):
            tipos.append("Crédito")
        if not tipos:
            st.warning(
                "Esta unidad no tiene un análisis habilitado con los datos actuales.",
                icon="⚠️",
            )
            return

        if len(tipos) > 1:
            tipo_analisis = st.radio(
                "**Tipo de análisis**",
                options=tipos,
                horizontal=True,
                key="calc_masiva_redir_tipo_{}".format(referencia),
            )
        else:
            tipo_analisis = tipos[0]
            st.caption("Tipo de análisis: **{}**".format(tipo_analisis))

        if st.button(
            "**Ir a la calculadora individual**",
            type="primary",
            icon="🚀",
            width="stretch",
            key="calc_masiva_redir_boton_{}".format(referencia),
        ):
            valores, claves_limpiar = _preparar_estado_redireccion_individual(
                referencia=referencia,
                deudas_referencia=deudas_referencia,
                deudas_unidad=_normalizar_lista(unidad.get("Deudas", [])),
                tipo_analisis=tipo_analisis,
            )
            for clave in list(st.session_state.keys()):
                if str(clave).startswith("select_calc_ind_debt_"):
                    del st.session_state[clave]
            for clave in claves_limpiar:
                st.session_state.pop(clave, None)
            st.session_state.update(valores)
            st.rerun()

def _mostrar_tarjeta_cliente(*, cliente: pd.Series) -> None:
    """Muestra la tarjeta de un cliente con sus oportunidades por unidad."""
    referencia = str(cliente.get("Referencia", ""))
    nombre = str(cliente.get("Nombre_Cliente", "")).strip()
    negociador = str(cliente.get("Negociador", "")).strip()
    prospecto_credito = str(cliente.get("Prospecto_Credito", "")).strip()
    prospecto_tradicional = str(cliente.get("Prospecto_Tradicional", "")).strip()
    oportunidades = _normalizar_lista(cliente.get("Oportunidades", []))
    num_oportunidades = int(cliente.get("Num_Oportunidades", 0) or 0)
    tipos_analisis = _normalizar_lista(cliente.get("Tipos_Analisis", []))
    viable_por = _normalizar_lista(cliente.get("Viable_Por", []))
    portafolios = _normalizar_lista(cliente.get("Portafolios_Detalle", []))
    fuente_descuento = str(cliente.get("Fuente_Descuento", "Masivas") or "Masivas")
    try:
        ingreso_estimado = float(cliente.get("Ingreso_Estimado", 0) or 0)
    except (TypeError, ValueError):
        ingreso_estimado = 0.0
    if pd.isna(ingreso_estimado):
        ingreso_estimado = 0.0
    detalle_ingreso = cliente.get("Ingreso_Estimado_Detalle")
    if not isinstance(detalle_ingreso, dict):
        detalle_ingreso = {}
    ingreso_oportunidad = str(detalle_ingreso.get("oportunidad") or "").strip()
    ingreso_unidad = str(detalle_ingreso.get("unidad") or "").strip()
    ingreso_tipo = str(detalle_ingreso.get("tipo_analisis") or "").strip()

    with st.container(border=True):
        # Paso 1: Encabezado y Badges
        colEncabezado, colBadges = st.columns([3, 2], vertical_alignment="center")
        with colEncabezado:
            st.markdown("### 🧾 **{}**".format(referencia))
            st.caption(
                "Cliente: **{}** | Negociador: **{}** | Prospecto Crédito: **{}** | Prospecto Tradicional: **{}**".format(
                    nombre or "Sin nombre", negociador or "Sin asignar",
                    prospecto_credito or "N/A", prospecto_tradicional or "N/A",
                )
            )
        with colBadges:
            with st.container(horizontal=True):
                st.badge(
                    "{} Oportunidad(es)".format(num_oportunidades),
                    color="green" if num_oportunidades > 0 else "gray",
                    icon="🔅",
                )
                if _es_verdadero(cliente.get("Es_Viable", False)):
                    st.badge("Viable", color="green", icon="✅")
                if viable_por:
                    st.badge(
                        "Viable por: {}".format(" y ".join(viable_por)),
                        color="green",
                        icon="✅",
                    )
                if _es_verdadero(cliente.get("Tiene_Deudas_Liquidaciones", False)):
                    st.badge("Tiene deudas liquidadas", color="gray", icon="⚠️")
                if "Crédito" in tipos_analisis and "Tradicional" not in tipos_analisis:
                    st.badge("Solo Crédito", color="violet", icon="🏦")
            with st.container(horizontal=True):
                if oportunidades:
                    for oportunidad in oportunidades:
                        st.badge(
                            oportunidad,
                            color=COLORES_OPORTUNIDADES.get(oportunidad, "gray"),
                            icon=ICONOS_OPORTUNIDADES.get(oportunidad, "🔅"),
                        )
                else:
                    st.badge("Sin oportunidades", color="gray", icon="ℹ️")

        # Paso 2: Métricas del Cliente
        colDum, colPab, colDescuento, colAhorro, colIngreso = st.columns(5)
        with colDum:
            st.metric("**💰 DUM Analizado**", _formatear_monto(cliente.get("PaB_Origen_Total", 0)))
        with colPab:
            st.metric(
                "**💵 PaB Actual ({})**".format(fuente_descuento),
                _formatear_monto(cliente.get("PaB_Actualizado_Total", 0)),
            )
        with colDescuento:
            st.metric("**✅ Descuento Actual**", _formatear_porcentaje(cliente.get("Descuento_Actual", 0)))
        with colAhorro:
            st.metric("**📈 Ahorro Neto**", _formatear_monto(cliente.get("Ahorro_Neto", 0)))
        with colIngreso:
            st.metric(
                "**💸 Ingreso Estimado**",
                _formatear_monto(ingreso_estimado),
                help=(
                    "Máximo ingreso estimado entre las oportunidades aplicables "
                    "de las unidades analizadas, sin IVA. Cambia con los filtros "
                    "de Oportunidad y Tipo de Análisis."
                ),
            )

        if ingreso_estimado > 0 and ingreso_oportunidad:
            st.caption(
                _md(
                    "💸 Máximo desde **{}** en **{}** ({}).".format(
                        ingreso_oportunidad,
                        ingreso_unidad or "Unidad",
                        ingreso_tipo or "General",
                    )
                )
            )
        elif ingreso_estimado > 0:
            st.caption(
                "💸 Ingreso estimado máximo de las oportunidades aplicables."
            )
        elif oportunidades:
            st.caption(
                "💸 Con los filtros actuales, las oportunidades no generan un "
                "ingreso estimado mayor a cero."
            )
        else:
            st.caption(
                _md("💸 Sin oportunidades aplicables: Ingreso Estimado **$ 0**.")
            )

        st.caption(
            _md(
                "Las métricas de **DUM**, **PaB Actual** y **Descuento Actual** "
                "corresponden a las deudas analizadas (descuento desde {})."
                .format(fuente_descuento)
            )
        )
        st.caption(
            _md(
                "Deudas analizadas: **{}** | Con Masivas: **{}** | Con PaB Ideal: **{}** | "
                "Unidades: **{}** | Tipos de análisis: **{}**".format(
                    int(cliente.get("Deudas_Analizadas", 0) or 0),
                    int(cliente.get("Deudas_Masivas", 0) or 0),
                    int(cliente.get("Deudas_Con_PaB_Ideal", 0) or 0),
                    len(portafolios),
                    " y ".join(str(t) for t in tipos_analisis) if tipos_analisis else "Ninguno",
                )
            )
        )
        st.caption(
            _md(
                "💸 El **Ingreso Estimado** no incluye IVA. Con IVA: **{}**. "
                "Se toma el mayor ingreso entre las oportunidades de las unidades; "
                "la ContraOferta Viable usa el descuento viable y las demás el "
                "Descuento Actual.".format(
                    _formatear_monto(ingreso_estimado * 1.19)
                )
            )
        )

        # Paso 3: Análisis por Tradicional y Crédito, Lado a Lado
        colTradicional, colCredito = st.columns(
            2, border=True, vertical_alignment="top"
        )
        with colTradicional:
            _mostrar_bloque_analisis(
                cliente=cliente, tipo="Tradicional", portafolios=portafolios
            )
        with colCredito:
            _mostrar_bloque_analisis(
                cliente=cliente, tipo="Crédito", portafolios=portafolios
            )

        # Paso 4: Oportunidades Generales
        _mostrar_oportunidades_generales(cliente=cliente)

        if not oportunidades:
            st.info("No se detectaron oportunidades con los datos actuales.", icon="ℹ️")

        # Paso 5: Detalle de Deudas y de Portafolios
        _mostrar_detalle_deudas(cliente=cliente)
        _mostrar_detalle_portafolios(cliente=cliente)

        # Paso 6: Redireccionamiento a la Calculadora Individual
        _mostrar_redireccion_individual(cliente=cliente)

# --- Paginación ---
def _mostrar_paginacion_masiva(*, total_registros: int) -> tuple[int, int, int]:
    """Muestra los controles de paginación y devuelve página, inicio y fin.

    Toda la paginación se maneja con enteros para evitar errores de indexación
    cuando Streamlit deja strings en Session State.
    """
    registros_por_pagina = int(st.session_state.get(
        "calc_masiva_registros_por_pagina", REGISTROS_POR_PAGINA_DEFAULT
    ))
    if registros_por_pagina not in REGISTROS_POR_PAGINA_MASIVA:
        registros_por_pagina = REGISTROS_POR_PAGINA_DEFAULT
        st.session_state["calc_masiva_registros_por_pagina"] = registros_por_pagina

    total_paginas = max(1, int(math.ceil(total_registros / registros_por_pagina)))
    pagina_actual = _normalizar_pagina_actual(
        st.session_state.get(LLAVE_PAGINA_MASIVA, 1), total_paginas
    )
    st.session_state[LLAVE_PAGINA_MASIVA] = pagina_actual

    colRegistros, colAnterior, colPagina, colSiguiente, colIrA = st.columns(
        [1.5, 1, 1.2, 1, 1.5], vertical_alignment="center"
    )
    with colRegistros:
        st.selectbox(
            "**Clientes por página**",
            options=REGISTROS_POR_PAGINA_MASIVA,
            key="calc_masiva_registros_por_pagina",
            on_change=_reiniciar_pagina_masiva,
        )
    with colAnterior:
        st.space("small")
        if st.button(
            "◀ Anterior",
            key="calc_masiva_pagina_anterior",
            disabled=pagina_actual <= 1,
            width="stretch",
        ):
            st.session_state[LLAVE_PAGINA_MASIVA] = int(max(1, pagina_actual - 1))
            st.rerun()
    with colPagina:
        st.markdown("**Página {} de {}**".format(pagina_actual, total_paginas))
    with colSiguiente:
        st.space("small")
        if st.button(
            "Siguiente ▶",
            key="calc_masiva_pagina_siguiente",
            disabled=pagina_actual >= total_paginas,
            width="stretch",
        ):
            st.session_state[LLAVE_PAGINA_MASIVA] = int(min(total_paginas, pagina_actual + 1))
            st.rerun()
    with colIrA:
        if LLAVE_PAGINA_INPUT_MASIVA not in st.session_state:
            st.session_state[LLAVE_PAGINA_INPUT_MASIVA] = int(pagina_actual)
        elif st.session_state[LLAVE_PAGINA_INPUT_MASIVA] != int(pagina_actual):
            st.session_state[LLAVE_PAGINA_INPUT_MASIVA] = int(pagina_actual)

        def _ir_a_pagina_masiva() -> None:
            st.session_state[LLAVE_PAGINA_MASIVA] = _normalizar_pagina_actual(
                st.session_state.get(LLAVE_PAGINA_INPUT_MASIVA, 1),
                total_paginas,
            )

        st.number_input(
            "**Ir a página**",
            min_value=1,
            max_value=int(total_paginas),
            step=1,
            format="%d",
            key=LLAVE_PAGINA_INPUT_MASIVA,
            on_change=_ir_a_pagina_masiva,
        )

    inicio, fin = _calcular_slice_pagina(
        pagina=pagina_actual,
        total_registros=total_registros,
        registros_por_pagina=registros_por_pagina,
    )
    return int(pagina_actual), int(inicio), int(fin)

# --- Cálculo Compartido entre las Pestañas Masiva y Resumen ---
def calcular_y_guardar_resultado_masivo(
    *,
    solo_masivas: bool,
) -> Optional[pd.DataFrame]:
    """Ejecuta el cálculo masivo y guarda el resultado en Session State.

    Args:
        solo_masivas (bool): Si True, el descuento sale de Masivas; si False,
            sale de Actualizaciones.

    Returns:
        Optional[pd.DataFrame]: Resultado calculado o None si falló.
    """
    st.session_state.pop(LLAVE_RESULTADO_MASIVO, None)
    _limpiar_filtros_masivos()
    barra = st.progress(0.0, text="Iniciando cálculo masivo...")

    def _actualizar_progreso(avance: float, mensaje: str) -> None:
        barra.progress(float(avance), text=str(mensaje))

    try:
        with st.spinner("Calculando oportunidades de toda la cartera..."):
            resultado = calcular_oportunidades_masivas(
                solo_masivas=bool(solo_masivas),
                incluir_acuerdos_robo=True,
                progreso_callback=_actualizar_progreso,
            )
    except Exception as exc:
        barra.empty()
        st.error(
            "No se pudo completar el cálculo masivo. Intenta de nuevo o reduce el "
            "alcance. Detalle: {}".format(exc),
            icon="❌",
        )
        return None

    barra.progress(1.0, text="Cálculo masivo completado.")
    st.session_state[LLAVE_RESULTADO_MASIVO] = resultado
    st.session_state["calc_masiva_solo_masivas_aplicado"] = bool(solo_masivas)
    st.session_state[LLAVE_PAGINA_MASIVA] = 1
    st.session_state.pop(LLAVE_PAGINA_INPUT_MASIVA, None)
    st.success(
        "Cálculo completado: **{}** Referencias analizadas.".format(
            len(resultado)
        ),
        icon="✅",
    )
    return resultado

# --- Vista Principal de la Calculadora Masiva ---
def mostrar_calculadora_masiva() -> None:
    """Muestra la calculadora de oportunidades para toda la cartera habilitada."""
    st.subheader("🛠️ Calculadora de Oportunidades Masiva")
    st.markdown(
        "Recorre **todas las Referencias habilitadas para tu rol** y calcula, de forma "
        "vectorizada, las oportunidades de liquidación de cada cliente y de cada "
        "portafolio/unidad de análisis. Con **Solo de Masivas de Alianzas** activo, el "
        "descuento sale de la Base del Mes de Masivas; con el toggle inactivo, sale de "
        "las Actualizaciones (etiquetas confiables y regla de portafolios)."
    )

    with st.container(border=True):
        colToggle, colBoton = st.columns([2, 1], vertical_alignment="center")
        with colToggle:
            solo_masivas = st.toggle(
                "**Solo de Masivas de Alianzas**",
                value=True,
                key="calc_masiva_solo_masivas",
                help=(
                    "Activo: solo se analizan deudas con un descuento vigente en Masivas; "
                    "los clientes sin deudas en Masivas no aparecen. Inactivo: se analizan "
                    "todas las deudas activas y el descuento actual sale de las "
                    "Actualizaciones; las deudas sin actualización usan PaB_Origen."
                ),
            )
            st.caption(
                "💡 Activo: descuento desde Masivas (máxima certeza del aliado). "
                "Inactivo: descuento desde Actualizaciones, con portafolios agrupados "
                "por etiqueta y ventana de 45 s. En ambos casos se descartan las "
                "Masivas con `Fecha_Limite_Uso` vencida."
            )
        with colBoton:
            calcular = st.button(
                "**Calcular Oportunidades**",
                type="primary",
                icon="🚀",
                width="stretch",
                key="calc_masiva_boton_calcular",
            )

    if calcular:
        if calcular_y_guardar_resultado_masivo(
            solo_masivas=bool(solo_masivas)
        ) is None:
            return

    resultado = st.session_state.get(LLAVE_RESULTADO_MASIVO)
    if resultado is None:
        st.info(
            "Configura el alcance y presiona **Calcular Oportunidades** para comenzar. "
            "El cálculo puede tardar unos segundos mientras se cargan las fuentes.",
            icon="ℹ️",
        )
        return

    if not isinstance(resultado, pd.DataFrame) or resultado.empty:
        st.warning(
            "No se encontraron Referencias con deudas analizables para tu usuario. "
            "Revisa la Asignación de Cartera o el alcance de Referencias.",
            icon="⚠️",
        )
        return

    if (
        "Portafolios_Detalle" not in resultado.columns
        or "Ingreso_Estimado" not in resultado.columns
        or "Estados_Actualizacion" not in resultado.columns
        or "Bancos" not in resultado.columns
        or "Casas_Cobro" not in resultado.columns
    ):
        st.session_state.pop(LLAVE_RESULTADO_MASIVO, None)
        st.warning(
            "El resultado guardado pertenece a una versión anterior de la calculadora. "
            "Presiona **Calcular Oportunidades** para actualizarlo.",
            icon="⚠️",
        )
        return

    # Paso 1: Resumen del Resultado
    total = int(len(resultado))
    con_oportunidades = int((resultado["Num_Oportunidades"].astype(int) > 0).sum())
    viables = int(resultado["Es_Viable"].astype(bool).sum())
    con_credito = int(resultado["Credito_Habilitado"].astype(bool).sum())
    con_tradicional = int(resultado["Tradicional_Habilitado"].astype(bool).sum())

    colTotal, colOportunidades, colViables, colCredito, colTradicional = st.columns(5)
    with colTotal:
        st.metric("**Clientes calculados**", "{:,}".format(total))
    with colOportunidades:
        st.metric("**Con oportunidades**", "{:,}".format(con_oportunidades))
    with colViables:
        st.metric("**Viables**", "{:,}".format(viables))
    with colCredito:
        st.metric("**Crédito viable**", "{:,}".format(con_credito))
    with colTradicional:
        st.metric("**Tradicional**", "{:,}".format(con_tradicional))

    solo_masivas_aplicado = str(
        resultado.get("Fuente_Descuento", pd.Series(["Masivas"])).iloc[0]
    ) == "Masivas"
    st.caption(
        "Resultado calculado con descuento desde **{}** | "
        "**{:.1%}** de los clientes calculados tienen al menos una oportunidad.".format(
            "Masivas" if solo_masivas_aplicado else "Actualizaciones",
            (con_oportunidades / total) if total > 0 else 0.0,
        )
    )

    # Paso 2: Filtros
    with st.container(border=True):
        filtros = _mostrar_filtros_masivos(
            resultado, on_change=_reiniciar_pagina_masiva
        )
    filtrado = filtrar_oportunidades_masivas(resultado, **filtros)

    st.caption(
        "Mostrando **{:,}** de **{:,}** clientes después de aplicar los filtros.".format(
            len(filtrado), total
        )
    )
    if filtrado.empty:
        st.warning(
            "No hay clientes que cumplan los filtros seleccionados. Ajusta los filtros "
            "o vuelve a calcular.",
            icon="⚠️",
        )
        return

    # Paso 3: Paginación Entera
    pagina_actual, inicio, fin = _mostrar_paginacion_masiva(total_registros=len(filtrado))
    pagina_df = filtrado.iloc[int(inicio):int(fin)]
    st.caption(
        "Mostrando clientes **{}-{}** de **{}** (**{:.1%}**) | Página **{}**.".format(
            inicio + 1 if fin > inicio else 0,
            fin,
            len(filtrado),
            (len(pagina_df) / len(filtrado)) if len(filtrado) > 0 else 0.0,
            pagina_actual,
        )
    )

    # Paso 4: Tarjetas de la Página Actual
    for _, cliente in pagina_df.iterrows():
        _mostrar_tarjeta_cliente(cliente=cliente)

    # Paso 5: Feedback de la Vista
    configs_feedback = {
        "Solo_Masivas": bool(solo_masivas_aplicado),
        "Invertir_Orden": bool(filtros.get("invertir_orden", False)),
        "Total_Clientes": total,
        "Clientes_Filtrados": int(len(filtrado)),
        "Pagina_Actual": int(pagina_actual),
        "Filtros": {
            clave: str(valor) if not isinstance(valor, (list, tuple, dict)) else valor
            for clave, valor in filtros.items()
        },
    }
    mostrar_componente_feedback(
        origin="Calculadora_Masiva_Opps",
        configs=configs_feedback,
        type_container="expander",
    )
