import { Howl } from 'howler'

let currentSound: Howl | null = null

export function playTTS(url: string, onEnd?: () => void) {
  // stop anything currently playing
  currentSound?.stop()

  currentSound = new Howl({
    src: [url],
    format: ['mp3', 'wav'],
    html5: true, // streaming
    onend: () => {
      onEnd?.()
    },
    onplayerror: (e) => {
      console.error('audio error:', e)
      onEnd?.()
    },
  })

  currentSound.play()
}

export function stopAudio() {
  currentSound?.stop()
  currentSound = null
}