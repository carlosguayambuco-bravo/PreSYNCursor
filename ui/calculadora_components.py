# Estándar usando PEP8
# Librerías de Python
from typing import Any, Optional
# Librerías de Terceros
import numpy as np
import streamlit as st
# Librerías Locales
from data.data_loader import load_client_balances
from modules.constants import (
    COLORES_OPORTUNIDADES,
    DESCRIPCION_OPORTUNIDADES,
    ICONOS_OPORTUNIDADES,
    IVA,
    OPORTUNIDADES,
)
from modules.gest_sols import (
    distribuir_monto_por_deuda,
    get_descuento_en_base,
    obtener_valor_pab_ideal,
)
from modules.oportunidades import (
    calcular_oportunidades_referencia,
    evaluar_viabilidad_cliente,
    obtener_asignacion_para_referencia,
    obtener_estado_actual_credito,
    obtener_estado_liquidacion_deudas,
    obtener_pab_actualizado_deuda,
    obtener_pricing_para_referencia,
    obtener_prospecto_credito_para_referencia,
    obtener_prospecto_tradicional_para_deuda,
    obtener_prospecto_tradicional_para_referencia,
    obtener_referencias_habilitadas,
    obtener_ultima_actualizacion_deuda,
    registrar_opp_individual,
)
from ui.forms_components import mostrar_componente_feedback
from utils.helpers_general import cleanNumber, formatNumber

# --- Configuración visual de la lista de deudas ---
# Alto máximo (px) de la lista de deudas. El usuario puede ajustarlo.
ALTO_MAXIMO_LISTA_DEUDAS = 600
# Alto estimado (px) de cada fila de deuda para calcular el espacio sobrante.
ALTO_ESTIMADO_FILA_DEUDA = 300
# Alto mínimo (px) para mostrar el bloque "Espacio para Reflexionar".
ALTO_MINIMO_ESPACIO_REFLEXION = 60

# Función Auxiliar para Normalizar un Id de Deuda en la UI
def _normalizar_id_deuda_ui(valor: Any) -> str:
    """Normaliza un Id de Deuda para usarlo como llave de diccionario."""
    return str(valor).replace(".0", "").strip()

# Función Auxiliar para Saber si el Usuario Actual es Admin
def _usuario_es_admin() -> bool:
    """Devuelve True si el usuario de la sesión tiene rol admin."""
    user_obj = st.session_state.get("user_obj", None)
    if user_obj is not None and hasattr(user_obj, "is_admin"):
        try:
            return bool(user_obj.is_admin())
        except Exception:
            pass
    return st.session_state.get("user_role", None) == "admin"

# Función Auxiliar para Mostrar el Bloque de Espacio para Reflexionar
def _mostrar_espacio_para_reflexion(*, alto: int) -> None:
    """Muestra un bloque con gradiente azul que llena el espacio sobrante."""
    st.markdown(
        (
            '<div style="height:{alto}px; min-height:{alto}px; border-radius:12px; '
            'background:linear-gradient(180deg,#e3f2fd 0%,#64b5f6 45%,#0d47a1 100%); '
            'display:flex; align-items:center; justify-content:center; '
            'color:#ffffff; font-weight:800; letter-spacing:.5px; '
            'text-shadow:0 1px 3px rgba(0,0,0,.35); font-size:.95rem; '
            'box-shadow:0 4px 14px rgba(13,71,161,.18);">'
            'Espacio para Reflexionar'
            '</div>'
        ).format(alto=int(alto)),
        unsafe_allow_html=True,
    )

# Función Auxiliar para Reiniciar la Selección de las Deudas
def reiniciar_seleccion_deudas(deudas: list[str], seleccionado: bool):
    for d in deudas:
        key_deuda_select = f"select_calc_ind_debt_{d}"
        st.session_state[key_deuda_select] = seleccionado

