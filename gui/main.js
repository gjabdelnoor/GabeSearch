const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

let currentProcess = null;

function createWindow() {
  const win = new BrowserWindow({
    width: 400,
    height: 500,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    }
  });
  win.loadFile('index.html');
}

app.whenReady().then(() => {
  createWindow();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => {
  if (currentProcess) {
    currentProcess.kill();
    currentProcess = null;
  }
  spawn('docker-compose', ['down'], { cwd: path.join(__dirname, '..') });
});

ipcMain.handle('start', (event, params) => {
  if (currentProcess) return;

  const env = {
    ...process.env,
    TOP_K: String(params.topK),
    QUERIES: String(params.numQueries),
    PER_PAGE_CHARS: String(params.perPageChars),
    TOTAL_CHARS: String(params.totalChars)
  };

  const script = process.platform === 'win32' ? 'start_servers.bat' : './start_servers.sh';
  currentProcess = spawn(script, { cwd: path.join(__dirname, '..'), env, shell: true });

  currentProcess.on('close', code => {
    currentProcess = null;
    event.sender.send('stopped', code);
  });

  currentProcess.on('error', err => {
    currentProcess = null;
    event.sender.send('error', err.message);
  });

  event.sender.send('started');
});

ipcMain.handle('stop', event => {
  if (currentProcess) {
    currentProcess.kill();
    currentProcess = null;
  }
  const down = spawn('docker-compose', ['down'], { cwd: path.join(__dirname, '..') });
  down.on('close', code => event.sender.send('stopped', code));
  down.on('error', err => event.sender.send('error', err.message));
});

ipcMain.handle('upload-files', async (event) => {
  const { canceled, filePaths } = await dialog.showOpenDialog({ properties: ['openFile', 'multiSelections'] });
  if (canceled || filePaths.length === 0) {
    event.sender.send('upload-complete', 1);
    return;
  }
  const py = process.platform === 'win32' ? 'python' : 'python3';
  const proc = spawn(py, ['orchestrator/ingest_files.py', ...filePaths], { cwd: path.join(__dirname, '..') });
  proc.on('close', code => event.sender.send('upload-complete', code));
  proc.on('error', err => event.sender.send('upload-error', err.message));
});
