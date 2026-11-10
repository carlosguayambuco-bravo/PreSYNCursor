# Estándar usando Pep8
# Librerías de Python
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
# Librerías de Terceros
import pandas as pd
# Librerías Locales
from data.data_loader import (
    obtener_prioridad_archivo,
    obtener_prioridad_hoja,
    _parse_mes_anio_desde_nombre_archivo,
    load_mes_operativo_liquidaciones,
)
from data.data_models import ActualizacionesSchema, AsignacionSchema
from modules.oportunidades import (
    _resolver_pab_actualizado_alianzas,
    calcular_apartado_neto_cliente,
    calcular_contraoferta_credito,
    calcular_contraoferta_tradicional,
    calcular_deposito_extra_credito,
    calcular_deposito_extra_tradicional,
    calcular_descuento_actual,
    calcular_descuento_esperado_ponderado,
    calcular_oportunidades_referencia,
    evaluar_contraoferta,
    evaluar_deposito_extra,
    evaluar_ia_liquidadora,
    evaluar_liq_insta,
    evaluar_viabilidad_cliente,
    obtener_acuerdos_robo,
    obtener_pab_actualizado_deuda,
    obtener_referencias_habilitadas,
    obtener_ultima_actualizacion_deuda,
)
from ui.calculadora_components import (
    _calcular_descuento_desde_pab,
    _calcular_pab_desde_descuento,
    _obtener_pab_inicial_deuda,
    _sincronizar_desde_slider_descuento,
    _sincronizar_desde_slider_pab,
    _sincronizar_desde_texto_pab,
)


class TestPrioridadAsignacion(unittest.TestCase):
    def test_parse_nombre_archivo_valido(self):
        self.assertEqual(_parse_mes_anio_desde_nombre_archivo("Asignacion-Oct25.xlsx"), (10, 2025))
        self.assertEqual(_parse_mes_anio_desde_nombre_archivo("Cartera - Feb26.xlsx"), (2, 2026))

    def test_parse_nombre_archivo_invalido(self):
        self.assertIsNone(_parse_mes_anio_desde_nombre_archivo("Asignacion.xlsx"))
        self.assertIsNone(_parse_mes_anio_desde_nombre_archivo("Asignacion-Oct.xlsx"))
        self.assertIsNone(_parse_mes_anio_desde_nombre_archivo("Asignacion-Oct25.csv"))
        self.assertIsNone(_parse_mes_anio_desde_nombre_archivo("Asignacion-Octubre25.xlsx"))

    def test_prioridad_archivo_ordena_por_mes_y_anio(self):
        self.assertGreater(
            obtener_prioridad_archivo("Asignacion-Feb26.xlsx"),
            obtener_prioridad_archivo("Asignacion-Oct25.xlsx"),
        )
        self.assertEqual(obtener_prioridad_archivo("Asignacion.xlsx"), 0)

    def test_prioridad_hoja(self):
        self.assertEqual(obtener_prioridad_hoja("Octubre 2025"), (2025 * 13 + 10, 2025, 10))
        self.assertEqual(obtener_prioridad_hoja("Oct 25"), (2025 * 13 + 10, 2025, 10))
        self.assertEqual(obtener_prioridad_hoja("Octubre-2025"), (0, 0, 0))
        self.assertEqual(obtener_prioridad_hoja("Octubre"), (0, 0, 0))

    def test_asignacion_schema_incluye_banco(self):
        columnas = list(AsignacionSchema.to_schema().columns)
        self.assertIn("Banco", columnas)
        self.assertNotIn("Fecha_Cartera", columnas)

    def test_actualizaciones_schema_incluye_pab_actualizado(self):
        columnas = list(ActualizacionesSchema.to_schema().columns)
        self.assertIn("PaB_Actualizado", columnas)


