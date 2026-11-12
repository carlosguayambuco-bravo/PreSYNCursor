"""Tests de los filtros y el ordenamiento de la Identificación Manual del cruce.

Cubren la construcción de columnas internas, los filtros determinantes para
identificar una deuda (aliado, etiqueta, estado, banco, cédula, monto, fechas
y búsqueda global), el ordenamiento ascendente/descendente y la reutilización
de las columnas internas cacheadas por Id_Cruce.
"""

import unittest
from datetime import date

import pandas as pd
import streamlit as st

from ui.cruce_deudas_components import (
    LLAVE_CACHE_DETALLES_CRUCE,
    LLAVE_CACHE_FILTROS_CRUCE,
    OPCION_FILTRO_FECHA_CRUCE,
    OPCION_FILTRO_FECHA_ULTIMA,
    OPCION_FILTRO_ID_ADDENDUM,
    OPCION_FILTRO_ID_CON,
    OPCION_FILTRO_ID_SIN,
    OPCION_FILTRO_ID_TODOS,
    OPCION_ORDEN_BANCO,
    OPCION_ORDEN_CEDULA,
    OPCION_ORDEN_ETIQUETA,
    OPCION_ORDEN_FECHA_CRUCE,
    OPCION_ORDEN_MONTO_ACTUAL,
    OPCION_ORDEN_ORIGINAL,
    OPCION_ORDEN_ULTIMA_ACTUALIZACION,
    _aplicar_filtros_cruce,
    _construir_df_detalles,
    _construir_df_filtros_cruce,
    _ordenar_cruce,
    limpiar_cache_columnas_cruce,
)


def _metadata(
    *,
    id_registro: str,
    casa: str,
    alias: str = '',
    archivo: str = 'base.xlsx',
    etiqueta: str,
    id_definitivo: str = '',
    fechas: dict,
    deudas: list | None = None,
) -> dict:
    return {
        'Id_Registro': id_registro,
        'Casa_Cobro': casa,
        'Alias_Casa': alias,
        'Archivo_Origen': archivo,
        'Etiqueta': etiqueta,
        'Id_Definitivo': id_definitivo,
        'Ultima_Actualizacion': fechas,
        'Deudas_Posibles': deudas or [],
        'Pagos_Cuotas': [],
        'Motivos_Cruce': [],
    }


