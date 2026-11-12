"""Tests del panel 'Cómo se Cruza' (control de las personas que cruzan).

Cubren la normalización de los responsables, los filtros por persona y fecha,
el resumen de cruces/Addendums/frecuencia, el desglose por etiqueta y el
timeline diario de la actividad.
"""

import unittest
from datetime import date

import pandas as pd

from ui.cruce_deudas_components import (
    _construir_df_detalles,
    _construir_resumen_personas_cruce,
    _construir_timeline_personas_cruce,
    _filtrar_detalles_personas_cruce,
    _normalizar_detalles_personas_cruce,
    limpiar_cache_columnas_cruce,
)

MAPA_NOMBRES = {
    'p1@x.com': 'Persona Uno',
    'p2@x.com': 'Persona Dos',
}


def _metadata(
    *,
    id_registro: str,
    etiqueta: str,
    identificado_por: str,
    id_definitivo: str = '',
    fechas: dict | None = None,
) -> dict:
    return {
        'Id_Registro': id_registro,
        'Casa_Cobro': 'Aliado A',
        'Archivo_Origen': 'base_1.xlsx',
        'Etiqueta': etiqueta,
        'Id_Definitivo': id_definitivo,
        'Ejecutivo_Subida': 'ejecutivo@x.com',
        'Identificado_Por': identificado_por,
        'Ultima_Actualizacion': fechas or {},
        'Deudas_Posibles': [],
        'Pagos_Cuotas': [],
        'Motivos_Cruce': [],
    }


