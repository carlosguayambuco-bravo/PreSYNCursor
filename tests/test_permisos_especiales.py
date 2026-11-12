"""Tests de los roles y permisos especiales de usuarios.

La hoja ``Usuarios`` del spreadsheet de Configs controla:
- ``Cargo_Interno``: rol que reemplaza el rol asignado por el headcount.
- ``Permisos``: permisos adicionales por correo.

Estos tests fijan la normalización del rol, la tolerancia a columnas
adicionales y los fallbacks cuando los datos están incompletos.
"""

import unittest
from typing import get_args
from unittest.mock import patch

import pandas as pd

import core.auth as core_auth
import data.data_loader as data_loader
from core.permissions import DEFAULT_PERMISSIONS, PERMISSIONS_DICT
from core.users import User
from modules.constants import PERMITTED_USERS


class TestNormalizacionCargoInterno(unittest.TestCase):
    def test_acepta_roles_permitidos_sin_importar_mayusculas_ni_espacios(self):
        for rol in get_args(PERMITTED_USERS):
            self.assertEqual(
                data_loader._normalizar_cargo_interno(f"  {rol.upper()}  "),
                rol,
            )

    def test_descarta_cargos_invalidos_y_vacios(self):
        self.assertIsNone(data_loader._normalizar_cargo_interno("Administrador"))
        self.assertIsNone(data_loader._normalizar_cargo_interno(""))
        self.assertIsNone(data_loader._normalizar_cargo_interno(None))
        self.assertIsNone(data_loader._normalizar_cargo_interno(pd.NA))


class TestRolesEspeciales(unittest.TestCase):
    def test_construye_mapa_normalizado_y_descarta_invalidos(self):
        usuarios_df = pd.DataFrame({
            'Correo': [
                '  Admin@Empresa.com ',
                'leader@empresa.com',
                'invalido@empresa.com',
                'vacio@empresa.com',
            ],
            'Cargo_Interno': [' ADMIN ', 'Leader', 'Administrador', None],
            'Permisos': [None, 'ver_logs', None, None],
        })

        resultado = data_loader._construir_roles_especiales(usuarios_df)

        self.assertEqual(
            resultado,
            {'admin@empresa.com': 'admin', 'leader@empresa.com': 'leader'},
        )

    def test_devuelve_vacio_si_no_existe_la_columna(self):
        usuarios_df = pd.DataFrame({
            'Correo': ['admin@empresa.com'],
            'Permisos': [None],
        })

        self.assertEqual(data_loader._construir_roles_especiales(usuarios_df), {})

    def test_devuelve_vacio_con_dataframe_vacio(self):
        self.assertEqual(data_loader._construir_roles_especiales(pd.DataFrame()), {})


class TestLoadersPermisos(unittest.TestCase):
    @staticmethod
    def _fake_service(df: pd.DataFrame):
        class FakeSheetsService:
            def get_sheet_as_dataframe(self, spreadsheet_id: str, worksheet_name: str):
                return df.copy()

        return FakeSheetsService()

    def test_load_permisos_especiales_lee_cargo_interno(self):
        usuarios_df = pd.DataFrame({
            'Correo': ['Admin@Empresa.com'],
            'Cargo_Interno': ['Admin'],
            'Permisos': [None],
        })

        with patch.object(data_loader.st, "session_state", {
            "google_sheets_service": self._fake_service(usuarios_df),
        }):
            resultado = data_loader.load_permisos_especiales.__wrapped__()

        self.assertEqual(resultado, {'admin@empresa.com': 'admin'})

    def test_load_special_user_permissions_tolera_columnas_extra(self):
        usuarios_df = pd.DataFrame({
            'Correo': ['Admin@Empresa.com', 'sinpermisos@empresa.com'],
            'Permisos': ['subida_formulario, ver_logs', None],
            'Cargo_Interno': ['admin', 'nego'],
        })

        with patch.object(data_loader.st, "session_state", {
            "google_sheets_service": self._fake_service(usuarios_df),
        }):
            resultado = data_loader.load_special_user_permissions.__wrapped__()

        self.assertEqual(
            resultado['admin@empresa.com'],
            [PERMISSIONS_DICT['subida_formulario'], PERMISSIONS_DICT['ver_logs']],
        )
        self.assertEqual(resultado['sinpermisos@empresa.com'], [])

    def test_load_special_user_permissions_sin_columna_permisos_devuelve_vacio(self):
        usuarios_df = pd.DataFrame({
            'Correo': ['admin@empresa.com'],
            'Cargo_Interno': ['admin'],
        })

        with patch.object(data_loader.st, "session_state", {
            "google_sheets_service": self._fake_service(usuarios_df),
        }):
            resultado = data_loader.load_special_user_permissions.__wrapped__()

        self.assertEqual(resultado, {})


