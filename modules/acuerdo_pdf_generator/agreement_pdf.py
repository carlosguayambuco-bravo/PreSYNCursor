"""Generador de acuerdos de pago para Streamlit Cloud."""
from __future__ import annotations

import copy
import io
import json
import os
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Union

import reportlab
from pypdf import PdfReader, PdfWriter
from reportlab.graphics import renderPDF
from reportlab.lib import colors
from reportlab.lib.colors import Color, HexColor
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph, Table, TableStyle
from svglib.svglib import svg2rlg
import pandas as pd


DEFAULT_CONSIDERATIONS = (
    "Realice el pago dentro de la fecha límite acordada.",
    "Reporte cualquier novedad o error a su ejecutivo de cuenta.",
)
DEFAULT_COLORS = {"primary": "#5B3DB6", "border": "#D9D0F2", "text": "#27213E", "accent": "#16A971", "muted": "#756D8A", "card": "#FFFFFF"}


def generate_payment_agreement_pdf(
    agreement: Mapping[str, Any], *, font: str = "Vera",
    colors_config: Optional[Mapping[str, str]] = None,
    considerations: Optional[Sequence[str]] = None,
    assets_dir: Optional[Union[str, os.PathLike[str]]] = None,
    orientation: str = "horizontal",
    alpha: float = 0.10,
) -> bytes:
    """Retorna el PDF del acuerdo como bytes.

    Parameters
    ----------
    agreement:
        Serie de pandas o mapeo con las claves indicadas en el README.
    font:
        ``"Vera"`` (por defecto), fuente estándar de ReportLab o ruta a TTF.
    colors_config:
        Sobrescribe colores ``primary``, ``border``, ``text``, ``accent``,
        ``muted`` y ``card`` mediante valores hexadecimales.
    orientation:
        ``"horizontal"`` (Carta horizontal, predeterminado) o ``"vertical"``
        (Carta vertical).
    """
    normalized_orientation = orientation.strip().lower()
    aliases = {"horizontal": "horizontal", "landscape": "horizontal", "vertical": "vertical", "portrait": "vertical"}
    if normalized_orientation not in aliases:
        raise ValueError("orientation debe ser 'horizontal' o 'vertical'.")
    normalized_orientation = aliases[normalized_orientation]
    source = _as_mapping(agreement)
    debts = _extract_debts(source)
    data = _extract_agreement(source, debts)
    moment = pd.Timestamp.now("America/Bogota")
    page_size = landscape(letter) if normalized_orientation == "horizontal" else letter
    normal_font, bold_font = _resolve_fonts(font)
    stream = io.BytesIO()
    pdf = _AgreementCanvas(stream, page_size, _palette(colors_config), normal_font, bold_font, Path(assets_dir) if assets_dir else Path(__file__).parent / "assets", normalized_orientation, alpha)
    pdf.draw_document(data, debts, tuple(considerations or DEFAULT_CONSIDERATIONS), moment)
    pdf.save()
    return _embed_metadata(stream.getvalue(), {"agreement": agreement, "generated_at": moment.isoformat()})


