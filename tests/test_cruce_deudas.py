"""Tests del algoritmo de reconocimiento de deudas y de sus helpers de cruce.

Cubren la normalización de cédulas, nombres, números de crédito y bancos, la
etiquetación del modelo (EXACTO, DUPLICADO, AMBIGUO, ADDENDUM, NULO) y la
distribución/agrupación de portafolios que alimenta la pestaña "Agregar
Cartera" de la aplicación.
"""

import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from modules.constants import MOTIVO_BANCOS_SELECCIONADOS
from modules.id_aut_deud.deuda_matcher import match_deudas
from modules.id_aut_deud.helpers import (
    _calcular_pago_estructurado,
    _calcular_propuesta_pago,
    _construir_metadata_masivas,
    _int_cuotas_pago,
    adivinar_columna,
    agrupar_montos_portafolio,
    build_pendiente_cruce_df,
    cleanCedula,
    cleanNombreCliente,
    cleanNumeroCredito,
    cleanText,
    distribuir_montos_portafolio,
    is_generalized_crop,
    obtener_pago_minimo,
    obtener_ultimo_status_cruce,
)


class TestLimpiezaDatosCruce(unittest.TestCase):
    def test_clean_cedula(self):
        self.assertEqual(cleanCedula("1.234.567"), "1234567")
        self.assertEqual(cleanCedula("1234567.0"), "1234567")
        self.assertEqual(cleanCedula("123.456.789.0"), "1234567890")
        self.assertEqual(cleanCedula(" 1234567 "), "1234567")
        self.assertEqual(cleanCedula(float("nan")), "")

    def test_clean_nombre_cliente(self):
        self.assertEqual(cleanNombreCliente("José   Pérez"), "JOSE PEREZ")
        self.assertEqual(cleanNombreCliente("Pérez José"), "JOSE PEREZ")
        self.assertEqual(cleanNombreCliente("  María   Gómez  "), "GOMEZ MARIA")
        self.assertEqual(cleanNombreCliente(float("nan")), "")

    def test_clean_numero_credito(self):
        self.assertEqual(cleanNumeroCredito(12345.0), "12345")
        self.assertEqual(cleanNumeroCredito("00ABC-123"), "ABC123")
        self.assertEqual(cleanNumeroCredito("0001"), "0001")
        self.assertEqual(cleanNumeroCredito("ABCX123"), "ABC123")
        self.assertEqual(cleanNumeroCredito(float("nan")), "")

    def test_clean_text_reglas_de_bancos(self):
        self.assertEqual(cleanText("Banco de Bogotá S.A."), "BOGOTA")
        self.assertEqual(cleanText("Bco. Colpatria"), "DAVI BANK")
        self.assertEqual(cleanText("BBVA Colombia"), "BBVA")
        self.assertEqual(cleanText(float("nan")), "NAN")

    def test_is_generalized_crop(self):
        self.assertTrue(is_generalized_crop("123456", "123456"))
        self.assertTrue(is_generalized_crop("123456", "12356"))
        self.assertTrue(is_generalized_crop("ABCDEF", "ABE"))
        self.assertFalse(is_generalized_crop("ABCDEF", "ACE"))
        self.assertFalse(is_generalized_crop("ABC", "CBA"))

    def test_adivinar_columna(self):
        columnas = ["Numero_Credito", "Cedula", "Monto Actual"]
        self.assertEqual(adivinar_columna(columnas, ["cedula", "documento"]), "Cedula")
        self.assertEqual(
            adivinar_columna(columnas, ["credito", "numero crédito"]),
            "Numero_Credito",
        )
        self.assertEqual(adivinar_columna(columnas, ["no-existe"]), "Sin Columna")


