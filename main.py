import os
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from utils.pdf_tools import (
    merge_pdfs_task,
    split_pdf_task,
    reorder_pages_task,
    rotate_pages_task,
    compress_pdf_task,
    convert_task,
    generate_pdf_thumbnails,
    edit_to_docx_task,
    edit_to_pdf_task,
)

BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "converted"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

for d in [UPLOAD_DIR, OUTPUT_DIR, STATIC_DIR, TEMPLATES_DIR]:
    d.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="All-File Converter + PDF/DOCX Editor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static and uploaded files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")


class JobStatus(BaseModel):
    job_id: str
    status: str
    message: Optional[str] = None
    output_path: Optional[str] = None
    progress: int = 0


# In-memory job store (metadata only; files on disk)
JOB_STORE: dict[str, JobStatus] = {}


def new_job(status: str = "queued", message: str = "") -> str:
    job_id = uuid.uuid4().hex
    JOB_STORE[job_id] = JobStatus(job_id=job_id, status=status, message=message, progress=0)
    (UPLOAD_DIR / job_id).mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / job_id).mkdir(parents=True, exist_ok=True)
    return job_id


def ensure_job(job_id: str) -> JobStatus:
    job = JOB_STORE.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.get("/")
def health():
    return {"message": "Backend running", "version": "1.0"}


@app.post("/upload")
async def upload_files(files: List[UploadFile] = File(...)):
    job_id = new_job(status="uploading", message="Saving files")
    dest_dir = UPLOAD_DIR / job_id

    allowed = {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/plain",
        "image/jpeg",
        "image/png",
        "video/mp4",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "text/csv",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }
    max_size = 100 * 1024 * 1024  # 100MB per file

    saved_files = []
    for f in files:
        if f.content_type not in allowed:
            raise HTTPException(status_code=400, detail=f"Unsupported type: {f.content_type}")
        content = await f.read()
        if len(content) > max_size:
            raise HTTPException(status_code=400, detail=f"File too large: {f.filename}")
        safe_name = Path(f.filename).name
        out_path = dest_dir / safe_name
        with open(out_path, "wb") as out:
            out.write(content)
        saved_files.append(str(out_path))

    JOB_STORE[job_id].status = "uploaded"
    JOB_STORE[job_id].message = "Files uploaded"

    # Generate thumbnails for PDFs
    thumb_urls: List[str] = []
    for path in saved_files:
        if path.lower().endswith(".pdf"):
            try:
                thumbs_dir = dest_dir / "thumbnails"
                thumbs_dir.mkdir(exist_ok=True)
                tpaths = generate_pdf_thumbnails(Path(path), thumbs_dir)
                for p in tpaths:
                    # Expose via mounted /uploads
                    rel = p.relative_to(UPLOAD_DIR)
                    thumb_urls.append(f"/uploads/{rel.as_posix()}")
            except Exception:
                pass

    return {"job_id": job_id, "files": saved_files, "thumbnails": thumb_urls}


@app.get("/job/{job_id}")
def job_status(job_id: str):
    return ensure_job(job_id)


@app.post("/merge")
async def merge_pdfs(background_tasks: BackgroundTasks, job_id: Optional[str] = Form(None)):
    job = job_id or new_job(status="processing", message="Merging PDFs")
    up_dir = UPLOAD_DIR / job
    if not up_dir.exists():
        raise HTTPException(400, "Job has no uploads")
    pdfs = sorted([str(p) for p in up_dir.glob("*.pdf")])
    if not pdfs:
        raise HTTPException(400, "No PDFs uploaded for this job")

    out_path = OUTPUT_DIR / job / "merged.pdf"
    background_tasks.add_task(merge_pdfs_task, pdfs, out_path, JOB_STORE[job])
    return {"job_id": job, "output": str(out_path)}


@app.post("/split")
async def split_pdf(background_tasks: BackgroundTasks, job_id: str = Form(...), ranges: str = Form("")):
    ensure_job(job_id)
    up_dir = UPLOAD_DIR / job_id
    pdfs = sorted([str(p) for p in up_dir.glob("*.pdf")])
    if not pdfs:
        raise HTTPException(400, "No PDFs uploaded for this job")
    src_pdf = pdfs[0]

    out_dir = OUTPUT_DIR / job_id / "split"
    out_dir.mkdir(parents=True, exist_ok=True)
    background_tasks.add_task(split_pdf_task, src_pdf, ranges, out_dir, JOB_STORE[job_id])
    return {"job_id": job_id, "output_dir": str(out_dir)}