class TestReferenciasHabilitadas(unittest.TestCase):
    def _asignacion(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "Referencia": ["REF-A", "REF-A", "REF-B", "REF-C"],
                "Negociador": ["Nego A", "Nego A", "Nego B", "Nego C"],
            }
        )

    def _headcount(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "Correo": ["a@x.com", "b@x.com", "c@x.com", "lider@x.com"],
                "Nombre": ["Nego A", "Nego B", "Nego C", "Lider A"],
                "Lider": ["Lider A", "Lider A", "Lider A", "Lider A"],
            }
        )

    def _fake_st(self, *, role: str, email: str, permitir_no_asignado: bool = False):
        fake_st = MagicMock()
        fake_st.session_state = {
            "user_obj": SimpleNamespace(role=role),
            "user_email": email,
        }
        fake_st.secrets.get.return_value = permitir_no_asignado
        return fake_st

    def test_admin_ve_todas_las_referencias(self):
        fake_st = self._fake_st(role="admin", email="admin@x.com")
        with patch("modules.oportunidades.st", fake_st), patch(
            "modules.oportunidades.load_asignacion_cartera", return_value=self._asignacion()
        ):
            referencias = obtener_referencias_habilitadas()

        self.assertEqual(referencias, ["REF-A", "REF-B", "REF-C"])

    def test_nego_solo_ve_sus_referencias(self):
        fake_st = self._fake_st(role="nego", email="a@x.com")
        with patch("modules.oportunidades.st", fake_st), patch(
            "modules.oportunidades.load_asignacion_cartera", return_value=self._asignacion()
        ), patch(
            "modules.oportunidades.load_headcount_negociacion", return_value=self._headcount()
        ):
            referencias = obtener_referencias_habilitadas()

        self.assertEqual(referencias, ["REF-A"])

    def test_lider_ve_referencias_de_su_equipo(self):
        fake_st = self._fake_st(role="leader", email="lider@x.com")
        with patch("modules.oportunidades.st", fake_st), patch(
            "modules.oportunidades.load_asignacion_cartera", return_value=self._asignacion()
        ), patch(
            "modules.oportunidades.load_headcount_negociacion", return_value=self._headcount()
        ):
            referencias = obtener_referencias_habilitadas()

        self.assertEqual(referencias, ["REF-A", "REF-B", "REF-C"])

    def test_secreto_habilita_todas_las_referencias(self):
        fake_st = self._fake_st(role="nego", email="a@x.com", permitir_no_asignado=True)
        with patch("modules.oportunidades.st", fake_st), patch(
            "modules.oportunidades.load_asignacion_cartera", return_value=self._asignacion()
        ):
            referencias = obtener_referencias_habilitadas()

        self.assertEqual(referencias, ["REF-A", "REF-B", "REF-C"])

    def test_asignacion_vacia_devuelve_lista_vacia(self):
        fake_st = self._fake_st(role="admin", email="admin@x.com")
        with patch("modules.oportunidades.st", fake_st), patch(
            "modules.oportunidades.load_asignacion_cartera", return_value=AsignacionSchema.empty()
        ):
            referencias = obtener_referencias_habilitadas()

        self.assertEqual(referencias, [])


class TestUltimaActualizacionDeuda(unittest.TestCase):
    def _actualizaciones(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "Id_Deuda": ["D1", "D1", "D2"],
                "Fecha_Act": [
                    pd.Timestamp("2026-01-10 10:00:00"),
                    pd.Timestamp("2026-02-10 10:00:00"),
                    pd.Timestamp("2026-02-11 10:00:00"),
                ],
                "Etiqueta_Act": ["CAMBIO DE PAB", "ACUERDO", "DEPOSITO"],
                "Nombre": ["Ana", "Luis", "Marta"],
            }
        )

    def test_sin_fecha_minima_toma_la_mas_reciente(self):
        with patch(
            "modules.oportunidades.load_actualizacines_negos", return_value=self._actualizaciones()
        ):
            resultado = obtener_ultima_actualizacion_deuda("D1")

        self.assertIn("ACUERDO", resultado)
        self.assertIn("Luis", resultado)
        self.assertNotIn("CAMBIO DE PAB", resultado)

    def test_con_fecha_minima_filtra_actualizaciones_antiguas(self):
        with patch(
            "modules.oportunidades.load_actualizacines_negos", return_value=self._actualizaciones()
        ):
            resultado = obtener_ultima_actualizacion_deuda(
                "D1", fecha_min=pd.Timestamp("2026-02-01")
            )

        self.assertIn("ACUERDO", resultado)
        self.assertNotIn("CAMBIO DE PAB", resultado)

    def test_deuda_sin_actualizaciones_devuelve_na(self):
        with patch(
            "modules.oportunidades.load_actualizacines_negos", return_value=self._actualizaciones()
        ):
            resultado = obtener_ultima_actualizacion_deuda("D3")

        self.assertEqual(resultado, "N/A")


class TestMesOperativoLiquidaciones(unittest.TestCase):
    def _liquidaciones(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "Id_Deuda": ["D1", "D2"],
                "Fecha_Liq": [
                    pd.Timestamp("2025-10-15 10:00:00"),
                    pd.Timestamp("2025-10-03 09:00:00"),
                ],
            }
        )

    def test_toma_el_primer_dia_del_mes_de_la_fecha_minima(self):
        with patch(
            "data.data_loader.load_liquidaciones_mec", return_value=self._liquidaciones()
        ):
            mes_operativo = load_mes_operativo_liquidaciones.__wrapped__()

        self.assertEqual(mes_operativo, pd.Timestamp("2025-10-01"))

    def test_sin_liquidaciones_cae_al_fallback(self):
        fallback = pd.Timestamp("2026-01-01")
        with patch(
            "data.data_loader.load_liquidaciones_mec", return_value=pd.DataFrame()
        ), patch("data.data_loader.getMesOperativo", return_value=fallback):
            mes_operativo = load_mes_operativo_liquidaciones.__wrapped__()

        self.assertEqual(mes_operativo, fallback)

    def test_fecha_nula_cae_al_fallback(self):
        fallback = pd.Timestamp("2026-01-01")
        liqs = pd.DataFrame({"Id_Deuda": ["D1"], "Fecha_Liq": [pd.NaT]})
        with patch(
            "data.data_loader.load_liquidaciones_mec", return_value=liqs
        ), patch("data.data_loader.getMesOperativo", return_value=fallback):
            mes_operativo = load_mes_operativo_liquidaciones.__wrapped__()

        self.assertEqual(mes_operativo, fallback)


