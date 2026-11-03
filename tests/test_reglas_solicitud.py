"""Tests de reglas de negocio y cálculos de estado de las solicitudes.

Cubren máscaras de filtrado, aprobaciones, comités, liquidaciones, fechas
límite de respuesta y métricas agregadas. No requieren conexión a Google
Sheets: las fuentes externas se mockean y los DataFrames se construyen en
memoria.
"""

import unittest
from unittest.mock import patch

import pandas as pd

from modules.classes import Aliado, get_banned_manager
from modules.gest_sols import (
    es_acuerdo_reasignable,
    es_solicitud_aprobacion_necesaria,
    es_solicitud_sin_responder,
    obtener_estado_liquidacion,
    obtener_fecha_limite_respuesta_solicitud,
    obtener_mascara_aprobacion_necesaria,
    obtener_mascara_exitosas,
    obtener_mascara_reasignable,
    obtener_mascara_sin_responder,
    obtener_metricas_cumplimiento_tiempos_respuesta,
    obtener_promedio_respuestas_dia,
    obtener_promedio_tiempos_respuesta,
    obtener_resumen_liquidaciones,
    obtener_resumen_respuestas_automaticas,
    obtener_resumen_respuestas_vencidas,
    obtener_tipo_aprobacion_necesaria,
    obtener_tops_negociadores,
    obtener_valores_bajo_comite,
)


def _aliado(nombre: str, horas: float = 48) -> Aliado:
    return Aliado(
        nombre=nombre,
        bancos=[],
        ejecutivo="",
        pago_co_obligatorio=False,
        brinda_descuento_max=False,
        permiso_cuotas=True,
        tiempo_horas_respuesta=horas,
        toca_validar_bancos=False,
    )