@app.post("/reorder")
async def reorder_pages(background_tasks: BackgroundTasks, job_id: str = Form(...), order: str = Form(...)):
    ensure_job(job_id)
    up_dir = UPLOAD_DIR / job_id
    pdfs = sorted([str(p) for p in up_dir.glob("*.pdf")])
    if not pdfs:
        raise HTTPException(400, "No PDFs uploaded for this job")
    src_pdf = pdfs[0]
    out_path = OUTPUT_DIR / job_id / "reordered.pdf"
    background_tasks.add_task(reorder_pages_task, src_pdf, order, out_path, JOB_STORE[job_id])
    return {"job_id": job_id, "output": str(out_path)}


@app.post("/rotate")
async def rotate_pages(background_tasks: BackgroundTasks, job_id: str = Form(...), degrees: int = Form(90), pages: str = Form("")):
    ensure_job(job_id)
    up_dir = UPLOAD_DIR / job_id
    pdfs = sorted([str(p) for p in up_dir.glob("*.pdf")])
    if not pdfs:
        raise HTTPException(400, "No PDFs uploaded for this job")
    src_pdf = pdfs[0]
    out_path = OUTPUT_DIR / job_id / "rotated.pdf"
    background_tasks.add_task(rotate_pages_task, src_pdf, degrees, pages, out_path, JOB_STORE[job_id])
    return {"job_id": job_id, "output": str(out_path)}


@app.post("/compress")
async def compress_pdf(background_tasks: BackgroundTasks, job_id: str = Form(...), preset: str = Form("medium")):
    ensure_job(job_id)
    up_dir = UPLOAD_DIR / job_id
    pdfs = sorted([str(p) for p in up_dir.glob("*.pdf")])
    if not pdfs:
        raise HTTPException(400, "No PDFs uploaded for this job")
    src_pdf = pdfs[0]
    out_path = OUTPUT_DIR / job_id / f"compressed_{preset}.pdf"
    background_tasks.add_task(compress_pdf_task, src_pdf, preset, out_path, JOB_STORE[job_id])
    return {"job_id": job_id, "output": str(out_path)}


@app.post("/convert")
async def convert(background_tasks: BackgroundTasks, job_id: str = Form(...), target: str = Form(...)):
    ensure_job(job_id)
    up_dir = UPLOAD_DIR / job_id
    files = [str(p) for p in up_dir.iterdir() if p.is_file()]
    if not files:
        raise HTTPException(400, "No files uploaded for this job")

    out_dir = OUTPUT_DIR / job_id
    out_path = out_dir / f"converted.{target.lower()}"
    background_tasks.add_task(convert_task, files[0], target, out_path, JOB_STORE[job_id])
    return {"job_id": job_id, "output": str(out_path)}


@app.post("/edit/docx")
async def edit_docx(background_tasks: BackgroundTasks, job_id: Optional[str] = Form(None), content: str = Form("")):
    job = job_id or new_job(status="processing", message="Editing DOCX")
    out_path = OUTPUT_DIR / job / "edited.docx"
    background_tasks.add_task(edit_to_docx_task, content, out_path, JOB_STORE[job])
    return {"job_id": job, "output": str(out_path)}


@app.post("/edit/pdf")
async def edit_pdf(background_tasks: BackgroundTasks, job_id: Optional[str] = Form(None), content: str = Form("")):
    job = job_id or new_job(status="processing", message="Editing PDF")
    out_path = OUTPUT_DIR / job / "edited.pdf"
    background_tasks.add_task(edit_to_pdf_task, content, out_path, JOB_STORE[job])
    return {"job_id": job, "output": str(out_path)}


@app.get("/download/{job_id}")
def download(job_id: str):
    out_dir = OUTPUT_DIR / job_id
    if not out_dir.exists():
        raise HTTPException(404, "Not found")
    # pick first file
    files = sorted(out_dir.glob("*"))
    if not files:
        raise HTTPException(404, "No output")
    return FileResponse(files[0])


@app.get("/pages")
def pages_info():
    return {
        "pages": ["Home", "Upload + Merge", "Editor", "Conversion", "Result / Download"],
        "note": "This backend is API-first. A React frontend is provided in the frontend service."
    }


@app.get("/test")
def test():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
