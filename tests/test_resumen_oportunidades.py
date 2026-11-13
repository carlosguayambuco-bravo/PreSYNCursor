# Estándar usando PEP8
# Librerías de Python
import unittest
# Librerías de Terceros
import pandas as pd
# Librerías Locales
from modules.oportunidades import calcular_oportunidades_masivas_datos
from modules.resumen_oportunidades import (
    _rango_descuento,
    calcular_resumen_oportunidades,
    construir_detalle_oportunidades,
)
from ui.calculadora_masiva_components import filtrar_oportunidades_masivas

HOY = pd.Timestamp("2026-11-13")

# --- Funciones Auxiliares para Construir Resultados de Prueba ---
def _oportunidad(
    nombre: str,
    *,
    ingreso: float,
    tipo: str,
    valor: object = 0.3,
    incluida: bool = True,
    deudas: list[str] | None = None,
) -> dict:
    oportunidad = {
        "nombre": nombre,
        "valor": valor,
        "detalle": "",
        "ingreso_estimado": ingreso,
        "incluida_en_ingreso_estimado": incluida,
        "tipo_analisis": tipo,
    }
    if deudas is not None:
        oportunidad["deudas"] = deudas
    return oportunidad

def _deuda(
    id_deuda: str,
    *,
    banco: str = "BBVA Colombia",
    casa: str = "ALIADO",
    pab_origen: float = 60_000_000,
    pab_actualizado: float = 42_000_000,
    etiqueta: str = "ACUERDO",
    fecha: object = pd.Timestamp("2026-11-01"),
    prospecto: str = "N/A",
    prob_liq: float = 0.0,
    pab_ideal: float = 0.0,
    unidad_id: str = "U1",
) -> dict:
    return {
        "Id_Deuda": id_deuda,
        "Banco": banco,
        "Casa_Cobro": casa,
        "PaB_Origen": pab_origen,
        "PaB_Actualizado": pab_actualizado,
        "Descuento_Deuda": (
            1 - (pab_actualizado / pab_origen) if pab_origen else 0.0
        ),
        "PaB_Ideal": pab_ideal,
        "Prospecto": prospecto,
        "Prob_Liq": prob_liq,
        "Tiene_Masiva": True,
        "Etiqueta_Actualizacion": etiqueta,
        "Fecha_Actualizacion": fecha,
        "Unidad_Id": unidad_id,
    }

def _unidad(
    *,
    unidad_id: str = "U1",
    etiqueta: str = "Portafolio U1",
    tipo: str = "Portafolio Masivas",
    deudas: list[str] | None = None,
    pab_origen: float = 100_000_000,
    pab_actualizado: float = 70_000_000,
    descuento: float = 0.3,
    ingreso: float = 10_000_000,
    trad: list[dict] | None = None,
    cred: list[dict] | None = None,
    generales: list[dict] | None = None,
    deudas_detalle: list[dict] | None = None,
) -> dict:
    deudas = deudas or ["D1", "D2"]
    deudas_detalle = deudas_detalle or [
        _deuda("D1"),
        _deuda("D2", banco="Itaú", pab_origen=40_000_000),
    ]
    return {
        "Unidad_Id": unidad_id,
        "Etiqueta": etiqueta,
        "Tipo_Unidad": tipo,
        "Deudas": deudas,
        "Num_Deudas": len(deudas),
        "PaB_Origen": pab_origen,
        "PaB_Actualizado": pab_actualizado,
        "Descuento_Actual": descuento,
        "Ingreso_Actual": 4_500_000,
        "Ingreso_Estimado": ingreso,
        "Pricing": 0.15,
        "Usa_Tradicional": True,
        "Usa_Credito": True,
        "Trad_Oportunidades": trad or [],
        "Cred_Oportunidades": cred or [],
        "Oportunidades_Generales": generales or [],
        "Deudas_Detalle": deudas_detalle,
    }