class TestMatchDeudas(unittest.TestCase):
    @staticmethod
    def _datos():
        return pd.DataFrame([
            {
                "Cedula": "123456789",
                "Nombre_Cliente": "JUAN PEREZ",
                "Banco": "BANCOLOMBIA",
                "Monto_Actual": 1000000,
                "Numero_Credito": "ABC123",
                "Id_Deuda": "D1",
            },
            {
                "Cedula": "123456789",
                "Nombre_Cliente": "JUAN PEREZ",
                "Banco": "BANCOLOMBIA",
                "Monto_Actual": 1000000,
                "Numero_Credito": "ABC124",
                "Id_Deuda": "D2",
            },
            {
                "Cedula": "987654321",
                "Nombre_Cliente": "MARIA GOMEZ",
                "Banco": "DAVIVIENDA",
                "Monto_Actual": 2000000,
                "Numero_Credito": "XYZ999",
                "Id_Deuda": "D3",
            },
            {
                "Cedula": "555555555",
                "Nombre_Cliente": "CASA COBRO",
                "Banco": "ALIADO X",
                "Monto_Actual": 3000000,
                "Numero_Credito": "QQQ111",
                "Id_Deuda": "D4",
            },
        ])

    @staticmethod
    def _buscar():
        return pd.DataFrame([
            {
                "Id_Cruce": "C1",
                "Cedula": "123456789",
                "Nombre_Cliente": "PEREZ JUAN",
                "Banco": "BANCOLOMBIA",
                "Monto_Actual": 1000000,
                "Numero_Credito": "ABC123",
            },
            {
                "Id_Cruce": "C2",
                "Cedula": "123456789",
                "Nombre_Cliente": "JUAN PEREZ",
                "Banco": "BANCOLOMBIA",
                "Monto_Actual": 1000000,
            },
            {
                "Id_Cruce": "C3",
                "Cedula": "123456789",
                "Nombre_Cliente": "JUAN PEREZ",
            },
            {
                "Id_Cruce": "C4",
                "Cedula": "555555555",
                "Nombre_Cliente": "CASA COBRO",
            },
            {
                "Id_Cruce": "C5",
                "Cedula": "000000000",
                "Nombre_Cliente": "NO EXISTE",
            },
        ])

    def _match(self, buscar, *, datos=None, casa_cobro=None):
        with patch("modules.id_aut_deud.deuda_matcher.st.progress") as progress:
            progress.return_value.progress = MagicMock()
            return match_deudas(
                df_buscar=buscar,
                df_datos=datos if datos is not None else self._datos(),
                casa_cobro=casa_cobro,
            )

    def test_coincidencia_exacta(self):
        resultado = self._match(self._buscar().iloc[[0]])
        self.assertEqual(resultado.iloc[0]["Etiqueta_Registro"], "EXACTO")
        self.assertEqual(resultado.iloc[0]["Ids_Candidatos"], ["D1"])
        motivos = resultado.iloc[0]["Motivos_Etiqueta"]
        for motivo in ["Cedula", "Nombre_Cliente", "Banco", "Monto_Actual", "Numero_Credito"]:
            self.assertIn(motivo, motivos)

    def test_coincidencia_ambigua_por_deuda(self):
        resultado = self._match(self._buscar().iloc[[1]])
        self.assertEqual(resultado.iloc[0]["Etiqueta_Registro"], "AMBIGUO")
        self.assertEqual(resultado.iloc[0]["Ids_Candidatos"], ["D1", "D2"])

    def test_coincidencia_nula_sin_cliente(self):
        resultado = self._match(self._buscar().iloc[[4]])
        self.assertEqual(resultado.iloc[0]["Etiqueta_Registro"], "NULO")
        self.assertEqual(resultado.iloc[0]["Ids_Candidatos"], [])
        self.assertEqual(resultado.iloc[0]["Motivos_Etiqueta"], "")

    def test_coincidencia_addendum(self):
        resultado = self._match(self._buscar().iloc[[2]])
        self.assertEqual(resultado.iloc[0]["Etiqueta_Registro"], "ADDENDUM")
        self.assertEqual(resultado.iloc[0]["Ids_Candidatos"], ["D1", "D2"])
        self.assertEqual(resultado.iloc[0]["Motivos_Etiqueta"], "Cedula|Nombre_Cliente")

    def test_dos_registros_que_reclaman_el_mismo_id_son_duplicados(self):
        buscar = pd.concat([self._buscar().iloc[[0]], self._buscar().iloc[[0]]])
        buscar = buscar.assign(Id_Cruce=["C1", "C1B"])
        resultado = self._match(buscar)
        self.assertEqual(resultado["Etiqueta_Registro"].tolist(), ["DUPLICADO", "DUPLICADO"])
        self.assertEqual(resultado["Ids_Candidatos"].tolist(), [["D1"], ["D1"]])

    def test_casa_de_cobro_simula_el_banco(self):
        resultado = self._match(
            self._buscar().iloc[[3]],
            casa_cobro="ALIADO X",
        )
        self.assertEqual(resultado.iloc[0]["Etiqueta_Registro"], "AMBIGUO")
        self.assertIn("Casa de Cobro", resultado.iloc[0]["Motivos_Etiqueta"])

    def test_validaciones_de_columnas_requeridas(self):
        datos_incompletos = self._datos().drop(columns=["Banco"])
        with self.assertRaises(ValueError):
            self._match(self._buscar().iloc[[0]], datos=datos_incompletos)

        buscar_sin_id = self._buscar().drop(columns=["Id_Cruce"])
        with self.assertRaises(ValueError):
            self._match(buscar_sin_id, datos=self._datos())

        buscar_sin_cliente = pd.DataFrame([{"Id_Cruce": "C1", "Banco": "X"}])
        with self.assertRaises(LookupError):
            self._match(buscar_sin_cliente, datos=self._datos())


