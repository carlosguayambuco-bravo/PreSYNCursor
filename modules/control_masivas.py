# Estándar usando Pep8
# Librerías de Python
from datetime import datetime
import json
import uuid
from typing import Any, Optional, get_args
# Librerías de Terceros
import numpy as np
import pandas as pd
# Librerías Locales
from modules.constants import CAMBIO_MASIVAS_COLUMNS, TIPOS_CONTRAOFERTAS

# Columnas del Reporte de Alertas de Distribución
ALERTAS_DISTRIBUCION_COLUMNS = [
    'Casa_Cobro',
    'Referencia',
    'Tipo_Alerta',
    'Detalle',
]

# Función Auxiliar para Normalizar una Fecha de Base
def _normalizar_fecha_base(valor: Any) -> pd.Timestamp:
    fecha = pd.to_datetime(valor, errors='coerce')
    if pd.isna(fecha):
        return pd.NaT
    return pd.Timestamp(fecha).normalize()

# Función Auxiliar para Formatear una Fecha en las Alertas de Distribución
def _formatear_fecha_alerta(valor: Any) -> str:
    fecha = pd.to_datetime(valor, errors='coerce')
    if pd.isna(fecha):
        return 'sin fecha'
    return pd.Timestamp(fecha).strftime('%d/%m/%Y')

# Función Auxiliar para Construir la Clave de una Base (Casa de Cobro + Fecha)
def obtener_clave_base(*, casa_cobro: Any, fecha_masiva: Any) -> tuple[str, pd.Timestamp]:
    return (
        str(casa_cobro or '').strip(),
        _normalizar_fecha_base(fecha_masiva),
    )

# Función Auxiliar para Convertir un Valor Escalar a Texto Limpio
def _texto_limpio(valor: Any) -> str:
    if valor is None:
        return ''
    try:
        if pd.isna(valor):
            return ''
    except (TypeError, ValueError):
        pass
    texto = str(valor).strip()
    return '' if texto.lower() in ('none', 'nan', '<na>', 'nat') else texto

# Función Auxiliar para Determinar si una Metadata está Completa
def metadata_masiva_completa(metadata: Any) -> bool:
    if not isinstance(metadata, dict):
        return False
    # La Metadata Mínima para Operar Requiere el UUID, el Tipo de Contraoferta y la Fecha Límite
    id_cruce = _texto_limpio(metadata.get('Id_Cruce'))
    tipo_contraoferta = metadata.get('Tipo_Contraoferta')
    fecha_limite = pd.to_datetime(metadata.get('Fecha_Limite_Uso'), errors='coerce')
    return bool(
        id_cruce
        and (tipo_contraoferta in get_args(TIPOS_CONTRAOFERTAS))
        and (not pd.isna(fecha_limite))
    )

# Función Auxiliar para Convertir la Metadata a un Diccionario Seguro
def _metadata_a_dict(metadata: Any) -> dict:
    if isinstance(metadata, dict):
        return dict(metadata)
    return {}

# Función Auxiliar para Obtener el PaB_Portafolio de Cada Fila (Columna o Metadata)
def _obtener_pab_portafolio(df: pd.DataFrame) -> pd.Series:
    if 'PaB_Portafolio' in df.columns:
        columna = pd.to_numeric(df['PaB_Portafolio'], errors='coerce')
    else:
        columna = pd.Series(np.nan, index=df.index, dtype='float64')
    if 'Metadata' in df.columns:
        metadata = df['Metadata'].apply(
            lambda m: m.get('PaB_Portafolio') if isinstance(m, dict) else np.nan
        )
        metadata = pd.to_numeric(metadata, errors='coerce')
    else:
        metadata = pd.Series(np.nan, index=df.index, dtype='float64')
    return columna.where(columna.notna(), metadata)

# Función Auxiliar para Normalizar los Valores de la Metadata antes de Compararla
def _normalizar_valor_metadata(valor: Any) -> Any:
    if isinstance(valor, dict):
        return {
            str(clave): _normalizar_valor_metadata(contenido)
            for clave, contenido in valor.items()
        }
    if isinstance(valor, (list, tuple, set)):
        return [_normalizar_valor_metadata(contenido) for contenido in valor]
    if isinstance(valor, (datetime, pd.Timestamp)):
        return pd.Timestamp(valor).strftime('%Y-%m-%d %H:%M:%S')
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float, np.integer, np.floating)):
        if pd.isna(valor):
            return None
        return float(valor)
    if isinstance(valor, str):
        return None if valor.strip().lower() in ('nan', '<na>', 'nat') else valor
    try:
        if pd.isna(valor):
            return None
    except (TypeError, ValueError):
        pass
    return valor

# Función Auxiliar para Serializar la Metadata y Poder Compararla
def _serializar_metadata(metadata: Any) -> str:
    if not isinstance(metadata, dict):
        return ''
    return json.dumps(
        _normalizar_valor_metadata(metadata),
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )

# Función Auxiliar para Comparar Dos Montos (incluyendo nulos)
def _montos_diferentes(antes: Any, despues: Any, tolerancia: float = 0.01) -> bool:
    antes_nulo = (antes is None) or pd.isna(antes)
    despues_nulo = (despues is None) or pd.isna(despues)
    if antes_nulo and despues_nulo:
        return False
    if antes_nulo != despues_nulo:
        return True
    try:
        return abs(float(antes) - float(despues)) > tolerancia
    except (TypeError, ValueError):
        return str(antes) != str(despues)

# Función Auxiliar para Construir la Columna de Agrupación de Portafolios
def _construir_grupo_col(df: pd.DataFrame) -> pd.Series:
    # La Marca Es_Portafolio y la Fecha No Forman Parte del Grupo: los Grupos se Detectan
    # Automáticamente y la Fecha se Controla desde el Alcance Seleccionado en la Vista.
    # Así, una Base Subida por Partes en Fechas Distintas se Distribuye como una Sola Base.
    return (
        'Masiva_'
        + df['Referencia'].fillna('').astype(str).str.strip()
        + '_'
        + df['Casa_Cobro'].fillna('').astype(str).str.strip()
    )

# Función para Completar la Metadata de las Filas que no la Tienen
def completar_metadata_masivas(
    df: pd.DataFrame,
    configs_por_base: dict[tuple[str, pd.Timestamp], dict],
) -> pd.DataFrame:
    """Completa la Metadata de las filas que no la tienen.

    La configuración se define por base (Casa_Cobro + Fecha_Masiva). Las filas que ya
    tienen una Metadata completa se conservan sin cambios. Para las filas incompletas
    se genera un UUID si no existe y se completan los campos faltantes.
    """
    df = df.copy()
    if df.empty:
        return df

    def _completar(fila: pd.Series) -> dict:
        metadata = _metadata_a_dict(fila.get('Metadata'))
        if metadata_masiva_completa(metadata):
            return metadata

        clave = obtener_clave_base(
            casa_cobro=fila.get('Casa_Cobro'),
            fecha_masiva=fila.get('Fecha_Masiva'),
        )
        config = configs_por_base.get(clave)
        if config is None:
            raise ValueError(
                "No hay configuración de metadata para la base {} del {}.".format(
                    clave[0], clave[1].strftime('%Y-%m-%d') if pd.notna(clave[1]) else 'SIN FECHA'
                )
            )

        id_cruce = _texto_limpio(metadata.get('Id_Cruce')) or str(uuid.uuid4())
        tipo_contraoferta = metadata.get('Tipo_Contraoferta')
        if tipo_contraoferta not in get_args(TIPOS_CONTRAOFERTAS):
            tipo_contraoferta = config.get('Tipo_Contraoferta')
        fecha_limite = pd.to_datetime(metadata.get('Fecha_Limite_Uso'), errors='coerce')
        if pd.isna(fecha_limite):
            fecha_limite = _normalizar_fecha_base(config.get('Fecha_Limite_Uso'))
        alias = _texto_limpio(metadata.get('Alias'))
        if not alias:
            alias = _texto_limpio(config.get('Alias')) or None

        # Preservar el PaB_Portafolio existente (Metadata o Columna) al Completar la Metadata
        pab_portafolio = metadata.get('PaB_Portafolio')
        if pab_portafolio is None:
            pab_portafolio = fila.get('PaB_Portafolio')
        pab_portafolio = pd.to_numeric(pab_portafolio, errors='coerce')
        if pd.isna(pab_portafolio):
            pab_portafolio = None
        else:
            pab_portafolio = float(pab_portafolio)

        return {
            'Id_Cruce': id_cruce,
            'Tipo_Contraoferta': tipo_contraoferta,
            'Fecha_Limite_Uso': pd.Timestamp(fecha_limite) if not pd.isna(fecha_limite) else None,
            'Alias': alias,
            'Id_Portafolio': str(metadata.get('Id_Portafolio') or ''),
            'PaB_Portafolio': pab_portafolio,
        }

    df['Metadata'] = df.apply(_completar, axis=1)
    return df

