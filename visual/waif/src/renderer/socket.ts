type EventHandler = (event: any) => void

let socket: WebSocket | null = null
let onEventCallback: EventHandler | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null

const WS_URL = 'ws://localhost:8000/ws'

export function connectSocket(onEvent: EventHandler) {
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
      console.log('event received:', event)
      onEventCallback?.(event)
    } catch (e) {
      console.error('failed to parse event:', e)
    }
  }

  socket.onclose = () => {
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
  if (reconnectTimer) clearTimeout(reconnectTimer)
  socket?.close()
  socket = null
}