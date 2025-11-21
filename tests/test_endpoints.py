import io
from fastapi.testclient import TestClient
from main import app, UPLOAD_DIR, OUTPUT_DIR

client = TestClient(app)


def test_root():
    r = client.get('/')
    assert r.status_code == 200


def test_upload_and_merge(tmp_path):
    # Create two tiny PDFs in memory using reportlab
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter

    def make_pdf(text: str) -> bytes:
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=letter)
        c.drawString(72, 720, text)
        c.showPage()
        c.save()
        return buf.getvalue()

    files = [
        ('files', ('a.pdf', make_pdf('A'), 'application/pdf')),
        ('files', ('b.pdf', make_pdf('B'), 'application/pdf')),
    ]
    r = client.post('/upload', files=files)
    assert r.status_code == 200
    job = r.json()['job_id']

    r2 = client.post('/merge', data={'job_id': job})
    assert r2.status_code == 200
    out = OUTPUT_DIR / job / 'merged.pdf'
    # Background task runs after response; simulate by calling merge directly if needed.


def test_compress_requires_upload():
    r = client.post('/compress', data={'job_id': 'missing'})
    assert r.status_code in (400, 404)