# Función Auxiliar para mostrar los Datos por Deuda de una Referencia en Específico
def mostrar_datos_por_deuda_referencia(referencia: str) -> list[str]:
    """Función para mostrar la escogencia de las Deudas. Para esto se muestran las siguientes columnas:
    - Selección de Deuda (Toggle)
    - Id_Deuda
    - Banco
    - PaB_Origen
    - Ultima Act

    Args:
        referencia (str): La Referencia que se seleccióno

    Returns:
        list[str]: Lista con las Deudas que se escogieron para analizar
    """
    # Primero Obtenemos los Datos de la Referencia Escogida
    datos_ref = obtener_asignacion_para_referencia(referencia)
    # Ordenamos los Datos por Banco y PaB_Origen
    datos_ref = datos_ref.sort_values(by=['Banco','PaB_Origen'])

    # Inicializamos las Llaves de Selección
    for d in datos_ref['Id_Deuda'].unique():
        key_deuda_select = f"select_calc_ind_debt_{d}"
        if not (key_deuda_select in st.session_state):
            st.session_state[key_deuda_select] = False

    # Creamos las Columnas para los Headers
    colSelect, colIdDebt, colBanco, colPaB, colAct = st.columns([1,2,2,2,3])
    with colSelect:
        st.markdown("**Seleccionar**")
    with colIdDebt:
        st.markdown("**Id de Deuda**")
    with colBanco:
        st.markdown("**Banco**")
    with colPaB:
        st.markdown("**Deuda Resuelve**")
    with colAct:
        st.markdown("**Última Actualización**")

    # Iteramos por cada uno de los datos
    for _, row in datos_ref.iterrows():
        # Creamos las Columnas para los Datos
        colSelect, colIdDebt, colBanco, colPaB, colAct = st.columns([1,2,2,2,3])
        # Vamos introduciendo los datos por columna
        key_deuda_select = "select_calc_ind_debt_{debt}".format(debt=row['Id_Deuda'])
        ultima_act_deuda = obtener_ultima_actualizacion_deuda(row['Id_Deuda'])
        prospecto_deuda = obtener_prospecto_tradicional_para_deuda(row['Id_Deuda'])

        with colSelect:
            st.toggle("Escogencia",key=key_deuda_select, label_visibility="collapsed")
        with colIdDebt:
            st.markdown("**{}**".format(row['Id_Deuda']))
            # Si la deuda es prospecto se agrega un st.caption
            if prospecto_deuda != "N/A":
                st.caption("🆔Prospecto Tradicional: **{}**".format(prospecto_deuda))
        with colBanco:
            st.write(row['Banco'])
        with colPaB:
            st.write("$ " +formatNumber(row['PaB_Origen']))
        with colAct:
            st.markdown(ultima_act_deuda)

    # Ahora Creamos 2 Botones: 1 para seleccionar todas y otra para deseleccionar todas
    colDeselectAll, colSelectAll = st.columns(2)
    deudas_unicas = list(datos_ref['Id_Deuda'].unique())

    with colDeselectAll:
        st.button(
            "**Deseleccionar Todas**",
            type="primary",
            width="stretch",
            icon="⛔",
            key = "deselect_all_debts_calc_ind",
            on_click=reiniciar_seleccion_deudas,
            kwargs={"deudas": deudas_unicas, "seleccionado": False}
        )

    with colSelectAll:
        st.button(
            "**Seleccionar Todas**",
            type="secondary",
            width="stretch",
            icon="🔅",
            key = "select_all_debts_calc_ind",
            on_click=reiniciar_seleccion_deudas,
            kwargs={"deudas": deudas_unicas, "seleccionado": True}
        )

    # Ahora obtenemos las deudas que estan seleccionadas
    deudas_seleccionadas = [
        debt for debt in deudas_unicas
        if st.session_state[f"select_calc_ind_debt_{debt}"]
    ]
    # Si no hay deudas Seleccionadas se detiene la selección y se muestra una alerta
    if not deudas_seleccionadas:
        st.warning("Selecciona al menos una deuda para continuar",icon="🚧")
        st.stop()
    # Devolvemos las Deudas y mostramos un st.caption de resumen
    st.caption("ℹ️Se seleccionaron {} de {} deudas ({:.0%})".format(
        len(deudas_seleccionadas),
        len(deudas_unicas),
        len(deudas_seleccionadas) / len(deudas_unicas)
    ))

    return deudas_seleccionadas

# Función para mostrar alertas de liquidación de deudas
def mostrar_alertas_liquidacion(*,deudas: list[str]):
    # Primero Obtenemos los estados de liquidación para cada deuda
    estados_liq = obtener_estado_liquidacion_deudas(deudas=deudas)
    # Ahora Iteramos y construimos el str con los baadges
    st.caption("✅Verificando que las deudas no esten liquidadas")
    str_badge = ""
    for idx, (d, is_liq) in enumerate(estados_liq.items(),start=1):

        str_badge += ":{color}-badge[ID: {debt_id} - **{liq_state}**]".format(
            color = "red" if is_liq else "green",
            debt_id = d,
            liq_state = "LIQUIDADA" if is_liq else "Sin Liq"
        )

        if idx % 5 == 0:
            if str_badge:
                st.markdown(str_badge)
                str_badge = ""

    # Mostramos si alguna falta
    if str_badge:
        st.markdown(str_badge)

    # Detenemos el App si hay alguna liquidada
    if any(estados_liq.values()):
        st.error("No puedes calcular datos para deudas liquidadas {}".format(
            "-".join([d for d, is_liq in estados_liq.items() if is_liq])
        ),icon="❌")
        st.stop()
    

# Función para mostrar alertas relacionadas con el cálculo por Crédito
def mostrar_alertas_credito(*, referencia: str, deudas: list[str]):
    # Primero inicializamos si ya se generó una alerta
    debtsIncumplir = []
    # Ahora iteramos por cada deuda
    with st.expander("⛔ Verificación de PaB Ideal desde Crédito", expanded=False):
        for d in deudas:
            pab_ideal = obtener_valor_pab_ideal(debt=d)
            if pab_ideal == 0:
                st.error("La Deuda <{}> NO CUENTA CON **PAB IDEAL**".format(d), icon="❌")
                debtsIncumplir += [d]
            else:
                st.success("Deuda <{}> tiene PaB Ideal de $ {:,.0f}".format(d,pab_ideal), icon = "✅")

    if debtsIncumplir:
        st.error(
            "**SIN PAB IDEAL PARA TODAS LAS DEUDAS**\n\n"
            "Las Deudas **{}** no tienen PaB ideal de crédito por lo que no se pueden analizar por este medio".format(
                ' - '.join(debtsIncumplir)
            ),
            icon="🚧"
        )
        st.stop()
    # Siguiente: Verificamos el Rechazo de Crédito
    status, rechazo, no_opp = obtener_estado_actual_credito(referencia=referencia)

    # Creamos 3 Columnas para Mostrar estos Datos
    colReferencia, colCred, colAlerta = st.columns([1,3,2])

    with colReferencia:
        st.metric(
            label="**Referencia**",
            value=referencia,
            delta=None
        )

    with colCred:
        str_cred = ":{color_status}-badge[{dato_status}]".format(
            color_status = "green" if status == "CERRADO" else ("gray" if not (rechazo or no_opp) else "red"),
            dato_status = status
        )
        # Agregamos detalle según rechazo o no_opp
        if rechazo:
            str_cred += " :{color_status}-badge[{dato_status}]".format(
                color_status = "yellow", dato_status = "⚠️CRÉDITO RECHAZADO"
            )
        if no_opp:
            str_cred += " :{color_status}-badge[{dato_status}]".format(
                color_status = "red", dato_status = "❌NO OPTA A CRÉDITO"
            )
        # Mostramos el Detalle
        st.markdown(str_cred)

    with colAlerta:
        if no_opp:
            st.error("Cliente no es Apto para Crédito", icon="❌")
            st.stop()
        elif rechazo:
            st.warning("Cliente ya había rechazado el crédito, aunque puede Salir 👍", icon="🚧")
        else:
            st.success("Cliente pasa precauciones de Crédito", icon="✅")

