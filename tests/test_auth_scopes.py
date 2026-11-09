"""Tests de los scopes OAuth del App.

El App comparte el client_id con el MCP de Google Workspace. Estos tests fijan
el comportamiento que evita el error "Scope has changed" cuando el token trae
scopes adicionales, sin aceptar un token al que le falten permisos del App.
"""

import os
import unittest
from unittest.mock import patch

from oauthlib.oauth2 import WebApplicationClient

from core.auth_scopes import (
    RELAX_TOKEN_SCOPE_ENV,
    configure_oauthlib_for_shared_client,
    missing_scopes,
    normalize_scope_list,
)

APP_SCOPES = ["openid", "scope.email", "scope.drive", "scope.gmail"]


class TestConfiguracionOauthlib(unittest.TestCase):
    def test_configura_relax_token_scope(self):
        with patch.dict(os.environ, {}, clear=True):
            configure_oauthlib_for_shared_client()
            self.assertEqual(os.environ.get(RELAX_TOKEN_SCOPE_ENV), "1")

    def test_oauthlib_acepta_token_con_scopes_extra(self):
        with patch.dict(os.environ, {RELAX_TOKEN_SCOPE_ENV: "1"}, clear=False):
            client = WebApplicationClient("client-id")
            client.parse_request_body_response(
                '{"access_token": "fake", "token_type": "Bearer", '
                '"expires_in": 3600, "scope": "scope.email scope.drive '
                'scope.gmail scope.extra"}',
                scope=APP_SCOPES,
            )
            self.assertEqual(
                client.token["scope"],
                ["scope.email", "scope.drive", "scope.gmail", "scope.extra"],
            )


class TestNormalizacionScopes(unittest.TestCase):
    def test_normaliza_cadena(self):
        self.assertEqual(
            normalize_scope_list("scope.a scope.b"),
            ["scope.a", "scope.b"],
        )

    def test_normaliza_lista(self):
        self.assertEqual(
            normalize_scope_list(["scope.a", "scope.b"]),
            ["scope.a", "scope.b"],
        )

    def test_normaliza_vacio(self):
        self.assertEqual(normalize_scope_list(None), [])
        self.assertEqual(normalize_scope_list(""), [])


class TestScopesFaltantes(unittest.TestCase):
    def test_no_faltan_scopes(self):
        self.assertEqual(
            missing_scopes(
                ["scope.a", "scope.b", "scope.extra"],
                ["scope.a", "scope.b"],
            ),
            [],
        )

    def test_detecta_scopes_faltantes(self):
        self.assertEqual(
            missing_scopes(["scope.a"], ["scope.a", "scope.b"]),
            ["scope.b"],
        )

    def test_sin_scope_en_el_token_no_reporta_faltantes(self):
        # Google omite el campo `scope` cuando coincide con lo solicitado.
        self.assertEqual(missing_scopes([], ["scope.a", "scope.b"]), [])
