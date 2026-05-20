import { Application, Graphics, Assets, Container, Texture } from 'pixi.js'
import { SteeringController } from './steering'
import { getCharSize, initCharacter, loadSpritesheet, onMovementChange, playDrag, playDrop, getBodySprite } from './animator'
import characterSheet from '../assets/image_2.png'

// --- GLOBAL STATE ---
let app: Application
let gen = 0
let steering: SteeringController
let spritesheetLoaded = false

// --- INTERACTION STATE ---
let isDragging = false
let windowPointerHandler: ((e: PointerEvent) => void) | null = null
let isWindowInteractive = false
let lastInputRegionKey = ''

export type InteractionType = 'poke' | 'drag' | 'drop'

function setWindowInteractive(interactive: boolean) {
  if (interactive === isWindowInteractive) return
  isWindowInteractive = interactive
  window.ipcRenderer?.send('set-mouse-interactive', interactive)
}

function setCharacterInputRegion(pos: { x: number; y: number } | null) {
  if (!pos) {
    lastInputRegionKey = ''
    window.ipcRenderer?.send('set-character-input-region', null)
    return
  }

  const size = getCharSize()
  const width = Math.round(Math.max(size.w + 120, 220))
  const height = Math.round(Math.max(size.h + 180, 300))
  const x = Math.round(pos.x - width / 2)
  const y = Math.round(pos.y - height + 50)
  const key = `${x}:${y}:${width}:${height}`

  if (key === lastInputRegionKey) return
  lastInputRegionKey = key
  window.ipcRenderer?.send('set-character-input-region', { x, y, width, height })
}

function isPointerOverCharacter(e: PointerEvent) {
  if (!steering) return false

  const size = getCharSize()
  const halfWidth = Math.max(size.w / 2, 60)
  const height = Math.max(size.h, 120)

  return (
    e.clientX >= steering.pos.x - halfWidth &&
    e.clientX <= steering.pos.x + halfWidth &&
    e.clientY >= steering.pos.y - height &&
    e.clientY <= steering.pos.y + 20
  )
}

