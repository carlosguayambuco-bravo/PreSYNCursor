"""Tests de las funciones de cálculo del negocio.

Estos tests fijan el comportamiento actual de las fórmulas y utilidades que
sostienen el formulario de alianzas, la comparación de descuentos y la
distribución de montos. No acceden a Google Sheets, Streamlit ni Metabase:
las dependencias externas se reemplazan con mocks o con datos en memoria.
"""

import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from modules.bank_normalizer import normalizar_banco, normalizar_bancos_vectorizado
from modules.classes import Aliado, crear_diccionario_aliados, parse_tiempos_respuesta
from modules.forms import (
    _obtener_nombre_corto_negociador,
    alertar_excedencia_contraprop_max_relativa,
    obtener_descuento_optimo,
    obtener_descuento_optimo_credito,
    obtener_descuento_optimo_tradicional,
    validar_descuento_base,
    verificar_bloqueo_bancos,
)
from modules.gest_sols import (
    _distribuir_hamilton,
    _distribuir_monto_con_granularidad,
    _es_multiplo_de,
    _evaluar_distribucion_granular,
    _generar_unidades_descendentes,
    _normalizar_pesos_para_distribucion,
    _potencia_de_diez_divisora,
    calcular_comparacion_descuentos,
    calcular_porcentaje_descuento,
    distribuir_monto_por_deuda,
    formatear_descuento_base,
    formatear_pab_ideal,
    formatear_valor_solicitado,
    obtener_color_comparacion,
)
from utils.helpers_general import (
    cleanNumber,
    formatNumber,
    getBDDaysDiffFloat,
    getBDDaysDiffFloat_vectorized,
    getMesOperativo,
    getSheetMonthNumber,
    move_business_days,
    parsePercentage,
)


class TestUtilidadesNumericas(unittest.TestCase):
    def test_clean_number_formatos_colombianos(self):
        self.assertEqual(cleanNumber("$ 1.234,56"), 1234.56)
        self.assertEqual(cleanNumber("1.234,56"), 1234.56)
        self.assertEqual(cleanNumber("1,234.56"), 1234.56)
        self.assertEqual(cleanNumber("1.234.567"), 1234567.0)
        self.assertEqual(cleanNumber("1,234"), 1234.0)
        self.assertEqual(cleanNumber("12,5"), 12.5)
        self.assertEqual(cleanNumber("X123"), 123.0)

    def test_clean_number_invalido_usa_default(self):
        self.assertIsNone(cleanNumber("abc", default_nan=None))
        self.assertEqual(cleanNumber("", default_nan=-1.0), -1.0)
        self.assertEqual(cleanNumber(1234), 1234)

    def test_format_number_formato_colombiano(self):
        self.assertEqual(formatNumber(1234.56), "1.234,56")
        self.assertEqual(formatNumber(1000000), "1.000.000")
        self.assertEqual(formatNumber("1.234,56"), "1.234,56")

    def test_parse_percentage(self):
        self.assertAlmostEqual(parsePercentage("15%"), 0.15)
        self.assertAlmostEqual(parsePercentage(15), 0.15)
        self.assertAlmostEqual(parsePercentage(0.15), 0.15)
        self.assertAlmostEqual(parsePercentage("no-es-numero", default_value=0.2), 0.2)
        self.assertAlmostEqual(parsePercentage(None, default_value=0.2), 0.2)

    def test_get_sheet_month_number(self):
        self.assertEqual(getSheetMonthNumber("Enero-25"), 301)
        self.assertEqual(getSheetMonthNumber("Diciembre-99"), 1200)
        self.assertEqual(getSheetMonthNumber("Septiembre-26"), 321)
        self.assertEqual(getSheetMonthNumber("Enero-2025"), -1)
        self.assertEqual(getSheetMonthNumber("formato-invalido"), -1)

    def test_mes_operativo_es_el_primer_dia_del_mes(self):
        mes_operativo = getMesOperativo()
        self.assertEqual(mes_operativo.day, 1)
        self.assertIsInstance(mes_operativo, pd.Timestamp)