# Función Auxiliar para Formatear el Valor de una Oportunidad
def _formatear_valor_oportunidad(*, oportunidad: dict) -> str:
    valor = oportunidad.get("valor", 0)
    tipo_valor = oportunidad.get("tipo_valor", "texto")
    if tipo_valor == "monto":
        return "$ {}".format(formatNumber(valor))
    if tipo_valor == "porcentaje":
        return "{:.1%}".format(valor)
    return str(valor)

# Función para Mostrar las oportunidades
def mostrar_oportunidades_referencia(
    *,
    referencia: str,
    debts_selected: list[str],
    es_opp_cred: bool,
    ahorro: Optional[float],
    porcobrar: Optional[float],
    deposito_extra: float,
    pab_por_deuda: Optional[dict[str, float]] = None,
):
    """Muestra las oportunidades aplicables de una Referencia.

    Args:
        referencia (str): Referencia analizada.
        debts_selected (list[str]): Deudas seleccionadas.
        es_opp_cred (bool): True si el análisis es por Crédito.
        ahorro (Optional[float]): Ahorro simulado.
        porcobrar (Optional[float]): Por Cobrar simulado.
        deposito_extra (float): Depósito Extra simulado; hace parte del
            Ahorro Total y reduce el depósito requerido.
        pab_por_deuda (Optional[dict[str, float]]): PaB simulado por deuda
            desde los inputs de la calculadora.
    """
    # Primero calculamos todas las oportunidades de la Referencia
    with st.spinner("Calculando oportunidades..."):
        opps_cliente = calcular_oportunidades_referencia(
            referencia=referencia,
            deudas=debts_selected,
            es_opp_cred=es_opp_cred,
            ahorro=ahorro,
            porcobrar=porcobrar,
            deposito_extra=deposito_extra,
            pab_por_deuda=pab_por_deuda,
        )
    oportunidades_aplicables = [
        oportunidad for oportunidad in OPORTUNIDADES
        if opps_cliente.get(oportunidad, {}).get("aplica", False)
    ]

    # Mostramos un resumen de los insumos usados en el cálculo
    pab_simulado_total = sum(
        float((pab_por_deuda or {}).get(deuda, 0.0))
        for deuda in debts_selected
    )
    ahorro_total = (ahorro or 0) + max(deposito_extra or 0, 0)
    st.caption(
        "Análisis: **{}** | Ahorro: **\\$ {:,.0f}** | Depósito Extra: **\\$ {:,.0f}** | Ahorro Total: **\\$ {:,.0f}** | Por Cobrar: **\\$ {:,.0f}** | PaB simulado: **\\$ {:,.0f}**".format(
            "Crédito" if es_opp_cred else "Tradicional",
            ahorro or 0,
            deposito_extra or 0,
            ahorro_total,
            porcobrar or 0,
            pab_simulado_total,
        )
    )

    # Mostramos los badges de las oportunidades a la izquierda y el detalle a la derecha
    colRef, colDetalle = st.columns([1, 3], vertical_alignment="top", border=True)
    with colRef:
        st.metric(
            label="**Referencia**",
            value=referencia
        )
        if oportunidades_aplicables:
            for oportunidad in oportunidades_aplicables:
                st.badge(
                    oportunidad,
                    color=COLORES_OPORTUNIDADES[oportunidad],
                    icon=ICONOS_OPORTUNIDADES[oportunidad],
                )
        else:
            st.error("Sin Oportunidades", icon="❌")

    with colDetalle:
        colHNombre, colHDescripcion, colHValor = st.columns([1, 3, 2], vertical_alignment="top")
        with colHNombre:
            st.markdown("##### **🧮 Oportunidad**")
        with colHDescripcion:
            st.markdown("##### **❔¿Que significa?**")
        with colHValor:
            st.markdown("##### **🔅 Valor**")

        if not oportunidades_aplicables:
            st.info("No se detectaron oportunidades con los datos actuales.", icon="ℹ️")
            return

        for oportunidad in oportunidades_aplicables:
            resultado = opps_cliente[oportunidad]
            colNombre, colDescripcion, colValor = st.columns([1, 3, 2], vertical_alignment="top")

            with colNombre:
                st.badge(
                    oportunidad,
                    color=COLORES_OPORTUNIDADES[oportunidad],
                    icon=ICONOS_OPORTUNIDADES[oportunidad],
                )
            with colDescripcion:
                st.markdown(DESCRIPCION_OPORTUNIDADES[oportunidad])
            with colValor:
                st.markdown("**{}**".format(_formatear_valor_oportunidad(oportunidad=resultado)))
                if resultado.get("detalle"):
                    st.caption(resultado["detalle"])

# Funciones Auxiliares para Sincronizar los Controles de una Deuda
def _formatear_pab_texto(pab: float) -> str:
    """Formatea un PaB para mostrarlo en un text_input."""
    return "{:,.0f}".format(pab)

def _formatear_descuento_texto(descuento: float) -> str:
    """Formatea un descuento decimal como porcentaje para un text_input."""
    return "{:.1f}".format(descuento * 100)

def _calcular_pab_desde_descuento(*, pab_origen: float, descuento_pct: float) -> float:
    """Calcula el PaB a partir de un descuento porcentual."""
    descuento_pct = min(max(float(descuento_pct), 0.0), 100.0)
    return max(0.0, pab_origen * (1 - descuento_pct / 100.0))

def _calcular_descuento_desde_pab(*, pab_origen: float, pab: float) -> float:
    """Calcula el descuento decimal a partir de un PaB."""
    if pab_origen <= 0:
        return 0.0
    return min(max(1 - (pab / pab_origen), 0.0), 1.0)

def _paso_slider_pab(pab_origen: float) -> float:
    """Define un paso razonable para el slider de PaB según el monto."""
    if pab_origen >= 10_000_000:
        return 100_000.0
    if pab_origen >= 1_000_000:
        return 10_000.0
    if pab_origen >= 100_000:
        return 1_000.0
    if pab_origen >= 10_000:
        return 100.0
    return 1.0

