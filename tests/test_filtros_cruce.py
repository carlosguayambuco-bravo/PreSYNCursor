"""Tests de los filtros y el ordenamiento de la Identificación Manual del cruce.

Cubren la construcción de columnas internas, los filtros determinantes para
identificar una deuda (aliado, etiqueta, estado, banco, cédula, monto, fechas
y búsqueda global) y el ordenamiento ascendente/descendente.
"""

import unittest
from datetime import date

import pandas as pd

from ui.cruce_deudas_components import (
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
    _construir_df_filtros_cruce,
    _ordenar_cruce,
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


if __name__ == '__main__':
    unittest.main()