class TestMatchDeudasBancosSeleccionados(unittest.TestCase):
    @staticmethod
    def _datos():
        return pd.DataFrame([
            {
                "Cedula": "123456789",
                "Nombre_Cliente": "JUAN PEREZ",
                "Banco": "BANCOLOMBIA",
                "Monto_Actual": 1000000,
                "Numero_Credito": "ABC123",
                "Id_Deuda": "D1",
            },
            {
                "Cedula": "123456789",
                "Nombre_Cliente": "JUAN PEREZ",
                "Banco": "BANCO DAVIVIENDA",
                "Monto_Actual": 2000000,
                "Numero_Credito": "ABC124",
                "Id_Deuda": "D2",
            },
            {
                "Cedula": "123456789",
                "Nombre_Cliente": "JUAN PEREZ",
                "Banco": "BANCO DE BOGOTA",
                "Monto_Actual": 3000000,
                "Numero_Credito": "ABC125",
                "Id_Deuda": "D3",
            },
        ])

    @staticmethod
    def _buscar(**extra):
        fila = {
            "Id_Cruce": "C1",
            "Cedula": "123456789",
            "Nombre_Cliente": "PEREZ JUAN",
        }
        fila.update(extra)
        return pd.DataFrame([fila])

    def _match(self, *, bancos=None, buscar=None):
        with patch("modules.id_aut_deud.deuda_matcher.st.progress") as progress:
            progress.return_value.progress = MagicMock()
            return match_deudas(
                df_buscar=buscar if buscar is not None else self._buscar(),
                df_datos=self._datos(),
                bancos_seleccionados=bancos,
            )

    def test_sin_bancos_seleccionados_es_addendum(self):
        resultado = self._match()
        self.assertEqual(resultado.iloc[0]["Etiqueta_Registro"], "ADDENDUM")
        self.assertEqual(resultado.iloc[0]["Ids_Candidatos"], ["D1", "D2", "D3"])
        self.assertEqual(resultado.iloc[0]["Motivos_Etiqueta"], "Cedula|Nombre_Cliente")

    def test_un_banco_seleccionado_acota_los_candidatos(self):
        resultado = self._match(bancos=["Banco Davivienda"])
        self.assertEqual(resultado.iloc[0]["Etiqueta_Registro"], "AMBIGUO")
        self.assertEqual(resultado.iloc[0]["Ids_Candidatos"], ["D2"])
        self.assertIn(MOTIVO_BANCOS_SELECCIONADOS, resultado.iloc[0]["Motivos_Etiqueta"])

    def test_multiples_bancos_seleccionados_aplican_union(self):
        resultado = self._match(bancos=["Bancolombia", "Banco de Bogotá"])
        self.assertEqual(resultado.iloc[0]["Etiqueta_Registro"], "AMBIGUO")
        self.assertEqual(resultado.iloc[0]["Ids_Candidatos"], ["D1", "D3"])

    def test_banco_seleccionado_sin_coincidencia_no_restringe(self):
        resultado = self._match(bancos=["Banco Falabella"])
        self.assertEqual(resultado.iloc[0]["Etiqueta_Registro"], "ADDENDUM")
        self.assertEqual(resultado.iloc[0]["Ids_Candidatos"], ["D1", "D2", "D3"])
        self.assertNotIn(MOTIVO_BANCOS_SELECCIONADOS, resultado.iloc[0]["Motivos_Etiqueta"])

    def test_bancos_seleccionados_se_combinan_con_el_monto(self):
        resultado = self._match(
            bancos=["Bancolombia", "Banco Davivienda"],
            buscar=self._buscar(Monto_Actual=2000000),
        )
        self.assertEqual(resultado.iloc[0]["Etiqueta_Registro"], "AMBIGUO")
        self.assertEqual(resultado.iloc[0]["Ids_Candidatos"], ["D2"])
        motivos = resultado.iloc[0]["Motivos_Etiqueta"]
        self.assertIn(MOTIVO_BANCOS_SELECCIONADOS, motivos)
        self.assertIn("Monto_Actual", motivos)

    def test_banco_seleccionado_acepta_alias_del_catalogo(self):
        resultado = self._match(bancos=["Qnt Bancolombia"])
        self.assertEqual(resultado.iloc[0]["Ids_Candidatos"], ["D1"])
        self.assertIn(MOTIVO_BANCOS_SELECCIONADOS, resultado.iloc[0]["Motivos_Etiqueta"])


