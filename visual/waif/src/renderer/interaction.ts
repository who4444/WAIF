import { SteeringController } from './steering'

export interface IconTarget {
  id: string
  label: string
  x: number
  y: number
}

const INTERACT_RADIUS = 80

export class InteractionSystem {
  private steering: SteeringController
  private onInteractComplete: (icon: IconTarget) => void
  private onSpeech: (text: string) => void

  constructor(
    steering: SteeringController,
    onInteractComplete: (icon: IconTarget) => void,
    onSpeech: (text: string) => void
  ) {
    this.steering = steering
    this.onInteractComplete = onInteractComplete
    this.onSpeech = onSpeech
  }

  goToIcon(icon: IconTarget) {
    // convert screen coords to nav coords
    // icons come from backend as screen pixel positions
    const targetX = icon.x
    const targetY = icon.y

    this.steering.goTo(targetX, targetY, () => {
      this.onArrive(icon)
    })
  }

  private onArrive(icon: IconTarget) {
    // play reach animation (placeholder — log for now)
    console.log('arrived at:', icon.label)

    // say something
    const quips: Record<string, string[]> = {
      default: ['hello~', 'found it!', 'here we go!'],
      spotify: ['music time~', 'la la la~', 'play something good!'],
      vscode: ['coding time!', 'let me peek at the code~', 'ooh bugs!'],
      browser: ['surfing the web~', 'what are we searching?'],
      discord: ['checking messages~', 'anyone online?'],
    }

    const key = icon.label.toLowerCase()
    const lines = quips[key] ?? quips.default
    const text = lines[Math.floor(Math.random() * lines.length)]

    this.onSpeech(text)
    this.onInteractComplete(icon)
  }
}