class TestCalculosOportunidades(unittest.TestCase):
    def test_deposito_extra_credito(self):
        # Si el pago actual es menor al cupo, no se requiere depósito
        self.assertEqual(
            calcular_deposito_extra_credito(
                pab_ideal_total=80_000_000,
                pab_actualizado_total=60_000_000,
            ),
            -19_980_000,
        )
        # Si el pago actual supera el cupo, el cliente cubre la diferencia
        self.assertEqual(
            calcular_deposito_extra_credito(
                pab_ideal_total=80_000_000,
                pab_actualizado_total=90_000_000,
            ),
            10_020_000,
        )

    def test_deposito_extra_tradicional(self):
        self.assertAlmostEqual(
            calcular_deposito_extra_tradicional(
                pab_origen_total=100_000_000,
                pab_actualizado_total=60_000_000,
                pricing=0.15,
                ahorro=50_000_000,
                por_cobrar=5_000_000,
            ),
            22_160_000,
        )

    def test_contraoferta_credito(self):
        self.assertAlmostEqual(
            calcular_contraoferta_credito(
                pab_ideal_total=80_000_000,
                pab_origen_total=100_000_000,
            ),
            1 - (80_020_000 / 100_000_000),
        )

    def test_contraoferta_tradicional(self):
        self.assertAlmostEqual(
            calcular_contraoferta_tradicional(
                pab_origen_total=100_000_000,
                pricing=0.15,
                ahorro=50_000_000,
                por_cobrar=5_000_000,
            ),
            55_020_000 / 82_150_000,
            places=6,
        )

    def test_descuento_actual(self):
        self.assertAlmostEqual(
            calcular_descuento_actual(
                pab_origen_total=100_000_000,
                pab_actualizado_total=60_000_000,
            ),
            0.4,
        )
        self.assertEqual(
            calcular_descuento_actual(
                pab_origen_total=0,
                pab_actualizado_total=60_000_000,
            ),
            0.0,
        )

    def test_descuento_esperado_ponderado(self):
        self.assertAlmostEqual(
            calcular_descuento_esperado_ponderado(
                descuentos=[0.2, 0.4],
                pab_origen=[100_000_000, 300_000_000],
            ),
            0.35,
        )

    def test_apartado_neto_cliente_toma_un_solo_valor(self):
        asignacion = pd.DataFrame({
            "Id_Deuda": ["D1", "D2", "D3"],
            "Apartado_Neto": [1_000_000, 3_000_000, 2_000_000],
        })
        self.assertEqual(calcular_apartado_neto_cliente(asignacion), 3_000_000)

    def test_evaluar_deposito_extra(self):
        self.assertTrue(
            evaluar_deposito_extra(deposito_extra=30_000_000, apartado_neto=10_000_000)
        )
        self.assertTrue(
            evaluar_deposito_extra(deposito_extra=1_000_000, apartado_neto=0)
        )
        self.assertFalse(
            evaluar_deposito_extra(deposito_extra=30_000_001, apartado_neto=10_000_000)
        )
        self.assertFalse(
            evaluar_deposito_extra(deposito_extra=1_000_001, apartado_neto=0)
        )
        self.assertFalse(
            evaluar_deposito_extra(deposito_extra=-1, apartado_neto=10_000_000)
        )

    def test_evaluar_contraoferta(self):
        self.assertTrue(
            evaluar_contraoferta(
                contraoferta=0.6,
                descuento_actual=0.3,
                descuento_esperado=0.5,
            )
        )
        self.assertFalse(
            evaluar_contraoferta(
                contraoferta=0.96,
                descuento_actual=0.3,
                descuento_esperado=0.9,
            )
        )
        self.assertFalse(
            evaluar_contraoferta(
                contraoferta=0.3,
                descuento_actual=0.3,
                descuento_esperado=0.5,
            )
        )
        self.assertFalse(
            evaluar_contraoferta(
                contraoferta=0.75,
                descuento_actual=0.3,
                descuento_esperado=0.5,
            )
        )

    def test_evaluar_liq_insta(self):
        self.assertTrue(
            evaluar_liq_insta(
                descuento_actual=0.5,
                contraoferta=0.5,
                deposito_extra=0,
            )
        )
        self.assertTrue(
            evaluar_liq_insta(
                descuento_actual=0.6,
                contraoferta=0.5,
                deposito_extra=0,
            )
        )
        self.assertFalse(
            evaluar_liq_insta(
                descuento_actual=0.4,
                contraoferta=0.5,
                deposito_extra=0,
            )
        )
        self.assertFalse(
            evaluar_liq_insta(
                descuento_actual=0.0,
                contraoferta=-0.1,
                deposito_extra=0,
            )
        )
        self.assertTrue(
            evaluar_liq_insta(
                descuento_actual=0.0,
                contraoferta=0.5,
                deposito_extra=-1,
            )
        )

    def test_evaluar_ia_liquidadora(self):
        self.assertTrue(evaluar_ia_liquidadora(probabilidades=[0.4, 0.5]))
        self.assertFalse(evaluar_ia_liquidadora(probabilidades=[0.49]))

    def test_evaluar_viabilidad_cliente(self):
        resultado = evaluar_viabilidad_cliente(
            pab_total=60_000_000,
            pab_ideal_total=80_000_000,
            ingreso_total=6_000_000,
            ahorro=50_000_000,
            por_cobrar=5_000_000,
            es_opp_cred=True,
        )
        self.assertFalse(resultado["viable_tradicional"])
        self.assertTrue(resultado["viable_credito"])
        self.assertTrue(resultado["viable"])
        self.assertAlmostEqual(resultado["pago_total"], 67_160_000)

        sin_credito = evaluar_viabilidad_cliente(
            pab_total=60_000_000,
            pab_ideal_total=80_000_000,
            ingreso_total=6_000_000,
            ahorro=50_000_000,
            por_cobrar=5_000_000,
            es_opp_cred=False,
        )
        self.assertFalse(sin_credito["viable"])