class _AgreementCanvas(Canvas):
    def __init__(self, stream: io.BytesIO, page_size: tuple[float, float], palette: Mapping[str, Color], font: str, bold_font: str, assets: Path, orientation: str, alpha: float = 0.10) -> None:
        super().__init__(stream, pagesize=page_size, pageCompression=1, pdfVersion=(1, 4))
        self.width, self.height = page_size
        self.palette, self.font, self.bold_font = palette, font, bold_font
        self.assets, self.orientation = assets, orientation
        self.watermark = _load_svg(assets / "water_mark.svg")
        self.alpha = alpha

    def card(self, x: float, y: float, width: float, height: float, radius: float = 11, fill: Optional[Color] = None) -> None:
        """Dibuja una tarjeta y recorta la marca de agua a sus límites."""
        self.saveState()
        clip = self.beginPath(); clip.roundRect(x, y, width, height, radius)
        self.clipPath(clip, stroke=0, fill=0)
        self.setFillColor(fill or self.palette["card"]); self.rect(x, y, width, height, stroke=0, fill=1)
        if self.watermark and self.orientation != "horizontal":
            drawing = copy.deepcopy(self.watermark)
            scale = width / float(drawing.width)
            drawing.scale(scale, scale)
            self.setFillAlpha(self.alpha)
            self.setStrokeAlpha(self.alpha)
            _set_drawing_alpha(drawing, self.alpha)
            renderPDF.draw(drawing, self, x, y + (height - drawing.height * scale) / 2)
        self.restoreState()
        self.setStrokeColor(self.palette["border"]); self.setLineWidth(1.15)
        self.roundRect(x, y, width, height, radius, stroke=1, fill=0)

    def draw_document(self, data: Mapping[str, Any], debts: list[dict[str, Any]], considerations: Sequence[str], moment: datetime) -> None:
        margin, content_w = 26, self.width - 52
        if self.orientation == "horizontal":
            self._page_watermark()
        y = self._header(margin)
        y = self._identity(data, margin, y, content_w)
        y = self._summary(data, debts, margin, y - 14, content_w) - 14
        per_page = 7 if self.orientation == "horizontal" else 12
        chunks = [debts[index:index + per_page] for index in range(0, len(debts), per_page)] or [[]]
        for page_index, chunk in enumerate(chunks):
            if page_index:
                self._footer(data, moment); self.showPage()
                if self.orientation == "horizontal":
                    self._page_watermark()
                y = self._header(margin, compact=True)
            if self.orientation == "horizontal":
                table_w, gap = content_w * .63, 12
                y_after_table = self._debt_table(chunk, margin, y, table_w)
                comment_h = max(90, y - y_after_table)
                self._comment(data["executive_comment"], margin + table_w + gap, y, content_w - table_w - gap, comment_h)
                recommendations_h = max(65, 30 + 14 * len(considerations))
                y = min(y_after_table, y - comment_h) - 14
                self._considerations(considerations, margin, y, content_w, recommendations_h)
                y -= recommendations_h
            else:
                y = self._debt_table(chunk, margin, y, content_w)

        if self.orientation == "vertical":
            box_h = max(70, 30 + 14 * len(considerations))
            if y - 16 - box_h < 55:
                self._footer(data, moment); self.showPage(); y = self._header(margin, compact=True)
            self._considerations(considerations, margin, y - 16, content_w, box_h)
        self._footer(data, moment)

    def _header(self, margin: float, compact: bool = False) -> float:
        y = self.height - 34
        self.setFillColor(self.palette["primary"]); self.setFont(self.bold_font, 17 if not compact else 13)
        self.drawString(margin, y, "ACUERDO DE PAGO - ALIANZAS")
        if not compact:
            self.setFillColor(self.palette["muted"]); self.setFont(self.font, 8)
            self.drawString(margin, y - 15, "Resumen y condiciones del acuerdo de pago")
            self._logo(self.width - 136, y - 19, 106, 38)
            return y - 30
        return y - 16

    def _identity(self, data: Mapping[str, Any], x: float, y: float, width: float) -> float:
        height, ally_w = 82, min(155, width * .24)
        main_w = width - ally_w - 10
        self.card(x, y - height, main_w, height); self.card(x + main_w + 10, y - height, ally_w, height)
        columns = (main_w * .27, main_w * .50, main_w * .23)
        cursor = x
        for column in columns[:-1]:
            cursor += column; self.setStrokeColor(self.palette["border"]); self.line(cursor, y - height, cursor, y)
        emphasis_size = 13.5 if self.orientation == "horizontal" else 9
        self._field("REFERENCIA", data["reference"], x + 10, y, columns[0] - 18)
        self._field("CLIENTE", data["customer_name"], x + columns[0] + 10, y, columns[1] - 18, value_size=emphasis_size)
        self._field("DOCUMENTO", data["document"], x + columns[0] + columns[1] + 10, y, columns[2] - 18, value_size=emphasis_size)
        ally_x = x + main_w + 10
        # Casa de Cobro ahora ocupa todo el alto disponible (height = 82) de forma centrada
        self._center_field("CASA DE COBRO", data["settlement_partner"], ally_x, y, ally_w, height, important=True, value_size=emphasis_size)
        return y - height

    def _summary(self, data: Mapping[str, Any], debts: list[dict[str, Any]], x: float, y: float, width: float) -> float:
        height, left_w = 77, width * .60
        self.card(x, y - height, width, height)
        self.setStrokeColor(self.palette["border"]); self.line(x + left_w, y - height, x + left_w, y); self.line(x + left_w, y - 38, x + width, y - 38)
        total = sum((debt["amount"] for debt in debts), Decimal("0"))
        centered = self.orientation == "horizontal"
        self._field("MONTO TOTAL DE PAGO", _currency(total), x + 13, y, left_w - 24, important=True, value_size=21, value_alignment=1 if centered else 0)
        self._field("FORMA DE PAGO", data["payment_method"], x + left_w + 12, y, width - left_w - 20, important=True, value_size=10, label_offset=15, value_bottom_offset=34, value_alignment=1 if centered else 0)
        self._field("FECHA LÍMITE DE PAGO", _format_date(data["due_date"]), x + left_w + 12, y - 38, width - left_w - 20, important=True, value_size=10, label_offset=15, value_bottom_offset=34, value_alignment=1 if centered else 0)
        return y - height

    def _debt_table(self, debts: list[dict[str, Any]], x: float, y: float, width: float) -> float:
        title_h, row_h = 25, 23
        rows = debts or [{"id": "-", "credit_number": "-", "bank": "-"}]
        height = title_h + row_h * (len(rows) + 1)
        self.card(x, y - height, width, height)
        self.setFillColor(self.palette["primary"]); self.setFont(self.bold_font, 11)
        self.drawCentredString(x + width / 2, y - 16, "RELACIÓN DE DEUDAS")
        
        # Columna BANCO integrada para ambas orientaciones entre ID DEUDA y NÚMERO CRÉDITO
        table_data = [["ID DEUDA", "BANCO", "NÚMERO CRÉDITO"]] + [[d["id"], d["bank"], d["credit_number"]] for d in rows]
        column_widths = [width * .25, width * .35, width * .40]

        table = Table(table_data, colWidths=column_widths, rowHeights=row_h)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), self.palette["primary"]), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), self.bold_font), ("FONTNAME", (0, 1), (-1, -1), self.font),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5), ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), .35, self.palette["border"]), ("BACKGROUND", (0, 1), (-1, -1), colors.white),
        ]))
        table.wrapOn(self, width, height - title_h); table.drawOn(self, x, y - height)
        return y - height

    def _considerations(self, items: Sequence[str], x: float, y: float, width: float, height: float) -> None:
        self.card(x, y - height, width, height, fill=HexColor("#FFF8F7"))
        self.setFillColor(self.palette["primary"]); self.setFont(self.bold_font, 10)
        self.drawString(x + 12, y - 18, "RECOMENDACIONES")
        style = ParagraphStyle("consideration", fontName=self.font, fontSize=8.2, leading=10.2, textColor=self.palette["text"])
        cursor = y - 33
        for index, item in enumerate(items, 1):
            paragraph = Paragraph(_escape(f"{index}. {item}"), style); _, p_h = paragraph.wrap(width - 24, height)
            paragraph.drawOn(self, x + 14, cursor - p_h); cursor -= p_h + 4

    def _comment(self, value: Any, x: float, y: float, width: float, height: float) -> None:
        self.card(x, y - height, width, height, fill=HexColor("#FFF8F7"))
        self.setFillColor(self.palette["primary"]); self.setFont(self.bold_font, 10)
        self.drawString(x + 12, y - 18, "COMENTARIO DEL EJECUTIVO")
        style = ParagraphStyle("executive-comment", fontName=self.font, fontSize=8.2, leading=10.2, textColor=self.palette["text"])
        paragraph = Paragraph(_escape(str(value or "Sin Comentario adicional, priorizar el pago")), style)
        _, p_h = paragraph.wrap(width - 24, height - 35)
        paragraph.drawOn(self, x + 14, y - 33 - p_h)

    def _field(self, label: str, value: Any, x: float, top: float, width: float, important: bool = False, value_size: float = 9, label_offset: float = 18, value_bottom_offset: Optional[float] = None, value_alignment: int = 0) -> None:
        self.setFillColor(self.palette["muted"]); self.setFont(self.font, 7)
        self.drawString(x, top - label_offset, label)
        style = ParagraphStyle("field", fontName=self.bold_font if important else self.font, fontSize=value_size, leading=value_size * 1.16, textColor=self.palette["text"], alignment=value_alignment) # type: ignore
        paragraph = Paragraph(_escape(str(value or "-")), style); _, p_h = paragraph.wrap(width, 31)
        paragraph.drawOn(self, x, top - value_bottom_offset if value_bottom_offset is not None else top - 31 - p_h)

    def _page_watermark(self) -> None:
        """Dibuja la marca de agua de fondo sin invadir encabezado ni pie."""
        if not self.watermark:
            return
        self.saveState()
        lower, upper = 52, self.height - 108
        path = self.beginPath(); path.rect(0, lower, self.width, upper - lower)
        self.clipPath(path, stroke=0, fill=0)
        drawing = copy.deepcopy(self.watermark)
        scale = self.width / float(drawing.width)
        drawing.scale(scale, scale)
        self.setFillAlpha(self.alpha); self.setStrokeAlpha(self.alpha)
        _set_drawing_alpha(drawing, self.alpha)
        renderPDF.draw(drawing, self, 0, lower + (upper - lower - drawing.height * scale) / 2)
        self.restoreState()

    def _center_field(self, label: str, value: Any, x: float, top: float, width: float, height: float, important: bool = False, value_size: float = 7.4) -> None:
        self.setFillColor(self.palette["muted"]); self.setFont(self.font, 6.6)
        self.drawCentredString(x + width / 2, top - 14, label)
        style = ParagraphStyle("center-field", fontName=self.font if not important else self.bold_font, fontSize=value_size, leading=value_size * 1.16, textColor=self.palette["text"], alignment=1)
        paragraph = Paragraph(_escape(str(value or "-")), style); _, p_h = paragraph.wrap(width - 16, height - 20)
        content_bottom = top - height + 5
        available_height = height - 25
        paragraph.drawOn(self, x + 8, content_bottom + max(0, (available_height - p_h) / 2))

    def _logo(self, x: float, y: float, width: float, height: float) -> None:
        logo = self.assets / "logo.png"
        if not logo.is_file(): return
        image = ImageReader(str(logo)); source_w, source_h = image.getSize(); scale = min(width / source_w, height / source_h)
        self.drawImage(image, x + (width - source_w * scale) / 2, y + (height - source_h * scale) / 2, source_w * scale, source_h * scale, mask="auto")

    def _footer(self, data: Mapping[str, Any], moment: datetime) -> None:
        self.setStrokeColor(self.palette["border"]); self.line(26, 38, self.width - 26, 38)
        self.setFillColor(self.palette["muted"]); self.setFont(self.font, 7)
        self.drawCentredString(self.width * .25, 25, f"Generado el {moment.strftime('%d/%m/%Y %H:%M')}")
        self.drawCentredString(self.width * .75, 25, f"Ejecutivo: {data['executive'] or '-'}")


