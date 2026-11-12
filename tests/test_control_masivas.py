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
    detectar_fechas_portafolio_fuera_alcance,
    distribuir_portafolios_masivas,
    distribuir_portafolios_masivas_con_alertas,
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
        es_portafolio=False,
        pab_origen=600000,
        pab_propuesta=500000,
        pab_portafolio=None,
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
            "PaB_Portafolio": pab_portafolio,
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
        self.assertTrue(distribuido["Es_Portafolio"].all())
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

    def test_distribuye_sin_marca_portafolio(self):
        df = self._df([
            self._fila(fila=2, id_deuda="D1", es_portafolio=False, pab_origen=600000, pab_propuesta=500000),
            self._fila(fila=3, id_deuda="D2", es_portafolio=False, pab_origen=400000, pab_propuesta=500000),
        ])

        distribuido, detalle = distribuir_portafolios_masivas(df)

        self.assertEqual(distribuido["PaB_Propuesta"].tolist(), [300000.0, 200000.0])
        self.assertTrue(distribuido["Es_Portafolio"].all())
        self.assertEqual(len(detalle), 2)
        self.assertTrue(detalle["Es_Portafolio"].all())

    def test_agrupa_y_distribuye_con_marca_mixta(self):
        df = self._df([
            self._fila(fila=2, id_deuda="D1", es_portafolio=True, pab_origen=600000, pab_propuesta=500000),
            self._fila(fila=3, id_deuda="D2", es_portafolio=False, pab_origen=400000, pab_propuesta=500000),
        ])

        distribuido, detalle = distribuir_portafolios_masivas(df)

        self.assertEqual(distribuido["PaB_Propuesta"].tolist(), [300000.0, 200000.0])
        self.assertTrue(distribuido["Es_Portafolio"].all())
        self.assertEqual(len(detalle), 2)

    def test_no_marca_si_no_aplica_ninguna_regla(self):
        df = self._df([
            self._fila(fila=2, id_deuda="D1", es_portafolio=False, pab_origen=600000, pab_propuesta=500000),
            self._fila(fila=3, id_deuda="D2", es_portafolio=False, pab_origen=400000, pab_propuesta=300000),
        ])

        distribuido, detalle = distribuir_portafolios_masivas(df)

        self.assertEqual(distribuido["PaB_Propuesta"].tolist(), [500000.0, 300000.0])
        self.assertFalse(distribuido["Es_Portafolio"].any())
        self.assertTrue(detalle.empty)

    def test_distribuye_entre_fechas_distintas_de_una_base_por_partes(self):
        # La misma base se subió en tres fechas: el grupo no debe partirse por fecha
        df = self._df([
            self._fila(fila=2, id_deuda="D1", fecha="2026-11-04", pab_origen=600000, pab_propuesta=500000),
            self._fila(fila=3, id_deuda="D2", fecha="2026-11-05", pab_origen=300000, pab_propuesta=500000),
            self._fila(fila=4, id_deuda="D3", fecha="2026-11-06", pab_origen=100000, pab_propuesta=500000),
        ])

        distribuido, detalle = distribuir_portafolios_masivas(df)

        self.assertEqual(distribuido["PaB_Propuesta"].tolist(), [300000.0, 150000.0, 50000.0])
        self.assertTrue(distribuido["Es_Portafolio"].all())
        self.assertEqual(len(detalle), 3)
        self.assertTrue(detalle["Regla_Especial"].all())

    def test_regla_jcap_tambien_cruza_fechas_distintas(self):
        df = self._df([
            self._fila(fila=2, id_deuda="D1", casa="JCAP", fecha="2026-11-04", pab_origen=700000, pab_propuesta=100),
            self._fila(fila=3, id_deuda="D2", casa="JCAP", fecha="2026-11-06", pab_origen=300000, pab_propuesta=50),
        ])

        distribuido, detalle = distribuir_portafolios_masivas(df)

        self.assertEqual(distribuido["PaB_Propuesta"].tolist(), [105.0, 45.0])
        self.assertTrue(distribuido["Es_Portafolio"].all())
        self.assertTrue(detalle["Regla_JCAP"].all())

    def test_no_mezcla_referencias_distintas_aunque_la_fecha_sea_la_misma(self):
        df = self._df([
            self._fila(fila=2, id_deuda="D1", referencia="REF1", pab_origen=600000, pab_propuesta=500000),
            self._fila(fila=3, id_deuda="D2", referencia="REF2", pab_origen=400000, pab_propuesta=500000),
        ])

        distribuido, detalle = distribuir_portafolios_masivas(df)

        self.assertEqual(distribuido["PaB_Propuesta"].tolist(), [500000.0, 500000.0])
        self.assertFalse(distribuido["Es_Portafolio"].any())
        self.assertTrue(detalle.empty)

    def test_no_mezcla_casas_distintas_aunque_la_referencia_sea_la_misma(self):
        df = self._df([
            self._fila(fila=2, id_deuda="D1", casa="ALIADO A", pab_origen=600000, pab_propuesta=500000),
            self._fila(fila=3, id_deuda="D2", casa="ALIADO B", pab_origen=400000, pab_propuesta=500000),
        ])

        distribuido, detalle = distribuir_portafolios_masivas(df)

        self.assertEqual(distribuido["PaB_Propuesta"].tolist(), [500000.0, 500000.0])
        self.assertFalse(distribuido["Es_Portafolio"].any())
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

    def test_usa_pab_portafolio_existente_para_redistribuir_lote_nuevo(self):
        # El lote 1 ya fue distribuido (600k y 400k) y guardó PaB_Portafolio = 1M.
        # El lote 2 trae una deuda nueva con el total repetido: se debe ignorar su
        # PaB_Propuesta y redistribuir el total guardado entre las tres deudas.
        df = self._df([
            self._fila(
                fila=2, id_deuda="D1", fecha="2026-11-04",
                pab_origen=600000, pab_propuesta=600000, pab_portafolio=1000000,
            ),
            self._fila(
                fila=3, id_deuda="D2", fecha="2026-11-04",
                pab_origen=400000, pab_propuesta=400000, pab_portafolio=1000000,
            ),
            self._fila(
                fila=4, id_deuda="D3", fecha="2026-11-07",
                pab_origen=1000000, pab_propuesta=1000000,
            ),
        ])

        distribuido, detalle, alertas = distribuir_portafolios_masivas_con_alertas(df)

        self.assertEqual(
            distribuido["PaB_Propuesta"].tolist(),
            [300000.0, 200000.0, 500000.0],
        )
        self.assertTrue(distribuido["Es_Portafolio"].all())
        self.assertTrue(detalle["Regla_Portafolio_Existente"].all())
        self.assertFalse(detalle["Regla_Especial"].any())
        self.assertTrue(alertas.empty)

    def test_pab_portafolio_tiene_prioridad_sobre_regla_especial(self):
        # La regla especial usaría el pago común (600k) y daría 300k/300k.
        # El PaB_Portafolio oficial (1M) debe imponerse y dar 500k/500k.
        df = self._df([
            self._fila(
                fila=2, id_deuda="D1", pab_origen=500000,
                pab_propuesta=600000, pab_portafolio=1000000,
            ),
            self._fila(
                fila=3, id_deuda="D2", pab_origen=500000,
                pab_propuesta=600000, pab_portafolio=1000000,
            ),
        ])

        distribuido, detalle, alertas = distribuir_portafolios_masivas_con_alertas(df)

        self.assertEqual(distribuido["PaB_Propuesta"].tolist(), [500000.0, 500000.0])
        self.assertTrue(detalle["Regla_Portafolio_Existente"].all())
        self.assertFalse(detalle["Regla_Especial"].any())
        self.assertTrue(alertas.empty)

    def test_no_redistribuye_portafolio_individual_no_proporcional(self):
        # Los pagos individuales no guardan proporción con PaB_Origen:
        # se debe conservar el modo 'Monto Individual de Portafolio'.
        metadata = {
            "Id_Cruce": "C1",
            "Id_Portafolio": "C1-C2",
            "PaB_Portafolio": 1000000.0,
        }
        df = self._df([
            self._fila(
                fila=2, id_deuda="D1", pab_origen=600000,
                pab_propuesta=100000, pab_portafolio=1000000,
                metadata=metadata,
            ),
            self._fila(
                fila=3, id_deuda="D2", pab_origen=400000,
                pab_propuesta=300000, pab_portafolio=1000000,
                metadata=metadata,
            ),
        ])

        distribuido, detalle, alertas = distribuir_portafolios_masivas_con_alertas(df)

        self.assertEqual(distribuido["PaB_Propuesta"].tolist(), [100000.0, 300000.0])
        self.assertTrue(detalle.empty)
        self.assertEqual(alertas["Tipo_Alerta"].tolist(), ["Portafolio Individual"])

    def test_redistribuye_si_deuda_nueva_trae_el_total_repetido(self):
        # Aunque los pagos previos no sean proporcionales, una deuda nueva con
        # el total del portafolio repetido confirma que el portafolio se distribuye.
        metadata = {
            "Id_Cruce": "C1",
            "Id_Portafolio": "C1-C2",
            "PaB_Portafolio": 1000000.0,
        }
        df = self._df([
            self._fila(
                fila=2, id_deuda="D1", pab_origen=600000,
                pab_propuesta=100000, pab_portafolio=1000000,
                metadata=metadata,
            ),
            self._fila(
                fila=3, id_deuda="D2", pab_origen=400000,
                pab_propuesta=300000, pab_portafolio=1000000,
                metadata=metadata,
            ),
            self._fila(
                fila=4, id_deuda="D3", fecha="2026-11-07",
                pab_origen=1000000, pab_propuesta=1000000,
            ),
        ])

        distribuido, detalle, alertas = distribuir_portafolios_masivas_con_alertas(df)

        self.assertEqual(
            distribuido["PaB_Propuesta"].tolist(),
            [300000.0, 200000.0, 500000.0],
        )
        self.assertTrue(detalle["Regla_Portafolio_Existente"].all())
        self.assertTrue(alertas.empty)

    def test_pab_portafolio_usa_el_valor_mas_reciente_y_alerta(self):
        df = self._df([
            self._fila(
                fila=2, id_deuda="D1", fecha="2026-11-04",
                pab_origen=600000, pab_propuesta=600000, pab_portafolio=1000000,
            ),
            self._fila(
                fila=3, id_deuda="D2", fecha="2026-11-06",
                pab_origen=400000, pab_propuesta=400000, pab_portafolio=1200000,
            ),
        ])

        distribuido, _, alertas = distribuir_portafolios_masivas_con_alertas(df)

        self.assertEqual(distribuido["PaB_Propuesta"].tolist(), [720000.0, 480000.0])
        self.assertEqual(alertas["Tipo_Alerta"].tolist(), ["Portafolios Múltiples"])
        self.assertIn("1,200,000", alertas.loc[0, "Detalle"])
        self.assertIn("06/11/2026", alertas.loc[0, "Detalle"])

    def test_no_redistribuye_pab_portafolio_si_falta_un_pago(self):
        df = self._df([
            self._fila(
                fila=2, id_deuda="D1", pab_origen=600000,
                pab_propuesta=600000, pab_portafolio=1000000,
            ),
            self._fila(
                fila=3, id_deuda="D2", pab_origen=400000,
                pab_propuesta=None, pab_portafolio=1000000,
            ),
        ])

        distribuido, detalle, alertas = distribuir_portafolios_masivas_con_alertas(df)

        self.assertEqual(distribuido["PaB_Propuesta"].iloc[0], 600000.0)
        self.assertTrue(pd.isna(distribuido["PaB_Propuesta"].iloc[1]))
        self.assertTrue(detalle.empty)
        self.assertEqual(alertas["Tipo_Alerta"].tolist(), ["Pago Faltante"])

    def test_flujo_pab_portafolio_es_idempotente(self):
        df = self._df([
            self._fila(
                fila=2, id_deuda="D1", fecha="2026-11-04",
                pab_origen=600000, pab_propuesta=600000, pab_portafolio=1000000,
            ),
            self._fila(
                fila=3, id_deuda="D2", fecha="2026-11-04",
                pab_origen=400000, pab_propuesta=400000, pab_portafolio=1000000,
            ),
            self._fila(
                fila=4, id_deuda="D3", fecha="2026-11-07",
                pab_origen=1000000, pab_propuesta=1000000,
            ),
        ])

        primera, _, _ = distribuir_portafolios_masivas_con_alertas(df)
        primera = actualizar_metadata_portafolios(primera)
        segunda, _, alertas = distribuir_portafolios_masivas_con_alertas(primera)
        segunda = actualizar_metadata_portafolios(segunda)

        self.assertEqual(
            primera["PaB_Propuesta"].tolist(),
            segunda["PaB_Propuesta"].tolist(),
        )
        self.assertEqual(
            primera["PaB_Portafolio"].tolist(),
            segunda["PaB_Portafolio"].tolist(),
        )
        self.assertTrue(alertas.empty)

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

    def test_completar_metadata_no_modifica_montos_ni_portafolios(self):
        df = self._df([
            {
                "Casa_Cobro": "ALIADO A",
                "Fecha_Masiva": pd.Timestamp("2026-11-06"),
                "PaB_Propuesta": 100000.0,
                "PaB_Portafolio": 500000.0,
                "Es_Portafolio": True,
                "Metadata": pd.NA,
            },
            {
                "Casa_Cobro": "ALIADO A",
                "Fecha_Masiva": pd.Timestamp("2026-11-06"),
                "PaB_Propuesta": 200000.0,
                "PaB_Portafolio": 500000.0,
                "Es_Portafolio": True,
                "Metadata": pd.NA,
            },
        ])
        configs = {
            ("ALIADO A", pd.Timestamp("2026-11-06")): {
                "Tipo_Contraoferta": "ContraOferta sin Compromiso",
                "Fecha_Limite_Uso": pd.Timestamp("2026-11-30"),
                "Alias": None,
            }
        }

        resultado = completar_metadata_masivas(df, configs)

        self.assertTrue(resultado["Metadata"].apply(metadata_masiva_completa).all())
        self.assertEqual(resultado["PaB_Propuesta"].tolist(), [100000.0, 200000.0])
        self.assertEqual(resultado["PaB_Portafolio"].tolist(), [500000.0, 500000.0])
        self.assertEqual(resultado["Es_Portafolio"].tolist(), [True, True])

    def test_completar_metadata_preserva_pab_portafolio_de_la_columna(self):
        df = self._df([{
            "Casa_Cobro": "ALIADO A",
            "Fecha_Masiva": pd.Timestamp("2026-11-06"),
            "PaB_Propuesta": 100000.0,
            "PaB_Portafolio": 500000.0,
            "Es_Portafolio": True,
            "Metadata": pd.NA,
        }])
        configs = {
            ("ALIADO A", pd.Timestamp("2026-11-06")): {
                "Tipo_Contraoferta": "ContraOferta sin Compromiso",
                "Fecha_Limite_Uso": pd.Timestamp("2026-11-30"),
                "Alias": None,
            }
        }

        resultado = completar_metadata_masivas(df, configs)

        self.assertEqual(resultado.loc[0, "Metadata"]["PaB_Portafolio"], 500000.0)
        self.assertEqual(resultado.loc[0, "Metadata"]["Id_Portafolio"], "")
        self.assertEqual(resultado.loc[0, "PaB_Portafolio"], 500000.0)

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

    def test_completa_varias_fechas_con_la_misma_configuracion_de_aliado(self):
        # La vista replica la configuración de un solo formulario a cada fecha pendiente
        df = self._df([
            {
                "Casa_Cobro": "ALIADO A",
                "Fecha_Masiva": pd.Timestamp("2026-11-04"),
                "Metadata": pd.NA,
            },
            {
                "Casa_Cobro": "ALIADO A",
                "Fecha_Masiva": pd.Timestamp("2026-11-06"),
                "Metadata": pd.NA,
            },
        ])
        config_aliado = {
            "Tipo_Contraoferta": "ContraOferta sin Compromiso",
            "Fecha_Limite_Uso": pd.Timestamp("2026-11-30"),
            "Alias": "Alias 1",
        }
        configs = {
            ("ALIADO A", pd.Timestamp("2026-11-04")): config_aliado,
            ("ALIADO A", pd.Timestamp("2026-11-06")): config_aliado,
        }

        resultado = completar_metadata_masivas(df, configs)

        self.assertTrue(resultado["Metadata"].apply(metadata_masiva_completa).all())
        self.assertEqual(
            resultado["Metadata"].apply(lambda m: m["Alias"]).tolist(),
            ["Alias 1", "Alias 1"],
        )

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

    def test_flujo_automatico_marca_y_actualiza_metadata(self):
        df = pd.DataFrame([
            self._fila(fila=2, id_deuda="D1", id_cruce="C1", es_portafolio=False, pab=500000),
            self._fila(fila=3, id_deuda="D2", id_cruce="C2", es_portafolio=False, pab=500000),
        ])

        distribuido, _ = distribuir_portafolios_masivas(df)
        resultado = actualizar_metadata_portafolios(distribuido)

        self.assertTrue(resultado["Es_Portafolio"].all())
        self.assertEqual(resultado.loc[0, "Metadata"]["Id_Portafolio"], "C1-C2")
        self.assertEqual(resultado.loc[1, "Metadata"]["Id_Portafolio"], "C1-C2")
        self.assertEqual(resultado.loc[0, "Metadata"]["PaB_Portafolio"], 500000.0)
        self.assertEqual(resultado.loc[1, "Metadata"]["PaB_Portafolio"], 500000.0)

    def test_no_marca_portafolio_si_no_aplica_ninguna_regla(self):
        df = pd.DataFrame([
            self._fila(fila=2, id_deuda="D1", id_cruce="C1", es_portafolio=False, pab=500000),
            self._fila(fila=3, id_deuda="D2", id_cruce="C2", es_portafolio=False, pab=300000),
        ])

        distribuido, _ = distribuir_portafolios_masivas(df)
        resultado = actualizar_metadata_portafolios(distribuido)

        self.assertFalse(resultado["Es_Portafolio"].any())
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

    def test_preserva_metadata_de_portafolio_si_falta_un_pago(self):
        metadata_portafolio = {
            "Id_Cruce": "C1",
            "Tipo_Contraoferta": "Descuento Máximo",
            "Fecha_Limite_Uso": pd.Timestamp("2026-11-30"),
            "Alias": None,
            "Id_Portafolio": "C1-C2",
            "PaB_Portafolio": 1000000.0,
        }
        df = pd.DataFrame([
            {
                **self._fila(
                    fila=2, id_deuda="D1", id_cruce="C1",
                    es_portafolio=True, pab=600000, metadata=metadata_portafolio,
                ),
                "PaB_Portafolio": 1000000.0,
            },
            {
                **self._fila(
                    fila=3, id_deuda="D2", id_cruce="C2",
                    es_portafolio=False, pab=None,
                    metadata={"Id_Cruce": "C2"},
                ),
                "PaB_Portafolio": float("nan"),
            },
        ])

        resultado = actualizar_metadata_portafolios(df)

        self.assertEqual(resultado.loc[0, "Metadata"]["Id_Portafolio"], "C1-C2")
        self.assertEqual(resultado.loc[0, "Metadata"]["PaB_Portafolio"], 1000000.0)
        self.assertEqual(resultado.loc[0, "PaB_Portafolio"], 1000000.0)
        self.assertTrue(pd.isna(resultado.loc[1, "PaB_Portafolio"]))


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

    def test_cambios_solo_metadata_no_marcan_pagos_ni_portafolios(self):
        original = self._df_base()
        resultado = original.copy()
        resultado["Metadata"] = [
            {
                "Id_Cruce": "C1",
                "Tipo_Contraoferta": "Descuento Máximo",
                "Fecha_Limite_Uso": pd.Timestamp("2026-11-30"),
            },
            {
                "Id_Cruce": "C2",
                "Tipo_Contraoferta": "Descuento Máximo",
                "Fecha_Limite_Uso": pd.Timestamp("2026-11-30"),
            },
        ]

        cambios = construir_cambios_masivas(
            df_original=original,
            df_resultado=resultado,
        )

        self.assertEqual(len(cambios), 2)
        self.assertTrue(cambios["Metadata_Cambio"].all())
        self.assertFalse(cambios["PaB_Cambio"].any())
        self.assertFalse(cambios["Portafolio_Cambio"].any())

    def test_cambios_incluyen_marca_automatica_de_portafolio(self):
        original = self._df_base()
        original["Es_Portafolio"] = False
        original["PaB_Origen"] = [600000, 400000]
        resultado, _ = distribuir_portafolios_masivas(original)
        resultado = actualizar_metadata_portafolios(resultado)

        cambios = construir_cambios_masivas(df_original=original, df_resultado=resultado)

        self.assertEqual(len(cambios), 2)
        self.assertTrue(cambios["Es_Portafolio_Despues"].all())
        self.assertTrue(cambios["Portafolio_Cambio"].all())
        self.assertTrue(cambios["Metadata_Cambio"].all())
        self.assertTrue(cambios["PaB_Cambio"].all())
        self.assertEqual(cambios["PaB_Propuesta_Despues"].tolist(), [300000.0, 200000.0])

    def test_flujo_completo_entre_fechas_genera_cambios_y_log_por_fecha(self):
        original = pd.DataFrame([
            {
                "Fila_Sheets": 2,
                "Id_Deuda": "D1",
                "Referencia": "REF1",
                "Casa_Cobro": "ALIADO A",
                "Fecha_Masiva": pd.Timestamp("2026-11-04"),
                "Es_Portafolio": False,
                "PaB_Origen": 600000,
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
                "Es_Portafolio": False,
                "PaB_Origen": 400000,
                "PaB_Propuesta": 500000.0,
                "PaB_Portafolio": None,
                "Metadata": {"Id_Cruce": "C2"},
            },
        ])

        resultado, _ = distribuir_portafolios_masivas(original)
        resultado = actualizar_metadata_portafolios(resultado)
        cambios = construir_cambios_masivas(
            df_original=original,
            df_resultado=resultado,
        )
        log = construir_log_cambios_masivas(
            df_original=original,
            df_cambios=cambios,
            usuario="usuario@gobravo.com.co",
            fecha_cambio=pd.Timestamp("2026-11-11 10:00:00"),
        )

        self.assertEqual(len(cambios), 2)
        self.assertTrue(resultado["Es_Portafolio"].all())
        self.assertEqual(resultado.loc[0, "Metadata"]["Id_Portafolio"], "C1-C2")
        self.assertEqual(resultado.loc[0, "Metadata"]["PaB_Portafolio"], 500000.0)
        self.assertEqual(len(log), 2)
        self.assertEqual(log["Num_Registros"].tolist(), [1, 1])
        self.assertEqual(log["Num_Cambiados"].tolist(), [1, 1])
        self.assertEqual(
            log["Fecha_Aliado_Cambio"].tolist(),
            [pd.Timestamp("2026-11-04"), pd.Timestamp("2026-11-06")],
        )

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


