# Estándar usando PEP8
# Librerías de Python
from typing import Any, Optional
# Librerías de Terceros
import pandas as pd
# Librerías Locales
from modules.constants import OPORTUNIDADES

# --- Configuración del Resumen ---
OPORTUNIDADES_CALCULADAS = [
    "Depósito Extra",
    "ContraOferta Viable",
    "Liquidación Instantánea",
]
OPORTUNIDADES_GENERALES = [
    "Acuerdo para Robo",
    "IA Liquidadora",
]
# Orden de desempate del Ingreso Estimado. Debe coincidir con
# PRIORIDAD_INGRESO_ESTIMADO de modules/oportunidades.py.
PRIORIDAD_INGRESO = {
    "Liquidación Instantánea": 0,
    "ContraOferta Viable": 1,
    "Depósito Extra": 2,
    "Acuerdo para Robo": 3,
    "IA Liquidadora": 4,
}
RANGOS_DESCUENTO = [
    "0%",
    "0% - 10%",
    "10% - 20%",
    "20% - 30%",
    "30% - 40%",
    "40% - 50%",
    "50% - 60%",
    "60% - 70%",
    "70% - 80%",
    "80% - 90%",
    "90% - 100%",
]
TIPOS_ANALISIS_RESUMEN = ["Tradicional", "Crédito", "General"]

# --- Columnas de las Tablas del Resumen ---
COLUMNAS_DETALLE = [
    "Referencia",
    "Nombre_Cliente",
    "Negociador",
    "Prospecto_Credito",
    "Prospecto_Tradicional",
    "Estado_Pipeline",
    "Es_Viable",
    "Viable_Por",
    "Tiene_Deudas_Liquidaciones",
    "DUM_Cliente",
    "PaB_Actualizado_Cliente",
    "Descuento_Actual_Cliente",
    "Ingreso_Estimado_Cliente",
    "Fuente_Descuento",
    "Estados_Actualizacion",
    "Bancos",
    "Casas_Cobro",
    "Unidad_Id",
    "Etiqueta_Unidad",
    "Tipo_Unidad",
    "Num_Deudas_Unidad",
    "DUM_Unidad",
    "PaB_Actualizado_Unidad",
    "Descuento_Actual_Unidad",
    "Ingreso_Actual_Unidad",
    "Ingreso_Estimado_Unidad",
    "Rango_Descuento",
    "Pago_Compartido",
    "Oportunidad",
    "Tipo_Analisis",
    "Valor",
    "Detalle",
    "Ingreso_Estimado_Oportunidad",
    "Incluida_Ingreso_Estimado",
    "Deudas",
    "Es_General",
    "Es_Maximo_Unidad",
    "Ingreso_Asignado_Unidad",
]
COLUMNAS_DETALLE_DEUDAS = [
    "Referencia",
    "Nombre_Cliente",
    "Negociador",
    "Prospecto_Credito",
    "Prospecto_Tradicional",
    "Estado_Pipeline",
    "Oportunidad",
    "Tipo_Analisis",
    "Es_General",
    "Unidad_Id",
    "Etiqueta_Unidad",
    "Tipo_Unidad",
    "Rango_Descuento",
    "Id_Deuda",
    "Banco_Resumen",
    "Casa_Cobro_Resumen",
    "Estado_Actualizacion",
    "Fecha_Actualizacion",
    "PaB_Origen_Deuda",
    "PaB_Actualizado_Deuda",
    "Descuento_Deuda",
    "PaB_Ideal",
    "Prospecto_Deuda",
    "Prob_Liq",
    "Tiene_Masiva",
    "Ingreso_Estimado_Oportunidad",
    "Ingreso_Asignado_Oportunidad",
    "Ingreso_Asignado_Maximo",
    "Es_Maximo_Unidad",
    "Incluida_Ingreso_Estimado",
]
COLUMNAS_TABLA_OPORTUNIDAD = [
    "Oportunidad",
    "Incidencias",
    "Clientes",
    "Deudas",
    "Unidades",
    "Ingreso_Estimado",
    "Ingreso_Potencial",
    "Porcentaje_Ingreso",
    "Es_Total",
]
COLUMNAS_TABLA_TIPO = [
    "Tipo_Analisis",
    "Incidencias",
    "Clientes",
    "Deudas",
    "Unidades",
    "Ingreso_Estimado",
    "Ingreso_Potencial",
    "Porcentaje_Ingreso",
    "Es_Total",
]
COLUMNAS_TABLA_DIMENSION = [
    "Valor",
    "Incidencias",
    "Clientes",
    "Deudas",
    "Unidades",
    "Ingreso_Estimado",
    "Ingreso_Potencial",
    "Porcentaje_Ingreso",
]

# --- Funciones Auxiliares de Normalización ---
def _a_lista(valor: Any) -> list[Any]:
    """Convierte un valor de columna lista en una lista segura."""
    if isinstance(valor, (list, tuple, set)):
        return list(valor)
    return []

def _a_float(valor: Any, default: float = 0.0) -> float:
    """Convierte un valor a float sin propagar NaN."""
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return float(default)
    if pd.isna(numero):
        return float(default)
    return float(numero)

