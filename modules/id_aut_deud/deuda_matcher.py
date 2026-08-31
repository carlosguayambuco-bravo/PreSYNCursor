# Estándar usando Pep8
# Librerías de Python
from collections import defaultdict
from itertools import combinations
from typing import Optional
# Librerías de Terceros
import numpy as np
import pandas as pd
from pandera.typing import DataFrame
from thefuzz import fuzz
import streamlit as st
# Librerías Locales
from data.data_models import InputCruceSchema, OutputCruceSchema
from modules.constants import COLUMNAS_UNIVERSO, DIF_MONTO_MAX, ETIQUETA_ADDENDUM, ETIQUETA_AMBIGUO, ETIQUETA_DUPLICADO, LIMITE_VERIFICACION, MAX_COMB_NOMBRE, MIN_PALABRAS_NOMBRE, MOTIVO_CASA_COBRO, RATIO_FUZZY_BANCO, RATIO_FUZZY_CREDITO, UMBRAL_BLOQUEO
from modules.id_aut_deud.helpers import *

# --- Funciones de Match por Columna ---

# Función Auxiliar de Crop con pre-chequeos baratos (en ambas direcciones)
def _match_crop(*, a, b) -> bool:
    # a y b tienen longitud >= 4
    if len(b) <= len(a):
        if set(b) <= set(a) and is_generalized_crop(a, b):
            return True
    if set(a) <= set(b) and is_generalized_crop(b, a):
        return True
    return False

# --- Sub-Funciones de Acotación por Columna ---

# Sub-Función de Acotación por Cédula (coincidencia exacta)
def _mascara_cedula(*, cedula_val, cedula_index, n: int) -> np.ndarray:
    mascara = np.zeros(n, dtype=bool)
    if not cedula_val:
        return mascara
    posiciones = cedula_index.get(cedula_val)
    if posiciones is not None and posiciones.size:
        mascara[posiciones] = True
    return mascara

# Sub-Función de Acotación por Nombre del Cliente (exacto y contención)
def _mascara_nombre(*, nombre_val, nombre_exact_index, nombre_word_index, n: int) -> np.ndarray:
    mascara = np.zeros(n, dtype=bool)
    if not nombre_val:
        return mascara
    candidatos = set(nombre_exact_index.get(nombre_val, ()))
    palabras = nombre_val.split()
    if len(palabras) >= MIN_PALABRAS_NOMBRE:
        palabras_distintas = sorted(set(palabras))
        # Contención Dirección 1: el universo contiene todas las palabras del registro
        palabras_ordenadas = sorted(palabras_distintas, key=lambda p: len(nombre_word_index.get(p, ())))
        comunes = set(nombre_word_index.get(palabras_ordenadas[0], ()))
        for palabra in palabras_ordenadas[1:]:
            comunes &= nombre_word_index.get(palabra, ())
            if not comunes:
                break
        candidatos |= comunes
        # Contención Dirección 2: el registro contiene todas las palabras del universo
        tope = min(len(palabras_distintas), MAX_COMB_NOMBRE)
        for tam in range(MIN_PALABRAS_NOMBRE, tope + 1):
            for combinacion in combinations(palabras_distintas, tam):
                for pos in nombre_exact_index.get(' '.join(combinacion), ()):
                    candidatos.add(pos)
    if candidatos:
        mascara[np.asarray(list(candidatos), dtype=np.int64)] = True
    return mascara

