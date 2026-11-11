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

# Función Auxiliar para Normalizar una Fecha de Base
def _normalizar_fecha_base(valor: Any) -> pd.Timestamp:
    fecha = pd.to_datetime(valor, errors='coerce')
    if pd.isna(fecha):
        return pd.NaT
    return pd.Timestamp(fecha).normalize()

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
    fechas = pd.to_datetime(df['Fecha_Masiva'], errors='coerce').dt.strftime('%Y-%m-%d')
    fechas = fechas.fillna('SIN_FECHA')
    es_portafolio = df['Es_Portafolio'].fillna(False).astype(bool).astype(str)
    return (
        'Masiva_'
        + df['Referencia'].fillna('').astype(str).str.strip()
        + '_'
        + df['Casa_Cobro'].fillna('').astype(str).str.strip()
        + '_'
        + es_portafolio
        + '_'
        + fechas
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

        return {
            'Id_Cruce': id_cruce,
            'Tipo_Contraoferta': tipo_contraoferta,
            'Fecha_Limite_Uso': pd.Timestamp(fecha_limite) if not pd.isna(fecha_limite) else None,
            'Alias': alias,
            'Id_Portafolio': str(metadata.get('Id_Portafolio') or ''),
            'PaB_Portafolio': metadata.get('PaB_Portafolio'),
        }

    df['Metadata'] = df.apply(_completar, axis=1)
    return df

# Función para Distribuir los Portafolios de las Bases Ya Cargadas
def distribuir_portafolios_masivas(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Aplica la distribución de portafolios sobre la Base del Mes.

    Reglas:
    1. Si todas las filas de un grupo tienen el mismo PaB_Propuesta, son portafolio y
       hay más de una deuda, se redistribuye el pago según PaB_Origen.
    2. Para JCAP, si al menos dos filas del grupo tienen PaB_Propuesta <= 100 y no
       aplicó la regla anterior, se redistribuye la suma de los pagos originales.

    Returns:
        tuple: (DataFrame con los nuevos PaB_Propuesta, DataFrame con el detalle
        de las deudas cuyo pago cambió).
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

    # Paso 2: Calcular la Participación de Cada Deuda Dentro del Grupo
    grupo = df.groupby('GrupoCol', dropna=False, sort=False)
    suma_origen = grupo['PaB_Origen'].transform('sum')
    df['%Pago'] = np.where(
        suma_origen > 0,
        df['PaB_Origen'] / suma_origen,
        np.nan,
    )

    # Paso 3: Regla Especial (Todos los Pagos Iguales dentro de un Portafolio)
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
        & grupo['Es_Portafolio'].transform('all')
        & df['%Pago'].notna()
    )
    df.loc[mask_especial, 'PaB_Propuesta'] = (
        df.loc[mask_especial, 'PaB_Act_Original'] * df.loc[mask_especial, '%Pago']
    ).round(2)

    # Paso 4: Regla JCAP (Pagos Menores o Iguales a 100 en al Menos Dos Deudas del Grupo)
    df['Cond'] = (
        (df['PaB_Propuesta'] <= 100)
        & ~mask_especial
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

    # Paso 5: Construir el Detalle de las Deudas que Cambiaron
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
    detalle['Regla_Especial'] = mask_especial[mask_cambio_pago].to_numpy()
    detalle['Regla_JCAP'] = mask_cambio[mask_cambio_pago].to_numpy()

    # Paso 6: Limpiar las Columnas Auxiliares (se conserva GrupoCol para la Metadata)
    df = df.drop(columns=['PaB_Act_Original', '%Pago', '_Igual', 'Cond'])
    return df, detalle.reset_index(drop=True)

# Función para Actualizar el Id_Portafolio y el PaB_Portafolio en la Metadata
def actualizar_metadata_portafolios(df: pd.DataFrame) -> pd.DataFrame:
    """Recalcula Id_Portafolio y PaB_Portafolio de cada fila según su grupo."""
    df = df.copy()
    if df.empty:
        return df
    if 'GrupoCol' not in df.columns:
        df['GrupoCol'] = _construir_grupo_col(df)

    df['Es_Portafolio'] = df['Es_Portafolio'].fillna(False).astype(bool)
    df['PaB_Propuesta'] = pd.to_numeric(df['PaB_Propuesta'], errors='coerce')
    grupo = df.groupby('GrupoCol', dropna=False, sort=False)
    tamano_grupo = grupo['Id_Deuda'].transform('size')
    montos_completos = grupo['PaB_Propuesta'].transform(lambda s: s.notna().all())
    mask_portafolio = (
        grupo['Es_Portafolio'].transform('all')
        & (tamano_grupo > 1)
        & montos_completos
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
    df['Metadata'] = df.apply(_actualizar_metadata, axis=1)
    # La Columna de la Hoja ('Monto Portafolio') se mantiene sincronizada con la Metadata
    df['PaB_Portafolio'] = np.where(
        mask_portafolio & monto_portafolio.notna(),
        monto_portafolio,
        np.nan,
    )
    df = df.drop(columns=['_Es_Portafolio_Grupo', '_Id_Portafolio_Grupo', '_Monto_Portafolio_Grupo'])
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
