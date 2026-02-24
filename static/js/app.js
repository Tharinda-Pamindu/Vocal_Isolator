/* ============================================================
   Demucs Studio — app.js
   Handles: drag-drop upload, settings, API calls,
            progress polling, audio player, downloads
   ============================================================ */

(function () {
  'use strict';

  // ── State ───────────────────────────────────────────────────
  let selectedFile = null;
  let selectedModel = 'htdemucs';
  let selectedMode = 'vocals';
  let currentFileId = null;
  let pollTimer = null;

  // ── Elements ─────────────────────────────────────────────────
  const dropZone = document.getElementById('drop-zone');
  const fileInput = document.getElementById('file-input');
  const filePreview = document.getElementById('file-preview');
  const fileName = document.getElementById('file-name');
  const fileSize = document.getElementById('file-size');
  const removeFileBtn = document.getElementById('remove-file');

  const processBtn = document.getElementById('process-btn');
  const btnLabel = document.getElementById('btn-label');

  const progressSection = document.getElementById('progress-section');
  const progressBar = document.getElementById('progress-bar');
  const progressPct = document.getElementById('progress-pct');
  const progressMsg = document.getElementById('progress-message');

  const resultsSection = document.getElementById('results-section');
  const stemsGrid = document.getElementById('stems-grid');
  const newUploadBtn = document.getElementById('new-upload-btn');

  const errorToast = document.getElementById('error-toast');
  const errorMsg = document.getElementById('error-msg');

  // ── Drag & Drop ──────────────────────────────────────────────
  dropZone.addEventListener('click', () => fileInput.click());
  dropZone.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') fileInput.click(); });

  dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('dragover'); });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  });

  fileInput.addEventListener('change', () => {
    if (fileInput.files[0]) handleFile(fileInput.files[0]);
  });

  removeFileBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    clearFile();
  });

  function handleFile(file) {
    const allowedTypes = ['audio/mpeg', 'audio/wav', 'audio/flac', 'audio/ogg',
                          'audio/mp4', 'audio/aac', 'audio/x-m4a', 'video/mp4'];
    const allowedExt = /\.(mp3|wav|flac|ogg|m4a|aac)$/i;

    if (!allowedExt.test(file.name)) {
      showError('Unsupported file type. Please upload MP3, WAV, FLAC, OGG, M4A, or AAC.');
      return;
    }

    if (file.size > 200 * 1024 * 1024) {
      showError('File is too large. Maximum size is 200 MB.');
      return;
    }

    selectedFile = file;
    fileName.textContent = file.name;
    fileSize.textContent = formatBytes(file.size);
    filePreview.classList.remove('hidden');
    dropZone.style.display = 'none';
    processBtn.disabled = false;
    resetResults();
  }

  function clearFile() {
    selectedFile = null;
    fileInput.value = '';
    filePreview.classList.add('hidden');
    dropZone.style.display = '';
    processBtn.disabled = true;
    resetResults();
    stopPolling();
  }

  // ── Model / Mode Selection ───────────────────────────────────
  document.querySelectorAll('.model-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.model-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      selectedModel = btn.dataset.model;
    });
  });

  document.querySelectorAll('.stem-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.stem-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      selectedMode = btn.dataset.mode;
      btnLabel.textContent = selectedMode === 'vocals' ? 'Isolate Vocals' : 'Separate All Stems';
    });
  });

  // ── Process ──────────────────────────────────────────────────
  processBtn.addEventListener('click', startProcessing);

  async function startProcessing() {
    if (!selectedFile) return;

    processBtn.disabled = true;
    processBtn.style.opacity = '0.7';
    btnLabel.textContent = 'Uploading...';

    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
      // 1. Upload
      const uploadRes = await fetch('/upload', { method: 'POST', body: formData });
      const uploadData = await uploadRes.json();

      if (!uploadRes.ok) throw new Error(uploadData.error || 'Upload failed');

      currentFileId = uploadData.file_id;
      btnLabel.textContent = 'Starting separation...';

      // 2. Separate
      const sepRes = await fetch('/separate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_id: currentFileId,
          model: selectedModel,
          stem_mode: selectedMode,
        }),
      });
      const sepData = await sepRes.json();
      if (!sepRes.ok) throw new Error(sepData.error || 'Separation failed to start');

      // 3. Show progress and start polling
      showProgress();
      startPolling(currentFileId);

    } catch (err) {
      showError(err.message);
      resetBtn();
    }
  }

  // ── Polling ──────────────────────────────────────────────────
  function startPolling(fileId) {
    stopPolling();
    pollTimer = setInterval(async () => {
      try {
        const res = await fetch(`/status/${fileId}`);
        const data = await res.json();

        updateProgress(data.progress, data.status);

        if (data.status === 'done') {
          stopPolling();
          showResults(fileId, data.stems);
        } else if (data.status === 'error') {
          stopPolling();
          showError(data.error || 'An error occurred during separation.');
          hideProgress();
          resetBtn();
        }
      } catch (e) {
        // Network hiccup — keep polling
      }
    }, 1500);
  }

  function stopPolling() {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  }

  // ── Progress UI ──────────────────────────────────────────────
  function showProgress() {
    progressSection.classList.remove('hidden');
    resultsSection.classList.add('hidden');
    updateProgress(0, 'queued');
  }

  function hideProgress() {
    progressSection.classList.add('hidden');
  }

  function updateProgress(pct, status) {
    progressBar.style.width = `${pct}%`;
    progressPct.textContent = `${pct}%`;
    progressMsg.textContent = statusMessage(status, pct);
  }

  function statusMessage(status, pct) {
    if (status === 'uploaded' || status === 'queued') return 'Queued — waiting to start…';
    if (pct < 20) return 'Loading Demucs model weights…';
    if (pct < 80) return `Separating audio stems on ${isGPU() ? 'GPU 🚀' : 'CPU'}…`;
    if (pct < 100) return 'Saving output files…';
    return 'Finishing up…';
  }

  function isGPU() {
    // We can't know from the frontend, assume CPU (backend will use GPU if available)
    return false;
  }

  // ── Results UI ───────────────────────────────────────────────
  const stemEmojis = {
    vocals: '🎤',
    no_vocals: '🎸',
    drums: '🥁',
    bass: '🎵',
    other: '🎹',
    guitar: '🎸',
    piano: '🎹',
  };

  const stemLabels = {
    vocals: 'Vocals',
    no_vocals: 'Instrumental',
    drums: 'Drums',
    bass: 'Bass',
    other: 'Other',
    guitar: 'Guitar',
    piano: 'Piano',
  };

  function showResults(fileId, stems) {
    hideProgress();
    stemsGrid.innerHTML = '';

    stems.forEach((stem) => {
      const downloadUrl = `/download/${fileId}/${stem}`;
      const emoji = stemEmojis[stem] || '🎵';
      const label = stemLabels[stem] || capitalize(stem);

      const card = document.createElement('div');
      card.className = 'stem-card';
      card.innerHTML = `
        <div class="stem-card-icon">${emoji}</div>
        <div class="stem-card-name">${label}</div>
        <audio controls src="${downloadUrl}" preload="metadata"></audio>
        <a class="stem-download-btn" href="${downloadUrl}" download="${stem}.wav">
          ⬇ Download WAV
        </a>
      `;
      stemsGrid.appendChild(card);
    });

    resultsSection.classList.remove('hidden');
    processBtn.style.opacity = '';
    processBtn.disabled = false;
    btnLabel.textContent = selectedMode === 'vocals' ? 'Isolate Vocals' : 'Separate All Stems';
  }

  newUploadBtn.addEventListener('click', () => {
    resetResults();
    clearFile();
    stopPolling();
    document.getElementById('upload-section').scrollIntoView({ behavior: 'smooth' });
  });

  function resetResults() {
    resultsSection.classList.add('hidden');
    progressSection.classList.add('hidden');
    stemsGrid.innerHTML = '';
    currentFileId = null;
  }

  function resetBtn() {
    processBtn.disabled = false;
    processBtn.style.opacity = '';
    btnLabel.textContent = selectedMode === 'vocals' ? 'Isolate Vocals' : 'Separate All Stems';
  }

  // ── Error Toast ──────────────────────────────────────────────
  let errorTimer = null;

  function showError(msg) {
    errorMsg.textContent = msg;
    errorToast.classList.remove('hidden');
    if (errorTimer) clearTimeout(errorTimer);
    errorTimer = setTimeout(() => errorToast.classList.add('hidden'), 6000);
  }

  // ── Utilities ────────────────────────────────────────────────
  function formatBytes(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  }

  function capitalize(s) {
    return s.charAt(0).toUpperCase() + s.slice(1);
  }

})();