# Función Auxiliar para Construir las Alertas de Distribución de Portafolios
def _construir_alertas_portafolios(df: pd.DataFrame) -> pd.DataFrame:
    alertas = []
    if df.empty:
        return pd.DataFrame(columns=ALERTAS_DISTRIBUCION_COLUMNS)
    for _, filas_grupo in df.groupby('GrupoCol', dropna=False, sort=False):
        if not bool(filas_grupo['_Grupo_Tiene_Portafolio'].iloc[0]):
            continue
        casa = str(filas_grupo['Casa_Cobro'].iloc[0] or '')
        referencia = str(filas_grupo['Referencia'].iloc[0] or '')
        num_distintos = int(filas_grupo['_Num_PaB_Portafolio_Distintos'].iloc[0])
        if num_distintos > 1:
            valores = (
                filas_grupo.loc[
                    filas_grupo['_Portafolio_Valido'], '_PaB_Portafolio_Original'
                ]
                .dropna()
                .drop_duplicates()
                .sort_values()
            )
            valores_texto = ', '.join(
                '${:,.0f}'.format(float(valor)) for valor in valores
            )
            fecha_usada = filas_grupo['_Fecha_Portafolio_Grupo'].iloc[0]
            total_usado = filas_grupo['_PaB_Portafolio_Grupo'].iloc[0]
            alertas.append({
                'Casa_Cobro': casa,
                'Referencia': referencia,
                'Tipo_Alerta': 'Portafolios Múltiples',
                'Detalle': (
                    "Se encontraron {} valores distintos de PaB_Portafolio ({}). "
                    "Se usó el más reciente: ${:,.0f} ({})."
                ).format(
                    num_distintos,
                    valores_texto,
                    float(total_usado),
                    _formatear_fecha_alerta(fecha_usada),
                ),
            })
        pagos_faltantes = int(filas_grupo['PaB_Propuesta'].isna().sum())
        participacion_faltante = int(filas_grupo['%Pago'].isna().sum())
        if pagos_faltantes > 0:
            alertas.append({
                'Casa_Cobro': casa,
                'Referencia': referencia,
                'Tipo_Alerta': 'Pago Faltante',
                'Detalle': (
                    "El portafolio no se redistribuyó porque {:,} fila(s) no tienen "
                    "PaB_Propuesta. Completa el pago y vuelve a procesar."
                ).format(pagos_faltantes),
            })
        elif participacion_faltante > 0:
            alertas.append({
                'Casa_Cobro': casa,
                'Referencia': referencia,
                'Tipo_Alerta': 'PaB_Origen Faltante',
                'Detalle': (
                    "El portafolio no se redistribuyó porque {:,} fila(s) no tienen "
                    "PaB_Origen válido para calcular la participación."
                ).format(participacion_faltante),
            })
        elif not bool(filas_grupo['_Grupo_Portafolio_Aplicable'].iloc[0]):
            alertas.append({
                'Casa_Cobro': casa,
                'Referencia': referencia,
                'Tipo_Alerta': 'Portafolio Individual',
                'Detalle': (
                    "El grupo tiene PaB_Portafolio, pero sus pagos actuales no son "
                    "proporcionales a PaB_Origen y no hay una deuda nueva con el total "
                    "repetido. Se asume un portafolio individual y no se redistribuye."
                ),
            })
    return pd.DataFrame(alertas, columns=ALERTAS_DISTRIBUCION_COLUMNS)