class TestDiasHabiles(unittest.TestCase):
    def test_diferencia_en_dias_habiles(self):
        # Lunes 7 de septiembre de 2026 a miércoles 9 de septiembre de 2026.
        inicio = pd.Timestamp("2026-09-07 00:00:00")
        fin = pd.Timestamp("2026-09-09 00:00:00")
        self.assertEqual(getBDDaysDiffFloat(inicio, fin), 2.0)

    def test_diferencia_con_fracciones_de_dia(self):
        inicio = pd.Timestamp("2026-09-07 12:00:00")
        fin = pd.Timestamp("2026-09-09 12:00:00")
        self.assertEqual(getBDDaysDiffFloat(inicio, fin), 2.0)

    def test_diferencia_invierte_fechas_por_defecto(self):
        inicio = pd.Timestamp("2026-09-09 00:00:00")
        fin = pd.Timestamp("2026-09-07 00:00:00")
        self.assertEqual(getBDDaysDiffFloat(inicio, fin), 2.0)

    def test_diferencia_con_fecha_nula(self):
        resultado = getBDDaysDiffFloat(pd.Timestamp("2026-09-07"), pd.NaT)
        self.assertTrue(np.isnan(resultado))

    def test_diferencia_vectorizada_y_nulos(self):
        resultado = getBDDaysDiffFloat_vectorized(
            pd.Series([pd.Timestamp("2026-09-07 12:00:00"), pd.NaT]),
            pd.Series([pd.Timestamp("2026-09-09 12:00:00"), pd.Timestamp("2026-09-09")]),
        )
        self.assertEqual(resultado.iloc[0], 2.0)
        self.assertTrue(pd.isna(resultado.iloc[1]))

    def test_move_business_days_salta_el_fin_de_semana(self):
        # Viernes 11 de septiembre de 2026 + 1 día hábil = lunes 14.
        self.assertEqual(
            move_business_days(date=pd.Timestamp("2026-09-11"), delta_days=1),
            pd.Timestamp("2026-09-14"),
        )


class TestTiemposRespuestaAliado(unittest.TestCase):
    def test_parse_tiempos_respuesta(self):
        casos = {
            "1 día": 24.0,
            "2 dias": 48.0,
            "1 semana": 120.0,
            "1.5 semanas": 180.0,
            "2 semanas hábiles": 240.0,
            "inmediato": 72.0,
            "": 72.0,
            None: 72.0,
        }
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(parse_tiempos_respuesta(texto), esperado)

    def test_aliado_calcula_dias_y_texto_de_respuesta(self):
        aliado = Aliado(
            nombre="Aliado A",
            bancos=["Bancolombia", "Banco de Bogotá"],
            ejecutivo="Ejecutivo",
            pago_co_obligatorio=True,
            brinda_descuento_max=True,
            permiso_cuotas=False,
            tiempo_horas_respuesta=49,
            toca_validar_bancos=True,
            contraprop_max_relativa=0.1,
        )
        self.assertEqual(aliado.obtener_tr_dias(), 2)
        self.assertEqual(aliado.obtener_tr_horas_parsed(), "2.04 días hábiles")
        self.assertTrue(aliado.pagar_co_obligatorio())
        self.assertTrue(aliado.brinda_maximo_descuento())
        self.assertTrue(aliado.necesita_validar_bancos())
        self.assertFalse(aliado.permite_cuotas())
        self.assertAlmostEqual(aliado.obtener_contraprop_max_relativa(), 0.1)

    def test_aliado_valida_bancos_con_texto_limpio(self):
        aliado = Aliado(
            nombre="Aliado A",
            bancos=["Bancolombia", "Banco de Bogotá"],
            ejecutivo="",
            pago_co_obligatorio=False,
            brinda_descuento_max=False,
            permiso_cuotas=True,
            tiempo_horas_respuesta=72,
            toca_validar_bancos=True,
        )
        self.assertTrue(aliado.validar_banco("BANCOLOMBIA S.A."))
        self.assertTrue(aliado.validar_banco("Banco de Bogota"))
        self.assertFalse(aliado.validar_banco("Davivienda"))

    def test_crear_diccionario_aliados_parsea_tiempos(self):
        df = pd.DataFrame([
            {
                "Nombre Normalizado": "Aliado A",
                "Bancos": "Bancolombia, Davivienda",
                "Ejecutivo": "Ejecutivo A",
                "Contraofertas de Pago Obligatorio": True,
                "Brindan Máx. Descuento": False,
                "Pago a Cuotas": True,
                "Tiempos de Respuesta": "2 días",
                "Bloquear Bancos": False,
                "Contrapropuesta_Maxima_Relativa": 0.15,
            }
        ])
        aliados = crear_diccionario_aliados(df)
        self.assertIn("Aliado A", aliados)
        aliado = aliados["Aliado A"]
        self.assertEqual(aliado.obtener_bancos(), ["Bancolombia", "Davivienda"])
        self.assertEqual(aliado.obtener_tr_horas(), 48.0)
        self.assertTrue(aliado.permite_cuotas())

    def test_verificar_bloqueo_bancos_respeta_configuracion_del_aliado(self):
        sin_bloqueo = Aliado(
            nombre="Sin Bloqueo",
            bancos=[],
            ejecutivo="",
            pago_co_obligatorio=False,
            brinda_descuento_max=False,
            permiso_cuotas=True,
            tiempo_horas_respuesta=72,
            toca_validar_bancos=False,
        )
        self.assertEqual(
            verificar_bloqueo_bancos(
                bancos_verificar=["Bancolombia", "Davivienda"],
                aliado_bloqueo=sin_bloqueo,
            ),
            {"Bancolombia": True, "Davivienda": True},
        )

        con_bloqueo = Aliado(
            nombre="Con Bloqueo",
            bancos=["Bancolombia"],
            ejecutivo="",
            pago_co_obligatorio=False,
            brinda_descuento_max=False,
            permiso_cuotas=True,
            tiempo_horas_respuesta=72,
            toca_validar_bancos=True,
        )
        self.assertEqual(
            verificar_bloqueo_bancos(
                bancos_verificar=["Bancolombia", "Davivienda"],
                aliado_bloqueo=con_bloqueo,
            ),
            {"Bancolombia": True, "Davivienda": False},
        )


