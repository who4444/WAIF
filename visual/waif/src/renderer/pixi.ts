import { Application, Graphics } from 'pixi.js'
import { SteeringController } from './steering'

let app: Application
let initialized = false
let steering: SteeringController

export async function initPixi(
  container: HTMLElement,
  onPositionUpdate: (pos: { x: number; y: number }) => void
) {
  if (initialized) return
  initialized = true

  app = new Application()

  await app.init({
    width: window.innerWidth,
    height: window.innerHeight,
    backgroundAlpha: 0,
    antialias: true,
    resolution: window.devicePixelRatio || 1,
    autoDensity: true,
  })

  app.canvas.style.position = 'fixed'
  app.canvas.style.top = '0'
  app.canvas.style.left = '0'
  app.canvas.style.pointerEvents = 'none'
  app.canvas.style.zIndex = '0'

  container.appendChild(app.canvas)

  await loadPlaceholder(onPositionUpdate)
}

async function loadPlaceholder(
  onPositionUpdate: (pos: { x: number; y: number }) => void
) {
  const chibi = new Graphics()
  chibi.circle(0, 0, 40)
  chibi.fill(0x7c6dfa)
  chibi.x = window.innerWidth / 2
  chibi.y = window.innerHeight - 100
  app.stage.addChild(chibi)

  steering = new SteeringController(
    chibi.x,
    chibi.y,
    window.innerWidth,
    window.innerHeight,
    (pos, facingLeft) => {
      chibi.x = pos.x
      chibi.y = pos.y
      chibi.scale.x = facingLeft ? -1 : 1
      onPositionUpdate({ x: pos.x, y: window.innerHeight - pos.y })
    }
  )

  steering.startWander()

  app.ticker.add(({ deltaMS }) => {
    const dt = deltaMS / 1000
    steering.update(dt)
  })
}

export function getSteering() { return steering }
export function getApp() { return app }