# Función para Distribuir los Portafolios de las Bases Ya Cargadas
def distribuir_portafolios_masivas(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Aplica la distribución de portafolios sobre la Base del Mes.

    Se mantiene esta firma por compatibilidad; usa
    ``distribuir_portafolios_masivas_con_alertas`` si necesitas el reporte de alertas.
    """
    resultado, detalle, _ = distribuir_portafolios_masivas_con_alertas(df)
    return resultado, detalle

# Función para Distribuir los Portafolios y Reportar las Alertas Detectadas
def distribuir_portafolios_masivas_con_alertas(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Aplica la distribución de portafolios sobre la Base del Mes.

    El grupo de portafolio se construye con ``Referencia`` + ``Casa_Cobro``. La
    ``Fecha_Masiva`` no delimita el grupo: el alcance de fechas se define en la
    vista y se recibe ya filtrado en ``df``. Esto permite distribuir una misma
    base que fue subida por partes en fechas diferentes.

    Reglas:
    1. Si el grupo ya tiene ``PaB_Portafolio`` (columna ``Monto Portafolio`` o
       metadata), se usa el valor más reciente como total y se redistribuye
       entre todas las deudas del grupo por ``PaB_Origen``. Esta regla tiene
       prioridad sobre las demás y permite corregir portafolios que quedaron
       incompletos en lotes anteriores.
    2. Si todas las filas de un grupo tienen el mismo PaB_Propuesta y hay más de
       una deuda, se redistribuye el pago según PaB_Origen. La marca
       ``Es_Portafolio`` no se exige como entrada: el grupo se marca
       automáticamente cuando aplica esta regla.
    3. Para JCAP, si al menos dos filas del grupo tienen PaB_Propuesta <= 100 y no
       aplicó la regla anterior, se redistribuye la suma de los pagos originales.
       Este grupo también se marca automáticamente como portafolio.

    La regla 1 solo se aplica si los pagos previos del grupo son proporcionales
    a PaB_Origen o si una deuda nueva trae el total del portafolio repetido. Así
    se protege el modo ``Monto Individual de Portafolio``, donde cada deuda tiene
    su propio pago y no debe redistribuirse por PaB_Origen.

    Returns:
        tuple: (DataFrame con los nuevos PaB_Propuesta, DataFrame con el detalle
        de las deudas cuyo pago cambió, DataFrame con las alertas detectadas).
    """
    columnas_requeridas = [
        'Referencia', 'Casa_Cobro', 'Es_Portafolio', 'Fecha_Masiva',
        'PaB_Origen', 'PaB_Propuesta',
    ]
    columnas_faltantes = [col for col in columnas_requeridas if col not in df.columns]
    if columnas_faltantes:
        raise ValueError(
            "Faltan columnas para distribuir los portafolios: {}".format(
                ', '.join(columnas_faltantes)
            )
        )

    df = df.copy()
    df['PaB_Origen'] = pd.to_numeric(df['PaB_Origen'], errors='coerce')
    df['PaB_Propuesta'] = pd.to_numeric(df['PaB_Propuesta'], errors='coerce')
    df['Es_Portafolio'] = df['Es_Portafolio'].fillna(False).astype(bool)

    # Paso 1: Guardar los Valores Originales y Construir el Grupo
    df['PaB_Act_Original'] = df['PaB_Propuesta']
    df['GrupoCol'] = _construir_grupo_col(df)
    df['_PaB_Portafolio_Original'] = _obtener_pab_portafolio(df)
    df['_Portafolio_Valido'] = (
        df['_PaB_Portafolio_Original'].notna()
        & df['_PaB_Portafolio_Original'].gt(0)
    )
    df['_Fecha_Orden'] = pd.to_datetime(df['Fecha_Masiva'], errors='coerce')
    if 'Fila_Sheets' in df.columns:
        df['_Fila_Orden'] = pd.to_numeric(df['Fila_Sheets'], errors='coerce')
    else:
        df['_Fila_Orden'] = np.arange(len(df), dtype=float)
    df['_Orden_Original'] = np.arange(len(df), dtype=float)

    # Paso 2: Calcular la Participación de Cada Deuda Dentro del Grupo
    grupo = df.groupby('GrupoCol', dropna=False, sort=False)
    suma_origen = grupo['PaB_Origen'].transform('sum')
    df['%Pago'] = np.where(
        suma_origen > 0,
        df['PaB_Origen'] / suma_origen,
        np.nan,
    )

    # Paso 3: Usar el PaB_Portafolio de un Portafolio Ya Distribuido como Total
    df_orden = df.sort_values(
        by=['GrupoCol', '_Fecha_Orden', '_Fila_Orden', '_Orden_Original'],
        na_position='first',
        kind='stable',
    )
    filas_portafolio = df_orden.loc[df_orden['_Portafolio_Valido']]
    ultimo_portafolio = (
        filas_portafolio
        .groupby('GrupoCol', dropna=False, sort=False)
        .tail(1)
        .set_index('GrupoCol')
    )
    df['_PaB_Portafolio_Grupo'] = df['GrupoCol'].map(
        ultimo_portafolio['_PaB_Portafolio_Original']
    )
    df['_Fecha_Portafolio_Grupo'] = df['GrupoCol'].map(
        ultimo_portafolio['_Fecha_Orden'].to_dict()
    )
    df['_Num_PaB_Portafolio_Distintos'] = df['GrupoCol'].map(
        filas_portafolio.groupby('GrupoCol', dropna=False, sort=False)[
            '_PaB_Portafolio_Original'
        ].nunique()
    ).fillna(0).astype(int)
    grupo = df.groupby('GrupoCol', dropna=False, sort=False)
    df['_Grupo_Tiene_Portafolio'] = df['_PaB_Portafolio_Grupo'].notna()

    # Paso 3.1: Verificar si los Pagos Previos son Proporcionales a PaB_Origen
    # (Portafolio de Distribución) o si una Deuda Nueva trae el Total Repetido.
    # Así se protege el modo 'Monto Individual de Portafolio', donde cada deuda
    # tiene su propio pago y no debe redistribuirse por PaB_Origen.
    df['_Id_Portafolio_Original'] = df['Metadata'].apply(
        lambda m: str(m.get('Id_Portafolio') or '') if isinstance(m, dict) else ''
    )
    id_o_total = df['_Id_Portafolio_Original'].where(
        df['_Id_Portafolio_Original'].ne(''),
        df['_PaB_Portafolio_Original'].astype(str),
    )
    df['_Subconjunto_Portafolio'] = np.where(
        df['_Portafolio_Valido'],
        df['GrupoCol'].astype(str) + '||' + id_o_total,
        np.nan,
    )
    df['_Subconjunto_Proporcional'] = pd.Series(
        np.nan, index=df.index, dtype='object'
    )
    for _, filas_sub in df.loc[
        df['_Subconjunto_Portafolio'].notna()
    ].groupby('_Subconjunto_Portafolio', sort=False):
        origenes = pd.to_numeric(filas_sub['PaB_Origen'], errors='coerce')
        pagos = pd.to_numeric(filas_sub['PaB_Propuesta'], errors='coerce')
        if not (origenes.gt(0) & pagos.notna()).all():
            df.loc[filas_sub.index, '_Subconjunto_Proporcional'] = False
            continue
        ratios = pagos / origenes
        df.loc[filas_sub.index, '_Subconjunto_Proporcional'] = bool(
            np.isclose(ratios, ratios.mean(), rtol=1e-6, atol=0.01).all()
        )
    proporcional_por_grupo = (
        df.loc[df['_Subconjunto_Portafolio'].notna()]
        .groupby('GrupoCol', dropna=False, sort=False)['_Subconjunto_Proporcional']
        .all()
    )
    df['_Grupo_Subconjuntos_Proporcionales'] = df['GrupoCol'].map(
        proporcional_por_grupo
    ).fillna(False).astype(bool)
    df['_Pago_Igual_Total'] = np.isclose(
        df['PaB_Propuesta'],
        df['_PaB_Portafolio_Grupo'],
        rtol=1e-9,
        atol=0.01,
    )
    df['_Grupo_Nueva_Con_Total'] = (
        (~df['_Portafolio_Valido'])
        & df['_Pago_Igual_Total']
        & df['_Grupo_Tiene_Portafolio']
    ).groupby(
        df['GrupoCol'], dropna=False, sort=False
    ).transform('any')
    df['_Grupo_Portafolio_Aplicable'] = (
        df['_Grupo_Tiene_Portafolio']
        & (df['_Grupo_Subconjuntos_Proporcionales'] | df['_Grupo_Nueva_Con_Total'])
    )

    df['_Grupo_Pagos_Completos'] = grupo['PaB_Propuesta'].transform(
        lambda s: s.notna().all()
    )
    df['_Grupo_Participacion_Completa'] = grupo['%Pago'].transform(
        lambda s: s.notna().all()
    )
    mask_portafolio_existente = (
        df['_Grupo_Portafolio_Aplicable']
        & df['_Grupo_Pagos_Completos']
        & df['_Grupo_Participacion_Completa']
    )
    df.loc[mask_portafolio_existente, 'PaB_Propuesta'] = (
        df.loc[mask_portafolio_existente, '_PaB_Portafolio_Grupo']
        * df.loc[mask_portafolio_existente, '%Pago']
    ).round(2)

    # Paso 4: Regla Especial (Todos los Pagos Iguales dentro de un Portafolio)
    df['_Igual'] = np.isclose(
        df['PaB_Propuesta'],
        grupo['PaB_Propuesta'].transform('mean'),
        rtol=1e-9,
        atol=0.01,
    )
    grupo = df.groupby('GrupoCol', dropna=False, sort=False)
    mask_especial = (
        grupo['_Igual'].transform('all')
        & (grupo['_Igual'].transform('sum') > 1)
        & df['%Pago'].notna()
        & ~df['_Grupo_Tiene_Portafolio']
    )
    df.loc[mask_especial, 'PaB_Propuesta'] = (
        df.loc[mask_especial, 'PaB_Act_Original'] * df.loc[mask_especial, '%Pago']
    ).round(2)

    # Paso 5: Regla JCAP (Pagos Menores o Iguales a 100 en al Menos Dos Deudas del Grupo)
    df['Cond'] = (
        (df['PaB_Propuesta'] <= 100)
        & ~mask_especial
        & ~df['_Grupo_Tiene_Portafolio']
        & (df['Casa_Cobro'].astype(str).str.strip().str.upper() == 'JCAP')
    )
    grupo = df.groupby('GrupoCol', dropna=False, sort=False)
    mask_cambio = (
        grupo['Cond'].transform('any')
        & (grupo['Cond'].transform('sum') > 1)
        & grupo['PaB_Act_Original'].transform(lambda s: s.notna().all())
        & df['%Pago'].notna()
    )
    suma_original_grupo = grupo['PaB_Act_Original'].transform('sum')
    df.loc[mask_cambio, 'PaB_Propuesta'] = (
        suma_original_grupo[mask_cambio] * df.loc[mask_cambio, '%Pago']
    ).round(2)

    # Paso 6: Marcar Automáticamente como Portafolio los Grupos Detectados
    mask_portafolio_auto = (
        mask_portafolio_existente | mask_especial | mask_cambio
    ).groupby(
        df['GrupoCol'], dropna=False, sort=False
    ).transform('all')
    df.loc[mask_portafolio_auto, 'Es_Portafolio'] = True

    # Paso 7: Construir el Detalle de las Deudas que Cambiaron
    mask_cambio_pago = df.apply(
        lambda fila: _montos_diferentes(
            fila['PaB_Act_Original'],
            fila['PaB_Propuesta'],
        ),
        axis=1,
    )
    columnas_detalle = [
        col for col in [
            'Fila_Sheets', 'Id_Deuda', 'Referencia', 'Casa_Cobro', 'Fecha_Masiva',
            'Es_Portafolio', 'PaB_Origen',
        ] if col in df.columns
    ]
    detalle = df.loc[mask_cambio_pago, columnas_detalle].copy()
    detalle['PaB_Propuesta_Antes'] = df.loc[mask_cambio_pago, 'PaB_Act_Original']
    detalle['PaB_Propuesta_Despues'] = df.loc[mask_cambio_pago, 'PaB_Propuesta']
    detalle['Diferencia'] = (
        detalle['PaB_Propuesta_Despues'] - detalle['PaB_Propuesta_Antes']
    ).round(2)
    detalle['Regla_Portafolio_Existente'] = (
        mask_portafolio_existente[mask_cambio_pago].to_numpy()
    )
    detalle['Regla_Especial'] = mask_especial[mask_cambio_pago].to_numpy()
    detalle['Regla_JCAP'] = mask_cambio[mask_cambio_pago].to_numpy()

    # Paso 8: Construir las Alertas de Portafolios
    alertas = _construir_alertas_portafolios(df)

    # Paso 9: Limpiar las Columnas Auxiliares (se conserva GrupoCol para la Metadata)
    columnas_temporales = [
        'PaB_Act_Original', '%Pago', '_Igual', 'Cond',
        '_PaB_Portafolio_Original', '_Portafolio_Valido', '_Fecha_Orden',
        '_Fila_Orden', '_Orden_Original', '_PaB_Portafolio_Grupo',
        '_Fecha_Portafolio_Grupo', '_Num_PaB_Portafolio_Distintos',
        '_Id_Portafolio_Original', '_Subconjunto_Portafolio',
        '_Subconjunto_Proporcional', '_Grupo_Subconjuntos_Proporcionales',
        '_Pago_Igual_Total', '_Grupo_Nueva_Con_Total',
        '_Grupo_Portafolio_Aplicable',
        '_Grupo_Tiene_Portafolio', '_Grupo_Pagos_Completos',
        '_Grupo_Participacion_Completa',
    ]
    df = df.drop(columns=[col for col in columnas_temporales if col in df.columns])
    return df, detalle.reset_index(drop=True), alertas

# Función para Actualizar el Id_Portafolio y el PaB_Portafolio en la Metadata
def actualizar_metadata_portafolios(df: pd.DataFrame) -> pd.DataFrame:
    """Recalcula Id_Portafolio y PaB_Portafolio de cada fila según su grupo.

    La marca ``Es_Portafolio`` ya viene resuelta por ``distribuir_portafolios_masivas``:
    los grupos detectados automáticamente se marcan allí antes de llamar esta función.
    """
    df = df.copy()
    if df.empty:
        return df
    if 'GrupoCol' not in df.columns:
        df['GrupoCol'] = _construir_grupo_col(df)

    df['Es_Portafolio'] = df['Es_Portafolio'].fillna(False).astype(bool)
    df['PaB_Propuesta'] = pd.to_numeric(df['PaB_Propuesta'], errors='coerce')
    pab_portafolio_original = _obtener_pab_portafolio(df)
    id_portafolio_original = df['Metadata'].apply(
        lambda m: str(m.get('Id_Portafolio') or '') if isinstance(m, dict) else ''
    )
    grupo = df.groupby('GrupoCol', dropna=False, sort=False)
    tamano_grupo = grupo['Id_Deuda'].transform('size')
    montos_completos = grupo['PaB_Propuesta'].transform(lambda s: s.notna().all())
    mask_portafolio = (
        grupo['Es_Portafolio'].transform('all')
        & (tamano_grupo > 1)
        & montos_completos
    )
    # Preservar la Metadata de los Grupos que Ya Eran Portafolio y No se Pueden Recalcular
    df['_Portafolio_Previo'] = (
        pab_portafolio_original.notna()
        | id_portafolio_original.ne('')
        | df['Metadata'].apply(
            lambda m: isinstance(m, dict) and pd.notna(m.get('PaB_Portafolio'))
        )
    )
    grupo = df.groupby('GrupoCol', dropna=False, sort=False)
    mask_preservar = (
        grupo['_Portafolio_Previo'].transform('any')
        & ~mask_portafolio
    )
    ids_portafolio = grupo.apply(
        lambda g: '-'.join(
            str(valor) for valor in g.get('Metadata', pd.Series(dtype=object)).apply(
                lambda m: (m or {}).get('Id_Cruce', '') if isinstance(m, dict) else ''
            ) if str(valor).strip()
        ),
        include_groups=False,
    )
    ids_portafolio = df['GrupoCol'].map(ids_portafolio)
    monto_portafolio = grupo['PaB_Propuesta'].transform('sum').round(2)

    def _actualizar_metadata(fila: pd.Series) -> dict:
        metadata = _metadata_a_dict(fila.get('Metadata'))
        if bool(fila.get('_Preservar_Metadata', False)):
            return metadata
        es_portafolio = bool(fila.get('_Es_Portafolio_Grupo', False))
        metadata['Id_Portafolio'] = (
            str(fila.get('_Id_Portafolio_Grupo') or '') if es_portafolio else ''
        )
        metadata['PaB_Portafolio'] = (
            float(fila['_Monto_Portafolio_Grupo'])
            if es_portafolio and pd.notna(fila.get('_Monto_Portafolio_Grupo'))
            else None
        )
        return metadata

    df['_Es_Portafolio_Grupo'] = mask_portafolio
    df['_Id_Portafolio_Grupo'] = ids_portafolio
    df['_Monto_Portafolio_Grupo'] = monto_portafolio
    df['_Preservar_Metadata'] = mask_preservar
    df['Metadata'] = df.apply(_actualizar_metadata, axis=1)
    # La Columna de la Hoja ('Monto Portafolio') se mantiene sincronizada con la Metadata
    df['PaB_Portafolio'] = np.where(
        mask_portafolio & monto_portafolio.notna(),
        monto_portafolio,
        np.where(mask_preservar, pab_portafolio_original, np.nan),
    )
    df = df.drop(columns=[
        '_Portafolio_Previo',
        '_Preservar_Metadata',
        '_Es_Portafolio_Grupo',
        '_Id_Portafolio_Grupo',
        '_Monto_Portafolio_Grupo',
    ])
    return df

# Función para Construir la Tabla de Cambios entre la Base Original y la Procesada
def construir_cambios_masivas(
    *,
    df_original: pd.DataFrame,
    df_resultado: pd.DataFrame,
) -> pd.DataFrame:
    columnas_salida = [
        'Fila_Sheets', 'Id_Deuda', 'Referencia', 'Casa_Cobro', 'Fecha_Masiva',
        'Es_Portafolio', 'PaB_Propuesta_Antes', 'PaB_Propuesta_Despues',
        'Diferencia_PaB', 'PaB_Portafolio_Antes', 'PaB_Portafolio_Despues',
        'Diferencia_Portafolio', 'Metadata_Antes', 'Metadata_Despues',
        'Metadata_Cambio', 'PaB_Cambio', 'Portafolio_Cambio', 'Es_Portafolio_Despues',
    ]
    if df_original.empty or df_resultado.empty:
        return pd.DataFrame(columns=columnas_salida)

    original = (
        df_original
        .drop_duplicates(subset=['Fila_Sheets'], keep='last')
        .set_index('Fila_Sheets', drop=False)
    )
    resultado = (
        df_resultado
        .drop_duplicates(subset=['Fila_Sheets'], keep='last')
        .set_index('Fila_Sheets', drop=False)
    )
    filas_comunes = original.index.intersection(resultado.index)

    filas = []
    for fila_sheets in filas_comunes:
        antes = original.loc[fila_sheets]
        despues = resultado.loc[fila_sheets]
        metadata_cambio = (
            _serializar_metadata(antes.get('Metadata'))
            != _serializar_metadata(despues.get('Metadata'))
        )
        pab_cambio = _montos_diferentes(
            antes.get('PaB_Propuesta'),
            despues.get('PaB_Propuesta'),
        )
        portafolio_monto_cambio = _montos_diferentes(
            antes.get('PaB_Portafolio'),
            despues.get('PaB_Portafolio'),
        )
        es_portafolio_antes = bool(antes.get('Es_Portafolio', False))
        es_portafolio_despues = bool(despues.get('Es_Portafolio', False))
        portafolio_cambio = portafolio_monto_cambio or (es_portafolio_antes != es_portafolio_despues)
        if not (metadata_cambio or pab_cambio or portafolio_cambio):
            continue
        filas.append({
            'Fila_Sheets': int(fila_sheets),
            'Id_Deuda': despues.get('Id_Deuda'),
            'Referencia': despues.get('Referencia'),
            'Casa_Cobro': despues.get('Casa_Cobro'),
            'Fecha_Masiva': despues.get('Fecha_Masiva'),
            'Es_Portafolio': despues.get('Es_Portafolio'),
            'PaB_Propuesta_Antes': antes.get('PaB_Propuesta'),
            'PaB_Propuesta_Despues': despues.get('PaB_Propuesta'),
            'Diferencia_PaB': (
                float(despues.get('PaB_Propuesta')) - float(antes.get('PaB_Propuesta'))
                if pd.notna(antes.get('PaB_Propuesta')) and pd.notna(despues.get('PaB_Propuesta'))
                else np.nan
            ),
            'PaB_Portafolio_Antes': antes.get('PaB_Portafolio'),
            'PaB_Portafolio_Despues': despues.get('PaB_Portafolio'),
            'Diferencia_Portafolio': (
                float(despues.get('PaB_Portafolio')) - float(antes.get('PaB_Portafolio'))
                if pd.notna(antes.get('PaB_Portafolio')) and pd.notna(despues.get('PaB_Portafolio'))
                else np.nan
            ),
            'Metadata_Antes': antes.get('Metadata'),
            'Metadata_Despues': despues.get('Metadata'),
            'Metadata_Cambio': metadata_cambio,
            'PaB_Cambio': pab_cambio,
            'Portafolio_Cambio': portafolio_cambio,
            'Es_Portafolio_Despues': es_portafolio_despues,
        })
    return pd.DataFrame(filas, columns=columnas_salida)

# Función para Construir el Registro de Trazabilidad por Base
def construir_log_cambios_masivas(
    *,
    df_original: pd.DataFrame,
    df_cambios: pd.DataFrame,
    usuario: str,
    fecha_cambio: Optional[pd.Timestamp] = None,
) -> pd.DataFrame:
    if df_original.empty:
        return pd.DataFrame(columns=CAMBIO_MASIVAS_COLUMNS)

    fecha_cambio = fecha_cambio or pd.Timestamp.now(tz='America/Bogota').tz_localize(None)
    cambios_por_base = {}
    if not df_cambios.empty:
        cambios_unicos = df_cambios.drop_duplicates(subset=['Fila_Sheets'])
        for (casa, fecha), grupo in cambios_unicos.groupby(
            ['Casa_Cobro', 'Fecha_Masiva'], dropna=False
        ):
            clave = (casa, _normalizar_fecha_base(fecha))
            cambios_por_base[clave] = int(grupo['Fila_Sheets'].nunique())

    filas = []
    for (casa, fecha), grupo in df_original.groupby(
        ['Casa_Cobro', 'Fecha_Masiva'], dropna=False, sort=False
    ):
        fecha_normalizada = _normalizar_fecha_base(fecha)
        clave = (casa, fecha_normalizada)
        filas.append({
            'Fecha_Cambio': pd.Timestamp(fecha_cambio),
            'Usuario': str(usuario or ''),
            'Nombre_Aliado_Cambio': str(casa or ''),
            'Fecha_Aliado_Cambio': fecha_normalizada,
            'Num_Registros': int(len(grupo)),
            'Num_Cambiados': int(cambios_por_base.get(clave, 0)),
        })
    return pd.DataFrame(filas, columns=CAMBIO_MASIVAS_COLUMNS)

# Función para Resumir las Bases que Aún no Tienen Metadata Completa
def resumen_bases_sin_metadata(df: pd.DataFrame) -> pd.DataFrame:
    columnas_salida = ['Casa_Cobro', 'Fecha_Masiva', 'Num_Registros', 'Num_Sin_Metadata']
    if df.empty:
        return pd.DataFrame(columns=columnas_salida)
    df = df.copy()
    df['_Metadata_Completa'] = df['Metadata'].apply(metadata_masiva_completa)
    resumen = (
        df.groupby(['Casa_Cobro', 'Fecha_Masiva'], dropna=False)
        .agg(
            Num_Registros=('Id_Deuda', 'size'),
            Num_Sin_Metadata=('_Metadata_Completa', lambda s: int((~s).sum())),
        )
        .reset_index()
    )
    return resumen[resumen['Num_Sin_Metadata'] > 0].reset_index(drop=True)

# Función para Detectar Fechas con Portafolios Ya Distribuidos Fuera del Alcance
def detectar_fechas_portafolio_fuera_alcance(
    *,
    df: pd.DataFrame,
    casa_cobro: Any,
    fechas_alcance: list[Any],
    referencias: Optional[list[Any]] = None,
) -> pd.DataFrame:
    """Devuelve las fechas de la Casa que tienen PaB_Portafolio y quedaron fuera del alcance.

    Sirve para advertir que un portafolio subido por lotes no se podrá redistribuir
    completo si no se seleccionan todas sus fechas. Si se pasan ``referencias``, solo
    se consideran las filas de esas Referencias.
    """
    columnas_salida = ['Fecha_Masiva', 'Num_Registros']
    if df.empty or ('Fecha_Masiva' not in df.columns) or ('Casa_Cobro' not in df.columns):
        return pd.DataFrame(columns=columnas_salida)

    df = df.copy()
    fechas = pd.to_datetime(df['Fecha_Masiva'], errors='coerce').dt.normalize()
    casa_normalizada = str(casa_cobro or '').strip().casefold()
    mask = (
        df['Casa_Cobro'].fillna('').astype(str).str.strip().str.casefold()
        .eq(casa_normalizada)
        & fechas.notna()
    )
    fechas_alcance_norm = {
        pd.Timestamp(fecha).normalize()
        for fecha in (fechas_alcance or [])
        if pd.notna(fecha)
    }
    mask &= ~fechas.isin(fechas_alcance_norm)
    mask &= _obtener_pab_portafolio(df).gt(0)

    referencias_norm = {
        str(referencia).strip()
        for referencia in (referencias or [])
        if pd.notna(referencia)
    }
    if referencias_norm and ('Referencia' in df.columns):
        mask &= df['Referencia'].fillna('').astype(str).str.strip().isin(
            referencias_norm
        )

    if not mask.any():
        return pd.DataFrame(columns=columnas_salida)
    resumen = (
        pd.DataFrame({'Fecha_Masiva': fechas[mask]})
        .groupby('Fecha_Masiva', dropna=True)
        .size()
        .reset_index(name='Num_Registros')
        .sort_values('Fecha_Masiva')
        .reset_index(drop=True)
    )
    return resumen[columnas_salida]