class TestDescuentosYFormato(unittest.TestCase):
    def test_calcular_porcentaje_descuento(self):
        self.assertAlmostEqual(
            calcular_porcentaje_descuento(valor=75000, monto_actual=100000),
            0.25,
        )
        self.assertEqual(calcular_porcentaje_descuento(valor=0, monto_actual=0), 0.0)
        self.assertAlmostEqual(
            calcular_porcentaje_descuento(valor="$ 1.000", monto_actual="2.000"),
            0.5,
        )

    def test_formatear_valor_solicitado_y_pab_ideal(self):
        self.assertEqual(
            formatear_valor_solicitado(monto_propuesto=75000, monto_actual=100000),
            r"\$75,000 (25.0%)",
        )
        self.assertEqual(
            formatear_pab_ideal(valor=80000, monto_actual=100000),
            r"\$80,000 (20.0%)",
        )

    def test_formatear_descuento_base(self):
        self.assertEqual(
            formatear_descuento_base(
                casa_cobro="Aliado A",
                valor=75000,
                monto_actual=100000,
            ),
            r"**Aliado A**: \$75,000 (25.0%) - **Origen**: Base",
        )
        self.assertEqual(
            formatear_descuento_base(
                casa_cobro="Aliado A",
                valor=75000,
                monto_actual=100000,
                origen="Solicitud Exitosa",
                valor_portafolio=20000,
                incluir_origen=False,
            ),
            r"**Aliado A**: \$75,000 (25.0%) - **Portafolio**: \$20,000",
        )
        self.assertTrue(
            formatear_descuento_base(
                casa_cobro=float("nan"),
                valor=1000,
                monto_actual=2000,
            ).startswith("**Directo Base**")
        )

    def test_color_comparacion_por_umbrales(self):
        self.assertEqual(obtener_color_comparacion(valor=90, valor_solicitado=100), "green")
        self.assertEqual(obtener_color_comparacion(valor=100, valor_solicitado=100), "green")
        self.assertEqual(obtener_color_comparacion(valor=110, valor_solicitado=100), "yellow")
        self.assertEqual(obtener_color_comparacion(valor=115, valor_solicitado=100), "yellow")
        self.assertEqual(obtener_color_comparacion(valor=115.01, valor_solicitado=100), "orange")


