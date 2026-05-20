type EventHandler = (event: any) => void

let socket: WebSocket | null = null
let onEventCallback: EventHandler | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let shouldReconnect = true

const WS_URL = 'ws://localhost:8000/ws'

export function connectSocket(onEvent: EventHandler) {
  disconnectSocket()
  shouldReconnect = true
  onEventCallback = onEvent
  connect()
}

function connect() {
  console.log('connecting to backend...')
  socket = new WebSocket(WS_URL)

  socket.onopen = () => {
    console.log('backend connected')
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
  }

  socket.onmessage = (msg) => {
    try {
      const event = JSON.parse(msg.data)
      if (event.type === 'PING') return
      if (event.type === 'SPEECH_CHUNK') {
        onEventCallback?.({ type: 'SPEECH_CHUNK', text: event.text })
        return
      }
      console.log('event received:', event)
      onEventCallback?.(event)
    } catch (e) {
      console.error('failed to parse event:', e)
    }
  }
  socket.onclose = () => {
    if (!shouldReconnect) return

    console.log('backend disconnected, retrying in 3s...')
    reconnectTimer = setTimeout(connect, 3000)
  }

  socket.onerror = (e) => {
    console.error('socket error:', e)
  }
}

export function sendToBackend(data: object) {
  if (socket?.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(data))
  }
}

export function disconnectSocket() {
  shouldReconnect = false
  onEventCallback = null
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  socket?.close()
  socket = null
}