class TestMascarasDeSolicitud(unittest.TestCase):
    def setUp(self):
        get_banned_manager().reset()

    @staticmethod
    def _df():
        hoy = pd.Timestamp.now("America/Bogota").tz_localize(None).normalize()
        return pd.DataFrame([
            {
                "ID_Solicitud": "S1",
                "Estado_Solicitud": "Sin Tocar",
                "Metadata_Solicitud": {},
                "Es_Historico": False,
                "Fecha_Limite_Pago": hoy - pd.Timedelta(days=5),
                "Tipo_Solicitud": "Acuerdo de Pago",
                "Estado_Liquidacion": "Sin Liquidar",
            },
            {
                "ID_Solicitud": "S2",
                "Estado_Solicitud": "Solicitado",
                "Metadata_Solicitud": {},
                "Es_Historico": False,
                "Fecha_Limite_Pago": hoy - pd.Timedelta(days=5),
                "Tipo_Solicitud": "Acuerdo de Pago",
                "Estado_Liquidacion": "Sin Liquidar",
            },
            {
                "ID_Solicitud": "S3",
                "Estado_Solicitud": "Bajo Comité",
                "Metadata_Solicitud": {"Estado_Comite": 3},
                "Es_Historico": False,
                "Fecha_Limite_Pago": hoy - pd.Timedelta(days=5),
                "Tipo_Solicitud": "Acuerdo de Pago",
                "Estado_Liquidacion": "Sin Liquidar",
            },
            {
                "ID_Solicitud": "S4",
                "Estado_Solicitud": "Bajo Comité",
                "Metadata_Solicitud": {"Estado_Comite": 1},
                "Es_Historico": False,
                "Fecha_Limite_Pago": hoy - pd.Timedelta(days=5),
                "Tipo_Solicitud": "Acuerdo de Pago",
                "Estado_Liquidacion": "Sin Liquidar",
            },
            {
                "ID_Solicitud": "S5",
                "Estado_Solicitud": "Titular Ilocalizable",
                "Metadata_Solicitud": {"Estado_Titular_Ilocalizable": 3},
                "Es_Historico": False,
                "Fecha_Limite_Pago": hoy - pd.Timedelta(days=5),
                "Tipo_Solicitud": "Acuerdo de Pago",
                "Estado_Liquidacion": "Sin Liquidar",
            },
            {
                "ID_Solicitud": "S6",
                "Estado_Solicitud": "Exitosa",
                "Metadata_Solicitud": {},
                "Es_Historico": False,
                "Fecha_Limite_Pago": hoy - pd.Timedelta(days=5),
                "Tipo_Solicitud": "Acuerdo de Pago",
                "Estado_Liquidacion": "Sin Liquidar",
            },
            {
                "ID_Solicitud": "S7",
                "Estado_Solicitud": "Sin Tocar",
                "Metadata_Solicitud": {},
                "Es_Historico": True,
                "Fecha_Limite_Pago": hoy - pd.Timedelta(days=5),
                "Tipo_Solicitud": "Acuerdo de Pago",
                "Estado_Liquidacion": "Sin Liquidar",
            },
            {
                "ID_Solicitud": "S8",
                "Estado_Solicitud": "Sin Tocar",
                "Metadata_Solicitud": {},
                "Es_Historico": False,
                "Fecha_Limite_Pago": hoy - pd.Timedelta(days=5),
                "Tipo_Solicitud": "Acuerdo de Pago",
                "Estado_Liquidacion": "Sin Liquidar",
            },
        ])

    def test_mascara_sin_responder(self):
        df = self._df()
        get_banned_manager().ban("S8")
        self.assertEqual(
            obtener_mascara_sin_responder(df).tolist(),
            [True, True, True, False, True, False, False, False],
        )

    def test_es_solicitud_sin_responder(self):
        df = self._df()
        self.assertTrue(es_solicitud_sin_responder(df.iloc[0]))
        self.assertFalse(es_solicitud_sin_responder(df.iloc[3]))
        self.assertFalse(es_solicitud_sin_responder(df.iloc[5]))
        self.assertFalse(es_solicitud_sin_responder(df.iloc[6]))

        get_banned_manager().ban("S1")
        self.assertFalse(es_solicitud_sin_responder(df.iloc[0]))

    def test_mascara_exitosas(self):
        df = self._df()
        self.assertEqual(
            obtener_mascara_exitosas(df).tolist(),
            [False, False, False, False, False, True, False, False],
        )

    def test_mascara_aprobacion_necesaria(self):
        df = self._df()
        self.assertEqual(
            obtener_mascara_aprobacion_necesaria(df).tolist(),
            [False, False, False, True, False, False, False, False],
        )

    def test_tipo_y_es_aprobacion_necesaria(self):
        df = self._df()
        self.assertTrue(es_solicitud_aprobacion_necesaria(df.iloc[3]))
        self.assertEqual(obtener_tipo_aprobacion_necesaria(df.iloc[3]), "Comité")
        self.assertFalse(es_solicitud_aprobacion_necesaria(df.iloc[2]))
        self.assertIsNone(obtener_tipo_aprobacion_necesaria(df.iloc[2]))

        titular = pd.Series({
            "Estado_Solicitud": "Titular Ilocalizable",
            "Metadata_Solicitud": {"Estado_Titular_Ilocalizable": 1},
        })
        self.assertTrue(es_solicitud_aprobacion_necesaria(titular))
        self.assertEqual(obtener_tipo_aprobacion_necesaria(titular), "Titular Ilocalizable")

    def test_mascara_reasignable(self):
        hoy = pd.Timestamp.now("America/Bogota").tz_localize(None).normalize()
        df = pd.DataFrame([
            {
                "Estado_Solicitud": "Exitosa",
                "Tipo_Solicitud": "Acuerdo de Pago",
                "Fecha_Limite_Pago": hoy - pd.Timedelta(days=1),
                "Es_Historico": False,
                "Estado_Liquidacion": "Sin Liquidar",
            },
            {
                "Estado_Solicitud": "Exitosa",
                "Tipo_Solicitud": "Acuerdo de Pago",
                "Fecha_Limite_Pago": hoy + pd.Timedelta(days=1),
                "Es_Historico": False,
                "Estado_Liquidacion": "Sin Liquidar",
            },
            {
                "Estado_Solicitud": "Exitosa",
                "Tipo_Solicitud": "Acuerdo de Pago",
                "Fecha_Limite_Pago": hoy - pd.Timedelta(days=1),
                "Es_Historico": False,
                "Estado_Liquidacion": "Liquidado Total",
            },
            {
                "Estado_Solicitud": "Exitosa",
                "Tipo_Solicitud": "Validación",
                "Fecha_Limite_Pago": hoy - pd.Timedelta(days=1),
                "Es_Historico": False,
                "Estado_Liquidacion": "Sin Liquidar",
            },
            {
                "Estado_Solicitud": "Exitosa",
                "Tipo_Solicitud": "Acuerdo de Pago",
                "Fecha_Limite_Pago": hoy - pd.Timedelta(days=1),
                "Es_Historico": True,
                "Estado_Liquidacion": "Sin Liquidar",
            },
        ])
        self.assertEqual(
            obtener_mascara_reasignable(df).tolist(),
            [True, False, False, False, False],
        )

    def test_es_acuerdo_reasignable(self):
        hoy = pd.Timestamp.now("America/Bogota").tz_localize(None).normalize()

        def solicitud(**cambios):
            base = {
                "Estado_Solicitud": "Exitosa",
                "Tipo_Solicitud": "Acuerdo de Pago",
                "Es_Historico": False,
                "Estado_Liquidacion": "Sin Liquidar",
                "Fecha_Limite_Pago": hoy - pd.Timedelta(days=1),
            }
            base.update(cambios)
            return pd.Series(base)

        self.assertTrue(es_acuerdo_reasignable(solicitud()))
        self.assertFalse(es_acuerdo_reasignable(solicitud(Fecha_Limite_Pago=hoy + pd.Timedelta(days=1))))
        self.assertIsNone(es_acuerdo_reasignable(solicitud(Estado_Liquidacion="Liquidado Total")))
        self.assertIsNone(es_acuerdo_reasignable(solicitud(Tipo_Solicitud="Validación")))
        self.assertIsNone(es_acuerdo_reasignable(solicitud(Es_Historico=True)))
        self.assertIsNone(es_acuerdo_reasignable(solicitud(Estado_Solicitud="No Exitosa")))