def _a_bool(valor: Any, default: bool = False) -> bool:
    """Convierte un valor con posibles NaN a booleano."""
    try:
        if pd.isna(valor):
            return bool(default)
    except (TypeError, ValueError):
        pass
    return bool(valor)

def _texto(valor: Any, default: str = "") -> str:
    """Normaliza un valor a texto sin espacios sobrantes."""
    if valor is None:
        return str(default)
    try:
        if pd.isna(valor):
            return str(default)
    except (TypeError, ValueError):
        pass
    texto = str(valor).strip()
    return texto if texto else str(default)

def _rango_descuento(valor: Any) -> str:
    """Ubica un descuento decimal en uno de los rangos del resumen."""
    descuento = _a_float(valor)
    if descuento <= 0:
        return "0%"
    if descuento >= 1:
        return "90% - 100%"
    indice = int(descuento * 10)
    if indice <= 0:
        return "0% - 10%"
    return "{}% - {}%".format(indice * 10, (indice + 1) * 10)

def _prioridad_oportunidad(nombre: Any) -> int:
    """Devuelve la prioridad de desempate de una oportunidad."""
    return PRIORIDAD_INGRESO.get(_texto(nombre), 99)

def _tabla_vacia(columnas: list[str]) -> pd.DataFrame:
    """Crea un DataFrame vacío con las columnas indicadas."""
    return pd.DataFrame(columns=columnas)