class TestFiltrosIdentificacionManual(unittest.TestCase):
    def setUp(self):
        limpiar_cache_columnas_cruce()
        self.cruce_df = pd.DataFrame([
            {
                'Id_Cruce': 'c1',
                'Cedula': '1234567890',
                'Nombre_Cliente': 'Ana Pérez',
                'Banco': 'BBVA Colombia',
                'Monto_Actual': 1000.0,
                'Numero_Credito': 'A1',
                'Metadata': _metadata(
                    id_registro='1',
                    casa='Aliado A',
                    alias='Alias 1',
                    archivo='base_1.xlsx',
                    etiqueta='AMBIGUO',
                    fechas={'Sin Reconocer': '2026-01-01T10:00:00'},
                    deudas=[
                        {
                            'Id_Deuda': 'D-100',
                            'Banco': 'BBVA Colombia',
                            'Numero_Credito': 'A1',
                        }
                    ],
                ),
            },
            {
                'Id_Cruce': 'c2',
                'Cedula': '9876543210',
                'Nombre_Cliente': 'Luis Gómez',
                'Banco': 'Davivienda',
                'Monto_Actual': 5000.0,
                'Numero_Credito': 'B2',
                'Metadata': _metadata(
                    id_registro='2',
                    casa='Aliado B',
                    archivo='base_2.xlsx',
                    etiqueta='EXACTO',
                    id_definitivo='D-200',
                    fechas={
                        'Sin Reconocer': '2026-02-01T10:00:00',
                        'Reconocido': '2026-02-02T10:00:00',
                    },
                    deudas=[
                        {
                            'Id_Deuda': 'D-200',
                            'Banco': 'Davivienda',
                            'Numero_Credito': 'B2',
                        }
                    ],
                ),
            },
            {
                'Id_Cruce': 'c3',
                'Cedula': '1234567890',
                'Nombre_Cliente': 'Ana Pérez',
                'Banco': 'BBVA Colombia',
                'Monto_Actual': 2500.0,
                'Numero_Credito': 'A2',
                'Metadata': _metadata(
                    id_registro='3',
                    casa='Aliado A',
                    alias='Alias 2',
                    archivo='base_1.xlsx',
                    etiqueta='NULO',
                    fechas={'Sin Reconocer': '2026-03-01T10:00:00'},
                ),
            },
            {
                'Id_Cruce': 'c4',
                'Cedula': '555000111',
                'Nombre_Cliente': 'Carla Ruiz',
                'Banco': 'BBVA Colombia',
                'Monto_Actual': 8000.0,
                'Numero_Credito': 'C3',
                'Metadata': _metadata(
                    id_registro='4',
                    casa='Aliado A',
                    alias='Alias 1',
                    archivo='base_1.xlsx',
                    etiqueta='ADDENDUM',
                    id_definitivo='ADDENDUM',
                    fechas={
                        'Sin Reconocer': '2026-04-01T10:00:00',
                        'Reconocido': '2026-04-02T10:00:00',
                        'Subido Alianzas': '2026-04-03T10:00:00',
                    },
                ),
            },
        ])
        self.df = _construir_df_filtros_cruce(cruce_df=self.cruce_df)

    def _ids(self, df: pd.DataFrame) -> list[str]:
        return df['Id_Cruce'].tolist()

    def test_construir_columnas_internas(self):
        fila_c1 = self.df[self.df['Id_Cruce'] == 'c1'].iloc[0]
        fila_c2 = self.df[self.df['Id_Cruce'] == 'c2'].iloc[0]
        fila_c4 = self.df[self.df['Id_Cruce'] == 'c4'].iloc[0]

        self.assertEqual(fila_c1['_Casa_Cobro'], 'Aliado A')
        self.assertEqual(fila_c1['_Etiqueta'], 'AMBIGUO')
        self.assertEqual(fila_c1['_Estado'], 'Sin Reconocer')
        self.assertFalse(bool(fila_c1['_Tiene_Id_Definitivo_Actual']))
        self.assertTrue(bool(fila_c2['_Tiene_Id_Definitivo_Metadata']))
        self.assertEqual(fila_c2['_Estado'], 'Reconocido')
        self.assertTrue(bool(fila_c4['_Es_Addendum_Metadata']))
        self.assertEqual(fila_c4['_Estado'], 'Subido Alianzas')
        self.assertEqual(fila_c1['_Fecha_Sin_Reconocer'], pd.Timestamp('2026-01-01 10:00:00'))
        self.assertIn('d-100', fila_c1['_Busqueda'])
        self.assertIn('ana pérez', fila_c1['_Busqueda'])

    def test_cambios_pendientes_de_id_definitivo(self):
        df = _construir_df_filtros_cruce(
            cruce_df=self.cruce_df,
            cambios={'c1': 'D-999'},
        )
        fila_c1 = df[df['Id_Cruce'] == 'c1'].iloc[0]

        self.assertEqual(fila_c1['_Id_Definitivo_Actual'], 'D-999')
        self.assertTrue(bool(fila_c1['_Tiene_Id_Definitivo_Actual']))
        self.assertFalse(bool(fila_c1['_Tiene_Id_Definitivo_Metadata']))
        self.assertEqual(fila_c1['_Id_Definitivo_Metadata'], '')
        self.assertIn('d-999', fila_c1['_Busqueda'])

        # El Filtro de Id_Definitivo usa lo Guardado: un Cambio Pendiente no Oculta la Fila
        df_pendientes = _aplicar_filtros_cruce(
            df=df,
            tipo_id=OPCION_FILTRO_ID_SIN,
        )
        self.assertEqual(self._ids(df_pendientes), ['c1', 'c3'])

    def test_filtros_de_contexto_y_tipo_id(self):
        df = _aplicar_filtros_cruce(
            df=self.df,
            casas=['Aliado A'],
            etiquetas=['AMBIGUO', 'NULO'],
            bancos=['BBVA Colombia'],
            tipo_id=OPCION_FILTRO_ID_SIN,
        )
        self.assertEqual(self._ids(df), ['c1', 'c3'])

        df_con_id = _aplicar_filtros_cruce(df=self.df, tipo_id=OPCION_FILTRO_ID_CON)
        self.assertEqual(self._ids(df_con_id), ['c2', 'c4'])

        df_addendum = _aplicar_filtros_cruce(df=self.df, tipo_id=OPCION_FILTRO_ID_ADDENDUM)
        self.assertEqual(self._ids(df_addendum), ['c4'])

        df_todos = _aplicar_filtros_cruce(df=self.df, tipo_id=OPCION_FILTRO_ID_TODOS)
        self.assertEqual(self._ids(df_todos), ['c1', 'c2', 'c3', 'c4'])

    def test_filtro_no_validados_incluye_registros_identificados(self):
        df = _aplicar_filtros_cruce(
            df=self.df,
            tipo_id=OPCION_FILTRO_ID_SIN,
            filtrar_no_validados=True,
            ids_no_validados={'D-200'},
        )
        self.assertEqual(self._ids(df), ['c2'])

        df_sin_ids = _aplicar_filtros_cruce(
            df=self.df,
            filtrar_no_validados=True,
            ids_no_validados=set(),
        )
        self.assertTrue(df_sin_ids.empty)

    def test_filtro_cedula_exacta_y_rango_de_montos(self):
        df_cedula = _aplicar_filtros_cruce(
            df=self.df,
            cedula='1.234.567.890',
            tipo_id=OPCION_FILTRO_ID_TODOS,
        )
        self.assertEqual(self._ids(df_cedula), ['c1', 'c3'])

        df_cedula_parcial = _aplicar_filtros_cruce(
            df=self.df,
            cedula='123',
            tipo_id=OPCION_FILTRO_ID_TODOS,
        )
        self.assertTrue(df_cedula_parcial.empty)

        df_montos = _aplicar_filtros_cruce(
            df=self.df,
            monto_min=2500.0,
            monto_max=1000.0,
            tipo_id=OPCION_FILTRO_ID_TODOS,
        )
        self.assertEqual(self._ids(df_montos), ['c1', 'c3'])

    def test_busqueda_global_por_id_deuda_y_credito(self):
        df_id_deuda = _aplicar_filtros_cruce(
            df=self.df,
            busqueda='D-100',
            tipo_id=OPCION_FILTRO_ID_TODOS,
        )
        self.assertEqual(self._ids(df_id_deuda), ['c1'])

        df_credito = _aplicar_filtros_cruce(
            df=self.df,
            busqueda='B2',
            tipo_id=OPCION_FILTRO_ID_TODOS,
        )
        self.assertEqual(self._ids(df_credito), ['c2'])

        df_cedula_puntos = _aplicar_filtros_cruce(
            df=self.df,
            busqueda='1.234.567.890',
            tipo_id=OPCION_FILTRO_ID_TODOS,
        )
        self.assertEqual(self._ids(df_cedula_puntos), ['c1', 'c3'])

    def test_filtro_rango_de_fechas(self):
        df_cruce = _aplicar_filtros_cruce(
            df=self.df,
            campo_fecha=OPCION_FILTRO_FECHA_CRUCE,
            rango_fecha=(date(2026, 2, 1), date(2026, 3, 1)),
            tipo_id=OPCION_FILTRO_ID_TODOS,
        )
        self.assertEqual(self._ids(df_cruce), ['c2', 'c3'])

        df_ultima = _aplicar_filtros_cruce(
            df=self.df,
            campo_fecha=OPCION_FILTRO_FECHA_ULTIMA,
            rango_fecha=(date(2026, 4, 1), date(2026, 4, 30)),
            tipo_id=OPCION_FILTRO_ID_TODOS,
        )
        self.assertEqual(self._ids(df_ultima), ['c4'])

    def test_ordenamiento_ascendente_y_descendente(self):
        df = _aplicar_filtros_cruce(df=self.df, tipo_id=OPCION_FILTRO_ID_TODOS)

        df_monto_asc = _ordenar_cruce(
            df=df,
            orden=OPCION_ORDEN_MONTO_ACTUAL,
            ascendente=True,
        )
        self.assertEqual(self._ids(df_monto_asc), ['c1', 'c3', 'c2', 'c4'])

        df_monto_desc = _ordenar_cruce(
            df=df,
            orden=OPCION_ORDEN_MONTO_ACTUAL,
            ascendente=False,
        )
        self.assertEqual(self._ids(df_monto_desc), ['c4', 'c2', 'c3', 'c1'])

        df_etiqueta = _ordenar_cruce(
            df=df,
            orden=OPCION_ORDEN_ETIQUETA,
            ascendente=True,
        )
        self.assertEqual(self._ids(df_etiqueta), ['c2', 'c1', 'c4', 'c3'])

        df_original_desc = _ordenar_cruce(
            df=df,
            orden=OPCION_ORDEN_ORIGINAL,
            ascendente=False,
        )
        self.assertEqual(self._ids(df_original_desc), ['c4', 'c3', 'c2', 'c1'])

        df_cedula = _ordenar_cruce(
            df=df,
            orden=OPCION_ORDEN_CEDULA,
            ascendente=True,
        )
        self.assertEqual(self._ids(df_cedula), ['c1', 'c3', 'c4', 'c2'])

        df_banco = _ordenar_cruce(
            df=df,
            orden=OPCION_ORDEN_BANCO,
            ascendente=True,
        )
        self.assertEqual(self._ids(df_banco), ['c1', 'c3', 'c4', 'c2'])

        df_fecha = _ordenar_cruce(
            df=df,
            orden=OPCION_ORDEN_FECHA_CRUCE,
            ascendente=True,
        )
        self.assertEqual(self._ids(df_fecha), ['c1', 'c2', 'c3', 'c4'])

        df_ultima = _ordenar_cruce(
            df=df,
            orden=OPCION_ORDEN_ULTIMA_ACTUALIZACION,
            ascendente=False,
        )
        self.assertEqual(self._ids(df_ultima), ['c4', 'c3', 'c2', 'c1'])