class TestPaBActualizado(unittest.TestCase):
    def _acts(self, fechas, etiquetas, pabs):
        return pd.DataFrame({
            "Id_Deuda": ["D1"] * len(fechas),
            "Fecha_Act": fechas,
            "Etiqueta_Act": etiquetas,
            "PaB_Actualizado": pabs,
            "Correo": ["a@x.com"] * len(fechas),
            "Referencia": ["REF"] * len(fechas),
            "Nombre": ["Ana"] * len(fechas),
        })

    def test_toma_la_actualizacion_confiable_mas_reciente(self):
        acts = self._acts(
            fechas=[pd.Timestamp("2026-01-01"), pd.Timestamp("2026-02-01")],
            etiquetas=["CAMBIO DE PAB", "ACUERDO"],
            pabs=[70_000_000, 60_000_000],
        )
        with patch("modules.oportunidades.load_actualizacines_negos", return_value=acts):
            resultado = obtener_pab_actualizado_deuda("D1", pab_origen=100_000_000)
        self.assertEqual(resultado, 60_000_000)

    def test_si_la_ultima_no_es_confiable_usa_pab_origen(self):
        acts = self._acts(
            fechas=[pd.Timestamp("2026-01-01"), pd.Timestamp("2026-02-01")],
            etiquetas=["ACUERDO", "LLAMADA"],
            pabs=[60_000_000, 70_000_000],
        )
        with patch("modules.oportunidades.load_actualizacines_negos", return_value=acts):
            resultado = obtener_pab_actualizado_deuda("D1", pab_origen=100_000_000)
        self.assertEqual(resultado, 100_000_000)

    def test_sin_actualizaciones_usa_pab_origen(self):
        with patch(
            "modules.oportunidades.load_actualizacines_negos",
            return_value=pd.DataFrame(columns=["Id_Deuda", "Fecha_Act", "Etiqueta_Act", "PaB_Actualizado"]),
        ):
            resultado = obtener_pab_actualizado_deuda("D1", pab_origen=100_000_000)
        self.assertEqual(resultado, 100_000_000)

    def test_actualizado_alianzas_usa_el_resolver(self):
        acts = self._acts(
            fechas=[pd.Timestamp("2026-02-01")],
            etiquetas=["ACTUALIZADO_ALIANZAS"],
            pabs=[65_000_000],
        )
        with patch("modules.oportunidades.load_actualizacines_negos", return_value=acts), patch(
            "modules.oportunidades._resolver_pab_actualizado_alianzas",
            return_value=55_000_000,
        ):
            resultado = obtener_pab_actualizado_deuda("D1", pab_origen=100_000_000)
        self.assertEqual(resultado, 55_000_000)

    def test_acota_el_pab_actualizado_al_origen(self):
        acts = self._acts(
            fechas=[pd.Timestamp("2026-02-01")],
            etiquetas=["ACUERDO"],
            pabs=[120_000_000],
        )
        with patch("modules.oportunidades.load_actualizacines_negos", return_value=acts):
            resultado = obtener_pab_actualizado_deuda("D1", pab_origen=100_000_000)
        self.assertEqual(resultado, 100_000_000)