# --- Construcción del Detalle de Oportunidades ---
def construir_detalle_oportunidades(df: pd.DataFrame) -> pd.DataFrame:
    """Convierte el resultado masivo en una fila por unidad y oportunidad.

    Args:
        df (pd.DataFrame): Resultado de ``calcular_oportunidades_masivas``.

    Returns:
        pd.DataFrame: Detalle con una fila por incidencia unidad/oportunidad.
        Incluye el ingreso de la oportunidad, el ingreso máximo de la unidad y
        la bandera ``Es_Maximo_Unidad`` para atribuir el ingreso sin doble
        conteo.
    """
    if df is None or df.empty:
        return _tabla_vacia(COLUMNAS_DETALLE)

    registros: list[dict[str, Any]] = []
    for _, cliente in df.iterrows():
        referencia = _texto(cliente.get("Referencia"))
        if not referencia:
            continue

        atributos_cliente = {
            "Referencia": referencia,
            "Nombre_Cliente": _texto(cliente.get("Nombre_Cliente")),
            "Negociador": _texto(
                cliente.get("Negociador"), "Sin Negociador Asignado"
            ),
            "Prospecto_Credito": _texto(cliente.get("Prospecto_Credito"), "N/A"),
            "Prospecto_Tradicional": _texto(
                cliente.get("Prospecto_Tradicional"), "N/A"
            ),
            "Estado_Pipeline": _texto(
                cliente.get("Estado_Credito"), "Sin registro en Pipeline"
            ),
            "Es_Viable": _a_bool(cliente.get("Es_Viable")),
            "Viable_Por": _a_lista(cliente.get("Viable_Por")),
            "Tiene_Deudas_Liquidaciones": _a_bool(
                cliente.get("Tiene_Deudas_Liquidaciones")
            ),
            "DUM_Cliente": _a_float(cliente.get("PaB_Origen_Total")),
            "PaB_Actualizado_Cliente": _a_float(
                cliente.get("PaB_Actualizado_Total")
            ),
            "Descuento_Actual_Cliente": _a_float(
                cliente.get("Descuento_Actual")
            ),
            "Ingreso_Estimado_Cliente": _a_float(
                cliente.get("Ingreso_Estimado")
            ),
            "Fuente_Descuento": _texto(
                cliente.get("Fuente_Descuento"), "Masivas"
            ),
            "Estados_Actualizacion": _a_lista(
                cliente.get("Estados_Actualizacion")
            ),
            "Bancos": _a_lista(cliente.get("Bancos")),
            "Casas_Cobro": _a_lista(cliente.get("Casas_Cobro")),
        }

        for unidad in _a_lista(cliente.get("Portafolios_Detalle")):
            if not isinstance(unidad, dict):
                continue

            deudas_unidad = sorted({
                _texto(deuda)
                for deuda in _a_lista(unidad.get("Deudas"))
                if _texto(deuda)
            })
            descuento_unidad = _a_float(unidad.get("Descuento_Actual"))
            atributos_unidad = {
                "Unidad_Id": _texto(unidad.get("Unidad_Id")),
                "Etiqueta_Unidad": _texto(
                    unidad.get("Etiqueta"), _texto(unidad.get("Unidad_Id"))
                ),
                "Tipo_Unidad": _texto(
                    unidad.get("Tipo_Unidad"), "Deuda individual"
                ),
                "Num_Deudas_Unidad": len(deudas_unidad),
                "DUM_Unidad": _a_float(unidad.get("PaB_Origen")),
                "PaB_Actualizado_Unidad": _a_float(
                    unidad.get("PaB_Actualizado")
                ),
                "Descuento_Actual_Unidad": descuento_unidad,
                "Ingreso_Actual_Unidad": _a_float(unidad.get("Ingreso_Actual")),
                "Ingreso_Estimado_Unidad": _a_float(
                    unidad.get("Ingreso_Estimado")
                ),
                "Rango_Descuento": _rango_descuento(descuento_unidad),
                "Pago_Compartido": _a_bool(unidad.get("Pago_Compartido")),
            }

            # Paso 1: Oportunidades Calculadas (Tradicional y Crédito)
            candidatos: list[dict[str, Any]] = []
            tiene_bandera_ingreso = False
            for clave, etiqueta in (
                ("Trad_Oportunidades", "Tradicional"),
                ("Cred_Oportunidades", "Crédito"),
            ):
                for oportunidad in _a_lista(unidad.get(clave)):
                    if not isinstance(oportunidad, dict):
                        continue
                    nombre = _texto(oportunidad.get("nombre"))
                    if not nombre:
                        continue
                    if "incluida_en_ingreso_estimado" in oportunidad:
                        tiene_bandera_ingreso = True
                    candidatos.append({
                        "Oportunidad": nombre,
                        "Tipo_Analisis": _texto(
                            oportunidad.get("tipo_analisis"), etiqueta
                        ),
                        "Valor": oportunidad.get("valor", 0.0),
                        "Detalle": _texto(oportunidad.get("detalle")),
                        "Ingreso_Estimado_Oportunidad": _a_float(
                            oportunidad.get("ingreso_estimado")
                        ),
                        "Incluida_Ingreso_Estimado": _a_bool(
                            oportunidad.get("incluida_en_ingreso_estimado")
                        ),
                        "Deudas": list(deudas_unidad),
                        "Es_General": False,
                    })

            # Paso 2: Oportunidades Generales (Robo e IA)
            for oportunidad in _a_lista(unidad.get("Oportunidades_Generales")):
                if not isinstance(oportunidad, dict):
                    continue
                nombre = _texto(oportunidad.get("nombre"))
                if not nombre:
                    continue
                if "incluida_en_ingreso_estimado" in oportunidad:
                    tiene_bandera_ingreso = True
                deudas_oportunidad = sorted({
                    _texto(deuda)
                    for deuda in _a_lista(oportunidad.get("deudas"))
                    if _texto(deuda)
                }) or list(deudas_unidad)
                candidatos.append({
                    "Oportunidad": nombre,
                    "Tipo_Analisis": "General",
                    "Valor": oportunidad.get("valor", 0.0),
                    "Detalle": _texto(oportunidad.get("detalle")),
                    "Ingreso_Estimado_Oportunidad": _a_float(
                        oportunidad.get("ingreso_estimado")
                    ),
                    "Incluida_Ingreso_Estimado": _a_bool(
                        oportunidad.get("incluida_en_ingreso_estimado")
                    ),
                    "Deudas": deudas_oportunidad,
                    "Es_General": True,
                })

            if not candidatos:
                continue

            # Los resultados anteriores a la bandera de ingreso se consideran
            # incluidos para no perder oportunidades ya calculadas.
            if not tiene_bandera_ingreso:
                for candidato in candidatos:
                    candidato["Incluida_Ingreso_Estimado"] = True

            # Solo se resumen las oportunidades que el filtro vigente incluyó
            # en el Ingreso Estimado. Las demás siguen visibles en las
            # tarjetas, pero no deben contaminar las distribuciones filtradas.
            candidatos = [
                candidato for candidato in candidatos
                if candidato["Incluida_Ingreso_Estimado"]
            ]
            if not candidatos:
                continue

            # Paso 3: Identificar la Oportunidad que Aporta el Máximo de la Unidad
            indices_elegibles = [
                indice
                for indice, candidato in enumerate(candidatos)
                if candidato["Incluida_Ingreso_Estimado"]
                and candidato["Ingreso_Estimado_Oportunidad"] > 0
            ]
            indice_maximo: Optional[int] = None
            if indices_elegibles:
                indice_maximo = min(
                    indices_elegibles,
                    key=lambda indice: (
                        -candidatos[indice]["Ingreso_Estimado_Oportunidad"],
                        _prioridad_oportunidad(
                            candidatos[indice]["Oportunidad"]
                        ),
                    ),
                )

            # Paso 4: Aplanar las Incidencias de la Unidad
            for indice, candidato in enumerate(candidatos):
                es_maximo = indice == indice_maximo
                registro = {}
                registro.update(atributos_cliente)
                registro.update(atributos_unidad)
                registro.update(candidato)
                registro["Es_Maximo_Unidad"] = es_maximo
                # El ingreso máximo se repite en todas las oportunidades de la
                # unidad; la bandera Es_Maximo_Unidad indica cuál lo aporta.
                registro["Ingreso_Asignado_Unidad"] = (
                    atributos_unidad["Ingreso_Estimado_Unidad"]
                )
                registros.append(registro)

    if not registros:
        return _tabla_vacia(COLUMNAS_DETALLE)
    return pd.DataFrame(registros, columns=COLUMNAS_DETALLE)