export async function initPixi(
  container: HTMLElement,
  onPositionUpdate: (pos: { x: number; y: number }) => void,
  onInteraction?: (type: InteractionType) => void
) {
  // Synchronously destroy any existing app/canvas before creating a new one.
  // Handles double-init, HMR re-run, StrictMode remount, and race between
  // two in-flight initPixi calls where both pass the nuke phase before either
  // appends — destroyPixi increments gen so the older call bails.
  destroyPixi()

  const myGen = ++gen
  console.log('[pixi] initPixi called gen=', myGen)

  // Belt and suspenders: nuke any leaked canvas from prior mount
  const preNuke = container.querySelectorAll('canvas').length
  if (preNuke) console.warn('[pixi] pre-nuke found', preNuke, 'canvases')
  container.querySelectorAll('canvas').forEach(c => c.remove())

  const localApp = new Application()

  try {
    await localApp.init({
      width: window.innerWidth,
      height: window.innerHeight,
      backgroundAlpha: 0,
      antialias: true,
      resolution: window.devicePixelRatio || 1,
      autoDensity: true,
    })
  } catch {
    console.warn('[pixi] app.init rejected gen=', myGen)
    try { localApp.destroy(true) } catch { /* ignore */ }
    return
  }

  // Newer init started or app destroyed — bail
  if (myGen !== gen) {
    console.warn('[pixi] superseded gen=', myGen, 'current gen=', gen, 'app=', !!app)
    try { localApp.destroy(true) } catch { /* ignore */ }
    return
  }

  app = localApp
  app.canvas.style.position = 'fixed'
  app.canvas.style.top = '0'
  app.canvas.style.left = '0'
  app.canvas.style.zIndex = '0'

  // --- DYNAMIC POINTER EVENTS ---
  // Start with 'none' so empty canvas doesn't block background HTML clicks
  app.canvas.style.pointerEvents = 'none'

  windowPointerHandler = (e: PointerEvent) => {
    // If dragging, force canvas to stay active so we don't drop the sprite
    if (isDragging) {
      setWindowInteractive(true)
      app.canvas.style.pointerEvents = 'auto'
      return
    }

    const overCharacter = isPointerOverCharacter(e)
    setWindowInteractive(overCharacter)
    app.canvas.style.pointerEvents = overCharacter ? 'auto' : 'none';
  };

  window.addEventListener('pointermove', windowPointerHandler);

  // Belt and suspenders: nuke again right before append
  const preAppend = container.querySelectorAll('canvas').length
  if (preAppend) console.warn('[pixi] pre-append found', preAppend, 'canvases gen=', myGen)
  container.querySelectorAll('canvas').forEach(c => c.remove())
  container.appendChild(app.canvas)
  console.log('[pixi] canvas appended gen=', myGen)

  // ── LOAD SPRITESHEET ──────────────────────────────────
  let sheet: Texture
  try {
    sheet = await Assets.load(characterSheet)
  } catch {
    if (myGen !== gen) return
    console.warn('[pixi] failed to load spritesheet, using placeholder')
    loadPlaceholder(onPositionUpdate)
    return
  }
  if (myGen !== gen) return

  spritesheetLoaded = true
  loadSpritesheet(sheet)

  const char = new Container()
  char.x = window.innerWidth / 2
  char.y = window.innerHeight - 100
  app.stage.addChild(char)
  setCharacterInputRegion({ x: char.x, y: char.y })
  let lastFacingLeft = false
  let wasMoving = false

  initCharacter(char)
  setupInteraction(onInteraction)

  steering = new SteeringController(
    char.x, char.y,
    window.innerWidth, window.innerHeight,
    (pos, facingLeft) => {
      lastFacingLeft = facingLeft
      char.x = pos.x
      char.y = pos.y
      onMovementChange(true, facingLeft)
      onPositionUpdate({ x: pos.x, y: pos.y })
      setCharacterInputRegion(pos)
    }
  )

  app.ticker.add(({ deltaMS }) => {
    const dt = deltaMS / 1000
    steering.update(dt)
    const moving = steering.isMoving()
    if (wasMoving && !moving) onMovementChange(false, lastFacingLeft)
    wasMoving = moving
  })

  // --- RESIZE HANDLER (Optional but recommended) ---
  window.addEventListener('resize', handleResize)
}

function handleResize() {
  if (!app || !steering) return;
  app.renderer.resize(window.innerWidth, window.innerHeight);
  app.stage.hitArea = app.screen;

  // Update steering boundaries so the character doesn't walk off-screen
  steering.updateBounds?.(window.innerWidth, window.innerHeight);
}

function setupInteraction(onInteraction?: (type: InteractionType) => void) {
  const body = getBodySprite()
  if (!body) return
  const bodySprite = body

  bodySprite.eventMode = 'static'
  bodySprite.cursor = 'grab'

  const HOLD_TO_DRAG_MS = 250
  let isPointerDown = false
  let dragStart = { x: 0, y: 0 }
  let holdTimer: ReturnType<typeof setTimeout> | null = null

  function clearHoldTimer() {
    if (!holdTimer) return
    clearTimeout(holdTimer)
    holdTimer = null
  }

  function startDrag() {
    if (!isPointerDown || isDragging) return
    isDragging = true
    bodySprite.cursor = 'grabbing'
    playDrag()
    onInteraction?.('drag')
    steering?.stopWander()
  }

  bodySprite.on('pointerdown', (e) => {
    isPointerDown = true
    setWindowInteractive(true)
    app.canvas.style.pointerEvents = 'auto'
    dragStart = { x: e.globalX, y: e.globalY }
    clearHoldTimer()
    holdTimer = setTimeout(startDrag, HOLD_TO_DRAG_MS)
  })

  app.stage.eventMode = 'static'
  app.stage.hitArea = app.screen

  app.stage.on('pointermove', (e) => {
    if (!isDragging || !steering) return
    const pos = e.global
    steering.pos.x = pos.x
    steering.pos.y = pos.y
    steering.onMoveExternal?.(pos, pos.x < dragStart.x)
  })

  const endDrag = (e: any) => {
    const wasDragging = isDragging
    clearHoldTimer()
    isPointerDown = false
    isDragging = false
    bodySprite.cursor = 'grab'
    setWindowInteractive(false)
    app.canvas.style.pointerEvents = 'none'

    if (!wasDragging) {
      onInteraction?.('poke')
      return
    }

    const dx = e.globalX - dragStart.x
    const dy = e.globalY - dragStart.y
    onMovementChange(false, dx < 0)
    playDrop()
    if (Math.sqrt(dx * dx + dy * dy) >= 10) onInteraction?.('drop')
  }

  app.stage.on('pointerup', endDrag)
  app.stage.on('pointerupoutside', endDrag)
  app.stage.on('pointercancel', endDrag)
}

