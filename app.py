import os
import sys
import copy
import uuid
import time
import threading
import shutil
import subprocess
import numpy as np
import soundfile as sf
from flask import Flask, request, jsonify, render_template, send_file, abort

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
OUTPUT_FOLDER = os.path.join(BASE_DIR, "outputs")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {"mp3", "wav", "flac", "ogg", "m4a", "aac"}
MAX_FILE_SIZE = 200 * 1024 * 1024  # 200 MB

# In-memory job store
jobs = {}
jobs_lock = threading.Lock()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def cleanup_old_jobs():
    cutoff = time.time() - 3600
    with jobs_lock:
        expired = [fid for fid, j in jobs.items() if j.get("created_at", 0) < cutoff]
    for fid in expired:
        _delete_job_files(fid)
        with jobs_lock:
            jobs.pop(fid, None)


def _delete_job_files(file_id):
    for folder in [UPLOAD_FOLDER, OUTPUT_FOLDER]:
        d = os.path.join(folder, file_id)
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)


def convert_to_wav(input_path, output_wav_path):
    """
    Convert any audio file to a 44.1 kHz stereo WAV using audioread + soundfile.
    This requires NO FFmpeg or system-level codecs.
    - WAV/FLAC: read directly via soundfile
    - MP3/OGG/M4A: decoded via audioread (uses OS codecs + mad/pymad fallback)
    """
    ext = input_path.rsplit(".", 1)[-1].lower()

    # soundfile can read WAV and FLAC directly
    if ext in ("wav", "flac"):
        data, samplerate = sf.read(input_path, dtype="float32", always_2d=True)
        sf.write(output_wav_path, data, samplerate, subtype="PCM_16")
        return

    # For MP3/OGG etc. use audioread
    import audioread
    TARGET_SR = 44100
    N_CH = 2

    raw_data = []
    with audioread.audio_open(input_path) as f:
        file_sr = f.samplerate
        file_ch = f.channels
        for block in f:
            raw_data.append(block)

    # Combine all raw int16 bytes, convert to float32
    raw_bytes = b"".join(raw_data)
    samples = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32768.0

    # Reshape to (frames, channels)
    if file_ch > 1:
        samples = samples.reshape(-1, file_ch)
    else:
        samples = samples.reshape(-1, 1)

    # Convert mono → stereo if needed
    if samples.shape[1] == 1:
        samples = np.repeat(samples, 2, axis=1)
    elif samples.shape[1] > 2:
        samples = samples[:, :2]

    # Resample if needed using a simple linear interpolation
    if file_sr != TARGET_SR:
        from julius import resample_frac
        import torch
        tensor = torch.from_numpy(samples.T)  # (C, T)
        tensor = resample_frac(tensor, file_sr, TARGET_SR)
        samples = tensor.numpy().T

    sf.write(output_wav_path, samples, TARGET_SR, subtype="PCM_16")


def run_separation(file_id, input_path, model_name, two_stems):
    """Run Demucs separation using subprocess (demucs 4.0.1 compatible)."""
    wav_path = None
    try:
        with jobs_lock:
            jobs[file_id]["status"] = "processing"
            jobs[file_id]["progress"] = 5

        out_dir = os.path.join(OUTPUT_FOLDER, file_id)
        os.makedirs(out_dir, exist_ok=True)

        # Step 1: Convert input to WAV (bypasses all torchaudio backend issues)
        ext = input_path.rsplit(".", 1)[-1].lower()
        if ext != "wav":
            wav_path = input_path.rsplit(".", 1)[0] + "_converted.wav"
            convert_to_wav(input_path, wav_path)
            demucs_input = wav_path
        else:
            demucs_input = input_path

        with jobs_lock:
            jobs[file_id]["progress"] = 20

        # Step 2: Run demucs separation on the WAV file
        python_exe = sys.executable
        cmd = [
            python_exe, "-m", "demucs.separate",
            "--out", out_dir,
            "--name", model_name,
        ]
        if two_stems:
            cmd += ["--two-stems", two_stems]
        cmd.append(demucs_input)

        # Force soundfile backend as primary torchaudio backend
        env = copy.copy(os.environ)
        env["TORCHAUDIO_BACKEND"] = "soundfile"

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
        )

        with jobs_lock:
            jobs[file_id]["progress"] = 85

        if result.returncode != 0:
            # Filter out known harmless torchcodec warning from stderr
            stderr = "\n".join(
                line for line in result.stderr.splitlines()
                if "torchcodec" not in line and "ModuleNotFoundError" not in line
            ).strip()
            raise RuntimeError(stderr or f"Demucs exited with code {result.returncode}")

        # Step 3: Move output WAV stems to flat output directory
        stems_info = []
        model_out = os.path.join(out_dir, model_name)
        if os.path.isdir(model_out):
            track_folders = [
                d for d in os.listdir(model_out)
                if os.path.isdir(os.path.join(model_out, d))
            ]
            if track_folders:
                track_dir = os.path.join(model_out, track_folders[0])
                for wav_file in os.listdir(track_dir):
                    if wav_file.endswith(".wav"):
                        stem_name = wav_file[:-4]
                        src = os.path.join(track_dir, wav_file)
                        dst = os.path.join(out_dir, f"{stem_name}.wav")
                        shutil.copy2(src, dst)
                        stems_info.append(stem_name)

        if not stems_info:
            raise RuntimeError(
                "Separation finished but no WAV stems were produced. "
                + (result.stderr or "")
            )

        with jobs_lock:
            jobs[file_id]["status"] = "done"
            jobs[file_id]["progress"] = 100
            jobs[file_id]["stems"] = stems_info

    except Exception as e:
        with jobs_lock:
            jobs[file_id]["status"] = "error"
            jobs[file_id]["error"] = str(e)
    finally:
        for path in [input_path, wav_path]:
            try:
                if path and os.path.isfile(path):
                    os.remove(path)
            except Exception:
                pass


# ── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    cleanup_old_jobs()

    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty filename"}), 400
    if not allowed_file(f.filename):
        return jsonify({"error": f"Unsupported type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"}), 400

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
    stem_mode = data.get("stem_mode", "vocals")

    valid_models = ["htdemucs", "htdemucs_ft", "htdemucs_6s", "mdx_q"]
    if model_name not in valid_models:
        return jsonify({"error": "Invalid model"}), 400

    two_stems = "vocals" if stem_mode == "vocals" else None

    with jobs_lock:
        job = jobs.get(file_id)

    if not job:
        return jsonify({"error": "Unknown file_id"}), 404
    if job["status"] != "uploaded":
        return jsonify({"error": "Job already started or completed"}), 400

    thread = threading.Thread(
        target=run_separation,
        args=(file_id, job["input_path"], model_name, two_stems),
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
    print("Demucs Vocal Isolation App")
    print("   Server: http://127.0.0.1:5000")
    app.run(debug=True, host="0.0.0.0", port=5000, threaded=True)
