"""Build small PDFs in memory for tests, so no binary fixtures live in the repo."""

import textwrap
from io import BytesIO

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def make_pdf(pages: list[str], wrap: int = 90) -> bytes:
    """One string per page. Blank lines in a string become paragraph gaps; an empty
    string becomes a page with no text (like a scanned image)."""
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    for page_text in pages:
        text = pdf.beginText(72, 720)
        text.setFont("Helvetica", 10)
        for paragraph in page_text.split("\n\n"):
            for line in textwrap.wrap(paragraph, wrap) or [""]:
                text.textLine(line)
            text.textLine("")
        pdf.drawText(text)
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def sentences(prefix: str, count: int) -> str:
    template = "{} sentence {} explains how retrieval and long context compare."
    return " ".join(template.format(prefix, i) for i in range(count))
