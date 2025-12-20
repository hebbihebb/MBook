const { app, BrowserWindow, ipcMain, dialog } = require("electron");
const path = require("path");
const { PythonShell } = require("python-shell");
const http = require("http");

let mainWindow;
let pythonShell;
let pythonReady = false;

// Function to check if Python server is ready
function waitForPythonServer(callback, retries = 30) {
  const options = {
    host: '127.0.0.1',
    port: 5000,
    path: '/api/voice_presets',
    timeout: 1000
  };

  const req = http.get(options, (res) => {
    if (res.statusCode === 200) {
      pythonReady = true;
      callback();
    } else if (retries > 0) {
      setTimeout(() => waitForPythonServer(callback, retries - 1), 500);
    }
  });

  req.on('error', () => {
    if (retries > 0) {
      setTimeout(() => waitForPythonServer(callback, retries - 1), 500);
    }
  });

  req.on('timeout', () => {
    req.destroy();
    if (retries > 0) {
      setTimeout(() => waitForPythonServer(callback, retries - 1), 500);
    }
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  // Start the Flask server in background
  pythonShell = new PythonShell(path.join(__dirname, "webview_server.py"));

  pythonShell.on('message', (message) => {
    console.log('[Python]', message);
  });

  pythonShell.on('error', (err) => {
    console.error('[Python Error]', err);
  });

  // Wait for Python server to be ready before loading UI
  waitForPythonServer(() => {
    console.log('Python server is ready');
    // Load the UI via the Flask server to ensure template rendering and CSRF token injection
    mainWindow.loadURL('http://127.0.0.1:5000/');
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
    // Kill the python process when the window is closed
    if (pythonShell && pythonShell.childProcess) {
      pythonShell.childProcess.kill();
    }
  });
}

// IPC Handlers for file dialogs
ipcMain.handle('dialog:openFile', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: 'Select EPUB File',
    filters: [
      { name: 'EPUB files', extensions: ['epub'] },
      { name: 'All Files', extensions: ['*'] }
    ],
    properties: ['openFile']
  });

  if (!result.canceled && result.filePaths.length > 0) {
    return result.filePaths[0];
  }
  return null;
});

ipcMain.handle('dialog:openFolder', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: 'Select Output Directory',
    properties: ['openDirectory']
  });

  if (!result.canceled && result.filePaths.length > 0) {
    return result.filePaths[0];
  }
  return null;
});

// IPC Handler for API requests (proxy to Python backend)
ipcMain.handle('api:request', async (event, endpoint, options = {}) => {
  return new Promise((resolve, reject) => {
    const url = `http://127.0.0.1:5000${endpoint}`;
    const method = options.method || 'GET';
    const body = options.body ? JSON.stringify(options.body) : null;

    const urlObj = new URL(url);
    const reqOptions = {
      hostname: urlObj.hostname,
      port: urlObj.port,
      path: urlObj.pathname,
      method: method,
      headers: {
        'Content-Type': 'application/json',
      }
    };

    if (body) {
      reqOptions.headers['Content-Length'] = Buffer.byteLength(body);
    }

    const req = http.request(reqOptions, (res) => {
      let data = '';
      res.on('data', (chunk) => {
        data += chunk;
      });
      res.on('end', () => {
        try {
          const parsed = JSON.parse(data);
          resolve(parsed);
        } catch (e) {
          resolve({ data: data });
        }
      });
    });

    req.on('error', (error) => {
      reject(error);
    });

    if (body) {
      req.write(body);
    }
    req.end();
  });
});

app.on("ready", createWindow);

app.on("window-all-closed", () => {
  if (pythonShell && pythonShell.childProcess) {
    pythonShell.childProcess.kill();
  }
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("activate", () => {
  if (mainWindow === null) {
    createWindow();
  }
});