# Sub-Función de Acotación por Texto (Banco, Casa de Cobro o Número de Crédito)
def _acotar_texto(*,
        cand: np.ndarray,
        valor,
        valores: np.ndarray,
        exact_index,
        char_index,
        start2_index,
        gram_index,
        umbral_fuzzy: int,
        es_credito: bool,
        n: int
    ):
    if not valor:
        return cand, False
    posiciones = np.nonzero(cand)[0]
    if posiciones.size > UMBRAL_BLOQUEO:
        # Ruta Bloqueada: se restringe el universo con los índices construidos
        mascara = np.zeros(n, dtype=bool)
        # Coincidencia Exacta
        exactos = exact_index.get(valor)
        if exactos is not None and exactos.size:
            mascara[exactos[cand[exactos]]] = True
        if len(valor) >= MIN_LEN_TEXTO:
            restantes = cand & ~mascara
            # Contención Dirección 1: valor dentro del valor del universo
            bloque_grama = gram_index.get(valor[:4])
            if bloque_grama is not None:
                bloque_grama = bloque_grama[restantes[bloque_grama]]
                if bloque_grama.size <= LIMITE_VERIFICACION:
                    for p in bloque_grama:
                        if valor in valores[p]:
                            mascara[p] = True
                            restantes[p] = False
            # Contención Dirección 2: valor del universo dentro de valor
            for tam in range(MIN_LEN_TEXTO, len(valor) + 1):
                for ini in range(len(valor) - tam + 1):
                    pos = exact_index.get(valor[ini:ini + tam])
                    if pos is not None and pos.size:
                        arr = pos[restantes[pos]]
                        mascara[arr] = True
                        restantes[arr] = False
            # Coincidencia Fuzzy: bloque por las dos primeras letras
            bloque_fuzzy = start2_index.get(valor[:2])
            if bloque_fuzzy is not None:
                bloque_fuzzy = bloque_fuzzy[restantes[bloque_fuzzy]]
                if bloque_fuzzy.size <= LIMITE_VERIFICACION:
                    for p in bloque_fuzzy:
                        if fuzz.ratio(valor, valores[p]) >= umbral_fuzzy:
                            mascara[p] = True
                            restantes[p] = False
            # Contención Cortada (solo Número de Crédito): bloque por primera y última letra
            if es_credito:
                b1 = char_index.get(valor[0])
                b2 = char_index.get(valor[-1])
                if b1 is not None and b2 is not None:
                    bloque_crop = b1 if valor[-1] == valor[0] else np.intersect1d(b1, b2)
                    bloque_crop = bloque_crop[restantes[bloque_crop]]
                    if bloque_crop.size <= LIMITE_VERIFICACION:
                        for p in bloque_crop:
                            if _match_crop(a=valores[p], b=valor):
                                mascara[p] = True
                                restantes[p] = False
        return mascara, bool(mascara.any())
    # Ruta Directa: verificación vectorizada de exacta y contención, y por candidato para fuzzy y crop
    vals = valores[posiciones]
    cumple = vals == valor
    if len(valor) >= MIN_LEN_TEXTO:
        idx_pendientes = np.nonzero((np.array([len(v) for v in vals]) >= MIN_LEN_TEXTO) & ~cumple)[0]
        if idx_pendientes.size:
            sub = vals[idx_pendientes]
            # Contención Dirección 1: valor dentro del valor del universo
            dir1 = np.array([valor in s for s in sub])
            # Contención Dirección 2: valor del universo dentro de valor
            dir2 = np.array([s in valor for s in sub])
            cumple[idx_pendientes[dir1 | dir2]] = True
            # Fuzzy y Crop sobre el resto de candidatos pendientes
            resto = idx_pendientes[~(dir1 | dir2)]
            if resto.size <= LIMITE_VERIFICACION:
                for j in resto:
                    v = vals[j]
                    if fuzz.ratio(valor, v) >= umbral_fuzzy:
                        cumple[j] = True
                        continue
                    if es_credito and _match_crop(a=valor, b=v):
                        cumple[j] = True
    hits = posiciones[cumple]
    mascara = np.zeros(n, dtype=bool)
    if hits.size:
        mascara[hits] = True
    return mascara, bool(hits.size)