# --- Construcción del Detalle por Deuda ---
def construir_detalle_deudas_oportunidades(
    df: pd.DataFrame,
    detalle: pd.DataFrame,
) -> pd.DataFrame:
    """Explota cada oportunidad en sus deudas y asigna el ingreso por DUM.

    La asignación proporcional permite sumar el ingreso por banco o casa de
    cobro sin multiplicarlo por el número de deudas de la unidad. El ingreso
    máximo se asigna solo a la oportunidad que ganó en la unidad, de modo que
    la suma de ``Ingreso_Asignado_Maximo`` coincide con el Ingreso Estimado.

    Args:
        df (pd.DataFrame): Resultado masivo con ``Portafolios_Detalle``.
        detalle (pd.DataFrame): Salida de ``construir_detalle_oportunidades``.

    Returns:
        pd.DataFrame: Una fila por incidencia y deuda involucrada.
    """
    if detalle is None or detalle.empty:
        return _tabla_vacia(COLUMNAS_DETALLE_DEUDAS)

    # Paso 1: Indexar las deudas de cada unidad para recuperar sus atributos
    unidades_por_clave: dict[tuple[str, str], dict[str, Any]] = {}
    if df is not None and not df.empty:
        for _, cliente in df.iterrows():
            referencia = _texto(cliente.get("Referencia"))
            for unidad in _a_lista(cliente.get("Portafolios_Detalle")):
                if not isinstance(unidad, dict):
                    continue
                clave = (referencia, _texto(unidad.get("Unidad_Id")))
                unidades_por_clave[clave] = unidad

    registros: list[dict[str, Any]] = []
    for fila in detalle.to_dict("records"):
        referencia = _texto(fila.get("Referencia"))
        unidad_id = _texto(fila.get("Unidad_Id"))
        deudas = [
            _texto(deuda)
            for deuda in _a_lista(fila.get("Deudas"))
            if _texto(deuda)
        ]
        if not deudas:
            continue

        unidad = unidades_por_clave.get((referencia, unidad_id), {})
        detalles_deuda = {
            _texto(deuda.get("Id_Deuda")): deuda
            for deuda in _a_lista(unidad.get("Deudas_Detalle"))
            if isinstance(deuda, dict) and _texto(deuda.get("Id_Deuda"))
        }

        # Paso 2: Calcular los pesos por PaB_Origen para repartir el ingreso
        pesos = []
        for deuda in deudas:
            info = detalles_deuda.get(deuda, {})
            pesos.append(max(_a_float(info.get("PaB_Origen")), 0.0))
        suma_pesos = float(sum(pesos))
        if suma_pesos > 0:
            factores = [peso / suma_pesos for peso in pesos]
        else:
            factores = [1.0 / len(deudas)] * len(deudas)

        ingreso_oportunidad = _a_float(fila.get("Ingreso_Estimado_Oportunidad"))
        es_maximo = _a_bool(fila.get("Es_Maximo_Unidad"))

        # Paso 3: Crear una Fila por Deuda Involucrada
        for deuda, factor in zip(deudas, factores):
            info = detalles_deuda.get(deuda, {})
            pab_origen = _a_float(info.get("PaB_Origen"))
            pab_actualizado = _a_float(info.get("PaB_Actualizado"))
            descuento_deuda = _a_float(info.get("Descuento_Deuda"))
            descuento_original = info.get("Descuento_Deuda")
            if (
                pab_origen > 0
                and (
                    "Descuento_Deuda" not in info
                    or descuento_original is None
                    or pd.isna(descuento_original)
                )
            ):
                descuento_deuda = 1 - (pab_actualizado / pab_origen)
            ingreso_asignado = ingreso_oportunidad * factor
            registros.append({
                "Referencia": referencia,
                "Nombre_Cliente": _texto(fila.get("Nombre_Cliente")),
                "Negociador": _texto(
                    fila.get("Negociador"), "Sin Negociador Asignado"
                ),
                "Prospecto_Credito": _texto(
                    fila.get("Prospecto_Credito"), "N/A"
                ),
                "Prospecto_Tradicional": _texto(
                    fila.get("Prospecto_Tradicional"), "N/A"
                ),
                "Estado_Pipeline": _texto(
                    fila.get("Estado_Pipeline"), "Sin registro en Pipeline"
                ),
                "Oportunidad": _texto(fila.get("Oportunidad")),
                "Tipo_Analisis": _texto(
                    fila.get("Tipo_Analisis"), "General"
                ),
                "Es_General": _a_bool(fila.get("Es_General")),
                "Unidad_Id": unidad_id,
                "Etiqueta_Unidad": _texto(fila.get("Etiqueta_Unidad")),
                "Tipo_Unidad": _texto(
                    fila.get("Tipo_Unidad"), "Deuda individual"
                ),
                "Rango_Descuento": _texto(fila.get("Rango_Descuento"), "0%"),
                "Id_Deuda": deuda,
                "Banco_Resumen": _texto(info.get("Banco"), "Sin banco"),
                "Casa_Cobro_Resumen": _texto(
                    info.get("Casa_Cobro"), "Sin casa de cobro"
                ),
                "Estado_Actualizacion": _texto(
                    info.get("Etiqueta_Actualizacion"), "Sin actualización"
                ),
                "Fecha_Actualizacion": info.get("Fecha_Actualizacion"),
                "PaB_Origen_Deuda": pab_origen,
                "PaB_Actualizado_Deuda": pab_actualizado,
                "Descuento_Deuda": max(min(descuento_deuda, 1.0), 0.0),
                "PaB_Ideal": _a_float(info.get("PaB_Ideal")),
                "Prospecto_Deuda": _texto(info.get("Prospecto"), "N/A"),
                "Prob_Liq": _a_float(info.get("Prob_Liq")),
                "Tiene_Masiva": _a_bool(info.get("Tiene_Masiva")),
                "Ingreso_Estimado_Oportunidad": ingreso_oportunidad,
                "Ingreso_Asignado_Oportunidad": ingreso_asignado,
                "Ingreso_Asignado_Maximo": (
                    ingreso_asignado if es_maximo else 0.0
                ),
                "Es_Maximo_Unidad": es_maximo,
                "Incluida_Ingreso_Estimado": _a_bool(
                    fila.get("Incluida_Ingreso_Estimado")
                ),
            })

    if not registros:
        return _tabla_vacia(COLUMNAS_DETALLE_DEUDAS)
    return pd.DataFrame(registros, columns=COLUMNAS_DETALLE_DEUDAS)