# Función Auxiliar para Limpiar el Monto del Portafolio
def _limpiar_monto_portafolio(valor: Any) -> tuple[float, bool]:
    """Limpia un monto de portafolio y devuelve si el valor era numérico."""
    monto = cleanNumber(valor, default_nan=np.nan)
    try:
        monto_float = float(monto)
    except (TypeError, ValueError):
        return 0.0, False
    if np.isnan(monto_float):
        return 0.0, False
    return monto_float, True

# Función Auxiliar para Sincronizar el Total del Portafolio con las Deudas
def _sincronizar_total_portafolio(
    *,
    session_state,
    clave_total: str,
    clave_deudas: str,
    deudas: list[str],
    pab_total: float,
) -> None:
    """Inicializa o recalcula el total cuando cambia el conjunto de deudas."""
    deudas_actuales = tuple(
        sorted(_normalizar_id_deuda_ui(d) for d in deudas)
    )
    if (
        session_state.get(clave_deudas) != deudas_actuales
        or clave_total not in session_state
    ):
        session_state[clave_deudas] = deudas_actuales
        session_state[clave_total] = "{:,.0f}".format(pab_total)

# Función Auxiliar para Distribuir un Monto de Portafolio por PaB_Origen
def _distribuir_portafolio_por_pab_origen(
    *,
    deudas: list[str],
    pab_origen_por_deuda: dict[str, float],
    monto_total: float,
) -> dict[str, float]:
    """Distribuye un monto total entre las deudas usando SIEMPRE el PaB_Origen.

    Se reutiliza ``distribuir_monto_por_deuda`` sin aliado, de modo que la
    función toma ``montos_actuales`` (aquí el PaB_Origen) como pesos.
    """
    montos_actuales = {
        _normalizar_id_deuda_ui(deuda): float(pab_origen_por_deuda.get(
            _normalizar_id_deuda_ui(deuda), 0.0
        ))
        for deuda in deudas
    }
    resultado = distribuir_monto_por_deuda(
        deudas=[_normalizar_id_deuda_ui(deuda) for deuda in deudas],
        montos_actuales=montos_actuales,
        monto_total=monto_total,
        aliado=None,
    )
    return {
        _normalizar_id_deuda_ui(deuda): float(monto)
        for deuda, monto in resultado.get("montos", {}).items()
    }

# Función Auxiliar para Aplicar el Monto de Portafolio a las Deudas
def _aplicar_monto_portafolio(
    *,
    clave_total: str,
    deudas: list[str],
    pab_origen_por_deuda: dict[str, float],
    modo: str,
) -> None:
    """Callback: distribuye el monto total y actualiza los PaB de cada deuda."""
    texto = st.session_state.get(clave_total, "")
    monto_total, es_valido = _limpiar_monto_portafolio(texto)
    if not es_valido or monto_total <= 0:
        return

    montos = _distribuir_portafolio_por_pab_origen(
        deudas=deudas,
        pab_origen_por_deuda=pab_origen_por_deuda,
        monto_total=monto_total,
    )

    for deuda in deudas:
        deuda_norm = _normalizar_id_deuda_ui(deuda)
        pab = max(float(montos.get(deuda_norm, 0.0)), 0.0)
        pab_origen = max(float(pab_origen_por_deuda.get(deuda_norm, 0.0)), 0.0)
        clave = "{}_{}".format(modo, deuda)
        descuento = _calcular_descuento_desde_pab(pab_origen=pab_origen, pab=pab)
        st.session_state[f"calc_ind_pab_{clave}"] = pab
        st.session_state[f"calc_ind_pab_slider_{clave}"] = pab
        st.session_state[f"calc_ind_pab_text_{clave}"] = _formatear_pab_texto(pab)
        st.session_state[f"calc_ind_disc_slider_{clave}"] = descuento * 100
        st.session_state[f"calc_ind_disc_text_{clave}"] = _formatear_descuento_texto(descuento)

def _sincronizar_desde_slider_descuento(*, clave: str, pab_origen: float):
    """Sincroniza los controles cuando cambia el slider de descuento."""
    descuento_pct = float(st.session_state.get(f"calc_ind_disc_slider_{clave}", 0.0))
    pab = _calcular_pab_desde_descuento(pab_origen=pab_origen, descuento_pct=descuento_pct)
    st.session_state[f"calc_ind_pab_{clave}"] = pab
    st.session_state[f"calc_ind_pab_slider_{clave}"] = pab
    st.session_state[f"calc_ind_pab_text_{clave}"] = _formatear_pab_texto(pab)
    st.session_state[f"calc_ind_disc_text_{clave}"] = _formatear_descuento_texto(descuento_pct / 100.0)

def _sincronizar_desde_slider_pab(*, clave: str, pab_origen: float):
    """Sincroniza los controles cuando cambia el slider de PaB."""
    pab = float(st.session_state.get(f"calc_ind_pab_slider_{clave}", 0.0))
    # El PaB puede superar el Origen si el portafolio distribuido es mayor al DUM
    pab = max(pab, 0.0)
    descuento = _calcular_descuento_desde_pab(pab_origen=pab_origen, pab=pab)
    st.session_state[f"calc_ind_pab_{clave}"] = pab
    st.session_state[f"calc_ind_disc_slider_{clave}"] = descuento * 100
    st.session_state[f"calc_ind_disc_text_{clave}"] = _formatear_descuento_texto(descuento)
    st.session_state[f"calc_ind_pab_text_{clave}"] = _formatear_pab_texto(pab)

