"""Tests del Centro de Control de Masivas.

Estos tests cubren las funciones puras de distribución de portafolios, llenado de
metadata y construcción del registro de cambios. No acceden a Google Sheets,
Streamlit ni Metabase.
"""

import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

import data.data_loader as data_loader
import data.data_uploader as data_uploader
from modules.control_masivas import (
    _serializar_metadata,
    actualizar_metadata_portafolios,
    completar_metadata_masivas,
    construir_cambios_masivas,
    construir_log_cambios_masivas,
    distribuir_portafolios_masivas,
    metadata_masiva_completa,
    resumen_bases_sin_metadata,
)


class TestDistribucionPortafoliosMasivas(unittest.TestCase):
    def _df(self, filas):
        return pd.DataFrame(filas)

    def _fila(
        self,
        *,
        fila=2,
        id_deuda="D1",
        referencia="REF1",
        casa="ALIADO A",
        fecha="2026-11-06",
        es_portafolio=True,
        pab_origen=600000,
        pab_propuesta=500000,
        id_cruce=None,
        metadata=None,
    ):
        return {
            "Fila_Sheets": fila,
            "Id_Deuda": id_deuda,
            "Referencia": referencia,
            "Casa_Cobro": casa,
            "Fecha_Masiva": pd.Timestamp(fecha),
            "Es_Portafolio": es_portafolio,
            "PaB_Origen": pab_origen,
            "PaB_Propuesta": pab_propuesta,
            "Metadata": metadata if metadata is not None else {"Id_Cruce": id_cruce or "C{}".format(fila)},
        }

    def test_distribuye_cuando_todos_los_pagos_son_iguales(self):
        df = self._df([
            self._fila(fila=2, id_deuda="D1", pab_origen=600000, pab_propuesta=500000),
            self._fila(fila=3, id_deuda="D2", pab_origen=400000, pab_propuesta=500000),
        ])

        distribuido, detalle = distribuir_portafolios_masivas(df)

        self.assertEqual(distribuido["PaB_Propuesta"].tolist(), [300000.0, 200000.0])
        self.assertEqual(len(detalle), 2)
        self.assertTrue(detalle["Regla_Especial"].all())
        self.assertFalse(detalle["Regla_JCAP"].any())

    def test_regla_jcap_redistribuye_suma_de_originales(self):
        df = self._df([
            self._fila(fila=2, id_deuda="D1", casa="JCAP", pab_origen=700000, pab_propuesta=100),
            self._fila(fila=3, id_deuda="D2", casa="JCAP", pab_origen=300000, pab_propuesta=50),
        ])

        distribuido, detalle = distribuir_portafolios_masivas(df)

        self.assertEqual(distribuido["PaB_Propuesta"].tolist(), [105.0, 45.0])
        self.assertTrue(detalle["Regla_JCAP"].all())
        self.assertFalse(detalle["Regla_Especial"].any())

    def test_no_modifica_casa_distinta_a_jcap(self):
        df = self._df([
            self._fila(fila=2, id_deuda="D1", casa="OTRO", pab_origen=700000, pab_propuesta=100),
            self._fila(fila=3, id_deuda="D2", casa="OTRO", pab_origen=300000, pab_propuesta=50),
        ])

        distribuido, detalle = distribuir_portafolios_masivas(df)

        self.assertEqual(distribuido["PaB_Propuesta"].tolist(), [100.0, 50.0])
        self.assertTrue(detalle.empty)

    def test_no_modifica_grupos_sin_portafolio(self):
        df = self._df([
            self._fila(fila=2, id_deuda="D1", es_portafolio=False, pab_origen=600000, pab_propuesta=500000),
            self._fila(fila=3, id_deuda="D2", es_portafolio=False, pab_origen=400000, pab_propuesta=500000),
        ])

        distribuido, detalle = distribuir_portafolios_masivas(df)

        self.assertEqual(distribuido["PaB_Propuesta"].tolist(), [500000.0, 500000.0])
        self.assertTrue(detalle.empty)

    def test_no_falla_si_falta_pab_origen(self):
        df = self._df([
            self._fila(fila=2, id_deuda="D1", pab_origen=None, pab_propuesta=500000),
            self._fila(fila=3, id_deuda="D2", pab_origen=400000, pab_propuesta=500000),
        ])

        distribuido, detalle = distribuir_portafolios_masivas(df)

        self.assertEqual(distribuido["PaB_Propuesta"].tolist(), [500000.0, 500000.0])
        self.assertTrue(detalle.empty)

    def test_no_aplica_jcap_si_falta_un_pago(self):
        df = self._df([
            self._fila(fila=2, id_deuda="D1", casa="JCAP", pab_origen=500000, pab_propuesta=100),
            self._fila(fila=3, id_deuda="D2", casa="JCAP", pab_origen=300000, pab_propuesta=50),
            self._fila(fila=4, id_deuda="D3", casa="JCAP", pab_origen=200000, pab_propuesta=None),
        ])

        distribuido, detalle = distribuir_portafolios_masivas(df)

        self.assertEqual(distribuido["PaB_Propuesta"].iloc[0], 100.0)
        self.assertEqual(distribuido["PaB_Propuesta"].iloc[1], 50.0)
        self.assertTrue(pd.isna(distribuido["PaB_Propuesta"].iloc[2]))
        self.assertTrue(detalle.empty)

    def test_exige_columnas_requeridas(self):
        with self.assertRaises(ValueError):
            distribuir_portafolios_masivas(pd.DataFrame([{"Referencia": "REF1"}]))


