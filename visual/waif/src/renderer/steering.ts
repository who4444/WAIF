export interface Vec2 {
  x: number
  y: number
}

const SPEED = 120 // pixels per second
const ARRIVE_RADIUS = 8
const WANDER_PAUSE_MIN = 1500 // ms
const WANDER_PAUSE_MAX = 4000 // ms

export class SteeringController {
  pos: Vec2
  target: Vec2 | null = null
  onArrive: (() => void) | null = null
  private paused = false
  private pauseTimer = 0
  private screenW: number
  private screenH: number
  private wandering = false
  private onMove: (pos: Vec2, facingLeft: boolean) => void

  constructor(
    startX: number,
    startY: number,
    screenW: number,
    screenH: number,
    onMove: (pos: Vec2, facingLeft: boolean) => void
  ) {
    this.pos = { x: startX, y: startY }
    this.screenW = screenW
    this.screenH = screenH
    this.onMove = onMove
  }
    onMoveExternal(pos: Vec2, facingLeft: boolean) {
      this.pos = pos
      this.onMove(pos, facingLeft)
    }
  // called every ticker frame, dt in seconds
  update(dt: number) {
    if (this.paused) {
      this.pauseTimer -= dt * 1000
      if (this.pauseTimer <= 0) {
        this.paused = false
        if (this.wandering) this.pickWanderTarget()
      }
      return
    }

    if (!this.target) return

    const dx = this.target.x - this.pos.x
    const dy = this.target.y - this.pos.y
    const dist = Math.sqrt(dx * dx + dy * dy)

    if (dist < ARRIVE_RADIUS) {
      this.target = null
      this.onArrive?.()

      if (this.wandering) {
        // pause before picking next target
        this.paused = true
        this.pauseTimer = WANDER_PAUSE_MIN + Math.random() * (WANDER_PAUSE_MAX - WANDER_PAUSE_MIN)
      }
      return
    }

    const nx = dx / dist
    const ny = dy / dist
    const step = SPEED * dt

    this.pos.x += nx * step
    this.pos.y += ny * step

    // clamp to screen
    this.pos.x = Math.max(40, Math.min(this.pos.x, this.screenW - 40))
    this.pos.y = Math.max(40, Math.min(this.pos.y, this.screenH - 80))

    this.onMove(this.pos, dx < 0)
  }

  goTo(x: number, y: number, onArrive?: () => void) {
    this.target = { x, y }
    this.onArrive = onArrive ?? null
    this.wandering = false
  }

  startWander() {
    this.wandering = true
    this.pickWanderTarget()
  }

  stopWander() {
    this.wandering = false
    this.target = null
  }

  private pickWanderTarget() {
    const margin = 80
    this.target = {
      x: margin + Math.random() * (this.screenW - margin * 2),
      y: margin + Math.random() * (this.screenH - margin * 2),
    }
  }
}