# --- Métricas Agregadas ---
def _metricas_desde_detalle(
    filas: pd.DataFrame,
    filas_deudas: pd.DataFrame,
    total_ingreso: float,
) -> dict[str, Any]:
    """Calcula las métricas de un subconjunto a nivel de incidencia."""
    if filas is None or filas.empty:
        return {
            "Incidencias": 0,
            "Clientes": 0,
            "Deudas": 0,
            "Unidades": 0,
            "Ingreso_Estimado": 0.0,
            "Ingreso_Potencial": 0.0,
            "Porcentaje_Ingreso": 0.0,
        }

    incidencias = int(len(filas))
    clientes = int(filas["Referencia"].nunique())
    unidades = int(
        filas[["Referencia", "Unidad_Id"]].drop_duplicates().shape[0]
    )
    if filas_deudas is not None and not filas_deudas.empty:
        deudas = int(
            filas_deudas[["Referencia", "Id_Deuda"]].drop_duplicates().shape[0]
        )
    else:
        deudas = 0
    ingreso_estimado = _a_float(
        filas.loc[filas["Es_Maximo_Unidad"], "Ingreso_Asignado_Unidad"].sum()
    )
    ingreso_potencial = _a_float(
        filas["Ingreso_Estimado_Oportunidad"].sum()
    )
    porcentaje = (
        ingreso_estimado / total_ingreso if total_ingreso > 0 else 0.0
    )
    return {
        "Incidencias": incidencias,
        "Clientes": clientes,
        "Deudas": deudas,
        "Unidades": unidades,
        "Ingreso_Estimado": ingreso_estimado,
        "Ingreso_Potencial": ingreso_potencial,
        "Porcentaje_Ingreso": porcentaje,
    }

def _metricas_desde_detalle_deudas(
    filas: pd.DataFrame,
    total_ingreso: float,
) -> dict[str, Any]:
    """Calcula las métricas de un subconjunto a nivel de deuda."""
    if filas is None or filas.empty:
        return {
            "Incidencias": 0,
            "Clientes": 0,
            "Deudas": 0,
            "Unidades": 0,
            "Ingreso_Estimado": 0.0,
            "Ingreso_Potencial": 0.0,
            "Porcentaje_Ingreso": 0.0,
        }

    incidencias = int(
        filas[["Referencia", "Unidad_Id", "Oportunidad"]]
        .drop_duplicates()
        .shape[0]
    )
    clientes = int(filas["Referencia"].nunique())
    deudas = int(
        filas[["Referencia", "Id_Deuda"]].drop_duplicates().shape[0]
    )
    unidades = int(
        filas[["Referencia", "Unidad_Id"]].drop_duplicates().shape[0]
    )
    ingreso_estimado = _a_float(filas["Ingreso_Asignado_Maximo"].sum())
    ingreso_potencial = _a_float(
        filas["Ingreso_Asignado_Oportunidad"].sum()
    )
    porcentaje = (
        ingreso_estimado / total_ingreso if total_ingreso > 0 else 0.0
    )
    return {
        "Incidencias": incidencias,
        "Clientes": clientes,
        "Deudas": deudas,
        "Unidades": unidades,
        "Ingreso_Estimado": ingreso_estimado,
        "Ingreso_Potencial": ingreso_potencial,
        "Porcentaje_Ingreso": porcentaje,
    }