def _cliente(
    referencia: str = "REF-A",
    *,
    nombre: str = "Cliente A",
    negociador: str = "Nego A",
    prospecto_credito: str = "Batch 1",
    prospecto_tradicional: str = "Trad 1",
    estado_credito: str = "CERRADO",
    ingreso: float = 10_000_000,
    portafolios: list[dict] | None = None,
    deudas_analizadas: int = 2,
    estados_actualizacion: list[str] | None = None,
    bancos: list[str] | None = None,
    casas: list[str] | None = None,
) -> dict:
    portafolios = portafolios or [_unidad()]
    return {
        "Referencia": referencia,
        "Nombre_Cliente": nombre,
        "Negociador": negociador,
        "Prospecto_Credito": prospecto_credito,
        "Prospecto_Tradicional": prospecto_tradicional,
        "Estado_Credito": estado_credito,
        "Es_Viable": True,
        "Viable_Por": ["Tradicional"],
        "Tiene_Deudas_Liquidaciones": False,
        "Deudas_Analizadas": deudas_analizadas,
        "PaB_Origen_Total": 100_000_000,
        "PaB_Actualizado_Total": 70_000_000,
        "Descuento_Actual": 0.3,
        "Ingreso_Estimado": ingreso,
        "Ingreso_Estimado_Detalle": {},
        "Fuente_Descuento": "Masivas",
        "Estados_Actualizacion": estados_actualizacion or ["ACUERDO"],
        "Bancos": bancos or ["BBVA Colombia"],
        "Casas_Cobro": casas or ["ALIADO"],
        "Portafolios_Detalle": portafolios,
    }


class TestDetalleResumen(unittest.TestCase):
    def test_marca_el_maximo_por_unidad(self):
        unidad = _unidad(
            trad=[
                _oportunidad(
                    "Liquidación Instantánea", ingreso=10_000_000,
                    tipo="Tradicional",
                ),
                _oportunidad(
                    "Depósito Extra", ingreso=4_000_000,
                    tipo="Tradicional", valor=1_000_000,
                ),
            ],
            ingreso=10_000_000,
        )
        detalle = construir_detalle_oportunidades(
            pd.DataFrame([_cliente(portafolios=[unidad])])
        )

        self.assertEqual(len(detalle), 2)
        maximos = detalle[detalle["Es_Maximo_Unidad"]]
        self.assertEqual(len(maximos), 1)
        self.assertEqual(maximos.iloc[0]["Oportunidad"], "Liquidación Instantánea")
        self.assertAlmostEqual(
            float(maximos.iloc[0]["Ingreso_Asignado_Unidad"]),
            10_000_000,
        )

    def test_oportunidad_general_usa_sus_propias_deudas(self):
        general = _oportunidad(
            "Acuerdo para Robo",
            ingreso=3_000_000,
            tipo="General",
            valor="1 deuda(s)",
            deudas=["D1"],
        )
        unidad = _unidad(generales=[general], ingreso=10_000_000)
        detalle = construir_detalle_oportunidades(
            pd.DataFrame([_cliente(portafolios=[unidad])])
        )

        fila = detalle.iloc[0]
        self.assertEqual(fila["Oportunidad"], "Acuerdo para Robo")
        self.assertEqual(fila["Tipo_Analisis"], "General")
        self.assertTrue(bool(fila["Es_General"]))
        self.assertEqual(fila["Deudas"], ["D1"])

    def test_tipo_analisis_tradicional_y_credito(self):
        unidad = _unidad(
            trad=[
                _oportunidad(
                    "Depósito Extra", ingreso=4_000_000,
                    tipo="Tradicional",
                )
            ],
            cred=[
                _oportunidad(
                    "Liquidación Instantánea", ingreso=10_000_000,
                    tipo="Crédito",
                )
            ],
        )
        detalle = construir_detalle_oportunidades(
            pd.DataFrame([_cliente(portafolios=[unidad])])
        )
        tipos = dict(zip(detalle["Oportunidad"], detalle["Tipo_Analisis"]))
        self.assertEqual(tipos["Depósito Extra"], "Tradicional")
        self.assertEqual(tipos["Liquidación Instantánea"], "Crédito")

    def test_excluye_oportunidades_fuera_del_filtro(self):
        unidad = _unidad(
            trad=[
                _oportunidad(
                    "Liquidación Instantánea", ingreso=10_000_000,
                    tipo="Tradicional",
                ),
                _oportunidad(
                    "Depósito Extra", ingreso=4_000_000,
                    tipo="Tradicional", valor=1_000_000, incluida=False,
                ),
            ],
            ingreso=10_000_000,
        )
        detalle = construir_detalle_oportunidades(
            pd.DataFrame([_cliente(portafolios=[unidad])])
        )
        self.assertEqual(
            detalle["Oportunidad"].tolist(), ["Liquidación Instantánea"]
        )
        self.assertEqual(
            float(detalle["Ingreso_Estimado_Oportunidad"].sum()),
            10_000_000,
        )

    def test_rangos_de_descuento(self):
        self.assertEqual(_rango_descuento(0), "0%")
        self.assertEqual(_rango_descuento(0.05), "0% - 10%")
        self.assertEqual(_rango_descuento(0.1), "10% - 20%")
        self.assertEqual(_rango_descuento(0.99), "90% - 100%")


