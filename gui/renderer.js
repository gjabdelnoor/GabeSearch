window.addEventListener('DOMContentLoaded', () => {
  const startBtn = document.getElementById('startBtn');
  const stopBtn = document.getElementById('stopBtn');
  const uploadBtn = document.getElementById('uploadBtn');
  const inputs = Array.from(document.querySelectorAll('input[type=number]'));
  const status = document.getElementById('status');

  const setRunning = () => {
    startBtn.textContent = 'Running';
    startBtn.disabled = true;
    stopBtn.disabled = false;
    inputs.forEach(i => (i.disabled = true));
    status.textContent = 'Running';
  };

  const setStopped = () => {
    startBtn.textContent = 'Start';
    startBtn.disabled = false;
    stopBtn.disabled = true;
    inputs.forEach(i => (i.disabled = false));
    status.textContent = 'Stopped';
  };

  startBtn.onclick = async () => {
    startBtn.disabled = true;
    startBtn.textContent = 'Starting...';
    const perPageChars = parseInt(document.getElementById('perPage').value, 10);
    const totalChars = parseInt(document.getElementById('totalChars').value, 10);
    const topK = parseInt(document.getElementById('topK').value, 10);
    const numQueries = parseInt(document.getElementById('numQueries').value, 10);
    await window.api.start({ perPageChars, totalChars, topK, numQueries });
  };

  stopBtn.onclick = async () => {
    stopBtn.disabled = true;
    status.textContent = 'Stopping...';
    await window.api.stop();
  };

  uploadBtn.onclick = async () => {
    uploadBtn.disabled = true;
    status.textContent = 'Uploading...';
    await window.api.uploadFiles();
    uploadBtn.disabled = false;
  };

  window.api.onStarted(() => setRunning());
  window.api.onStopped(code => {
    setStopped();
    if (code !== 0) {
      status.textContent = `Stopped (code ${code})`;
    }
  });
  window.api.onError(message => {
    setStopped();
    status.textContent = `Error: ${message}`;
  });

  window.api.onUploadComplete(code => {
    if (code === 0) {
      status.textContent = 'Upload complete';
    } else {
      status.textContent = `Upload failed (code ${code})`;
    }
  });
  window.api.onUploadError(message => {
    status.textContent = `Upload error: ${message}`;
  });

  setStopped();
});
