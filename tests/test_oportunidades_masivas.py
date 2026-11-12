# Estándar usando Pep8
# Librerías de Python
import time
import unittest
# Librerías de Terceros
import pandas as pd
# Librerías Locales
from modules.oportunidades import (
    _aplicar_pago_unidades,
    _construir_fechas_metabase_acuerdos,
    _construir_unidades_actualizaciones,
    _deduplicar_actualizaciones,
    _resolver_pab_actualizado_actualizaciones,
    calcular_oportunidades_masivas_datos,
    seleccionar_descuentos_masivas,
)
from modules.constants import (
    LLAVE_REDIRECCION_CALCULADORA,
)
from ui.calculadora_masiva_components import (
    _calcular_slice_pagina,
    _formatear_valor_oportunidad_masiva,
    _normalizar_pagina_actual,
    _oportunidades_de_bloque,
    _preparar_estado_redireccion_individual,
    filtrar_oportunidades_masivas,
)
from utils.helpers_general import escapar_dolar_markdown

HOY = pd.Timestamp("2026-11-11")

# Función Auxiliar para Construir la Asignación de Cartera de Prueba
def _asignacion(registros: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(registros)

# Función Auxiliar para Construir una Masiva de Prueba
def _masiva(
    *,
    id_deuda: str,
    pab: float,
    fecha_limite: object = pd.Timestamp("2026-12-31"),
    casa: str = "ALIADO",
    fecha_masiva: object = pd.Timestamp("2026-11-01"),
    fila: int = 2,
    id_portafolio: str = "",
    pab_portafolio: object = None,
    es_portafolio: bool = False,
) -> dict:
    metadata = {"Fecha_Limite_Uso": fecha_limite} if fecha_limite is not None else {}
    if id_portafolio:
        metadata["Id_Portafolio"] = id_portafolio
    if pab_portafolio is not None:
        metadata["PaB_Portafolio"] = pab_portafolio
    return {
        "Id_Deuda": id_deuda,
        "PaB_Propuesta": pab,
        "Metadata": metadata or None,
        "Fecha_Masiva": fecha_masiva,
        "Casa_Cobro": casa,
        "Es_Portafolio": es_portafolio,
        "Fila_Sheets": fila,
    }

# Función Auxiliar para Construir los Insumos Completos del Cálculo
def _calcular(
    *,
    asignacion: pd.DataFrame,
    masivas: pd.DataFrame,
    pab_ideal: dict | None = None,
    saldos: dict | None = None,
    prospectos_credito: dict | None = None,
    prospectos_tradicional: pd.DataFrame | None = None,
    pipeline_credito: pd.DataFrame | None = None,
    liquidaciones: set | None = None,
    solicitudes_df: pd.DataFrame | None = None,
    actualizaciones_df: pd.DataFrame | None = None,
    solo_masivas: bool = True,
    incluir_acuerdos_robo: bool = False,
    fechas_metabase: dict | None = None,
) -> pd.DataFrame:
    return calcular_oportunidades_masivas_datos(
        asignacion_df=asignacion,
        masivas_df=masivas,
        pab_ideal=pab_ideal or {},
        saldos=saldos or {"Saldos": {}, "PorCobrar": {}},
        prospectos_credito=prospectos_credito or {},
        prospectos_tradicional=prospectos_tradicional if prospectos_tradicional is not None else pd.DataFrame(),
        pipeline_credito=pipeline_credito if pipeline_credito is not None else pd.DataFrame(),
        liquidaciones=liquidaciones or set(),
        solicitudes_df=solicitudes_df,
        actualizaciones_df=actualizaciones_df,
        solo_masivas=solo_masivas,
        incluir_acuerdos_robo=incluir_acuerdos_robo,
        fechas_metabase=fechas_metabase,
        hoy=HOY,
    )


class TestSeleccionDescuentosMasivas(unittest.TestCase):
    def test_toma_el_mejor_descuento_vigente(self):
        masivas = pd.DataFrame([
            _masiva(id_deuda="D1", pab=40_000_000, fecha_limite=pd.Timestamp("2020-01-01")),
            _masiva(id_deuda="D1", pab=60_000_000),
            _masiva(id_deuda="D1", pab=50_000_000),
            _masiva(id_deuda="D1", pab=70_000_000, fecha_limite=None),
            _masiva(id_deuda="D1", pab=0),
            _masiva(id_deuda="D2", pab=30_000_000, fecha_limite=pd.Timestamp("2020-01-01")),
        ])
        seleccion = seleccionar_descuentos_masivas(masivas_df=masivas, hoy=HOY)

        self.assertEqual(len(seleccion), 1)
        self.assertEqual(seleccion.iloc[0]["Id_Deuda"], "D1")
        self.assertEqual(seleccion.iloc[0]["PaB_Propuesta"], 50_000_000)

    def test_empate_prioriza_la_masiva_mas_reciente(self):
        masivas = pd.DataFrame([
            _masiva(
                id_deuda="D1", pab=50_000_000, casa="VIEJA",
                fecha_masiva=pd.Timestamp("2026-10-01"), fila=2,
            ),
            _masiva(
                id_deuda="D1", pab=50_000_000, casa="NUEVA",
                fecha_masiva=pd.Timestamp("2026-11-01"), fila=3,
            ),
        ])
        seleccion = seleccionar_descuentos_masivas(masivas_df=masivas, hoy=HOY)

        self.assertEqual(seleccion.iloc[0]["Casa_Cobro"], "NUEVA")


class TestCalculoMasivoTradicional(unittest.TestCase):
    def _datos(self):
        asignacion = _asignacion([
            {
                "Referencia": "REF-TRAD",
                "Nombre_Cliente": "Cliente Tradicional",
                "Banco": "BBVA Colombia",
                "Id_Deuda": "D1",
                "PaB_Origen": 100_000_000.0,
                "Negociador": "Nego A",
                "Descuento_Esperado": 0.5,
                "Apartado_Neto": 10_000_000.0,
                "Pricing": 0.15,
            },
        ])
        masivas = pd.DataFrame([_masiva(id_deuda="D1", pab=60_000_000)])
        prospectos = pd.DataFrame([{
            "Referencia": "REF-TRAD",
            "Id_Deuda": "D1",
            "Prospecto": "Trad 1",
            "Prob_Liq": 0.6,
        }])
        return asignacion, masivas, prospectos

    def test_calcula_oportunidades_tradicionales(self):
        asignacion, masivas, prospectos = self._datos()
        resultado = _calcular(
            asignacion=asignacion,
            masivas=masivas,
            saldos={"Saldos": {"REF-TRAD": 50_000_000}, "PorCobrar": {"REF-TRAD": 5_000_000}},
            prospectos_credito={"REF-TRAD": "Tradicional"},
            prospectos_tradicional=prospectos,
        )

        self.assertEqual(len(resultado), 1)
        fila = resultado.iloc[0]
        self.assertTrue(bool(fila["Tradicional_Habilitado"]))
        self.assertFalse(bool(fila["Credito_Habilitado"]))
        self.assertAlmostEqual(float(fila["Descuento_Actual"]), 0.4)
        self.assertAlmostEqual(float(fila["Trad_Deposito_Extra_Valor"]), 22_160_000)
        self.assertTrue(bool(fila["Trad_Deposito_Extra_Aplica"]))
        self.assertTrue(bool(fila["Trad_Contraoferta_Aplica"]))
        self.assertFalse(bool(fila["Trad_Liq_Insta_Aplica"]))
        self.assertIn("Depósito Extra", fila["Oportunidades"])
        self.assertIn("ContraOferta Viable", fila["Oportunidades"])
        self.assertIn("IA Liquidadora", fila["Oportunidades"])
        self.assertEqual(int(fila["Num_Oportunidades"]), 3)
        self.assertEqual(len(fila["Deudas_Detalle"]), 1)
        self.assertIn("Prospecto Tradicional", fila["Credito_Detalle"])

    def test_prospecto_tradicional_no_permite_credito(self):
        asignacion, masivas, prospectos = self._datos()
        pipeline = pd.DataFrame([{
            "Referencia": "REF-TRAD",
            "Fecha_Subida": pd.Timestamp("2026-10-01"),
            "Status_Credito": "CERRADO",
            "No_Opta_Credito": False,
            "Rechazo_Credito": False,
        }])
        resultado = _calcular(
            asignacion=asignacion,
            masivas=masivas,
            pab_ideal={"D1": 80_000_000},
            saldos={"Saldos": {"REF-TRAD": 50_000_000}, "PorCobrar": {"REF-TRAD": 5_000_000}},
            prospectos_credito={"REF-TRAD": "Tradicional"},
            prospectos_tradicional=prospectos,
            pipeline_credito=pipeline,
        )

        self.assertFalse(bool(resultado.iloc[0]["Credito_Habilitado"]))
        self.assertIn("Prospecto Tradicional", resultado.iloc[0]["Credito_Detalle"])


class TestCalculoMasivoCredito(unittest.TestCase):
    def _datos(self, prospecto: str = "Batch 1", status: str = "CERRADO"):
        asignacion = _asignacion([
            {
                "Referencia": "REF-CRED",
                "Nombre_Cliente": "Cliente Crédito",
                "Banco": "BBVA Colombia",
                "Id_Deuda": "D1",
                "PaB_Origen": 100_000_000.0,
                "Negociador": "Nego B",
                "Descuento_Esperado": 0.5,
                "Apartado_Neto": 20_000_000.0,
                "Pricing": 0.15,
            },
            {
                "Referencia": "REF-CRED",
                "Nombre_Cliente": "Cliente Crédito",
                "Banco": "Itaú",
                "Id_Deuda": "D2",
                "PaB_Origen": 50_000_000.0,
                "Negociador": "Nego B",
                "Descuento_Esperado": 0.4,
                "Apartado_Neto": 20_000_000.0,
                "Pricing": 0.15,
            },
        ])
        masivas = pd.DataFrame([
            _masiva(id_deuda="D1", pab=60_000_000),
            _masiva(id_deuda="D2", pab=30_000_000),
        ])
        pipeline = pd.DataFrame([{
            "Referencia": "REF-CRED",
            "Fecha_Subida": pd.Timestamp("2026-10-01"),
            "Status_Credito": status,
            "No_Opta_Credito": status in {"NO_PERFILA", "NO_VIABLE_MEC", "DTO_INSUFICIENTE"},
            "Rechazo_Credito": status == "NO_LE_INTERESA",
        }])
        return asignacion, masivas, pipeline, prospecto

    def test_credito_usa_solo_deudas_con_pab_ideal(self):
        asignacion, masivas, pipeline, prospecto = self._datos()
        resultado = _calcular(
            asignacion=asignacion,
            masivas=masivas,
            pab_ideal={"D1": 80_000_000},
            saldos={"Saldos": {"REF-CRED": 80_000_000}, "PorCobrar": {"REF-CRED": 5_000_000}},
            prospectos_credito={"REF-CRED": prospecto},
            pipeline_credito=pipeline,
        )

        fila = resultado.iloc[0]
        self.assertTrue(bool(fila["Tradicional_Habilitado"]))
        self.assertTrue(bool(fila["Credito_Habilitado"]))
        self.assertAlmostEqual(float(fila["PaB_Origen_Total"]), 150_000_000)
        self.assertAlmostEqual(float(fila["PaB_Actualizado_Total"]), 90_000_000)
        self.assertAlmostEqual(float(fila["Cred_PaB_Origen_Total"]), 100_000_000)
        self.assertAlmostEqual(float(fila["Cred_PaB_Actualizado_Total"]), 60_000_000)
        self.assertAlmostEqual(float(fila["Cred_PaB_Ideal_Total"]), 80_000_000)
        self.assertAlmostEqual(float(fila["Cred_Deposito_Extra_Valor"]), -19_980_000)
        self.assertTrue(bool(fila["Cred_Liq_Insta_Aplica"]))
        self.assertIn("1 de 2", fila["Credito_Detalle"])
        self.assertIn("sin PaB Ideal", fila["Credito_Detalle"])

        detalles = {d["Id_Deuda"]: d for d in fila["Deudas_Detalle"]}
        self.assertEqual(len(detalles), 2)
        self.assertTrue(detalles["D1"]["Usa_Tradicional"])
        self.assertTrue(detalles["D1"]["Usa_Credito"])
        self.assertTrue(detalles["D2"]["Usa_Tradicional"])
        self.assertFalse(detalles["D2"]["Usa_Credito"])

    def test_cr_parcial_solo_permite_credito(self):
        asignacion, masivas, pipeline, _ = self._datos(prospecto="Cr Parcial")
        resultado = _calcular(
            asignacion=asignacion,
            masivas=masivas,
            pab_ideal={"D1": 80_000_000},
            saldos={"Saldos": {"REF-CRED": 80_000_000}, "PorCobrar": {"REF-CRED": 5_000_000}},
            prospectos_credito={"REF-CRED": "Cr Parcial"},
            pipeline_credito=pipeline,
        )

        fila = resultado.iloc[0]
        self.assertFalse(bool(fila["Tradicional_Habilitado"]))
        self.assertTrue(bool(fila["Credito_Habilitado"]))
        self.assertEqual(fila["Tipos_Analisis"], ["Crédito"])
        self.assertFalse(bool(fila["Trad_Deposito_Extra_Aplica"]))

    def test_estado_no_apto_desactiva_credito(self):
        asignacion, masivas, pipeline, _ = self._datos(
            prospecto="Cr Parcial", status="NO_VIABLE_MEC"
        )
        resultado = _calcular(
            asignacion=asignacion,
            masivas=masivas,
            pab_ideal={"D1": 80_000_000},
            saldos={"Saldos": {"REF-CRED": 80_000_000}, "PorCobrar": {"REF-CRED": 5_000_000}},
            prospectos_credito={"REF-CRED": "Cr Parcial"},
            pipeline_credito=pipeline,
        )

        fila = resultado.iloc[0]
        self.assertFalse(bool(fila["Credito_Viable"]))
        self.assertFalse(bool(fila["Credito_Habilitado"]))
        self.assertEqual(fila["Tipos_Analisis"], [])
        self.assertIn("no opta a Crédito", fila["Credito_Detalle"])

    def test_sin_pipeline_si_es_viable(self):
        asignacion, masivas, _, _ = self._datos(prospecto="Batch 1")
        resultado = _calcular(
            asignacion=asignacion,
            masivas=masivas,
            pab_ideal={"D1": 80_000_000},
            saldos={"Saldos": {"REF-CRED": 80_000_000}, "PorCobrar": {"REF-CRED": 5_000_000}},
            prospectos_credito={"REF-CRED": "Batch 1"},
            pipeline_credito=pd.DataFrame(),
        )

        fila = resultado.iloc[0]
        self.assertTrue(bool(fila["Credito_Viable"]))
        self.assertTrue(bool(fila["Credito_Habilitado"]))
        self.assertEqual(fila["Tipos_Analisis"], ["Tradicional", "Crédito"])
        self.assertIn("Sin registro en el Pipeline", fila["Credito_Detalle"])
        self.assertIn("se analiza por Crédito", fila["Credito_Detalle"])

    def test_cr_parcial_sin_pipeline_si_analiza_credito(self):
        asignacion, masivas, _, _ = self._datos(prospecto="Cr Parcial")
        resultado = _calcular(
            asignacion=asignacion,
            masivas=masivas,
            pab_ideal={"D1": 80_000_000},
            saldos={"Saldos": {"REF-CRED": 80_000_000}, "PorCobrar": {"REF-CRED": 5_000_000}},
            prospectos_credito={"REF-CRED": "Cr Parcial"},
            pipeline_credito=pd.DataFrame(),
        )

        fila = resultado.iloc[0]
        self.assertTrue(bool(fila["Credito_Viable"]))
        self.assertTrue(bool(fila["Credito_Habilitado"]))
        self.assertFalse(bool(fila["Tradicional_Habilitado"]))
        self.assertEqual(fila["Tipos_Analisis"], ["Crédito"])


class TestSoloMasivas(unittest.TestCase):
    def _datos(self):
        asignacion = _asignacion([
            {
                "Referencia": "REF-MIX",
                "Nombre_Cliente": "Cliente Mix",
                "Banco": "BBVA Colombia",
                "Id_Deuda": "D1",
                "PaB_Origen": 100_000_000.0,
                "Negociador": "Nego C",
                "Descuento_Esperado": 0.5,
                "Apartado_Neto": 10_000_000.0,
                "Pricing": 0.15,
            },
            {
                "Referencia": "REF-MIX",
                "Nombre_Cliente": "Cliente Mix",
                "Banco": "Itaú",
                "Id_Deuda": "D2",
                "PaB_Origen": 50_000_000.0,
                "Negociador": "Nego C",
                "Descuento_Esperado": 0.4,
                "Apartado_Neto": 10_000_000.0,
                "Pricing": 0.15,
            },
            {
                "Referencia": "REF-NOMASIVA",
                "Nombre_Cliente": "Cliente Sin Masiva",
                "Banco": "Banco Popular",
                "Id_Deuda": "D3",
                "PaB_Origen": 50_000_000.0,
                "Negociador": "Nego C",
                "Descuento_Esperado": 0.3,
                "Apartado_Neto": 10_000_000.0,
                "Pricing": 0.15,
            },
        ])
        masivas = pd.DataFrame([_masiva(id_deuda="D1", pab=60_000_000)])
        return asignacion, masivas

    def test_activo_solo_analiza_deudas_con_masiva(self):
        asignacion, masivas = self._datos()
        resultado = _calcular(
            asignacion=asignacion,
            masivas=masivas,
            prospectos_credito={"REF-MIX": "Tradicional", "REF-NOMASIVA": "Tradicional"},
            solo_masivas=True,
        )

        self.assertNotIn("REF-NOMASIVA", resultado["Referencia"].tolist())
        fila = resultado[resultado["Referencia"] == "REF-MIX"].iloc[0]
        self.assertEqual(int(fila["Deudas_Analizadas"]), 1)
        self.assertAlmostEqual(float(fila["PaB_Origen_Total"]), 100_000_000)
        self.assertAlmostEqual(float(fila["PaB_Actualizado_Total"]), 60_000_000)
        self.assertAlmostEqual(float(fila["Descuento_Actual"]), 0.4)

    def test_inactivo_incluye_deudas_sin_masiva_con_pab_origen(self):
        asignacion, masivas = self._datos()
        resultado = _calcular(
            asignacion=asignacion,
            masivas=masivas,
            prospectos_credito={"REF-MIX": "Tradicional", "REF-NOMASIVA": "Tradicional"},
            solo_masivas=False,
        )

        fila = resultado[resultado["Referencia"] == "REF-MIX"].iloc[0]
        self.assertEqual(int(fila["Deudas_Analizadas"]), 2)
        self.assertAlmostEqual(float(fila["PaB_Origen_Total"]), 150_000_000)
        # Sin Actualizaciones y con los bancos BBVA/Itaú en BANCOS_PORTAFOLIO,
        # las dos deudas forman un portafolio sin descuento (PaB = Origen).
        self.assertAlmostEqual(float(fila["PaB_Actualizado_Total"]), 150_000_000)
        self.assertAlmostEqual(float(fila["Descuento_Actual"]), 0.0)
        # Sin Actualizaciones, cada banco de BANCOS_PORTAFOLIO forma su propio
        # grupo. Como D1 y D2 están en bancos distintos y cada grupo tiene una
        # sola deuda, ambas quedan como unidades individuales.
        self.assertEqual(len(fila["Portafolios_Detalle"]), 2)
        self.assertTrue(
            all(
                unidad["Tipo_Unidad"] == "Deuda individual"
                for unidad in fila["Portafolios_Detalle"]
            )
        )

        fila_sin = resultado[resultado["Referencia"] == "REF-NOMASIVA"].iloc[0]
        self.assertAlmostEqual(float(fila_sin["PaB_Actualizado_Total"]), 50_000_000)
        self.assertAlmostEqual(float(fila_sin["Descuento_Actual"]), 0.0)

    def test_deudas_liquidadas_no_se_analizan(self):
        asignacion, masivas = self._datos()
        resultado = _calcular(
            asignacion=asignacion,
            masivas=masivas,
            prospectos_credito={"REF-MIX": "Tradicional"},
            liquidaciones={"D1"},
            solo_masivas=False,
        )

        fila = resultado[resultado["Referencia"] == "REF-MIX"].iloc[0]
        self.assertEqual(int(fila["Deudas_Analizadas"]), 1)
        self.assertAlmostEqual(float(fila["PaB_Origen_Total"]), 50_000_000)
        self.assertAlmostEqual(float(fila["PaB_Actualizado_Total"]), 50_000_000)
        self.assertTrue(bool(fila["Tiene_Deudas_Liquidaciones"]))

    def test_pab_masiva_mayor_al_origen_se_acota(self):
        asignacion, _ = self._datos()
        masivas = pd.DataFrame([_masiva(id_deuda="D1", pab=150_000_000)])
        resultado = _calcular(
            asignacion=asignacion[asignacion["Referencia"] == "REF-MIX"],
            masivas=masivas,
            prospectos_credito={"REF-MIX": "Tradicional"},
            solo_masivas=True,
        )

        fila = resultado.iloc[0]
        self.assertAlmostEqual(float(fila["PaB_Actualizado_Total"]), 100_000_000)
        self.assertAlmostEqual(float(fila["Descuento_Actual"]), 0.0)


class TestAcuerdosRoboMasivos(unittest.TestCase):
    def _datos(self):
        asignacion = _asignacion([{
            "Referencia": "REF-ROBO",
            "Nombre_Cliente": "Cliente Robo",
            "Banco": "BBVA Colombia",
            "Id_Deuda": "D1",
            "PaB_Origen": 100_000_000.0,
            "Negociador": "Nego D",
            "Descuento_Esperado": 0.5,
            "Apartado_Neto": 10_000_000.0,
            "Pricing": 0.15,
        }])
        masivas = pd.DataFrame([_masiva(id_deuda="D1", pab=60_000_000)])
        actualizaciones = pd.DataFrame([{
            "Id_Deuda": "D1",
            "Fecha_Act": pd.Timestamp("2020-01-01"),
            "Etiqueta_Act": "ACUERDO",
            "Correo": "a@x.com",
        }])
        solicitudes = pd.DataFrame([{
            "Estado_Solicitud": "Exitosa",
            "Tipo_Solicitud": "Acuerdo de Pago",
            "Fecha_Limite_Pago": pd.Timestamp("2020-01-15"),
            "Fecha_Respuesta": pd.Timestamp("2020-01-01"),
            "Timestamp": pd.Timestamp("2020-01-01"),
            "Ids_Deuda": "D1",
            "Datos_Solicitud": [],
            "JSON_Respuesta": [],
            "Es_Historico": False,
        }])
        return asignacion, masivas, actualizaciones, solicitudes

    def test_acuerdo_de_alianza_vencido_es_robo(self):
        asignacion, masivas, actualizaciones, solicitudes = self._datos()
        resultado = _calcular(
            asignacion=asignacion,
            masivas=masivas,
            prospectos_credito={"REF-ROBO": "Tradicional"},
            actualizaciones_df=actualizaciones,
            solicitudes_df=solicitudes,
            incluir_acuerdos_robo=True,
        )

        fila = resultado.iloc[0]
        self.assertTrue(bool(fila["Acuerdo_Robo_Aplica"]))
        self.assertEqual(int(fila["Acuerdo_Robo_Deudas"]), 1)
        self.assertIn("15/01/2020", fila["Acuerdo_Robo_Detalle"])

    def test_metabase_sin_fecha_se_reporta(self):
        asignacion, masivas, actualizaciones, _ = self._datos()
        resultado = _calcular(
            asignacion=asignacion,
            masivas=masivas,
            prospectos_credito={"REF-ROBO": "Tradicional"},
            actualizaciones_df=actualizaciones,
            solicitudes_df=pd.DataFrame(),
            incluir_acuerdos_robo=True,
            fechas_metabase={"D1": pd.NaT},
        )

        fila = resultado.iloc[0]
        self.assertTrue(bool(fila["Acuerdo_Robo_Aplica"]))
        self.assertIn("Sin fecha", fila["Acuerdo_Robo_Detalle"])

    def test_metabase_con_error_no_es_oportunidad(self):
        asignacion, masivas, actualizaciones, _ = self._datos()
        resultado = _calcular(
            asignacion=asignacion,
            masivas=masivas,
            prospectos_credito={"REF-ROBO": "Tradicional"},
            actualizaciones_df=actualizaciones,
            solicitudes_df=pd.DataFrame(),
            incluir_acuerdos_robo=True,
            fechas_metabase={},
        )

        self.assertFalse(bool(resultado.iloc[0]["Acuerdo_Robo_Aplica"]))

    def test_gestion_posterior_no_es_oportunidad(self):
        asignacion, masivas, actualizaciones, solicitudes = self._datos()
        actualizaciones = pd.concat([
            actualizaciones,
            pd.DataFrame([{
                "Id_Deuda": "D1",
                "Fecha_Act": pd.Timestamp("2020-01-02"),
                "Etiqueta_Act": "LLAMADA",
                "Correo": "a@x.com",
            }]),
        ], ignore_index=True)
        resultado = _calcular(
            asignacion=asignacion,
            masivas=masivas,
            prospectos_credito={"REF-ROBO": "Tradicional"},
            actualizaciones_df=actualizaciones,
            solicitudes_df=solicitudes,
            incluir_acuerdos_robo=True,
        )

        self.assertFalse(bool(resultado.iloc[0]["Acuerdo_Robo_Aplica"]))


class TestVencimientosMetabaseBatch(unittest.TestCase):
    def test_toma_la_maxima_fecha_por_deuda_y_correo(self):
        vencimientos = pd.DataFrame([
            {
                "Id_Deuda": "D1", "Correo_Act": "a@x.com",
                "Etiqueta_Act": "agreement",
                "Fecha_Expiracion": pd.Timestamp("2020-01-01"),
            },
            {
                "Id_Deuda": "D1", "Correo_Act": "a@x.com",
                "Etiqueta_Act": "agreement",
                "Fecha_Expiracion": pd.Timestamp("2020-02-01"),
            },
            {
                "Id_Deuda": "D1", "Correo_Act": "otro@x.com",
                "Etiqueta_Act": "agreement",
                "Fecha_Expiracion": pd.Timestamp("2099-01-01"),
            },
        ])
        fechas = _construir_fechas_metabase_acuerdos(
            vencimientos_df=vencimientos,
            pendientes=[
                {"Id_Deuda": "D1", "Correo": "a@x.com"},
                {"Id_Deuda": "D2", "Correo": "a@x.com"},
            ],
        )

        self.assertEqual(fechas["D1"], pd.Timestamp("2020-02-01"))
        self.assertTrue(pd.isna(fechas["D2"]))

    def test_sin_datos_no_construye_fechas(self):
        self.assertEqual(
            _construir_fechas_metabase_acuerdos(
                vencimientos_df=pd.DataFrame(),
                pendientes=[{"Id_Deuda": "D1", "Correo": "a@x.com"}],
            ),
            {},
        )
        self.assertEqual(
            _construir_fechas_metabase_acuerdos(
                vencimientos_df=None,
                pendientes=[{"Id_Deuda": "D1", "Correo": "a@x.com"}],
            ),
            {},
        )


class TestBloqueOportunidadesUI(unittest.TestCase):
    def test_construye_bloque_tradicional(self):
        fila = pd.Series({
            "Trad_Deposito_Extra_Aplica": True,
            "Trad_Deposito_Extra_Valor": 100_000,
            "Trad_Deposito_Extra_Detalle": "detalle depósito",
            "Trad_Contraoferta_Aplica": False,
            "Trad_Liq_Insta_Aplica": True,
            "Trad_Descuento_Actual": 0.4,
            "Trad_Liq_Insta_Detalle": "detalle liquidación",
        })
        oportunidades = _oportunidades_de_bloque(
            fila=fila,
            prefijo="Trad",
            nombres=["Depósito Extra", "ContraOferta Viable", "Liquidación Instantánea"],
        )

        self.assertEqual([o[0] for o in oportunidades], ["Depósito Extra", "Liquidación Instantánea"])
        self.assertEqual(oportunidades[0][1], 100_000)
        self.assertAlmostEqual(oportunidades[1][1], 0.4)
        self.assertEqual(oportunidades[1][2], "detalle liquidación")


class TestFiltrosMasivos(unittest.TestCase):
    def _resultado(self) -> pd.DataFrame:
        return pd.DataFrame([
            {
                "Referencia": "REF-A", "Nombre_Cliente": "Ana", "Negociador": "Nego A",
                "Prospecto_Credito": "Batch 1", "Tradicional_Habilitado": True,
                "Credito_Habilitado": True, "Num_Oportunidades": 2,
                "Oportunidades": ["Depósito Extra", "IA Liquidadora"], "Es_Viable": True,
                "Descuento_Actual": 0.4, "PaB_Origen_Total": 100_000_000,
                "Ahorro_Neto": 45_000_000, "Tiene_Deudas_Liquidaciones": False,
                "Ingreso_Actual": 30_000_000,
            },
            {
                "Referencia": "REF-B", "Nombre_Cliente": "Bruno", "Negociador": "Nego B",
                "Prospecto_Credito": "Tradicional", "Tradicional_Habilitado": True,
                "Credito_Habilitado": False, "Num_Oportunidades": 1,
                "Oportunidades": ["ContraOferta Viable"], "Es_Viable": False,
                "Descuento_Actual": 0.2, "PaB_Origen_Total": 50_000_000,
                "Ahorro_Neto": 10_000_000, "Tiene_Deudas_Liquidaciones": True,
                "Ingreso_Actual": 5_000_000,
            },
            {
                "Referencia": "REF-C", "Nombre_Cliente": "Carla", "Negociador": "Nego A",
                "Prospecto_Credito": "Cr Parcial", "Tradicional_Habilitado": False,
                "Credito_Habilitado": True, "Num_Oportunidades": 0,
                "Oportunidades": [], "Es_Viable": True,
                "Descuento_Actual": 0.6, "PaB_Origen_Total": 150_000_000,
                "Ahorro_Neto": 0, "Tiene_Deudas_Liquidaciones": False,
                "Ingreso_Actual": 60_000_000,
            },
        ])

    def test_busqueda_y_oportunidad(self):
        resultado = filtrar_oportunidades_masivas(
            self._resultado(), busqueda="ana", solo_con_oportunidades=False
        )
        self.assertEqual(resultado["Referencia"].tolist(), ["REF-A"])

        resultado = filtrar_oportunidades_masivas(
            self._resultado(), oportunidades=["IA Liquidadora"]
        )
        self.assertEqual(resultado["Referencia"].tolist(), ["REF-A"])

    def test_tipo_analisis_y_viabilidad(self):
        resultado = filtrar_oportunidades_masivas(
            self._resultado(), tipo_analisis="Crédito", solo_con_oportunidades=False,
            orden="Referencia (A-Z)",
        )
        self.assertEqual(resultado["Referencia"].tolist(), ["REF-A", "REF-C"])

        resultado = filtrar_oportunidades_masivas(
            self._resultado(), solo_viables=True, orden="Referencia (A-Z)"
        )
        self.assertEqual(resultado["Referencia"].tolist(), ["REF-A"])

    def test_rangos_y_liquidaciones(self):
        resultado = filtrar_oportunidades_masivas(
            self._resultado(),
            descuento_min=0.3,
            descuento_max=0.5,
            solo_con_oportunidades=False,
            orden="Referencia (A-Z)",
        )
        self.assertEqual(resultado["Referencia"].tolist(), ["REF-A"])

        resultado = filtrar_oportunidades_masivas(
            self._resultado(),
            dum_min=60_000_000,
            dum_max=160_000_000,
            solo_con_oportunidades=False,
            orden="Referencia (A-Z)",
        )
        self.assertEqual(resultado["Referencia"].tolist(), ["REF-A", "REF-C"])

        resultado = filtrar_oportunidades_masivas(
            self._resultado(), excluir_clientes_con_liquidaciones=True,
            solo_con_oportunidades=False, orden="Referencia (A-Z)",
        )
        self.assertNotIn("REF-B", resultado["Referencia"].tolist())

    def test_ordenamiento(self):
        resultado = filtrar_oportunidades_masivas(
            self._resultado(), orden="Mayor DUM", solo_con_oportunidades=False
        )
        self.assertEqual(resultado["Referencia"].tolist(), ["REF-C", "REF-A", "REF-B"])


class TestMetadatosPortafolioMasivas(unittest.TestCase):
    def test_extrae_id_pab_y_completitud(self):
        masivas = pd.DataFrame([
            _masiva(
                id_deuda="D1", pab=20_000_000,
                id_portafolio="P1", pab_portafolio=30_000_000,
                es_portafolio=True,
            ),
            _masiva(
                id_deuda="D2", pab=10_000_000,
                id_portafolio="P1", pab_portafolio=30_000_000,
                es_portafolio=True, fila=3,
            ),
        ])
        seleccion = seleccionar_descuentos_masivas(masivas_df=masivas, hoy=HOY)

        self.assertEqual(set(seleccion["Id_Portafolio"]), {"P1"})
        self.assertTrue(seleccion["Portafolio_Completo"].astype(bool).all())
        self.assertAlmostEqual(float(seleccion["PaB_Portafolio"].iloc[0]), 30_000_000)

    def test_marca_incompleto_si_falta_una_deuda_del_portafolio(self):
        masivas = pd.DataFrame([
            _masiva(
                id_deuda="D1", pab=20_000_000,
                id_portafolio="P1", pab_portafolio=30_000_000,
                es_portafolio=True,
            ),
            _masiva(
                id_deuda="D2", pab=10_000_000,
                fecha_limite=pd.Timestamp("2020-01-01"),
                id_portafolio="P1", pab_portafolio=30_000_000,
                es_portafolio=True, fila=3,
            ),
        ])
        seleccion = seleccionar_descuentos_masivas(masivas_df=masivas, hoy=HOY)

        self.assertEqual(len(seleccion), 1)
        self.assertEqual(seleccion.iloc[0]["Id_Deuda"], "D1")
        self.assertFalse(bool(seleccion.iloc[0]["Portafolio_Completo"]))


class TestPortafolioMasivasCalculo(unittest.TestCase):
    def _datos(self, *, fecha_d2=pd.Timestamp("2026-12-31")):
        asignacion = pd.DataFrame([
            {
                "Referencia": "REF-PORT", "Nombre_Cliente": "Cliente Portafolio",
                "Banco": "BBVA Colombia", "Id_Deuda": "D1",
                "PaB_Origen": 100_000_000.0, "Negociador": "Nego P",
                "Descuento_Esperado": 0.5, "Apartado_Neto": 10_000_000.0,
                "Pricing": 0.15,
            },
            {
                "Referencia": "REF-PORT", "Nombre_Cliente": "Cliente Portafolio",
                "Banco": "BBVA Colombia", "Id_Deuda": "D2",
                "PaB_Origen": 50_000_000.0, "Negociador": "Nego P",
                "Descuento_Esperado": 0.4, "Apartado_Neto": 10_000_000.0,
                "Pricing": 0.15,
            },
        ])
        masivas = pd.DataFrame([
            _masiva(
                id_deuda="D1", pab=20_000_000,
                id_portafolio="P1", pab_portafolio=30_000_000,
                es_portafolio=True,
            ),
            _masiva(
                id_deuda="D2", pab=10_000_000, fecha_limite=fecha_d2,
                id_portafolio="P1", pab_portafolio=30_000_000,
                es_portafolio=True, fila=3,
            ),
        ])
        return asignacion, masivas

    def test_usa_pab_portafolio_y_distribuye_por_origen(self):
        asignacion, masivas = self._datos()
        resultado = _calcular(
            asignacion=asignacion,
            masivas=masivas,
            saldos={"Saldos": {"REF-PORT": 10_000_000}, "PorCobrar": {"REF-PORT": 0}},
            prospectos_credito={"REF-PORT": "Tradicional"},
            solo_masivas=True,
        )

        fila = resultado.iloc[0]
        self.assertAlmostEqual(float(fila["PaB_Actualizado_Total"]), 30_000_000)
        self.assertAlmostEqual(float(fila["Descuento_Actual"]), 0.8)
        self.assertAlmostEqual(float(fila["Ingreso_Actual"]), 18_000_000)

        portafolios = fila["Portafolios_Detalle"]
        self.assertEqual(len(portafolios), 1)
        unidad = portafolios[0]
        self.assertEqual(unidad["Deudas"], ["D1", "D2"])
        self.assertEqual(int(unidad["Num_Deudas"]), 2)
        self.assertTrue(unidad["Pago_Compartido"])
        self.assertAlmostEqual(float(unidad["PaB_Actualizado"]), 30_000_000)

        detalles = {d["Id_Deuda"]: d for d in unidad["Deudas_Detalle"]}
        self.assertAlmostEqual(float(detalles["D1"]["PaB_Actualizado"]), 20_000_000)
        self.assertAlmostEqual(float(detalles["D2"]["PaB_Actualizado"]), 10_000_000)
        self.assertEqual(detalles["D1"]["Unidad_Id"], unidad["Unidad_Id"])

    def test_portafolio_incompleto_usa_suma_de_pab_propuesta(self):
        asignacion, masivas = self._datos(fecha_d2=pd.Timestamp("2020-01-01"))
        resultado = _calcular(
            asignacion=asignacion,
            masivas=masivas,
            saldos={"Saldos": {"REF-PORT": 10_000_000}, "PorCobrar": {"REF-PORT": 0}},
            prospectos_credito={"REF-PORT": "Tradicional"},
            solo_masivas=True,
        )

        fila = resultado.iloc[0]
        self.assertEqual(int(fila["Deudas_Analizadas"]), 1)
        self.assertAlmostEqual(float(fila["PaB_Actualizado_Total"]), 20_000_000)
        unidad = fila["Portafolios_Detalle"][0]
        self.assertFalse(unidad["Pago_Compartido"])
        self.assertAlmostEqual(float(unidad["PaB_Actualizado"]), 20_000_000)


class TestPortafolioActualizacionesCalculo(unittest.TestCase):
    def _datos(self):
        asignacion = pd.DataFrame([
            {
                "Referencia": "REF-ACT", "Nombre_Cliente": "Cliente Actualizaciones",
                "Banco": "BBVA Colombia", "Id_Deuda": "D1",
                "PaB_Origen": 100_000_000.0, "Negociador": "Nego A",
                "Descuento_Esperado": 0.7, "Apartado_Neto": 10_000_000.0,
                "Pricing": 0.15,
            },
            {
                "Referencia": "REF-ACT", "Nombre_Cliente": "Cliente Actualizaciones",
                "Banco": "Itaú", "Id_Deuda": "D2",
                "PaB_Origen": 50_000_000.0, "Negociador": "Nego A",
                "Descuento_Esperado": 0.7, "Apartado_Neto": 10_000_000.0,
                "Pricing": 0.15,
            },
        ])
        return asignacion

    def _calcular_con_acts(self, acts):
        return _calcular(
            asignacion=self._datos(),
            masivas=pd.DataFrame(),
            saldos={"Saldos": {"REF-ACT": 100_000_000}, "PorCobrar": {"REF-ACT": 0}},
            prospectos_credito={"REF-ACT": "Tradicional"},
            actualizaciones_df=acts,
            solicitudes_df=pd.DataFrame(),
            solo_masivas=False,
        )

    def _acts(self, valores, fechas=None, etiquetas=None):
        fechas = fechas or [
            pd.Timestamp("2026-11-01 10:00:00"),
            pd.Timestamp("2026-11-01 10:00:30"),
        ]
        etiquetas = etiquetas or ["ACUERDO", "ACUERDO"]
        return pd.DataFrame([
            {
                "Id_Deuda": "D1", "Fecha_Act": fechas[0],
                "Etiqueta_Act": etiquetas[0], "PaB_Actualizado": valores[0],
                "Correo": "a@x.com",
            },
            {
                "Id_Deuda": "D2", "Fecha_Act": fechas[1],
                "Etiqueta_Act": etiquetas[1], "PaB_Actualizado": valores[1],
                "Correo": "a@x.com",
            },
        ])

    def test_valores_iguales_usa_el_pago_una_sola_vez(self):
        resultado = self._calcular_con_acts(
            self._acts([20_000_000, 20_000_000])
        )
        fila = resultado.iloc[0]

        self.assertAlmostEqual(float(fila["PaB_Actualizado_Total"]), 20_000_000)
        self.assertAlmostEqual(float(fila["Descuento_Actual"]), 1 - (20_000_000 / 150_000_000))
        unidad = fila["Portafolios_Detalle"][0]
        self.assertTrue(unidad["Pago_Compartido"])
        self.assertEqual(unidad["Deudas"], ["D1", "D2"])
        detalles = {d["Id_Deuda"]: d for d in unidad["Deudas_Detalle"]}
        self.assertAlmostEqual(
            float(detalles["D1"]["PaB_Actualizado"]), 20_000_000 * (100 / 150)
        )
        self.assertAlmostEqual(
            float(detalles["D2"]["PaB_Actualizado"]), 20_000_000 * (50 / 150)
        )

    def test_valores_distintos_se_suman(self):
        resultado = self._calcular_con_acts(
            self._acts([20_000_000, 10_000_000])
        )
        fila = resultado.iloc[0]

        self.assertAlmostEqual(float(fila["PaB_Actualizado_Total"]), 30_000_000)
        self.assertAlmostEqual(float(fila["Descuento_Actual"]), 0.8)
        unidad = fila["Portafolios_Detalle"][0]
        self.assertFalse(unidad["Pago_Compartido"])
        detalles = {d["Id_Deuda"]: d for d in unidad["Deudas_Detalle"]}
        self.assertAlmostEqual(float(detalles["D1"]["PaB_Actualizado"]), 20_000_000)
        self.assertAlmostEqual(float(detalles["D2"]["PaB_Actualizado"]), 10_000_000)

    def test_etiquetas_distintas_no_se_agrupan(self):
        resultado = self._calcular_con_acts(
            self._acts([20_000_000, 10_000_000], etiquetas=["ACUERDO", "DEPOSITO"])
        )
        fila = resultado.iloc[0]

        self.assertEqual(len(fila["Portafolios_Detalle"]), 2)
        self.assertTrue(
            all(
                unidad["Tipo_Unidad"] == "Deuda individual"
                for unidad in fila["Portafolios_Detalle"]
            )
        )
        self.assertAlmostEqual(float(fila["PaB_Actualizado_Total"]), 30_000_000)

    def test_gap_mayor_a_la_ventana_no_se_agrupa(self):
        resultado = self._calcular_con_acts(
            self._acts(
                [20_000_000, 20_000_000],
                fechas=[
                    pd.Timestamp("2026-11-01 10:00:00"),
                    pd.Timestamp("2026-11-01 10:01:00"),
                ],
            )
        )
        fila = resultado.iloc[0]

        self.assertEqual(len(fila["Portafolios_Detalle"]), 2)
        self.assertAlmostEqual(float(fila["PaB_Actualizado_Total"]), 40_000_000)

    def test_actualizacion_no_confiable_no_forma_portafolio(self):
        resultado = self._calcular_con_acts(
            self._acts([20_000_000, 20_000_000], etiquetas=["LLAMADA", "LLAMADA"])
        )
        fila = resultado.iloc[0]

        self.assertEqual(len(fila["Portafolios_Detalle"]), 2)
        self.assertAlmostEqual(float(fila["PaB_Actualizado_Total"]), 150_000_000)
        self.assertAlmostEqual(float(fila["Descuento_Actual"]), 0.0)


class TestActualizacionesDuplicadas(unittest.TestCase):
    def test_deduplica_mismo_id_y_fecha_conservando_ultima_fila(self):
        ts_1 = pd.Timestamp("2026-11-01 10:00:00")
        ts_2 = pd.Timestamp("2026-11-02 10:00:00")
        acts = pd.DataFrame([
            {
                "Id_Deuda": "D1", "Fecha_Act": ts_1,
                "Etiqueta_Act": "ACUERDO", "PaB_Actualizado": 20_000_000.0,
                "Correo": "a@x.com",
            },
            {
                "Id_Deuda": "D1", "Fecha_Act": ts_1,
                "Etiqueta_Act": "ACUERDO", "PaB_Actualizado": 30_000_000.0,
                "Correo": "a@x.com",
            },
            {
                "Id_Deuda": "D1", "Fecha_Act": ts_2,
                "Etiqueta_Act": "DEPOSITO", "PaB_Actualizado": 25_000_000.0,
                "Correo": "a@x.com",
            },
        ])

        dedup = _deduplicar_actualizaciones(acts)

        self.assertEqual(len(dedup), 2)
        fila_duplicada = dedup[dedup["Fecha_Act"] == ts_1].iloc[0]
        self.assertAlmostEqual(
            float(fila_duplicada["PaB_Actualizado"]), 30_000_000.0
        )

    def test_calculo_masivo_usa_la_ultima_fila_duplicada(self):
        asignacion = pd.DataFrame([{
            "Referencia": "REF-DUP", "Nombre_Cliente": "Cliente Duplicado",
            "Banco": "BBVA Colombia", "Id_Deuda": "D1",
            "PaB_Origen": 100_000_000.0, "Negociador": "Nego D",
            "Descuento_Esperado": 0.5, "Apartado_Neto": 10_000_000.0,
            "Pricing": 0.15,
        }])
        acts = pd.DataFrame([
            {
                "Id_Deuda": "D1",
                "Fecha_Act": pd.Timestamp("2026-11-01 10:00:00"),
                "Etiqueta_Act": "ACUERDO",
                "PaB_Actualizado": 20_000_000.0,
                "Correo": "a@x.com",
            },
            {
                "Id_Deuda": "D1",
                "Fecha_Act": pd.Timestamp("2026-11-01 10:00:00"),
                "Etiqueta_Act": "ACUERDO",
                "PaB_Actualizado": 30_000_000.0,
                "Correo": "a@x.com",
            },
        ])

        resultado = _calcular(
            asignacion=asignacion,
            masivas=pd.DataFrame(),
            actualizaciones_df=acts,
            solicitudes_df=pd.DataFrame(),
            solo_masivas=False,
            incluir_acuerdos_robo=False,
        )
        fila = resultado.iloc[0]

        self.assertEqual(int(fila["Deudas_Analizadas"]), 1)
        self.assertAlmostEqual(
            float(fila["PaB_Actualizado_Total"]), 30_000_000.0
        )
        self.assertEqual(len(fila["Portafolios_Detalle"]), 1)


class TestRendimientoPortafoliosActualizaciones(unittest.TestCase):
    """Comparación de tiempo del pipeline de portafolios con Actualizaciones.

    Antes de la vectorización, 10k deudas + 4k actualizaciones + 300
    solicitudes tardaban ~64 s: 37,9 s en ``_construir_unidades_actualizaciones``,
    21,7 s en ``_aplicar_pago_unidades`` y 4,3 s en resolver Actualizaciones.
    El umbral de 20 s falla si vuelve una implementación con bucles por cliente
    o por deuda.
    """

    N_DEUDAS = 10_000
    N_ACTUALIZACIONES = 4_000
    N_SOLICITUDES = 300

    def _datos(self):
        bancos = [
            "BBVA Colombia", "Itaú", "Banco de Occidente",
            "Banco Popular", "Bancolombia",
        ]
        etiquetas = [
            "ACUERDO", "DEPOSITO", "CAMBIO DE PAB",
            "ACTUALIZADO_ALIANZAS", "LLAMADA",
        ]
        deudas = pd.DataFrame([
            {
                "Referencia": "REF-{:05d}".format(i // 4),
                "Nombre_Cliente": "Cliente {}".format(i // 4),
                "Banco": bancos[i % len(bancos)],
                "Id_Deuda": "D{:06d}".format(i),
                "PaB_Origen": float(1_000_000 + (i % 97) * 1_000_000),
                "Negociador": "Nego {}".format(i % 20),
                "Descuento_Esperado": float((i % 8) + 1) / 10,
                "Apartado_Neto": float((i % 5) * 1_000_000),
                "Pricing": [0.15, 0.20, 0.25][i % 3],
            }
            for i in range(self.N_DEUDAS)
        ])

        base_fecha = pd.Timestamp("2026-10-01")
        registros_acts = [
            {
                "Correo": "correo{}@x.com".format(i % 20),
                "Id_Deuda": "D{:06d}".format((i * 37) % self.N_DEUDAS),
                "Fecha_Act": base_fecha + pd.Timedelta(
                    minutes=(i * 7) % 40_000
                ),
                "Etiqueta_Act": etiquetas[i % len(etiquetas)],
                "PaB_Actualizado": float(1_000_000 + (i % 90) * 1_000_000),
            }
            for i in range(self.N_ACTUALIZACIONES)
        ]
        # Duplicados de la misma deuda en el mismo instante.
        registros_acts.extend(registros_acts[:800])
        actualizaciones = pd.DataFrame(registros_acts)

        masivas = pd.DataFrame([
            {
                "Id_Deuda": "D{:06d}".format((i * 11) % self.N_DEUDAS),
                "PaB_Propuesta": float(1_000_000 + (i % 80) * 1_000_000),
                "Fecha_Masiva": pd.Timestamp("2026-11-01"),
                "Fila_Sheets": i + 2,
                "Casa_Cobro": "ALIADO",
                "Es_Portafolio": False,
                "Metadata": {"Fecha_Limite_Uso": pd.Timestamp("2026-12-31")},
            }
            for i in range(2_500)
        ])

        solicitudes = pd.DataFrame([
            {
                "Estado_Solicitud": "Exitosa",
                "Fecha_Respuesta": base_fecha + pd.Timedelta(days=i % 30),
                "Timestamp": pd.Timestamp("2026-09-01"),
                "Datos_Solicitud": [
                    {
                        "Id_Deuda": "D{:06d}".format(
                            (i * 13 + j) % self.N_DEUDAS
                        ),
                        "Monto_Propuesto": float(
                            1_000_000 + ((i + j) % 90) * 1_000_000
                        ),
                    }
                    for j in range(3)
                ],
                "JSON_Respuesta": [],
                "Es_Historico": False,
            }
            for i in range(self.N_SOLICITUDES)
        ])
        return deudas, actualizaciones, masivas, solicitudes

    def test_identifica_unidades_en_menos_de_20_segundos(self):
        deudas, actualizaciones, masivas, solicitudes = self._datos()

        inicio = time.perf_counter()
        resueltas = _resolver_pab_actualizado_actualizaciones(
            deudas=deudas,
            actualizaciones_df=actualizaciones,
            masivas_df=masivas,
            solicitudes_df=solicitudes,
        )
        unidades = _construir_unidades_actualizaciones(deudas=resueltas)
        pagos = _aplicar_pago_unidades(deudas=unidades, solo_masivas=False)
        duracion = time.perf_counter() - inicio

        self.assertLess(
            duracion,
            20.0,
            "El pipeline de portafolios/unidades tardó {:.2f}s; antes de la "
            "vectorización tardaba ~64s con 10k deudas.".format(duracion),
        )
        self.assertEqual(len(pagos), len(deudas))
        self.assertTrue((pagos["Unidad_Id"].astype(str) != "").all())
        self.assertGreater(pagos["Unidad_Id"].nunique(), 0)

        suma_pagos = pagos.groupby("Unidad_Id")["PaB_Actualizado"].sum()
        total_unidad = pagos.groupby(
            "Unidad_Id"
        )["_PaB_Actualizado_Unidad"].first()
        diferencia_maxima = (suma_pagos - total_unidad).abs().max()
        self.assertLess(diferencia_maxima, 1e-6)


class TestReglaBancos(unittest.TestCase):
    def _datos(self):
        return pd.DataFrame([
            {
                "Referencia": "REF-BANCO", "Nombre_Cliente": "Cliente Banco",
                "Banco": "BBVA Colombia", "Id_Deuda": "D1",
                "PaB_Origen": 100_000_000.0, "Negociador": "Nego B",
                "Descuento_Esperado": 0.4, "Apartado_Neto": 10_000_000.0,
                "Pricing": 0.15,
            },
            {
                "Referencia": "REF-BANCO", "Nombre_Cliente": "Cliente Banco",
                "Banco": "BBVA Colombia", "Id_Deuda": "D2",
                "PaB_Origen": 50_000_000.0, "Negociador": "Nego B",
                "Descuento_Esperado": 0.4, "Apartado_Neto": 10_000_000.0,
                "Pricing": 0.15,
            },
            {
                "Referencia": "REF-BANCO", "Nombre_Cliente": "Cliente Banco",
                "Banco": "Itaú", "Id_Deuda": "D3",
                "PaB_Origen": 30_000_000.0, "Negociador": "Nego B",
                "Descuento_Esperado": 0.4, "Apartado_Neto": 10_000_000.0,
                "Pricing": 0.15,
            },
        ])

    def test_sin_actualizaciones_agrupa_por_banco(self):
        resultado = _calcular(
            asignacion=self._datos(),
            masivas=pd.DataFrame(),
            saldos={"Saldos": {"REF-BANCO": 50_000_000}, "PorCobrar": {"REF-BANCO": 0}},
            prospectos_credito={"REF-BANCO": "Tradicional"},
            solo_masivas=False,
        )
        fila = resultado.iloc[0]

        self.assertAlmostEqual(float(fila["PaB_Actualizado_Total"]), 180_000_000)
        self.assertAlmostEqual(float(fila["Descuento_Actual"]), 0.0)
        portafolios = fila["Portafolios_Detalle"]
        self.assertEqual(len(portafolios), 2)
        banco = next(
            unidad for unidad in portafolios
            if unidad["Tipo_Unidad"] == "Portafolio Banco"
        )
        self.assertEqual(banco["Deudas"], ["D1", "D2"])
        self.assertEqual(banco["Num_Deudas"], 2)
        individual = next(
            unidad for unidad in portafolios if "D3" in unidad["Deudas"]
        )
        self.assertEqual(individual["Tipo_Unidad"], "Deuda individual")

    def test_con_actualizaciones_no_aplica_regla_de_bancos(self):
        acts = pd.DataFrame([{
            "Id_Deuda": "D1",
            "Fecha_Act": pd.Timestamp("2026-11-01 10:00:00"),
            "Etiqueta_Act": "ACUERDO",
            "PaB_Actualizado": 20_000_000.0,
            "Correo": "a@x.com",
        }])
        resultado = _calcular(
            asignacion=self._datos(),
            masivas=pd.DataFrame(),
            saldos={"Saldos": {"REF-BANCO": 50_000_000}, "PorCobrar": {"REF-BANCO": 0}},
            prospectos_credito={"REF-BANCO": "Tradicional"},
            actualizaciones_df=acts,
            solicitudes_df=pd.DataFrame(),
            solo_masivas=False,
        )
        fila = resultado.iloc[0]

        self.assertEqual(len(fila["Portafolios_Detalle"]), 3)
        self.assertTrue(
            all(
                unidad["Tipo_Unidad"] == "Deuda individual"
                for unidad in fila["Portafolios_Detalle"]
            )
        )


class TestCreditoPorUnidad(unittest.TestCase):
    def _datos(self, *, id_portafolio="", pab_portafolio=None, pab_ideal=None):
        asignacion = pd.DataFrame([
            {
                "Referencia": "REF-CRED-U", "Nombre_Cliente": "Cliente Crédito Unidad",
                "Banco": "BBVA Colombia", "Id_Deuda": "D1",
                "PaB_Origen": 100_000_000.0, "Negociador": "Nego C",
                "Descuento_Esperado": 0.4, "Apartado_Neto": 20_000_000.0,
                "Pricing": 0.15,
            },
            {
                "Referencia": "REF-CRED-U", "Nombre_Cliente": "Cliente Crédito Unidad",
                "Banco": "Itaú", "Id_Deuda": "D2",
                "PaB_Origen": 50_000_000.0, "Negociador": "Nego C",
                "Descuento_Esperado": 0.4, "Apartado_Neto": 20_000_000.0,
                "Pricing": 0.15,
            },
        ])
        masivas = pd.DataFrame([
            _masiva(
                id_deuda="D1", pab=20_000_000,
                id_portafolio=id_portafolio, pab_portafolio=pab_portafolio,
                es_portafolio=bool(id_portafolio),
            ),
            _masiva(
                id_deuda="D2", pab=10_000_000,
                id_portafolio=id_portafolio, pab_portafolio=pab_portafolio,
                es_portafolio=bool(id_portafolio), fila=3,
            ),
        ])
        pipeline = pd.DataFrame([{
            "Referencia": "REF-CRED-U",
            "Fecha_Subida": pd.Timestamp("2026-10-01"),
            "Status_Credito": "CERRADO",
            "No_Opta_Credito": False,
            "Rechazo_Credito": False,
        }])
        return asignacion, masivas, pipeline, (pab_ideal or {})

    def _calcular(self, **kwargs):
        asignacion, masivas, pipeline, pab_ideal = self._datos(**kwargs)
        return _calcular(
            asignacion=asignacion,
            masivas=masivas,
            pab_ideal=pab_ideal,
            saldos={"Saldos": {"REF-CRED-U": 80_000_000}, "PorCobrar": {"REF-CRED-U": 0}},
            prospectos_credito={"REF-CRED-U": "Batch 1"},
            pipeline_credito=pipeline,
        )

    def test_portafolio_con_una_deuda_sin_pab_ideal_no_analiza_credito(self):
        resultado = self._calcular(
            id_portafolio="P1", pab_portafolio=30_000_000,
            pab_ideal={"D1": 80_000_000},
        )
        fila = resultado.iloc[0]

        self.assertFalse(bool(fila["Credito_Habilitado"]))
        self.assertEqual(fila["Tipos_Analisis"], ["Tradicional"])
        unidad = fila["Portafolios_Detalle"][0]
        self.assertFalse(unidad["Usa_Credito"])
        self.assertEqual(int(fila["Cred_Num_Deudas"]), 0)

    def test_deudas_individuales_con_ideal_si_analiza_credito(self):
        resultado = self._calcular(pab_ideal={"D1": 80_000_000})
        fila = resultado.iloc[0]

        self.assertTrue(bool(fila["Credito_Habilitado"]))
        self.assertEqual(len(fila["Portafolios_Detalle"]), 2)
        unidades = {
            deuda: unidad
            for unidad in fila["Portafolios_Detalle"]
            for deuda in unidad["Deudas"]
        }
        self.assertTrue(unidades["D1"]["Usa_Credito"])
        self.assertFalse(unidades["D2"]["Usa_Credito"])
        self.assertEqual(int(fila["Cred_Num_Deudas"]), 1)

    def test_portafolio_completo_con_ideal_si_analiza_credito(self):
        resultado = self._calcular(
            id_portafolio="P1", pab_portafolio=30_000_000,
            pab_ideal={"D1": 80_000_000, "D2": 40_000_000},
        )
        fila = resultado.iloc[0]

        self.assertTrue(bool(fila["Credito_Habilitado"]))
        unidad = fila["Portafolios_Detalle"][0]
        self.assertTrue(unidad["Usa_Credito"])
        self.assertEqual(int(fila["Cred_Num_Deudas"]), 2)


class TestResumenOportunidadesPorUnidad(unittest.TestCase):
    def _datos(self):
        asignacion = pd.DataFrame([
            {
                "Referencia": "REF-OPS", "Nombre_Cliente": "Cliente Ops",
                "Banco": "BBVA Colombia", "Id_Deuda": "D1",
                "PaB_Origen": 100_000_000.0, "Negociador": "Nego O",
                "Descuento_Esperado": 0.4, "Apartado_Neto": 10_000_000.0,
                "Pricing": 0.15,
            },
            {
                "Referencia": "REF-OPS", "Nombre_Cliente": "Cliente Ops",
                "Banco": "Itaú", "Id_Deuda": "D2",
                "PaB_Origen": 50_000_000.0, "Negociador": "Nego O",
                "Descuento_Esperado": 0.4, "Apartado_Neto": 10_000_000.0,
                "Pricing": 0.15,
            },
        ])
        masivas = pd.DataFrame([
            _masiva(id_deuda="D1", pab=20_000_000),
            _masiva(id_deuda="D2", pab=10_000_000, fila=3),
        ])
        return asignacion, masivas

    def test_cuenta_incidencias_por_unidad(self):
        asignacion, masivas = self._datos()
        resultado = _calcular(
            asignacion=asignacion,
            masivas=masivas,
            saldos={"Saldos": {"REF-OPS": 100_000_000}, "PorCobrar": {"REF-OPS": 0}},
            prospectos_credito={"REF-OPS": "Tradicional"},
        )
        fila = resultado.iloc[0]

        self.assertEqual(len(fila["Portafolios_Detalle"]), 2)
        for unidad in fila["Portafolios_Detalle"]:
            self.assertIn("Liquidación Instantánea", unidad["Oportunidades"])
        self.assertEqual(fila["Oportunidades"], ["Liquidación Instantánea"])
        self.assertEqual(int(fila["Num_Oportunidades"]), 2)
        self.assertEqual(int(fila["Num_Oportunidades_Calculadas"]), 2)
        self.assertEqual(int(fila["Num_Oportunidades_Generales"]), 0)

    def test_oportunidad_general_se_cuenta_una_vez(self):
        asignacion, masivas = self._datos()
        prospectos = pd.DataFrame([{
            "Referencia": "REF-OPS",
            "Id_Deuda": "D1",
            "Prospecto": "Trad 1",
            "Prob_Liq": 0.7,
        }])
        resultado = _calcular(
            asignacion=asignacion,
            masivas=masivas,
            saldos={"Saldos": {"REF-OPS": 100_000_000}, "PorCobrar": {"REF-OPS": 0}},
            prospectos_credito={"REF-OPS": "Tradicional"},
            prospectos_tradicional=prospectos,
        )
        fila = resultado.iloc[0]

        self.assertEqual(int(fila["Num_Oportunidades_Calculadas"]), 2)
        self.assertEqual(int(fila["Num_Oportunidades_Generales"]), 1)
        self.assertEqual(int(fila["Num_Oportunidades"]), 3)
        self.assertIn("IA Liquidadora", fila["Oportunidades"])
        self.assertEqual(len(fila["Oportunidades_Generales"]), 1)
        self.assertEqual(fila["Oportunidades_Generales"][0]["deudas"], ["D1"])


class TestIngresoYOrden(unittest.TestCase):
    def _resultado(self):
        return pd.DataFrame([
            {
                "Referencia": "REF-A", "Nombre_Cliente": "Ana", "Negociador": "Nego A",
                "Prospecto_Credito": "Batch 1", "Tradicional_Habilitado": True,
                "Credito_Habilitado": True, "Num_Oportunidades": 2,
                "Oportunidades": ["Depósito Extra", "IA Liquidadora"], "Es_Viable": True,
                "Descuento_Actual": 0.4, "PaB_Origen_Total": 100_000_000,
                "Ahorro_Neto": 45_000_000, "Tiene_Deudas_Liquidaciones": False,
                "Ingreso_Actual": 30_000_000,
            },
            {
                "Referencia": "REF-B", "Nombre_Cliente": "Bruno", "Negociador": "Nego B",
                "Prospecto_Credito": "Tradicional", "Tradicional_Habilitado": True,
                "Credito_Habilitado": False, "Num_Oportunidades": 1,
                "Oportunidades": ["ContraOferta Viable"], "Es_Viable": False,
                "Descuento_Actual": 0.2, "PaB_Origen_Total": 50_000_000,
                "Ahorro_Neto": 10_000_000, "Tiene_Deudas_Liquidaciones": True,
                "Ingreso_Actual": 5_000_000,
            },
            {
                "Referencia": "REF-C", "Nombre_Cliente": "Carla", "Negociador": "Nego A",
                "Prospecto_Credito": "Cr Parcial", "Tradicional_Habilitado": False,
                "Credito_Habilitado": True, "Num_Oportunidades": 0,
                "Oportunidades": [], "Es_Viable": True,
                "Descuento_Actual": 0.6, "PaB_Origen_Total": 150_000_000,
                "Ahorro_Neto": 0, "Tiene_Deudas_Liquidaciones": False,
                "Ingreso_Actual": 60_000_000,
            },
        ])

    def test_ordena_por_ingreso_por_defecto(self):
        resultado = filtrar_oportunidades_masivas(
            self._resultado(), solo_con_oportunidades=False
        )
        self.assertEqual(
            resultado["Referencia"].tolist(), ["REF-C", "REF-A", "REF-B"]
        )

    def test_invertir_orden_numerico(self):
        resultado = filtrar_oportunidades_masivas(
            self._resultado(),
            orden="Mayor DUM",
            invertir_orden=True,
            solo_con_oportunidades=False,
        )
        self.assertEqual(
            resultado["Referencia"].tolist(), ["REF-B", "REF-A", "REF-C"]
        )

    def test_invertir_orden_alfabetico(self):
        resultado = filtrar_oportunidades_masivas(
            self._resultado(),
            orden="Referencia (A-Z)",
            invertir_orden=True,
            solo_con_oportunidades=False,
        )
        self.assertEqual(
            resultado["Referencia"].tolist(), ["REF-C", "REF-B", "REF-A"]
        )


class TestRedireccionIndividual(unittest.TestCase):
    def test_apaga_las_deudas_que_no_son_del_portafolio(self):
        valores, claves_limpiar = _preparar_estado_redireccion_individual(
            referencia="REF-1",
            deudas_referencia=["D1", "D2.0", "D3"],
            deudas_unidad=["D2"],
            tipo_analisis="Crédito",
        )

        self.assertFalse(valores["select_calc_ind_debt_D1"])
        self.assertTrue(valores["select_calc_ind_debt_D2"])
        self.assertFalse(valores["select_calc_ind_debt_D3"])
        self.assertEqual(valores["selectbox_referencia_calc_ind"], "REF-1")
        self.assertEqual(valores["select_analysis_calc_ind"], "**Por Crédito**")
        self.assertTrue(valores["continuar_calc_opp_REF-1"])
        self.assertTrue(valores[LLAVE_REDIRECCION_CALCULADORA])
        self.assertIn(
            "portafolio_total_REF-1_credito_calc_opps", claves_limpiar
        )
        self.assertIn("calc_ind_pab_credito_D1", claves_limpiar)
        self.assertIn("calc_ind_init_credito_D2", claves_limpiar)

    def test_tradicional_usa_las_llaves_del_modo_tradicional(self):
        valores, claves_limpiar = _preparar_estado_redireccion_individual(
            referencia="REF-2",
            deudas_referencia=["D1", "D2"],
            deudas_unidad=["D1"],
            tipo_analisis="Tradicional",
        )

        self.assertEqual(valores["select_analysis_calc_ind"], "**Por Tradicional**")
        self.assertIn(
            "portafolio_total_REF-2_tradicional_calc_opps", claves_limpiar
        )


class TestEscapeMarkdown(unittest.TestCase):
    def test_escapa_los_dolares(self):
        self.assertEqual(
            escapar_dolar_markdown("$1 y $2"), "\\$1 y \\$2"
        )
        self.assertEqual(escapar_dolar_markdown(None), "")
        self.assertEqual(escapar_dolar_markdown("sin montos"), "sin montos")


class TestFormatoValorOportunidad(unittest.TestCase):
    def test_deposito_extra_sin_simbolo_ni_decimales(self):
        valor = _formatear_valor_oportunidad_masiva(
            nombre="Depósito Extra", valor=12_345_678.9
        )
        self.assertEqual(valor, "12.345.679")

    def test_contraoferta_conserva_porcentaje(self):
        valor = _formatear_valor_oportunidad_masiva(
            nombre="ContraOferta Viable", valor=0.4321
        )
        self.assertEqual(valor, "43.2%")


class TestPaginacionEntera(unittest.TestCase):
    def test_normaliza_pagina(self):
        self.assertEqual(_normalizar_pagina_actual(None, 5), 1)
        self.assertEqual(_normalizar_pagina_actual("2", 5), 2)
        self.assertEqual(_normalizar_pagina_actual("2.9", 5), 2)
        self.assertEqual(_normalizar_pagina_actual(0, 5), 1)
        self.assertEqual(_normalizar_pagina_actual(9, 5), 5)
        self.assertEqual(_normalizar_pagina_actual("no-numero", 5), 1)

    def test_slice_pagina(self):
        self.assertEqual(
            _calcular_slice_pagina(pagina=1, total_registros=25, registros_por_pagina=10),
            (0, 10),
        )
        self.assertEqual(
            _calcular_slice_pagina(pagina=2, total_registros=25, registros_por_pagina=10),
            (10, 20),
        )
        self.assertEqual(
            _calcular_slice_pagina(pagina=3, total_registros=25, registros_por_pagina=10),
            (20, 25),
        )
        self.assertEqual(
            _calcular_slice_pagina(pagina=5, total_registros=25, registros_por_pagina=10),
            (25, 25),
        )


if __name__ == "__main__":
    unittest.main()