class TestResumenAgregado(unittest.TestCase):
    def _datos(self):
        cliente_a = _cliente(
            "REF-A",
            portafolios=[
                _unidad(
                    trad=[
                        _oportunidad(
                            "Liquidación Instantánea",
                            ingreso=10_000_000,
                            tipo="Tradicional",
                        ),
                        _oportunidad(
                            "Depósito Extra",
                            ingreso=4_000_000,
                            tipo="Tradicional",
                            valor=1_000_000,
                        ),
                    ],
                    ingreso=10_000_000,
                )
            ],
        )
        cliente_b = _cliente(
            "REF-B",
            nombre="Cliente B",
            negociador="Nego B",
            prospecto_credito="Cr Parcial",
            prospecto_tradicional="N/A",
            estado_credito="NO_VIABLE_MEC",
            ingreso=5_000_000,
            deudas_analizadas=1,
            estados_actualizacion=["DEPOSITO"],
            bancos=["Itaú"],
            casas=["OTRO"],
            portafolios=[
                _unidad(
                    unidad_id="U2",
                    etiqueta="Deuda D3",
                    tipo="Deuda individual",
                    deudas=["D3"],
                    pab_origen=50_000_000,
                    pab_actualizado=30_000_000,
                    descuento=0.4,
                    ingreso=5_000_000,
                    trad=[],
                    cred=[
                        _oportunidad(
                            "ContraOferta Viable",
                            ingreso=5_000_000,
                            tipo="Crédito",
                            valor=0.45,
                        )
                    ],
                    deudas_detalle=[
                        _deuda(
                            "D3",
                            banco="Itaú",
                            casa="OTRO",
                            pab_origen=50_000_000,
                            pab_actualizado=30_000_000,
                            etiqueta="DEPOSITO",
                        )
                    ],
                )
            ],
        )
        return pd.DataFrame([cliente_a, cliente_b])

    def test_kpis_y_oportunidades(self):
        resumen = calcular_resumen_oportunidades(self._datos())
        kpis = resumen["kpis"]

        self.assertEqual(kpis["Clientes_Total"], 2)
        self.assertEqual(kpis["Clientes_Con_Oportunidad"], 2)
        self.assertEqual(kpis["Incidencias"], 3)
        self.assertEqual(kpis["Deudas_Con_Oportunidad"], 3)
        self.assertAlmostEqual(kpis["Ingreso_Estimado_Total"], 15_000_000)
        self.assertAlmostEqual(kpis["Ingreso_Potencial_Total"], 19_000_000)
        self.assertAlmostEqual(kpis["Cobertura_Clientes"], 1.0)
        self.assertAlmostEqual(kpis["Cobertura_Deudas"], 1.0)
        self.assertAlmostEqual(kpis["Ingreso_Promedio_Cliente"], 7_500_000)

        tabla = resumen["por_oportunidad"].set_index("Oportunidad")
        self.assertEqual(int(tabla.loc["Liquidación Instantánea", "Incidencias"]), 1)
        self.assertEqual(int(tabla.loc["Liquidación Instantánea", "Deudas"]), 2)
        self.assertAlmostEqual(
            float(tabla.loc["Liquidación Instantánea", "Ingreso_Estimado"]),
            10_000_000,
        )
        self.assertAlmostEqual(
            float(tabla.loc["Depósito Extra", "Ingreso_Estimado"]),
            0.0,
        )
        self.assertAlmostEqual(
            float(tabla.loc["Depósito Extra", "Ingreso_Potencial"]),
            4_000_000,
        )
        self.assertAlmostEqual(
            float(tabla.loc["ContraOferta Viable", "Ingreso_Estimado"]),
            5_000_000,
        )
        self.assertAlmostEqual(
            float(tabla.loc["Total", "Ingreso_Estimado"]),
            15_000_000,
        )

        tipos = resumen["por_tipo_analisis"].set_index("Tipo_Analisis")
        self.assertAlmostEqual(
            float(tipos.loc["Tradicional", "Ingreso_Estimado"]),
            10_000_000,
        )
        self.assertAlmostEqual(
            float(tipos.loc["Crédito", "Ingreso_Estimado"]),
            5_000_000,
        )
        self.assertAlmostEqual(
            float(tipos.loc["General", "Ingreso_Estimado"]),
            0.0,
        )

    def test_ingreso_total_suma_maximos_por_unidad(self):
        unidad_1 = _unidad(
            unidad_id="U1",
            trad=[
                _oportunidad(
                    "Liquidación Instantánea",
                    ingreso=10_000_000,
                    tipo="Tradicional",
                )
            ],
            ingreso=10_000_000,
        )
        unidad_2 = _unidad(
            unidad_id="U2",
            etiqueta="Deuda D3",
            tipo="Deuda individual",
            deudas=["D3"],
            trad=[
                _oportunidad(
                    "ContraOferta Viable",
                    ingreso=5_000_000,
                    tipo="Tradicional",
                    valor=0.45,
                )
            ],
            ingreso=5_000_000,
            deudas_detalle=[_deuda("D3")],
        )
        df = pd.DataFrame([
            _cliente(
                "REF-MULTI",
                ingreso=10_000_000,
                portafolios=[unidad_1, unidad_2],
                deudas_analizadas=3,
            )
        ])
        resumen = calcular_resumen_oportunidades(df)

        self.assertAlmostEqual(
            resumen["kpis"]["Ingreso_Estimado_Total"], 15_000_000
        )
        self.assertAlmostEqual(
            resumen["kpis"]["Ingreso_Potencial_Total"], 15_000_000
        )
        self.assertEqual(resumen["kpis"]["Unidades_Con_Oportunidad"], 2)

    def test_dimensiones_y_asignacion_por_banco(self):
        resumen = calcular_resumen_oportunidades(self._datos())

        negociadores = resumen["por_negociador"].set_index("Valor")
        self.assertAlmostEqual(
            float(negociadores.loc["Nego A", "Ingreso_Estimado"]),
            10_000_000,
        )
        self.assertAlmostEqual(
            float(negociadores.loc["Nego B", "Ingreso_Estimado"]),
            5_000_000,
        )

        bancos = resumen["por_banco"].set_index("Valor")
        self.assertAlmostEqual(
            float(bancos.loc["BBVA Colombia", "Ingreso_Estimado"]),
            6_000_000,
        )
        self.assertAlmostEqual(
            float(bancos.loc["Itaú", "Ingreso_Estimado"]),
            9_000_000,
        )
        self.assertAlmostEqual(
            float(bancos["Ingreso_Estimado"].sum()),
            resumen["kpis"]["Ingreso_Estimado_Total"],
        )

        pipeline = resumen["por_estado_pipeline"].set_index("Valor")
        self.assertEqual(int(pipeline.loc["CERRADO", "Clientes"]), 1)
        self.assertEqual(int(pipeline.loc["NO_VIABLE_MEC", "Clientes"]), 1)

        actualizacion = resumen["por_estado_actualizacion"].set_index("Valor")
        self.assertEqual(int(actualizacion.loc["ACUERDO", "Deudas"]), 2)
        self.assertEqual(int(actualizacion.loc["DEPOSITO", "Deudas"]), 1)

        tipo_unidad = resumen["por_tipo_unidad"].set_index("Valor")
        self.assertEqual(
            int(tipo_unidad.loc["Portafolio Masivas", "Unidades"]), 1
        )
        self.assertEqual(
            int(tipo_unidad.loc["Deuda individual", "Unidades"]), 1
        )

        rangos = resumen["por_rango_descuento"].set_index("Valor")
        self.assertEqual(int(rangos.loc["30% - 40%", "Unidades"]), 1)
        self.assertEqual(int(rangos.loc["40% - 50%", "Unidades"]), 1)

    def test_ingreso_total_no_depende_del_orden_de_las_oportunidades(self):
        unidad = _unidad(
            trad=[
                _oportunidad(
                    "Depósito Extra", ingreso=4_000_000,
                    tipo="Tradicional", valor=1_000_000,
                ),
                _oportunidad(
                    "Liquidación Instantánea", ingreso=10_000_000,
                    tipo="Tradicional",
                ),
            ],
            ingreso=10_000_000,
        )
        resumen = calcular_resumen_oportunidades(
            pd.DataFrame([_cliente(portafolios=[unidad])])
        )
        self.assertAlmostEqual(
            resumen["kpis"]["Ingreso_Estimado_Total"], 10_000_000
        )
        maximos = resumen["detalle"][
            resumen["detalle"]["Es_Maximo_Unidad"]
        ]
        self.assertEqual(len(maximos), 1)
        self.assertEqual(
            maximos.iloc[0]["Oportunidad"], "Liquidación Instantánea"
        )

    def test_dimensiones_reconcilian_el_ingreso(self):
        resumen = calcular_resumen_oportunidades(self._datos())
        total_estimado = resumen["kpis"]["Ingreso_Estimado_Total"]
        total_potencial = resumen["kpis"]["Ingreso_Potencial_Total"]

        for clave in (
            "por_negociador",
            "por_prospecto_credito",
            "por_prospecto_tradicional",
            "por_estado_pipeline",
            "por_estado_actualizacion",
            "por_banco",
            "por_casa_cobro",
            "por_tipo_unidad",
            "por_rango_descuento",
        ):
            tabla = resumen[clave]
            self.assertAlmostEqual(
                float(tabla["Ingreso_Estimado"].sum()),
                total_estimado,
                msg=clave,
            )
            self.assertAlmostEqual(
                float(tabla["Ingreso_Potencial"].sum()),
                total_potencial,
                msg=clave,
            )

        for clave in ("por_oportunidad", "por_tipo_analisis"):
            tabla = resumen[clave]
            sin_total = tabla[~tabla["Es_Total"].fillna(False).astype(bool)]
            self.assertAlmostEqual(
                float(sin_total["Ingreso_Estimado"].sum()),
                total_estimado,
                msg=clave,
            )
            self.assertAlmostEqual(
                float(sin_total["Ingreso_Potencial"].sum()),
                total_potencial,
                msg=clave,
            )

    def test_cruces_de_oportunidad_y_estado(self):
        resumen = calcular_resumen_oportunidades(self._datos())

        cruce_pipeline = resumen["cruce_oportunidad_pipeline"].set_index(
            "Oportunidad"
        )
        self.assertEqual(
            int(cruce_pipeline.loc["Liquidación Instantánea", "CERRADO"]), 1
        )
        self.assertEqual(
            int(cruce_pipeline.loc["ContraOferta Viable", "NO_VIABLE_MEC"]), 1
        )

        cruce_act = resumen["cruce_oportunidad_actualizacion"].set_index(
            "Oportunidad"
        )
        self.assertEqual(
            int(cruce_act.loc["Liquidación Instantánea", "ACUERDO"]), 2
        )
        self.assertEqual(
            int(cruce_act.loc["ContraOferta Viable", "DEPOSITO"]), 1
        )

    def test_cliente_sin_oportunidades(self):
        cliente = _cliente(
            "REF-SIN",
            ingreso=0,
            portafolios=[_unidad(trad=[], cred=[], generales=[], ingreso=0)],
        )
        resumen = calcular_resumen_oportunidades(pd.DataFrame([cliente]))

        self.assertEqual(resumen["kpis"]["Clientes_Total"], 1)
        self.assertEqual(resumen["kpis"]["Clientes_Con_Oportunidad"], 0)
        self.assertAlmostEqual(
            resumen["kpis"]["Ingreso_Estimado_Total"], 0.0
        )
        self.assertTrue(resumen["por_oportunidad"].empty)

    def test_dataframe_vacio(self):
        resumen = calcular_resumen_oportunidades(pd.DataFrame())
        self.assertEqual(resumen["kpis"]["Clientes_Total"], 0)
        self.assertEqual(resumen["kpis"]["Incidencias"], 0)
        self.assertTrue(resumen["detalle"].empty)
        self.assertTrue(resumen["detalle_deudas"].empty)