def _sincronizar_desde_texto_descuento(*, clave: str, pab_origen: float):
    """Sincroniza los controles cuando cambia el text_input de descuento."""
    texto = st.session_state.get(f"calc_ind_disc_text_{clave}", "0")
    descuento_pct = cleanNumber(texto, default_nan=np.nan)
    if np.isnan(descuento_pct):
        pab_actual = float(st.session_state.get(f"calc_ind_pab_{clave}", pab_origen))
        descuento_pct = _calcular_descuento_desde_pab(pab_origen=pab_origen, pab=pab_actual) * 100
    descuento_pct = min(max(float(descuento_pct), 0.0), 100.0)
    pab = _calcular_pab_desde_descuento(pab_origen=pab_origen, descuento_pct=descuento_pct)
    st.session_state[f"calc_ind_pab_{clave}"] = pab
    st.session_state[f"calc_ind_pab_slider_{clave}"] = pab
    st.session_state[f"calc_ind_disc_slider_{clave}"] = descuento_pct
    st.session_state[f"calc_ind_pab_text_{clave}"] = _formatear_pab_texto(pab)
    st.session_state[f"calc_ind_disc_text_{clave}"] = _formatear_descuento_texto(descuento_pct / 100.0)

def _sincronizar_desde_texto_pab(*, clave: str, pab_origen: float):
    """Sincroniza los controles cuando cambia el text_input de PaB."""
    texto = st.session_state.get(f"calc_ind_pab_text_{clave}", "0")
    pab = cleanNumber(texto, default_nan=np.nan)
    if np.isnan(pab):
        pab = float(st.session_state.get(f"calc_ind_pab_{clave}", pab_origen))
    # El PaB puede superar el Origen si el portafolio distribuido es mayor al DUM
    pab = max(float(pab), 0.0)
    descuento = _calcular_descuento_desde_pab(pab_origen=pab_origen, pab=pab)
    st.session_state[f"calc_ind_pab_{clave}"] = pab
    st.session_state[f"calc_ind_pab_slider_{clave}"] = pab
    st.session_state[f"calc_ind_disc_slider_{clave}"] = descuento * 100
    st.session_state[f"calc_ind_disc_text_{clave}"] = _formatear_descuento_texto(descuento)
    st.session_state[f"calc_ind_pab_text_{clave}"] = _formatear_pab_texto(pab)

# Función Auxiliar para Obtener el PaB Inicial de una Deuda
def _obtener_pab_inicial_deuda(*, deuda: str, pab_origen: float) -> float:
    """Obtiene el PaB inicial de una deuda: su descuento actual.

    Si la deuda no tiene una actualización confiable, o el PaB_Actualizado
    confiable viene en 0, se devuelve el ``PaB_Origen`` (0% de descuento),
    nunca el PaB Ideal de Crédito ni un PaB en 0.
    """
    pab_inicial = obtener_pab_actualizado_deuda(deuda, pab_origen=pab_origen)
    if pab_origen > 0 and pab_inicial <= 0:
        return float(pab_origen)
    return float(pab_inicial)

# Función Auxiliar para Mostrar la Selección de una Deuda
def mostrar_seleccion_deuda(
    *,
    deuda: str,
    pab_origen: float,
    init_pab: Optional[float],
    pricing: float,
    modo: str,
) -> float:
    """Función para mostrar la selección de una deuda.

    Muestra el ID, el DUM (PaB_Origen), sliders sincronizados de Descuento y
    PaB, inputs manuales de Descuento y PaB, el ingreso que dejaría la deuda y
    un popover con los descuentos en base de alianzas. El PaB puede superar el
    PaB_Origen cuando el portafolio distribuido es mayor al DUM.

    Args:
        deuda (str): El Id de la Deuda Seleccionada.
        pab_origen (float): El PaB_Origen (DUM) de la deuda.
        init_pab (Optional[float]): El PaB inicial a tomar.
        pricing (float): El Pricing de la Referencia.
        modo (str): "tradicional" o "credito"; se usa para aislar el estado.

    Returns:
        float: El Pago por la Deuda.
    """
    # Paso 1: Validar el PaB_Origen
    pab_origen = max(float(pab_origen), 0.0)
    if pab_origen <= 0:
        st.warning("La deuda <{}> no tiene un PaB_Origen válido.".format(deuda), icon="⚠️")
        return 0.0

    # Paso 2: Inicializar el estado de la deuda
    clave = "{}_{}".format(modo, deuda)
    if init_pab is None:
        init_pab = pab_origen
    else:
        init_pab = max(float(init_pab), 0.0)
        # Si no hay descuento actual, el PaB inicial debe ser el Origen
        if init_pab <= 0 and pab_origen > 0:
            init_pab = pab_origen
        init_pab = min(init_pab, pab_origen)
    key_init = f"calc_ind_init_{clave}"
    if st.session_state.get(key_init) != init_pab:
        descuento_inicial = _calcular_descuento_desde_pab(pab_origen=pab_origen, pab=init_pab)
        st.session_state[key_init] = init_pab
        st.session_state[f"calc_ind_pab_{clave}"] = init_pab
        st.session_state[f"calc_ind_disc_{clave}"] = descuento_inicial
        st.session_state[f"calc_ind_pab_slider_{clave}"] = init_pab
        st.session_state[f"calc_ind_disc_slider_{clave}"] = descuento_inicial * 100
        st.session_state[f"calc_ind_pab_text_{clave}"] = _formatear_pab_texto(init_pab)
        st.session_state[f"calc_ind_disc_text_{clave}"] = _formatear_descuento_texto(descuento_inicial)

    # Paso 3: Leer el estado final y crear las columnas
    pab_final = float(st.session_state[f"calc_ind_pab_{clave}"])
    descuento_final = _calcular_descuento_desde_pab(pab_origen=pab_origen, pab=pab_final)
    ingreso = max((pab_origen - pab_final) * float(pricing), 0.0)
    # El slider debe permitir el PaB distribuido aunque supere el Origen
    max_pab_slider = max(float(pab_origen), max(pab_final, 0.0))

    colIdDum, colSliders, colManual, colDiscPayment, colIngreso = st.columns(
        [2, 3, 1, 2, 2], vertical_alignment="center", gap="small"
    )

    with colIdDum:
        st.metric(
            label="🆔Id Deuda",
            value=deuda
        )
        st.caption("DUM: **$ {}**".format(formatNumber(pab_origen)))
        if modo == "credito":
            # Mostramos También el PaB_Ideal
            st.caption("PaB Ideal de Crédito: **{}**".format(formatNumber(
                obtener_valor_pab_ideal(debt = deuda) 
            )))

        # Mostramos los Descuentos en Base de Alianzas para Comparación
        try:
            descuentos_base = get_descuento_en_base(
                debt=deuda,
                original_amount=pab_origen,
                show_casa=_usuario_es_admin(),
            )
        except Exception:
            descuentos_base = []
        with st.popover(
            "💼 Descuentos en Base",
            help="Descuentos actuales de alianzas para comparar y copiar al input de PaB.",
        ):
            if descuentos_base:
                st.caption("Copia el valor y pégalo en **PaB ($)**.")
                for descuento in descuentos_base:
                    st.markdown(descuento)
            else:
                st.info("No hay descuentos en base para esta deuda.", icon="ℹ️")

    with colSliders:
        st.slider(
            label="**Descuento (%)**",
            min_value=0.0,
            max_value=100.0,
            step=0.5,
            key=f"calc_ind_disc_slider_{clave}",
            on_change=_sincronizar_desde_slider_descuento,
            kwargs={"clave": clave, "pab_origen": pab_origen},
        )
        st.slider(
            label="**PaB ($)**",
            min_value=0.0,
            max_value=max_pab_slider,
            step=min(_paso_slider_pab(pab_origen), max(max_pab_slider, 1.0)),
            key=f"calc_ind_pab_slider_{clave}",
            on_change=_sincronizar_desde_slider_pab,
            kwargs={"clave": clave, "pab_origen": pab_origen},
        )

    with colManual:
        st.text_input(
            label="**Descuento (%)**",
            key=f"calc_ind_disc_text_{clave}",
            on_change=_sincronizar_desde_texto_descuento,
            kwargs={"clave": clave, "pab_origen": pab_origen},
        )
        st.text_input(
            label="**PaB ($)**",
            key=f"calc_ind_pab_text_{clave}",
            on_change=_sincronizar_desde_texto_pab,
            kwargs={"clave": clave, "pab_origen": pab_origen},
        )

    with colDiscPayment:
        st.metric(
            label="**✅ %Descuento**",
            value="{:.1%}".format(descuento_final)
        )
        st.metric(
            label="**💵 PaB**",
            value="${:,.0f}".format(pab_final)
        )

    with colIngreso:
        st.metric(
            label="**😁 Ingreso**",
            value="$ {}".format(formatNumber(ingreso)),
            delta="$ {} con IVA".format(formatNumber(ingreso * IVA)),
        )

    # Por último devolvemos el PaB final
    return pab_final