class TestMetadataMasivas(unittest.TestCase):
    def _df(self, filas):
        return pd.DataFrame(filas)

    def test_detecta_metadata_completa(self):
        self.assertTrue(metadata_masiva_completa({
            "Id_Cruce": "C1",
            "Tipo_Contraoferta": "Descuento Máximo",
            "Fecha_Limite_Uso": pd.Timestamp("2026-11-30"),
        }))
        self.assertFalse(metadata_masiva_completa(None))
        self.assertFalse(metadata_masiva_completa({"Id_Cruce": "C1"}))

    def test_completa_metadata_faltante(self):
        df = self._df([{
            "Casa_Cobro": "ALIADO A",
            "Fecha_Masiva": pd.Timestamp("2026-11-06"),
            "Metadata": pd.NA,
        }])
        configs = {
            ("ALIADO A", pd.Timestamp("2026-11-06")): {
                "Tipo_Contraoferta": "ContraOferta sin Compromiso",
                "Fecha_Limite_Uso": pd.Timestamp("2026-11-30"),
                "Alias": "Alias 1",
            }
        }

        resultado = completar_metadata_masivas(df, configs)
        metadata = resultado.loc[0, "Metadata"]

        self.assertTrue(metadata_masiva_completa(metadata))
        self.assertTrue(str(metadata["Id_Cruce"]).strip())
        self.assertEqual(metadata["Tipo_Contraoferta"], "ContraOferta sin Compromiso")
        self.assertEqual(metadata["Alias"], "Alias 1")
        self.assertEqual(metadata["Fecha_Limite_Uso"], pd.Timestamp("2026-11-30"))

    def test_preserva_metadata_existente(self):
        metadata_original = {
            "Id_Cruce": "C1",
            "Tipo_Contraoferta": "Descuento Máximo",
            "Fecha_Limite_Uso": pd.Timestamp("2026-11-15"),
            "Alias": "Original",
            "Id_Portafolio": "",
            "PaB_Portafolio": None,
        }
        df = self._df([{
            "Casa_Cobro": "ALIADO A",
            "Fecha_Masiva": pd.Timestamp("2026-11-06"),
            "Metadata": metadata_original,
        }])
        configs = {
            ("ALIADO A", pd.Timestamp("2026-11-06")): {
                "Tipo_Contraoferta": "ContraOferta de Pago Obligatorio",
                "Fecha_Limite_Uso": pd.Timestamp("2026-12-31"),
                "Alias": "Nuevo",
            }
        }

        resultado = completar_metadata_masivas(df, configs)

        self.assertEqual(resultado.loc[0, "Metadata"], metadata_original)

    def test_exige_configuracion_para_base_sin_metadata(self):
        df = self._df([{
            "Casa_Cobro": "ALIADO A",
            "Fecha_Masiva": pd.Timestamp("2026-11-06"),
            "Metadata": pd.NA,
        }])
        with self.assertRaises(ValueError):
            completar_metadata_masivas(df, {})

    def test_serializacion_metadata_equipara_enteros_y_flotantes(self):
        metadata_entero = {
            "Id_Cruce": "C1",
            "PaB_Portafolio": 500000,
            "Fecha_Limite_Uso": pd.Timestamp("2026-11-30"),
        }
        metadata_flotante = {
            "Id_Cruce": "C1",
            "PaB_Portafolio": 500000.0,
            "Fecha_Limite_Uso": pd.Timestamp("2026-11-30"),
        }
        self.assertEqual(
            _serializar_metadata(metadata_entero),
            _serializar_metadata(metadata_flotante),
        )