class TestPanelPersonasCruce(unittest.TestCase):
    def setUp(self):
        limpiar_cache_columnas_cruce()
        self.cruce_df = pd.DataFrame([
            {
                'Id_Cruce': 'c1',
                'Cedula': '111',
                'Nombre_Cliente': 'Cliente 1',
                'Banco': 'BBVA Colombia',
                'Monto_Actual': 1000.0,
                'Numero_Credito': 'A1',
                'Metadata': _metadata(
                    id_registro='1',
                    etiqueta='EXACTO',
                    identificado_por='p1@x.com',
                    id_definitivo='D-1',
                    fechas={
                        'Sin Reconocer': '2026-01-01T08:00:00',
                        'Reconocido': '2026-01-01T10:00:00',
                    },
                ),
            },
            {
                'Id_Cruce': 'c2',
                'Cedula': '222',
                'Nombre_Cliente': 'Cliente 2',
                'Banco': 'BBVA Colombia',
                'Monto_Actual': 2000.0,
                'Numero_Credito': 'A2',
                'Metadata': _metadata(
                    id_registro='2',
                    etiqueta='EXACTO',
                    identificado_por='p1@x.com',
                    id_definitivo='D-2',
                    fechas={
                        'Sin Reconocer': '2026-01-01T08:00:00',
                        'Reconocido': '2026-01-02T09:00:00',
                    },
                ),
            },
            {
                'Id_Cruce': 'c3',
                'Cedula': '333',
                'Nombre_Cliente': 'Cliente 3',
                'Banco': 'BBVA Colombia',
                'Monto_Actual': 3000.0,
                'Numero_Credito': 'A3',
                'Metadata': _metadata(
                    id_registro='3',
                    etiqueta='ADDENDUM',
                    identificado_por='p1@x.com',
                    id_definitivo='ADDENDUM',
                    fechas={
                        'Sin Reconocer': '2026-01-01T08:00:00',
                        'Reconocido': '2026-01-02T11:00:00',
                    },
                ),
            },
            {
                'Id_Cruce': 'c4',
                'Cedula': '444',
                'Nombre_Cliente': 'Cliente 4',
                'Banco': 'Davivienda',
                'Monto_Actual': 4000.0,
                'Numero_Credito': 'A4',
                'Metadata': _metadata(
                    id_registro='4',
                    etiqueta='DUPLICADO',
                    identificado_por='p1@x.com',
                    id_definitivo='D-4',
                    fechas={'Sin Reconocer': '2026-01-03T08:00:00'},
                ),
            },
            {
                'Id_Cruce': 'c5',
                'Cedula': '555',
                'Nombre_Cliente': 'Cliente 5',
                'Banco': 'Davivienda',
                'Monto_Actual': 5000.0,
                'Numero_Credito': 'A5',
                'Metadata': _metadata(
                    id_registro='5',
                    etiqueta='NULO',
                    identificado_por='p2@x.com',
                    id_definitivo='D-5',
                    fechas={
                        'Sin Reconocer': '2026-01-01T08:00:00',
                        'Reconocido': '2026-01-01T12:00:00',
                    },
                ),
            },
            {
                'Id_Cruce': 'c6',
                'Cedula': '666',
                'Nombre_Cliente': 'Cliente 6',
                'Banco': 'Banco de Bogotá',
                'Monto_Actual': 6000.0,
                'Numero_Credito': 'A6',
                'Metadata': _metadata(
                    id_registro='6',
                    etiqueta='EXACTO',
                    identificado_por='Automatico',
                    id_definitivo='D-6',
                    fechas={
                        'Sin Reconocer': '2026-01-01T08:00:00',
                        'Reconocido': '2026-01-03T09:00:00',
                    },
                ),
            },
            {
                'Id_Cruce': 'c7',
                'Cedula': '777',
                'Nombre_Cliente': 'Cliente 7',
                'Banco': 'Banco de Bogotá',
                'Monto_Actual': 7000.0,
                'Numero_Credito': 'A7',
                'Metadata': _metadata(
                    id_registro='7',
                    etiqueta='AMBIGUO',
                    identificado_por='N/A',
                    fechas={'Sin Reconocer': '2026-01-01T08:00:00'},
                ),
            },
        ])
        self.detalles = _construir_df_detalles(
            cruce_df=self.cruce_df,
            mapa_nombres=MAPA_NOMBRES,
        )

    def tearDown(self):
        limpiar_cache_columnas_cruce()

    def _personas(self, **kwargs) -> pd.DataFrame:
        return _filtrar_detalles_personas_cruce(
            df_detalles=self.detalles,
            **kwargs,
        )

    def test_normalizacion_de_personas(self):
        df = _normalizar_detalles_personas_cruce(df_detalles=self.detalles)
        fila = df.set_index('Id_Cruce').loc['c1']

        self.assertEqual(fila['_Persona'], 'p1@x.com')
        self.assertEqual(fila['_Nombre_Persona'], 'Persona Uno')
        self.assertEqual(fila['_Etiqueta_Persona'], 'Persona Uno (p1@x.com)')

        fila_auto = df.set_index('Id_Cruce').loc['c6']
        self.assertEqual(fila_auto['_Persona'], 'Automatico')
        self.assertEqual(fila_auto['_Etiqueta_Persona'], 'Automático')

    def test_filtro_manual_excluye_automaticos_y_sin_registro(self):
        df = self._personas()

        self.assertEqual(sorted(df['Id_Cruce'].tolist()), ['c1', 'c2', 'c3', 'c4', 'c5'])
        self.assertNotIn('Automatico', df['_Persona'].tolist())
        self.assertNotIn('No registrado', df['_Persona'].tolist())

    def test_filtro_incluye_automaticos_cuando_se_solicita(self):
        df = self._personas(incluir_automaticos=True)

        self.assertIn('Automatico', df['_Persona'].tolist())
        self.assertNotIn('No registrado', df['_Persona'].tolist())
        self.assertEqual(len(df), 6)

    def test_resumen_por_persona(self):
        resumen = _construir_resumen_personas_cruce(df_personas=self._personas())
        resumen = resumen.set_index('_Persona')

        fila_p1 = resumen.loc['p1@x.com']
        self.assertEqual(int(fila_p1['Cruces']), 4)
        self.assertEqual(int(fila_p1['Addendums']), 1)
        self.assertAlmostEqual(float(fila_p1['Pct_Addendums']), 0.25)
        self.assertAlmostEqual(float(fila_p1['Pct_Total']), 4 / 5)
        self.assertEqual(int(fila_p1['Dias_Activos']), 2)
        self.assertAlmostEqual(float(fila_p1['Frecuencia_Diaria']), 2.0)
        self.assertEqual(int(fila_p1['Etiqueta_EXACTO']), 2)
        self.assertEqual(int(fila_p1['Etiqueta_ADDENDUM']), 1)
        self.assertEqual(int(fila_p1['Etiqueta_DUPLICADO']), 1)
        self.assertEqual(int(fila_p1['Etiqueta_NULO']), 0)
        self.assertEqual(int(fila_p1['Bases']), 1)

        fila_p2 = resumen.loc['p2@x.com']
        self.assertEqual(int(fila_p2['Cruces']), 1)
        self.assertEqual(int(fila_p2['Addendums']), 0)
        self.assertAlmostEqual(float(fila_p2['Pct_Addendums']), 0.0)
        self.assertEqual(int(fila_p2['Dias_Activos']), 1)
        self.assertAlmostEqual(float(fila_p2['Frecuencia_Diaria']), 1.0)

    def test_resumen_vacio(self):
        df_vacio = self._personas().iloc[0:0]

        self.assertTrue(_construir_resumen_personas_cruce(df_personas=df_vacio).empty)
        self.assertTrue(_construir_timeline_personas_cruce(df_personas=df_vacio).empty)

    def test_filtro_por_persona_y_rango_de_fechas(self):
        df = self._personas(
            personas=['p1@x.com'],
            rango_fecha=(date(2026, 1, 2), date(2026, 1, 2)),
        )

        self.assertEqual(sorted(df['Id_Cruce'].tolist()), ['c2', 'c3'])

        # El registro sin fecha de reconocimiento no entra al rango
        self.assertNotIn('c4', df['Id_Cruce'].tolist())

    def test_timeline_por_dia_y_persona(self):
        timeline = _construir_timeline_personas_cruce(df_personas=self._personas())

        self.assertEqual(len(timeline), 3)
        fila = timeline[
            (timeline['Fecha'] == pd.Timestamp('2026-01-02'))
            & (timeline['_Persona'] == 'p1@x.com')
        ].iloc[0]
        self.assertEqual(int(fila['Cruces']), 2)
        self.assertEqual(int(fila['Addendums']), 1)
        self.assertEqual(int(fila['Etiqueta_EXACTO']), 1)
        self.assertEqual(int(fila['Etiqueta_ADDENDUM']), 1)

        # El registro sin fecha de reconocimiento queda fuera del timeline
        self.assertEqual(
            int(timeline[timeline['_Persona'] == 'p1@x.com']['Cruces'].sum()),
            3,
        )


if __name__ == '__main__':
    unittest.main()