class TestPagosYStatusCruce(unittest.TestCase):
    def test_int_cuotas_pago(self):
        self.assertEqual(_int_cuotas_pago({"Cuotas": 6}), 6)
        self.assertEqual(_int_cuotas_pago({"Cuotas": "3"}), 3)
        self.assertEqual(_int_cuotas_pago({"Cuotas": None}), 1)
        self.assertEqual(_int_cuotas_pago({"Cuotas": "no-numero"}), 1)
        self.assertEqual(_int_cuotas_pago({}), 1)

    def test_obtener_pago_minimo(self):
        metadata = {
            "Pagos_Cuotas": [
                {"Cuotas": 3, "Monto": 100},
                {"Cuotas": 1, "Monto": 300},
            ]
        }
        self.assertEqual(obtener_pago_minimo(metadata), {"Cuotas": 1, "Monto": 300})
        self.assertIsNone(obtener_pago_minimo({"Pagos_Cuotas": []}))
        self.assertIsNone(obtener_pago_minimo({}))

    def test_calcular_propuesta_pago(self):
        self.assertEqual(
            _calcular_propuesta_pago(
                mtdt={"Pagos_Cuotas": [{"Cuotas": 1, "Monto": 300}, {"Cuotas": 3, "Monto": 100}]}
            ),
            300.0,
        )
        self.assertEqual(
            _calcular_propuesta_pago(mtdt={"Pagos_Cuotas": [], "Monto_Actual_Original": 200}),
            200.0,
        )
        self.assertEqual(
            _calcular_propuesta_pago(
                mtdt={
                    "Pagos_Cuotas": [],
                    "Id_Definitivo": "D1",
                    "Deudas_Posibles": [{"Id_Deuda": "D1", "Monto_Actual": 150}],
                }
            ),
            150.0,
        )
        self.assertEqual(
            _calcular_propuesta_pago(mtdt={"Pagos_Cuotas": []}, monto_actual_fila=120),
            120.0,
        )
        self.assertTrue(
            pd.isna(_calcular_propuesta_pago(mtdt={"Pagos_Cuotas": []}, monto_actual_fila=None))
        )

    def test_calcular_pago_estructurado(self):
        monto, plazo = _calcular_pago_estructurado({
            "Pagos_Cuotas": [
                {"Cuotas": 3, "Monto": 100},
                {"Cuotas": 6, "Monto": 60},
            ]
        })
        self.assertEqual(monto, 60.0)
        self.assertEqual(plazo, 6)

        monto, plazo = _calcular_pago_estructurado({
            "Pagos_Cuotas": [{"Cuotas": 1, "Monto": 300}]
        })
        self.assertTrue(pd.isna(monto))
        self.assertTrue(pd.isna(plazo))

    def test_obtener_ultimo_status_cruce(self):
        metadata = {
            "Ultima_Actualizacion": {
                "Sin Reconocer": "2026-10-01 10:00:00",
                "Reconocido": "2026-10-02 10:00:00",
                "Subido Alianzas": "2026-10-02 10:00:00",
            }
        }
        self.assertEqual(obtener_ultimo_status_cruce(metadata), "Subido Alianzas")
        self.assertEqual(obtener_ultimo_status_cruce({}), "Sin Reconocer")
        self.assertEqual(
            obtener_ultimo_status_cruce({"Ultima_Actualizacion": {"Sin Reconocer": "2026-10-01"}}),
            "Sin Reconocer",
        )