def calcular_kpis_resumen(
    df: pd.DataFrame,
    detalle: pd.DataFrame,
    detalle_deudas: pd.DataFrame,
) -> dict[str, Any]:
    """Calcula los KPIs generales del panel de resumen.

    El Ingreso Estimado Total es la **suma de los máximos por unidad de
    análisis**. No es el máximo del cliente que muestra la tarjeta de la
    calculadora masiva: un cliente con dos portafolios con oportunidad aporta
    el máximo de cada portafolio. El Ingreso Potencial suma todas las
    oportunidades y se informa como referencia, sin sumarse al total.
    """
    if df is None:
        df = pd.DataFrame()

    clientes_total = int(len(df))
    clientes_con_oportunidad = (
        int(detalle["Referencia"].nunique()) if not detalle.empty else 0
    )
    incidencias = int(len(detalle))
    deudas_con_oportunidad = (
        int(
            detalle_deudas[["Referencia", "Id_Deuda"]]
            .drop_duplicates()
            .shape[0]
        )
        if not detalle_deudas.empty else 0
    )
    deudas_incidencia = int(len(detalle_deudas))

    if "Deudas_Analizadas" in df.columns:
        deudas_analizadas = int(
            pd.to_numeric(df["Deudas_Analizadas"], errors="coerce")
            .fillna(0)
            .sum()
        )
    else:
        deudas_analizadas = deudas_con_oportunidad

    if "Portafolios_Detalle" in df.columns:
        unidades_analizadas = int(
            df["Portafolios_Detalle"]
            .apply(lambda valor: len(_a_lista(valor)))
            .sum()
        )
    else:
        unidades_analizadas = 0

    unidades_con_oportunidad = (
        int(
            detalle[["Referencia", "Unidad_Id"]]
            .drop_duplicates()
            .shape[0]
        )
        if not detalle.empty else 0
    )

    if not detalle.empty:
        unidades_unicas = detalle[
            ["Referencia", "Unidad_Id", "DUM_Unidad"]
        ].drop_duplicates(subset=["Referencia", "Unidad_Id"])
        ingreso_estimado_total = _a_float(
            detalle.loc[
                detalle["Es_Maximo_Unidad"], "Ingreso_Asignado_Unidad"
            ].sum()
        )
        dum_con_oportunidad = _a_float(unidades_unicas["DUM_Unidad"].sum())
    else:
        ingreso_estimado_total = 0.0
        dum_con_oportunidad = 0.0

    ingreso_potencial_total = (
        _a_float(detalle["Ingreso_Estimado_Oportunidad"].sum())
        if not detalle.empty else 0.0
    )
    dum_total = (
        _a_float(pd.to_numeric(
            df["PaB_Origen_Total"], errors="coerce"
        ).fillna(0).sum())
        if "PaB_Origen_Total" in df.columns else 0.0
    )

    def _dividir(numerador: float, denominador: float) -> float:
        return float(numerador) / float(denominador) if denominador else 0.0

    return {
        "Clientes_Total": clientes_total,
        "Clientes_Con_Oportunidad": clientes_con_oportunidad,
        "Cobertura_Clientes": _dividir(
            clientes_con_oportunidad, clientes_total
        ),
        "Deudas_Analizadas": deudas_analizadas,
        "Deudas_Con_Oportunidad": deudas_con_oportunidad,
        "Cobertura_Deudas": _dividir(
            deudas_con_oportunidad, deudas_analizadas
        ),
        "Unidades_Analizadas": unidades_analizadas,
        "Unidades_Con_Oportunidad": unidades_con_oportunidad,
        "Cobertura_Unidades": _dividir(
            unidades_con_oportunidad, unidades_analizadas
        ),
        "Incidencias": incidencias,
        "Deudas_Incidencia": deudas_incidencia,
        "Ingreso_Estimado_Total": ingreso_estimado_total,
        "Ingreso_Potencial_Total": ingreso_potencial_total,
        "DUM_Total": dum_total,
        "DUM_Con_Oportunidad": dum_con_oportunidad,
        "Ingreso_Promedio_Cliente": _dividir(
            ingreso_estimado_total, clientes_con_oportunidad
        ),
        "DUM_Promedio_Cliente": _dividir(
            dum_con_oportunidad, clientes_con_oportunidad
        ),
        "Oportunidades_Promedio_Cliente": _dividir(
            incidencias, clientes_con_oportunidad
        ),
        "Ingreso_Promedio_Oportunidad": _dividir(
            ingreso_potencial_total, incidencias
        ),
        "Deudas_Promedio_Oportunidad": _dividir(
            deudas_incidencia, incidencias
        ),
        "Ingreso_Sobre_DUM": _dividir(
            ingreso_estimado_total, dum_con_oportunidad
        ),
    }

def calcular_resumen_por_oportunidad(
    detalle: pd.DataFrame,
    detalle_deudas: pd.DataFrame,
    total_ingreso: float,
) -> pd.DataFrame:
    """Agrupa las métricas por tipo de oportunidad."""
    if detalle is None or detalle.empty:
        return _tabla_vacia(COLUMNAS_TABLA_OPORTUNIDAD)

    registros: list[dict[str, Any]] = []
    for nombre in OPORTUNIDADES:
        filas = detalle[detalle["Oportunidad"] == nombre]
        filas_deudas = (
            detalle_deudas[detalle_deudas["Oportunidad"] == nombre]
            if detalle_deudas is not None and not detalle_deudas.empty
            else pd.DataFrame()
        )
        metricas = _metricas_desde_detalle(
            filas, filas_deudas, total_ingreso
        )
        registros.append({
            "Oportunidad": nombre,
            **metricas,
            "Es_Total": False,
        })

    total = _metricas_desde_detalle(
        detalle, detalle_deudas, total_ingreso
    )
    registros.append({
        "Oportunidad": "Total",
        **total,
        "Es_Total": True,
    })
    return pd.DataFrame(registros, columns=COLUMNAS_TABLA_OPORTUNIDAD)