class TestGetUserRole(unittest.TestCase):
    @staticmethod
    def _headcount(es_negociador: bool = True, nombre_empleo: str = 'Negociador'):
        return pd.DataFrame([{
            'Correo': 'usuario@empresa.com',
            'ID_Empleado': '1',
            'Nombre': 'Usuario Headcount',
            'Nombre_Empleo': nombre_empleo,
            'Lider': 'Lider',
            'Estado': 'Activo',
            'Cedula': '123456789',
            'Es_Negociador': es_negociador,
        }])

    def test_rol_especial_reemplaza_el_rol_del_headcount(self):
        session_state = {}

        with patch.object(
            core_auth, 'load_headcount_negociacion', return_value=self._headcount()
        ), patch.object(
            core_auth, 'load_permisos_especiales',
            return_value={'usuario@empresa.com': 'admin'},
        ), patch.object(core_auth.st, 'session_state', session_state):
            rol = core_auth.get_user_role('Usuario@Empresa.com')

        self.assertEqual(rol, 'admin')
        self.assertEqual(session_state['user_name'], 'Usuario Headcount')

    def test_sin_rol_especial_usa_el_rol_del_headcount(self):
        session_state = {}

        with patch.object(
            core_auth, 'load_headcount_negociacion', return_value=self._headcount()
        ), patch.object(
            core_auth, 'load_permisos_especiales', return_value={}
        ), patch.object(core_auth.st, 'session_state', session_state):
            rol = core_auth.get_user_role('usuario@empresa.com')

        self.assertEqual(rol, 'nego')

    def test_usuario_fuera_del_headcount_puede_tener_rol_especial(self):
        session_state = {}

        with patch.object(
            core_auth, 'load_headcount_negociacion', return_value=pd.DataFrame()
        ), patch.object(
            core_auth, 'load_permisos_especiales',
            return_value={'externo@empresa.com': 'executive'},
        ), patch.object(core_auth.st, 'session_state', session_state):
            rol = core_auth.get_user_role('externo@empresa.com')

        self.assertEqual(rol, 'executive')

    def test_create_user_from_session_guarda_el_nombre_de_google(self):
        session_state = {"credentials": {"token": "fake"}}

        with patch.object(
            core_auth,
            'get_user_info_from_credentials',
            return_value={'email': 'externo@empresa.com', 'name': 'Nombre Google'},
        ), patch.object(
            core_auth, 'get_user_role', return_value='executive'
        ), patch.object(
            core_auth, 'User'
        ) as mock_user, patch.object(core_auth.st, 'session_state', session_state):
            core_auth.create_user_from_session()

        self.assertEqual(session_state['user_email'], 'externo@empresa.com')
        self.assertEqual(session_state['user_name'], 'Nombre Google')
        mock_user.assert_called_once()


class TestUserBuildPermits(unittest.TestCase):
    def test_busca_permisos_especiales_sin_importar_mayusculas(self):
        user = User.__new__(User)
        user.email = 'Admin@Empresa.com'
        user.role = 'nego'

        with patch(
            'core.users.load_special_user_permissions',
            return_value={'admin@empresa.com': [PERMISSIONS_DICT['ver_logs']]},
        ):
            user.build_permits()

        self.assertEqual(user.permits, [PERMISSIONS_DICT['ver_logs']])

    def test_sin_permisos_especiales_usa_los_del_rol(self):
        user = User.__new__(User)
        user.email = 'nego@empresa.com'
        user.role = 'nego'

        with patch(
            'core.users.load_special_user_permissions',
            return_value={'nego@empresa.com': []},
        ):
            user.build_permits()

        self.assertEqual(user.permits, DEFAULT_PERMISSIONS['nego'])
        self.assertIn(PERMISSIONS_DICT['subida_formulario'], user.permits)


if __name__ == '__main__':
    unittest.main()