def _extract_agreement(source: Mapping[str, Any], debts: list[dict[str, Any]]) -> dict[str, Any]:
    metadata = _mapping_value(source, "Metadata_Solicitud")
    return {"reference": _find(source, "Referencia", "Id del Cliente"), "customer_name": _find(metadata, "Nombre_Cliente", "Nombre del Cliente"), "document": _find(source, "Cedula", "Documento del Cliente"), "payment_method": _find(metadata, "Metodo_Pago", "Forma de Pago"), "due_date": _find(source, "Fecha_Limite_Pago", "Fecha Limite de Pago"), "settlement_partner": _find(source, "Casa_Cobro", "Aliado de Liquidación"), "executive": _find(source, "Ejecutivo"), "executive_comment": _find(metadata, "Comentario_Ejecutivo", "Comentario Ejecutivo"), "banks": list(dict.fromkeys(debt["bank"] for debt in debts if debt["bank"] != "-"))}


def _extract_debts(source: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = _find(source, "Deudas", "Detalle de Deudas", "JSON_Respuesta", "Respuestas_Deuda", "debt_details")
    if isinstance(raw, str):
        try: raw = json.loads(raw)
        except json.JSONDecodeError: return []
    if isinstance(raw, Mapping): raw = raw.get("deudas", raw.get("debts", [raw]))
    if not isinstance(raw, (list, tuple)): return []
    debts = []
    for item in raw:
        if not isinstance(item, Mapping): continue
        response, request = _mapping_value(item, "JSON_Respuesta"), _mapping_value(item, "Datos_Solicitud")
        debts.append({"id": str(_find(response, "Id_Deuda", "Id de la Deuda") or _find(item, "Id_Deuda", "Id de la Deuda") or "-"), "credit_number": str(_find(response, "Numero_Credito", "Numero de Credito de la Deuda") or _find(item, "Numero_Credito", "Numero de Credito de la Deuda") or "-"), "bank": str(_find(request, "Banco") or _find(response, "Banco") or _find(item, "Banco", "Banco de la Deuda") or "-"), "amount": _amount(_find(response, "Monto_Propuesto", "Monto a Pagar por la Deuda") or _find(item, "Monto_Propuesto", "Monto a Pagar por la Deuda")), "installments": str(_find(response, "Num_Cuotas", "Plazos de Pago para la Deuda") or _find(item, "Num_Cuotas", "Plazos de Pago para la Deuda") or "-")})
    return debts


def _as_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]: 
    return value.to_dict() if hasattr(value, "to_dict") else value # type: ignore