class TestCacheColumnasCruce(unittest.TestCase):
    """Valida que las columnas internas se reutilicen y se invaliden correctamente."""

    def setUp(self):
        limpiar_cache_columnas_cruce()
        self.cruce_df = pd.DataFrame([
            {
                'Id_Cruce': 'c1',
                'Cedula': '1234567890',
                'Nombre_Cliente': 'Ana Pérez',
                'Banco': 'BBVA Colombia',
                'Monto_Actual': 1000.0,
                'Numero_Credito': 'A1',
                'Metadata': {
                    'Id_Registro': '1',
                    'Casa_Cobro': 'Aliado A',
                    'Archivo_Origen': 'base_1.xlsx',
                    'Etiqueta': 'AMBIGUO',
                    'Identificado_Por': 'persona@x.com',
                    'Ultima_Actualizacion': {
                        'Sin Reconocer': '2026-01-01T10:00:00',
                        'Reconocido': '2026-01-02T10:00:00',
                    },
                    'Deudas_Posibles': [],
                    'Pagos_Cuotas': [],
                    'Motivos_Cruce': [],
                },
            },
            {
                'Id_Cruce': 'c2',
                'Cedula': '9876543210',
                'Nombre_Cliente': 'Luis Gómez',
                'Banco': 'Davivienda',
                'Monto_Actual': 5000.0,
                'Numero_Credito': 'B2',
                'Metadata': {
                    'Id_Registro': '2',
                    'Casa_Cobro': 'Aliado B',
                    'Archivo_Origen': 'base_2.xlsx',
                    'Etiqueta': 'EXACTO',
                    'Id_Definitivo': 'D-200',
                    'Ultima_Actualizacion': {'Sin Reconocer': '2026-02-01T10:00:00'},
                    'Deudas_Posibles': [],
                    'Pagos_Cuotas': [],
                    'Motivos_Cruce': [],
                },
            },
        ])

    def tearDown(self):
        limpiar_cache_columnas_cruce()

    def test_filtros_reutiliza_la_construccion_cacheada(self):
        df_1 = _construir_df_filtros_cruce(cruce_df=self.cruce_df)
        cache_1 = st.session_state.get(LLAVE_CACHE_FILTROS_CRUCE)
        df_2 = _construir_df_filtros_cruce(cruce_df=self.cruce_df)
        cache_2 = st.session_state.get(LLAVE_CACHE_FILTROS_CRUCE)

        self.assertIsNotNone(cache_1)
        self.assertIsNotNone(cache_2)
        self.assertIs(cache_1['df'], cache_2['df'])
        pd.testing.assert_frame_equal(df_1, df_2)

    def test_cambios_pendientes_no_reconstruyen_columnas(self):
        _construir_df_filtros_cruce(cruce_df=self.cruce_df)
        cache_antes = st.session_state.get(LLAVE_CACHE_FILTROS_CRUCE)

        df = _construir_df_filtros_cruce(
            cruce_df=self.cruce_df,
            cambios={'c1': 'D-999'},
        )
        cache_despues = st.session_state.get(LLAVE_CACHE_FILTROS_CRUCE)

        self.assertIs(cache_antes['df'], cache_despues['df'])
        self.assertEqual(df.loc[0, '_Id_Definitivo_Actual'], 'D-999')
        self.assertIn('d-999', df.loc[0, '_Busqueda'])
        self.assertEqual(df.loc[0, '_Id_Definitivo_Metadata'], '')

    def test_cache_se_invalida_al_cambiar_la_metadata(self):
        _construir_df_filtros_cruce(cruce_df=self.cruce_df)
        cache_antes = st.session_state.get(LLAVE_CACHE_FILTROS_CRUCE)

        df_modificado = self.cruce_df.copy()
        metadata = dict(df_modificado.loc[0, 'Metadata'])
        metadata['Etiqueta'] = 'NULO'
        metadata['Id_Definitivo'] = 'D-777'
        df_modificado.at[0, 'Metadata'] = metadata

        df = _construir_df_filtros_cruce(cruce_df=df_modificado)
        cache_despues = st.session_state.get(LLAVE_CACHE_FILTROS_CRUCE)

        self.assertIsNot(cache_antes['df'], cache_despues['df'])
        self.assertEqual(df.loc[0, '_Etiqueta'], 'NULO')
        self.assertEqual(df.loc[0, '_Id_Definitivo_Metadata'], 'D-777')

    def test_detalles_reutiliza_la_construccion_cacheada(self):
        df_1 = _construir_df_detalles(cruce_df=self.cruce_df, mapa_nombres={})
        cache_1 = st.session_state.get(LLAVE_CACHE_DETALLES_CRUCE)
        df_2 = _construir_df_detalles(cruce_df=self.cruce_df, mapa_nombres={})
        cache_2 = st.session_state.get(LLAVE_CACHE_DETALLES_CRUCE)

        self.assertIs(cache_1['df'], cache_2['df'])
        pd.testing.assert_frame_equal(df_1, df_2)

    def test_detalles_resuelven_el_nombre_del_responsable(self):
        df = _construir_df_detalles(
            cruce_df=self.cruce_df,
            mapa_nombres={'persona@x.com': 'Ana'},
        )

        self.assertEqual(df.loc[0, '_Identificado_Por_Nombre'], 'Ana')
        self.assertEqual(df.loc[0, '_Estado'], 'Reconocido')
        self.assertEqual(df.loc[1, '_Estado'], 'Sin Reconocer')


if __name__ == '__main__':
    unittest.main()
