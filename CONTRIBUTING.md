# Contributing to Demucs Vocal Isolation App

Thank you for your interest in contributing! 🎉  
All contributions — bug fixes, features, docs, or ideas — are welcome.

---

## 🐛 Reporting Bugs

1. **Search existing [Issues](../../issues)** first to avoid duplicates
2. Open a new issue with:
   - Your OS and Python version
   - Steps to reproduce
   - The full error message or traceback
   - The audio format you were using (WAV, MP3, etc.)

---

## 💡 Suggesting Features

Open an issue with the label `enhancement` and describe:

- What problem it solves
- What the ideal behaviour would look like

---

## 🔧 Submitting a Pull Request

### Setup

```bash
git clone https://github.com/Tharinda-Pamindu/Vocal_Isolator.git
cd demucs-vocal-isolation
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux / macOS
pip install -r requirements.txt
```

### Workflow

```bash
# 1. Create a branch
git checkout -b feature/your-feature-name

# 2. Make your changes

# 3. Test it manually — start the server and try an upload
python app.py

# 4. Commit with a clear message
git commit -m "feat: add support for ..."

# 5. Push and open a PR
git push origin feature/your-feature-name
```

### PR Checklist

- [ ] Tested with at least one WAV file end-to-end
- [ ] No new breaking changes to existing API routes
- [ ] Code follows the existing style (PEP 8 for Python)
- [ ] Updated `README.md` if you added a new feature or changed setup steps

---

## 📁 Project Layout

| Path                   | Purpose                                                           |
| ---------------------- | ----------------------------------------------------------------- |
| `app.py`               | Flask routes, job management, audio conversion, subprocess runner |
| `templates/index.html` | Single-page frontend                                              |
| `static/css/style.css` | Dark glassmorphism theme                                          |
| `static/js/app.js`     | Upload handling, progress polling, stem rendering                 |

---

## 🧪 Testing Tips

- Use a short (10–30 sec) WAV file for quick iteration — Demucs on CPU is slow for long tracks
- Check the Flask console for subprocess stderr if a separation job shows an error
- The `/status/<file_id>` endpoint returns the raw `error` field which is helpful for debugging

---

## 📜 Code of Conduct

Be respectful, constructive, and inclusive. This project follows the [Contributor Covenant](https://www.contributor-covenant.org/) v2.1.

---

## 📄 License

By contributing, you agree that your contributions will be licensed under the **MIT License**.
