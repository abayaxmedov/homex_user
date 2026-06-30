from datetime import datetime
from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from django.utils import timezone


DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def order_receipt_filename(order):
    return f"homex-order-{order_code(order).lower()}-receipt.docx"


def order_code(order):
    return f"HX{str(order.id).split('-')[0].upper()}"


def build_order_receipt_docx(order, request=None):
    rows = receipt_rows(order, request)
    document_xml = build_document_xml(rows)
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as docx:
        docx.writestr("[Content_Types].xml", content_types_xml())
        docx.writestr("_rels/.rels", root_rels_xml())
        docx.writestr("docProps/core.xml", core_props_xml(order))
        docx.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


def receipt_rows(order, request=None):
    rows = [
        ("Check raqami", order_code(order)),
        ("Order ID", order.id),
        ("Status", order.get_status_display()),
        ("Check tasdiqlangan vaqt", format_datetime(order.receipt_approved_at)),
        ("Client", full_name(order.client)),
        ("Client telefon", getattr(order.client, "phone", "")),
        ("Usta", full_name(order.master) if order.master else "-"),
        ("Usta telefon", getattr(order.master, "phone", "") if order.master else "-"),
        ("Xizmat", order.service.name),
        ("Kategoriya", getattr(order.service.category, "name", "")),
        ("Manzil", order.address_text),
        ("Latitude", order.lat),
        ("Longitude", order.lng),
        ("Rejalashtirilgan sana", order.scheduled_date),
        ("Rejalashtirilgan vaqt", order.scheduled_time),
        ("To'lov turi", order.get_payment_type_display()),
        ("Xizmat haqi", money(order.service_fee)),
        ("Ishlatilgan uskunalar jami", money(order.inventory_total)),
        ("Bonus ishlatilgan", money(order.bonus_used)),
        ("Jami summa", money(order.total_amount)),
        ("Izoh", order.note or "-"),
        ("Ishdan oldingi rasm", file_url(order.before_photo, request)),
        ("Ishdan keyingi rasm", file_url(order.completion_photo, request)),
        ("Yaratilgan vaqt", format_datetime(order.created_at)),
        ("Yangilangan vaqt", format_datetime(order.updated_at)),
    ]

    usages = list(order.inventory_usages.select_related("inventory__warehouse_product").all())
    if usages:
        rows.append(("Ishlatilgan uskunalar", ""))
        for index, usage in enumerate(usages, start=1):
            product_name = getattr(usage.inventory.warehouse_product, "name", str(usage.inventory))
            rows.append(
                (
                    f"Uskuna {index}",
                    f"{product_name}; miqdor: {usage.quantity}; birlik narx: {money(usage.unit_price)}; jami: {money(usage.total_price)}",
                )
            )
    else:
        rows.append(("Ishlatilgan uskunalar", "-"))

    if order.cancel_reason:
        rows.append(("Bekor qilish sababi", order.cancel_reason))
    if order.rejected_reason:
        rows.append(("Rad etish sababi", order.rejected_reason))
    return rows


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


def build_document_xml(rows):
    body = [
        paragraph("HomeX order check", bold=True),
        paragraph("Buyurtma haqidagi barcha tafsilotlar", bold=True),
        table(rows),
        paragraph("Ushbu check usta tomonidan tasdiqlangandan keyin client uchun yuklab olishga ochiladi."),
    ]
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{''.join(body)}"
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr>'
        "</w:body></w:document>"
    )


def paragraph(text, bold=False):
    bold_xml = "<w:b/>" if bold else ""
    return f"<w:p><w:r><w:rPr>{bold_xml}</w:rPr><w:t>{escape(str(text))}</w:t></w:r></w:p>"


def table(rows):
    cells = []
    for label, value in rows:
        cells.append(
            "<w:tr>"
            f"<w:tc><w:p><w:r><w:rPr><w:b/></w:rPr><w:t>{escape(str(label))}</w:t></w:r></w:p></w:tc>"
            f"<w:tc><w:p><w:r><w:t>{escape(str(value))}</w:t></w:r></w:p></w:tc>"
            "</w:tr>"
        )
    return (
        "<w:tbl>"
        '<w:tblPr><w:tblBorders><w:top w:val="single" w:sz="4"/><w:left w:val="single" w:sz="4"/>'
        '<w:bottom w:val="single" w:sz="4"/><w:right w:val="single" w:sz="4"/>'
        '<w:insideH w:val="single" w:sz="4"/><w:insideV w:val="single" w:sz="4"/></w:tblBorders></w:tblPr>'
        f"{''.join(cells)}</w:tbl>"
    )


def content_types_xml():
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        "</Types>"
    )


def root_rels_xml():
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        "</Relationships>"
    )


def core_props_xml(order):
    created = timezone.localtime(order.created_at).isoformat() if order.created_at else timezone.now().isoformat()
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        f"<dc:title>HomeX {escape(order_code(order))} check</dc:title>"
        "<dc:creator>HomeX</dc:creator>"
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{escape(created)}</dcterms:created>'
        "</cp:coreProperties>"
    )