class TestFechasPortafolioFueraAlcance(unittest.TestCase):
    def _df(self):
        return pd.DataFrame([
            {
                "Casa_Cobro": "ALIADO A",
                "Referencia": "REF1",
                "Fecha_Masiva": pd.Timestamp("2026-11-04"),
                "PaB_Portafolio": 1000000,
                "Metadata": {"Id_Cruce": "C1"},
            },
            {
                "Casa_Cobro": "ALIADO A",
                "Referencia": "REF1",
                "Fecha_Masiva": pd.Timestamp("2026-11-06"),
                "PaB_Portafolio": 1000000,
                "Metadata": {"Id_Cruce": "C2"},
            },
            {
                "Casa_Cobro": "ALIADO A",
                "Referencia": "REF2",
                "Fecha_Masiva": pd.Timestamp("2026-11-04"),
                "PaB_Portafolio": 500000,
                "Metadata": {"Id_Cruce": "C3"},
            },
            {
                "Casa_Cobro": "ALIADO B",
                "Referencia": "REF1",
                "Fecha_Masiva": pd.Timestamp("2026-11-04"),
                "PaB_Portafolio": 1000000,
                "Metadata": {"Id_Cruce": "C4"},
            },
            {
                "Casa_Cobro": "ALIADO A",
                "Referencia": "REF1",
                "Fecha_Masiva": pd.Timestamp("2026-11-05"),
                "PaB_Portafolio": None,
                "Metadata": {"Id_Cruce": "C5", "PaB_Portafolio": 900000},
            },
            {
                "Casa_Cobro": "ALIADO A",
                "Referencia": "REF1",
                "Fecha_Masiva": pd.Timestamp("2026-11-07"),
                "PaB_Portafolio": None,
                "Metadata": {"Id_Cruce": "C6"},
            },
        ])

    def test_detecta_fechas_con_portafolio_fuera_del_alcance(self):
        resultado = detectar_fechas_portafolio_fuera_alcance(
            df=self._df(),
            casa_cobro="aliado a",
            fechas_alcance=[pd.Timestamp("2026-11-06")],
            referencias=["REF1"],
        )

        self.assertEqual(
            resultado["Fecha_Masiva"].tolist(),
            [pd.Timestamp("2026-11-04"), pd.Timestamp("2026-11-05")],
        )
        self.assertEqual(resultado["Num_Registros"].tolist(), [1, 1])

    def test_sin_filtro_de_referencias_incluye_todas_las_de_la_casa(self):
        resultado = detectar_fechas_portafolio_fuera_alcance(
            df=self._df(),
            casa_cobro="ALIADO A",
            fechas_alcance=[pd.Timestamp("2026-11-06")],
        )

        self.assertEqual(
            resultado["Fecha_Masiva"].tolist(),
            [pd.Timestamp("2026-11-04"), pd.Timestamp("2026-11-05")],
        )
        self.assertEqual(resultado["Num_Registros"].tolist(), [2, 1])

    def test_devuelve_vacio_si_todas_las_fechas_estan_en_el_alcance(self):
        resultado = detectar_fechas_portafolio_fuera_alcance(
            df=self._df(),
            casa_cobro="ALIADO A",
            fechas_alcance=[
                pd.Timestamp("2026-11-04"),
                pd.Timestamp("2026-11-05"),
                pd.Timestamp("2026-11-06"),
                pd.Timestamp("2026-11-07"),
            ],
        )

        self.assertTrue(resultado.empty)


if __name__ == '__main__':
    unittest.main()
