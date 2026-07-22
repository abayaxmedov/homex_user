from datetime import datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


PDF_CONTENT_TYPE = "application/pdf"

# DejaVu (bundled under fonts/) is used instead of reportlab's built-in Helvetica/Vera
# because those cover neither Cyrillic nor the Uzbek turned comma (oʻ / gʻ, U+02BB),
# which appear in client names, addresses and notes.
FONT_DIR = Path(__file__).resolve().parent / "fonts"
FONT_REGULAR = "DejaVuSans"
FONT_BOLD = "DejaVuSans-Bold"


def _register_fonts():
    if FONT_REGULAR in pdfmetrics.getRegisteredFontNames():
        return
    pdfmetrics.registerFont(TTFont(FONT_REGULAR, str(FONT_DIR / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, str(FONT_DIR / "DejaVuSans-Bold.ttf")))
    pdfmetrics.registerFontFamily(FONT_REGULAR, normal=FONT_REGULAR, bold=FONT_BOLD)


def order_receipt_filename(order):
    return f"homex-order-{order_code(order).lower()}-receipt.pdf"


def order_code(order):
    return f"HX{str(order.id).split('-')[0].upper()}"


def build_order_receipt_pdf(order, request=None):
    """Render the order receipt as a PDF and return its bytes."""
    _register_fonts()
    rows = receipt_rows(order, request)

    label_style = ParagraphStyle("label", fontName=FONT_BOLD, fontSize=9, leading=12)
    value_style = ParagraphStyle("value", fontName=FONT_REGULAR, fontSize=9, leading=12)
    title_style = ParagraphStyle("title", fontName=FONT_BOLD, fontSize=16, leading=20)
    subtitle_style = ParagraphStyle("subtitle", fontName=FONT_REGULAR, fontSize=10, leading=14)
    footer_style = ParagraphStyle("footer", fontName=FONT_REGULAR, fontSize=8, leading=11, textColor=colors.grey)

    table = Table(
        [
            [Paragraph(escape(str(label)), label_style), Paragraph(escape(str(value)), value_style)]
            for label, value in rows
        ],
        colWidths=[55 * mm, 105 * mm],
        # Let long receipts flow onto extra pages instead of overflowing one.
        repeatRows=0,
    )
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D0D0D0")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#FAFAFA")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )

    story = [
        Paragraph(f"HomeX order check — {escape(order_code(order))}", title_style),
        Spacer(1, 3 * mm),
        Paragraph("Buyurtma haqidagi barcha tafsilotlar", subtitle_style),
        Spacer(1, 5 * mm),
        table,
        Spacer(1, 5 * mm),
        Paragraph(
            "Ushbu check usta tomonidan tasdiqlangandan keyin client uchun yuklab olishga ochiladi.",
            footer_style,
        ),
    ]

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"HomeX {order_code(order)} check",
        author="HomeX",
    )
    doc.build(story)
    return buffer.getvalue()


def receipt_rows(order, request=None):
    # Only the fields the check PDF needs — nothing else.
    return [
        ("Check tasdiqlangan vaqt", format_datetime(order.receipt_approved_at)),
        ("Usta", full_name(order.master) if order.master else "-"),
        ("Usta telefon", getattr(order.master, "phone", "") if order.master else "-"),
        ("Xizmat", order.service.name),
        ("Kategoriya", getattr(order.service.category, "name", "")),
        ("To'lov turi", order.get_payment_type_display() or "-"),
        ("Xizmat haqi", money(order.service_fee)),
        ("Ishlatilgan uskunalar jami", money(order.inventory_total)),
        ("Bonus ishlatilgan", money(order.bonus_used)),
        ("Jami summa", money(order.total_amount)),
    ]


def full_name(user):
    if not user:
        return "-"
    if hasattr(user, "full_name"):
        return user.full_name or getattr(user, "phone", "-")
    return f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip() or getattr(user, "phone", "-")


def file_url(file_field, request=None):
    if not file_field:
        return "-"
    url = file_field.url
    return request.build_absolute_uri(url) if request else url


def format_datetime(value):
    if not value:
        return "-"
    if isinstance(value, datetime):
        return timezone.localtime(value).strftime("%Y-%m-%d %H:%M")
    return str(value)


def money(value):
    value = value if value is not None else Decimal("0")
    return f"{value:,.2f} so'm"

