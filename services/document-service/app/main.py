"""Document service: PDF text extraction (with image fallback for scans) and response-letter rendering."""

import base64
import io
from datetime import date
from xml.sax.saxutils import escape

import pypdfium2 as pdfium
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

MIN_TEXT_CHARS = 80  # below this, a page is treated as a scan
MAX_IMAGE_PAGES = 3

app = FastAPI(title="Document Service", version="0.1.0")

FONT_DIR = "/usr/share/fonts/truetype/dejavu"
pdfmetrics.registerFont(TTFont("DejaVu", f"{FONT_DIR}/DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("DejaVu-Bold", f"{FONT_DIR}/DejaVuSans-Bold.ttf"))
BODY = ParagraphStyle("body", fontName="DejaVu", fontSize=10, leading=14, spaceAfter=6)
BOLD = ParagraphStyle("bold", parent=BODY, fontName="DejaVu-Bold", fontSize=11)
TITLE = ParagraphStyle("title", parent=BOLD, fontSize=13, alignment=1, spaceBefore=8, spaceAfter=10)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/extract")
async def extract(file: UploadFile = File(...)):
    data = await file.read()
    try:
        pdf = pdfium.PdfDocument(data)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Fișierul nu este un PDF valid: {e}")

    pages_text = []
    for page in pdf:
        tp = page.get_textpage()
        pages_text.append(tp.get_text_range())
    text = "\n\n".join(t.strip() for t in pages_text).strip()
    has_text = len(text) >= MIN_TEXT_CHARS

    images = []
    if not has_text:
        for i in range(min(len(pdf), MAX_IMAGE_PAGES)):
            pil = pdf[i].render(scale=1.5).to_pil().convert("L")
            buf = io.BytesIO()
            pil.save(buf, "PNG", optimize=True)
            images.append(base64.b64encode(buf.getvalue()).decode())

    return {"pages": len(pdf), "has_text_layer": has_text, "text": text if has_text else "", "page_images_png_b64": images}


class HoldLine(BaseModel):
    iban: str
    currency: str
    amount: float


class LetterIn(BaseModel):
    bank_name: str
    reference: str
    recipient: str
    case_ref: str
    debtor_name: str
    debtor_cnp: str | None = None
    subject: str
    paragraphs: list[str]
    holds: list[HoldLine] = []
    signature: str = "Departamentul Executări Silite"


def _fmt(x: float) -> str:
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


@app.post("/render/letter")
def render_letter(body: LetterIn):
    f = [
        Paragraph(escape(body.bank_name.upper()), BOLD),
        Paragraph("Departamentul Executări Silite · executari@bancademo.ro", BODY),
        Spacer(1, 4),
        Paragraph(f"Nr. {body.reference} din {date.today():%d.%m.%Y}", BODY),
        Paragraph(f"Către: <b>{escape(body.recipient)}</b>", BODY),
        Paragraph(f"Referitor la: dosarul nr. <b>{escape(body.case_ref)}</b> · debitor <b>{escape(body.debtor_name)}</b>"
                  + (f", CNP {body.debtor_cnp}" if body.debtor_cnp else ""), BODY),
        Paragraph(escape(body.subject), TITLE),
    ]
    f += [Paragraph(escape(p), BODY) for p in body.paragraphs]
    if body.holds:
        rows = [["Cont (IBAN)", "Moneda", "Suma indisponibilizată"]] + [[h.iban, h.currency, _fmt(h.amount)] for h in body.holds]
        t = Table(rows, colWidths=[85 * mm, 25 * mm, 50 * mm])
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "DejaVu"), ("FONTNAME", (0, 0), (-1, 0), "DejaVu-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (2, 1), (2, -1), "RIGHT"),
        ]))
        f += [Spacer(1, 4), t, Spacer(1, 8)]
    f += [Spacer(1, 14), Paragraph(f"Cu stimă,<br/><b>{escape(body.bank_name)}</b><br/>{escape(body.signature)}", BODY),
          Spacer(1, 10), Paragraph("Document generat automat de agentul de procesare a popririlor și verificat conform procedurii interne.",
                                   ParagraphStyle("note", parent=BODY, fontSize=7, textColor=colors.grey))]

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=18 * mm).build(f)
    return Response(content=buf.getvalue(), media_type="application/pdf")
