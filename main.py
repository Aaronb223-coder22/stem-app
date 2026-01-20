from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import subprocess, uuid, shutil, threading, time, os
from typing import Dict

app = FastAPI()

# -------------------------
# GLOBAL JOB TRACKING
# -------------------------
jobs: Dict[str, dict] = {}

# -------------------------
# CORS
# -------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------
# PATHS
# -------------------------
BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "Frontend"
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# -------------------------
# STATIC FILES (safe mounting)
# -------------------------
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")

# -------------------------
# FRONTEND
# -------------------------
@app.get("/")
def root():
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"status": "API running"}

# -------------------------
# START JOB
# -------------------------
@app.post("/separate")
async def separate_audio(file: UploadFile = File(...)):
    job_id = str(uuid.uuid4())
    input_path = UPLOAD_DIR / f"{job_id}_{file.filename}"

    with open(input_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    jobs[job_id] = {
        "progress": 5,
        "status": "starting",
        "files": []
    }

    def run_demucs():
        try:
            jobs[job_id]["status"] = "processing"
            jobs[job_id]["progress"] = 10

            cmd = [
                "demucs",
                str(input_path),
                "-o",
                str(OUTPUT_DIR),
                "--float32"
            ]

            process = subprocess.Popen(cmd)

            # Simulated progress
            while process.poll() is None:
                current = jobs[job_id]["progress"]
                if current < 90:
                    jobs[job_id]["progress"] += 2
                time.sleep(1)

            process.wait()
            jobs[job_id]["progress"] = 95

            stem_dir = OUTPUT_DIR / "htdemucs" / input_path.stem
            if stem_dir.exists():
                for f in stem_dir.glob("*.wav"):
                    jobs[job_id]["files"].append({
                        "name": f.name,
                        "url": f"/outputs/htdemucs/{input_path.stem}/{f.name}"
                    })

            jobs[job_id]["progress"] = 100
            jobs[job_id]["status"] = "done"

        except Exception as e:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = str(e)

    threading.Thread(target=run_demucs, daemon=True).start()

    return {"job_id": job_id}

# -------------------------
# PROGRESS ENDPOINT
# -------------------------
@app.get("/progress/{job_id}")
def get_progress(job_id: str):
    if job_id not in jobs:
        return {"error": "Job not found"}
    return jobs[job_id]

# -------------------------
# RENDER / LOCAL ENTRYPOINT
# -------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
