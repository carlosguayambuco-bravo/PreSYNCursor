import unittest
from io import BytesIO

from pypdf import PdfReader, PdfWriter

from modules.forms import obtener_descuento_optimo
from modules.gest_sols import unir_pdfs


class TestObtenerDescuentoOptimo(unittest.TestCase):
    pass


class TestUnirPdfs(unittest.TestCase):
    @staticmethod
    def _make_pdf_bytes() -> bytes:
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        buffer = BytesIO()
        writer.write(buffer)
        return buffer.getvalue()

    def test_unir_pdfs_sin_contrasenia_no_falla(self):
        pdf_bytes = self._make_pdf_bytes()
        merged = unir_pdfs(archivos_pdf=[BytesIO(pdf_bytes), BytesIO(pdf_bytes)])
        self.assertGreater(len(merged), 0)
        reader = PdfReader(BytesIO(merged))
        self.assertEqual(len(reader.pages), 2)

    def test_unir_pdfs_mixto_encriptado_y_no_encriptado(self):
        pdf_bytes = self._make_pdf_bytes()

        encrypted_writer = PdfWriter()
        encrypted_writer.add_blank_page(width=80, height=80)
        encrypted_buffer = BytesIO()
        encrypted_writer.encrypt("secret")
        encrypted_writer.write(encrypted_buffer)
        encrypted_bytes = encrypted_buffer.getvalue()

        merged = unir_pdfs(
            archivos_pdf=[BytesIO(pdf_bytes), BytesIO(encrypted_bytes)],
            contrasenia_inicial="secret",
        )
        self.assertGreater(len(merged), 0)
        reader = PdfReader(BytesIO(merged))
        self.assertEqual(len(reader.pages), 2)