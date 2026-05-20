import { AnimatedSprite, Texture, Rectangle, Container } from 'pixi.js'

// ── spritesheet grid config ───────────────────────────────────
// Layout: 9 rows. Tweak frame size, row numbers, frame count per state.

const FRAME_W = 189
const FRAME_H = 208
const CHAR_SCALE = 0.5   // display scale (native 256×208 too large)

export function getCharSize() {
  return { w: FRAME_W * CHAR_SCALE, h: FRAME_H * CHAR_SCALE }
}

export function getBodySprite() { return bodySprite }

// Row index → machine state (0 = top row)
// Spritesheet rows: idle, run_right, run_left, waving, jumping, failed, waiting, running, review
const ROW_MAP: Record<string, number> = {
  idle:         0,   // idle
  run_right:    1,
  run_left:     2,
  listening:    6,   // waiting
  processing:   8,   // review
  speaking:     3,   // waving
  alert:        4,   // jumping
  interacting:  3,   // waving
  focused_dim:  8,   // idle (dim version)
  sleeping:     5,   // waiting (still pose)
}

// Frames to use per state (columns read left→right)
const STATE_FRAME_COUNT: Record<string, number> = {
  idle:         4,
  run_right:    4,
  run_left:     4,
  listening:    4,
  processing:   4,
  speaking:     4,
  alert:        4,
  interacting:  4,
  focused_dim:  4,
  sleeping:     4,
}

const STATE_FPS: Record<string, number> = {
  idle:         5,
  run_right:    5,
  run_left:     5,
  listening:    4,
  processing:   4,
  speaking:     5,
  alert:        5,
  interacting:  5,
  focused_dim:  5,
  sleeping:     5,
}

// ── runtime state ─────────────────────────────────────────────
let charContainer: Container | null = null
let bodySprite: AnimatedSprite | null = null
let currentState = ''
let currentAnim = ''
let isPlayingEmote = false
let isMoving = false

const stateTextures: Record<string, Texture[]> = {}

// ── spritesheet loader ────────────────────────────────────────

export function loadSpritesheet(sheet: Texture) {
  const src = sheet.source

  for (const [state, row] of Object.entries(ROW_MAP)) {
    const count = STATE_FRAME_COUNT[state] ?? 4
    const frames: Texture[] = []
    for (let col = 0; col < count; col++) {
      const rect = new Rectangle(col * FRAME_W, row * FRAME_H, FRAME_W, FRAME_H)
      frames.push(new Texture({ source: src, frame: rect }))
    }
    stateTextures[state] = frames
  }
}

// ── helpers ───────────────────────────────────────────────────

function setBodyAnim(state: string) {
  if (!bodySprite) return
  if (state === currentAnim) return
  const frames = stateTextures[state]
  if (!frames || frames.length === 0) return

  currentAnim = state
  bodySprite.textures = frames
  bodySprite.animationSpeed = (STATE_FPS[state] ?? 6) / 60
  bodySprite.loop = true
  bodySprite.play()
}

// ── public API ────────────────────────────────────────────────

export function initCharacter(container: Container) {
  charContainer = container
  charContainer.scale.set(CHAR_SCALE, CHAR_SCALE)

  const idleFrames = stateTextures['idle'] ?? [Texture.EMPTY]
  bodySprite = new AnimatedSprite(idleFrames)
  bodySprite.anchor.set(0.5, 1)
  bodySprite.animationSpeed = (STATE_FPS.idle ?? 6) / 60
  bodySprite.loop = true
  bodySprite.play()
  charContainer.addChild(bodySprite)

  currentState = 'idle'
  currentAnim = 'idle'
}

export function onStateChange(newState: string) {
  if (newState === currentState) return
  currentState = newState

  if (isPlayingEmote || isMoving) return

  const animName = ROW_MAP[newState] !== undefined ? newState : 'idle'
  setBodyAnim(animName)
}

export function onMovementChange(moving: boolean, facingLeft: boolean) {
  if (!charContainer) return
  charContainer.scale.x = CHAR_SCALE
  charContainer.scale.y = CHAR_SCALE

  if (isPlayingEmote) return

  if (moving) {
    isMoving = true
    setBodyAnim(facingLeft ? 'run_left' : 'run_right')
    return
  }

  if (!isMoving) return
  isMoving = false
  const animName = ROW_MAP[currentState] !== undefined ? currentState : 'idle'
  setBodyAnim(animName)
}

// ── emotes ────────────────────────────────────────────────────

let emoteTimer: ReturnType<typeof setTimeout> | null = null

export function playEmote(_name: string) {
  if (!bodySprite) return
  if (isPlayingEmote) return

  isPlayingEmote = true

  const origX = bodySprite.scale.x
  const origY = bodySprite.scale.y
  const dir = origX >= 0 ? 1 : -1

  bodySprite.scale.set(dir * 1, 1)

  if (emoteTimer) clearTimeout(emoteTimer)
  emoteTimer = setTimeout(() => {
    if (!bodySprite) return
    bodySprite.scale.set(origX, origY)
    isPlayingEmote = false
  }, 120)
}

export function playPoke()  { playEmote('poke') }
export function playDrag()  { playEmote('drag') }
export function playDrop()  { playEmote('drop') }
export function playReach() { playEmote('reach') }
