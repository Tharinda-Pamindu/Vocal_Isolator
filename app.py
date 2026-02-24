import os
import uuid
import time
import threading
import shutil
from flask import Flask, request, jsonify, render_template, send_file, abort

app = Flask(__name__)

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
OUTPUT_FOLDER = os.path.join(os.path.dirname(__file__), "outputs")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {"mp3", "wav", "flac", "ogg", "m4a", "aac"}
MAX_FILE_SIZE = 200 * 1024 * 1024  # 200 MB

# In-memory job store: {file_id: {status, progress, stems, error, created_at}}
jobs = {}
jobs_lock = threading.Lock()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def cleanup_old_jobs():
    """Clean up jobs and files older than 1 hour."""
    cutoff = time.time() - 3600
    with jobs_lock:
        expired = [fid for fid, j in jobs.items() if j.get("created_at", 0) < cutoff]
    for fid in expired:
        _delete_job_files(fid)
        with jobs_lock:
            jobs.pop(fid, None)


def _delete_job_files(file_id):
    upload_dir = os.path.join(UPLOAD_FOLDER, file_id)
    output_dir = os.path.join(OUTPUT_FOLDER, file_id)
    for d in [upload_dir, output_dir]:
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)


def run_separation(file_id, input_path, model_name, two_stems):
    """Run Demucs separation in a background thread."""
    try:
        with jobs_lock:
            jobs[file_id]["status"] = "processing"
            jobs[file_id]["progress"] = 5

        from demucs.api import Separator, save_audio
        import torch

        device = "cuda" if torch.cuda.is_available() else "cpu"

        separator = Separator(
            model=model_name,
            device=device,
            two_stems=two_stems,  # e.g. "vocals" or None for all stems
        )

        with jobs_lock:
            jobs[file_id]["progress"] = 20

        origin, separated = separator.separate_audio_file(input_path)

        with jobs_lock:
            jobs[file_id]["progress"] = 80

        out_dir = os.path.join(OUTPUT_FOLDER, file_id)
        os.makedirs(out_dir, exist_ok=True)

        stems_info = []
        for stem_name, audio_tensor in separated.items():
            out_path = os.path.join(out_dir, f"{stem_name}.wav")
            save_audio(audio_tensor, out_path, samplerate=separator.samplerate)
            stems_info.append(stem_name)

        with jobs_lock:
            jobs[file_id]["status"] = "done"
            jobs[file_id]["progress"] = 100
            jobs[file_id]["stems"] = stems_info

    except Exception as e:
        with jobs_lock:
            jobs[file_id]["status"] = "error"
            jobs[file_id]["error"] = str(e)
    finally:
        # Small delay then clean upload file
        try:
            if os.path.isfile(input_path):
                os.remove(input_path)
        except Exception:
            pass


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    cleanup_old_jobs()

    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    f = request.files["file"]
    if f.filename == "":
        return jsonify({"error": "Empty filename"}), 400
    if not allowed_file(f.filename):
        return jsonify({"error": f"Unsupported file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"}), 400

    # Check size
    f.seek(0, 2)
    size = f.tell()
    f.seek(0)
    if size > MAX_FILE_SIZE:
        return jsonify({"error": "File too large (max 200 MB)"}), 413

    file_id = str(uuid.uuid4())
    upload_dir = os.path.join(UPLOAD_FOLDER, file_id)
    os.makedirs(upload_dir, exist_ok=True)

    ext = f.filename.rsplit(".", 1)[1].lower()
    save_path = os.path.join(upload_dir, f"input.{ext}")
    f.save(save_path)

    with jobs_lock:
        jobs[file_id] = {
            "status": "uploaded",
            "progress": 0,
            "stems": [],
            "error": None,
            "created_at": time.time(),
            "input_path": save_path,
        }

    return jsonify({"file_id": file_id, "filename": f.filename, "size": size})


@app.route("/separate", methods=["POST"])
def separate():
    data = request.get_json(silent=True) or {}
    file_id = data.get("file_id")
    model_name = data.get("model", "htdemucs")
    stem_mode = data.get("stem_mode", "vocals")  # "vocals" or "all"

    valid_models = ["htdemucs", "htdemucs_ft", "htdemucs_6s", "mdx_q"]
    if model_name not in valid_models:
        return jsonify({"error": "Invalid model"}), 400

    two_stems = "vocals" if stem_mode == "vocals" else None

    with jobs_lock:
        job = jobs.get(file_id)

    if not job:
        return jsonify({"error": "Unknown file_id"}), 404
    if job["status"] not in ("uploaded",):
        return jsonify({"error": "Job already started or completed"}), 400

    input_path = job["input_path"]

    thread = threading.Thread(
        target=run_separation,
        args=(file_id, input_path, model_name, two_stems),
        daemon=True,
    )
    thread.start()

    return jsonify({"file_id": file_id, "status": "started"})


@app.route("/status/<file_id>")
def status(file_id):
    with jobs_lock:
        job = jobs.get(file_id)
    if not job:
        return jsonify({"error": "Unknown file_id"}), 404
    return jsonify({
        "status": job["status"],
        "progress": job["progress"],
        "stems": job["stems"],
        "error": job.get("error"),
    })


@app.route("/download/<file_id>/<stem>")
def download(file_id, stem):
    # Sanitize stem name
    stem = stem.replace("..", "").replace("/", "").replace("\\", "")
    out_path = os.path.join(OUTPUT_FOLDER, file_id, f"{stem}.wav")
    if not os.path.isfile(out_path):
        abort(404)
    return send_file(
        out_path,
        as_attachment=True,
        download_name=f"{stem}.wav",
        mimetype="audio/wav",
    )


if __name__ == "__main__":
    print("🎵 Demucs Vocal Isolation App")
    print("   Server: http://127.0.0.1:5000")
    app.run(debug=True, host="0.0.0.0", port=5000, threaded=True)
