import { useEffect, useRef, useState } from 'react'
import { useMachine } from '@xstate/react'
import { companionMachine } from './renderer/machine'
import { initPixi, getSteering } from './renderer/pixi'
import { connectSocket, sendToBackend } from './renderer/socket'
import { InteractionSystem } from './renderer/interaction'
import { playTTS, stopAudio } from './renderer/audio'
import SpeechBubble from './renderer/speechbubble'

export default function App() {
  const initialized = useRef(false)
  const [state, send] = useMachine(companionMachine)
  const [chibiPos, setChibiPos] = useState({
    x: window.innerWidth / 2,
    y: window.innerHeight - 100,
  })
  const [bubbleText, setBubbleText] = useState('')
  const [bubbleVisible, setBubbleVisible] = useState(false)
  const bubbleDismissTimer = useRef<ReturnType<typeof setTimeout> | null>(null)


  const idleTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const SLEEP_AFTER = 10 * 60 * 1000 // 10 minutes

  const isDragging = useRef(false)
  const dragOffset = useRef({ x: 0, y: 0 })
  const pokeTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const pokeReactions = [
    'hey!!', 'kyaa~', 'stop that!', 'oww!',
    'hmph!', '(>_<)', 'not now~', 'heyyy!'
  ]

  const dragReactions = ['wheee~', 'waaah!', 'put me down!', 'woooah~']
  const dropReactions = ['oof!', 'that was fun~', 'again!', 'dizzy...']

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
    window.addEventListener('mousemove', resetIdleTimer)
    window.addEventListener('keydown', resetIdleTimer)
    resetIdleTimer()
    return () => {
      window.removeEventListener('mousemove', resetIdleTimer)
      window.removeEventListener('keydown', resetIdleTimer)
    }
  }, [])
  function onMouseDown(e: React.MouseEvent) {
    e.preventDefault()
    isDragging.current = true

    const steering = getSteering()
    steering?.stopWander()
    steering?.disableCursorFollow?.()

    // offset so chibi doesn't snap to cursor center
    dragOffset.current = {
      x: e.clientX - chibiPos.x,
      y: e.clientY - (window.innerHeight - chibiPos.y),
    }

    // start drag reaction after holding 200ms
    pokeTimer.current = setTimeout(() => {
      if (isDragging.current) {
        showBubble(dragReactions[Math.floor(Math.random() * dragReactions.length)], 1500)
      }
    }, 200)

    window.addEventListener('mousemove', onDrag)
    window.addEventListener('mouseup', onMouseUp)
  }

  function onDrag(e: MouseEvent) {
    if (!isDragging.current) return

    const newX = e.clientX - dragOffset.current.x
    const newY = e.clientY - dragOffset.current.y

    // clamp to screen
    const clampedX = Math.max(40, Math.min(newX, window.innerWidth - 40))
    const clampedY = Math.max(40, Math.min(newY, window.innerHeight - 80))

    // move the pixi sprite directly
    const steering = getSteering()
    if (steering) {
      steering.pos.x = clampedX
      steering.pos.y = window.innerHeight - clampedY
      steering.onMoveExternal?.(
        { x: clampedX, y: window.innerHeight - clampedY },
        e.movementX < 0
      )
    }

    setChibiPos({ x: clampedX, y: clampedY })
  }

  function onMouseUp(e: MouseEvent) {
    window.removeEventListener('mousemove', onDrag)
    window.removeEventListener('mouseup', onMouseUp)

    if (pokeTimer.current) clearTimeout(pokeTimer.current)

    const wasDragging = isDragging.current
    isDragging.current = false

    const dragDist = Math.sqrt(
      Math.pow(e.clientX - chibiPos.x, 2) +
      Math.pow(e.clientY - (window.innerHeight - chibiPos.y), 2)
    )

    if (dragDist < 10) {
      // it was a poke, not a drag
      onPoke()
    } else {
      // it was a drop
      showBubble(dropReactions[Math.floor(Math.random() * dropReactions.length)], 1500)
      // resume wandering after a beat
      setTimeout(() => {
        getSteering()?.startWander()
        send({ type: 'WANDER_START' })
      }, 1800)
    }
  }

  function onPoke() {
    const reaction = pokeReactions[Math.floor(Math.random() * pokeReactions.length)]
    showBubble(reaction, 1500)

    // little bounce — move her slightly then back
    const steering = getSteering()
    if (!steering) return

    const bounceX = steering.pos.x + (Math.random() - 0.5) * 60
    const bounceY = steering.pos.y + (Math.random() - 0.5) * 40

    steering.goTo(bounceX, bounceY, () => {
      setTimeout(() => steering.startWander(), 800)
    })
  }
  function showBubble(text: string, duration?: number) {
    setBubbleText(text)
    setBubbleVisible(true)
    if (bubbleDismissTimer.current) clearTimeout(bubbleDismissTimer.current)
    const ms = duration ?? Math.max(2000, text.length * 50)
    bubbleDismissTimer.current = setTimeout(() => {
      setBubbleVisible(false)
      send({ type: 'SPEECH_END' })
    }, ms)
  }

  useEffect(() => {
    if (initialized.current) return
    initialized.current = true

    const container = document.getElementById('pixi-root')!
    initPixi(container, setChibiPos).then(() => {
      const interaction = new InteractionSystem(
        getSteering(),
        (icon) => {
          // after arriving at icon, resume wander
          setTimeout(() => {
            getSteering()?.startWander()
            send({ type: 'WANDER_START' })
          }, 2500)
        },
        (text) => {
          // local speech from interaction (no audio)
          showBubble(text, 2500)
          send({ type: 'SPEECH' })
        }
      )

      ;(window as any).interaction = interaction
    })

    connectSocket((event) => {
      send(event)

      if (event.type === 'NAVIGATE') {
        getSteering()?.goTo(event.x, event.y, () => {
          showBubble(event.label ? `reached ${event.label}~` : 'here!', 2000)
          setTimeout(() => {
            getSteering()?.startWander()
            send({ type: 'WANDER_START' })
          }, 2500)
        })
      }

      if (event.type === 'WANDER_START') getSteering()?.startWander()
      if (event.type === 'WANDER_STOP') getSteering()?.stopWander()
    })
  }, [])

  // audio playback
  useEffect(() => {
    if (state.matches('speaking')) {
      const { audioUrl, speechText } = state.context
      if (audioUrl) {
        showBubble(speechText)
        playTTS(audioUrl, () => send({ type: 'SPEECH_END' }))
      } else if (speechText) {
        showBubble(speechText)
      }
    }
    if (state.matches('idle')) stopAudio()
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
        pointerEvents: 'none',
      }} />
      {/* Invisible interaction hitbox over chibi position */}
      <div
        onMouseDown={onMouseDown}
        style={{
          position: 'fixed',
          left: chibiPos.x - 40,
          bottom: chibiPos.y - 40,
          width: 80,
          height: 100,
          pointerEvents: 'auto',
          cursor: isDragging.current ? 'grabbing' : 'grab',
          zIndex: 50,
          // background: 'rgba(255,0,0,0.2)', // uncomment to debug hitbox
        }}
      />
      <SpeechBubble
        text={bubbleText}
        chibiX={chibiPos.x}
        chibiY={chibiPos.y}
        visible={bubbleVisible}
      />
    </>
  )
}