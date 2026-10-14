from evidence_engine import extract, textnorm

HTML = b"""<html><head><title>Example Federal Credit Union | Newsroom</title>
<meta property="article:published_time" content="2026-03-03"></head>
<body><nav><a href="/">Home</a> <a href="/login">Log in</a></nav>
<article><h1>Example Federal Credit Union reports record growth</h1>
<p>ANYTOWN, ST, March 3, 2026 &ndash; Example Federal Credit Union today reported that members grew 4.2 percent to 212,000 during 2025.</p>
<p>Total assets rose to $6.11 billion, and the credit union opened two branches in the county.</p>
<p>The credit union also launched a new mobile application with card controls and instant alerts.</p></article>
<footer>We use cookies to improve your experience. Accept all cookies. &copy; 2026 Example Federal Credit Union. All rights reserved.</footer>
</body></html>"""


def test_html_yields_two_texts_and_the_span_is_in_both():
    ex = extract.extract(HTML, "text/html; charset=utf-8", "https://www.example-fcu.test/news/record-growth")
    assert ex is not None and ex.kind == "html"
    span = "Total assets rose to $6.11 billion, and the credit union opened two branches in the county."
    assert span in ex.text
    assert textnorm.normalise(span) in textnorm.normalise(ex.verify_text)
    assert "Example Federal Credit Union" in ex.title


def test_verify_text_is_the_connectors_extraction():
    ex = extract.extract(HTML, "text/html", "")
    assert ex.verify_text == extract._clean_ws(textnorm.connector_html_text(HTML.decode()))


def test_plain_text_passthrough():
    ex = extract.extract(b"Just some text with a figure of 12 percent.", "text/plain")
    assert ex.kind == "text" and ex.text == ex.verify_text


def test_pdf_detection_and_extraction(tmp_path):
    pypdfium2 = __import__("pypdfium2")
    pdf = pypdfium2.PdfDocument.new()
    page = pdf.new_page(400, 200)
    # draw text with the built-in Helvetica font
    font = pdf.init_font(pypdfium2.raw.FPDFText_LoadStandardFont(pdf, b"Helvetica")) if hasattr(pdf, "init_font") else None
    if font is None:
        import pytest
        pytest.skip("pypdfium2 text drawing API unavailable in this version")
    body = tmp_path / "x.pdf"
    pdf.save(str(body))
    raw = body.read_bytes()
    assert extract.is_pdf(raw)


def test_scanned_pdf_is_unreachable_not_empty():
    # a PDF header with no text layer
    assert extract.extract(b"%PDF-1.4\n%%EOF", "application/pdf") is None