class TestFiltrosResumen(unittest.TestCase):
    def _resultado(self) -> pd.DataFrame:
        base = {
            "Nombre_Cliente": "Cliente",
            "Negociador": "Nego A",
            "Prospecto_Credito": "Batch 1",
            "Num_Oportunidades": 1,
            "Oportunidades": ["Liquidación Instantánea"],
            "Es_Viable": True,
            "Descuento_Actual": 0.3,
            "PaB_Origen_Total": 100_000_000,
            "Ahorro_Neto": 10_000_000,
            "Tiene_Deudas_Liquidaciones": False,
            "Tradicional_Habilitado": True,
            "Credito_Habilitado": True,
            "Ingreso_Actual": 4_500_000,
        }
        return pd.DataFrame([
            {
                **base,
                "Referencia": "REF-A",
                "Prospecto_Tradicional": "Trad 1",
                "Estado_Credito": "CERRADO",
                "Estados_Actualizacion": ["ACUERDO"],
                "Bancos": ["BBVA Colombia"],
                "Casas_Cobro": ["ALIADO"],
            },
            {
                **base,
                "Referencia": "REF-B",
                "Negociador": "Nego B",
                "Prospecto_Tradicional": "Trad 2",
                "Estado_Credito": "NO_VIABLE_MEC",
                "Estados_Actualizacion": ["DEPOSITO", "Sin actualización"],
                "Bancos": ["Itaú"],
                "Casas_Cobro": ["OTRO"],
            },
            {
                **base,
                "Referencia": "REF-C",
                "Prospecto_Tradicional": "N/A",
                "Estado_Credito": "",
                "Estados_Actualizacion": ["Sin actualización"],
                "Bancos": ["BBVA Colombia", "Itaú"],
                "Casas_Cobro": ["ALIADO"],
            },
        ])

    def _filtrar(self, **kwargs) -> list[str]:
        base = {
            "solo_con_oportunidades": False,
            "orden": "Referencia (A-Z)",
        }
        base.update(kwargs)
        return filtrar_oportunidades_masivas(
            self._resultado(), **base
        )["Referencia"].tolist()

    def test_prospecto_tradicional(self):
        self.assertEqual(
            self._filtrar(prospectos_tradicionales=["Trad 1"]),
            ["REF-A"],
        )

    def test_estado_pipeline(self):
        self.assertEqual(
            self._filtrar(estados_pipeline=["NO_VIABLE_MEC"]),
            ["REF-B"],
        )
        self.assertEqual(
            self._filtrar(estados_pipeline=["Sin registro en Pipeline"]),
            ["REF-C"],
        )

    def test_estado_actualizacion(self):
        self.assertEqual(
            self._filtrar(estados_actualizacion=["ACUERDO"]),
            ["REF-A"],
        )
        self.assertEqual(
            self._filtrar(estados_actualizacion=["Sin actualización"]),
            ["REF-B", "REF-C"],
        )

    def test_banco_y_casa(self):
        self.assertEqual(
            self._filtrar(bancos=["Itaú"]),
            ["REF-B", "REF-C"],
        )
        self.assertEqual(
            self._filtrar(casas_cobro=["ALIADO"]),
            ["REF-A", "REF-C"],
        )

    def test_columnas_nuevas_ausentes_no_rompen_el_filtro(self):
        df = self._resultado().drop(
            columns=[
                "Prospecto_Tradicional",
                "Estado_Credito",
                "Estados_Actualizacion",
                "Bancos",
                "Casas_Cobro",
            ]
        )
        resultado = filtrar_oportunidades_masivas(
            df,
            prospectos_tradicionales=["Trad 1"],
            estados_pipeline=["CERRADO"],
            estados_actualizacion=["ACUERDO"],
            bancos=["BBVA Colombia"],
            casas_cobro=["ALIADO"],
            solo_con_oportunidades=False,
            orden="Referencia (A-Z)",
        )
        self.assertEqual(
            resultado["Referencia"].tolist(), ["REF-A", "REF-B", "REF-C"]
        )

    def test_filtro_de_oportunidad_restringe_el_resumen(self):
        unidad = _unidad(
            trad=[
                _oportunidad(
                    "Liquidación Instantánea", ingreso=10_000_000,
                    tipo="Tradicional",
                ),
                _oportunidad(
                    "Depósito Extra", ingreso=4_000_000,
                    tipo="Tradicional", valor=1_000_000,
                ),
            ],
            ingreso=10_000_000,
        )
        cliente = _cliente(portafolios=[unidad])
        cliente.update({
            "Num_Oportunidades": 2,
            "Oportunidades": ["Liquidación Instantánea", "Depósito Extra"],
            "Tradicional_Habilitado": True,
            "Credito_Habilitado": True,
            "Ahorro_Neto": 10_000_000,
            "Deudas_Detalle": [_deuda("D1"), _deuda("D2")],
        })
        filtrado = filtrar_oportunidades_masivas(
            pd.DataFrame([cliente]),
            oportunidades=["Liquidación Instantánea"],
            solo_con_oportunidades=True,
            orden="Referencia (A-Z)",
        )
        resumen = calcular_resumen_oportunidades(filtrado)
        tabla = resumen["por_oportunidad"].set_index("Oportunidad")

        self.assertEqual(
            int(tabla.loc["Liquidación Instantánea", "Incidencias"]), 1
        )
        self.assertEqual(int(tabla.loc["Depósito Extra", "Incidencias"]), 0)
        self.assertAlmostEqual(
            float(resumen["kpis"]["Ingreso_Estimado_Total"]), 10_000_000
        )