def _mapping_value(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = _find(data, key)
    if isinstance(value, str):
        try: value = json.loads(value)
        except json.JSONDecodeError: pass
    return value if isinstance(value, Mapping) else {}
def _find(data: Mapping[str, Any], *names: str) -> Any:
    normalized = {_normalize(key): value for key, value in data.items()}
    return next((normalized[_normalize(name)] for name in names if normalized.get(_normalize(name)) is not None), None)
def _normalize(value: Any) -> str: return "".join(char.lower() for char in str(value) if char.isalnum())
def _amount(value: Any) -> Decimal:
    if value is None or value == "": return Decimal("0")
    if isinstance(value, str):
        value = value.strip().replace("$", "").replace(" ", "")
        if "." in value and "," in value: value = value.replace(".", "").replace(",", ".")
        elif value.count(",") == 1: value = value.replace(",", ".")
    try: return Decimal(str(value))
    except (InvalidOperation, ValueError): return Decimal("0")
def _currency(value: Decimal) -> str:
    """Formatea moneda con miles en punto y exactamente dos decimales."""
    formatted = f"{value:,.2f}"
    return "$ " + formatted.replace(",", "_").replace(".", ",").replace("_", ".")
def _format_date(value: Any) -> str: return value.strftime("%d/%m/%Y") if isinstance(value, (date, datetime)) else str(value or "-")
def _palette(overrides: Optional[Mapping[str, str]]) -> dict[str, Color]:
    values = dict(DEFAULT_COLORS); values.update(overrides or {}); return {name: HexColor(value) for name, value in values.items()}
def _resolve_fonts(font: str) -> tuple[str, str]:
    if font == "Vera":
        directory = Path(reportlab.__file__).parent / "fonts"
        normal, bold = "AgreementFont-Vera", "AgreementFont-VeraBold"
        if normal not in pdfmetrics.getRegisteredFontNames(): pdfmetrics.registerFont(TTFont(normal, str(directory / "Vera.ttf")))
        if bold not in pdfmetrics.getRegisteredFontNames(): pdfmetrics.registerFont(TTFont(bold, str(directory / "VeraBd.ttf")))
        return normal, bold
    path = Path(font)
    if path.is_file():
        normal = f"AgreementFont-{path.stem}"
        if normal not in pdfmetrics.getRegisteredFontNames(): pdfmetrics.registerFont(TTFont(normal, str(path)))
        return normal, normal
    return font, f"{font}-Bold" if font in {"Helvetica", "Times-Roman", "Courier"} else font
def _load_svg(path: Path):
    try: return svg2rlg(str(path)) if path.is_file() else None
    except (OSError, ValueError): return None
def _set_drawing_alpha(node: Any, alpha: float) -> None:
    for attribute in ("fillColor", "strokeColor"):
        color = getattr(node, attribute, None)
        if isinstance(color, Color):
            setattr(node, attribute, Color(1 - (1 - color.red) * alpha, 1 - (1 - color.green) * alpha, 1 - (1 - color.blue) * alpha, alpha=alpha))
    for child in getattr(node, "contents", ()):
        _set_drawing_alpha(child, alpha)
def _embed_metadata(pdf: bytes, payload: Mapping[str, Any]) -> bytes:
    reader, writer = PdfReader(io.BytesIO(pdf)), PdfWriter()
    for page in reader.pages: writer.add_page(page)
    writer.add_metadata({"/Title": "Acuerdo de pago", "/Acuerdo_Info_Metadata": json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":"))})
    output = io.BytesIO(); writer.write(output); return output.getvalue()
def _escape(value: str) -> str: return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")