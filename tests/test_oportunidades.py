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
    load_mes_operativo_asignacion,
)
from data.data_models import AsignacionSchema
from modules.oportunidades import (
    obtener_referencias_habilitadas,
    obtener_ultima_actualizacion_deuda,
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

    def test_asignacion_schema_incluye_fecha_cartera_y_banco(self):
        columnas = list(AsignacionSchema.to_schema().columns)
        self.assertIn("Fecha_Cartera", columnas)
        self.assertIn("Banco", columnas)


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


class TestMesOperativoAsignacion(unittest.TestCase):
    def _fake_st(self, files: list[dict]):
        fake_st = MagicMock()
        fake_st.session_state = {"google_drive_service": MagicMock()}
        fake_st.session_state["google_drive_service"].list_folder_contents.return_value = files
        fake_st.secrets = {"google_drive": {"folder_asignaciones": "folder-id"}}
        return fake_st

    def test_usa_el_archivo_mas_reciente(self):
        files = [
            {"id": "1", "name": "Asignacion-Oct25.xlsx"},
            {"id": "2", "name": "Asignacion-Feb26.xlsx"},
        ]
        fake_st = self._fake_st(files)
        with patch("data.data_loader.st", fake_st):
            mes_operativo = load_mes_operativo_asignacion.__wrapped__()

        self.assertEqual(mes_operativo, pd.Timestamp("2026-02-01"))

    def test_sin_archivos_cae_al_fallback(self):
        fake_st = self._fake_st([])
        fallback = pd.Timestamp("2026-01-01")
        with patch("data.data_loader.st", fake_st), patch(
            "data.data_loader.getMesOperativo", return_value=fallback
        ):
            mes_operativo = load_mes_operativo_asignacion.__wrapped__()

        self.assertEqual(mes_operativo, fallback)

    def test_nombre_invalido_cae_al_fallback(self):
        fake_st = self._fake_st([{"id": "1", "name": "Asignacion.xlsx"}])
        fallback = pd.Timestamp("2026-01-01")
        with patch("data.data_loader.st", fake_st), patch(
            "data.data_loader.getMesOperativo", return_value=fallback
        ):
            mes_operativo = load_mes_operativo_asignacion.__wrapped__()

        self.assertEqual(mes_operativo, fallback)


if __name__ == "__main__":
    unittest.main()
