import json
import unittest
from io import BytesIO

import pandas as pd
from pypdf import PdfReader, PdfWriter

from data.data_models import ArchivosSubidosSchema
from modules.constants import TIPO_ARCHIVO_SOPORTE_PAGO
from modules.gest_sols import (
    add_metadata_to_pdf,
    add_metadata_to_uploaded_pdf,
    generar_nombre_acuerdo_firmado,
    generar_nombre_soporte_pago,
    obtener_ids_deuda_validos,
)
from ui.archivos_components import _agregar_id_origen, _obtener_soportes_por_deuda


class TestNombresArchivos(unittest.TestCase):
    @staticmethod
    def _solicitud() -> pd.Series:
        return pd.Series({
            'ID_Solicitud': '4601900',
            'Cedula': '123456789',
            'JSON_Respuesta': [
                {'Id_Deuda': '1001', 'Monto_Propuesto': '100.000'},
                {'Id_Deuda': '1002', 'Monto_Propuesto': 0},
                {'Id_Deuda': '1003', 'Monto_Propuesto': 25000},
            ],
        })

    def test_ids_deuda_validos(self):
        self.assertEqual(
            obtener_ids_deuda_validos(solicitud=self._solicitud()),
            ['1001', '1003'],
        )

    def test_nombre_acuerdo_firmado(self):
        self.assertEqual(
            generar_nombre_acuerdo_firmado(solicitud=self._solicitud()),
            'APF_123456789_4601900_1001-1003.pdf',
        )

    def test_nombre_soporte_pago(self):
        self.assertEqual(
            generar_nombre_soporte_pago(
                cedula='123456789',
                ids_deuda=['1001', '1003'],
            ),
            'SOP_123456789_1001-1003.pdf',
        )


class TestMetadataPdf(unittest.TestCase):
    @staticmethod
    def _make_pdf_bytes() -> bytes:
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        buffer = BytesIO()
        writer.write(buffer)
        return buffer.getvalue()

    def test_metadata_general(self):
        metadata = {'Correo': 'persona@gobravo.com.co', 'Cedula': '123456789'}
        pdf = add_metadata_to_pdf(
            pdf_bytes=self._make_pdf_bytes(),
            metadata_name='Archivo_Info_Metadata',
            metadata=metadata,
        )
        reader = PdfReader(BytesIO(pdf))
        payload = json.loads(reader.metadata['/Archivo_Info_Metadata'])
        self.assertEqual(payload['Archivo_Info_Metadata'], metadata)
        self.assertIn('generated_at', payload)

    def test_metadata_acuerdo_conserva_llave_historica(self):
        metadata = {'ID_Solicitud': '4601900'}
        pdf = add_metadata_to_uploaded_pdf(
            pdf_bytes=self._make_pdf_bytes(),
            metadata=metadata,
        )
        reader = PdfReader(BytesIO(pdf))
        payload = json.loads(reader.metadata['/Acuerdo_Info_Metadata'])
        self.assertEqual(payload['agreement'], metadata)


class TestArchivosSubidosSchema(unittest.TestCase):
    def test_esquema_valido(self):
        df = pd.DataFrame([{
            'Id_Archivo': '123e4567-e89b-12d3-a456-426614174000',
            'Id_Archivo_Drive': 'drive-id',
            'Nombre_Archivo': 'SOP_123456789_1001.pdf',
            'Correo_Subida': 'persona@gobravo.com.co',
            'Referencia': 'REF-1',
            'Cedula': '123456789',
            'Fecha_Subida': pd.Timestamp('2026-10-30 10:30:00'),
            'Tipo_Archivo': 'Soporte de Pago',
            'Id_Solicitud': '',
            'Ids_Deuda': '1001',
        }])
        validado = ArchivosSubidosSchema.validate(df)
        self.assertEqual(len(validado), 1)


class TestSoportesArchivos(unittest.TestCase):
    def test_deduplica_ultimo_soporte_por_deuda(self):
        df = pd.DataFrame([
            {
                'Id_Archivo': 'soporte-1',
                'Id_Archivo_Drive': 'drive-1',
                'Nombre_Archivo': 'SOP_1.pdf',
                'Tipo_Archivo': TIPO_ARCHIVO_SOPORTE_PAGO,
                'Ids_Deuda': '1001-1002',
                'Fecha_Subida': pd.Timestamp('2026-10-20 10:00:00'),
                'Correo_Subida': 'persona@gobravo.com.co',
            },
            {
                'Id_Archivo': 'soporte-2',
                'Id_Archivo_Drive': 'drive-2',
                'Nombre_Archivo': 'SOP_2.pdf',
                'Tipo_Archivo': TIPO_ARCHIVO_SOPORTE_PAGO,
                'Ids_Deuda': '1002',
                'Fecha_Subida': pd.Timestamp('2026-10-21 10:00:00'),
                'Correo_Subida': 'persona@gobravo.com.co',
            },
        ])
        soportes = _obtener_soportes_por_deuda(archivos_df=df, ids_deuda=['1001', '1002'])
        self.assertEqual(soportes.loc['1001', 'Id_Archivo'], 'soporte-1')
        self.assertEqual(soportes.loc['1002', 'Id_Archivo'], 'soporte-2')

    def test_resuelve_solicitud_de_origen(self):
        df = pd.DataFrame([
            {
                'ID_Solicitud': '10',
                'Metadata_Solicitud': {'Id_Respuesta_Autom': '10'},
            },
            {
                'ID_Solicitud': '11',
                'Metadata_Solicitud': {'Id_Respuesta_Autom': '10'},
            },
            {
                'ID_Solicitud': '12',
                'Metadata_Solicitud': {},
            },
        ])
        resultado = _agregar_id_origen(df)
        self.assertEqual(resultado['Id_Solicitud_Origen'].tolist(), ['10', '10', '12'])


if __name__ == '__main__':
    unittest.main()