export function destroyPixi() {
  gen++ // invalidate in-flight init before touching app
  console.log('[pixi] destroyPixi gen=', gen)

  // --- CLEANUP LISTENERS ---
  if (windowPointerHandler) {
    window.removeEventListener('pointermove', windowPointerHandler);
    windowPointerHandler = null;
  }
  window.removeEventListener('resize', handleResize);
  isDragging = false;
  setWindowInteractive(false)
  setCharacterInputRegion(null)

  steering = null!
  chibiGraphic = null
  spritesheetLoaded = false

  // Nuke every canvas inside pixi-root — catch leaked canvases
  const nukeCount = document.querySelectorAll('#pixi-root canvas').length
  if (nukeCount) console.warn('[pixi] destroy nuking', nukeCount, 'canvases')
  document.querySelectorAll('#pixi-root canvas').forEach(c => {
    try { c.remove() } catch { /* ignore */ }
  })
  if (app) {
    try { app.ticker?.stop() } catch { /* ignore */ }
    try { app.destroy(true, { children: true }) } catch { /* ignore */ }
    app = null!
  }
}

// HMR: tear down before Vite reloads module
if (import.meta.hot) {
  import.meta.hot.dispose(() => destroyPixi())
}

// ── CIRCLE PLACEHOLDER (FALLBACK) ────────────────────────────

const STATE_COLORS: Record<string, number> = {
  idle:         0x7c6dfa,
  listening:    0x38bdf8,
  processing:   0xfb923c,
  speaking:     0x4ade80,
  alert:        0xf43f5e,
  wandering:    0x7c6dfa,
  interacting:  0xf59e0b,
  focused_dim:  0x444441,
  sleeping:     0x3d2060,
}

let chibiGraphic: Graphics | null = null

export function setPlaceholderState(stateName: string) {
  if (spritesheetLoaded) return
  if (!chibiGraphic) return
  chibiGraphic.clear()
  chibiGraphic.circle(0, 0, 40)
  chibiGraphic.fill(STATE_COLORS[stateName] ?? 0x7c6dfa)
}

function loadPlaceholder(
  onPositionUpdate: (pos: { x: number; y: number }) => void
) {
  chibiGraphic = new Graphics()

  chibiGraphic.circle(0, 0, 40)
  chibiGraphic.fill(0x7c6dfa)
  chibiGraphic.x = window.innerWidth / 2
  chibiGraphic.y = window.innerHeight - 100
  app.stage.addChild(chibiGraphic)
  setCharacterInputRegion({ x: chibiGraphic.x, y: chibiGraphic.y })

  steering = new SteeringController(
    chibiGraphic.x,
    chibiGraphic.y,
    window.innerWidth,
    window.innerHeight,
    (pos, facingLeft) => {
      chibiGraphic!.x = pos.x
      chibiGraphic!.y = pos.y
      chibiGraphic!.scale.x = facingLeft ? -1 : 1
      onPositionUpdate({ x: pos.x, y: pos.y })
      setCharacterInputRegion(pos)
    }
  )

  app.ticker.add(({ deltaMS }) => {
    const dt = deltaMS / 1000
    steering.update(dt)
  })
}

export function getSteering() { return steering }
export function getApp() { return app }
