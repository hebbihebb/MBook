const { app, BrowserWindow } = require("electron");
const path = require("path");
const { PythonShell } = require("python-shell");

let mainWindow;
let pythonShell;

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

  // Start the Flask server
  pythonShell = new PythonShell(path.join(__dirname, "webview_server.py"));

  // Load the UI
  mainWindow.loadURL("http://127.0.0.1:5000");

  mainWindow.on("closed", () => {
    mainWindow = null;
    // Kill the python process when the window is closed
    if (pythonShell) {
      pythonShell.kill();
    }
  });
}

app.on("ready", createWindow);

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("activate", () => {
  if (mainWindow === null) {
    createWindow();
  }
});