def calcular_resumen_por_tipo_analisis(
    detalle: pd.DataFrame,
    detalle_deudas: pd.DataFrame,
    total_ingreso: float,
) -> pd.DataFrame:
    """Agrupa las métricas por tipo de análisis."""
    if detalle is None or detalle.empty:
        return _tabla_vacia(COLUMNAS_TABLA_TIPO)

    registros: list[dict[str, Any]] = []
    for tipo in TIPOS_ANALISIS_RESUMEN:
        filas = detalle[detalle["Tipo_Analisis"] == tipo]
        filas_deudas = (
            detalle_deudas[detalle_deudas["Tipo_Analisis"] == tipo]
            if detalle_deudas is not None and not detalle_deudas.empty
            else pd.DataFrame()
        )
        metricas = _metricas_desde_detalle(
            filas, filas_deudas, total_ingreso
        )
        registros.append({
            "Tipo_Analisis": tipo,
            **metricas,
            "Es_Total": False,
        })

    total = _metricas_desde_detalle(
        detalle, detalle_deudas, total_ingreso
    )
    registros.append({
        "Tipo_Analisis": "Total",
        **total,
        "Es_Total": True,
    })
    return pd.DataFrame(registros, columns=COLUMNAS_TABLA_TIPO)

def calcular_resumen_por_dimension(
    detalle_deudas: pd.DataFrame,
    *,
    columna: str,
    etiqueta_vacio: str,
    total_ingreso: float,
    orden_categorias: Optional[list[str]] = None,
) -> pd.DataFrame:
    """Agrupa las métricas por una dimensión del detalle de deudas.

    Args:
        detalle_deudas (pd.DataFrame): Detalle con una fila por deuda.
        columna (str): Columna por la que se agrupa.
        etiqueta_vacio (str): Etiqueta para valores vacíos.
        total_ingreso (float): Ingreso Estimado Total para el porcentaje.
        orden_categorias (Optional[list[str]]): Orden fijo de las categorías.

    Returns:
        pd.DataFrame: Métricas por valor de la dimensión.
    """
    if (
        detalle_deudas is None
        or detalle_deudas.empty
        or columna not in detalle_deudas.columns
    ):
        return _tabla_vacia(COLUMNAS_TABLA_DIMENSION)

    serie = (
        detalle_deudas[columna]
        .fillna("")
        .astype(str)
        .str.strip()
        .replace("", etiqueta_vacio)
    )
    valores = serie.drop_duplicates().tolist()
    registros: list[dict[str, Any]] = []
    for valor in valores:
        filas = detalle_deudas[serie == valor]
        metricas = _metricas_desde_detalle_deudas(filas, total_ingreso)
        registros.append({"Valor": str(valor), **metricas})

    if not registros:
        return _tabla_vacia(COLUMNAS_TABLA_DIMENSION)

    tabla = pd.DataFrame(registros, columns=COLUMNAS_TABLA_DIMENSION)
    if orden_categorias:
        orden = {valor: indice for indice, valor in enumerate(orden_categorias)}
        tabla["_Orden"] = tabla["Valor"].map(orden).fillna(len(orden))
        tabla = tabla.sort_values(
            by=["_Orden", "Ingreso_Estimado", "Deudas"],
            ascending=[True, False, False],
        ).drop(columns=["_Orden"])
    else:
        tabla = tabla.sort_values(
            by=["Ingreso_Estimado", "Deudas", "Clientes", "Valor"],
            ascending=[False, False, False, True],
        )
    return tabla.reset_index(drop=True)

def calcular_cruce_oportunidad_estado(
    detalle_deudas: pd.DataFrame,
    *,
    columna_estado: str,
    etiqueta_vacio: str,
    conteo: str = "deudas",
) -> pd.DataFrame:
    """Cruza las oportunidades con un estado.

    Args:
        detalle_deudas (pd.DataFrame): Detalle con una fila por deuda.
        columna_estado (str): Columna del estado.
        etiqueta_vacio (str): Etiqueta para valores vacíos.
        conteo (str): ``deudas`` para contar deudas únicas por oportunidad y
            estado; ``clientes`` para contar clientes únicos.

    Returns:
        pd.DataFrame: Tabla con las oportunidades en las filas y los estados
        en las columnas.
    """
    if (
        detalle_deudas is None
        or detalle_deudas.empty
        or columna_estado not in detalle_deudas.columns
    ):
        return pd.DataFrame()

    base = detalle_deudas.copy()
    base[columna_estado] = (
        base[columna_estado]
        .fillna("")
        .astype(str)
        .str.strip()
        .replace("", etiqueta_vacio)
    )

    if conteo == "clientes":
        claves = ["Oportunidad", "Referencia", columna_estado]
        valores = "Referencia"
    elif conteo == "unidades":
        claves = ["Oportunidad", "Referencia", "Unidad_Id", columna_estado]
        valores = "Unidad_Id"
    else:
        claves = ["Oportunidad", "Referencia", "Id_Deuda", columna_estado]
        valores = "Id_Deuda"

    base = base.drop_duplicates(subset=claves)
    pivot = base.pivot_table(
        index="Oportunidad",
        columns=columna_estado,
        values=valores,
        aggfunc="count",
        fill_value=0,
    )
    orden_filas = [
        oportunidad for oportunidad in OPORTUNIDADES
        if oportunidad in pivot.index
    ]
    pivot = pivot.reindex(orden_filas).fillna(0).astype(int)
    pivot.columns.name = None
    return pivot.reset_index()

