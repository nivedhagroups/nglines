import asyncio
import hashlib
from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import StoredFile


LOCAL_ZONE = ZoneInfo("Asia/Kolkata")
FOREST = colors.HexColor("#176B52")
INK = colors.HexColor("#202622")
MUTED = colors.HexColor("#69736D")
PALE = colors.HexColor("#EDF5E9")


def _format_money(value: Decimal | int | str | None) -> str:
    amount = Decimal(str(value or 0)).quantize(Decimal("0.01"))
    whole, paise = f"{amount:.2f}".split(".")
    if len(whole) > 3:
        last_three = whole[-3:]
        prefix = whole[:-3]
        groups = []
        while prefix:
            groups.append(prefix[-2:])
            prefix = prefix[:-2]
        whole = ",".join(reversed(groups)) + "," + last_three
    return f"INR {whole}.{paise}"


def _text(value: object | None) -> str:
    return escape(str(value)).replace("\n", "<br/>") if value else "-"


def render_document_pdf(document, lines: list, document_type: str) -> bytes:
    output = BytesIO()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Brand", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=18, textColor=FOREST, spaceAfter=2))
    styles.add(ParagraphStyle(name="DocTitle", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=14, textColor=INK, spaceAfter=4))
    styles.add(ParagraphStyle(name="Small", parent=styles["BodyText"], fontSize=8, leading=11, textColor=MUTED))
    styles.add(ParagraphStyle(name="Cell", parent=styles["BodyText"], fontSize=8, leading=10, textColor=INK))

    document_number = document.invoice_number if document_type == "invoice" else document.estimate_number
    document_date = document.invoice_date if document_type == "invoice" else document.estimate_date
    title = "TAX INVOICE" if document_type == "invoice" else "ESTIMATE - NOT A TAX INVOICE"
    story = [Paragraph(_text(document.company_name_snapshot), styles["Brand"])]
    if document.company_address_snapshot:
        story.append(Paragraph(_text(document.company_address_snapshot), styles["Small"]))
    if document.company_gstin_snapshot:
        story.append(Paragraph(f"GSTIN: {_text(document.company_gstin_snapshot)}", styles["Small"]))
    story.extend((Spacer(1, 8 * mm), Paragraph(title, styles["DocTitle"])))

    meta = [
        [Paragraph(f"<b>Number</b><br/>{_text(document_number)}", styles["Cell"]), Paragraph(f"<b>Date</b><br/>{document_date.strftime('%d %b %Y')}", styles["Cell"])],
        [Paragraph(f"<b>Bill to</b><br/>{_text(document.customer_name_snapshot)}", styles["Cell"]), Paragraph(f"<b>Phone</b><br/>{_text(document.customer_mobile_snapshot)}", styles["Cell"])],
    ]
    if document.customer_location_snapshot:
        meta.append([Paragraph(f"<b>Address</b><br/>{_text(document.customer_location_snapshot)}", styles["Cell"]), ""])
    if document.customer_gstin_snapshot:
        meta.append([Paragraph(f"<b>Customer GSTIN</b><br/>{_text(document.customer_gstin_snapshot)}", styles["Cell"]), ""])
    meta_table = Table(meta, colWidths=[88 * mm, 88 * mm], hAlign="LEFT")
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE),
        ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#C9D9CF")),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D8E3DB")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.extend((meta_table, Spacer(1, 8 * mm)))

    item_rows = [["Description", "Qty", "Rate", "Amount"]]
    for line in lines:
        item_rows.append([
            Paragraph(_text(line.description_snapshot), styles["Cell"]),
            str(line.quantity),
            _format_money(line.unit_rate),
            _format_money(line.line_total),
        ])
    item_table = Table(item_rows, colWidths=[76 * mm, 22 * mm, 38 * mm, 40 * mm], repeatRows=1, hAlign="LEFT")
    item_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), FOREST),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D8E3DB")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9F7")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.extend((item_table, Spacer(1, 5 * mm)))

    totals = [
        ["Subtotal", _format_money(document.subtotal)],
        [f"Discount ({document.discount_percent}%)", f"- {_format_money(document.discount_amount)}"],
        ["Taxable amount", _format_money(document.taxable_amount)],
    ]
    if document.apply_gst:
        if document.igst_amount:
            totals.append([f"IGST ({document.gst_rate}%)", _format_money(document.igst_amount)])
        else:
            totals.extend(((f"CGST ({Decimal(document.gst_rate) / 2}%)", _format_money(document.cgst_amount)), (f"SGST ({Decimal(document.gst_rate) / 2}%)", _format_money(document.sgst_amount))))
    totals.append(["TOTAL", _format_money(document.total_amount)])
    totals_table = Table(totals, colWidths=[122 * mm, 54 * mm], hAlign="RIGHT")
    totals_table.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, -1), (-1, -1), 11),
        ("TEXTCOLOR", (0, -1), (-1, -1), FOREST),
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, FOREST),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.extend((totals_table, Spacer(1, 12 * mm)))
    if document.footer_snapshot:
        story.append(Paragraph(_text(document.footer_snapshot), styles["Small"]))

    pdf = SimpleDocTemplate(output, pagesize=A4, rightMargin=17 * mm, leftMargin=17 * mm, topMargin=17 * mm, bottomMargin=17 * mm, title=f"{title} {document_number}")
    pdf.build(story)
    return output.getvalue()


async def store_document_pdf(db: AsyncSession, document, lines: list, document_type: str, user_id) -> StoredFile:
    content = await asyncio.to_thread(render_document_pdf, document, lines, document_type)
    created_at = document.created_at or datetime.now(timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    folder_date = created_at.astimezone(LOCAL_ZONE)
    document_number = document.invoice_number if document_type == "invoice" else document.estimate_number
    safe_number = document_number.replace("/", "_")
    relative_path = Path("documents") / folder_date.strftime("%Y") / folder_date.strftime("%m") / folder_date.strftime("%d") / str(document.business_id) / f"{document_type}_{safe_number}.pdf"
    absolute_path = Path(settings.file_storage_root) / relative_path
    await asyncio.to_thread(absolute_path.parent.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread(absolute_path.write_bytes, content)

    file_record = await db.get(StoredFile, document.pdf_file_id) if document.pdf_file_id else None
    if file_record is None:
        file_record = StoredFile(
            business_id=document.business_id,
            created_by_id=user_id,
            storage_path=relative_path.as_posix(),
            original_filename=f"{safe_number}.pdf",
            content_type="application/pdf",
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
        )
        db.add(file_record)
        await db.flush()
        document.pdf_file_id = file_record.id
    else:
        file_record.storage_path = relative_path.as_posix()
        file_record.original_filename = f"{safe_number}.pdf"
        file_record.content_type = "application/pdf"
        file_record.size_bytes = len(content)
        file_record.sha256 = hashlib.sha256(content).hexdigest()
    await db.flush()
    return file_record