class TestUltimaActualizacionEnMasivas(unittest.TestCase):
    def _datos(self):
        asignacion = pd.DataFrame([
            {
                "Referencia": "REF-ACT",
                "Nombre_Cliente": "Cliente Actualizaciones",
                "Banco": "BBVA Colombia",
                "Id_Deuda": "D1",
                "PaB_Origen": 100_000_000.0,
                "Negociador": "Nego A",
                "Descuento_Esperado": 0.7,
                "Apartado_Neto": 10_000_000.0,
                "Pricing": 0.15,
            },
            {
                "Referencia": "REF-ACT",
                "Nombre_Cliente": "Cliente Actualizaciones",
                "Banco": "Itaú",
                "Id_Deuda": "D2",
                "PaB_Origen": 50_000_000.0,
                "Negociador": "Nego A",
                "Descuento_Esperado": 0.7,
                "Apartado_Neto": 10_000_000.0,
                "Pricing": 0.15,
            },
        ])
        masivas = pd.DataFrame([
            {
                "Id_Deuda": "D1",
                "PaB_Propuesta": 60_000_000,
                "Metadata": {"Fecha_Limite_Uso": pd.Timestamp("2026-12-31")},
                "Fecha_Masiva": pd.Timestamp("2026-11-01"),
                "Casa_Cobro": "ALIADO",
                "Es_Portafolio": False,
                "Fila_Sheets": 2,
            },
            {
                "Id_Deuda": "D2",
                "PaB_Propuesta": 30_000_000,
                "Metadata": {"Fecha_Limite_Uso": pd.Timestamp("2026-12-31")},
                "Fecha_Masiva": pd.Timestamp("2026-11-01"),
                "Casa_Cobro": "ALIADO",
                "Es_Portafolio": False,
                "Fila_Sheets": 3,
            },
        ])
        acts = pd.DataFrame([
            {
                "Id_Deuda": "D1",
                "Fecha_Act": pd.Timestamp("2026-10-01 10:00:00"),
                "Etiqueta_Act": "LLAMADA",
                "PaB_Actualizado": 80_000_000,
                "Correo": "a@x.com",
            },
            {
                "Id_Deuda": "D1",
                "Fecha_Act": pd.Timestamp("2026-11-01 10:00:00"),
                "Etiqueta_Act": "ACUERDO",
                "PaB_Actualizado": 60_000_000,
                "Correo": "a@x.com",
            },
            {
                "Id_Deuda": "D2",
                "Fecha_Act": pd.Timestamp("2026-11-02 10:00:00"),
                "Etiqueta_Act": "DEPOSITO",
                "PaB_Actualizado": 30_000_000,
                "Correo": "a@x.com",
            },
        ])
        return asignacion, masivas, acts

    def _calcular(self, acts):
        asignacion, masivas, _ = self._datos()
        return calcular_oportunidades_masivas_datos(
            asignacion_df=asignacion,
            masivas_df=masivas,
            pab_ideal={},
            saldos={
                "Saldos": {"REF-ACT": 100_000_000},
                "PorCobrar": {"REF-ACT": 0},
            },
            prospectos_credito={"REF-ACT": "Tradicional"},
            prospectos_tradicional=pd.DataFrame(),
            pipeline_credito=pd.DataFrame(),
            liquidaciones=set(),
            actualizaciones_df=acts,
            solo_masivas=True,
            incluir_acuerdos_robo=False,
            hoy=HOY,
        )

    def test_expone_ultima_actualizacion_sin_cambiar_el_pab(self):
        _, _, acts = self._datos()
        resultado = self._calcular(acts)
        fila = resultado.iloc[0]

        self.assertEqual(
            fila["Estados_Actualizacion"], ["ACUERDO", "DEPOSITO"]
        )
        self.assertAlmostEqual(
            float(fila["PaB_Actualizado_Total"]), 90_000_000
        )
        detalles = {d["Id_Deuda"]: d for d in fila["Deudas_Detalle"]}
        self.assertEqual(
            detalles["D1"]["Etiqueta_Actualizacion"], "ACUERDO"
        )
        self.assertEqual(
            detalles["D2"]["Etiqueta_Actualizacion"], "DEPOSITO"
        )
        self.assertEqual(
            pd.Timestamp(detalles["D1"]["Fecha_Actualizacion"]),
            pd.Timestamp("2026-11-01 10:00:00"),
        )

    def test_sin_actualizaciones_marca_sin_actualizacion(self):
        resultado = self._calcular(pd.DataFrame())
        fila = resultado.iloc[0]
        self.assertEqual(fila["Estados_Actualizacion"], ["Sin actualización"])
        detalles = fila["Deudas_Detalle"]
        self.assertTrue(
            all(
                deuda["Etiqueta_Actualizacion"] == ""
                for deuda in detalles
            )
        )


if __name__ == "__main__":
    unittest.main()