# --- Orquestador del Resumen ---
def _resumen_vacio() -> dict[str, Any]:
    """Devuelve la estructura vacía del resumen."""
    kpis = calcular_kpis_resumen(
        pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    )
    return {
        "kpis": kpis,
        "por_oportunidad": _tabla_vacia(COLUMNAS_TABLA_OPORTUNIDAD),
        "por_tipo_analisis": _tabla_vacia(COLUMNAS_TABLA_TIPO),
        "por_negociador": _tabla_vacia(COLUMNAS_TABLA_DIMENSION),
        "por_prospecto_credito": _tabla_vacia(COLUMNAS_TABLA_DIMENSION),
        "por_prospecto_tradicional": _tabla_vacia(COLUMNAS_TABLA_DIMENSION),
        "por_estado_pipeline": _tabla_vacia(COLUMNAS_TABLA_DIMENSION),
        "por_estado_actualizacion": _tabla_vacia(COLUMNAS_TABLA_DIMENSION),
        "por_banco": _tabla_vacia(COLUMNAS_TABLA_DIMENSION),
        "por_casa_cobro": _tabla_vacia(COLUMNAS_TABLA_DIMENSION),
        "por_tipo_unidad": _tabla_vacia(COLUMNAS_TABLA_DIMENSION),
        "por_rango_descuento": _tabla_vacia(COLUMNAS_TABLA_DIMENSION),
        "cruce_oportunidad_pipeline": pd.DataFrame(),
        "cruce_oportunidad_actualizacion": pd.DataFrame(),
        "detalle": _tabla_vacia(COLUMNAS_DETALLE),
        "detalle_deudas": _tabla_vacia(COLUMNAS_DETALLE_DEUDAS),
    }

def calcular_resumen_oportunidades(
    df: pd.DataFrame,
) -> dict[str, Any]:
    """Calcula todas las tablas y KPIs del panel de resumen.

    Args:
        df (pd.DataFrame): Resultado filtrado de oportunidades masivas.

    Returns:
        dict[str, Any]: KPIs, tablas por dimensión y detalles.
    """
    if df is None or df.empty:
        return _resumen_vacio()

    detalle = construir_detalle_oportunidades(df)
    detalle_deudas = construir_detalle_deudas_oportunidades(df, detalle)
    kpis = calcular_kpis_resumen(df, detalle, detalle_deudas)
    total_ingreso = _a_float(kpis.get("Ingreso_Estimado_Total"))

    dimensiones = {
        "por_negociador": (
            "Negociador", "Sin Negociador Asignado", None
        ),
        "por_prospecto_credito": (
            "Prospecto_Credito", "N/A", None
        ),
        "por_prospecto_tradicional": (
            "Prospecto_Tradicional", "N/A", None
        ),
        "por_estado_pipeline": (
            "Estado_Pipeline", "Sin registro en Pipeline", None
        ),
        "por_estado_actualizacion": (
            "Estado_Actualizacion", "Sin actualización", None
        ),
        "por_banco": ("Banco_Resumen", "Sin banco", None),
        "por_casa_cobro": (
            "Casa_Cobro_Resumen", "Sin casa de cobro", None
        ),
        "por_tipo_unidad": ("Tipo_Unidad", "Deuda individual", None),
        "por_rango_descuento": (
            "Rango_Descuento", "0%", RANGOS_DESCUENTO
        ),
    }
    tablas_dimension = {
        clave: calcular_resumen_por_dimension(
            detalle_deudas,
            columna=columna,
            etiqueta_vacio=etiqueta_vacio,
            total_ingreso=total_ingreso,
            orden_categorias=orden_categorias,
        )
        for clave, (columna, etiqueta_vacio, orden_categorias)
        in dimensiones.items()
    }

    return {
        "kpis": kpis,
        "por_oportunidad": calcular_resumen_por_oportunidad(
            detalle, detalle_deudas, total_ingreso
        ),
        "por_tipo_analisis": calcular_resumen_por_tipo_analisis(
            detalle, detalle_deudas, total_ingreso
        ),
        **tablas_dimension,
        "cruce_oportunidad_pipeline": calcular_cruce_oportunidad_estado(
            detalle_deudas,
            columna_estado="Estado_Pipeline",
            etiqueta_vacio="Sin registro en Pipeline",
            conteo="clientes",
        ),
        "cruce_oportunidad_actualizacion": calcular_cruce_oportunidad_estado(
            detalle_deudas,
            columna_estado="Estado_Actualizacion",
            etiqueta_vacio="Sin actualización",
            conteo="deudas",
        ),
        "detalle": detalle,
        "detalle_deudas": detalle_deudas,
    }