class TestComparacionDescuentos(unittest.TestCase):
    @staticmethod
    def _deudas():
        return [
            {"Id_Deuda": "1", "Monto_Actual": 100000, "Monto_Propuesto": 75000},
            {"Id_Deuda": "2", "Monto_Actual": 50000, "Monto_Propuesto": 30000},
        ]

    @staticmethod
    def _masivas():
        return pd.DataFrame([
            {
                "Id_Deuda": "1",
                "Casa_Cobro": "Aliado A",
                "PaB_Propuesta": 70000,
                "PaB_Portafolio": None,
                "Origen": "Base",
            },
            {
                "Id_Deuda": "1",
                "Casa_Cobro": "Aliado A",
                "PaB_Propuesta": 65000,
                "PaB_Portafolio": None,
                "Origen": "Base",
            },
            {
                "Id_Deuda": "1",
                "Casa_Cobro": "Aliado B",
                "PaB_Propuesta": 60000,
                "PaB_Portafolio": None,
                "Origen": "Base",
            },
            {
                "Id_Deuda": "2",
                "Casa_Cobro": "Aliado A",
                "PaB_Propuesta": 40000,
                "PaB_Portafolio": 10000,
                "Origen": "Solicitud Exitosa",
            },
        ])

    def test_elige_el_mejor_descuento_por_aliado_y_deuda(self):
        resultado = calcular_comparacion_descuentos(
            deudas=self._deudas(),
            masivas_df=self._masivas(),
            pab_ideal_dict={"1": 80000},
            aliado="Aliado A",
        )

        fila_1, fila_2 = resultado["filas"]
        self.assertEqual(fila_1["base"], 65000)
        self.assertEqual(fila_1["origen_base"], "Base")
        self.assertEqual(fila_1["base_otros"][0]["aliado"], "Aliado B")
        self.assertEqual(fila_1["base_otros"][0]["valor"], 60000)
        self.assertEqual(fila_2["base"], 40000)
        self.assertEqual(fila_2["origen_base"], "Solicitud Exitosa")
        self.assertEqual(fila_2["base_otros"], [])

    def test_calcula_totales_y_deudas_faltantes(self):
        resultado = calcular_comparacion_descuentos(
            deudas=self._deudas(),
            masivas_df=self._masivas(),
            pab_ideal_dict={"1": 80000},
            aliado="Aliado A",
        )

        self.assertTrue(resultado["hay_pab_ideal"])
        self.assertTrue(resultado["hay_base"])
        self.assertTrue(resultado["hay_base_aliado"])
        self.assertEqual(resultado["deudas_sin_pab_ideal"], ["2"])
        self.assertEqual(resultado["deudas_sin_base_aliado"], [])
        self.assertEqual(resultado["deudas_sin_base_aliado_con_otros"], [])
        self.assertEqual(resultado["deudas_sin_base"], [])

        totales = resultado["totales"]
        self.assertEqual(totales["valor_solicitado"]["valor"], 105000)
        self.assertAlmostEqual(totales["valor_solicitado"]["descuento"], 0.30)
        self.assertEqual(totales["base"]["valor"], 105000)
        self.assertAlmostEqual(totales["base"]["descuento"], 0.30)
        self.assertTrue(totales["base"]["completo"])
        self.assertEqual(totales["pab_ideal"]["valor"], 80000)
        self.assertFalse(totales["pab_ideal"]["completo"])
        self.assertEqual(totales["pab_ideal"]["deudas_faltantes"], ["2"])

    def test_normaliza_ids_con_sufijo_punto_cero(self):
        deudas = [
            {"Id_Deuda": "1.0", "Monto_Actual": 100000, "Monto_Propuesto": 75000},
        ]
        masivas = pd.DataFrame([
            {
                "Id_Deuda": "1",
                "Casa_Cobro": "Aliado A",
                "PaB_Propuesta": 65000,
                "PaB_Portafolio": None,
            },
        ])
        resultado = calcular_comparacion_descuentos(
            deudas=deudas,
            masivas_df=masivas,
            pab_ideal_dict={"1": 80000},
            aliado="Aliado A",
        )
        self.assertEqual(resultado["filas"][0]["id_deuda"], "1")
        self.assertEqual(resultado["filas"][0]["base"], 65000)

    def test_sin_datos_de_base_reporta_deudas_faltantes(self):
        resultado = calcular_comparacion_descuentos(
            deudas=self._deudas(),
            masivas_df=pd.DataFrame(),
            pab_ideal_dict={},
            aliado="Aliado A",
        )
        self.assertFalse(resultado["hay_pab_ideal"])
        self.assertFalse(resultado["hay_base"])
        self.assertFalse(resultado["hay_base_aliado"])
        self.assertIsNone(resultado["totales"]["base"]["valor"])
        self.assertEqual(resultado["deudas_sin_base"], ["1", "2"])
        self.assertEqual(resultado["deudas_sin_pab_ideal"], ["1", "2"])

    def test_comparacion_es_case_insensitive_para_el_aliado(self):
        resultado = calcular_comparacion_descuentos(
            deudas=self._deudas()[:1],
            masivas_df=self._masivas(),
            pab_ideal_dict={},
            aliado="aliado a",
        )
        self.assertEqual(resultado["filas"][0]["base"], 65000)


