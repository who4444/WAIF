import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";
const require$1 = createRequire(import.meta.url);
const electron = require$1("electron");
const { app, BrowserWindow, globalShortcut, ipcMain, screen } = electron;
const __dirname$1 = path.dirname(fileURLToPath(import.meta.url));
process.env.APP_ROOT = path.join(__dirname$1, "..");
const VITE_DEV_SERVER_URL = process.env["VITE_DEV_SERVER_URL"];
const MAIN_DIST = path.join(process.env.APP_ROOT, "dist-electron");
const RENDERER_DIST = path.join(process.env.APP_ROOT, "dist");
process.env.VITE_PUBLIC = VITE_DEV_SERVER_URL ? path.join(process.env.APP_ROOT, "public") : RENDERER_DIST;
let win;
const supportsWindowShape = process.platform === "linux" || process.platform === "win32";
function setWindowInteractive(interactive) {
  if (!win || win.isDestroyed()) return;
  if (supportsWindowShape) return;
  win.setIgnoreMouseEvents(!interactive, { forward: true });
}
function setCharacterInputRegion(region) {
  if (!win || win.isDestroyed() || !supportsWindowShape) return;
  if (!region) {
    win.setShape([{ x: 0, y: 0, width: 1, height: 1 }]);
    return;
  }
  win.setIgnoreMouseEvents(false);
  win.setShape([region]);
}
function createWindow() {
  if (win && !win.isDestroyed()) {
    win.focus();
    return;
  }
  win = new BrowserWindow(
    {
      width: screen.getPrimaryDisplay().workAreaSize.width,
      height: screen.getPrimaryDisplay().workAreaSize.height,
      x: 0,
      y: 0,
      frame: false,
      transparent: true,
      alwaysOnTop: true,
      skipTaskbar: true,
      resizable: false,
      hasShadow: false,
      webPreferences: {
        contextIsolation: true,
        nodeIntegration: false,
        preload: path.join(__dirname$1, "preload.mjs")
      }
    }
  );
  win.on("closed", () => {
    win = null;
  });
  if (supportsWindowShape) {
    setCharacterInputRegion(null);
  } else {
    setWindowInteractive(false);
  }
  if (process.env.NODE_ENV === "development") {
    win.webContents.openDevTools({ mode: "detach" });
  }
  win.webContents.on("did-finish-load", () => {
    win == null ? void 0 : win.webContents.send("main-process-message", (/* @__PURE__ */ new Date()).toLocaleString());
  });
  if (VITE_DEV_SERVER_URL) {
    win.loadURL(VITE_DEV_SERVER_URL);
  } else {
    win.loadFile(path.join(RENDERER_DIST, "index.html"));
  }
}
app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
    win = null;
  }
});
app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});
app.whenReady().then(() => {
  ipcMain.on("set-mouse-interactive", (_event, interactive) => {
    setWindowInteractive(interactive);
  });
  ipcMain.on("set-character-input-region", (_event, region) => {
    setCharacterInputRegion(region);
  });
  createWindow();
  if (process.env.NODE_ENV === "development") {
    globalShortcut.register("Escape", () => {
      app.quit();
    });
  }
});
export {
  MAIN_DIST,
  RENDERER_DIST,
  VITE_DEV_SERVER_URL
};
