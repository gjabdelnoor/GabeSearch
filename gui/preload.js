const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('api', {
  start: (params) => ipcRenderer.invoke('start', params),
  stop: () => ipcRenderer.invoke('stop'),
  onStarted: (callback) => ipcRenderer.on('started', callback),
  onStopped: (callback) => ipcRenderer.on('stopped', (event, code) => callback(code)),
  onError: (callback) => ipcRenderer.on('error', (event, message) => callback(message)),
  uploadFiles: () => ipcRenderer.invoke('upload-files'),
  onUploadComplete: (callback) => ipcRenderer.on('upload-complete', (event, code) => callback(code)),
  onUploadError: (callback) => ipcRenderer.on('upload-error', (event, message) => callback(message))
});
