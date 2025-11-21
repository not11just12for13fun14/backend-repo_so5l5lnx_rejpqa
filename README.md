# All-File Converter + PDF/DOCX Editor

A production-ready FastAPI backend with endpoints for uploading files, PDF tools (merge, split, reorder, rotate, compress), format conversions, and a simple online editor pipeline. The UI is built in the separate frontend service (Vite + React + Tailwind) and references iLovePDF for UX patterns.

## Quick start

1. Install backend + frontend deps and start servers

```
# Handled automatically in this environment by the run command
```

2. Visit the frontend URL to use the app. The backend lives at `/` on port 8000.

## Endpoints

- POST /upload — upload one or more files; returns job_id and saved files
- GET /job/{job_id} — poll job status
- POST /merge — merge uploaded PDFs for a job
- POST /split — split a PDF by ranges like "1-3, 7, 10-12"
- POST /reorder — reorder pages by comma order e.g. "3,1,2"
- POST /rotate — rotate some or all pages, degrees=90/180/270
- POST /compress — compress with presets: high|medium|low
- POST /convert — convert the first uploaded file to a target format (pdf, docx, xlsx, png, jpg)
- GET /download/{job_id} — fetch the first output file for a job

## Storage

- Uploads: backend/uploads/<jobid>
- Outputs: backend/converted/<jobid>

Clean up old jobs periodically in production (e.g., cron or startup task).

## Thumbnails

- `utils/pdf_tools.generate_pdf_thumbnails` converts PDF pages to small JPG previews using pdf2image + Pillow. Note: pdf2image requires poppler to be available in the system PATH for rasterization.

## Conversion Notes

- PDF -> DOCX uses pdfplumber (text extraction) + python-docx; layout is approximated.
- DOCX -> PDF uses reportlab to lay text; complex layouts aren't preserved but provides a reliable baseline.
- TXT/CSV/Image conversions included; extend with more as needed.

## Compression

- Uses pikepdf optimization and linearization. For stronger compression, integrate Ghostscript (gs) if available.

### Ghostscript (optional)

Install Ghostscript on the host and call it in a subprocess for aggressive compression presets:

```
gs -sDEVICE=pdfwrite -dCompatibilityLevel=1.5 -dPDFSETTINGS=/screen \
   -dNOPAUSE -dQUIET -dBATCH -sOutputFile=out.pdf in.pdf
```

## Tests

Run the test suite:

```
pytest -q
```

## Environment

- FastAPI + Uvicorn
- Python packages listed in requirements.txt

## Credits

UI/UX inspired by iLovePDF — designed for clarity and speed.