class TestValoresBajoComite(unittest.TestCase):
    @staticmethod
    def _solicitud():
        return pd.Series({
            "Estado_Solicitud": "Bajo Comité",
            "JSON_Respuesta": [
                {"Id_Deuda": "D1", "Monto_Propuesto": 500},
                {"Id_Deuda": "D2", "Monto_Propuesto": 0},
                {"Id_Deuda": "D3", "Monto_Propuesto": "300"},
            ],
            "Datos_Solicitud": [
                {"Id_Deuda": "D1", "Monto_Actual": 1000},
                {"Id_Deuda": "D2", "Monto_Actual": 500},
                {"Id_Deuda": "D3", "Monto_Actual": 600},
                {"Id_Deuda": "D4", "Monto_Actual": 9999},
            ],
            "Metadata_Solicitud": {
                "Pago_Total_Obligatorio": True,
                "Max_Descuento_Otorgado": False,
            },
            "Fecha_Limite_Pago": pd.Timestamp("2026-11-30"),
        })

    def test_calcula_montos_y_descuento_otorgado(self):
        resultado = obtener_valores_bajo_comite(solicitud=self._solicitud())
        self.assertIsNotNone(resultado)
        self.assertEqual([d["Id_Deuda"] for d in resultado["deudas"]], ["D1", "D3"])
        self.assertEqual(resultado["monto_total"], 800)
        self.assertEqual(resultado["monto_actual"], 1600)
        self.assertAlmostEqual(resultado["descuento"], 0.5)
        self.assertTrue(resultado["pago_total_obligatorio"])
        self.assertFalse(resultado["max_descuento_otorgado"])
        self.assertEqual(resultado["fecha_limite_pago"], pd.Timestamp("2026-11-30"))

    def test_no_aplica_si_no_esta_bajo_comite(self):
        self.assertIsNone(
            obtener_valores_bajo_comite(
                solicitud=pd.Series({"Estado_Solicitud": "Exitosa"})
            )
        )

    def test_no_aplica_sin_deudas_con_monto(self):
        solicitud = self._solicitud().copy()
        solicitud["JSON_Respuesta"] = [{"Id_Deuda": "D1", "Monto_Propuesto": 0}]
        self.assertIsNone(obtener_valores_bajo_comite(solicitud=solicitud))