class TestDistribucionMontos(unittest.TestCase):
    def test_potencia_de_diez_divisora(self):
        self.assertEqual(_potencia_de_diez_divisora(monto=1000000), 1000000)
        self.assertEqual(_potencia_de_diez_divisora(monto=1234000), 1000)
        self.assertEqual(_potencia_de_diez_divisora(monto=999), 1)
        self.assertEqual(_potencia_de_diez_divisora(monto=0), 1)

    def test_generar_unidades_descendentes(self):
        self.assertEqual(
            _generar_unidades_descendentes(unidad_inicial=1000000),
            [1000000, 500000, 100000, 50000, 10000, 5000, 1000],
        )
        self.assertEqual(_generar_unidades_descendentes(unidad_inicial=500), [])

    def test_es_multiplo_de(self):
        self.assertTrue(_es_multiplo_de(monto=1000000, divisor=1000))
        self.assertTrue(_es_multiplo_de(monto=1000000.0, divisor=1000))
        self.assertFalse(_es_multiplo_de(monto=1000001, divisor=1000))
        self.assertFalse(_es_multiplo_de(monto=1000000, divisor=0))
        self.assertFalse(_es_multiplo_de(monto=float("inf"), divisor=1000))

    def test_normalizar_pesos_para_distribucion(self):
        self.assertEqual(
            _normalizar_pesos_para_distribucion(pesos={"a": -5, "b": 2}),
            {"a": 0.0, "b": 2.0},
        )
        self.assertEqual(
            _normalizar_pesos_para_distribucion(pesos={"a": 0, "b": 0}),
            {"a": 1.0, "b": 1.0},
        )

    def test_hamilton_reparte_unidades_y_conserva_el_total(self):
        self.assertEqual(
            _distribuir_hamilton(pesos={"a": 1, "b": 1}, monto_total=1000, unidad=100),
            {"a": 500.0, "b": 500.0},
        )
        self.assertEqual(
            _distribuir_hamilton(pesos={"a": 1, "b": 2}, monto_total=1000, unidad=100),
            {"a": 300.0, "b": 700.0},
        )
        self.assertEqual(_distribuir_hamilton(pesos={}, monto_total=1000, unidad=100), {})
        self.assertEqual(
            sum(_distribuir_hamilton(pesos={"a": 1, "b": 3}, monto_total=1000, unidad=100).values()),
            1000.0,
        )

    def test_evaluacion_de_granularidad(self):
        evaluacion = _evaluar_distribucion_granular(
            montos={"a": 500, "b": 500},
            pesos={"a": 1, "b": 1},
            monto_total=1000,
            unidad=100,
        )
        self.assertTrue(evaluacion["cumple"])
        self.assertEqual(evaluacion["mae"], 0.0)
        self.assertEqual(evaluacion["mre"], 0.0)
        self.assertTrue(evaluacion["sin_extincion"])

        evaluacion_extinguida = _evaluar_distribucion_granular(
            montos={"a": 1000, "b": 0},
            pesos={"a": 1, "b": 1},
            monto_total=1000,
            unidad=100,
        )
        self.assertFalse(evaluacion_extinguida["cumple"])
        self.assertFalse(evaluacion_extinguida["sin_extincion"])

    def test_distribucion_con_granularidad(self):
        resultado = _distribuir_monto_con_granularidad(
            pesos={"a": 2, "b": 1},
            monto_total=1000000,
        )
        self.assertIsNotNone(resultado)
        self.assertEqual(resultado["montos"], {"a": 670000.0, "b": 330000.0})
        self.assertEqual(resultado["granularidad"], 10000.0)

        # Con tres deudas iguales y solo 1.000 disponibles no se puede evitar
        # extinguir deudas con la unidad mínima de 1.000.
        self.assertIsNone(
            _distribuir_monto_con_granularidad(
                pesos={"a": 1, "b": 1, "c": 1},
                monto_total=1000,
            )
        )

    def test_distribuir_una_sola_deuda_devuelve_el_total(self):
        resultado = distribuir_monto_por_deuda(
            deudas=["1"],
            montos_actuales={"1": 700},
            monto_total=1234.56,
        )
        self.assertEqual(resultado["montos"], {"1": 1234.56})
        self.assertEqual(resultado["granularidad"], 0.0)
        self.assertFalse(resultado["uso_base"])

    def test_distribucion_proporcional_al_monto_actual(self):
        resultado = distribuir_monto_por_deuda(
            deudas=["1", "2"],
            montos_actuales={"1": 700, "2": 300},
            monto_total=1000000,
        )
        self.assertEqual(resultado["montos"], {"1": 700000.0, "2": 300000.0})
        self.assertEqual(resultado["pesos"], {"1": 700.0, "2": 300.0})
        self.assertEqual(resultado["granularidad"], 100000.0)
        self.assertFalse(resultado["uso_base"])
        self.assertEqual(sum(resultado["montos"].values()), 1000000.0)

    def test_distribucion_sin_granularidad_ajusta_la_diferencia(self):
        resultado = distribuir_monto_por_deuda(
            deudas=["1", "2"],
            montos_actuales={"1": 700, "2": 300},
            monto_total=1001,
        )
        self.assertEqual(resultado["granularidad"], 0.0)
        self.assertEqual(sum(resultado["montos"].values()), 1001.0)
        self.assertEqual(resultado["montos"], {"1": 701.0, "2": 300.0})

    def test_distribucion_con_pesos_en_cero_reparte_igual(self):
        resultado = distribuir_monto_por_deuda(
            deudas=["1", "2"],
            montos_actuales={"1": 0, "2": 0},
            monto_total=1000,
        )
        self.assertEqual(resultado["montos"], {"1": 500.0, "2": 500.0})
        self.assertEqual(resultado["pesos"], {"1": 0.0, "2": 0.0})

    def test_distribucion_ignora_ids_duplicados(self):
        resultado = distribuir_monto_por_deuda(
            deudas=["1", "1", "2"],
            montos_actuales={"1": 500, "2": 500},
            monto_total=1000,
        )
        self.assertEqual(set(resultado["montos"]), {"1", "2"})
        self.assertEqual(sum(resultado["montos"].values()), 1000.0)

    def test_distribucion_sin_deudas(self):
        self.assertEqual(
            distribuir_monto_por_deuda(
                deudas=[],
                montos_actuales={},
                monto_total=1000,
            ),
            {"montos": {}, "pesos": {}, "uso_base": False, "granularidad": 0.0},
        )

    def test_distribucion_prioriza_valores_en_base_del_aliado(self):
        masivas = pd.DataFrame([
            {"Id_Deuda": "1", "Casa_Cobro": "Aliado A", "PaB_Propuesta": 60000, "PaB_Portafolio": None},
            {"Id_Deuda": "1", "Casa_Cobro": "Aliado A", "PaB_Propuesta": 55000, "PaB_Portafolio": None},
            {"Id_Deuda": "2", "Casa_Cobro": "Aliado A", "PaB_Propuesta": 30000, "PaB_Portafolio": None},
            {"Id_Deuda": "2", "Casa_Cobro": "Aliado B", "PaB_Propuesta": 20000, "PaB_Portafolio": None},
        ])
        resultado = distribuir_monto_por_deuda(
            deudas=["1", "2"],
            montos_actuales={"1": 100000, "2": 50000},
            monto_total=85000,
            aliado="Aliado A",
            masivas_df=masivas,
        )
        self.assertTrue(resultado["uso_base"])
        self.assertEqual(resultado["pesos"], {"1": 55000.0, "2": 30000.0})
        self.assertEqual(resultado["montos"], {"1": 55000.0, "2": 30000.0})
        self.assertEqual(resultado["granularidad"], 1000.0)

    def test_distribucion_cae_a_monto_actual_si_falta_base(self):
        masivas = pd.DataFrame([
            {"Id_Deuda": "1", "Casa_Cobro": "Aliado A", "PaB_Propuesta": 55000, "PaB_Portafolio": None},
        ])
        resultado = distribuir_monto_por_deuda(
            deudas=["1", "2"],
            montos_actuales={"1": 100000, "2": 50000},
            monto_total=85000,
            aliado="Aliado A",
            masivas_df=masivas,
        )
        self.assertFalse(resultado["uso_base"])
        self.assertEqual(resultado["pesos"], {"1": 100000.0, "2": 50000.0})
        self.assertEqual(resultado["montos"], {"1": 57000.0, "2": 28000.0})

    def test_directo_base_usa_montos_actuales(self):
        resultado = distribuir_monto_por_deuda(
            deudas=["1", "2"],
            montos_actuales={"1": 100000, "2": 50000},
            monto_total=85000,
            aliado="Directo Base",
            masivas_df=pd.DataFrame([
                {"Id_Deuda": "1", "Casa_Cobro": "Aliado A", "PaB_Propuesta": 55000, "PaB_Portafolio": None},
                {"Id_Deuda": "2", "Casa_Cobro": "Aliado A", "PaB_Propuesta": 30000, "PaB_Portafolio": None},
            ]),
        )
        self.assertFalse(resultado["uso_base"])
        self.assertEqual(resultado["pesos"], {"1": 100000.0, "2": 50000.0})