class TestMetadataPortafolios(unittest.TestCase):
    def _fila(self, *, fila, id_deuda, id_cruce, es_portafolio, pab, metadata=None):
        return {
            "Fila_Sheets": fila,
            "Id_Deuda": id_deuda,
            "Referencia": "REF1",
            "Casa_Cobro": "ALIADO A",
            "Fecha_Masiva": pd.Timestamp("2026-11-06"),
            "Es_Portafolio": es_portafolio,
            "PaB_Origen": 100000,
            "PaB_Propuesta": pab,
            "Metadata": metadata or {
                "Id_Cruce": id_cruce,
                "Tipo_Contraoferta": "Descuento Máximo",
                "Fecha_Limite_Uso": pd.Timestamp("2026-11-30"),
                "Alias": None,
            },
        }

    def test_actualiza_portafolio_completo(self):
        df = pd.DataFrame([
            self._fila(fila=2, id_deuda="D1", id_cruce="C1", es_portafolio=True, pab=600000),
            self._fila(fila=3, id_deuda="D2", id_cruce="C2", es_portafolio=True, pab=400000),
        ])

        resultado = actualizar_metadata_portafolios(df)

        self.assertEqual(resultado.loc[0, "Metadata"]["Id_Portafolio"], "C1-C2")
        self.assertEqual(resultado.loc[1, "Metadata"]["Id_Portafolio"], "C1-C2")
        self.assertEqual(resultado.loc[0, "Metadata"]["PaB_Portafolio"], 1000000.0)
        self.assertEqual(resultado.loc[1, "Metadata"]["PaB_Portafolio"], 1000000.0)

    def test_no_marca_portafolio_si_una_fila_no_lo_es(self):
        df = pd.DataFrame([
            self._fila(fila=2, id_deuda="D1", id_cruce="C1", es_portafolio=True, pab=600000),
            self._fila(fila=3, id_deuda="D2", id_cruce="C2", es_portafolio=False, pab=400000),
        ])

        resultado = actualizar_metadata_portafolios(df)

        self.assertEqual(resultado.loc[0, "Metadata"]["Id_Portafolio"], "")
        self.assertIsNone(resultado.loc[0, "Metadata"]["PaB_Portafolio"])
        self.assertEqual(resultado.loc[1, "Metadata"]["Id_Portafolio"], "")
        self.assertIsNone(resultado.loc[1, "Metadata"]["PaB_Portafolio"])

    def test_no_marca_portafolio_si_falta_un_monto(self):
        df = pd.DataFrame([
            self._fila(fila=2, id_deuda="D1", id_cruce="C1", es_portafolio=True, pab=600000),
            self._fila(fila=3, id_deuda="D2", id_cruce="C2", es_portafolio=True, pab=None),
        ])

        resultado = actualizar_metadata_portafolios(df)

        self.assertEqual(resultado.loc[0, "Metadata"]["Id_Portafolio"], "")
        self.assertIsNone(resultado.loc[0, "Metadata"]["PaB_Portafolio"])
        self.assertEqual(resultado.loc[1, "Metadata"]["Id_Portafolio"], "")
        self.assertIsNone(resultado.loc[1, "Metadata"]["PaB_Portafolio"])