class TestEstadoLiquidacion(unittest.TestCase):
    @staticmethod
    def _solicitud(estado="Exitosa", deudas=None):
        return pd.Series({
            "Estado_Solicitud": estado,
            "JSON_Respuesta": deudas if deudas is not None else [
                {"Id_Deuda": "D1", "Monto_Propuesto": 100},
                {"Id_Deuda": "D2", "Monto_Propuesto": 100},
            ],
        })

    def test_sin_liquidar(self):
        with patch("modules.gest_sols.load_liquidaciones", return_value=set()):
            self.assertEqual(obtener_estado_liquidacion(solicitud=self._solicitud()), "Sin Liquidar")

    def test_liquidado_parcial_y_total(self):
        with patch("modules.gest_sols.load_liquidaciones", return_value={"D1"}):
            self.assertEqual(
                obtener_estado_liquidacion(solicitud=self._solicitud()),
                "Liquidado Parcial",
            )
        with patch("modules.gest_sols.load_liquidaciones", return_value={"D1", "D2"}):
            self.assertEqual(
                obtener_estado_liquidacion(solicitud=self._solicitud()),
                "Liquidado Total",
            )

    def test_no_aplica_para_solicitudes_no_exitosas_o_sin_ids(self):
        with patch("modules.gest_sols.load_liquidaciones", return_value={"D1"}):
            self.assertEqual(
                obtener_estado_liquidacion(solicitud=self._solicitud(estado="No Exitosa")),
                "N/A",
            )
            self.assertEqual(
                obtener_estado_liquidacion(solicitud=self._solicitud(deudas=[])),
                "N/A",
            )
            solicitud = self._solicitud()
            solicitud["JSON_Respuesta"] = "texto-invalido"
            self.assertEqual(obtener_estado_liquidacion(solicitud=solicitud), "N/A")


class TestFechasLimiteRespuesta(unittest.TestCase):
    def test_prioriza_fecha_guardada_en_metadata(self):
        solicitud = pd.Series({
            "Metadata_Solicitud": {"Fecha_Limite_Respuesta": pd.Timestamp("2026-09-09 15:00:00")},
            "Casa_Cobro": "Aliado A",
            "Timestamp": pd.Timestamp("2026-09-07"),
        })
        fecha = obtener_fecha_limite_respuesta_solicitud(
            solicitud=solicitud,
            aliados_dict={"Aliado A": _aliado("Aliado A")},
        )
        self.assertEqual(fecha, pd.Timestamp("2026-09-09"))

    def test_calcula_fecha_con_dias_habiles_del_aliado(self):
        solicitud = pd.Series({
            "Metadata_Solicitud": {},
            "Casa_Cobro": "Aliado A",
            "Timestamp": pd.Timestamp("2026-09-07"),
        })
        fecha = obtener_fecha_limite_respuesta_solicitud(
            solicitud=solicitud,
            aliados_dict={"Aliado A": _aliado("Aliado A", horas=48)},
        )
        self.assertEqual(fecha, pd.Timestamp("2026-09-09"))

    def test_busca_aliado_sin_importar_mayusculas(self):
        solicitud = pd.Series({
            "Metadata_Solicitud": {},
            "Casa_Cobro": "aliado a",
            "Timestamp": pd.Timestamp("2026-09-07"),
        })
        fecha = obtener_fecha_limite_respuesta_solicitud(
            solicitud=solicitud,
            aliados_dict={"Aliado A": _aliado("Aliado A", horas=48)},
        )
        self.assertEqual(fecha, pd.Timestamp("2026-09-09"))

    def test_devuelve_none_sin_aliado_o_sin_timestamp(self):
        solicitud_sin_aliado = pd.Series({
            "Metadata_Solicitud": {},
            "Casa_Cobro": "Otro Aliado",
            "Timestamp": pd.Timestamp("2026-09-07"),
        })
        self.assertIsNone(obtener_fecha_limite_respuesta_solicitud(
            solicitud=solicitud_sin_aliado,
            aliados_dict={"Aliado A": _aliado("Aliado A")},
        ))

        solicitud_sin_timestamp = pd.Series({
            "Metadata_Solicitud": {},
            "Casa_Cobro": "Aliado A",
            "Timestamp": pd.NaT,
        })
        self.assertIsNone(obtener_fecha_limite_respuesta_solicitud(
            solicitud=solicitud_sin_timestamp,
            aliados_dict={"Aliado A": _aliado("Aliado A")},
        ))