# Sub-Función de Acotación por Monto (diferencia absoluta <= 1k)
def _acotar_monto(*,
        cand: np.ndarray,
        monto_val,
        monto_arr: np.ndarray,
        monto_sorted_idx: np.ndarray,
        monto_sorted: np.ndarray,
        n: int
    ):
    if pd.isna(monto_val):
        return cand, False
    posiciones = np.nonzero(cand)[0]
    if posiciones.size > UMBRAL_BLOQUEO:
        # Ruta Bloqueada: ventana de montos con búsqueda binaria
        lo = np.searchsorted(monto_sorted, monto_val - DIF_MONTO_MAX, side='left')
        hi = np.searchsorted(monto_sorted, monto_val + DIF_MONTO_MAX, side='right')
        mascara = np.zeros(n, dtype=bool)
        if hi > lo:
            mascara[monto_sorted_idx[lo:hi]] = True
            mascara &= cand
        return mascara, bool(mascara.any())
    # Ruta Directa: se verifica candidato a candidato
    hits = [p for p in posiciones
            if not pd.isna(monto_arr[p]) and abs(monto_arr[p] - monto_val) <= DIF_MONTO_MAX]
    mascara = np.zeros(n, dtype=bool)
    if hits:
        mascara[np.asarray(hits, dtype=np.int64)] = True
    return mascara, bool(hits)

# --- Función Principal ---

