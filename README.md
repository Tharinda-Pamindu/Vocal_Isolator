# 🎵 Demucs Vocal Isolation App

A sleek, browser-based audio stem separation tool powered by **Meta's Demucs v4** (`htdemucs`). Upload any audio file, isolate vocals from instruments, and download each stem — all from a beautiful dark glassmorphism UI.

![App Screenshot](https://github.com/Tharinda-Pamindu/Vocal_Isolator/blob/main/static/assest/img-ss.png)

---

## ✨ Features

- 🎤 **Vocal & instrument isolation** — separate vocals, drums, bass, and other stems
- 🎛️ **Multiple Demucs models** — `htdemucs`, `htdemucs_ft`, `htdemucs_6s`, `mdx_q`
- 📁 **Drag & drop upload** — supports WAV, FLAC, MP3, OGG, M4A (up to 200 MB)
- 📊 **Real-time progress** — live progress bar while Demucs runs
- ▶️ **In-browser playback** — listen to each stem directly from the results panel
- ⬇️ **Download stems** — save any stem as a WAV file
- 🌙 **Premium dark UI** — animated glassmorphism design

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+ (tested on 3.13)
- No FFmpeg required for WAV/FLAC input ✅

### 1. Clone & set up

```bash
git clone https://github.com/Tharinda-Pamindu/Vocal_Isolator.git
cd demucs-vocal-isolation

python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the app

```bash
python app.py
```

Open **http://localhost:5000** in your browser.

> **First run:** Demucs will download model weights (~200 MB for `htdemucs`). This only happens once and is cached locally.

---

## 📂 Project Structure

```
demucs-vocal-isolation/
├── app.py                  # Flask backend + separation logic
├── requirements.txt
├── templates/
│   └── index.html          # Single-page UI
└── static/
    ├── css/style.css        # Glassmorphism dark theme
    └── js/app.js            # Upload, polling, results rendering
```

---

## 🎛️ Available Models

| Model         | Description                                               | Speed |
| ------------- | --------------------------------------------------------- | ----- |
| `htdemucs`    | Latest hybrid transformer — best quality                  | ★★★   |
| `htdemucs_ft` | Fine-tuned version — higher quality, slower               | ★★    |
| `htdemucs_6s` | 6-stem output (vocals, drums, bass, guitar, piano, other) | ★★    |
| `mdx_q`       | Quantized MDX model — faster, smaller memory              | ★★★★  |

---

## 🛠️ Stem Modes

| Mode            | Output                                             |
| --------------- | -------------------------------------------------- |
| **Vocals only** | `vocals.wav` + `no_vocals.wav`                     |
| **All stems**   | `vocals.wav`, `drums.wav`, `bass.wav`, `other.wav` |

---

## 📋 Requirements

```
flask>=3.0.0
demucs>=4.0.0
torch>=2.0.0
torchaudio>=2.0.0
numpy
soundfile
audioread
```

---

## ⚠️ Known Limitations

- **MP3 / M4A input** requires [FFmpeg](https://ffmpeg.org/download.html) to be installed and on your system PATH
- **WAV and FLAC** work natively with no extra dependencies
- `torchaudio 2.10+` requires a fix applied automatically at runtime (see `app.py`) for Python 3.13 compatibility

---

## 🧠 How It Works

1. **Upload** — audio is saved server-side as a temp file
2. **Convert** — any non-WAV file is decoded to WAV via `soundfile` / `audioread`
3. **Separate** — `python -m demucs.separate` runs in a background thread
4. **Stream** — results are polled every 2 seconds and rendered in the browser
5. **Cleanup** — temp files are deleted automatically after 1 hour

---

## 🤝 Contributing

Pull requests are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on reporting bugs, suggesting features, and submitting PRs.

---

## 📄 License

This project is licensed under the **[MIT License](LICENSE)**.  
Demucs itself is licensed under the [MIT License](https://github.com/facebookresearch/demucs/blob/main/LICENSE) by Meta Platforms.

---

## 🙏 Credits

- [Demucs](https://github.com/facebookresearch/demucs) — Meta AI Research
- [Flask](https://flask.palletsprojects.com/) — Pallets
- [PyTorch](https://pytorch.org/) — Meta AI