class TestMetricasSolicitudes(unittest.TestCase):
    def setUp(self):
        get_banned_manager().reset()

    @staticmethod
    def _df_metricas():
        return pd.DataFrame([
            {
                "ID_Solicitud": "1",
                "Estado_Solicitud": "Exitosa",
                "Es_Historico": False,
                "Metadata_Solicitud": {"Fecha_Limite_Respuesta": pd.Timestamp("2026-09-09")},
                "Casa_Cobro": "Aliado A",
                "Fecha_Respuesta": pd.Timestamp("2026-09-09"),
                "Tipo_Solicitud": "Acuerdo de Pago",
            },
            {
                "ID_Solicitud": "2",
                "Estado_Solicitud": "No Exitosa",
                "Es_Historico": False,
                "Metadata_Solicitud": {"Fecha_Limite_Respuesta": pd.Timestamp("2026-09-09")},
                "Casa_Cobro": "Aliado A",
                "Fecha_Respuesta": pd.Timestamp("2026-09-10"),
                "Tipo_Solicitud": "Acuerdo de Pago",
            },
            {
                "ID_Solicitud": "3",
                "Estado_Solicitud": "Exitosa",
                "Es_Historico": False,
                "Metadata_Solicitud": {"Fecha_Limite_Respuesta": pd.Timestamp("2026-09-09")},
                "Casa_Cobro": "Aliado B",
                "Fecha_Respuesta": pd.Timestamp("2026-09-09"),
                "Tipo_Solicitud": "Validación",
            },
            {
                "ID_Solicitud": "4",
                "Estado_Solicitud": "Sin Tocar",
                "Es_Historico": False,
                "Metadata_Solicitud": {},
                "Casa_Cobro": "Aliado A",
                "Fecha_Respuesta": pd.NaT,
                "Tipo_Solicitud": "Validación",
            },
        ])

    def test_cumplimiento_por_aliado_y_tipo(self):
        aliados = {
            "Aliado A": _aliado("Aliado A", horas=48),
            "Aliado B": _aliado("Aliado B", horas=24),
        }
        resultado = obtener_metricas_cumplimiento_tiempos_respuesta(
            solicitudes_df=self._df_metricas(),
            aliados_dict=aliados,
            top_n=2,
            min_solicitudes=1,
        )
        self.assertEqual(resultado["total_respondidas"], 3)
        self.assertEqual(resultado["total_cumplidas"], 2)
        self.assertEqual(resultado["cumplimiento_general"], 66.67)
        self.assertEqual(
            resultado["cumplimiento_por_tipo"],
            {"Acuerdo de Pago": 50.0, "Validación": 100.0},
        )
        self.assertEqual(
            resultado["totales_por_tipo"],
            {
                "Acuerdo de Pago": {"cumplidas": 1, "total": 2},
                "Validación": {"cumplidas": 1, "total": 1},
            },
        )
        self.assertEqual(resultado["mejores_aliados"][0]["casa_cobro"], "Aliado B")
        self.assertEqual(resultado["peores_aliados"][0]["casa_cobro"], "Aliado A")
        self.assertEqual(resultado["max_solicitudes_aliado"], 2)

    def test_sla_excluye_vencidas_y_canceladas(self):
        df = pd.concat([
            self._df_metricas(),
            pd.DataFrame([
                {
                    "ID_Solicitud": "5",
                    "Estado_Solicitud": "Vencida",
                    "Es_Historico": False,
                    "Metadata_Solicitud": {"Fecha_Limite_Respuesta": pd.Timestamp("2026-09-09")},
                    "Casa_Cobro": "Aliado A",
                    "Fecha_Respuesta": pd.Timestamp("2026-09-09"),
                    "Tipo_Solicitud": "Acuerdo de Pago",
                },
                {
                    "ID_Solicitud": "6",
                    "Estado_Solicitud": "Cancelada",
                    "Es_Historico": False,
                    "Metadata_Solicitud": {"Fecha_Limite_Respuesta": pd.Timestamp("2026-09-09")},
                    "Casa_Cobro": "Aliado A",
                    "Fecha_Respuesta": pd.Timestamp("2026-09-09"),
                    "Tipo_Solicitud": "Acuerdo de Pago",
                },
            ]),
        ], ignore_index=True)
        aliados = {
            "Aliado A": _aliado("Aliado A", horas=48),
            "Aliado B": _aliado("Aliado B", horas=24),
        }
        resultado = obtener_metricas_cumplimiento_tiempos_respuesta(
            solicitudes_df=df,
            aliados_dict=aliados,
            top_n=2,
            min_solicitudes=1,
        )
        self.assertEqual(resultado["total_respondidas"], 3)
        self.assertEqual(resultado["total_cumplidas"], 2)
        self.assertEqual(resultado["cumplimiento_general"], 66.67)

    def test_minimo_de_solicitudes_filtra_el_top(self):
        aliados = {
            "Aliado A": _aliado("Aliado A", horas=48),
            "Aliado B": _aliado("Aliado B", horas=24),
        }
        resultado = obtener_metricas_cumplimiento_tiempos_respuesta(
            solicitudes_df=self._df_metricas(),
            aliados_dict=aliados,
            top_n=5,
            min_solicitudes=2,
        )
        self.assertEqual([a["casa_cobro"] for a in resultado["mejores_aliados"]], ["Aliado A"])

    def test_dataframe_vacio(self):
        resultado = obtener_metricas_cumplimiento_tiempos_respuesta(
            solicitudes_df=pd.DataFrame(),
            aliados_dict={},
        )
        self.assertEqual(resultado["total_respondidas"], 0)
        self.assertIsNone(resultado["cumplimiento_general"])

    def test_promedio_tiempos_respuesta(self):
        df = pd.DataFrame([
            {
                "Timestamp": pd.Timestamp("2026-09-07"),
                "Fecha_Respuesta": pd.Timestamp("2026-09-09"),
                "Tipo_Solicitud": "A",
                "Estado_Solicitud": "Exitosa",
            },
            {
                "Timestamp": pd.Timestamp("2026-09-07"),
                "Fecha_Respuesta": pd.Timestamp("2026-09-08"),
                "Tipo_Solicitud": "A",
                "Estado_Solicitud": "No Exitosa",
            },
            {
                "Timestamp": pd.Timestamp("2026-09-07"),
                "Fecha_Respuesta": pd.NaT,
                "Tipo_Solicitud": "B",
                "Estado_Solicitud": "Sin Tocar",
            },
            {
                "Timestamp": pd.Timestamp("2026-09-07"),
                "Fecha_Respuesta": pd.Timestamp("2026-09-30"),
                "Tipo_Solicitud": "A",
                "Estado_Solicitud": "Vencida",
            },
            {
                "Timestamp": pd.Timestamp("2026-09-07"),
                "Fecha_Respuesta": pd.Timestamp("2026-09-30"),
                "Tipo_Solicitud": "A",
                "Estado_Solicitud": "Cancelada",
            },
        ])
        resultado = obtener_promedio_tiempos_respuesta(df)
        self.assertEqual(resultado["promedio_general"], 1.5)
        self.assertEqual(resultado["promedio_por_tipo"]["A"], 1.5)
        self.assertTrue(pd.isna(resultado["promedio_por_tipo"]["B"]))

    def test_promedio_respuestas_por_dia(self):
        df = pd.DataFrame([
            {"Fecha_Respuesta": pd.Timestamp("2026-09-07 10:00"), "Tipo_Solicitud": "A"},
            {"Fecha_Respuesta": pd.Timestamp("2026-09-07 15:00"), "Tipo_Solicitud": "A"},
            {"Fecha_Respuesta": pd.Timestamp("2026-09-08 10:00"), "Tipo_Solicitud": "B"},
        ])
        resultado = obtener_promedio_respuestas_dia(df)
        self.assertEqual(resultado["promedio_general"], 1.5)
        self.assertEqual(resultado["promedio_por_tipo"], {"A": 2.0, "B": 1.0})

    def test_resumen_respuestas_vencidas(self):
        get_banned_manager().reset()
        df = pd.DataFrame([
            {
                "ID_Solicitud": "1",
                "Estado_Solicitud": "Vencida",
                "Metadata_Solicitud": {},
                "Es_Historico": False,
                "Tipo_Solicitud": "Acuerdo de Pago",
            },
            {
                "ID_Solicitud": "2",
                "Estado_Solicitud": "Exitosa",
                "Metadata_Solicitud": {},
                "Es_Historico": False,
                "Tipo_Solicitud": "Acuerdo de Pago",
            },
            {
                "ID_Solicitud": "3",
                "Estado_Solicitud": "Sin Tocar",
                "Metadata_Solicitud": {},
                "Es_Historico": False,
                "Tipo_Solicitud": "Validación",
            },
        ])
        resultado = obtener_resumen_respuestas_vencidas(df)
        self.assertEqual(resultado["total_general"], 1)
        self.assertEqual(resultado["total_por_tipo"], {"Acuerdo de Pago": 1})
        self.assertEqual(resultado["total_respondidas"], 2)

    def test_resumen_respuestas_automaticas(self):
        get_banned_manager().reset()
        df = pd.DataFrame([
            {
                "ID_Solicitud": "10",
                "Estado_Solicitud": "Exitosa",
                "Metadata_Solicitud": {"Id_Respuesta_Autom": "10"},
                "Es_Historico": False,
                "Tipo_Solicitud": "Acuerdo de Pago",
            },
            {
                "ID_Solicitud": "11",
                "Estado_Solicitud": "Exitosa",
                "Metadata_Solicitud": {"Id_Respuesta_Autom": "10"},
                "Es_Historico": False,
                "Tipo_Solicitud": "Acuerdo de Pago",
            },
            {
                "ID_Solicitud": "12",
                "Estado_Solicitud": "Sin Tocar",
                "Metadata_Solicitud": {},
                "Es_Historico": False,
                "Tipo_Solicitud": "Validación",
            },
        ])
        resultado = obtener_resumen_respuestas_automaticas(df)
        self.assertEqual(resultado["total_general"], 1)
        self.assertEqual(resultado["total_por_tipo"], {"Acuerdo de Pago": 1})
        self.assertEqual(resultado["total_respondidas"], 2)

    def test_resumen_liquidaciones(self):
        df = pd.DataFrame([
            {
                "Estado_Liquidacion": "Liquidado Total",
                "Tipo_Solicitud": "Acuerdo de Pago",
                "Cedula": "111",
                "JSON_Respuesta": [{"Id_Deuda": "D1"}, {"Id_Deuda": "D2"}],
            },
            {
                "Estado_Liquidacion": "Liquidado Parcial",
                "Tipo_Solicitud": "Acuerdo de Pago",
                "Cedula": "222",
                "JSON_Respuesta": [{"Id_Deuda": "D2"}, {"Id_Deuda": "D3"}],
            },
            {
                "Estado_Liquidacion": "Sin Liquidar",
                "Tipo_Solicitud": "Validación",
                "Cedula": "333",
                "JSON_Respuesta": [{"Id_Deuda": "D4"}],
            },
        ])
        resultado = obtener_resumen_liquidaciones(df)
        self.assertEqual(resultado["total_general"], 2)
        self.assertEqual(resultado["total_deudas_unicas"], 3)
        self.assertEqual(resultado["total_clientes_unicos"], 2)
        self.assertEqual(
            resultado["deudas_clientes_tipo_sol"]["Acuerdo de Pago"],
            {"num_deudas_unicas": 3, "num_clientes_unicos": 2},
        )

    def test_tops_negociadores(self):
        df = pd.DataFrame([
            {"Correo": "a@x.com", "Estado_Solicitud": "Exitosa", "Estado_Liquidacion": "Liquidado Total"},
            {"Correo": "a@x.com", "Estado_Solicitud": "No Exitosa", "Estado_Liquidacion": "Sin Liquidar"},
            {"Correo": "b@x.com", "Estado_Solicitud": "Exitosa", "Estado_Liquidacion": "Sin Liquidar"},
            {"Correo": "b@x.com", "Estado_Solicitud": "Exitosa", "Estado_Liquidacion": "Liquidado Parcial"},
            {"Correo": "c@x.com", "Estado_Solicitud": "Exitosa", "Estado_Liquidacion": "Sin Liquidar"},
        ])
        nombres = pd.Series({"a@x.com": "A", "b@x.com": "B", "c@x.com": "C"})
        with patch("modules.gest_sols.obtener_nombres_negociadores_masivo", return_value=nombres):
            resultado = obtener_tops_negociadores(
                solicitudes_df=df,
                user_email="b@x.com",
                top_n=2,
            )

        self.assertEqual(
            [(fila["correo"], fila["valor"]) for fila in resultado["top_solicitudes"]],
            [("a@x.com", 2), ("b@x.com", 2)],
        )
        self.assertEqual(
            [(fila["correo"], fila["valor"]) for fila in resultado["top_liquidaciones"]],
            [("a@x.com", 1), ("b@x.com", 1)],
        )
        efectividad = {fila["correo"]: fila["valor"] for fila in resultado["top_efectividad"]}
        self.assertEqual(efectividad, {"a@x.com": 100.0, "b@x.com": 50.0})
        self.assertEqual(resultado["usuario"]["solicitudes"]["posicion"], 2)
        self.assertEqual(int(resultado["usuario"]["efectividad"]["liquidadas"]), 1)
        self.assertEqual(int(resultado["usuario"]["efectividad"]["exitosas"]), 2)


if __name__ == "__main__":
    unittest.main()