class TestDescuentoOptimoYValidaciones(unittest.TestCase):
    def test_descuento_optimo_tradicional(self):
        saldos = {"Saldos": {"REF": 1000.0}, "PorCobrar": {"REF": 600.0}}
        with patch("modules.forms.load_client_balances", return_value=saldos):
            descuento = obtener_descuento_optimo_tradicional(
                referencia="REF",
                pricing=0.2,
                pago_total_original=500.0,
                descuento_pl=0.15,
            )
        self.assertAlmostEqual(descuento, 0.2624671916, places=8)

    def test_descuento_optimo_tradicional_respeta_piso(self):
        saldos = {"Saldos": {"REF": 1000.0}, "PorCobrar": {"REF": 100.0}}
        with patch("modules.forms.load_client_balances", return_value=saldos):
            descuento = obtener_descuento_optimo_tradicional(
                referencia="REF",
                pricing=0.2,
                pago_total_original=500.0,
                descuento_pl=0.15,
            )
        self.assertEqual(descuento, 0.15)

    def test_descuento_optimo_tradicional_respeta_techo(self):
        saldos = {"Saldos": {"REF": 0.0}, "PorCobrar": {"REF": 1000.0}}
        with patch("modules.forms.load_client_balances", return_value=saldos):
            descuento = obtener_descuento_optimo_tradicional(
                referencia="REF",
                pricing=0.2,
                pago_total_original=10.0,
                descuento_pl=0.15,
            )
        self.assertEqual(descuento, 1.0)

    def test_descuento_optimo_credito(self):
        saldos = {"Saldos": {"REF": 100.0}, "PorCobrar": {"REF": 50.0}}
        pab_ideal = {"D1": 100.0, "D2": 100.0}
        with patch("modules.forms.load_client_balances", return_value=saldos), patch(
            "modules.forms.load_pab_ideal", return_value=pab_ideal
        ):
            descuento = obtener_descuento_optimo_credito(
                referencia="REF",
                deudas=["D1", "D2"],
                pago_total_original=500.0,
            )
        self.assertEqual(descuento, 0.5)

    def test_descuento_optimo_credito_sin_pab_ideal(self):
        saldos = {"Saldos": {"REF": 100.0}, "PorCobrar": {"REF": 50.0}}
        with patch("modules.forms.load_client_balances", return_value=saldos), patch(
            "modules.forms.load_pab_ideal", return_value={"D1": 100.0}
        ):
            descuento = obtener_descuento_optimo_credito(
                referencia="REF",
                deudas=["D1", "DX"],
                pago_total_original=500.0,
            )
        self.assertEqual(descuento, 1)

    def test_descuento_optimo_credito_respeta_piso(self):
        saldos = {"Saldos": {"REF": 1000.0}, "PorCobrar": {"REF": 600.0}}
        pab_ideal = {"D1": 200.0, "D2": 200.0}
        with patch("modules.forms.load_client_balances", return_value=saldos), patch(
            "modules.forms.load_pab_ideal", return_value=pab_ideal
        ):
            descuento = obtener_descuento_optimo_credito(
                referencia="REF",
                deudas=["D1", "D2"],
                pago_total_original=500.0,
            )
        self.assertEqual(descuento, 0.15)

    def test_descuento_optimo_general_elige_el_menor(self):
        saldos = {"Saldos": {"REF": 1000.0}, "PorCobrar": {"REF": 600.0}}
        pab_ideal = {"D1": 200.0, "D2": 200.0}
        with patch("modules.forms.load_client_balances", return_value=saldos), patch(
            "modules.forms.load_pab_ideal", return_value=pab_ideal
        ):
            descuento, tipo = obtener_descuento_optimo(
                referencia="REF",
                deudas=["D1", "D2"],
                pricing=0.2,
                pago_total_original=500.0,
                descuento_pl=0.15,
            )
        self.assertEqual(descuento, 0.15)
        self.assertEqual(tipo, "Crédito - PaB Ideal")

    def test_alertar_excedencia_contrapropuesta(self):
        self.assertEqual(
            alertar_excedencia_contraprop_max_relativa(
                contraprop_max_relativa=None,
                descuento_propuesto=0.2,
            )[0],
            False,
        )
        self.assertEqual(
            alertar_excedencia_contraprop_max_relativa(
                contraprop_max_relativa=0.1,
                descuento_propuesto=0.2,
            )[0],
            True,
        )
        self.assertEqual(
            alertar_excedencia_contraprop_max_relativa(
                contraprop_max_relativa=0.2,
                descuento_propuesto=0.2,
            )[0],
            False,
        )

    def test_validar_descuento_base_individual(self):
        def descuento_base(deuda, portafolio=False):
            return np.nan if portafolio else 500.0

        with patch("modules.forms.obtener_descuento_base", side_effect=descuento_base):
            cumple, _ = validar_descuento_base(
                deuda="D1",
                deudas_info={"D1": 400.0},
            )
        self.assertTrue(cumple)

        with patch("modules.forms.obtener_descuento_base", side_effect=descuento_base):
            cumple, mensaje = validar_descuento_base(
                deuda="D1",
                deudas_info={"D1": 600.0},
            )
        self.assertFalse(cumple)
        self.assertIn("Pago Base", mensaje)

    def test_validar_descuento_base_portafolio(self):
        def descuento_base(deuda, portafolio=False):
            return 1000.0 if portafolio else 500.0

        with patch("modules.forms.obtener_descuento_base", side_effect=descuento_base), patch(
            "modules.forms.obtener_deudas_portafolio_masivas",
            return_value=["D1", "D2"],
        ):
            cumple, _ = validar_descuento_base(
                deuda="D1",
                deudas_info={"D1": 400.0, "D2": 500.0},
            )
            self.assertTrue(cumple)

            cumple, mensaje = validar_descuento_base(
                deuda="D1",
                deudas_info={"D1": 600.0, "D2": 500.0},
            )
            self.assertFalse(cumple)
            self.assertIn("Portafolio", mensaje)

            # Si no están todas las deudas del portafolio, no se aplica esa
            # restricción y se valida solo el descuento individual.
            cumple, _ = validar_descuento_base(
                deuda="D1",
                deudas_info={"D1": 400.0},
            )
            self.assertTrue(cumple)

    def test_sin_descuento_base_no_restringe(self):
        with patch("modules.forms.obtener_descuento_base", return_value=np.nan):
            cumple, _ = validar_descuento_base(
                deuda="D1",
                deudas_info={"D1": 999999.0},
            )
        self.assertTrue(cumple)

    def test_nombre_corto_negociador(self):
        self.assertEqual(
            _obtener_nombre_corto_negociador("Juan Pablo Perez Gomez"),
            "Juan Perez",
        )
        self.assertEqual(_obtener_nombre_corto_negociador("Juan Perez"), "Juan Perez")
        self.assertEqual(_obtener_nombre_corto_negociador(float("nan")), "")


class TestNormalizacionBancos(unittest.TestCase):
    def test_normalizar_banco_individual(self):
        self.assertEqual(normalizar_banco("Qnt Bancolombia"), "Bancolombia")
        self.assertEqual(normalizar_banco("Nu Bank"), "Nubank")
        self.assertEqual(normalizar_banco("Banco Falabella Casa De Cobro"), "Banco Falabella")
        self.assertEqual(normalizar_banco("Banco Desconocido"), "Banco Desconocido")

    def test_normalizar_bancos_vectorizado_conserva_indices(self):
        serie = pd.Series(
            ["Bancolombia", "Nu Bank", "Banco Desconocido"],
            index=["a", "b", "c"],
        )
        resultado = normalizar_bancos_vectorizado(serie)
        self.assertEqual(resultado.to_dict(), {
            "a": "Bancolombia",
            "b": "Nubank",
            "c": "Banco Desconocido",
        })


if __name__ == "__main__":
    unittest.main()