class TestPabAlianzas(unittest.TestCase):
    def _masivas(self, pab, fecha):
        metadata = {"Fecha_Limite_Uso": fecha} if fecha is not None else {}
        return pd.DataFrame({
            "Id_Deuda": ["D1"],
            "PaB_Propuesta": [pab],
            "Metadata": [metadata],
        })

    def _solicitudes(self, pab, fecha_respuesta):
        return pd.DataFrame({
            "Estado_Solicitud": ["Exitosa"],
            "Fecha_Respuesta": [fecha_respuesta],
            "Timestamp": [fecha_respuesta],
            "JSON_Respuesta": [[{"Id_Deuda": "D1", "Monto_Propuesto": pab}]],
            "Datos_Solicitud": [[]],
        })

    def test_prevalece_la_fuente_mas_reciente(self):
        with patch(
            "modules.oportunidades.load_masivas",
            return_value=self._masivas(70_000_000, pd.Timestamp("2026-01-01")),
        ), patch(
            "modules.oportunidades._obtener_solicitudes_mec_calculo",
            return_value=self._solicitudes(60_000_000, pd.Timestamp("2026-02-01")),
        ):
            resultado = _resolver_pab_actualizado_alianzas(
                id_deuda="D1",
                pab_origen=100_000_000,
                fecha_actualizacion=pd.Timestamp("2026-03-01"),
                pab_actualizado_fila=65_000_000,
            )
        self.assertEqual(resultado, 60_000_000)

    def test_masivas_puede_ser_la_mas_reciente(self):
        with patch(
            "modules.oportunidades.load_masivas",
            return_value=self._masivas(70_000_000, pd.Timestamp("2026-03-01")),
        ), patch(
            "modules.oportunidades._obtener_solicitudes_mec_calculo",
            return_value=self._solicitudes(60_000_000, pd.Timestamp("2026-02-01")),
        ):
            resultado = _resolver_pab_actualizado_alianzas(
                id_deuda="D1",
                pab_origen=100_000_000,
                fecha_actualizacion=pd.Timestamp("2026-04-01"),
                pab_actualizado_fila=65_000_000,
            )
        self.assertEqual(resultado, 70_000_000)

    def test_sin_fechas_usa_el_valor_de_la_fila(self):
        with patch(
            "modules.oportunidades.load_masivas",
            return_value=self._masivas(70_000_000, None),
        ), patch(
            "modules.oportunidades._obtener_solicitudes_mec_calculo",
            return_value=pd.DataFrame(),
        ):
            resultado = _resolver_pab_actualizado_alianzas(
                id_deuda="D1",
                pab_origen=100_000_000,
                fecha_actualizacion=pd.Timestamp("2026-04-01"),
                pab_actualizado_fila=65_000_000,
            )
        self.assertEqual(resultado, 65_000_000)