# Función para mostrar la calculadora individual
def mostrar_calculadora_individual(): 
    st.subheader("😁 Calculadora Individual por Referencia")

    # Mostramos un Selector de la Referencia, con otras 3 columnas para ahorro Neto, Pricing y Prospectos
    refs_habilitadas = obtener_referencias_habilitadas()

    colRef, colAhorro, colPricing, colProspectos = st.columns([2, 1, 1, 2])
    with colRef:
        ref_escogida = st.selectbox(
            "**😁 Referencia a Analizar**",
            options=refs_habilitadas,
            index=None,
            help=(
                "Selecciona la Referencia que deseas analizar. "
                "Solo se muestran las Referencias habilitadas para tu usuario."
            ),
            key="selectbox_referencia_calc_ind"
        )
        st.caption("Si no te sale la Ref es porque no estuvó asignada :(")

    if ref_escogida is None:
        st.info("Escoge una Referencia para Continuar",icon="ℹ️")
        st.stop()

    with colAhorro:
        # Traemos los Datos de la Referencia Escogida
        saldosDict = load_client_balances()
        # Obtenemos el Ahorro y el Por Cobrar del Cliente
        ahorro = saldosDict['Saldos'][ref_escogida]
        porcobrar = saldosDict['PorCobrar'][ref_escogida]
        ahorro_neto = ahorro - porcobrar
        st.metric(
            label="💰 Ahorro Neto",
            value=f"${ahorro_neto:,.0f}",
            delta=f"\\${ahorro:,.0f} - \\${porcobrar:,.0f}",
            delta_color="red" if ahorro_neto <=0 else "green",
            delta_arrow="down" if ahorro_neto <=0 else "up",
        )

    with colPricing:
        pricing_ref = obtener_pricing_para_referencia(ref_escogida)
        st.metric(
            label="💲 Pricing",
            value=f"{pricing_ref:,.0%}",
            delta="Pricing" if pricing_ref > 0.15 else "Tradicional",
            delta_color="normal"
        )

    with colProspectos:
        # Obtenemos los Prospectos de Crédito y Tradicional
        prosp_cred = obtener_prospecto_credito_para_referencia(ref_escogida)
        prosp_trad = obtener_prospecto_tradicional_para_referencia(ref_escogida)
        # Ahora los mostramos
        st.badge(
            f"Batch: **{prosp_cred}**", color="green" if prosp_cred != "Tradicional" else "gray"
        )
        st.badge(
            f"Prospecto Tradicional: **{prosp_trad}**", color="blue" if prosp_trad != "N/A" else "gray"
        )

    # Mostramos los Datos de Selección de Deudas
    debts_selected = mostrar_datos_por_deuda_referencia(ref_escogida)

    # Mostramos la alerta de las deudas
    mostrar_alertas_liquidacion(deudas = debts_selected)

    st.divider()

    # Escoger el Tipo de Análisis: Por Crédito o Tradicional
    tipo_analisis = st.radio(
        label="**🧮 Tipo de Análisis a Realizar**",
        options=[
            "**Por Tradicional**",
            "**Por Crédito**"
        ],
        captions=[
            "El Análisis se realiza con el Ahorro del Cliente",
            "El Análisis se realiza con el PAB Ideal que otorga Crédito",
        ],
        horizontal=True,
        key="select_analysis_calc_ind",
        index=1 if "parcial" in prosp_cred.lower() else (0 if prosp_cred == "Tradicional" else None),
        disabled= (prosp_cred == "Tradicional") or ("parcial" in prosp_cred.lower()),
    )

    if tipo_analisis is None:
        st.stop()

    opp_credito = (not ("Tradicional" in tipo_analisis))

    # En caso de ser Crédito, debe de existir un PaB Ideal, de lo contrario se muestra una alerta
    if opp_credito:
        mostrar_alertas_credito(referencia=ref_escogida,deudas=debts_selected)

    # Agregamos un Botón de Continuar
    continuar_opp_calc = st.button(
        label="**Continuar con Cálculo**",
        type="primary",
        width="stretch",
        key="button_continuar_calc_opps",
        icon="🔅"
    )
    llave_continuar_opp_ref = f'continuar_calc_opp_{ref_escogida}'

    if continuar_opp_calc:
        st.session_state[llave_continuar_opp_ref] = True

    if not st.session_state.get(llave_continuar_opp_ref,False):
        st.stop()

    st.divider()

    # Creamos las Configuraciones Iniciales (para el Feedback)
    configs = {
        "Referencia": ref_escogida,
        "Deudas": debts_selected
    }

    # Guardamos la Oportunidad
    registrar_opp_individual(
        referencia=ref_escogida,
        deudas=debts_selected,
        tipo_analisis=tipo_analisis
    )

    # Creamos 3 Columnas: Columna Ahorro, Columna Por Cobrar y Columna Depósito Extra
    colAhorroInput, colPorCobrarInput, colDEInput = st.columns(3, border=True)
    # Inicalizamos Valores
    dictInitInputs = {
        f"ahorro_input_{ref_escogida}_calc_opps": ahorro,
        f"porcobrar_input_{ref_escogida}_calc_opps": porcobrar,
        f"dep_extra_input_{ref_escogida}_calc_opps": 0,
    }
    for key, val in dictInitInputs.items():
        if not (key in st.session_state):
            st.session_state[key] = val
        # Ahora los Actualizamos limpiandolos
        cleanedVal = cleanNumber(st.session_state[key], default_nan=np.nan)
        # Verificamos si es un NaN
        if np.isnan(cleanedVal):
            st.error("No se puede convertir el valor {} a Númerico".format(st.session_state[key]))
            cleanedVal = 0
        # Actualizamos la llave (sin el ajuste de 999/001 de formatNumber)
        st.session_state[key] = "{:,.0f}".format(cleanedVal)

        # Agregamos los Valores a la Configuración
        name_input = key[:key.index("_input")]
        configs[name_input] = cleanedVal

    # Ahora Mostramos los inputs
    with colAhorroInput:
        ahorro_input = st.text_input(
            label="**💵 Ahorro**",
            key = f"ahorro_input_{ref_escogida}_calc_opps"
        )
    with colPorCobrarInput:
        porcobrar_input = st.text_input(
            label="**💼 Por Cobrar**",
            key = f"porcobrar_input_{ref_escogida}_calc_opps"
        )
    with colDEInput:
        dep_extra_input = st.text_input(
            label="**📈 Depósito Extra**",
            key = f"dep_extra_input_{ref_escogida}_calc_opps"
        )

    # Limpiamos los inputs numéricos para usarlos en los cálculos
    def _limpiar_input_numerico(valor, default):
        numero = cleanNumber(valor, default_nan=np.nan)
        if np.isnan(numero):
            st.error("No se puede convertir el valor {} a Númerico".format(valor))
            return float(default)
        return float(numero)

    ahorro_val = _limpiar_input_numerico(ahorro_input, ahorro)
    porcobrar_val = _limpiar_input_numerico(porcobrar_input, porcobrar)
    dep_extra_val = _limpiar_input_numerico(dep_extra_input, 0.0)
    st.caption(
        "💡 El **Depósito Extra** hace parte del ahorro disponible. "
        "Ahorro Total: **\\$ {:,.0f}**".format(
            ahorro_val + max(dep_extra_val, 0.0)
        )
    )

    # Actualizamos las Configuraciones con los valores finales de los inputs
    configs.update({
        "ahorro": ahorro_val,
        "porcobrar": porcobrar_val,
        "dep_extra": dep_extra_val,
        "Tipo_Analisis": "Crédito" if opp_credito else "Tradicional",
    })

    # Traemos el PaB_Origen de cada deuda seleccionada
    datos_ref = obtener_asignacion_para_referencia(ref_escogida).copy()
    mapa_pab_origen = {
        _normalizar_id_deuda_ui(row["Id_Deuda"]): float(row["PaB_Origen"])
        for _, row in datos_ref.iterrows()
    }
    pab_origen_por_deuda = {
        _normalizar_id_deuda_ui(d): float(mapa_pab_origen.get(
            _normalizar_id_deuda_ui(d), 0.0
        ))
        for d in debts_selected
    }

    # Mostramos una alerta para disminuir el tamaño
    st.info(
        "Para que puedas ver mejor la página, **debes de disminuir el tamaño y cerrar la pestaña lateral**",
        title="**Mejorar Vista**",
        icon="😁"
    )

    # Se crean 2 Columnas: Columna de Detalles de Deudas y Columna de Resultados
    colDetallesDeudas, colResultados = st.columns([4, 1], vertical_alignment="top", gap="small")

    pab_deudas = {}
    pab_ideal_deudas = {}

    with colDetallesDeudas:
        with st.container(height=ALTO_MAXIMO_LISTA_DEUDAS, border=False):
            for d in sorted(debts_selected):
                with st.container(border=True):
                    pab_origen_deuda = float(mapa_pab_origen.get(
                        _normalizar_id_deuda_ui(d), 0.0
                    ))
                    # El PaB inicial siempre refleja el descuento actual de la deuda.
                    # Si no hay actualización confiable, devuelve el PaB_Origen
                    # (0% de descuento), no el PaB Ideal.
                    init_pab = _obtener_pab_inicial_deuda(
                        deuda=d,
                        pab_origen=pab_origen_deuda,
                    )
                    pab_ideal_deudas[d] = (
                        obtener_valor_pab_ideal(debt=d) if opp_credito else 0.0
                    )

                    pab_deudas[d] = mostrar_seleccion_deuda(
                        deuda=d,
                        pab_origen=pab_origen_deuda,
                        init_pab=init_pab,
                        pricing=pricing_ref,
                        modo="credito" if opp_credito else "tradicional",
                    )

            # Si las deudas no llenan el alto máximo, mostramos el espacio restante
            alto_contenido = len(debts_selected) * ALTO_ESTIMADO_FILA_DEUDA
            alto_sobrante = ALTO_MAXIMO_LISTA_DEUDAS - alto_contenido
            if alto_sobrante >= ALTO_MINIMO_ESPACIO_REFLEXION:
                _mostrar_espacio_para_reflexion(alto=alto_sobrante)

    # Calculamos los totales y la viabilidad del cliente
    dum_total = sum(
        float(mapa_pab_origen.get(_normalizar_id_deuda_ui(d), 0.0))
        for d in debts_selected
    )
    pab_total = sum(pab_deudas.values())
    ingreso_total = sum(
        max(
            (
                float(mapa_pab_origen.get(_normalizar_id_deuda_ui(d), 0.0))
                - pab_deudas[d]
            ) * pricing_ref,
            0.0,
        )
        for d in debts_selected
    )
    pab_ideal_total = sum(pab_ideal_deudas.values())
    viabilidad = evaluar_viabilidad_cliente(
        pab_total=pab_total,
        pab_ideal_total=pab_ideal_total,
        ingreso_total=ingreso_total,
        ahorro=ahorro_val,
        por_cobrar=porcobrar_val,
        deposito_extra=dep_extra_val,
        es_opp_cred=opp_credito,
    )

    # Llave del input de monto total del portafolio (por Referencia y tipo de análisis)
    modo_analisis = "credito" if opp_credito else "tradicional"
    clave_total_portafolio = "portafolio_total_{}_{}_calc_opps".format(
        ref_escogida, modo_analisis
    )
    clave_deudas_portafolio = "portafolio_deudas_{}_{}_calc_opps".format(
        ref_escogida, modo_analisis
    )

    # Si cambió el conjunto de deudas seleccionadas, el total se recalcula
    # porque cambian las deudas y sus respectivos PaB.
    _sincronizar_total_portafolio(
        session_state=st.session_state,
        clave_total=clave_total_portafolio,
        clave_deudas=clave_deudas_portafolio,
        deudas=debts_selected,
        pab_total=pab_total,
    )

    # Limpiamos y formateamos el input igual que Ahorro, Por Cobrar y Depósito Extra
    valor_portafolio, portafolio_valido = _limpiar_monto_portafolio(
        st.session_state[clave_total_portafolio]
    )
    if not portafolio_valido:
        st.error(
            "No se puede convertir el valor {} a Númerico".format(
                st.session_state[clave_total_portafolio]
            )
        )
    st.session_state[clave_total_portafolio] = "{:,.0f}".format(valor_portafolio)

    with colResultados:
        with st.container(border=True):
            # El input de portafolio va primero para que sea accesible con muchas deudas
            st.text_input(
                label="**📦 Portafolio Total**",
                key=clave_total_portafolio,
                help=(
                    "Monto total para todas las deudas seleccionadas. Se distribuye "
                    "proporcionalmente al PaB_Origen de cada deuda y se recalcula al "
                    "cambiar la selección de deudas. No tiene tope: puede superar el "
                    "DUM total."
                ),
                on_change=_aplicar_monto_portafolio,
                kwargs={
                    "clave_total": clave_total_portafolio,
                    "deudas": debts_selected,
                    "pab_origen_por_deuda": pab_origen_por_deuda,
                    "modo": modo_analisis,
                },
            )
            st.caption("Distribución por **PaB_Origen**.")
            st.divider()

            # Mostramos Dum Total, PaB, Ingreso, Pago Total del Cliente y si es Viable
            st.metric(
                label="**💰 DUM Total**",
                value="$ {}".format(formatNumber(dum_total)),
            )
            st.metric(
                label="**💵 PaB**",
                value="$ {}".format(formatNumber(pab_total)),
            )
            st.metric(
                label="**😁 Ingreso**",
                value="$ {}".format(formatNumber(ingreso_total)),
                delta="$ {} con IVA".format(formatNumber(ingreso_total * IVA)),
            )
            st.metric(
                label="**ℹ️ Pago Total**",
                value="$ {}".format(formatNumber(viabilidad["pago_total"])),
                help="Incluye comisión con IVA y los $20.000 adicionales.",
            )
            st.metric(
                label="**❔Es Viable**",
                value="Viable 😁" if viabilidad["viable"] else "❌ No Viable",
            )
            st.caption("Tradicional: {} | Crédito: {}".format(
                "✅" if viabilidad["viable_tradicional"] else "❌",
                ("✅" if viabilidad["viable_credito"] else "❌") if opp_credito else "N/A",
            ))

    # Agregamos los resultados a las Configuraciones
    configs.update({
        "Pab_Deudas": pab_deudas,
        "Pab_Total": pab_total,
        "DUM_Total": dum_total,
        "Ingreso_Total": ingreso_total,
        "Pago_Total": viabilidad["pago_total"],
        "Es_Viable": viabilidad["viable"],
    })

    st.divider()
    # Mostramos las Oportunidades de la Referencia
    mostrar_oportunidades_referencia(
        referencia=ref_escogida,
        debts_selected=debts_selected,
        es_opp_cred=opp_credito,
        ahorro=ahorro_val,
        porcobrar=porcobrar_val,
        deposito_extra=dep_extra_val,
        pab_por_deuda=pab_deudas,
    )

    st.divider()
    # Mostramos Componente de Feedback
    mostrar_componente_feedback(origin="Calculadora_Individual_Opps",configs=configs, type_container="container")