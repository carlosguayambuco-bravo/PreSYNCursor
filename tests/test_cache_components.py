"""Tests del helper de reinicio de caches de Streamlit.

Estos tests no acceden a Google Sheets ni a Metabase y no requieren una sesión
real de Streamlit: el estado de sesión se reemplaza por un diccionario.
"""

import unittest
from unittest.mock import MagicMock, patch

import ui.cache_components as cache_components


class TestReiniciarCaches(unittest.TestCase):
    def test_limpia_todas_las_funciones_y_llaves_existentes(self):
        cache_uno = MagicMock()
        cache_dos = MagicMock()
        estado = {
            'masivas_df': object(),
            'local_masivas_changes': object(),
            'otra_llave': object(),
        }

        with patch.object(cache_components.st, 'session_state', estado):
            cache_components.reiniciar_caches(
                funciones=[cache_uno, cache_dos],
                claves_session_state=[
                    'masivas_df',
                    'local_masivas_changes',
                    'llave_inexistente',
                ],
            )

        cache_uno.clear.assert_called_once_with()
        cache_dos.clear.assert_called_once_with()
        self.assertEqual(list(estado.keys()), ['otra_llave'])

    def test_no_falla_sin_funciones_ni_llaves(self):
        estado = {'otra_llave': object()}

        with patch.object(cache_components.st, 'session_state', estado):
            cache_components.reiniciar_caches(
                funciones=[],
                claves_session_state=[],
            )

        self.assertEqual(list(estado.keys()), ['otra_llave'])


if __name__ == '__main__':
    unittest.main()