class TestPortafoliosCruce(unittest.TestCase):
    @staticmethod
    def _metadata(id_definitivo, pagos, monto_original=None):
        metadata = {
            "Id_Registro": "1",
            "Archivo_Origen": "base.xlsx",
            "Pagos_Cuotas": pagos,
            "Fecha_Limite_Pago": pd.Timestamp("2026-11-30"),
            "Etiqueta": "EXACTO",
            "Motivos_Cruce": [],
            "Deudas_Posibles": [],
            "Identificado_Por": "N/A",
            "Casa_Cobro": "Aliado A",
            "Ejecutivo_Subida": "Ejecutivo",
            "Tipo_Contraoferta": "Descuento Máximo",
            "Ultima_Actualizacion": {"Sin Reconocer": "2026-10-01 10:00:00"},
            "Id_Definitivo": id_definitivo,
        }
        if monto_original is not None:
            metadata["Monto_Actual_Original"] = monto_original
        return metadata

    def _cruce(self, filas):
        return pd.DataFrame(filas)

    @staticmethod
    def _fila(id_cruce, cedula, monto, id_definitivo, pagos, monto_original=None):
        return {
            "Id_Cruce": id_cruce,
            "Cedula": cedula,
            "Nombre_Cliente": "CLIENTE",
            "Banco": "BANCO",
            "Monto_Actual": monto,
            "Numero_Credito": "C1",
            "Metadata": TestPortafoliosCruce._metadata(
                id_definitivo=id_definitivo,
                pagos=pagos,
                monto_original=monto_original,
            ),
        }

    def test_distribuir_portafolio_por_monto_actual(self):
        cruce = self._cruce([
            self._fila("C1", "1", 600000, "D1", [{"Cuotas": 1, "Monto": 500000}], 600000),
            self._fila("C2", "1", 400000, "D2", [{"Cuotas": 1, "Monto": 500000}], 400000),
        ])
        distribuido, resumen, info = distribuir_montos_portafolio(
            cruce_df=cruce,
            columnas_portafolio=["Cedula"],
        )
        pagos_1 = distribuido.loc[distribuido["Id_Cruce"] == "C1", "Metadata"].iloc[0]["Pagos_Cuotas"]
        pagos_2 = distribuido.loc[distribuido["Id_Cruce"] == "C2", "Metadata"].iloc[0]["Pagos_Cuotas"]
        self.assertEqual(pagos_1[0]["Monto"], 300000.0)
        self.assertEqual(pagos_2[0]["Monto"], 200000.0)
        self.assertEqual(resumen["Participacion"].tolist(), [0.6, 0.4])
        self.assertEqual(resumen["Pago_Minimo_Distribuido"].tolist(), [300000.0, 200000.0])
        self.assertEqual(resumen["Portafolio_Distribuido"].tolist(), [True, True])
        self.assertEqual(info, {"Montos_Consultados": 0, "Montos_Encontrados": 0})

    def test_distribuir_portafolio_incompleto_no_distribuye(self):
        cruce = self._cruce([
            self._fila("C1", "1", 600000, "D1", [{"Cuotas": 1, "Monto": 500000}], 600000),
            self._fila("C2", "1", 400000, "", [{"Cuotas": 1, "Monto": 500000}], 400000),
        ])
        distribuido, resumen, _ = distribuir_montos_portafolio(
            cruce_df=cruce,
            columnas_portafolio=["Cedula"],
        )
        pagos_1 = distribuido.loc[distribuido["Id_Cruce"] == "C1", "Metadata"].iloc[0]["Pagos_Cuotas"]
        self.assertEqual(pagos_1[0]["Monto"], 500000.0)
        self.assertEqual(resumen["Portafolio_Distribuido"].tolist(), [False, False])

    def test_agrupar_portafolio_suma_pagos_individuales(self):
        cruce = self._cruce([
            self._fila("C1", "1", 600000, "D1", [{"Cuotas": 1, "Monto": 300000}], 600000),
            self._fila("C2", "1", 400000, "D2", [{"Cuotas": 1, "Monto": 200000}], 400000),
        ])
        _, resumen, info = agrupar_montos_portafolio(
            cruce_df=cruce,
            columnas_portafolio=["Cedula"],
        )
        self.assertEqual(resumen["Monto_Portafolio"].tolist(), [500000.0, 500000.0])
        self.assertEqual(resumen["Ids_Portafolio"].tolist(), ["C1-C2", "C1-C2"])
        self.assertEqual(resumen["Portafolio_Agrupado"].tolist(), [True, True])
        self.assertEqual(info["Registros_Agrupados"], 2)
        self.assertEqual(info["Grupos_Portafolio"], 1)

    def test_agrupar_portafolio_incompleto_no_marca_grupo(self):
        cruce = self._cruce([
            self._fila("C1", "1", 600000, "D1", [{"Cuotas": 1, "Monto": 300000}], 600000),
            self._fila("C2", "1", 400000, "", [{"Cuotas": 1, "Monto": 200000}], 400000),
        ])
        _, resumen, info = agrupar_montos_portafolio(
            cruce_df=cruce,
            columnas_portafolio=["Cedula"],
        )
        self.assertEqual(resumen["Portafolio_Agrupado"].tolist(), [False])
        self.assertEqual(info["Grupos_Incompletos"], 1)
        self.assertEqual(info["Registros_Agrupados"], 0)

    def test_agrupar_portafolio_excluye_addendums(self):
        cruce = self._cruce([
            self._fila("C1", "1", 600000, "D1", [{"Cuotas": 1, "Monto": 300000}], 600000),
            self._fila("C2", "1", 400000, "ADDENDUM", [{"Cuotas": 1, "Monto": 200000}], 400000),
        ])
        _, resumen, info = agrupar_montos_portafolio(
            cruce_df=cruce,
            columnas_portafolio=["Cedula"],
        )
        self.assertEqual(info["Registros_Addendum"], 1)
        self.assertEqual(resumen["Portafolio_Agrupado"].tolist(), [True])
        self.assertNotIn("C2", resumen["Id_Cruce"].tolist())

    def test_construir_metadata_masivas(self):
        metadata = _construir_metadata_masivas(
            id_cruce="C1",
            mtdt_cruce={
                "Tipo_Contraoferta": "Descuento Máximo",
                "Fecha_Limite_Pago": pd.Timestamp("2026-11-30"),
                "Alias_Casa": "Alias",
            },
            id_portafolio="P1",
            pab_portafolio=500000,
        )
        self.assertEqual(metadata["Id_Cruce"], "C1")
        self.assertEqual(metadata["Tipo_Contraoferta"], "Descuento Máximo")
        self.assertEqual(metadata["Id_Portafolio"], "P1")
        self.assertEqual(metadata["PaB_Portafolio"], 500000.0)
        self.assertEqual(metadata["Alias"], "Alias")