def match_deudas(*,
        df_buscar: DataFrame[InputCruceSchema],
        df_datos: DataFrame[InputCruceSchema],
        casa_cobro: Optional[str] = None
    ) -> DataFrame[OutputCruceSchema]:
    """
    Identifica las deudas (Id_Deuda) del universo 'df_datos' que corresponden a cada
    registro de 'df_buscar', priorizando la certeza sobre la cantidad de coincidencias.

    El algoritmo acota el universo de candidatos por cada registro en la secuencia:
        1. Unión por Datos del Cliente (Cédula y Nombre). Aquí se determinan las NULAS.
        2. Contraste con Datos de la Deuda excluyendo el Número de Crédito
            (Banco, Casa de Cobro simulando el Banco y Monto).
        3. Contraste con el Número de Crédito (se determinan AMBIGUAS y ADDENDUM;
            los restantes son prospectos a EXACTO o DUPLICADO).
        4. De los prospectos a EXACTO se identifican los duplicados (2 registros con el
            mismo Id_Deuda) y se convierten en DUPLICADO.

    Parámetros:
        df_buscar (DataFrame[InputCruceSchema]): Cartera a Buscar. Debe tener 'Id_Cruce' y puede tener
            alguna de las columnas: Cedula, Nombre_Cliente, Banco, Monto_Actual, Numero_Credito.
        df_datos (DataFrame[InputCruceSchema]): Cartera de Datos (universo). Debe tener las columnas:
            Cedula, Nombre_Cliente, Banco, Monto_Actual, Numero_Credito, Id_Deuda.
        casa_cobro (Optional[str]): La Casa de Cobro que maneja la deuda. Se acota por texto
            "simulando" que el Banco del universo sea la Casa de Cobro (en ocasiones el dato
            guardado como Banco corresponde directamente a la Casa de Cobro). Esta acotación
            tiene su propio motivo: 'Casa de Cobro'.

    Retorna:
        DataFrame con las columnas (OutputCruceSchema):
            - Id_Registro: El Id de cada registro buscado.
            - Ids_Candidatos: Los Id_Deuda candidatos resultantes de la acotación.
            - Etiqueta_Registro: EXACTO, DUPLICADO, AMBIGUO, ADDENDUM o NULO.
            - Motivos_Etiqueta: Las columnas que generaron la acotación (separadas por '|').
    """
    # Validación de Entradas
    columnas_faltantes = [c for c in COLUMNAS_UNIVERSO if c not in df_datos.columns]
    if columnas_faltantes:
        raise ValueError('La Cartera de Datos no tiene las columnas requeridas: {}'.format(columnas_faltantes))
    if COL_ID_CRUCE not in df_buscar.columns:
        raise ValueError("La Cartera a Buscar no tiene la columna '{}'".format(COL_ID_CRUCE))

    # Creamos una Barra de Progreso a Mostrar
    progress_cruce = st.progress(
        value=0,
        text="Preparando Universo de Deudas",
        width="stretch"
    )

    # Preparación de Datos
    univ = preparar_universo(df_datos=df_datos)

    # Aumentamos el Progreso #1
    progress_cruce.progress(1/5, text="Preparando Limpieza de Datos a Coincidir")

    n = univ['n']
    id_registro_arr, columnas = limpiar_busqueda(df_buscar=df_buscar)

    # Aumentamos el Progreso #2
    progress_cruce.progress(2/5, text="Ejecutando Reconocimiento por Cedula y Nombre")

    tiene_cedula = COL_CEDULA in columnas
    tiene_nombre = COL_NOMBRE in columnas
    tiene_banco = COL_BANCO in columnas
    tiene_monto = COL_MONTO_ACTUAL in columnas
    tiene_credito = COL_CREDITO in columnas

    # Verificación Intermedia: Por Lógica de Negocio, se necesita que la base tenga cedula o nombre
    if not (tiene_cedula or tiene_nombre):
        raise LookupError("La base de cruce no tiene Cedula o Nombre Cliente (Caracter Obligatorio)")

    # Preparación de la Casa de Cobro: se genera un array donde se mantiene la misma casa de cobro
    casa_cobro_arr = None
    if (casa_cobro is not None) and (not pd.isna(casa_cobro)):
        casa_cobro_limpia = cleanText(str(casa_cobro))
        if casa_cobro_limpia:
            casa_cobro_arr = np.full(len(df_buscar), casa_cobro_limpia, dtype=object)

    etiquetas = []
    ids_candidatos = []
    motivos_lista = []
    prospectos_exacto = []  # (índice del registro, Id_Deuda reclamado)

    # Ejecución del Algoritmo Registro por Registro
    for i in range(len(df_buscar)):
        motivos = []

        # Paso 1: Unión por Datos del Cliente (Cédula y Nombre)
        if tiene_cedula or tiene_nombre:
            mascara_cliente = np.zeros(n, dtype=bool)
            if tiene_cedula:
                m = _mascara_cedula(cedula_val=columnas[COL_CEDULA][i], cedula_index=univ['cedula_index'], n=n)
                if m.any():
                    motivos.append(COL_CEDULA)
                mascara_cliente |= m
            if tiene_nombre:
                m = _mascara_nombre(nombre_val=columnas[COL_NOMBRE][i],
                                    nombre_exact_index=univ['nombre_exact_index'],
                                    nombre_word_index=univ['nombre_word_index'],
                                    n=n)
                if m.any():
                    motivos.append(COL_NOMBRE)
                mascara_cliente |= m
            if not mascara_cliente.any():
                # NULO: sin coincidencia con datos del cliente
                etiquetas.append(ETIQUETA_NULO)
                ids_candidatos.append([])
                motivos_lista.append('')
                continue
            cand = mascara_cliente
        else:
            cand = np.ones(n, dtype=bool)

        # Aumentamos el Progreso en #3
        progress_cruce.progress(3/5, text="Ejecutando Reconocimiento por Características de Deuda")

        # Paso 2: Contraste con Datos de la Deuda (Banco, Casa de Cobro y Monto)
        banco_ok = False
        if tiene_banco:
            nuevo_cand, banco_ok = _acotar_texto(
                cand=cand,
                valor=columnas[COL_BANCO][i],
                valores=univ['banco_arr'],
                exact_index=univ['banco_exact_index'],
                char_index=univ['banco_char_index'],
                start2_index=univ['banco_start2_index'],
                gram_index=univ['banco_gram_index'],
                umbral_fuzzy=RATIO_FUZZY_BANCO,
                es_credito=False,
                n=n,
            )
            if banco_ok:
                cand = nuevo_cand
                motivos.append(COL_BANCO)
        casa_cobro_ok = False
        if casa_cobro_arr is not None:
            # Acotación por Casa de Cobro "simulando" que el Banco del universo sea la Casa de Cobro
            nuevo_cand, casa_cobro_ok = _acotar_texto(
                cand=cand,
                valor=casa_cobro_arr[i],
                valores=univ['banco_arr'],
                exact_index=univ['banco_exact_index'],
                char_index=univ['banco_char_index'],
                start2_index=univ['banco_start2_index'],
                gram_index=univ['banco_gram_index'],
                umbral_fuzzy=RATIO_FUZZY_BANCO,
                es_credito=False,
                n=n,
            )
            if casa_cobro_ok:
                cand = nuevo_cand
                motivos.append(MOTIVO_CASA_COBRO)
        monto_ok = False
        if tiene_monto:
            nuevo_cand, monto_ok = _acotar_monto(
                cand=cand,
                monto_val=columnas[COL_MONTO_ACTUAL][i],
                monto_arr=univ['monto_arr'],
                monto_sorted_idx=univ['monto_sorted_idx'],
                monto_sorted=univ['monto_sorted'],
                n=n,
            )
            if monto_ok:
                cand = nuevo_cand
                motivos.append(COL_MONTO_ACTUAL)

        # Paso 3: Contraste con Número de Crédito
        credito_ok = False
        if tiene_credito:
            nuevo_cand, credito_ok = _acotar_texto(
                cand=cand,
                valor=columnas[COL_CREDITO][i],
                valores=univ['credito_arr'],
                exact_index=univ['credito_exact_index'],
                char_index=univ['credito_char_index'],
                start2_index=univ['credito_start2_index'],
                gram_index=univ['credito_gram_index'],
                umbral_fuzzy=RATIO_FUZZY_CREDITO,
                es_credito=True,
                n=n,
            )
            if credito_ok:
                cand = nuevo_cand
                motivos.append(COL_CREDITO)

        posiciones = np.nonzero(cand)[0]
        candidatos = univ['id_deuda_arr'][posiciones].tolist()

        # Determinación de Etiquetas (los duplicados se resuelven en el Paso 4)
        if credito_ok:
            if len(posiciones) == 1:
                etiquetas.append(ETIQUETA_EXACTO)
                prospectos_exacto.append((i, candidatos[0]))
            else:
                # Múltiples Id_Deuda con el mismo Número de Crédito: entra a revisión
                etiquetas.append(ETIQUETA_DUPLICADO)
        elif banco_ok or monto_ok or casa_cobro_ok:
            etiquetas.append(ETIQUETA_AMBIGUO)
        else:
            etiquetas.append(ETIQUETA_ADDENDUM)
        ids_candidatos.append(candidatos)
        motivos_lista.append('|'.join(motivos))

    # Aumentamos el Proceso en 4
    progress_cruce.progress(4/5, text="Limpiando Duplicados de Exactitud")

    # Paso 4: Identificación de Duplicados entre los prospectos EXACTO
    reclamaciones = defaultdict(list)
    for indice, id_deuda in prospectos_exacto:
        reclamaciones[id_deuda].append(indice)
    for id_deuda, indices in reclamaciones.items():
        if len(indices) > 1:
            for indice in indices:
                etiquetas[indice] = ETIQUETA_DUPLICADO

    # Finalizado el Proceso en 5
    progress_cruce.progress(5/5, text="Cruce de Datos Realizado Correctamente")

    return_df = pd.DataFrame({
        'Id_Registro': id_registro_arr,
        'Ids_Candidatos': ids_candidatos,
        'Etiqueta_Registro': etiquetas,
        'Motivos_Etiqueta': motivos_lista,
    })

    return_df = OutputCruceSchema.validate(return_df)
    return return_df