class TestAcuerdosRobo(unittest.TestCase):
    def _acts(self, fecha_acuerdo, fecha_posterior=None):
        fechas = [fecha_acuerdo]
        etiquetas = ["ACUERDO"]
        if fecha_posterior is not None:
            fechas.append(fecha_posterior)
            etiquetas.append("LLAMADA")
        return pd.DataFrame({
            "Id_Deuda": ["D1"] * len(fechas),
            "Fecha_Act": fechas,
            "Etiqueta_Act": etiquetas,
            "PaB_Actualizado": [60_000_000] * len(fechas),
            "Correo": ["a@x.com"] * len(fechas),
        })

    def _solicitudes(self, fecha_limite):
        return pd.DataFrame({
            "Estado_Solicitud": ["Exitosa"],
            "Tipo_Solicitud": ["Acuerdo de Pago"],
            "Fecha_Limite_Pago": [fecha_limite],
            "Fecha_Respuesta": [pd.Timestamp("2020-01-01")],
            "Timestamp": [pd.Timestamp("2020-01-01")],
            "Ids_Deuda": ["D1"],
            "Datos_Solicitud": [[]],
            "JSON_Respuesta": [[]],
            "Es_Historico": [False],
        })

    def test_acuerdo_vencido_sin_gestion_posterior(self):
        with patch(
            "modules.oportunidades.load_actualizacines_negos",
            return_value=self._acts(pd.Timestamp("2020-01-01")),
        ), patch(
            "modules.oportunidades.load_liquidaciones",
            return_value=set(),
        ), patch(
            "modules.oportunidades._obtener_solicitudes_mec_calculo",
            return_value=self._solicitudes(pd.Timestamp("2020-01-15")),
        ):
            resultado = obtener_acuerdos_robo(deudas=["D1"])
        self.assertEqual(resultado, {"D1": "15/01/2020"})

    def test_acuerdo_con_gestion_posterior_no_aplica(self):
        with patch(
            "modules.oportunidades.load_actualizacines_negos",
            return_value=self._acts(
                pd.Timestamp("2020-01-01"),
                pd.Timestamp("2020-01-02"),
            ),
        ), patch(
            "modules.oportunidades.load_liquidaciones",
            return_value=set(),
        ), patch(
            "modules.oportunidades._obtener_solicitudes_mec_calculo",
            return_value=self._solicitudes(pd.Timestamp("2020-01-15")),
        ):
            resultado = obtener_acuerdos_robo(deudas=["D1"])
        self.assertEqual(resultado, {})

    def test_deuda_liquidada_no_aplica(self):
        with patch(
            "modules.oportunidades.load_actualizacines_negos",
            return_value=self._acts(pd.Timestamp("2020-01-01")),
        ), patch(
            "modules.oportunidades.load_liquidaciones",
            return_value={"D1"},
        ), patch(
            "modules.oportunidades._obtener_solicitudes_mec_calculo",
            return_value=self._solicitudes(pd.Timestamp("2020-01-15")),
        ):
            resultado = obtener_acuerdos_robo(deudas=["D1"])
        self.assertEqual(resultado, {})

    def test_metabase_sin_fecha_se_considera(self):
        with patch(
            "modules.oportunidades.load_actualizacines_negos",
            return_value=self._acts(pd.Timestamp("2020-01-01")),
        ), patch(
            "modules.oportunidades.load_liquidaciones",
            return_value=set(),
        ), patch(
            "modules.oportunidades._obtener_solicitudes_mec_calculo",
            return_value=pd.DataFrame(),
        ), patch(
            "modules.oportunidades.obtener_fecha_expiracion_acuerdo",
            return_value=pd.NaT,
        ):
            resultado = obtener_acuerdos_robo(deudas=["D1"])
        self.assertEqual(resultado, {"D1": "Sin fecha"})

    def test_metabase_con_error_no_se_considera(self):
        with patch(
            "modules.oportunidades.load_actualizacines_negos",
            return_value=self._acts(pd.Timestamp("2020-01-01")),
        ), patch(
            "modules.oportunidades.load_liquidaciones",
            return_value=set(),
        ), patch(
            "modules.oportunidades._obtener_solicitudes_mec_calculo",
            return_value=pd.DataFrame(),
        ), patch(
            "modules.oportunidades.obtener_fecha_expiracion_acuerdo",
            return_value=None,
        ):
            resultado = obtener_acuerdos_robo(deudas=["D1"])
        self.assertEqual(resultado, {})

    def test_acuerdo_de_alianzas_vigente_no_cae_a_metabase(self):
        with patch(
            "modules.oportunidades.load_actualizacines_negos",
            return_value=self._acts(pd.Timestamp("2020-01-01")),
        ), patch(
            "modules.oportunidades.load_liquidaciones",
            return_value=set(),
        ), patch(
            "modules.oportunidades._obtener_solicitudes_mec_calculo",
            return_value=self._solicitudes(pd.Timestamp("2099-01-01")),
        ), patch(
            "modules.oportunidades.obtener_fecha_expiracion_acuerdo",
            return_value=pd.Timestamp("2020-02-01"),
        ):
            resultado = obtener_acuerdos_robo(deudas=["D1"])
        self.assertEqual(resultado, {})


class TestSincronizacionDeudaUI(unittest.TestCase):
    def _fake_st(self):
        fake_st = MagicMock()
        fake_st.session_state = {}
        return fake_st

    def test_conversion_descuento_pab(self):
        self.assertEqual(
            _calcular_pab_desde_descuento(pab_origen=100_000_000, descuento_pct=40),
            60_000_000,
        )
        self.assertEqual(
            _calcular_pab_desde_descuento(pab_origen=100_000_000, descuento_pct=-10),
            100_000_000,
        )
        self.assertEqual(
            _calcular_pab_desde_descuento(pab_origen=100_000_000, descuento_pct=110),
            0,
        )
        self.assertAlmostEqual(
            _calcular_descuento_desde_pab(pab_origen=100_000_000, pab=60_000_000),
            0.4,
        )

    def test_slider_descuento_actualiza_pab(self):
        fake_st = self._fake_st()
        fake_st.session_state["calc_ind_disc_slider_D1"] = 40.0
        with patch("ui.calculadora_components.st", fake_st):
            _sincronizar_desde_slider_descuento(clave="D1", pab_origen=100_000_000)
        self.assertEqual(fake_st.session_state["calc_ind_pab_D1"], 60_000_000)
        self.assertEqual(fake_st.session_state["calc_ind_pab_slider_D1"], 60_000_000)
        self.assertEqual(fake_st.session_state["calc_ind_pab_text_D1"], "60,000,000")
        self.assertEqual(fake_st.session_state["calc_ind_disc_text_D1"], "40.0")

    def test_slider_pab_actualiza_descuento(self):
        fake_st = self._fake_st()
        fake_st.session_state["calc_ind_pab_slider_D1"] = 60_000_000
        with patch("ui.calculadora_components.st", fake_st):
            _sincronizar_desde_slider_pab(clave="D1", pab_origen=100_000_000)
        self.assertEqual(fake_st.session_state["calc_ind_pab_D1"], 60_000_000)
        self.assertEqual(fake_st.session_state["calc_ind_disc_slider_D1"], 40.0)
        self.assertEqual(fake_st.session_state["calc_ind_disc_text_D1"], "40.0")

    def test_texto_pab_invalido_vuelve_al_valor_actual(self):
        fake_st = self._fake_st()
        fake_st.session_state["calc_ind_pab_D1"] = 60_000_000
        fake_st.session_state["calc_ind_pab_text_D1"] = "no-numero"
        with patch("ui.calculadora_components.st", fake_st):
            _sincronizar_desde_texto_pab(clave="D1", pab_origen=100_000_000)
        self.assertEqual(fake_st.session_state["calc_ind_pab_D1"], 60_000_000)
        self.assertEqual(fake_st.session_state["calc_ind_pab_text_D1"], "60,000,000")