class TestBuildPendienteCruce(unittest.TestCase):
    @staticmethod
    def _cartera():
        return pd.DataFrame([
            {
                "Id_Deuda": "D1",
                "Banco": "BANCOLOMBIA",
                "Monto_Actual": 1000000,
                "Numero_Credito": "ABC123",
                "Liquidada": False,
            },
        ])

    @staticmethod
    def _match(buscar):
        datos = pd.DataFrame([
            {
                "Cedula": "123456789",
                "Nombre_Cliente": "JUAN PEREZ",
                "Banco": "BANCOLOMBIA",
                "Monto_Actual": 1000000,
                "Numero_Credito": "ABC123",
                "Id_Deuda": "D1",
            },
        ])
        with patch("modules.id_aut_deud.deuda_matcher.st.progress") as progress:
            progress.return_value.progress = MagicMock()
            return match_deudas(df_buscar=buscar, df_datos=datos)

    def _build(self, buscar):
        return build_pendiente_cruce_df(
            cruce_df=buscar,
            match_result=self._match(buscar),
            cartera_df=self._cartera(),
            pagos_cuotas_dict={},
            fecha_limite_serie=pd.Series([pd.Timestamp("2026-11-30")]),
            casa_cobro="Aliado A",
            ejecutivo_subida="ejecutivo@gobravo.com.co",
            nombre_archivo="base.xlsx",
            tipo_contraoferta="Descuento Máximo",
            alias_casa="Alias",
        )

    def test_valida_metadata_completa(self):
        buscar = pd.DataFrame([
            {
                "Id_Cruce": "C1",
                "Cedula": "123456789.0",
                "Nombre_Cliente": "JUAN PEREZ",
                "Banco": "BANCOLOMBIA",
                "Monto_Actual": 1000000,
                "Numero_Credito": "ABC123",
                "Monto_Propuesto": 700000,
            },
        ])

        resultado = self._build(buscar)

        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado.iloc[0]["Cedula"], "123456789")
        metadata = resultado.iloc[0]["Metadata"]
        self.assertEqual(metadata["Id_Definitivo"], "D1")
        self.assertEqual(metadata["Etiqueta"], "EXACTO")
        self.assertEqual(metadata["Tipo_Contraoferta"], "Descuento Máximo")
        self.assertEqual(metadata["Alias_Casa"], "Alias")
        self.assertEqual(metadata["Fecha_Limite_Pago"], pd.Timestamp("2026-11-30"))

    def test_permite_cruce_por_nombre_sin_cedula(self):
        # El matcher acepta nombre como dato obligatorio alternativo a la
        # cédula. Si el archivo del aliado no trae cédula, la fila debe poder
        # validarse: la cédula se guarda vacía en PendienteCruceSchema.
        buscar = pd.DataFrame([
            {
                "Id_Cruce": "C1",
                "Nombre_Cliente": "JUAN PEREZ",
                "Banco": "BANCOLOMBIA",
                "Monto_Actual": 1000000,
                "Numero_Credito": "ABC123",
                "Monto_Propuesto": 700000,
            },
        ])

        resultado = self._build(buscar)

        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado.iloc[0]["Cedula"], "")
        self.assertEqual(resultado.iloc[0]["Metadata"]["Id_Definitivo"], "D1")
        self.assertEqual(resultado.iloc[0]["Metadata"]["Etiqueta"], "EXACTO")


if __name__ == "__main__":
    unittest.main()
