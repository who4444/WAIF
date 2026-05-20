import { useEffect, useRef } from 'react'
import { useMachine } from '@xstate/react'
import { companionMachine } from './renderer/machine'
import { initPixi, destroyPixi, getSteering, setPlaceholderState } from './renderer/pixi'
import { connectSocket, disconnectSocket, sendToBackend } from './renderer/socket'
import { InteractionSystem } from './renderer/interaction'
import { playTTS, stopAudio } from './renderer/audio'
import { onStateChange, playPoke } from './renderer/animator'


export default function App() {
  const [state, send] = useMachine(companionMachine)

  const idleTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const SLEEP_AFTER = 10 * 60 * 1000 // 10 minutes
  const wanderTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const currentStateValue = useRef(state.value)

  function resetIdleTimer() {
    if (idleTimer.current) clearTimeout(idleTimer.current)
    idleTimer.current = setTimeout(() => {
      send({ type: 'SLEEP' })
      getSteering()?.stopWander()
      // walk to corner
      getSteering()?.goTo(window.innerWidth - 80, window.innerHeight - 80)
    }, SLEEP_AFTER)
  }
  useEffect(() => {
    currentStateValue.current = state.value
    onStateChange(state.value as string)
    setPlaceholderState(state.value as string)  // circle color changes with state
  }, [state.value])

  useEffect(() => {
    function scheduleWander(initial = false) {
      const delay = initial ? 6_000 + Math.random() * 6_000 : 20_000 + Math.random() * 35_000
      wanderTimer.current = setTimeout(() => {
        if (currentStateValue.current === 'idle') {
          getSteering()?.wanderOnce()
        }
        scheduleWander()
      }, delay)
    }

    scheduleWander(true)
    return () => {
      if (wanderTimer.current) clearTimeout(wanderTimer.current)
    }
  }, [])

  useEffect(() => {
    window.addEventListener('mousemove', resetIdleTimer)
    window.addEventListener('keydown', resetIdleTimer)
    resetIdleTimer()
    return () => {
      window.removeEventListener('mousemove', resetIdleTimer)
      window.removeEventListener('keydown', resetIdleTimer)
    }
  }, [])
  function onPoke() {
    playPoke()
    const steering = getSteering()
    if (!steering) return

    const bounceX = steering.pos.x + (Math.random() - 0.5) * 60
    const bounceY = steering.pos.y + (Math.random() - 0.5) * 40

    steering.goTo(bounceX, bounceY)
  }

  function onInteraction(type: 'poke' | 'drag' | 'drop') {
    if (type === 'poke') {
      onPoke()
    }
  }

  useEffect(() => {
    const container = document.getElementById('pixi-root')!
    initPixi(container, () => {}, onInteraction).then(() => {
      const interaction = new InteractionSystem(
        getSteering(),
        (_icon) => { /* arrival handled by NAVIGATE event */ },
        (_text) => {}
      )

      ;(window as any).interaction = interaction
    })

    connectSocket((event) => {
      if (event.type === 'SPEECH_CHUNK') {
        return
      }

      send(event)

      if (event.type === 'NAVIGATE') {
        getSteering()?.goTo(event.x, event.y)
      }
    })

    return () => {
      disconnectSocket()
      destroyPixi()
    }
  }, [])

  // audio playback
  useEffect(() => {
    if (state.matches('speaking')) {
      const { audioUrl } = state.context
      if (audioUrl) {
        playTTS(audioUrl, () => send({ type: 'SPEECH_END' }))
      } else {
        send({ type: 'SPEECH_END' })
      }
    }
    if (state.matches('idle')) stopAudio()
  }, [state.value])

  useEffect(() => {
    console.log('state', state.value)
  }, [state.value])

  useEffect(() => {
    ;(window as any).send = send

    ;(window as any).goTo = (x: number, y: number) => getSteering()?.goTo(x, y)
    ;(window as any).wander = () => getSteering()?.startWander()
    ;(window as any).sendToBackend = sendToBackend
  }, [send])

  return (
    <>
      <div id="pixi-root" style={{
        position: 'fixed',
        top: 0, left: 0,
        width: '100vw', height: '100vh',
        pointerEvents: 'auto',
      }} />
    </>
  )
}
