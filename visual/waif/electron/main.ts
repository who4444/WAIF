import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const require = createRequire(import.meta.url)
const electron = require('electron') as typeof Electron.CrossProcessExports
const { app, BrowserWindow, globalShortcut, ipcMain, screen } = electron

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// The built directory structure
//
// ├─┬─┬ dist
// │ │ └── index.html
// │ │
// │ ├─┬ dist-electron
// │ │ ├── main.js
// │ │ └── preload.mjs
// │
process.env.APP_ROOT = path.join(__dirname, '..')

// 🚧 Use ['ENV_NAME'] avoid vite:define plugin - Vite@2.x
export const VITE_DEV_SERVER_URL = process.env['VITE_DEV_SERVER_URL']
export const MAIN_DIST = path.join(process.env.APP_ROOT, 'dist-electron')
export const RENDERER_DIST = path.join(process.env.APP_ROOT, 'dist')

process.env.VITE_PUBLIC = VITE_DEV_SERVER_URL ? path.join(process.env.APP_ROOT, 'public') : RENDERER_DIST

let win: Electron.BrowserWindow | null
const supportsWindowShape = process.platform === 'linux' || process.platform === 'win32'

function setWindowInteractive(interactive: boolean) {
  if (!win || win.isDestroyed()) return
  if (supportsWindowShape) return
  win.setIgnoreMouseEvents(!interactive, { forward: true })
}

function setCharacterInputRegion(region: Electron.Rectangle | null) {
  if (!win || win.isDestroyed() || !supportsWindowShape) return

  if (!region) {
    win.setShape([{ x: 0, y: 0, width: 1, height: 1 }])
    return
  }

  win.setIgnoreMouseEvents(false)
  win.setShape([region])
}

function createWindow() {
  if (win && !win.isDestroyed()) {
    win.focus()
    return
  }

  win = new BrowserWindow({
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
      preload: path.join(__dirname, 'preload.mjs'),
    },
  }
)

  win.on('closed', () => {
    win = null
  })

  if (supportsWindowShape) {
    setCharacterInputRegion(null)
  } else {
    setWindowInteractive(false)
  }
  if (process.env.NODE_ENV === 'development') {
    win.webContents.openDevTools({ mode: 'detach' })
  }

  // Test active push message to Renderer-process.
  win.webContents.on('did-finish-load', () => {
    win?.webContents.send('main-process-message', (new Date).toLocaleString())
  })

  if (VITE_DEV_SERVER_URL) {
    win.loadURL(VITE_DEV_SERVER_URL)
  } else {
    // win.loadFile('dist/index.html')
    win.loadFile(path.join(RENDERER_DIST, 'index.html'))
  }
}

// Quit when all windows are closed, except on macOS. There, it's common
// for applications and their menu bar to stay active until the user quits
// explicitly with Cmd + Q.
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
    win = null
  }
})

app.on('activate', () => {
  // On OS X it's common to re-create a window in the app when the
  // dock icon is clicked and there are no other windows open.
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow()
  }
})

app.whenReady().then(() => {
  ipcMain.on('set-mouse-interactive', (_event, interactive: boolean) => {
    setWindowInteractive(interactive)
  })
  ipcMain.on('set-character-input-region', (_event, region: Electron.Rectangle | null) => {
    setCharacterInputRegion(region)
  })

  createWindow()

  if (process.env.NODE_ENV === 'development') {
    globalShortcut.register('Escape', () => {
      app.quit()
    })
  }
})