class TestCambiosYLog(unittest.TestCase):
    def _df_base(self):
        return pd.DataFrame([
            {
                "Fila_Sheets": 2,
                "Id_Deuda": "D1",
                "Referencia": "REF1",
                "Casa_Cobro": "ALIADO A",
                "Fecha_Masiva": pd.Timestamp("2026-11-06"),
                "Es_Portafolio": True,
                "PaB_Propuesta": 500000.0,
                "PaB_Portafolio": None,
                "Metadata": {"Id_Cruce": "C1"},
            },
            {
                "Fila_Sheets": 3,
                "Id_Deuda": "D2",
                "Referencia": "REF1",
                "Casa_Cobro": "ALIADO A",
                "Fecha_Masiva": pd.Timestamp("2026-11-06"),
                "Es_Portafolio": True,
                "PaB_Propuesta": 500000.0,
                "PaB_Portafolio": None,
                "Metadata": {"Id_Cruce": "C2"},
            },
        ])

    def test_construye_cambios_solo_de_filas_modificadas(self):
        original = self._df_base()
        resultado = original.copy()
        resultado.loc[0, "PaB_Propuesta"] = 300000.0
        resultado.loc[1, "PaB_Propuesta"] = 200000.0
        resultado["PaB_Portafolio"] = 500000.0
        resultado["Metadata"] = [
            {"Id_Cruce": "C1", "Id_Portafolio": "C1-C2", "PaB_Portafolio": 500000.0},
            {"Id_Cruce": "C2", "Id_Portafolio": "C1-C2", "PaB_Portafolio": 500000.0},
        ]

        cambios = construir_cambios_masivas(df_original=original, df_resultado=resultado)

        self.assertEqual(len(cambios), 2)
        self.assertTrue(cambios["PaB_Cambio"].all())
        self.assertTrue(cambios["Metadata_Cambio"].all())
        self.assertTrue(cambios["Portafolio_Cambio"].all())
        self.assertEqual(cambios["Diferencia_PaB"].tolist(), [-200000.0, -300000.0])

    def test_construye_log_por_base_incluso_sin_cambios(self):
        original = pd.concat([
            self._df_base(),
            pd.DataFrame([{
                "Fila_Sheets": 4,
                "Id_Deuda": "D3",
                "Referencia": "REF2",
                "Casa_Cobro": "ALIADO B",
                "Fecha_Masiva": pd.Timestamp("2026-11-07"),
                "Es_Portafolio": False,
                "PaB_Propuesta": 100000.0,
                "PaB_Portafolio": None,
                "Metadata": {"Id_Cruce": "C3"},
            }]),
        ], ignore_index=True)
        cambios = pd.DataFrame([{
            "Fila_Sheets": 2,
            "Casa_Cobro": "ALIADO A",
            "Fecha_Masiva": pd.Timestamp("2026-11-06"),
        }])

        log = construir_log_cambios_masivas(
            df_original=original,
            df_cambios=cambios,
            usuario="usuario@gobravo.com.co",
            fecha_cambio=pd.Timestamp("2026-11-11 10:00:00"),
        )

        self.assertEqual(len(log), 2)
        fila_a = log[log["Nombre_Aliado_Cambio"] == "ALIADO A"].iloc[0]
        fila_b = log[log["Nombre_Aliado_Cambio"] == "ALIADO B"].iloc[0]
        self.assertEqual(fila_a["Num_Registros"], 2)
        self.assertEqual(fila_a["Num_Cambiados"], 1)
        self.assertEqual(fila_b["Num_Registros"], 1)
        self.assertEqual(fila_b["Num_Cambiados"], 0)

    def test_upload_control_usa_batch_update_por_fila(self):
        headers = [
            'Metadata', 'Fecha', 'Hora', 'ID', 'Propuesta Pago', 'Portafolio',
            'Monto Portafolio',
        ]
        fake_ws = MagicMock()
        fake_ws.row_values.return_value = headers
        fake_service = MagicMock()
        fake_service.get_worksheet.return_value = fake_ws
        df_cambios = pd.DataFrame([{
            'Fila_Sheets': 5,
            'Metadata_Despues': {'Id_Cruce': 'C1'},
            'PaB_Propuesta_Despues': 300000.0,
            'PaB_Portafolio_Despues': 500000.0,
            'Portafolio_Cambio': True,
            'Es_Portafolio_Despues': True,
        }])
        log_df = pd.DataFrame([{
            'Fecha_Cambio': pd.Timestamp('2026-11-11 10:00:00'),
            'Usuario': 'usuario@gobravo.com.co',
            'Nombre_Aliado_Cambio': 'ALIADO',
            'Fecha_Aliado_Cambio': pd.Timestamp('2026-11-06'),
            'Num_Registros': 1,
            'Num_Cambiados': 1,
        }])

        with (
            patch.object(data_uploader.st, 'session_state', {
                'google_sheets_service': fake_service,
            }),
            patch.object(data_uploader, 'add_cambios_locales_to_session_state'),
            patch.object(data_uploader, 'upload_cambios_masivas_log', return_value=True),
        ):
            exito = data_uploader.upload_masivas_control(
                df_cambios=df_cambios,
                log_df=log_df,
            )

        self.assertTrue(exito)
        fake_ws.batch_update.assert_called()
        rangos = []
        for llamada in fake_ws.batch_update.call_args_list:
            rangos.extend([item['range'] for item in llamada.args[0]])
        self.assertIn('A5:A5', rangos)
        self.assertIn('E5:E5', rangos)
        self.assertIn('F5:F5', rangos)
        self.assertIn('G5:G5', rangos)

    def test_aplica_cambios_locales_por_fila_de_sheets(self):
        df = pd.DataFrame([
            {
                "Fila_Sheets": 2,
                "Id_Deuda": "D1",
                "Metadata": pd.NA,
                "PaB_Propuesta": 100.0,
                "PaB_Portafolio": float("nan"),
                "Es_Portafolio": False,
            },
            {
                "Fila_Sheets": 3,
                "Id_Deuda": "D2",
                "Metadata": pd.NA,
                "PaB_Propuesta": 200.0,
                "PaB_Portafolio": float("nan"),
                "Es_Portafolio": False,
            },
        ])
        cambios = [
            pd.Series({
                "Fila_Sheets": 2,
                "Metadata": {"Id_Cruce": "C1"},
                "PaB_Propuesta": 150.0,
                "PaB_Portafolio": 500000.0,
                "Es_Portafolio": True,
            })
        ]

        with patch.object(data_loader.st, "session_state", {
            "local_masivas_changes": cambios,
        }):
            resultado = data_loader._aplicar_cambios_locales_masivas(df)

        self.assertEqual(resultado.loc[0, "Metadata"], {"Id_Cruce": "C1"})
        self.assertEqual(resultado.loc[0, "PaB_Propuesta"], 150.0)
        self.assertEqual(resultado.loc[0, "PaB_Portafolio"], 500000.0)
        self.assertTrue(resultado.loc[0, "Es_Portafolio"])
        self.assertEqual(resultado.loc[1, "PaB_Propuesta"], 200.0)
        self.assertTrue(pd.isna(resultado.loc[1, "Metadata"]))

    def test_resumen_bases_sin_metadata(self):
        df = self._df_base()
        df["Metadata"] = [
            pd.NA,
            {
                "Id_Cruce": "C2",
                "Tipo_Contraoferta": "Descuento Máximo",
                "Fecha_Limite_Uso": pd.Timestamp("2026-11-30"),
            },
        ]

        resumen = resumen_bases_sin_metadata(df)

        self.assertEqual(len(resumen), 1)
        self.assertEqual(resumen.loc[0, "Num_Registros"], 2)
        self.assertEqual(resumen.loc[0, "Num_Sin_Metadata"], 1)


if __name__ == '__main__':
    unittest.main()