class TestCalcularOportunidadesReferencia(unittest.TestCase):
    def _asignacion(self):
        return pd.DataFrame({
            "Referencia": ["REF"],
            "Id_Deuda": ["D1"],
            "PaB_Origen": [100_000_000.0],
            "Descuento_Esperado": [0.5],
            "Apartado_Neto": [10_000_000.0],
            "Pricing": [0.15],
        })

    def _patches(self, es_opp_cred):
        return [
            patch(
                "modules.oportunidades.obtener_asignacion_para_referencia",
                return_value=self._asignacion(),
            ),
            patch(
                "modules.oportunidades.obtener_pricing_para_referencia",
                return_value=0.15,
            ),
            patch(
                "modules.oportunidades.obtener_pab_actualizado_deuda",
                return_value=60_000_000,
            ),
            patch(
                "modules.oportunidades._obtener_pab_ideal_deuda",
                return_value=80_000_000,
            ),
            patch(
                "modules.oportunidades.obtener_estado_actual_credito",
                return_value=("CERRADO", False, False),
            ),
            patch(
                "modules.oportunidades.obtener_acuerdos_robo",
                return_value={},
            ),
            patch(
                "modules.oportunidades.obtener_probabilidades_ia_liquidadora",
                return_value={"D1": 0.6},
            ),
        ]

    def _calcular(self, es_opp_cred, pab_por_deuda=None):
        patches = self._patches(es_opp_cred)
        for p in patches:
            p.start()
        try:
            return calcular_oportunidades_referencia(
                referencia="REF",
                deudas=["D1"],
                es_opp_cred=es_opp_cred,
                ahorro=50_000_000,
                porcobrar=5_000_000,
                deposito_extra=0,
                pab_por_deuda=pab_por_deuda,
            )
        finally:
            for p in patches:
                p.stop()

    def test_analisis_por_credito(self):
        opps = self._calcular(es_opp_cred=True)
        # El pago actual (60M) cabe en el cupo (80M): no requiere depósito
        self.assertFalse(opps["Depósito Extra"]["aplica"])
        self.assertEqual(opps["Depósito Extra"]["valor"], -19_980_000)
        self.assertFalse(opps["ContraOferta Viable"]["aplica"])
        self.assertTrue(opps["Liquidación Instantánea"]["aplica"])
        self.assertFalse(opps["Acuerdo para Robo"]["aplica"])
        self.assertTrue(opps["IA Liquidadora"]["aplica"])

    def test_analisis_por_tradicional(self):
        opps = self._calcular(es_opp_cred=False)
        self.assertTrue(opps["Depósito Extra"]["aplica"])
        self.assertEqual(opps["Depósito Extra"]["valor"], 22_160_000)
        self.assertTrue(opps["ContraOferta Viable"]["aplica"])
        self.assertFalse(opps["Liquidación Instantánea"]["aplica"])
        self.assertFalse(opps["Acuerdo para Robo"]["aplica"])
        self.assertTrue(opps["IA Liquidadora"]["aplica"])

    def test_pab_simulado_reemplaza_pab_actualizado_en_tradicional(self):
        opps = self._calcular(
            es_opp_cred=False,
            pab_por_deuda={"D1": 40_000_000},
        )
        # Con PaB simulado de 40M el depósito baja de 22.16M a 5.73M
        self.assertEqual(opps["Depósito Extra"]["valor"], 5_730_000)
        self.assertTrue(opps["ContraOferta Viable"]["aplica"])
        self.assertFalse(opps["Liquidación Instantánea"]["aplica"])

    def test_pab_simulado_se_usa_en_comparacion_de_contraoferta(self):
        opps = self._calcular(
            es_opp_cred=False,
            pab_por_deuda={"D1": 30_000_000},
        )
        # La fórmula de la ContraOferta no cambia, pero al simular 70% de
        # descuento ya no es oportunidad y pasa a Liquidación Instantánea
        self.assertAlmostEqual(opps["ContraOferta Viable"]["valor"], 55_020_000 / 82_150_000)
        self.assertFalse(opps["ContraOferta Viable"]["aplica"])
        self.assertTrue(opps["Liquidación Instantánea"]["aplica"])
        self.assertAlmostEqual(opps["Liquidación Instantánea"]["valor"], 0.7)

    def test_pab_simulado_reemplaza_pab_actualizado_en_credito(self):
        opps = self._calcular(
            es_opp_cred=True,
            pab_por_deuda={"D1": 50_000_000},
        )
        # Depósito Extra Crédito = 50M + 20k - 80M
        self.assertFalse(opps["Depósito Extra"]["aplica"])
        self.assertEqual(opps["Depósito Extra"]["valor"], -29_980_000)
        self.assertFalse(opps["ContraOferta Viable"]["aplica"])
        self.assertTrue(opps["Liquidación Instantánea"]["aplica"])
        self.assertAlmostEqual(opps["Liquidación Instantánea"]["valor"], 0.5)

    def test_pab_simulado_mayor_al_ideal_exige_deposito_extra_credito(self):
        opps = self._calcular(
            es_opp_cred=True,
            pab_por_deuda={"D1": 90_000_000},
        )
        # Depósito Extra Crédito = 90M + 20k - 80M
        self.assertTrue(opps["Depósito Extra"]["aplica"])
        self.assertEqual(opps["Depósito Extra"]["valor"], 10_020_000)
        self.assertTrue(opps["ContraOferta Viable"]["aplica"])
        self.assertFalse(opps["Liquidación Instantánea"]["aplica"])

    def test_pab_simulado_normaliza_ids_y_deudas_ausentes_usan_oficial(self):
        opps_sin_deuda = self._calcular(
            es_opp_cred=False,
            pab_por_deuda={"D2": 10_000_000},
        )
        self.assertEqual(opps_sin_deuda["Depósito Extra"]["valor"], 22_160_000)

        opps_id_con_sufijo = self._calcular(
            es_opp_cred=False,
            pab_por_deuda={"D1.0": 40_000_000},
        )
        self.assertEqual(opps_id_con_sufijo["Depósito Extra"]["valor"], 5_730_000)

    def test_pab_simulado_se_acota_al_pab_origen(self):
        opps = self._calcular(
            es_opp_cred=False,
            pab_por_deuda={"D1": 150_000_000},
        )
        # El input no puede superar el PaB_Origen: 100M + 20k - 45M
        self.assertEqual(opps["Depósito Extra"]["valor"], 55_020_000)
        self.assertAlmostEqual(opps["Liquidación Instantánea"]["valor"], 0.0)

    def test_sin_deudas_no_hay_oportunidades(self):
        opps = calcular_oportunidades_referencia(
            referencia="REF",
            deudas=[],
            es_opp_cred=True,
        )
        self.assertTrue(all(not opp["aplica"] for opp in opps.values()))

    def test_credito_sin_pab_ideal_desactiva_oportunidades_de_credito(self):
        patches = [
            patch(
                "modules.oportunidades.obtener_asignacion_para_referencia",
                return_value=self._asignacion(),
            ),
            patch(
                "modules.oportunidades.obtener_pricing_para_referencia",
                return_value=0.15,
            ),
            patch(
                "modules.oportunidades.obtener_pab_actualizado_deuda",
                return_value=60_000_000,
            ),
            patch(
                "modules.oportunidades._obtener_pab_ideal_deuda",
                return_value=0,
            ),
            patch(
                "modules.oportunidades.obtener_estado_actual_credito",
                return_value=("CERRADO", False, False),
            ),
            patch(
                "modules.oportunidades.obtener_acuerdos_robo",
                return_value={},
            ),
            patch(
                "modules.oportunidades.obtener_probabilidades_ia_liquidadora",
                return_value={"D1": 0.6},
            ),
        ]
        for p in patches:
            p.start()
        try:
            opps = calcular_oportunidades_referencia(
                referencia="REF",
                deudas=["D1"],
                es_opp_cred=True,
                ahorro=50_000_000,
                porcobrar=5_000_000,
                deposito_extra=0,
            )
        finally:
            for p in patches:
                p.stop()

        self.assertFalse(opps["Depósito Extra"]["aplica"])
        self.assertFalse(opps["ContraOferta Viable"]["aplica"])
        self.assertFalse(opps["Liquidación Instantánea"]["aplica"])
        self.assertIn("Falta PaB Ideal", opps["Depósito Extra"]["detalle"])
        self.assertTrue(opps["IA Liquidadora"]["aplica"])


class TestPabInicialCalculadora(unittest.TestCase):
    def test_pab_inicial_usa_descuento_actual_y_no_pab_ideal(self):
        with patch(
            "ui.calculadora_components.obtener_pab_actualizado_deuda",
            return_value=60_000_000,
        ) as mock_actualizado:
            pab_inicial = _obtener_pab_inicial_deuda(
                deuda="D1",
                pab_origen=100_000_000,
            )

        self.assertEqual(pab_inicial, 60_000_000)
        mock_actualizado.assert_called_once_with("D1", pab_origen=100_000_000)


if __name__ == "__main__":
    unittest.main()
